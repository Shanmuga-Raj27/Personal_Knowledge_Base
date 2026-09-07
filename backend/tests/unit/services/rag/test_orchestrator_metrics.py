"""
backend/tests/unit/services/rag/test_orchestrator_metrics.py

Phase 7 Orchestrator instrumentation unit tests.

Drives run_rag_query end-to-end over a real in-memory SQLite session with
Qdrant/Gemini/Redis all mocked and the RAG_METRICS_ENABLED flag forced on,
then asserts the runtime-metrics store was populated per stage and counter.
The `finally`-guarded generate block is also exercised so the timer always
samples, even when a stream dies mid-generation.
"""
import asyncio
import pytest
from contextlib import ExitStack
from unittest.mock import AsyncMock, patch
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import settings
from app.database import Base
from app.services.rag import runtime_metrics
from app.services.rag.rag_orchestrator import RAGRequest, run_rag_query

UUID_A = "01234567-89ab-4cde-8f01-23456789abcd"
UUID_B = "abcdef01-2345-4678-9abc-def012345678"

SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"
engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture
def db():
    Base.metadata.create_all(bind=engine)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture(autouse=True)
def _metrics_isolation():
    runtime_metrics.reset()
    yield
    runtime_metrics.reset()


def _hits():
    return [
        {
            "chunk_id": UUID_A, "file_id": 10, "index_version": 1,
            "chunk_index": 0, "score": 0.9, "rank": 0,
        },
        {
            "chunk_id": UUID_B, "file_id": 10, "index_version": 1,
            "chunk_index": 1, "score": 0.8, "rank": 1,
        },
    ]


def _hydrated():
    return [
        {
            "chunk_id": UUID_A, "file_id": 10, "index_version": 1,
            "chunk_index": 0, "clean_text": "alpha content alpha content " * 30,
            "page_start": 1, "page_end": 1, "original_filename": "doc10.pdf",
            "score": 0.9, "rank": 0,
        },
        {
            "chunk_id": UUID_B, "file_id": 10, "index_version": 1,
            "chunk_index": 1, "clean_text": "beta content beta content " * 30,
            "page_start": 2, "page_end": 2, "original_filename": "doc10.pdf",
            "score": 0.8, "rank": 1,
        },
    ]


def _successful_patches():
    async def fake_stream(question, sources):
        for s in sources:
            yield f"tok {s.chunk_id} id={s.chunk_id} "

    return (
        patch("app.services.rag.rag_orchestrator.get_cached_answer", AsyncMock(return_value=None)),
        patch("app.services.rag.rag_orchestrator.set_cached_answer", AsyncMock()),
        patch("app.services.rag.rag_orchestrator.search_similar_chunks", return_value=_hits()),
        patch("app.services.rag.rag_orchestrator.hydrate_chunks", return_value=_hydrated()),
        patch("app.services.rag.rag_orchestrator.generate_answer_stream", side_effect=fake_stream),
    )


async def _collect(request, db):
    return [ev async for ev in run_rag_query(request, db=db)]


def _run(patchers, request, db):
    with ExitStack() as stack:
        for p in patchers:
            stack.enter_context(p)
        events = asyncio.run(_collect(request, db))
    return events, runtime_metrics.snapshot()


def test_happy_path_records_expected_stages_and_counters(db):
    request = RAGRequest(user_id=1, question="q")
    with patch.object(settings, "RAG_METRICS_ENABLED", True):
        events, snap = _run(_successful_patches(), request, db)

    assert events[-1]["diagnostics"]["sources_used"] == 2
    assert snap["enabled"] is True
    assert snap["counters"]["queries.total"] == 1
    assert snap["counters"]["queries.cache_miss"] == 1
    assert snap["counters"].get("queries.cache_hit") is None
    assert snap["counters"].get("queries.abstain") is None
    assert snap["counters"]["citations.valid"] == 2


def test_happy_path_records_all_stage_samples(db):
    request = RAGRequest(user_id=1, question="q")
    with patch.object(settings, "RAG_METRICS_ENABLED", True):
        _, snap = _run(_successful_patches(), request, db)

    stages = set(snap["stages"])
    assert stages >= {
        "validate", "cache_read", "search", "hydrate", "postprocess",
        "generate", "citation", "cache_write", "total",
    }
    for name in ("generate", "search", "hydrate"):
        assert snap["stages"][name]["calls"] == 1
        assert snap["stages"][name]["max_ms"] >= 0.0


def test_metrics_are_noop_when_flag_off(db):
    request = RAGRequest(user_id=1, question="q")
    events, snap = _run(_successful_patches(), request, db)

    assert events[-1]["diagnostics"]["sources_used"] == 2  # behaviour unchanged
    assert snap["enabled"] is False
    assert snap["counters"] == {}
    assert snap["stages"] == {}


def test_cache_hit_records_cached_path_only(db):
    request = RAGRequest(user_id=1, question="q")
    patches = [
        patch("app.services.rag.rag_orchestrator.get_cached_answer", AsyncMock(return_value="cached!")),
        patch("app.services.rag.rag_orchestrator.set_cached_answer", AsyncMock()),
        patch("app.services.rag.rag_orchestrator.search_similar_chunks", return_value=_hits()),
    ]
    with patch.object(settings, "RAG_METRICS_ENABLED", True):
        events, snap = _run(patches, request, db)

    assert events[-1]["diagnostics"]["cache_hit"] is True
    assert snap["counters"]["queries.total"] == 1
    assert snap["counters"]["queries.cache_hit"] == 1
    assert snap["counters"].get("queries.cache_miss") is None
    assert snap["counters"].get("queries.abstain") is None
    assert not {"search", "hydrate", "generate"} & set(snap["stages"])
    assert {"validate", "cache_read", "total"} <= set(snap["stages"])


def test_no_hits_abstain_records_abstention(db):
    request = RAGRequest(user_id=1, question="q")
    patches = [
        patch("app.services.rag.rag_orchestrator.get_cached_answer", AsyncMock(return_value=None)),
        patch("app.services.rag.rag_orchestrator.set_cached_answer", AsyncMock()),
        patch("app.services.rag.rag_orchestrator.search_similar_chunks", return_value=[]),
    ]
    with patch.object(settings, "RAG_METRICS_ENABLED", True):
        events, snap = _run(patches, request, db)

    assert events[-1]["diagnostics"]["insufficient_evidence"] is True
    assert snap["counters"]["queries.abstain"] == 1
    assert "search" in snap["stages"]
    assert not {"hydrate", "generate", "citation"} & set(snap["stages"])
    assert "total" in snap["stages"]


def test_generate_stage_recorded_even_when_stream_fails_midway(db):
    """The finally-guarded generate timer must fire even on mid-stream failure."""

    async def broken_stream(question, sources):
        yield "x"
        raise RuntimeError("mid-stream failure")

    request = RAGRequest(user_id=1, question="q")
    patches = [
        patch("app.services.rag.rag_orchestrator.get_cached_answer", AsyncMock(return_value=None)),
        patch("app.services.rag.rag_orchestrator.set_cached_answer", AsyncMock()),
        patch("app.services.rag.rag_orchestrator.search_similar_chunks", return_value=_hits()),
        patch("app.services.rag.rag_orchestrator.hydrate_chunks", return_value=_hydrated()),
        patch("app.services.rag.rag_orchestrator.generate_answer_stream", side_effect=broken_stream),
    ]
    with patch.object(settings, "RAG_METRICS_ENABLED", True):
        with pytest.raises(RuntimeError):
            _run(patches, request, db)

    snap = runtime_metrics.snapshot()
    assert snap["stages"]["generate"]["calls"] == 1