"""
backend/app/services/rag/inspection.py

Thin service helpers for RAG document inspection (Phase 6).

Separates 'load data' from 'serialize HTTP'. The routes call get_index_status /
get_chunks and wrap the dicts in the Pydantic response models from schemas.py.
No SQLAlchemy queries live inside route handlers.

Every lookup is scoped by user_id (tenant isolation) and returns None when the
file is not owned by the caller, so the route can 404 independently of whether
the file exists at all.
"""
from sqlalchemy.orm import Session

from app.database.db_models import DocumentChunk, FileMetadata


def get_index_status(db: Session, user_id: int, file_id: int) -> dict | None:
    """Return status dict for a file owned by user_id, or None if absent."""
    fm = (
        db.query(FileMetadata)
        .filter(
            FileMetadata.fileid == file_id,
            FileMetadata.userid == user_id,
        )
        .first()
    )
    if fm is None:
        return None

    progress = _progress_for(fm.indexing_status)
    return {
        "file_id": fm.fileid,
        "filename": fm.filename,
        "indexing_status": fm.indexing_status,
        "active_index_version": fm.active_index_version,
        "corpus_revision": fm.corpus_revision,
        "progress": progress,
        "chunk_count": fm.chunk_count,
        "indexed_chunk_count": fm.indexed_chunk_count,
        "rag_error_code": fm.rag_error_code,
        "rag_error_message": fm.rag_error_message,
    }


def _progress_for(status: str) -> float:
    """Map lifecycle -> 0..1 progress for the client progress bar."""
    order = {
        "PENDING": 0.0,
        "EXTRACTING": 0.1,
        "CHUNKED": 0.35,
        "EMBEDDING": 0.6,
        "INDEXING": 0.85,
        "INDEXED": 1.0,
    }
    return order.get(status, 0.0)


def get_chunks(
    db: Session,
    user_id: int,
    file_id: int,
    index_version: int | None = None,
) -> list[dict] | None:
    """Return chunk inspection rows for an owned file.

    index_version defaults to the file's active_index_version.
    Returns None if the file is not owned by user_id; returns [] if no chunks.
    """
    fm = (
        db.query(FileMetadata)
        .filter(
            FileMetadata.fileid == file_id,
            FileMetadata.userid == user_id,
        )
        .first()
    )
    if fm is None:
        return None

    target = index_version if index_version is not None else fm.active_index_version
    rows = (
        db.query(DocumentChunk)
        .filter(
            DocumentChunk.file_id == file_id,
            DocumentChunk.user_id == user_id,
            DocumentChunk.index_version == target,
        )
        .order_by(DocumentChunk.chunk_index)
        .all()
    )
    return [
        {
            "chunk_id": r.chunk_id,
            "chunk_index": r.chunk_index,
            "index_version": r.index_version,
            "page_start": r.page_start,
            "page_end": r.page_end,
            "word_count": r.word_count,
            "word_start": r.word_start,
            "word_end": r.word_end,
            "clean_text": r.clean_text,
        }
        for r in rows
    ]