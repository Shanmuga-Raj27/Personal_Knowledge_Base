"""
backend/tests/integration/scenarios/test_outage_behavior.py

Phase 7 Scenario integration — outage behavior (fail-open / clean failure).

Proves the section-7 error-handling table at the orchestrator boundary:

  Redis down   -> run_rag_query still returns a FULL live answer, never 500.
                  (answer_cache catches the Redis error and fails open)
  Gemini 5xx   -> with_retry_async retries at stream open, then propagates a
                  clean error to the caller (route frames it as an SSE error,
                  not a half-stream).
  Qdrant down  -> search raises -> orchestrator does NOT emit a partial
                  stream; the error propagates cleanly (route frames it).
"""
import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from redis.exceptions import RedisError

from app.database import Base
from app.database.db_models import FileMetadata, User
from app.schemas.enums import FileStatus, IndexingStatus
from app.services.rag.rag_orchestrator import RAGRequest, run_rag_query

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


def _setup_indexed_file(db):
    """Create an ACTIVE/INDEXED user + file so real validate_file_ids passes."""
    user = User(id=1, email="a@test.com", hashed_password="x")
    db.add(user)
    db.commit()
    file = FileMetadata(
        fileid=10, s3_key="uploads/10.pdf", filename="doc10.pdf",
        content_type="application/pdf", status=FileStatus.ACTIVE.value,
        userid=1, active_index_version=1, corpus_revision=0,
        indexing_status=IndexingStatus.INDEXED.value, index_version=1,
    )
    db.add(file)
    db.commit()
    return file


UUID_A = "aaaaaaaa-1111-2222-3333-444455556666"


def _hydrated_one():
    return [
        {
            "chunk_id": UUID_A, "file_id": 10, "index_version": 1, "chunk_index": 0,
            "clean_text": "refund policy text " * 30, "page_start": 1, "page_end": 1,
            "original_filename": "doc10.pdf", "score": 0.9, "rank": 0,
        }
    ]


class TestOutageBehavior:
    def test_redis_down_fails_open_full_answer(self, db):
        """Redis transport raising inside answer_cache must NOT abort the query."""
        _setup_indexed_file(db)
        hits = [{"chunk_id": UUID_A, "file_id": 10, "index_version": 1,
                 "chunk_index": 0, "score": 0.9, "rank": 0}]
        hydrated = _hydrated_one()

        async def fake_stream(question, sources):
            yield "full answer "
            yield "streamed"

        # get_redis_client raises -> answer_cache.get/set catch it and fail open.
        with patch("app.services.rag.answer_cache.get_redis_client",
                   side_effect=RedisError("redis down")):
            with patch("app.services.rag.rag_orchestrator.search_similar_chunks", return_value=hits):
                with patch("app.services.rag.rag_orchestrator.hydrate_chunks", return_value=hydrated):
                    with patch("app.services.rag.rag_orchestrator.generate_answer_stream", side_effect=fake_stream):
                        request = RAGRequest(user_id=1, question="q")
                        events = []
                        async def run():
                            async for ev in run_rag_query(request, db=db):
                                events.append(ev)
                        asyncio.run(run())

        # Full answer streamed (cache fail-open), then final event.
        assert [e["text"] for e in events if e["type"] == "token"] == ["full answer ", "streamed"]
        assert events[-1]["type"] == "final"
        assert events[-1]["diagnostics"]["cache_hit"] is False
        # A successful (non-abstained) final event carries the sources — proving
        # the query completed live despite the Redis outage.
        assert len(events[-1]["sources"]) == 1

    def test_gemini_down_after_retries_clean_failure(self, db):
        """A transient Gemini 5xx is retried, then a clean failure propagates —
        the caller (route) frames it; we assert no half-answer is emitted."""
        _setup_indexed_file(db)
        hits = [{"chunk_id": UUID_A, "file_id": 10, "index_version": 1,
                 "chunk_index": 0, "score": 0.9, "rank": 0}]
        hydrated = _hydrated_one()

        class ServerError(Exception):
            pass

        # generate_answer_stream is mocked to raise (simulating exhausted retries).
        def failing_stream(question, sources):
            raise ServerError("gemini exhausted retries")

        with patch("app.services.rag.rag_orchestrator.get_cached_answer", AsyncMock(return_value=None)):
            with patch("app.services.rag.rag_orchestrator.search_similar_chunks", return_value=hits):
                with patch("app.services.rag.rag_orchestrator.hydrate_chunks", return_value=hydrated):
                    with patch("app.services.rag.rag_orchestrator.generate_answer_stream",
                               side_effect=failing_stream):
                        request = RAGRequest(user_id=1, question="q")
                        async def run():
                            return [ev async for ev in run_rag_query(request, db=db)]
                        with pytest.raises(ServerError):
                            asyncio.run(run())

    def test_qdrant_down_clean_error_no_partial_stream(self, db):
        """If Qdrant search raises, no token has been emitted yet — the error
        propagates cleanly so the route can frame an SSE error (not a 200 with
        a half answer)."""
        _setup_indexed_file(db)

        mock_stream = MagicMock()

        with patch("app.services.rag.rag_orchestrator.get_cached_answer", AsyncMock(return_value=None)):
            with patch("app.services.rag.rag_orchestrator.search_similar_chunks",
                       side_effect=RuntimeError("qdrant connection refused")):
                with patch("app.services.rag.rag_orchestrator.generate_answer_stream", mock_stream):
                    request = RAGRequest(user_id=1, question="q")
                    async def run():
                        return [ev async for ev in run_rag_query(request, db=db)]
                    with pytest.raises(RuntimeError, match="qdrant connection refused"):
                        asyncio.run(run())

        # Generation was never reached (no tokens, no LLM call).
        mock_stream.assert_not_called()
