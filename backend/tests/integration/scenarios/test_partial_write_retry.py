"""
backend/tests/integration/scenarios/test_partial_write_retry.py

Phase 7 Scenario integration — partial-write retry idempotency.

Proves the section-7 error-handling row:
    Merge/upsert mid-batch fail -> retry with SAME UUIDv5 point ids
    (idempotent, overwrite not duplicate), and cutover is REFUSED until
    verification passes.

Shapes asserted:
  1. On a retry, upsert_document_chunks re-sends identical deterministic
     point IDs for the same (file, version, chunk_index) — so Qdrant
     overwrites instead of duplicating.
  2. verify_and_cutover returns False (no activation) when the Qdrant count
     does not match the MySQL expected count.
"""
import pytest
from unittest.mock import MagicMock, patch
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.database.db_models import DocumentChunk, FileMetadata, User, UserCorpusState
from app.schemas.enums import FileStatus, IndexingStatus
from app.services.rag.document_processor import ProcessedDocument, TextChunk
from app.services.rag.ids import build_chunk_id
from app.services.rag.persistence import stage_document_chunks
from app.services.rag.qdrant_service import upsert_document_chunks, fetch_chunks_for_version

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


def _make_file(fileid=10, userid=1):
    return FileMetadata(
        fileid=fileid, s3_key="uploads/10.pdf", filename="doc10.pdf",
        content_type="application/pdf", status=FileStatus.ACTIVE.value,
        userid=userid, active_index_version=0, corpus_revision=0,
        indexing_status=IndexingStatus.PENDING.value, index_version=1,
    )


def _make_processed(chunk_count=4):
    chunks = [
        TextChunk(
            chunk_index=i,
            clean_text=f"chunk {i} content " * 30,
            page_start=1, page_end=1, word_start=i * 100, word_end=(i + 1) * 100 - 1,
            word_count=100, text_checksum="a" * 64,
        )
        for i in range(chunk_count)
    ]
    return ProcessedDocument(page_count=1, extracted_word_count=chunk_count * 100, chunks=chunks)


def _mock_vector():
    return [0.1] * 768


class TestPartialWriteRetry:
    def test_retry_reuses_identical_deterministic_point_ids(self, db):
        user = User(id=1, email="a@test.com", hashed_password="x")
        db.add(user)
        db.commit()
        file = _make_file()
        db.add(file)
        db.commit()

        processed = _make_processed(4)
        version = stage_document_chunks(db, file, processed)
        all_chunks = fetch_chunks_for_version(db, file.fileid, version)

        # Every upsert attempt must send the SAME deterministic point IDs, so a
        # retry after a mid-batch failure overwrites instead of duplicating.
        attempts: list[list[str]] = []
        call_n = {"n": 0}

        def retry_then_succeed(points):
            attempts.append([str(p.id) for p in points])
            call_n["n"] += 1
            if call_n["n"] == 1:
                err = Exception("server 500")
                err.status_code = 500  # retryable (type: ignore[attr-defined])
                raise err

        with patch("app.services.rag.qdrant_service._qdrant_upsert_batch",
                   side_effect=retry_then_succeed), \
             patch("app.services.rag.qdrant_service.embed_document", return_value=_mock_vector()), \
             patch("app.services.rag.qdrant_service.time.sleep", return_value=None), \
             patch("app.services.rag.qdrant_service.settings.RAG_MAX_RETRIES", 1):
            result = upsert_document_chunks(
                user_id=1, file_id=file.fileid, index_version=version,
                chunks=all_chunks, batch_size=100,
            )

        # Internal retry fired, re-sending identical deterministic IDs.
        assert len(attempts) == 2
        expected = [str(build_chunk_id(10, version, i)) for i in range(4)]
        assert attempts[0] == expected
        assert attempts[1] == expected
        assert result["upserted"] == 4
        assert result["failed"] == 0

    def test_cutover_refused_until_verification_passes(self, db):
        """If Qdrant count does NOT match MySQL chunk_count, activation is
        refused (active_index_version unchanged, lifecycle stays CHUNKED)."""
        from app.services.rag.indexing_service import verify_and_cutover

        user = User(id=2, email="b@test.com", hashed_password="x")
        db.add(user)
        db.commit()
        file = _make_file(userid=2)
        db.add(file)
        db.commit()
        processed = _make_processed(4)
        version = stage_document_chunks(db, file, processed)

        upsert_result = {"upserted": 3, "failed": 1, "total_chunks": 4}

        # First: upsert reports a failure -> must NOT cut over.
        with patch("app.services.rag.indexing_service.verify_qdrant_index", return_value=True):
            with patch("app.services.rag.indexing_service.activate_rag_index_version") as m_act:
                ok = verify_and_cutover(MagicMock(), file, version, upsert_result)
                assert ok is False
                m_act.assert_not_called()

        # Second: upsert "succeeds" but Qdrant count is short -> refused.
        ok_result = {"upserted": 4, "failed": 0, "total_chunks": 4}
        with patch("app.services.rag.indexing_service.verify_qdrant_index", return_value=False):
            with patch("app.services.rag.indexing_service.activate_rag_index_version") as m_act2:
                ok = verify_and_cutover(MagicMock(), file, version, ok_result)
                assert ok is False
                m_act2.assert_not_called()

        # Third: upsert ok AND Qdrant count matches -> cutover proceeds.
        from app.services.rag.persistence import activate_rag_index_version as real_activate

        with patch("app.services.rag.indexing_service.verify_qdrant_index", return_value=True):
            with patch("app.services.rag.indexing_service.cleanup_old_version_vectors"):
                with patch("app.services.rag.indexing_service.activate_rag_index_version",
                           side_effect=real_activate):
                    ok = verify_and_cutover(db, file, version, ok_result)
                    assert ok is True
                    db.refresh(file)
                    assert file.active_index_version == version
                    assert file.indexing_status == IndexingStatus.INDEXED.value
