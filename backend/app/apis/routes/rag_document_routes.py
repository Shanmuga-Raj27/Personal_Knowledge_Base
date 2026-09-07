"""
backend/app/apis/routes/rag_document_routes.py

Phase 6 RAG document surface.

Uploads themselves go through the EXISTING /files presigned-upload flow
(POST /files/upload-url -> client uploads bytes directly to S3 ->
POST /files/upload-complete). This router is the RAG-facing contract on top:

    POST /documents                trigger RAG indexing for an owned file
                                   (identified by file_id OR s3_key)
    GET  /documents/{id}/index-status   polling endpoint for indexing progress
    GET  /documents/{id}/chunks         inspect chunk clean_text for a version

Tenant isolation: every lookup filters on current_user.id. No Qdrant, Gemini,
Redis, or raw SQL lives here.
"""
import logging

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth.auth_dependencies import get_current_user
from app.database import get_db
from app.database.db_models import FileMetadata, User
from app.schemas.enums import FileStatus, IndexingStatus
from app.services.rag.inspection import get_chunks, get_index_status
from app.services.rag.schemas import (
    RAGChunkInspection,
    RAGChunkListResponse,
    RAGIndexStatusResponse,
)
from app.workers.rag_worker import sync_rag_chunks_in_background

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/documents", tags=["rag-documents"])


class RAGDocumentTriggerRequest(BaseModel):
    """Request body to trigger RAG indexing for an already-uploaded file.

    Exactly one of ``file_id`` / ``s3_key`` must be provided. The actual S3
    upload uses the existing presigned-upload flow; this endpoint only
    schedules the ingestion worker for a file the user owns.
    """

    file_id: int | None = None
    s3_key: str | None = None


@router.post("", status_code=202)
async def trigger_rag_indexing(
    payload: RAGDocumentTriggerRequest,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Schedule RAG indexing for a user-owned document.

    Re-runs the full worker pipeline (extract -> clean -> chunk -> embed ->
    Qdrant cutover). Idempotent by worker claim: if another worker already
    holds the file, this scheduling is a no-op for that run.
    """
    if (payload.file_id is None) == (payload.s3_key is None):
        raise HTTPException(
            status_code=400,
            detail="Provide exactly one of file_id or s3_key.",
        )

    query = db.query(FileMetadata).filter(FileMetadata.userid == current_user.id)
    if payload.file_id is not None:
        db_file = query.filter(FileMetadata.fileid == payload.file_id).first()
    else:
        db_file = query.filter(FileMetadata.s3_key == payload.s3_key).first()

    if db_file is None:
        raise HTTPException(
            status_code=404,
            detail="Document not found or access denied.",
        )

    if db_file.status != FileStatus.ACTIVE.value:
        raise HTTPException(
            status_code=400,
            detail="Document is not active. Complete the upload before indexing.",
        )

    db_file.indexing_status = IndexingStatus.PENDING.value
    db_file.indexing_started_at = None
    db_file.rag_error_code = None
    db_file.rag_error_message = None
    db.commit()
    db.refresh(db_file)

    background_tasks.add_task(
        sync_rag_chunks_in_background,
        file_id=db_file.fileid,
        user_id=current_user.id,
    )

    return {
        "id": db_file.fileid,
        "filename": db_file.filename,
        "indexing_status": db_file.indexing_status,
    }


@router.get("/{file_id}/index-status", response_model=RAGIndexStatusResponse)
async def index_status(
    file_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Report indexing status + derived progress for an owned document."""
    result = get_index_status(db, current_user.id, file_id)
    if result is None:
        raise HTTPException(
            status_code=404,
            detail="Document not found or access denied.",
        )
    return result


@router.get("/{file_id}/chunks", response_model=RAGChunkListResponse)
async def list_chunks(
    file_id: int,
    index_version: int | None = Query(default=None, ge=0),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Inspect chunks for an owned document.

    Omitted index_version defaults to the document's active_index_version.
    """
    chunks = get_chunks(db, current_user.id, file_id, index_version)
    if chunks is None:
        raise HTTPException(
            status_code=404,
            detail="Document not found or access denied.",
        )

    fm = get_index_status(db, current_user.id, file_id)
    resolved_version = index_version if index_version is not None else fm["active_index_version"]

    return RAGChunkListResponse(
        file_id=file_id,
        index_version=resolved_version,
        chunks=[RAGChunkInspection(**c) for c in chunks],
        total=len(chunks),
    )