"""The approved-document knowledge base, stored in Postgres with pgvector.

Chunks live in the same database as everything else, so a search filters by discipline and
ranks by similarity in one query, and the knowledge base survives a redeploy on a host with
no persistent disk.
"""

import hashlib
import logging
from dataclasses import dataclass
from pathlib import Path

import pymupdf
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.db import KnowledgeChunk
from app.services.embeddings import EmbeddingUnavailable, GeminiEmbedder

logger = logging.getLogger(__name__)

CHUNK_SIZE = 1200
CHUNK_OVERLAP = 180
MIN_CHUNK_CHARS = 100


@dataclass(frozen=True)
class RetrievedChunk:
    text: str
    source: str
    page: int | None


@dataclass(frozen=True)
class IngestResult:
    document_hash: str
    chunk_count: int
    already_present: bool


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

        document = pymupdf.open(path)
        passages: list[tuple[str, str, int]] = []
        for page_number, page in enumerate(document, start=1):
            page_text = page.get_text()
            # Parent chunks (size 1800, overlap 360)
            parents = self.chunk_text(page_text, chunk_size=1800, overlap=360)
            for parent in parents:
                # Child chunks (size 600, overlap 120)
                children = self.chunk_text(parent, chunk_size=600, overlap=120)
                for child in children:
                    if len(child) >= MIN_CHUNK_CHARS:
                        passages.append((child, parent, page_number))

        if not passages:
            return IngestResult(document_hash, 0, already_present=False)

        is_sqlite = (self.db.bind.dialect.name == "sqlite")
        vectors = self.embedder.embed_documents([child for child, _, _ in passages])
        self.db.add_all(
            KnowledgeChunk(
                document_hash=document_hash,
                source=path.name,
                page=page_number,
                discipline=discipline,
                content=child,
                parent_content=parent,
                embedding=str(vector) if is_sqlite else vector,
            )
            for (child, parent, page_number), vector in zip(passages, vectors, strict=True)
        )
        self.db.flush()
        return IngestResult(document_hash, len(passages), already_present=False)

    def delete_document(self, document_hash: str) -> None:
        self.db.execute(
            delete(KnowledgeChunk).where(KnowledgeChunk.document_hash == document_hash)
        )

    def retrieve(self, query: str, disciplines, limit: int = 3) -> list[RetrievedChunk]:
        """Return the closest passages the caller is allowed to see.

        Filtering happens in SQL rather than after ranking, so a member on a gym-only package
        cannot have their answer shaped by a document their package does not include.
        """
        allowed = tuple(disciplines)
        if not allowed:
            return []

        # Checking for candidates first avoids spending an embedding call on an empty shelf.
        available = self.db.scalar(
            select(func.count())
            .select_from(KnowledgeChunk)
            .where(KnowledgeChunk.discipline.in_(allowed))
        )
        if not available:
            return []

        try:
            embedded = self.embedder.embed_query(query)
        except EmbeddingUnavailable:
            logger.warning("Answering without documents because the query could not be embedded")
            return []

        is_postgres = (self.db.bind.dialect.name == "postgresql")
        if is_postgres:
            ts_query = func.plainto_tsquery("english", query)
            ts_vector = func.to_tsvector("english", KnowledgeChunk.content)
            ts_rank = func.ts_rank_cd(ts_vector, ts_query)
            
            # cosine_distance is 0 to 2, smaller is closer.
            # ts_rank is 0 to 1, larger is closer.
            # combined_score = 0.7 * cosine_distance - 0.3 * ts_rank.
            # Since we want to order by combined_score ascending:
            # smaller score is better (smaller cosine_distance, larger ts_rank).
            combined_score = 0.7 * KnowledgeChunk.embedding.cosine_distance(embedded) - 0.3 * ts_rank
            
            rows = self.db.scalars(
                select(KnowledgeChunk)
                .where(KnowledgeChunk.discipline.in_(allowed))
                .order_by(combined_score)
                .limit(limit)
            ).all()
        else:
            # SQLite / Fallback
            rows = self.db.scalars(
                select(KnowledgeChunk)
                .where(KnowledgeChunk.discipline.in_(allowed))
            ).all()

            # Python keyword and cosine distance fallback for SQLite re-ranking
            query_words = set(query.lower().split())
            
            def get_hybrid_score(row):
                try:
                    emb = row.embedding
                    if isinstance(emb, str):
                        emb = [float(x) for x in emb.strip('[]').split(',') if x.strip()]
                    
                    if emb and isinstance(emb, list) and isinstance(embedded, list):
                        cos_sim = sum(a * b for a, b in zip(emb, embedded))
                        cos_dist = 1.0 - cos_sim
                    else:
                        cos_dist = 1.0
                except Exception:
                    cos_dist = 1.0
                
                overlap = 0.0
                if query_words:
                    content_words = set(row.content.lower().split())
                    overlap = len(query_words & content_words) / len(query_words)
                
                return 0.7 * cos_dist - 0.3 * overlap

            rows = sorted(rows, key=get_hybrid_score)[:limit]

        return [
            RetrievedChunk(text=row.parent_content or row.content, source=row.source, page=row.page) for row in rows
        ]
