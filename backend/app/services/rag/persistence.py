"""
backend/app/services/rag/persistence.py

MySQL persistence service for RAG document chunks.

Handles staging chunks, error tracking, and zero-downtime version activation.
All database writes are short transactions; S3/Gemini/Qdrant calls happen outside.
"""
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.core.config import settings
from app.database.db_models import DocumentChunk, FileMetadata, UserCorpusState
from app.schemas.enums import IndexingStatus
from app.services.rag.document_processor import NoExtractableTextError, PdfExtractionError, ProcessedDocument
from app.services.rag.ids import build_chunk_id
from botocore.exceptions import BotoCoreError, ClientError


# ── Error code constants ──────────────────────────────────────────────────────
ERROR_OBJECT_NOT_FOUND = "OBJECT_NOT_FOUND"
ERROR_PDF_TOO_LARGE = "PDF_TOO_LARGE"
ERROR_PDF_READ_FAILED = "PDF_READ_FAILED"
ERROR_PDF_PARSE_FAILED = "PDF_PARSE_FAILED"
ERROR_NO_EXTRACTABLE_TEXT = "NO_EXTRACTABLE_TEXT"
ERROR_CHUNKING_FAILED = "CHUNKING_FAILED"


def next_rag_index_version(file: FileMetadata) -> int:
    """Calculate the next RAG index version for a file.

    Uses active_index_version as the baseline (not index_version which is for metadata vectors).
    """
    return int(file.active_index_version or 0) + 1


def map_rag_exception(exc: Exception) -> tuple[str, str, bool]:
    """Map Phase 2 exceptions to (error_code, error_message, retryable).

    Returns:
        tuple: (error_code, error_message, retryable)
    """
    if isinstance(exc, FileNotFoundError):
        return ERROR_OBJECT_NOT_FOUND, "S3 object not found", False
    if isinstance(exc, ValueError) and "too large" in str(exc).lower():
        return ERROR_PDF_TOO_LARGE, "PDF exceeds maximum size", False
    if isinstance(exc, PdfExtractionError):
        return ERROR_PDF_PARSE_FAILED, "Failed to parse PDF", False
    if isinstance(exc, NoExtractableTextError):
        return ERROR_NO_EXTRACTABLE_TEXT, "Scanned/image-only PDF", False
    if isinstance(exc, (BotoCoreError, ClientError)):
        return ERROR_PDF_READ_FAILED, "Storage read failed", True
    return ERROR_CHUNKING_FAILED, "Internal chunking error", False


def mark_rag_failure(
    db: Session,
    file: FileMetadata,
    code: str,
    message: str,
    retryable: bool,
) -> None:
    """Persist a RAG failure to file_metadata.

    Args:
        db: Database session.
        file: FileMetadata row to update.
        code: Error code (max 64 chars).
        message: Error message (max 500 chars).
        retryable: Whether the failure is retryable.
    """
    file.indexing_status = (
        IndexingStatus.FAILED_RETRYABLE.value
        if retryable
        else IndexingStatus.FAILED_TERMINAL.value
    )
    file.rag_error_code = code[:64]
    file.rag_error_message = message[:500]
    db.commit()


def stage_document_chunks(
    db: Session,
    file: FileMetadata,
    processed: ProcessedDocument,
) -> int:
    """Insert chunk rows for a new index version and mark file as CHUNKED.

    Does NOT activate the version. Call activate_rag_index_version() after
    Phase 4 verifies Qdrant upserts.

    Args:
        db: Database session.
        file: FileMetadata row (already loaded in this session).
        processed: ProcessedDocument from Phase 2 pipeline.

    Returns:
        The new index_version that was staged.
    """
    new_version = next_rag_index_version(file)

    # Defensive cleanup: delete any existing chunks for this file/version
    # (handles retries where the same version is re-staged)
    db.query(DocumentChunk).filter(
        DocumentChunk.file_id == file.fileid,
        DocumentChunk.index_version == new_version,
    ).delete(synchronize_session=False)

    rows = []
    for chunk in processed.chunks:
        rows.append(
            DocumentChunk(
                file_id=file.fileid,
                user_id=file.userid,
                index_version=new_version,
                chunk_index=chunk.chunk_index,
                chunk_id=str(build_chunk_id(file.fileid, new_version, chunk.chunk_index)),
                page_start=chunk.page_start,
                page_end=chunk.page_end,
                word_start=chunk.word_start,
                word_end=chunk.word_end,
                word_count=chunk.word_count,
                text_checksum=chunk.text_checksum,
                clean_text=chunk.clean_text,
                extraction_version=settings.RAG_EXTRACTION_VERSION,
                cleaning_version=settings.RAG_CLEANING_VERSION,
                chunking_version=settings.RAG_CHUNKING_VERSION,
                embedding_model=settings.GEMINI_EMBEDDING_MODEL,
                embedding_dimensions=settings.EMBEDDING_DIMENSIONS,
                source_key=file.s3_key,
                original_filename=file.filename,
            )
        )

    db.add_all(rows)

    file.indexing_status = IndexingStatus.CHUNKED.value
    file.page_count = processed.page_count
    file.extracted_word_count = processed.extracted_word_count
    file.chunk_count = len(processed.chunks)
    file.indexed_chunk_count = 0
    file.extraction_version = settings.RAG_EXTRACTION_VERSION
    file.cleaning_version = settings.RAG_CLEANING_VERSION
    file.chunking_version = settings.RAG_CHUNKING_VERSION
    file.embedding_model = settings.GEMINI_EMBEDDING_MODEL
    file.embedding_dimensions = settings.EMBEDDING_DIMENSIONS
    file.rag_error_code = None
    file.rag_error_message = None

    db.commit()
    return new_version


def activate_rag_index_version(
    db: Session,
    file: FileMetadata,
    index_version: int,
    indexed_chunk_count: int,
) -> None:
    """Atomically activate a staged index version and increment corpus revision.

    This is the zero-downtime cutover: queries see either old complete version
    or new complete version, never partial data.

    Args:
        db: Database session.
        file: FileMetadata row (already loaded in this session).
        index_version: The version to activate (must exist in document_chunks).
        indexed_chunk_count: Number of chunks successfully upserted to Qdrant.

    Raises:
        ValueError: If version has zero chunks or count mismatch.
    """
    chunk_count = db.query(DocumentChunk).filter(
        DocumentChunk.file_id == file.fileid,
        DocumentChunk.index_version == index_version,
    ).count()

    if chunk_count == 0:
        raise ValueError("Cannot activate an index version with zero chunks.")
    if indexed_chunk_count != chunk_count:
        raise ValueError("Cannot activate before every chunk is indexed.")

    state = db.get(UserCorpusState, file.userid)
    if state is None:
        state = UserCorpusState(user_id=file.userid, corpus_revision=0)
        db.add(state)

    state.corpus_revision += 1

    file.active_index_version = index_version
    file.indexed_chunk_count = indexed_chunk_count
    file.indexing_status = IndexingStatus.INDEXED.value
    file.indexing_completed_at = datetime.now(timezone.utc)
    file.corpus_revision = state.corpus_revision

    db.commit()