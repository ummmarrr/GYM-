"""Knowledge base administration. Only admins decide what FitBot is allowed to quote."""

import tempfile
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import require_admin
from app.db import AuditEvent, KnowledgeDocument, User, get_db
from app.schemas import DocumentResponse
from app.services.embeddings import EmbeddingUnavailable
from app.services.rag import KnowledgeBase

router = APIRouter(prefix="/admin/knowledge", tags=["knowledge"])

MAX_UPLOAD_BYTES = 20 * 1024 * 1024
ALLOWED_DISCIPLINES = {"gym", "yoga", "mma", "reception"}


@router.get("/documents", response_model=list[DocumentResponse])
def list_documents(
    current_user: Annotated[User, Depends(require_admin)],
    db: Annotated[Session, Depends(get_db)],
):
    return db.scalars(select(KnowledgeDocument).order_by(KnowledgeDocument.created_at.desc())).all()


@router.post("/documents", response_model=DocumentResponse, status_code=201)
async def upload_document(
    current_user: Annotated[User, Depends(require_admin)],
    db: Annotated[Session, Depends(get_db)],
    discipline: Annotated[str, Form()],
    file: Annotated[UploadFile, File()],
):
    if discipline not in ALLOWED_DISCIPLINES:
        raise HTTPException(
            status_code=400, detail=f"Discipline must be one of {sorted(ALLOWED_DISCIPLINES)}."
        )
    if not (file.filename or "").lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files can be ingested.")

    payload = await file.read()
    if len(payload) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="PDF is larger than the 20 MB limit.")

    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / Path(file.filename).name
        path.write_bytes(payload)
        try:
            result = KnowledgeBase(db).ingest_pdf(path, discipline)
        except EmbeddingUnavailable as unavailable:
            raise HTTPException(
                status_code=503,
                detail="The embedding service is unavailable, so this PDF could not be indexed.",
            ) from unavailable
        except RuntimeError as failed:
            # Scanned PDFs without a vision key, or other extract failures with a clear message.
            raise HTTPException(status_code=400, detail=str(failed)) from failed

    if result.already_present:
        existing = db.scalars(
            select(KnowledgeDocument).where(KnowledgeDocument.document_hash == result.document_hash)
        ).first()
        if existing:
            return existing
        raise HTTPException(
            status_code=409, detail="This document is already in the knowledge base."
        )

    document = KnowledgeDocument(
        filename=Path(file.filename).name,
        discipline=discipline,
        document_hash=result.document_hash,
        chunk_count=result.chunk_count,
        ingest_mode=result.ingest_mode,
        uploaded_by=current_user.id,
    )
    db.add(document)
    db.flush()
    db.add(
        AuditEvent(
            actor_id=current_user.id,
            action="knowledge.uploaded",
            resource_type="knowledge_document",
            resource_id=document.id,
            detail=(
                f"{document.filename} ({result.chunk_count} chunks, mode={result.ingest_mode})"
            ),
        )
    )
    db.commit()
    return document


@router.delete("/documents/{document_id}")
def delete_document(
    document_id: str,
    current_user: Annotated[User, Depends(require_admin)],
    db: Annotated[Session, Depends(get_db)],
):
    document = db.get(KnowledgeDocument, document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found.")

    KnowledgeBase(db).delete_document(document.document_hash)
    db.delete(document)
    db.add(
        AuditEvent(
            actor_id=current_user.id,
            action="knowledge.deleted",
            resource_type="knowledge_document",
            resource_id=document_id,
            detail=document.filename,
        )
    )
    db.commit()
    return {"message": f"{document.filename} removed from the knowledge base."}
