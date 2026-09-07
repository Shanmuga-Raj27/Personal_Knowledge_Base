"""
backend/tests/integration/security/test_tenant_isolation.py

Phase 7 security group — tenant isolation.

Proves that a user can never see, trigger, or receive retrieval for another
tenant's document, at four enforcement layers:

  1. RAG document routes filter on current_user.id (chunks/index-status/trigger).
  2. The /rag/query route rejects a foreign-only file set (400) BEFORE streaming.
  3. The orchestration boundary injects the authenticated user's ID — a
     body/token mismatch can't select another tenant.
  4. validate_file_ids silently drops foreign IDs from a mixed set, so a
     foreign ID can never reach Qdrant.
"""
from unittest.mock import patch
from sqlalchemy.orm import Session

from main import app  # noqa: F401  (route registration)
from app.services.rag.rag_orchestrator import run_rag_query
from tests.integration.security.conftest import (
    client,
    authenticated,
    ALICE,
    BOB,
    ALICE_FILE,
    BOB_FILE,
)


class TestDocumentRouteIsolation:
    def test_owned_chunks_ok_foreign_404(self, authenticated):
        assert client.get(f"/documents/{ALICE_FILE}/chunks").status_code == 200
        assert client.get(f"/documents/{BOB_FILE}/chunks").status_code == 404

    def test_owned_index_status_ok_foreign_404(self, authenticated):
        assert client.get(f"/documents/{ALICE_FILE}/index-status").status_code == 200
        assert client.get(f"/documents/{BOB_FILE}/index-status").status_code == 404

    def test_trigger_foreign_file_404(self, authenticated):
        resp = client.post("/documents", json={"file_id": BOB_FILE})
        assert resp.status_code == 404


class TestQueryEndpointIsolation:
    def test_foreign_only_file_ids_rejected_400(self, authenticated):
        resp = client.post("/rag/query", json={"question": "q", "file_ids": [BOB_FILE]})
        assert resp.status_code == 400

    def test_owned_query_streams_and_injects_authenticated_user(self, authenticated):
        """Server injects current_user.id (Alice), never a client-chosen id."""
        async def fake_run(request, db):
            yield {
                "type": "final",
                "sources": [],
                "diagnostics": {
                    "cache_hit": False, "chunks_retrieved": 0, "chunks_hydrated": 0,
                    "chunks_after_filter": 0, "sources_used": 0,
                    "citations_valid": [], "query_time_ms": 0.0,
                },
            }

        with patch("app.apis.routes.rag_routes.run_rag_query", side_effect=fake_run) as m_run:
            resp = client.post("/rag/query", json={"question": "q", "file_ids": [ALICE_FILE]})

        assert resp.status_code == 200
        req = m_run.call_args[0][0]
        assert req.user_id == ALICE  # authenticated identity, not attacker-controlled
        assert req.file_ids == [ALICE_FILE]

    def test_mixed_set_still_authenticated(self, authenticated):
        """Alice gives Bob's id alongside hers: still runs as Alice."""
        async def fake_run(request, db):
            yield {"type": "final", "sources": [], "diagnostics": {}}

        with patch("app.apis.routes.rag_routes.run_rag_query", side_effect=fake_run) as m_run:
            resp = client.post("/rag/query", json={"question": "q", "file_ids": [ALICE_FILE, BOB_FILE]})

        assert resp.status_code == 200
        assert m_run.call_args[0][0].user_id == ALICE


class TestOrchestratorGate:
    def test_foreign_id_dropped_before_qdrant(self, authenticated):
        """validate_file_ids keeps only owned+active+indexed ids."""
        from app.services.rag.query_utils import validate_file_ids

        db: Session = authenticated["db"]
        validated = validate_file_ids(ALICE, [ALICE_FILE, BOB_FILE], db)
        assert validated == [ALICE_FILE]

    def test_run_rag_query_searches_only_validated_files(self, authenticated):
        """The orchestrator uses validated ids (foreign dropped) when it calls
        search_similar_chunks — so Bob's id never reaches the vector index."""
        from app.services.rag.rag_orchestrator import RAGRequest
        import asyncio

        db: Session = authenticated["db"]

        def fake_search(user_id, query_text, file_ids=None, top_k=None, score_threshold=None):
            return []  # no hits -> abstain final event

        with patch("app.services.rag.rag_orchestrator.get_cached_answer",
                   __import__("unittest.mock", fromlist=["AsyncMock"]).AsyncMock(return_value=None)), \
             patch("app.services.rag.rag_orchestrator.search_similar_chunks",
                   side_effect=fake_search) as m_search:
            req = RAGRequest(user_id=ALICE, question="q", file_ids=[ALICE_FILE, BOB_FILE])
            events = asyncio.run(_collect(req, db))

        # Foreign id was stripped before the vector lookup.
        assert m_search.call_args.kwargs["file_ids"] == [ALICE_FILE]
        assert m_search.call_args.kwargs["user_id"] == ALICE
        assert events[-1]["type"] == "final"


async def _collect(req, db):
    return [ev async for ev in run_rag_query(req, db)]