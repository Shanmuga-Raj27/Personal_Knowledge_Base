"""
backend/tests/unit/services/test_redis_cache.py

Unit tests for Redis cache client factory, fail-open ping guard, and shutdown cleanup.
"""
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from redis.exceptions import RedisError

from app.services.cache.redis_cache import get_redis_client, ping_redis, close_redis_client


def test_get_redis_client_singleton():
    """Test that get_redis_client returns a valid Redis instance."""
    client1 = get_redis_client()
    client2 = get_redis_client()
    assert client1 is client2


def test_ping_redis_disabled():
    """Test that ping_redis returns False immediately when RAG_CACHE_ENABLED is False."""
    async def _run():
        with patch("app.services.cache.redis_cache.settings.RAG_CACHE_ENABLED", False):
            result = await ping_redis()
            assert result is False

    asyncio.run(_run())


def test_ping_redis_success():
    """Test that ping_redis returns True when Redis responds to ping."""
    async def _run():
        mock_r_client = MagicMock()
        mock_r_client.ping = AsyncMock(return_value=True)

        with patch("app.services.cache.redis_cache.settings.RAG_CACHE_ENABLED", True), \
             patch("app.services.cache.redis_cache.get_redis_client", return_value=mock_r_client):
            result = await ping_redis()
            assert result is True
            mock_r_client.ping.assert_called_once()

    asyncio.run(_run())


def test_ping_redis_failure_fail_open():
    """Test that ping_redis catches RedisError, logs warning, and returns False (fail open)."""
    async def _run():
        mock_r_client = MagicMock()
        mock_r_client.ping = AsyncMock(side_effect=RedisError("Connection refused"))

        with patch("app.services.cache.redis_cache.settings.RAG_CACHE_ENABLED", True), \
             patch("app.services.cache.redis_cache.get_redis_client", return_value=mock_r_client):
            result = await ping_redis()
            assert result is False

    asyncio.run(_run())


def test_close_redis_client():
    """Test that close_redis_client closes the active connection cleanly."""
    async def _run():
        mock_r_client = MagicMock()
        mock_r_client.aclose = AsyncMock()

        with patch("app.services.cache.redis_cache._redis_client", mock_r_client):
            await close_redis_client()
            mock_r_client.aclose.assert_called_once()

    asyncio.run(_run())
