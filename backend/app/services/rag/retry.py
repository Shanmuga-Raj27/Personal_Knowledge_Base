"""
backend/app/services/rag/retry.py

Phase 4 centralized retry and error classification.

Error table (RAG-phase-4.md:586-597):
    EMBEDDING_TIMEOUT       → retry with backoff
    EMBEDDING_429           → retry with jitter
    EMBEDDING_5XX           → retry exponential
    EMBEDDING_DIM_MISMATCH  → fail fast
    QDRANT_UPSERT_FAILED    → maybe (depends on is_retryable)
    QDRANT_COLLECTION_MISMATCH → fail fast
"""

import logging
import random
import time
from typing import Any, Callable

from app.core.config import settings

logger = logging.getLogger(__name__)

# ── Error codes ────────────────────────────────────────────────────────────
ERROR_EMBEDDING_TIMEOUT = "EMBEDDING_TIMEOUT"
ERROR_EMBEDDING_429 = "EMBEDDING_429"
ERROR_EMBEDDING_5XX = "EMBEDDING_5XX"
ERROR_EMBEDDING_DIM_MISMATCH = "EMBEDDING_DIM_MISMATCH"
ERROR_QDRANT_UPSERT_FAILED = "QDRANT_UPSERT_FAILED"
ERROR_QDRANT_COLLECTION_MISMATCH = "QDRANT_COLLECTION_MISMATCH"

RETRYABLE_CODES = {
    ERROR_EMBEDDING_TIMEOUT,
    ERROR_EMBEDDING_429,
    ERROR_EMBEDDING_5XX,
}


def extract_status_code(exc: Exception) -> int | None:
    """Extract HTTP status code from varied exception shapes."""
    for attr in ("status_code", "code"):
        if hasattr(exc, attr):
            val = getattr(exc, attr)
            if isinstance(val, int):
                return val
    resp = getattr(exc, "response", None)
    if resp is not None:
        for attr in ("status_code", "code", "status"):
            if hasattr(resp, attr):
                val = getattr(resp, attr)
                if isinstance(val, int):
                    return val
    msg = str(exc)
    if "429" in msg:
        return 429
    return None


def is_timeout(exc: Exception) -> bool:
    name = type(exc).__name__.lower()
    msg = str(exc).lower()
    return "timeout" in name or "timeout" in msg or "timed out" in msg or isinstance(exc, TimeoutError)


def is_retryable(exc: Exception) -> bool:
    """Retry only on 429, timeout, or 5xx per RAG-phase-4.md:162."""
    if is_timeout(exc):
        return True
    code = extract_status_code(exc)
    if code == 429:
        return True
    if code is not None and 500 <= code < 600:
        return True
    return False


def classify_error(exc: Exception) -> str:
    """Map exception to error code for logging/metrics."""
    if is_timeout(exc):
        return ERROR_EMBEDDING_TIMEOUT
    code = extract_status_code(exc)
    if code == 429:
        return ERROR_EMBEDDING_429
    if code is not None and 500 <= code < 600:
        return ERROR_EMBEDDING_5XX
    msg = str(exc).lower()
    # Collection mismatch must be checked before dimension (message may contain both "collection size" and "768")
    if "collection" in msg and ("size" in msg or "distance" in msg):
        return ERROR_QDRANT_COLLECTION_MISMATCH
    if "dimension" in msg or "768" in msg:
        return ERROR_EMBEDDING_DIM_MISMATCH
    return ERROR_QDRANT_UPSERT_FAILED


def with_retry(
    fn: Callable[[], Any],
    max_retries: int | None = None,
    base_delay: float | None = None,
    jitter: bool = True,
) -> Any:
    """Execute fn with exponential backoff + jitter (RAG-phase-4.md:605-623).

    Args:
        fn: Callable to execute (no args).
        max_retries: Override settings.RAG_MAX_RETRIES.
        base_delay: Override settings.RAG_BACKOFF_BASE.
        jitter: Add random(0,1) jitter.

    Returns:
        fn() return value on success.

    Raises:
        Last exception if non-retryable or retries exhausted.
    """
    if max_retries is None:
        max_retries = settings.RAG_MAX_RETRIES
    if base_delay is None:
        base_delay = settings.RAG_BACKOFF_BASE

    last_exc: Exception | None = None
    for attempt in range(max_retries + 1):
        try:
            return fn()
        except Exception as exc:
            last_exc = exc
            if not is_retryable(exc) or attempt >= max_retries:
                raise
            delay = (base_delay * (2 ** attempt)) + (random.random() if jitter else 0)
            logger.warning(
                "Retryable %s (attempt %d/%d) — backing off %.2fs: %s",
                classify_error(exc),
                attempt + 1,
                max_retries,
                delay,
                exc,
            )
            time.sleep(delay)
    if last_exc:
        raise last_exc
    raise RuntimeError("with_retry exhausted without exception")
