"""
backend/app/services/cache/redis_cache.py

Singleton Redis client factory and health check guard for RAG query response
and vector hit caching. Implements fail-open error handling so Redis failures
do not block backend startup or disrupt primary search functionality.
"""
import logging
import threading
from typing import Optional

from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.core.config import settings

logger = logging.getLogger(__name__)

_redis_client: Optional[Redis] = None
_redis_lock = threading.Lock()


def get_redis_client() -> Redis:
    """Retrieve or initialize the global singleton Redis client instance with thread safety."""
    global _redis_client
    if _redis_client is None:
        with _redis_lock:
            if _redis_client is None:
                _redis_client = Redis.from_url(
                    settings.REDIS_URL,
                    socket_timeout=settings.REDIS_SOCKET_TIMEOUT_SECONDS,
                    socket_connect_timeout=settings.REDIS_CONNECT_TIMEOUT_SECONDS,
                    decode_responses=True,
                )
    return _redis_client


async def close_redis_client() -> None:
    """Close the global Redis client connection cleanly on application shutdown."""
    global _redis_client
    if _redis_client is not None:
        try:
            await _redis_client.aclose()
        except Exception as exc:
            logger.warning("Error closing Redis client connection: %s", str(exc))
        finally:
            _redis_client = None


async def ping_redis() -> bool:
    """Health check guard for Redis connectivity.

    Fails open: if Redis is disabled or unreachable, logs a warning and returns False
    so application startup and core non-cached operations continue without interruption.
    """
    if not settings.RAG_CACHE_ENABLED:
        logger.info("RAG caching is disabled in configuration (RAG_CACHE_ENABLED=False).")
        return False

    try:
        r_client = get_redis_client()
        pong = await r_client.ping()
        if pong:
            logger.info("Redis cache service connected successfully (%s).", settings.REDIS_URL)
            return True
        return False
    except RedisError as exc:
        logger.warning("Redis unavailable; RAG cache will be skipped: %s", str(exc))
        return False
    except Exception as exc:
        logger.warning("Unexpected error checking Redis status; RAG cache will be skipped: %s", str(exc))
        return False
