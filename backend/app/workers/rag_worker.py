"""
backend/app/workers/rag_worker.py

Background worker task for RAG chunking pipeline.

Separate from sync_vector_in_background to keep metadata indexing and RAG indexing
decoupled. Runs Phase 2 extraction/chunking, stages chunks to MySQL, then runs
Phase 4 embedding + Qdrant cutover (run_full_indexing).

Flow:
    claim file atomically
    │
    v
    run process_pdf_from_storage in threadpool
    │
    v
    stage_document_chunks in new session
    │
    v
    close session (release DB lock)
    │
    v
    open NEW session → run_full_indexing (Phase 4)
    │
    v
    handle errors / persist status
"""
import asyncio
import logging
from datetime import datetime, timezone

from fastapi.concurrency import run_in_threadpool

from app.core.config import settings
from app.database.database import SessionLocal
from app.database.db_models import FileMetadata, User
from app.schemas.enums import FileStatus, IndexingStatus
from app.services.AI.vector_service import upsert_file_vector
from app.services.rag.document_processor import process_pdf_from_storage, NoExtractableTextError
from app.services.rag.indexing_service import run_full_indexing
from app.services.rag.persistence import (
    stage_document_chunks,
    mark_rag_failure,
    map_rag_exception,
)


logger = logging.getLogger(__name__)


async def sync_rag_chunks_in_background(file_id: int, user_id: int) -> None:
    """Background worker task for RAG chunking pipeline.

    Separate path from sync_vector_in_background:
    - Metadata vector indexing runs unchanged (Phase 1-style Gemini embeddings → Qdrant)
    - RAG chunking runs here: bounded S3 reads → PyMuPDF → clean → 800/100-word chunks
    - Chunks staged to MySQL with version tracking
    - No Qdrant/Gemini calls in this phase (Phase 4 handles that)

    Atomic claim prevents two workers from processing the same file simultaneously.
    """
    async with _embedding_semaphore:
        db = SessionLocal()
        try:
            # ── Step 1: Atomic claim ─────────────────────────────────────────────
            # Only one worker should succeed in changing status from PENDING
            # (or FAILED_RETRYABLE) to EXTRACTING.
            updated = (
                db.query(FileMetadata)
                .filter(
                    FileMetadata.fileid == file_id,
                    FileMetadata.userid == user_id,
                    FileMetadata.indexing_status.in_([
                        IndexingStatus.PENDING.value,
                        IndexingStatus.FAILED_RETRYABLE.value,
                    ]),
                )
                .update(
                    {
                        FileMetadata.indexing_status: IndexingStatus.EXTRACTING.value,
                        FileMetadata.indexing_started_at: datetime.now(timezone.utc),
                    },
                    synchronize_session=False,
                )
            )
            db.commit()

            if updated != 1:
                logger.info(
                    "RAG worker: file %s already claimed by another worker.",
                    file_id,
                )
                return

            # ── Step 2: Load file for processing ─────────────────────────────────
            db_file = db.query(FileMetadata).filter(FileMetadata.fileid == file_id).first()
            if not db_file:
                logger.error("RAG worker: file %s not found after claim.", file_id)
                return

            # ── Step 3: Run Phase 2 pipeline in threadpool ───────────────────────
            # S3 + PDF extraction happen outside DB transaction.
            try:
                processed = await run_in_threadpool(
                    process_pdf_from_storage,
                    db_file.s3_key,
                )
            except NoExtractableTextError:
                logger.info(
                    "RAG worker: file_id=%s has no extractable text layer (scanned/image-only).",
                    file_id,
                )
                mark_rag_failure(
                    db=db,
                    file=db_file,
                    code="NO_EXTRACTABLE_TEXT",
                    message="PDF has no extractable text layer. It may be a scanned or image-only document.",
                    retryable=False,
                )
                # Reset status to PENDING so it can be reprocessed
                db_file.indexing_status = IndexingStatus.PENDING.value
                db_file.indexing_started_at = None
                db.commit()
                return
            except Exception as exc:
                code, message, retryable = map_rag_exception(exc)
                logger.warning(
                    "RAG worker: processing failed for file_id=%s: %s (%s)",
                    file_id,
                    exc,
                    code,
                )
                mark_rag_failure(
                    db=db,
                    file=db_file,
                    code=code,
                    message=message,
                    retryable=retryable,
                )
                # Reset status to PENDING so it can be reprocessed
                db_file.indexing_status = IndexingStatus.PENDING.value
                db_file.indexing_started_at = None
                db.commit()
                return

            # ── Step 4: Stage chunks in one transaction ──────────────────────────
            # DB work is short; no S3/PDF/Gemini/Qdrant inside.
            try:
                new_version = stage_document_chunks(
                    db=db,
                    file=db_file,
                    processed=processed,
                )
                logger.info(
                    "RAG worker: file_id=%s staged %d chunks as version %d.",
                    file_id,
                    len(processed.chunks),
                    new_version,
                )
            except Exception as exc:
                code, message, retryable = map_rag_exception(exc)
                logger.error(
                    "RAG worker: staging failed for file_id=%s: %s (%s)",
                    file_id,
                    exc,
                    code,
                )
                mark_rag_failure(
                    db=db,
                    file=db_file,
                    code=code,
                    message=message,
                    retryable=retryable,
                )
                return

            # ── Step 5: Close session (release DB lock) ────────────────────────
            # Chunks are staged; now release DB before Phase 4 network calls.
            # Capture staged version BEFORE commit/close: commit expires loaded
            # attributes and close detaches the instance, so reading
            # active_index_version afterwards would raise DetachedInstanceError.
            staged_version = db_file.active_index_version
            db.commit()
            db.close()

            logger.info(
                "RAG worker: file_id=%s staged %d chunks (version=%s). Starting indexing.",
                file_id,
                len(processed.chunks),
                staged_version,
            )

            # ── Step 6: Phase 4 — Embed + Upsert + Cutover ────────────────────
            # Open a NEW session. run_full_indexing uses short transactions
            # and with_retry-wrapped Gemini/Qdrant calls; no long DB lock held.
            index_db = SessionLocal()
            try:
                index_file = index_db.query(FileMetadata).filter(
                    FileMetadata.fileid == file_id
                ).first()
                if index_file is None:
                    logger.error("RAG worker: file %s missing for indexing.", file_id)
                    return

                result = await run_in_threadpool(
                    run_full_indexing,
                    index_db,
                    index_file,
                )

                logger.info(
                    "RAG worker: file_id=%s indexing success=%s active_version=%s",
                    file_id,
                    result.get("success"),
                    result.get("active_index_version"),
                )

                if not result.get("success"):
                    # run_full_indexing already set FAILED_RETRYABLE + error codes
                    logger.warning(
                        "RAG worker: file_id=%s indexing did not complete successfully.",
                        file_id,
                    )

            except Exception as exc:
                code, message, retryable = map_rag_exception(exc)
                logger.error(
                    "RAG worker: indexing failed for file_id=%s: %s (%s)",
                    file_id,
                    exc,
                    code,
                )
                # Re-fetch file in case session is stale
                try:
                    fail_file = index_db.query(FileMetadata).filter(
                        FileMetadata.fileid == file_id
                    ).first()
                    if fail_file:
                        mark_rag_failure(
                            db=index_db,
                            file=fail_file,
                            code=code,
                            message=message,
                            retryable=retryable,
                        )
                except Exception:
                    index_db.rollback()
            finally:
                index_db.close()

        except Exception as exc:
            logger.error(
                "RAG worker: unexpected error for file_id=%s: %s",
                file_id,
                exc,
            )
            # Best-effort: try to reset status
            try:
                db.rollback()
                db.close()
            except Exception:
                pass

        finally:
            # Ensure session is closed even if something unexpected happened
            try:
                db.close()
            except Exception:
                pass


# Global semaphore to enforce concurrent rate limiting on background operations
_embedding_semaphore = asyncio.Semaphore(settings.MAX_CONCURRENT_EMBEDDING_TASKS)