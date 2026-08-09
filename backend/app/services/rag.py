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
        passages: list[tuple[str, int]] = []
        for page_number, page in enumerate(document, start=1):
            for chunk in self.chunk_text(page.get_text()):
                if len(chunk) >= MIN_CHUNK_CHARS:
                    passages.append((chunk, page_number))

        if not passages:
            return IngestResult(document_hash, 0, already_present=False)

        vectors = self.embedder.embed_documents([text for text, _ in passages])
        self.db.add_all(
            KnowledgeChunk(
                document_hash=document_hash,
                source=path.name,
                page=page_number,
                discipline=discipline,
                content=text,
                embedding=vector,
            )
            for (text, page_number), vector in zip(passages, vectors, strict=True)
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

        rows = self.db.scalars(
            select(KnowledgeChunk)
            .where(KnowledgeChunk.discipline.in_(allowed))
            .order_by(KnowledgeChunk.embedding.cosine_distance(embedded))
            .limit(limit)
        ).all()
        return [
            RetrievedChunk(text=row.content, source=row.source, page=row.page) for row in rows
        ]
