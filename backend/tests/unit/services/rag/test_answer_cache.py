"""
backend/tests/unit/services/rag/test_answer_cache.py

Unit tests for Phase 5 answer_cache:
- RAG_CACHE_ENABLED short-circuits (no Redis calls)
- cache hit returns value, miss returns None
- fail-open: Redis exceptions never propagate
"""
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from redis.exceptions import RedisError

from app.services.rag.answer_cache import get_cached_answer, set_cached_answer


class TestGetCachedAnswer:
    def test_disabled_returns_none(self):
        async def _run():
            with patch("app.services.rag.answer_cache.settings.RAG_CACHE_ENABLED", False):
                assert await get_cached_answer("k") is None

        asyncio.run(_run())

    def test_hit_returns_value(self):
        async def _run():
            mock_client = MagicMock()
            mock_client.get = AsyncMock(return_value="the answer")
            with patch("app.services.rag.answer_cache.settings.RAG_CACHE_ENABLED", True), \
                 patch("app.services.rag.answer_cache.get_redis_client", return_value=mock_client):
                assert await get_cached_answer("k") == "the answer"
                mock_client.get.assert_awaited_once_with("k")

        asyncio.run(_run())

    def test_miss_returns_none(self):
        async def _run():
            mock_client = MagicMock()
            mock_client.get = AsyncMock(return_value=None)
            with patch("app.services.rag.answer_cache.settings.RAG_CACHE_ENABLED", True), \
                 patch("app.services.rag.answer_cache.get_redis_client", return_value=mock_client):
                assert await get_cached_answer("k") is None

        asyncio.run(_run())

    def test_redis_error_fail_open(self):
        async def _run():
            mock_client = MagicMock()
            mock_client.get = AsyncMock(side_effect=RedisError("down"))
            with patch("app.services.rag.answer_cache.settings.RAG_CACHE_ENABLED", True), \
                 patch("app.services.rag.answer_cache.get_redis_client", return_value=mock_client):
                assert await get_cached_answer("k") is None  # never raises

        asyncio.run(_run())

    def test_generic_exception_fail_open(self):
        async def _run():
            mock_client = MagicMock()
            mock_client.get = AsyncMock(side_effect=RuntimeError("boom"))
            with patch("app.services.rag.answer_cache.settings.RAG_CACHE_ENABLED", True), \
                 patch("app.services.rag.answer_cache.get_redis_client", return_value=mock_client):
                assert await get_cached_answer("k") is None

        asyncio.run(_run())


class TestSetCachedAnswer:
    def test_disabled_is_noop(self):
        async def _run():
            with patch("app.services.rag.answer_cache.settings.RAG_CACHE_ENABLED", False), \
                 patch("app.services.rag.answer_cache.get_redis_client") as mock_get:
                await set_cached_answer("k", "v")
            mock_get.assert_not_called()

        asyncio.run(_run())

    def test_sets_with_ttl(self):
        async def _run():
            mock_client = MagicMock()
            mock_client.setex = AsyncMock()
            with patch("app.services.rag.answer_cache.settings.RAG_CACHE_ENABLED", True), \
                 patch("app.services.rag.answer_cache.settings.RAG_CACHE_TTL_SECONDS", 3600), \
                 patch("app.services.rag.answer_cache.get_redis_client", return_value=mock_client):
                await set_cached_answer("k", "v")
            mock_client.setex.assert_awaited_once_with("k", 3600, "v")

        asyncio.run(_run())

    def test_redis_error_never_raises(self):
        async def _run():
            mock_client = MagicMock()
            mock_client.setex = AsyncMock(side_effect=RedisError("down"))
            with patch("app.services.rag.answer_cache.settings.RAG_CACHE_ENABLED", True), \
                 patch("app.services.rag.answer_cache.get_redis_client", return_value=mock_client):
                await set_cached_answer("k", "v")  # never raises

        asyncio.run(_run())