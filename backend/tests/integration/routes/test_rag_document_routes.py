"""
backend/tests/integration/routes/test_rag_document_routes.py

Integration tests for /documents RAG endpoints:
- POST /documents: trigger indexing (202), auth (401), bad body (400),
  missing/foreign (404), not-active (400)
- GET /documents/{id}/index-status: owned (200), foreign (404)
- GET /documents/{id}/chunks: owned (200, respects index_version), foreign (404)

Uses a real in-memory SQLite DB via the get_db dependency override, and the
FakeParametersFromFileStatus pattern for owner scoping.
"""
import pytest
from unittest.mock import patch
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import StaticPool

from main import app
from app.database import Base, get_db
from app.auth.auth_dependencies import get_current_user
from app.database.db_models import DocumentChunk, FileMetadata, User
from app.schemas.enums import FileStatus, IndexingStatus

SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"
engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

client = TestClient(app)


def _make_user(db: Session, user_id: int) -> User:
    user = User(id=user_id, email=f"user{user_id}@example.com", hashed_password="pw", status="active")
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _make_file(
    db: Session,
    fileid: int,
    userid: int,
    status: str = FileStatus.ACTIVE.value,
    indexing_status: str = IndexingStatus.PENDING.value,
    s3_key: str | None = None,
) -> FileMetadata:
    file = FileMetadata(
        fileid=fileid,
        s3_key=s3_key or f"uploads/file_{fileid}.pdf",
        filename=f"file_{fileid}.pdf",
        content_type="application/pdf",
        size_bytes=1024,
        status=status,
        userid=userid,
        active_index_version=1,
        corpus_revision=0,
        indexing_status=indexing_status,
        index_version=1,
    )
    db.add(file)
    db.commit()
    db.refresh(file)
    return file


@pytest.fixture
def setup():
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    db_user = _make_user(db, 42)
    _make_file(db, fileid=10, userid=42)
    _make_file(db, fileid=20, userid=99)

    def override_get_db():
        yield db

    def override_get_current_user():
        return db_user

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = override_get_current_user
    yield
    app.dependency_overrides.pop(get_db, None)
    app.dependency_overrides.pop(get_current_user, None)
    db.close()
    Base.metadata.drop_all(bind=engine)


def test_trigger_requires_auth(setup):
    app.dependency_overrides.pop(get_current_user, None)
    response = client.post("/documents", json={"file_id": 10})
    assert response.status_code == 401


def test_trigger_by_file_id_202(setup):
    with patch(
        "app.apis.routes.rag_document_routes.sync_rag_chunks_in_background"
    ) as mock_worker:
        response = client.post("/documents", json={"file_id": 10})
        assert response.status_code == 202
        data = response.json()
        assert data["id"] == 10
        assert data["indexing_status"] == IndexingStatus.PENDING.value
        mock_worker.assert_called_once()


def test_trigger_by_s3_key_202(setup):
    with patch(
        "app.apis.routes.rag_document_routes.sync_rag_chunks_in_background"
    ) as mock_worker:
        response = client.post("/documents", json={"s3_key": "uploads/file_10.pdf"})
        assert response.status_code == 202
        assert response.json()["id"] == 10
        mock_worker.assert_called_once()


def test_trigger_neither_id_400(setup):
    response = client.post("/documents", json={})
    assert response.status_code == 400
    assert "exactly one" in response.json()["detail"].lower()


def test_trigger_both_id_400(setup):
    response = client.post(
        "/documents", json={"file_id": 10, "s3_key": "uploads/file_10.pdf"}
    )
    assert response.status_code == 400


def test_trigger_foreign_file_404(setup):
    response = client.post("/documents", json={"file_id": 20})
    assert response.status_code == 404


def test_trigger_missing_file_404(setup):
    response = client.post("/documents", json={"file_id": 999})
    assert response.status_code == 404


def test_trigger_not_active_400(setup):
    session = TestingSessionLocal()
    _make_file(
        session,
        fileid=30,
        userid=42,
        status=FileStatus.PENDING.value,
    )
    session.close()
    response = client.post("/documents", json={"file_id": 30})
    assert response.status_code == 400
    assert "not active" in response.json()["detail"].lower()


def test_index_status_owned_200(setup):
    response = client.get("/documents/10/index-status")
    assert response.status_code == 200
    data = response.json()
    assert data["file_id"] == 10
    assert data["indexing_status"] in [e.value for e in IndexingStatus]
    assert 0.0 <= data["progress"] <= 1.0


def test_index_status_foreign_404(setup):
    response = client.get("/documents/20/index-status")
    assert response.status_code == 404


def test_chunks_owned_200(setup):
    session = TestingSessionLocal()
    db_chunk = DocumentChunk(
        file_id=10,
        user_id=42,
        index_version=1,
        chunk_index=0,
        chunk_id="chunk-10-1-0",
        page_start=1,
        page_end=1,
        word_start=0,
        word_end=80,
        word_count=80,
        text_checksum="sha256-0",
        clean_text="Chunk zero clean text",
        extraction_version="1",
        cleaning_version="1",
        chunking_version="1",
        embedding_model="gemini-embedding-2",
        embedding_dimensions=768,
        source_key="uploads/file_10.pdf",
        original_filename="file_10.pdf",
    )
    session.add(db_chunk)
    session.commit()
    session.close()

    with patch(
        "app.apis.routes.rag_document_routes.get_index_status",
        return_value={
            "file_id": 10,
            "filename": "file_10.pdf",
            "indexing_status": IndexingStatus.INDEXED.value,
            "active_index_version": 1,
            "corpus_revision": 0,
            "progress": 1.0,
            "chunk_count": 1,
            "indexed_chunk_count": 1,
            "rag_error_code": None,
            "rag_error_message": None,
        },
    ):
        response = client.get("/documents/10/chunks")
        assert response.status_code == 200
        data = response.json()
        assert data["file_id"] == 10
        assert data["index_version"] == 1
        assert data["total"] == 1
        assert data["chunks"][0]["chunk_id"] == "chunk-10-1-0"
        assert data["chunks"][0]["clean_text"] == "Chunk zero clean text"


def test_chunks_explicit_index_version(setup):
    response = client.get("/documents/10/chunks?index_version=2")
    assert response.status_code == 200
    assert response.json()["index_version"] == 2
    assert response.json()["total"] == 0


def test_chunks_foreign_404(setup):
    response = client.get("/documents/20/chunks")
    assert response.status_code == 404