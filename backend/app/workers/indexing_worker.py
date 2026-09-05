"""
backend/app/workers/indexing_worker.py

Background worker tasks for vector embedding generation, Qdrant synchronization,
and automatic startup recovery for pending or failed indexing tasks.
"""
import asyncio
import logging
import random
from datetime import datetime, timezone, timedelta

from sqlalchemy import or_

from fastapi.concurrency import run_in_threadpool

from app.core.config import settings
from app.database.database import SessionLocal
from app.database.db_models import FileMetadata
from app.schemas.enums import FileStatus, IndexingStatus
from app.services.AI.vector_service import upsert_file_vector
from app.services.rag.document_processor import (
    NoExtractableTextError,
    process_pdf_from_storage,
)

logger = logging.getLogger(__name__)

# Global semaphore to enforce concurrent rate limiting on background embedding operations
_embedding_semaphore = asyncio.Semaphore(settings.MAX_CONCURRENT_EMBEDDING_TASKS)


async def sync_vector_in_background(
    file_id: int,
    user_id: int,
    filename: str,
    title: str | None,
    description: str | None,
    tags: str | None,
    target_version: int,
    s3_key: str | None = None,
):
    """Background worker task to compute Gemini embeddings and update Qdrant point asynchronously with semaphore rate limiting.

    Phase 2 (logging-only): If the file is a PDF and s3_key is provided, the full
    RAG extraction pipeline is also run. Chunk stats are logged but nothing is
    persisted until Phase 3 completes the MySQL schema and storage layer.
    """
    async with _embedding_semaphore:
        # ── Phase 2 RAG pipeline (logging-only, Option B) ─────────────────────
        # Processes PDFs through the full extraction/chunking pipeline and logs
        # stats to validate correctness. No data is persisted until Phase 3.
        if s3_key and filename.lower().endswith(".pdf"):
            try:
                processed = await run_in_threadpool(process_pdf_from_storage, s3_key)
                logger.info(
                    "RAG Phase 2 processed file_id=%s pages=%s words=%s chunks=%s key=%s",
                    file_id,
                    processed.page_count,
                    processed.extracted_word_count,
                    len(processed.chunks),
                    s3_key,
                )
            except NoExtractableTextError:
                logger.info(
                    "RAG Phase 2: file_id=%s has no extractable text layer (scanned/image-only PDF).",
                    file_id,
                )
            except Exception as exc:
                logger.warning(
                    "RAG Phase 2 processing failed for file_id=%s key=%s: %s",
                    file_id,
                    s3_key,
                    exc,
                )

        # ── Existing metadata vector indexing (unchanged) ──────────────────
        indexed_success = False
        error_msg = None
        try:
            indexed_success = await upsert_file_vector(
                file_id=file_id,
                user_id=user_id,
                filename=filename,
                title=title,
                description=description,
                tags=tags,
            )
            if not indexed_success:
                error_msg = "Embedding generation or Qdrant vector upsert failed."
        except Exception as exc:
            indexed_success = False
            error_msg = str(exc)

        db = SessionLocal()
        try:
            db_file = db.query(FileMetadata).filter(FileMetadata.fileid == file_id).first()
            if db_file:
                # Optimistic versioning check: commit status only if version matches target_version
                if db_file.index_version == target_version:
                    db_file.is_indexed = indexed_success
                    if indexed_success:
                        db_file.indexing_status = IndexingStatus.INDEXED.value
                        db_file.last_error = None
                        db_file.next_retry_at = None
                    else:
                        db_file.indexing_status = IndexingStatus.FAILED.value
                        current_retries = (db_file.retry_count or 0) + 1
                        db_file.retry_count = current_retries
                        db_file.last_error = (error_msg or "Indexing failed")[:500]
                        # Exponential backoff calculation with jitter (max 300 seconds)
                        backoff_delay = min(300, (2 ** current_retries) + random.uniform(0, 1))
                        db_file.next_retry_at = datetime.now(timezone.utc) + timedelta(seconds=backoff_delay)
                    db.commit()
                else:
                    logger.info(
                        "Skipping stale background indexing task for file %s (current version %s != target %s).",
                        file_id, db_file.index_version, target_version
                    )
        except Exception as exc:
            logger.error("Background task error updating indexing_status for file %s: %s", file_id, str(exc))
        finally:
            db.close()


async def recover_and_backfill_unindexed_files():
    """Startup task to scan and queue unindexed/failed active files for background vector indexing in chunked batches."""
    db = SessionLocal()
    try:
        now_utc = datetime.now(timezone.utc)
        unindexed_files = (
            db.query(FileMetadata)
            .filter(
                FileMetadata.status == FileStatus.ACTIVE.value,
                FileMetadata.retry_count < 3,
                or_(
                    FileMetadata.indexing_status.in_([
                        IndexingStatus.PENDING.value,
                        IndexingStatus.FAILED.value,
                        IndexingStatus.INDEXING.value,
                    ]),
                    FileMetadata.is_indexed == False,
                ),
                or_(
                    FileMetadata.next_retry_at == None,
                    FileMetadata.next_retry_at <= now_utc,
                )
            )
            .limit(25)
            .all()
        )
        if unindexed_files:
            logger.info("Found %d unindexed or failed active records for recovery backfill...", len(unindexed_files))
            file_ids = [db_file.fileid for db_file in unindexed_files]
            db.query(FileMetadata).filter(FileMetadata.fileid.in_(file_ids)).update(
                {FileMetadata.indexing_status: IndexingStatus.INDEXING.value}, synchronize_session=False
            )
            db.commit()

            tasks = [
                sync_vector_in_background(
                    file_id=db_file.fileid,
                    user_id=db_file.userid,
                    filename=db_file.filename,
                    title=db_file.title,
                    description=db_file.description,
                    tags=db_file.tags,
                    target_version=db_file.index_version,
                )
                for db_file in unindexed_files
            ]
            await asyncio.gather(*tasks, return_exceptions=True)
    except Exception as exc:
        logger.warning("Recovery worker warning: %s", str(exc))
    finally:
        db.close()
