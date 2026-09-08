"""
backend/app/services/rag/answer_cache.py

Phase 5 Redis answer cache with fail-open semantics.

Redis is a performance accelerator, never a correctness dependency:
- Redis healthy + hit  -> return cached answer fast
- Redis healthy + miss -> generate, cache, return
- Redis unhealthy/error -> skip cache silently (fail open)

These functions never raise. Cache loss must never become a 500.
"""
import logging
import time

from app.core.config import settings
from app.services.cache.redis_cache import get_redis_client

logger = logging.getLogger(__name__)

# Simple in-process fallback so a Redis flush/restart between browser
# sessions does not wipe every cached answer while the backend process
# stays up. No new MySQL table — just a dict with TTL. Redis remains
# the primary store; this is a second-level cache.
_local_cache: dict[str, tuple[str, float]] = {}


async def get_cached_answer(cache_key: str) -> str | None:
    """Retrieve a cached answer. Returns None on miss or Redis error.

    Fail-open: any Redis failure is logged and treated as a cache miss,
    so the caller proceeds with a normal (uncached) query path.
    Checks Redis first, then the in-process fallback dict.

    Args:
        cache_key: Key built by query_utils.build_cache_key().

    Returns:
        Cached answer string, or None when disabled / missing / failing.
    """
    if not settings.RAG_CACHE_ENABLED:
        return None
    # 1) Redis primary
    try:
        client = get_redis_client()
        value = await client.get(cache_key)
        if value is not None:
            logger.debug("Cache HIT (redis) for key=%s", cache_key[:20])
            # Warm the local fallback so next hit survives a Redis flush
            _local_cache[cache_key] = (value, time.monotonic() + settings.RAG_CACHE_TTL_SECONDS)
            return value
    except Exception as exc:
        logger.warning("Redis GET failed (fail open): %s", exc)

    # 2) In-process fallback (survives Redis flush within same backend process)
    entry = _local_cache.get(cache_key)
    if entry is not None:
        answer, expires_at = entry
        if time.monotonic() < expires_at:
            logger.debug("Cache HIT (local) for key=%s", cache_key[:20])
            return answer
        # Expired
        _local_cache.pop(cache_key, None)
    return None


async def set_cached_answer(cache_key: str, answer: str) -> None:
    """Store an answer with the configured TTL. Never raises.

    Fire-and-forget from the caller's perspective: a Redis write failure
    is logged but does not affect the already-streamed answer.
    Writes to both Redis and the local fallback dict.

    Args:
        cache_key: Key built by query_utils.build_cache_key().
        answer: Full generated answer string.
    """
    if not settings.RAG_CACHE_ENABLED:
        return
    # Always warm the local fallback
    _local_cache[cache_key] = (answer, time.monotonic() + settings.RAG_CACHE_TTL_SECONDS)
    # Bound local size (simple LRU-ish eviction of oldest 20% when over 500)
    if len(_local_cache) > 500:
        for k in list(_local_cache.keys())[:100]:
            _local_cache.pop(k, None)
    try:
        client = get_redis_client()
        await client.setex(
            cache_key, settings.RAG_CACHE_TTL_SECONDS, answer
        )
        logger.debug(
            "Cache SET for key=%s ttl=%s",
            cache_key[:20],
            settings.RAG_CACHE_TTL_SECONDS,
        )
    except Exception as exc:
        logger.warning("Redis SETEX failed (fail open): %s", exc)