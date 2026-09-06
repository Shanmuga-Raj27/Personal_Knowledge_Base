"""
backend/app/services/rag/indexing_service.py

Phase 4 versioned index cutover orchestrator.

Zero-downtime flow:
    1. Chunks already staged in MySQL via stage_document_chunks (Phase 3) — not active yet
    2. Embed + upsert to Qdrant with deterministic IDs (outside DB transaction)
    3. Verify Qdrant count == MySQL chunk_count
    4. Single short transaction: activate_rag_index_version() + corpus_revision increment
    5. Async cleanup of old version vectors after grace period

Queries always filter by active_index_version, so they see old complete version
or new complete version — never half-written.

External calls (Gemini, Qdrant) happen outside long DB transactions.
"""

import logging
from typing import Any

from sqlalchemy.orm import Session

from app.database.db_models import FileMetadata
from app.schemas.enums import IndexingStatus
from app.services.rag.persistence import activate_rag_index_version
from app.services.rag.qdrant_service import (
    cleanup_old_version_vectors,
    fetch_chunks_for_version,
    upsert_with_resume,
    verify_qdrant_index,
)

logger = logging.getLogger(__name__)


def build_new_version_vectors(
    db: Session,
    file: FileMetadata,
    index_version: int,
    batch_size: int | None = None,
    skip_existing_check: bool = False,
) -> dict:
    """Embed and upsert all staged chunks for a new version.

    Reads clean_text from MySQL (source of truth), embeds with RETRIEVAL_DOCUMENT,
    upserts to Qdrant in bounded batches with resume support. Does NOT activate.

    Args:
        db: SQLAlchemy Session (used only for reading chunks + status updates).
        file: FileMetadata row (must be in CHUNKED or EMBEDDING state).
        index_version: Version to build (from stage_document_chunks return).
        batch_size: Override RAG_EMBEDDING_BATCH_SIZE.
        skip_existing_check: If True, re-embed all even if some already in Qdrant.

    Returns:
        {"upserted": int, "failed": int, "batch_progress": list, "total_chunks": int}
        On partial failure, upserted < total_chunks and caller should not cut over.

    Side effects:
        Updates file.indexing_status to EMBEDDING → INDEXING during work.
    """
    # Mark embedding start (short transaction)
    try:
        file.indexing_status = IndexingStatus.EMBEDDING.value
        db.commit()
    except Exception:
        db.rollback()
        logger.warning("Failed to set EMBEDDING status for file_id=%s", file.fileid)

    all_chunks = fetch_chunks_for_version(db, file.fileid, index_version)
    total = len(all_chunks)

    if total == 0:
        logger.error("No chunks found for file_id=%s version=%s", file.fileid, index_version)
        raise ValueError("Cannot build vectors for zero chunks")

    logger.info(
        "Building vectors file_id=%s version=%s total=%d batch_size=%s",
        file.fileid,
        index_version,
        total,
        batch_size,
    )

    # EMBEDDING → INDEXING transition
    try:
        file.indexing_status = IndexingStatus.INDEXING.value
        db.commit()
    except Exception:
        db.rollback()

    # Upsert outside long transaction — network calls with retries inside
    result = upsert_with_resume(
        user_id=file.userid,
        file_id=file.fileid,
        index_version=index_version,
        all_chunks=all_chunks,
        batch_size=batch_size,
        skip_existing_check=skip_existing_check,
    )

    # Attach total for caller verification
    result["total_chunks"] = total
    return result


def verify_and_cutover(
    db: Session,
    file: FileMetadata,
    index_version: int,
    upsert_result: dict,
    cleanup_old: bool = True,
) -> bool:
    """Verify Qdrant completeness then atomically activate new version.

    Args:
        db: Session.
        file: FileMetadata row (re-fetched in transaction).
        index_version: Version to activate.
        upsert_result: Return value from build_new_version_vectors.
        cleanup_old: If True, delete old version vectors after successful cutover.

    Returns:
        True if cutover succeeded, False if verification failed (no DB change).

    Raises:
        ValueError: If chunk count mismatch or zero chunks (from activate).
    """
    expected = upsert_result.get("total_chunks", 0)
    upserted = upsert_result.get("upserted", 0)
    failed = upsert_result.get("failed", 0)
    skipped = upsert_result.get("skipped", 0)

    # Effective indexed = newly upserted + already skipped (existing)
    effective_indexed = upserted + skipped

    # If resume was used, pending=0 case returns skipped==total, upserted==0
    # If full upsert without resume, skipped==0, upserted==total
    # Use total as ground truth for verification
    if failed > 0:
        logger.error(
            "Upsert had failures file_id=%s version=%s upserted=%d failed=%d — not cutting over",
            file.fileid,
            index_version,
            upserted,
            failed,
        )
        return False

    # Verify Qdrant count matches MySQL expected
    qdrant_ok = verify_qdrant_index(
        user_id=file.userid,
        file_id=file.fileid,
        index_version=index_version,
        expected_chunk_count=expected,
    )

    if not qdrant_ok:
        logger.error(
            "Qdrant verification failed file_id=%s version=%s expected=%d — not cutting over",
            file.fileid,
            index_version,
            expected,
        )
        return False

    # Snapshot old version before cutover for cleanup
    old_version = file.active_index_version

    # Single short transaction — activate + corpus_revision increment
    # activate_rag_index_version validates chunk_count == indexed_chunk_count internally
    try:
        # effective_indexed should equal expected; prefer expected for idempotency
        activate_rag_index_version(
            db=db,
            file=file,
            index_version=index_version,
            indexed_chunk_count=expected,
        )
    except ValueError as exc:
        logger.error("Activation validation failed file_id=%s version=%s: %s", file.fileid, index_version, exc)
        raise

    logger.info(
        "Cutover success file_id=%s %s → %s corpus_revision=%s",
        file.fileid,
        old_version,
        index_version,
        file.corpus_revision,
    )

    # Async cleanup of old version vectors (best-effort, no DB transaction)
    if cleanup_old and old_version and old_version != index_version:
        try:
            cleanup_old_version_vectors(
                user_id=file.userid,
                old_index_version=old_version,
                file_id=file.fileid,
            )
        except Exception as exc:
            # Cleanup failure is non-fatal; old vectors just remain until next reconcile
            logger.warning(
                "Old version cleanup failed file_id=%s old_version=%s: %s — will retry later",
                file.fileid,
                old_version,
                exc,
            )

    return True


def run_full_indexing(
    db: Session,
    file: FileMetadata,
    index_version: int | None = None,
    batch_size: int | None = None,
    cleanup_old: bool = True,
) -> dict:
    """Convenience orchestrator: build → verify → cutover.

    Handles the common case where caller staged chunks and wants zero-downtime
    activation in one call. Keeps old vectors alive until new version verified.

    Args:
        db: Session.
        file: FileMetadata row.
        index_version: Version to index; if None, uses next expected (active+1) and expects chunks already staged.
        batch_size: Override batch size.
        cleanup_old: Delete old version vectors after success.

    Returns:
        {"success": bool, "upsert_result": dict, "active_index_version": int}

    Example:
        new_version = stage_document_chunks(db, file, processed)
        result = run_full_indexing(db, file, index_version=new_version)
        if result["success"]:
            # queries now see new version
    """
    # Resolve version if not provided
    if index_version is None:
        from app.services.rag.persistence import next_rag_index_version

        index_version = next_rag_index_version(file)

    upsert_result = build_new_version_vectors(
        db=db,
        file=file,
        index_version=index_version,
        batch_size=batch_size,
    )

    # If build had failures, mark retryable and return without cutover
    if upsert_result.get("failed", 0) > 0:
        try:
            file.indexing_status = IndexingStatus.FAILED_RETRYABLE.value
            file.rag_error_code = "QDRANT_UPSERT_FAILED"
            file.rag_error_message = f"Upsert failed {upsert_result['failed']}/{upsert_result['total_chunks']} chunks"
            db.commit()
        except Exception:
            db.rollback()
        return {"success": False, "upsert_result": upsert_result, "active_index_version": file.active_index_version}

    success = verify_and_cutover(
        db=db,
        file=file,
        index_version=index_version,
        upsert_result=upsert_result,
        cleanup_old=cleanup_old,
    )

    if not success:
        try:
            file.indexing_status = IndexingStatus.FAILED_RETRYABLE.value
            file.rag_error_code = "QDRANT_VERIFY_FAILED"
            file.rag_error_message = f"Qdrant count mismatch for version {index_version}"
            db.commit()
        except Exception:
            db.rollback()

    return {
        "success": success,
        "upsert_result": upsert_result,
        "active_index_version": file.active_index_version,
    }
