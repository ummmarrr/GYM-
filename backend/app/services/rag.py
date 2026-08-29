"""The approved-document knowledge base, stored in Postgres with pgvector.

Chunks live in the same database as everything else, so a search filters by discipline and
ranks by similarity in one query, and the knowledge base survives a redeploy on a host with
no persistent disk.

Retrieval is hybrid: semantic (embeddings) fused with lexical keyword hits via Reciprocal
Rank Fusion, then still package-filtered in SQL before ranking.
"""

from __future__ import annotations

import hashlib
import logging
import re
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.db import KnowledgeChunk
from app.services.embeddings import EmbeddingUnavailable, GeminiEmbedder
from app.services.pdf_extract import extract_pdf

logger = logging.getLogger(__name__)

CHUNK_SIZE = 1200
CHUNK_OVERLAP = 180
MIN_CHUNK_CHARS = 100
HYBRID_CANDIDATE_LIMIT = 12
RRF_K = 60


@dataclass(frozen=True)
class RetrievedChunk:
    text: str
    source: str
    page: int | None
    kind: str = "text"


@dataclass(frozen=True)
class IngestResult:
    document_hash: str
    chunk_count: int
    already_present: bool
    ingest_mode: str = "direct"


class KnowledgeBase:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.embedder = GeminiEmbedder()

    @staticmethod
    def chunk_text(text: str, chunk_size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP):
        clean = " ".join(text.split())
        step = chunk_size - overlap
        return [
            clean[i : i + chunk_size]
            for i in range(0, len(clean), step)
            if clean[i : i + chunk_size]
        ]

    @staticmethod
    def hash_file(path: Path) -> str:
        return hashlib.sha256(path.read_bytes()).hexdigest()

    def _already_ingested(self, document_hash: str) -> bool:
        return (
            self.db.scalar(
                select(func.count())
                .select_from(KnowledgeChunk)
                .where(KnowledgeChunk.document_hash == document_hash)
            )
            or 0
        ) > 0

    def ingest_pdf(self, path: Path, discipline: str) -> IngestResult:
        document_hash = self.hash_file(path)
        if self._already_ingested(document_hash):
            return IngestResult(document_hash, 0, already_present=True)

        extracted = extract_pdf(path)
        passages = [
            passage
            for passage in extracted.passages
            if len(passage.text.strip()) >= MIN_CHUNK_CHARS
            or passage.kind.startswith("image")
            or passage.kind == "table"
        ]
        # Tables / short image captions may be under MIN_CHUNK_CHARS — keep those with a floor.
        passages = [
            p
            for p in passages
            if len(p.text.strip()) >= (20 if p.kind != "text" else MIN_CHUNK_CHARS)
        ]

        if not passages:
            return IngestResult(
                document_hash, 0, already_present=False, ingest_mode=extracted.ingest_mode
            )

        vectors = self.embedder.embed_documents([passage.text for passage in passages])
        self.db.add_all(
            KnowledgeChunk(
                document_hash=document_hash,
                source=path.name,
                page=passage.page,
                discipline=discipline,
                kind=passage.kind,
                content=passage.text,
                embedding=vector,
            )
            for passage, vector in zip(passages, vectors, strict=True)
        )
        self.db.flush()
        return IngestResult(
            document_hash,
            len(passages),
            already_present=False,
            ingest_mode=extracted.ingest_mode,
        )

    def delete_document(self, document_hash: str) -> None:
        self.db.execute(
            delete(KnowledgeChunk).where(KnowledgeChunk.document_hash == document_hash)
        )

    @staticmethod
    def _query_tokens(query: str) -> list[str]:
        return [token for token in re.findall(r"[a-z0-9]+", query.lower()) if len(token) >= 3]

    def _keyword_rank(
        self, query: str, disciplines: tuple[str, ...], limit: int
    ) -> list[KnowledgeChunk]:
        tokens = self._query_tokens(query)
        if not tokens or not disciplines:
            return []
        rows = self.db.scalars(
            select(KnowledgeChunk).where(KnowledgeChunk.discipline.in_(disciplines))
        ).all()
        scored: list[tuple[int, int, KnowledgeChunk]] = []
        for row in rows:
            hay = row.content.lower()
            hits = sum(1 for token in tokens if token in hay)
            if hits:
                # Prefer more token hits, then denser (shorter) passages.
                scored.append((hits, -len(row.content), row))
        scored.sort(key=lambda item: (item[0], item[1]), reverse=True)
        return [row for _, _, row in scored[:limit]]

    def _semantic_rank(
        self, query: str, disciplines: tuple[str, ...], limit: int
    ) -> list[KnowledgeChunk]:
        try:
            embedded = self.embedder.embed_query(query)
        except EmbeddingUnavailable:
            logger.warning("Semantic leg skipped; query could not be embedded")
            return []
        return list(
            self.db.scalars(
                select(KnowledgeChunk)
                .where(KnowledgeChunk.discipline.in_(disciplines))
                .order_by(KnowledgeChunk.embedding.cosine_distance(embedded))
                .limit(limit)
            ).all()
        )

    @staticmethod
    def _rrf_fuse(
        ranked_lists: list[list[KnowledgeChunk]], limit: int
    ) -> list[KnowledgeChunk]:
        scores: dict[str, float] = defaultdict(float)
        by_id: dict[str, KnowledgeChunk] = {}
        for ranked in ranked_lists:
            for rank, row in enumerate(ranked, start=1):
                scores[row.id] += 1.0 / (RRF_K + rank)
                by_id[row.id] = row
        ordered = sorted(scores, key=scores.get, reverse=True)
        return [by_id[chunk_id] for chunk_id in ordered[:limit]]

    def retrieve(self, query: str, disciplines, limit: int = 3) -> list[RetrievedChunk]:
        """Hybrid retrieve: keyword + semantic, fused with RRF, filtered by package shelf.

        Filtering happens in SQL rather than after ranking, so a member on a gym-only package
        cannot have their answer shaped by a document their package does not include.
        """
        allowed = tuple(disciplines)
        if not allowed:
            return []

        available = self.db.scalar(
            select(func.count())
            .select_from(KnowledgeChunk)
            .where(KnowledgeChunk.discipline.in_(allowed))
        )
        if not available:
            return []

        candidate_limit = max(limit * 4, HYBRID_CANDIDATE_LIMIT)
        keyword_hits = self._keyword_rank(query, allowed, candidate_limit)
        semantic_hits = self._semantic_rank(query, allowed, candidate_limit)

        if not keyword_hits and not semantic_hits:
            return []
        if not keyword_hits:
            fused = semantic_hits[:limit]
        elif not semantic_hits:
            fused = keyword_hits[:limit]
        else:
            fused = self._rrf_fuse([keyword_hits, semantic_hits], limit)

        return [
            RetrievedChunk(
                text=row.content,
                source=row.source,
                page=row.page,
                kind=getattr(row, "kind", None) or "text",
            )
            for row in fused
        ]
