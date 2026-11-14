"""
backend/app/services/cache/redis_cache.py

Singleton Upstash Redis REST client factory and health check guard for RAG query response
and vector hit caching. Implements fail-open error handling so Redis failures
do not block backend startup or disrupt primary search functionality.
"""
import logging
import threading
from typing import Optional, Any

import httpx

# Old direct Redis client import:
# from redis.asyncio import Redis
# from redis.exceptions import RedisError

from app.core.config import settings

logger = logging.getLogger(__name__)


class UpstashRedisError(Exception):
    """Base exception for Upstash Redis REST API errors."""
    pass


class UpstashRedisRestClient:
    """Async client for Upstash Redis REST API using HTTP requests.

    Provides Redis-compatible methods (get, setex, ping, aclose/close)
    so callers (answer_cache, ping_redis, main lifespan) remain unchanged.
    """

    def __init__(
        self,
        rest_url: str,
        rest_token: str,
        timeout: float = 2.0,
    ) -> None:
        clean_url = rest_url.rstrip("/") if rest_url else ""
        if clean_url and not clean_url.startswith(("http://", "https://")):
            clean_url = f"https://{clean_url}"
        self.base_url = clean_url
        self.token = rest_token
        self.timeout = timeout
        self._http_client: Optional[httpx.AsyncClient] = None
        self._client_lock = threading.Lock()

    def _get_http_client(self) -> httpx.AsyncClient:
        if self._http_client is None or self._http_client.is_closed:
            with self._client_lock:
                if self._http_client is None or self._http_client.is_closed:
                    self._http_client = httpx.AsyncClient(
                        timeout=self.timeout,
                        headers={
                            "Authorization": f"Bearer {self.token}",
                        },
                    )
        return self._http_client

    async def execute_command(self, *args: Any) -> Any:
        """Execute a Redis command via the Upstash REST endpoint (POST /)."""
        if not self.base_url or not self.token:
            raise UpstashRedisError("Upstash Redis REST URL or Token is not configured.")

        client = self._get_http_client()
        command_list = [str(arg) if not isinstance(arg, (int, float, str)) else arg for arg in args]
        try:
            response = await client.post(self.base_url, json=command_list)
            if response.status_code != 200:
                raise UpstashRedisError(
                    f"Upstash REST API HTTP {response.status_code}: {response.text}"
                )
            data = response.json()
            if "error" in data and data["error"]:
                raise UpstashRedisError(f"Upstash REST command error: {data['error']}")
            return data.get("result")
        except httpx.HTTPError as exc:
            raise UpstashRedisError(f"Upstash REST request failed: {exc}") from exc

    async def get(self, key: str) -> Optional[str]:
        """Retrieve the value of a key. Returns None on miss."""
        result = await self.execute_command("GET", key)
        return str(result) if result is not None else None

    async def setex(self, key: str, time_seconds: int, value: str) -> bool:
        """Set key to hold the string value and set key to expire after a given time."""
        result = await self.execute_command("SETEX", key, int(time_seconds), value)
        return result == "OK" or result is True

    async def delete(self, key: str) -> bool:
        """Delete a key from Redis. Returns True if key existed and was deleted, False otherwise."""
        result = await self.execute_command("DEL", key)
        return bool(result)

    async def incr(self, key: str) -> int:
        """Increment the integer value of a key by one."""
        result = await self.execute_command("INCR", key)
        return int(result) if result is not None else 0

    async def ttl(self, key: str) -> int:
        """Get the time to live for a key in seconds."""
        result = await self.execute_command("TTL", key)
        return int(result) if result is not None else -2

    async def eval(self, script: str, numkeys: int, *keys_and_args: Any) -> Any:
        """Execute a Lua script on Redis via EVAL."""
        return await self.execute_command("EVAL", script, int(numkeys), *keys_and_args)

    async def ping(self) -> bool:
        """Ping the Upstash Redis instance to verify connectivity."""
        result = await self.execute_command("PING")
        return result == "PONG"

    async def aclose(self) -> None:
        """Close the underlying HTTP client session cleanly."""
        if self._http_client is not None and not self._http_client.is_closed:
            await self._http_client.aclose()
            self._http_client = None

    async def close(self) -> None:
        """Alias for aclose."""
        await self.aclose()


# _redis_client: Optional[Redis] = None
_redis_client: Optional[UpstashRedisRestClient] = None
_redis_lock = threading.Lock()


def get_redis_client() -> UpstashRedisRestClient:
    """Retrieve or initialize the global singleton Upstash Redis client instance with thread safety."""
    global _redis_client
    if _redis_client is None:
        with _redis_lock:
            if _redis_client is None:
                # Old Redis initialization:
                # _redis_client = Redis.from_url(
                #     settings.REDIS_URL,
                #     socket_timeout=settings.REDIS_SOCKET_TIMEOUT_SECONDS,
                #     socket_connect_timeout=settings.REDIS_CONNECT_TIMEOUT_SECONDS,
                #     decode_responses=True,
                # )
                _redis_client = UpstashRedisRestClient(
                    rest_url=settings.UPSTASH_REDIS_REST_URL,
                    rest_token=settings.UPSTASH_REDIS_REST_TOKEN,
                    timeout=getattr(settings, "UPSTASH_REDIS_REST_TIMEOUT_SECONDS", 2.0),
                )
    return _redis_client


async def close_redis_client() -> None:
    """Close the global Redis client connection cleanly on application shutdown."""
    global _redis_client
    if _redis_client is not None:
        try:
            await _redis_client.aclose()
        except Exception as exc:
            logger.warning("Error closing Upstash Redis client connection: %s", str(exc))
        finally:
            _redis_client = None


async def ping_redis() -> bool:

    """Health check guard for Upstash Redis connectivity.Fails open: if Redis is disabled or unreachable, logs a warning and returns False so application startup and core non-cached operations continue without interruption"""
    if not settings.RAG_CACHE_ENABLED:
        logger.info("RAG caching is disabled in configuration (RAG_CACHE_ENABLED=False).")
        return False

    if not settings.UPSTASH_REDIS_REST_URL or not settings.UPSTASH_REDIS_REST_TOKEN:
        logger.warning("Upstash Redis REST credentials not configured; RAG cache will be skipped.")
        return False

    try:
        r_client = get_redis_client()
        pong = await r_client.ping()
        if pong:
            logger.info("Upstash Redis cache service connected successfully (%s).", settings.UPSTASH_REDIS_REST_URL)
            return True
        return False
    # except RedisError as exc:
    #     logger.warning("Redis unavailable; RAG cache will be skipped: %s", str(exc))
    #     return False
    except UpstashRedisError as exc:
        logger.warning("Upstash Redis unavailable; RAG cache will be skipped: %s", str(exc))
        return False
    except Exception as exc:
        logger.warning("Unexpected error checking Upstash Redis status; RAG cache will be skipped: %s", str(exc))
        return False
