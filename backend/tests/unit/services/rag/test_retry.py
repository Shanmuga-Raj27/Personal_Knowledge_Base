"""
backend/tests/unit/services/rag/test_retry.py

Retry classification and with_retry (RAG-phase-4.md:589-624)

Phase 7 hardening (RAG-phase-7.md Step 1b):
- with_retry calls fn exactly N+1 times when success after N failures
- with_retry_async sleeps with asyncio.sleep, never blocking the event loop
"""
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.rag.retry import (
    ERROR_EMBEDDING_429,
    ERROR_EMBEDDING_5XX,
    ERROR_EMBEDDING_DIM_MISMATCH,
    ERROR_EMBEDDING_TIMEOUT,
    ERROR_QDRANT_COLLECTION_MISMATCH,
    classify_error,
    extract_status_code,
    is_retryable,
    is_timeout,
    with_retry,
    with_retry_async,
)


class TestExtractStatusCode:
    def test_direct_attribute(self):
        e = Exception("err")
        e.status_code = 429
        assert extract_status_code(e) == 429

    def test_response_wrapped(self):
        e = Exception("err")
        e.response = MagicMock(status_code=500)
        assert extract_status_code(e) == 500

    def test_string_429(self):
        assert extract_status_code(Exception("429 Too Many Requests")) == 429

    def test_none(self):
        assert extract_status_code(Exception("random")) is None


class TestIsTimeout:
    def test_timeout_name(self):
        assert is_timeout(TimeoutError("timeout")) is True
        class ReadTimeout(Exception):
            pass

        e = ReadTimeout("connection timeout")
        assert is_timeout(e) is True

    def test_timed_out_msg(self):
        assert is_timeout(Exception("request timed out")) is True

    def test_not_timeout(self):
        assert is_timeout(Exception("dimension mismatch")) is False


class TestIsRetryable:
    def test_429_retryable(self):
        e = Exception("429")
        e.status_code = 429
        assert is_retryable(e) is True

    def test_500_retryable(self):
        e = Exception("500")
        e.code = 500
        assert is_retryable(e) is True

    def test_400_not_retryable(self):
        e = Exception("400")
        e.status_code = 400
        assert is_retryable(e) is False

    def test_timeout_retryable(self):
        assert is_retryable(TimeoutError("timeout")) is True

    def test_dim_mismatch_not_retryable(self):
        assert is_retryable(RuntimeError("Unexpected embedding dimension")) is False


class TestClassifyError:
    def test_429(self):
        e = Exception("429")
        e.status_code = 429
        assert classify_error(e) == ERROR_EMBEDDING_429

    def test_timeout(self):
        assert classify_error(TimeoutError("timeout")) == ERROR_EMBEDDING_TIMEOUT

    def test_5xx(self):
        e = Exception("500")
        e.code = 503
        assert classify_error(e) == ERROR_EMBEDDING_5XX

    def test_dim_mismatch(self):
        assert classify_error(RuntimeError("dimension 768")) == ERROR_EMBEDDING_DIM_MISMATCH

    def test_collection_mismatch(self):
        assert classify_error(RuntimeError("collection distance mismatch cosine")) == ERROR_QDRANT_COLLECTION_MISMATCH


class TestWithRetry:
    def test_succeeds_after_retry(self, monkeypatch):
        monkeypatch.setattr("app.services.rag.retry.time.sleep", lambda x: None)
        calls = []

        def flaky():
            calls.append(1)
            if len(calls) == 1:
                e = Exception("429")
                e.status_code = 429
                raise e
            return "ok"

        assert with_retry(flaky, max_retries=3, base_delay=0.01) == "ok"
        assert len(calls) == 2

    def test_non_retryable_fails_fast(self, monkeypatch):
        monkeypatch.setattr("app.services.rag.retry.time.sleep", lambda x: None)
        calls = []

        def bad():
            calls.append(1)
            raise RuntimeError("dimension mismatch")

        with pytest.raises(RuntimeError):
            with_retry(bad, max_retries=5, base_delay=0.01)
        assert len(calls) == 1

    def test_exhausted_raises(self, monkeypatch):
        monkeypatch.setattr("app.services.rag.retry.time.sleep", lambda x: None)

        def always_fail():
            e = Exception("500")
            e.code = 500
            raise e

        with pytest.raises(Exception):
            with_retry(always_fail, max_retries=2, base_delay=0.01)


class TestWithRetryCallCount:
    def test_success_after_n_failures_calls_fn_n_plus_one_times(self, monkeypatch):
        """Phase 7: exactly N failures + 1 success = N+1 fn invocations."""
        monkeypatch.setattr("app.services.rag.retry.time.sleep", lambda x: None)
        calls = []

        def flaky():
            calls.append(1)
            if len(calls) <= 3:  # 3 failures, then success
                e = Exception("429")
                e.status_code = 429
                raise e
            return "ok"

        assert with_retry(flaky, max_retries=3, base_delay=0.01) == "ok"
        assert len(calls) == 4  # 3 failures + 1 success

    def test_no_extra_calls_on_first_try_success(self, monkeypatch):
        monkeypatch.setattr("app.services.rag.retry.time.sleep", lambda x: None)
        calls = []

        def works():
            calls.append(1)
            return "ok"

        assert with_retry(works, max_retries=5, base_delay=0.01) == "ok"
        assert len(calls) == 1


class TestWithRetryAsync:
    def test_success_after_retry(self, monkeypatch):
        """Async variant retries retryable failures and returns on success."""
        calls = []

        async def flaky():
            calls.append(1)
            if len(calls) == 1:
                e = Exception("429")
                e.status_code = 429
                raise e
            return "ok"

        with patch("app.services.rag.retry.asyncio.sleep", new=AsyncMock()):
            assert asyncio.run(with_retry_async(flaky, max_retries=3, base_delay=0.01)) == "ok"
        assert len(calls) == 2

    def test_uses_asyncio_sleep_not_time_sleep(self, monkeypatch):
        """Phase 7: must NOT block the event loop (uses asyncio.sleep)."""
        async_sleep = AsyncMock()

        async def always_fail():
            e = Exception("500")
            e.code = 503
            raise e

        with patch("app.services.rag.retry.asyncio.sleep", new=async_sleep):
            with patch("app.services.rag.retry.time.sleep") as sync_sleep:
                with pytest.raises(Exception):
                    asyncio.run(with_retry_async(always_fail, max_retries=2, base_delay=0.01))

        # The async path must wake the loop with asyncio.sleep, never time.sleep.
        assert async_sleep.await_count == 2
        sync_sleep.assert_not_called()

    def test_non_retryable_fails_fast(self):
        async def bad():
            raise RuntimeError("dimension mismatch")

        with patch("app.services.rag.retry.asyncio.sleep", new=AsyncMock()):
            with pytest.raises(RuntimeError, match="mismatch"):
                asyncio.run(with_retry_async(bad, max_retries=5, base_delay=0.01))
