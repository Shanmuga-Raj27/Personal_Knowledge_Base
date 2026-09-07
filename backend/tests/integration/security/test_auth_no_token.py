"""
backend/tests/integration/security/test_auth_no_token.py

Phase 7 security group — authentication enforcement at the RAG surface.

Proves the section-7 auth table:
    no token / bad token / unknown user  -> 401 (real JWT dependency)
    disabled user token                  -> 403
    every protected RAG/file endpoint    -> 401 without a token
"""
from fastapi.testclient import TestClient
from main import app
from tests.integration.security.conftest import (
    client,
    real_jwt_db_only,
    alice_token,
    bob_token,
    zoe_token,
)

AUTH_REQUIRED = [
    ("GET", "/files"),
    ("POST", "/files/view-url"),
    ("DELETE", "/files/10"),
    ("GET", "/documents/10/index-status"),
    ("GET", "/documents/10/chunks"),
    ("POST", "/documents"),
    ("POST", "/rag/query"),
]


class TestNoToken:
    def test_all_protected_endpoints_401_without_token(self):
        for method, url in AUTH_REQUIRED:
            resp = client.request(method, url)
            assert resp.status_code == 401, f"{method} {url} should be 401, got {resp.status_code}"


class TestRealJWTDependency:
    def test_garbage_token_401(self, real_jwt_db_only):
        resp = client.get("/documents/10/index-status",
                          headers={"Authorization": "Bearer not.a.jwt"})
        assert resp.status_code == 401
        assert resp.json()["detail"] == "Could not validate credentials"

    def test_unknown_user_token_401(self, real_jwt_db_only):
        from app.core.security import create_access_token
        token = create_access_token(user_id=99999)
        resp = client.get("/documents/10/index-status",
                          headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 401

    def test_disabled_user_token_403(self, real_jwt_db_only):
        resp = client.get("/documents/30/index-status",
                          headers={"Authorization": f"Bearer {zoe_token()}"})
        assert resp.status_code == 403
        assert resp.json()["detail"] == "User account is disabled"

    def test_valid_token_allows_owned_read(self, real_jwt_db_only):
        resp = client.get("/documents/10/index-status",
                          headers={"Authorization": f"Bearer {alice_token()}"})
        assert resp.status_code == 200
        assert resp.json()["file_id"] == 10

    def test_bob_token_cannot_read_alice_document(self, real_jwt_db_only):
        resp = client.get("/documents/10/index-status",
                          headers={"Authorization": f"Bearer {bob_token()}"})
        assert resp.status_code == 404