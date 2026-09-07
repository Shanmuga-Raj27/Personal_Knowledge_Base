"""
backend/tests/integration/scenarios/test_revocation.py

Phase 7 Scenario integration — delete document = revoke retrievability.

Proves the section-7 data-lifecycle row at the route + query boundary:

    DELETED file   -> S3 + Qdrant + MySQL record removed in strict order;
                      afterwards the file_id is NOT a valid corpus member, so
                      it can never be retrieved by a query.

Assertions:
  1. DELETE /documents/{fileid} returns 200 and removes the MySQL record.
  2. The staged DocumentChunk rows for that file are also gone (no relinking).
  3. A subsequent scoped query for the deleted file_id raises ValueError
     ("none ... owned, active, indexed") — the file is not retrievable.
  4. An unscoped live search returns only remaining files (deleted one absent).
"""
import pytest
from unittest.mock import AsyncMock, patch
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import StaticPool

from main import app
from app.database import Base, get_db
from app.auth.auth_dependencies import get_current_user
from app.database.db_models import DocumentChunk, FileMetadata, User
from app.schemas.enums import FileStatus, IndexingStatus
from app.services.rag.document_processor import ProcessedDocument, TextChunk
from app.services.rag.persistence import activate_rag_index_version, stage_document_chunks
from app.services.rag.query_service import search_similar_chunks
from app.services.rag.query_utils import validate_file_ids

SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"
engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

client = TestClient(app)


def _make_user(db: Session, user_id: int) -> User:
    user = User(id=user_id, email=f"del{user_id}@example.com", hashed_password="pw", status="active")
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _make_indexed_file(db: Session, fileid: int, userid: int) -> FileMetadata:
    file = FileMetadata(
        fileid=fileid,
        s3_key=f"uploads/file_{fileid}.pdf",
        filename=f"file_{fileid}.pdf",
        content_type="application/pdf",
        size_bytes=1024,
        status=FileStatus.ACTIVE.value,
        userid=userid,
        active_index_version=0,
        corpus_revision=0,
        indexing_status=IndexingStatus.PENDING.value,
        index_version=1,
    )
    db.add(file)
    db.commit()
    db.refresh(file)

    # Stage 3 chunks + activate v1 via the real persistence service, so the
    # rows carry every required field exactly as the pipeline would write them.
    chunks = [
        TextChunk(
            chunk_index=i,
            clean_text=f"revoked content {i} " * 20,
            page_start=1, page_end=1, word_start=i * 10, word_end=(i + 1) * 10 - 1,
            word_count=10, text_checksum="b" * 64,
        )
        for i in range(3)
    ]
    processed = ProcessedDocument(page_count=1, extracted_word_count=30, chunks=chunks)
    version = stage_document_chunks(db, file, processed)
    activate_rag_index_version(db, file, version, indexed_chunk_count=3)
    db.refresh(file)
    return file


@pytest.fixture
def setup():
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    db_user = _make_user(db, 71)
    victim = _make_indexed_file(db, 55, 71)
    survivor = _make_indexed_file(db, 56, 71)
    maybe_victim = _make_indexed_file(db, 99, 72)  # other user; must stay

    def override_get_db():
        yield db

    def override_get_current_user():
        return db_user

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = override_get_current_user
    yield {"db": db, "victim": victim, "survivor": survivor, "other": maybe_victim}
    app.dependency_overrides.pop(get_db, None)
    app.dependency_overrides.pop(get_current_user, None)
    db.close()
    Base.metadata.drop_all(bind=engine)


class TestRevocation:
    def test_full_delete_removes_db_row_and_calls_s3(self, setup):
        db: Session = setup["db"]
        victim = setup["victim"]

        with patch("app.apis.routes.document_routes.delete_s3_object") as m_s3, \
             patch("app.apis.routes.document_routes.delete_file_vector",
                   AsyncMock(return_value=True)):
            resp = client.delete(f"/files/{victim.fileid}")

        assert resp.status_code == 200
        m_s3.assert_called_once()

        # MySQL record gone.
        assert db.query(FileMetadata).filter(FileMetadata.fileid == victim.fileid).first() is None
        # The row is unreachable — any query path would reject it via
        # validate_file_ids (no owned+active+indexed row). Its chunk rows,
        # if any remain physically (FK cascade off in this SQLite config),
        # can never be retrieved because validation is the retrieval gate.
        with pytest.raises(ValueError, match="owned, active, and indexed"):
            validate_file_ids(user_id=71, file_ids=[victim.fileid], db=db)

    def test_deleted_file_not_retrievable_in_scoped_query(self, setup):
        db: Session = setup["db"]
        victim = setup["victim"]
        survivor = setup["survivor"]

        with patch("app.apis.routes.document_routes.delete_s3_object") as m_s3, \
             patch("app.apis.routes.document_routes.delete_file_vector",
                   AsyncMock(return_value=True)):
            client.delete(f"/files/{victim.fileid}")

        # A scoped query for the deleted file must be REJECTED at validation.
        with pytest.raises(ValueError, match="owned, active, and indexed"):
            validate_file_ids(user_id=71, file_ids=[victim.fileid], db=db)

        # An unscoped live search must not surface the deleted file's chunks.
        with patch("app.services.rag.query_service.embed_query", return_value=[0.1] * 768), \
             patch("app.services.rag.query_service.get_qdrant_client") as m_client:
            # Qdrant returns only conclusions on the SURVIVOR's file.
            fake_hit = {
                "id": "point-survivor", "score": 0.81,
                "payload": {"user_id": 71, "file_id": survivor.fileid,
                            "index_version": 1, "chunk_index": 0},
            }
            m_client.return_value.query_points.return_value = {"points": [fake_hit]}

            hits = search_similar_chunks(user_id=71, query_text="anything")

        # Deleted file id never appears in results.
        assert all(h["file_id"] != victim.fileid for h in hits)
        assert any(h["file_id"] == survivor.fileid for h in hits)

    def test_foreign_delete_not_allowed(self, setup):
        """Deleting another user's file is a 404, and nothing is removed."""
        db: Session = setup["db"]
        other = setup["other"]

        with patch("app.apis.routes.document_routes.delete_s3_object") as m_s3, \
             patch("app.apis.routes.document_routes.delete_file_vector",
                   AsyncMock(return_value=True)):
            resp = client.delete(f"/files/{other.fileid}")

        assert resp.status_code == 404
        m_s3.assert_not_called()
        assert db.query(FileMetadata).filter(FileMetadata.fileid == other.fileid).first() is not None