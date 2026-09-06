"""
backend/tests/unit/services/rag/test_retry.py

Retry classification and with_retry (RAG-phase-4.md:589-624)
"""
import pytest
from unittest.mock import MagicMock

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
