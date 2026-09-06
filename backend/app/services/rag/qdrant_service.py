"""
backend/app/services/rag/qdrant_service.py

Phase 4 Qdrant upsert and verification service for RAG chunk vectors.

- Sync QdrantClient (not Async) to match Phase 4 spec
- Deterministic UUIDv5 point IDs for idempotent upserts
- Bounded batches + exponential backoff with jitter for 429/timeout/5xx
- Tenant-isolated via mandatory user_id filter
- Verification and async cleanup helpers for zero-downtime cutover
"""

import logging
import random
import threading
import time
from typing import Any, Iterable

from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    MatchValue,
    PointStruct,
    VectorParams,
)

from app.core.config import settings
from app.services.rag.config import (
    EXPECTED_QDRANT_VECTOR_PARAMS,
    EXPECTED_VECTOR_SIZE,
    QDRANT_COLLECTION,
)
from app.services.rag.embedding import embed_document
from app.services.rag.ids import build_chunk_id
from app.services.rag.retry import extract_status_code as _retry_extract_status_code
from app.services.rag.retry import is_retryable as _retry_is_retryable
from app.services.rag.retry import is_timeout as _retry_is_timeout
from app.services.rag.schemas import ChunkPayload

logger = logging.getLogger(__name__)

# ── Singleton sync client ──────────────────────────────────────────────────
_qdrant_client: QdrantClient | None = None
_qdrant_lock = threading.Lock()


def get_qdrant_client() -> QdrantClient:
    """Return singleton sync QdrantClient."""
    global _qdrant_client
    if _qdrant_client is not None:
        return _qdrant_client
    with _qdrant_lock:
        if _qdrant_client is None:
            _qdrant_client = QdrantClient(
                url=settings.QDRANT_HOST,
                timeout=int(settings.GEMINI_API_TIMEOUT_SECONDS),
                check_compatibility=False,
            )
    return _qdrant_client


def _reset_qdrant_client_for_tests() -> None:
    """Test helper: clear singleton."""
    global _qdrant_client
    _qdrant_client = None


# ── Helpers ────────────────────────────────────────────────────────────────
def _batch_chunks(chunks: list, size: int) -> Iterable[list]:
    """Yield successive n-sized chunks."""
    for i in range(0, len(chunks), size):
        yield chunks[i : i + size]


# Re-export centralized retry helpers for backward compat
def _extract_status_code(exc: Exception) -> int | None:
    return _retry_extract_status_code(exc)


def _is_timeout(exc: Exception) -> bool:
    return _retry_is_timeout(exc)


def _is_retryable(exc: Exception) -> bool:
    return _retry_is_retryable(exc)


def _qdrant_upsert_batch(points: list[PointStruct]) -> int:
    """Upsert one batch to Qdrant; return count."""
    client = get_qdrant_client()
    client.upsert(
        collection_name=QDRANT_COLLECTION,
        points=points,
        wait=True,
    )
    return len(points)


# ── Collection guard ───────────────────────────────────────────────────────
def ensure_collection() -> None:
    """Ensure RAG collection exists with 768/COSINE; create if missing.

    Raises:
        RuntimeError: If existing collection has mismatched size/distance.
    """
    client = get_qdrant_client()

    # Fast path: collection_exists if available (sync client)
    try:
        if hasattr(client, "collection_exists"):
            exists = client.collection_exists(collection_name=QDRANT_COLLECTION)
            if not exists:
                logger.info("Creating Qdrant collection '%s' (768d, Cosine)...", QDRANT_COLLECTION)
                client.create_collection(
                    collection_name=QDRANT_COLLECTION,
                    vectors_config=VectorParams(
                        size=EXPECTED_VECTOR_SIZE,
                        distance=Distance.COSINE,
                    ),
                )
                for field in ("user_id", "file_id", "index_version"):
                    try:
                        client.create_payload_index(
                            collection_name=QDRANT_COLLECTION,
                            field_name=field,
                            field_schema="integer",
                        )
                    except Exception:
                        # Index may already exist or not supported in mock
                        pass
                logger.info("Qdrant collection '%s' created.", QDRANT_COLLECTION)
                return
        else:
            # Fallback: try get_collection and catch not-found
            client.get_collection(collection_name=QDRANT_COLLECTION)
            # If no exception, collection exists — validate below
            pass
    except Exception as exc:
        # collection_exists returned False or get_collection raised "not found"
        msg = str(exc).lower()
        if "not found" in msg or "doesn't exist" in msg or "not exist" in msg:
            logger.info("Creating Qdrant collection '%s' (768d, Cosine)...", QDRANT_COLLECTION)
            client.create_collection(
                collection_name=QDRANT_COLLECTION,
                vectors_config=VectorParams(
                    size=EXPECTED_VECTOR_SIZE,
                    distance=Distance.COSINE,
                ),
            )
            for field in ("user_id", "file_id", "index_version"):
                try:
                    client.create_payload_index(
                        collection_name=QDRANT_COLLECTION,
                        field_name=field,
                        field_schema="integer",
                    )
                except Exception:
                    pass
            return
        # Re-raise unexpected errors; validation will handle below if collection exists
        if "vector size" in msg or "distance" in msg:
            raise

    # Collection exists — validate size/distance
    info = client.get_collection(collection_name=QDRANT_COLLECTION)
    vectors_params = info.config.params.vectors  # type: ignore[attr-defined]

    if isinstance(vectors_params, dict):
        vector_size = vectors_params.get("size")
        vector_distance = vectors_params.get("distance")
    else:
        vector_size = getattr(vectors_params, "size", None)
        vector_distance = getattr(vectors_params, "distance", None)

    # Normalize distance comparison (handles string vs enum)
    expected_distance = Distance.COSINE
    # Allow both enum and string forms
    if isinstance(vector_distance, str):
        is_cosine = vector_distance.lower() == "cosine"
    else:
        is_cosine = vector_distance == expected_distance

    if vector_size != EXPECTED_VECTOR_SIZE:
        raise RuntimeError(
            f"Qdrant collection '{QDRANT_COLLECTION}' has vector size {vector_size}; "
            f"expected {EXPECTED_VECTOR_SIZE}"
        )
    if not is_cosine:
        raise RuntimeError(
            f"Qdrant collection '{QDRANT_COLLECTION}' has distance metric '{vector_distance}'; "
            f"expected '{expected_distance}'"
        )
    # Also check against EXPECTED_QDRANT_VECTOR_PARAMS for completeness
    assert EXPECTED_QDRANT_VECTOR_PARAMS.size == EXPECTED_VECTOR_SIZE


# ── Upsert ─────────────────────────────────────────────────────────────────
def upsert_document_chunks(
    user_id: int,
    file_id: int,
    index_version: int,
    chunks: list[dict | Any],
    batch_size: int | None = None,
) -> dict:
    """Upsert chunk vectors into Qdrant in bounded batches.

    Args:
        user_id: Owner user ID (mandatory tenant filter).
        file_id: FileMetadata.fileid.
        index_version: RAG index version to write.
        chunks: List of dicts with {chunk_index, clean_text} or TextChunk objects.
        batch_size: Override; defaults to settings.RAG_EMBEDDING_BATCH_SIZE (64, max 128).

    Returns:
        {"upserted": int, "failed": int, "batch_progress": [{"chunk_index", "point_id"}]}
    """
    if batch_size is None:
        batch_size = settings.RAG_EMBEDDING_BATCH_SIZE
    # Clamp to spec max
    batch_size = max(1, min(int(batch_size), 128))

    # Normalize chunks to list[dict]
    normalized: list[dict] = []
    for c in chunks:
        if isinstance(c, dict):
            normalized.append(c)
        elif hasattr(c, "chunk_index") and hasattr(c, "clean_text"):
            normalized.append({"chunk_index": c.chunk_index, "clean_text": c.clean_text})
        else:
            raise ValueError(f"Invalid chunk shape: {c!r}")

    # Build points (embedding happens here; outside DB transaction)
    points: list[PointStruct] = []
    for chunk in normalized:
        chunk_index = chunk["chunk_index"]
        clean_text = chunk["clean_text"]
        point_id = str(build_chunk_id(file_id, index_version, chunk_index))
        vector = embed_document(clean_text)
        # Extra dimension guard (embed_document already validates, but double-check before upsert)
        if len(vector) != EXPECTED_VECTOR_SIZE:
            raise RuntimeError(
                f"Unexpected embedding dimension: got {len(vector)}, expected {EXPECTED_VECTOR_SIZE}"
            )
        payload = ChunkPayload(
            user_id=user_id,
            file_id=file_id,
            index_version=index_version,
            chunk_index=chunk_index,
        ).model_dump()
        points.append(PointStruct(id=point_id, vector=vector, payload=payload))

    total_upserted = 0
    total_failed = 0
    batch_progress: list[dict] = []

    for batch in _batch_chunks(points, batch_size):
        attempt = 0
        success = False
        # Retry loop per batch
        while not success and attempt <= settings.RAG_MAX_RETRIES:
            try:
                _qdrant_upsert_batch(batch)
                success = True
                for point in batch:
                    batch_progress.append(
                        {
                            "chunk_index": point.payload["chunk_index"],  # type: ignore[index]
                            "point_id": str(point.id),
                        }
                    )
                total_upserted += len(batch)
            except Exception as exc:
                if _is_retryable(exc) and attempt < settings.RAG_MAX_RETRIES:
                    delay = (settings.RAG_BACKOFF_BASE ** (attempt + 1)) + random.random()
                    logger.warning(
                        "Qdrant upsert retryable error (attempt %d/%d): %s — backing off %.2fs",
                        attempt + 1,
                        settings.RAG_MAX_RETRIES,
                        exc,
                        delay,
                    )
                    time.sleep(delay)
                    attempt += 1
                    continue
                else:
                    # Non-retryable or exhausted
                    logger.error("Qdrant upsert failed for batch size %d: %s", len(batch), exc)
                    total_failed += len(batch)
                    break
        # If loop exhausted without success and not counted as failed, count as failed
        if not success and total_failed == 0:
            # Edge: retries exhausted without entering except's failed branch
            total_failed += len(batch)

    return {
        "upserted": total_upserted,
        "failed": total_failed,
        "batch_progress": batch_progress,
    }


# ── Verification and cleanup ───────────────────────────────────────────────
def verify_qdrant_index(
    user_id: int,
    file_id: int,
    index_version: int,
    expected_chunk_count: int,
) -> bool:
    """Verify Qdrant has expected number of points for a version."""
    client = get_qdrant_client()
    result = client.count(
        collection_name=QDRANT_COLLECTION,
        count_filter=Filter(
            must=[
                FieldCondition(key="user_id", match=MatchValue(value=user_id)),
                FieldCondition(key="file_id", match=MatchValue(value=file_id)),
                FieldCondition(key="index_version", match=MatchValue(value=index_version)),
            ]
        ),
        exact=True,
    )
    # Handle both .count attr and direct int
    count = getattr(result, "count", result)
    if isinstance(count, dict):
        count = count.get("count", 0)
    return int(count) == int(expected_chunk_count)


def cleanup_old_version_vectors(
    user_id: int,
    old_index_version: int,
    file_id: int | None = None,
) -> None:
    """Delete old version vectors after successful cutover.

    Args:
        user_id: Owner.
        old_index_version: Version to delete.
        file_id: Optional narrow to single file; if None, deletes all files for version.
    """
    client = get_qdrant_client()
    must = [
        FieldCondition(key="user_id", match=MatchValue(value=user_id)),
        FieldCondition(key="index_version", match=MatchValue(value=old_index_version)),
    ]
    if file_id is not None:
        must.append(FieldCondition(key="file_id", match=MatchValue(value=file_id)))

    client.delete(
        collection_name=QDRANT_COLLECTION,
        points_selector=Filter(must=must),
        wait=True,
    )
    logger.info(
        "Cleaned old Qdrant vectors user_id=%s index_version=%s file_id=%s",
        user_id,
        old_index_version,
        file_id if file_id is not None else "*",
    )


# ── Batch progress & resume (Phase 4 Step 4) ─────────────────────────────────
def get_existing_chunk_indexes(
    user_id: int,
    file_id: int,
    index_version: int,
    limit: int = 10000,
) -> set[int]:
    """Return set of chunk_index already upserted in Qdrant for this version.

    Uses scroll with tenant-isolated filter; deterministic IDs make this
    check reliable for resume. Called before re-trying a failed upsert
    so we only embed+upsert missing chunks.

    Args:
        user_id: Owner.
        file_id: File to check.
        index_version: Version to check.
        limit: Max points to scan (chunks per file rarely exceeds this).

    Returns:
        Set of chunk_index values present in Qdrant.
    """
    client = get_qdrant_client()
    qfilter = Filter(
        must=[
            FieldCondition(key="user_id", match=MatchValue(value=user_id)),
            FieldCondition(key="file_id", match=MatchValue(value=file_id)),
            FieldCondition(key="index_version", match=MatchValue(value=index_version)),
        ]
    )

    existing: set[int] = set()
    offset = None

    # Scroll until no more points; handle both tuple-return and object-return mocks
    while True:
        if hasattr(client, "scroll"):
            result = client.scroll(
                collection_name=QDRANT_COLLECTION,
                scroll_filter=qfilter,
                limit=min(256, limit - len(existing)),
                with_payload=True,
                with_vectors=False,
            )
            # Real client returns (points, next_offset); mock may return list
            if isinstance(result, tuple):
                points, offset = result
            elif isinstance(result, dict) and "points" in result:
                points = result["points"]
                offset = result.get("next_page_offset")
            elif hasattr(result, "points"):
                points = result.points  # type: ignore[attr-defined]
                offset = getattr(result, "next_page_offset", None)
            else:
                points = result  # type: ignore[assignment]
                offset = None
        else:
            # No scroll support in mock — return empty to force full re-upsert (safe idempotent)
            break

        if not points:
            break

        for pt in points:
            payload = getattr(pt, "payload", None)
            if isinstance(pt, dict):
                payload = pt.get("payload", {})
            if payload and "chunk_index" in payload:
                existing.add(int(payload["chunk_index"]))

        if offset is None or len(existing) >= limit:
            break
        if len(points) == 0:
            break

    logger.debug(
        "Existing Qdrant chunk_indexes user_id=%s file_id=%s version=%s → %s",
        user_id,
        file_id,
        index_version,
        sorted(existing),
    )
    return existing


def filter_pending_chunks(
    all_chunks: list[dict | Any],
    existing_chunk_indexes: set[int],
) -> list[dict]:
    """Filter all_chunks to only those not yet in Qdrant.

    Idempotent upserts mean re-running is safe, but filtering saves
    Gemini quota and time on resume. Preserves original chunk dict shape.

    Args:
        all_chunks: Full list of {chunk_index, clean_text} dicts.
        existing_chunk_indexes: Set from get_existing_chunk_indexes.

    Returns:
        Subset of all_chunks whose chunk_index not in existing set.
    """
    pending: list[dict] = []
    for c in all_chunks:
        if isinstance(c, dict):
            idx = c.get("chunk_index")
        elif hasattr(c, "chunk_index"):
            idx = getattr(c, "chunk_index")
        else:
            continue
        if idx not in existing_chunk_indexes:
            # Normalize to dict for downstream upsert
            if isinstance(c, dict):
                pending.append(c)
            else:
                pending.append({"chunk_index": c.chunk_index, "clean_text": c.clean_text})
    return pending


def fetch_chunks_for_version(
    db: Any,
    file_id: int,
    index_version: int,
) -> list[dict]:
    """Fetch staged chunks from MySQL for a given file/version.

    Helper for orchestrator — reads clean_text from DocumentChunk source of truth.

    Args:
        db: SQLAlchemy Session.
        file_id: FileMetadata.fileid.
        index_version: RAG index version.

    Returns:
        List of {chunk_index, clean_text} dicts ordered by chunk_index.
    """
    from app.database.db_models import DocumentChunk  # local import to avoid cycle

    rows = (
        db.query(DocumentChunk)
        .filter(
            DocumentChunk.file_id == file_id,
            DocumentChunk.index_version == index_version,
        )
        .order_by(DocumentChunk.chunk_index.asc())
        .all()
    )
    return [{"chunk_index": r.chunk_index, "clean_text": r.clean_text} for r in rows]


def upsert_with_resume(
    user_id: int,
    file_id: int,
    index_version: int,
    all_chunks: list[dict | Any],
    batch_size: int | None = None,
    skip_existing_check: bool = False,
) -> dict:
    """Upsert with automatic resume — skip already-upserted chunk_indexes.

    Combines get_existing_chunk_indexes + filter_pending_chunks + upsert_document_chunks.
    If skip_existing_check is True, directly re-upserts all (fully idempotent,
    simpler but wastes embedding calls). Default checks Qdrant first to save quota.

    Returns:
        Same dict as upsert_document_chunks: {upserted, failed, batch_progress}
        plus pending info in logs.
    """
    if skip_existing_check:
        pending = all_chunks  # type: ignore[assignment]
        logger.info(
            "Resume disabled — upserting all %d chunks file_id=%s version=%s",
            len(all_chunks),
            file_id,
            index_version,
        )
    else:
        try:
            existing = get_existing_chunk_indexes(user_id, file_id, index_version)
        except Exception as exc:
            logger.warning("Failed to check existing Qdrant indexes, falling back to full upsert: %s", exc)
            existing = set()
        pending = filter_pending_chunks(all_chunks, existing)
        logger.info(
            "Resume check file_id=%s version=%s: total=%d existing=%d pending=%d",
            file_id,
            index_version,
            len(all_chunks),
            len(existing),
            len(pending),
        )
        if not pending:
            # Already fully upserted — return progress for existing points without re-embedding
            batch_progress = [
                {
                    "chunk_index": idx,
                    "point_id": str(build_chunk_id(file_id, index_version, idx)),
                }
                for idx in sorted(existing)
            ]
            return {"upserted": 0, "failed": 0, "batch_progress": batch_progress, "skipped": len(existing)}

    # Delegate to core upsert (handles batching, retries, dimension validation)
    return upsert_document_chunks(
        user_id=user_id,
        file_id=file_id,
        index_version=index_version,
        chunks=pending,
        batch_size=batch_size,
    )
