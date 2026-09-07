"""
backend/tests/integration/security/test_guessed_ids.py

Phase 7 security group — guessed / nonexistent file IDs.

Proves the section-7 ID-guessing table:
    - a nonexistent file ID and a foreign file ID return the SAME 404
      detail, so the endpoint never acts as an existence oracle;
    - the search surface likewise refuses unknown scoped file IDs (400 via
      validate_file_ids, same message regardless of why).
"""
from tests.integration.security.conftest import (
    client,
    authenticated,
    ALICE,
    BOB_FILE,
    ALICE_FILE,
)


class TestGuessedIds:
    def test_nonexistent_and_foreign_return_same_detail(self, authenticated):
        missing = client.get("/documents/999/index-status").json()["detail"]
        foreign = client.get(f"/documents/{BOB_FILE}/index-status").json()["detail"]
        assert missing == foreign
        assert "access denied" in missing.lower()

    def test_nonexistent_chunks_404(self, authenticated):
        assert client.get("/documents/999/chunks").status_code == 404

    def test_trigger_unknown_id_404(self, authenticated):
        resp = client.post("/documents", json={"file_id": 999})
        assert resp.status_code == 404

    def test_delete_unknown_id_404(self, authenticated):
        with __import__("unittest.mock", fromlist=["patch"]).patch(
            "app.apis.routes.document_routes.delete_s3_object"
        ) as m_s3:
            resp = client.delete("/files/999")
        assert resp.status_code == 404
        m_s3.assert_not_called()

    def test_scoped_query_unknown_id_400(self, authenticated):
        resp = client.post("/rag/query", json={"question": "q", "file_ids": [999]})
        assert resp.status_code == 400
        assert "owned, active, and indexed" in resp.json()["detail"]

    def test_owned_file_not_leaked(self, authenticated):
        """Alice's own id still validates (200 stream); the 400s above are for
        unknowns only — owning an id must never be confusable with it being invalid."""
        from unittest.mock import patch

        async def fake_run(request, db):
            yield {"type": "final", "sources": [], "diagnostics": {}}

        with patch("app.apis.routes.rag_routes.run_rag_query", side_effect=fake_run):
            resp = client.post("/rag/query", json={"question": "q", "file_ids": [ALICE_FILE]})
        assert resp.status_code == 200