"""
backend/tests/integration/routes/test_rag_routes.py

Integration tests for POST /rag/query SSE endpoint:
- auth: unauthenticated → 401
- SSE framing: token + final events framed as 'data: {...}' lines
- invalid file_ids → clean 400 before streaming
- generation error → SSE error frame (no traceback as 200)
"""
import pytest
from fastapi.testclient import TestClient
from unittest.mock import MagicMock, patch

from main import app
from app.database import get_db
from app.auth.auth_dependencies import get_current_user
from app.database.db_models import User

client = TestClient(app)

mock_db_session = MagicMock()
mock_test_user = User(id=42, email="test@example.com", hashed_password="pw", status="active")


def override_get_db():
    yield mock_db_session


def override_get_current_user():
    return mock_test_user


@pytest.fixture(autouse=True)
def setup_dependency_overrides():
    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = override_get_current_user
    mock_db_session.reset_mock()
    yield
    app.dependency_overrides.pop(get_db, None)
    app.dependency_overrides.pop(get_current_user, None)


def test_rag_query_requires_auth():
    app.dependency_overrides.pop(get_current_user, None)
    try:
        response = client.post("/rag/query", json={"question": "Summarize"})
        assert response.status_code == 401
    finally:
        app.dependency_overrides[get_current_user] = override_get_current_user


def test_rag_query_streams_token_and_final():
    async def fake_run_rag_query(rag_request, db):
        yield {"type": "token", "text": "Hello"}
        yield {"type": "final", "sources": [], "diagnostics": {"cache_hit": False}}

    with patch("app.apis.routes.rag_routes.run_rag_query", new=fake_run_rag_query):
        response = client.post("/rag/query", json={"question": "Hi"})

        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        assert response.headers["cache-control"] == "no-cache"

        body = response.text
        assert ": connected" in body
        assert 'data: {"type": "token", "text": "Hello"}' in body
        assert 'data: {"type": "final", "sources": []' in body


def test_rag_query_invalid_file_ids_returns_400():
    def fake_validate(user_id, file_ids, db):
        raise ValueError("None of the requested file IDs are owned, active, and indexed for this user.")

    with patch("app.apis.routes.rag_routes.validate_file_ids", side_effect=fake_validate):
        response = client.post(
            "/rag/query",
            json={"question": "Hi", "file_ids": [999]},
        )
        assert response.status_code == 400
        assert "None of the requested file IDs" in response.json()["detail"]


def test_rag_query_generation_error_frames_clean_error():
    async def failing_run_rag_query(rag_request, db):
        raise RuntimeError("gemini exploded")
        yield  # pragma: no cover — makes this an async generator

    with patch("app.apis.routes.rag_routes.run_rag_query", new=failing_run_rag_query):
        response = client.post("/rag/query", json={"question": "Hi"})
        assert response.status_code == 200
        assert "Internal error during answer generation" in response.text
        assert "traceback" not in response.text.lower()


def test_rag_query_search_all_when_no_file_ids():
    seen = {}

    async def fake_run_rag_query(rag_request, db):
        seen["file_ids"] = rag_request.file_ids
        seen["top_k"] = rag_request.top_k
        seen["score_threshold"] = rag_request.score_threshold
        yield {"type": "final", "sources": [], "diagnostics": {"insufficient_evidence": True}}

    with patch("app.apis.routes.rag_routes.run_rag_query", new=fake_run_rag_query):
        response = client.post(
            "/rag/query",
            json={"question": "Search everything", "top_k": 8, "score_threshold": 0.5},
        )
        assert response.status_code == 200
        assert seen["file_ids"] is None
        assert seen["top_k"] == 8
        assert seen["score_threshold"] == 0.5
        assert "insufficient_evidence" in response.text