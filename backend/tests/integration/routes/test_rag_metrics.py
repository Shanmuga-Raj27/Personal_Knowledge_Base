"""
backend/tests/integration/routes/test_rag_metrics.py

Phase 7 /system/rag-metrics integration tests.

Covers the two-layer gate (authentication + RAG_METRICS_ENABLED flag) and the
end-to-end wiring: a real orchestrator run writes to the runtime-metrics store
and the authenticated route returns exactly that live snapshot.
"""
import asyncio
import pytest
from unittest.mock import AsyncMock, patch
from fastapi.testclient import TestClient

from main import app
from app.core.config import settings
from app.core.security import create_access_token
from app.services.rag import runtime_metrics
from app.services.rag.rag_orchestrator import RAGRequest, run_rag_query

client = TestClient(app)

UUID_A = "01234567-89ab-4cde-8f01-23456789abcd"
UUID_B = "abcdef01-2345-4678-9abc-def012345678"


@pytest.fixture(autouse=True)
def _metrics_isolation():
    runtime_metrics.reset()
    yield
    runtime_metrics.reset()


def _auth(token: str | None = None) -> dict:
    return {"Authorization": f"Bearer {token or create_access_token(user_id=1)}"}


def test_rag_metrics_requires_authentication():
    """No token -> 401, regardless of the feature flag."""
    with patch.object(settings, "RAG_METRICS_ENABLED", True):
        response = client.get("/system/rag-metrics")
    assert response.status_code == 401


def test_rag_metrics_disabled_by_default(real_jwt_db_only):
    """Flag off (the default) -> 404, even with a valid authenticated user."""
    response = client.get("/system/rag-metrics", headers=_auth())
    assert response.status_code == 404
    assert response.json() == {"detail": "RAG metrics are disabled."}


def test_rag_metrics_enabled_returns_authenticated_live_snapshot(
    real_jwt_db_only, monkeypatch
):
    monkeypatch.setattr(settings, "RAG_METRICS_ENABLED", True)
    runtime_metrics.increment("queries.total", 7)

    response = client.get("/system/rag-metrics", headers=_auth())
    assert response.status_code == 200
    body = response.json()
    assert body["enabled"] is True
    assert body["counters"]["queries.total"] == 7
    assert body["stages"] == {}


def test_orchestrator_metrics_visible_through_route(
    real_jwt_db_only, db_session, monkeypatch
):
    """E2E: a real orchestrator run populates the store the route reads."""
    monkeypatch.setattr(settings, "RAG_METRICS_ENABLED", True)

    hits = [
        {"chunk_id": UUID_A, "file_id": 10, "index_version": 1,
         "chunk_index": 0, "score": 0.9, "rank": 0},
        {"chunk_id": UUID_B, "file_id": 10, "index_version": 1,
         "chunk_index": 1, "score": 0.8, "rank": 1},
    ]
    hydrated = [
        {"chunk_id": UUID_A, "file_id": 10, "index_version": 1,
         "chunk_index": 0, "clean_text": "alpha content alpha content " * 30,
         "page_start": 1, "page_end": 1, "original_filename": "doc10.pdf",
         "score": 0.9, "rank": 0},
        {"chunk_id": UUID_B, "file_id": 10, "index_version": 1,
         "chunk_index": 1, "clean_text": "beta content beta content " * 30,
         "page_start": 2, "page_end": 2, "original_filename": "doc10.pdf",
         "score": 0.8, "rank": 1},
    ]

    async def fake_stream(question, sources):
        for s in sources:
            yield f"tok id={s.chunk_id} "

    async def run():
        return [ev async for ev in run_rag_query(RAGRequest(user_id=1, question="q"), db=db_session)]

    with patch("app.services.rag.rag_orchestrator.get_cached_answer", AsyncMock(return_value=None)), \
         patch("app.services.rag.rag_orchestrator.set_cached_answer", AsyncMock()), \
         patch("app.services.rag.rag_orchestrator.search_similar_chunks", return_value=hits), \
         patch("app.services.rag.rag_orchestrator.hydrate_chunks", return_value=hydrated), \
         patch("app.services.rag.rag_orchestrator.generate_answer_stream", side_effect=fake_stream):
        events = asyncio.run(run())
    assert events[-1]["diagnostics"]["sources_used"] == 2

    response = client.get("/system/rag-metrics", headers=_auth())
    assert response.status_code == 200
    body = response.json()
    assert body["counters"]["queries.total"] == 1
    assert body["counters"]["queries.cache_miss"] == 1
    assert body["counters"]["citations.valid"] == 2
    for stage in (
        "validate", "cache_read", "search", "hydrate", "postprocess",
        "generate", "citation", "cache_write", "total",
    ):
        assert body["stages"][stage]["calls"] == 1