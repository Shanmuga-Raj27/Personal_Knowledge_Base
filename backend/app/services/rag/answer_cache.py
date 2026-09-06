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

from app.core.config import settings
from app.services.cache.redis_cache import get_redis_client

logger = logging.getLogger(__name__)


async def get_cached_answer(cache_key: str) -> str | None:
    """Retrieve a cached answer. Returns None on miss or Redis error.

    Fail-open: any Redis failure is logged and treated as a cache miss,
    so the caller proceeds with a normal (uncached) query path.

    Args:
        cache_key: Key built by query_utils.build_cache_key().

    Returns:
        Cached answer string, or None when disabled / missing / failing.
    """
    if not settings.RAG_CACHE_ENABLED:
        return None
    try:
        client = get_redis_client()
        value = await client.get(cache_key)
        if value is not None:
            logger.debug("Cache HIT for key=%s", cache_key[:20])
        return value
    except Exception as exc:
        logger.warning("Redis GET failed (fail open): %s", exc)
        return None


async def set_cached_answer(cache_key: str, answer: str) -> None:
    """Store an answer with the configured TTL. Never raises.

    Fire-and-forget from the caller's perspective: a Redis write failure
    is logged but does not affect the already-streamed answer.

    Args:
        cache_key: Key built by query_utils.build_cache_key().
        answer: Full generated answer string.
    """
    if not settings.RAG_CACHE_ENABLED:
        return
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