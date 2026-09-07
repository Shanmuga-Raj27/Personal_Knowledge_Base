"""
backend/tests/unit/services/rag/test_inspection.py

Unit tests for Phase 6 inspection service:
- get_index_status: owned/foreign files, progress mapping per lifecycle
- get_chunks: tenant-scoped, version-scoped, ordered, default-to-active-version,
  empty-chunk handling
"""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.database.db_models import DocumentChunk, FileMetadata
from app.schemas.enums import FileStatus, IndexingStatus
from app.services.rag.inspection import _progress_for, get_chunks, get_index_status

SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"
engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture
def db_session():
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)


def _make_file(
    db: Session,
    fileid: int,
    userid: int = 1,
    indexing_status: str = IndexingStatus.INDEXED.value,
    active_index_version: int = 1,
    chunk_count: int = 2,
    indexed_chunk_count: int = 2,
    filename: str = "report.pdf",
) -> FileMetadata:
    file = FileMetadata(
        fileid=fileid,
        s3_key=f"uploads/file_{fileid}.pdf",
        filename=filename,
        content_type="application/pdf",
        size_bytes=1024,
        status=FileStatus.ACTIVE.value,
        userid=userid,
        active_index_version=active_index_version,
        corpus_revision=0,
        indexing_status=indexing_status,
        index_version=1,
        chunk_count=chunk_count,
        indexed_chunk_count=indexed_chunk_count,
    )
    db.add(file)
    db.commit()
    db.refresh(file)
    return file


def _make_chunk(
    db: Session,
    file_id: int,
    user_id: int,
    index_version: int,
    chunk_index: int,
    chunk_id: str | None = None,
) -> DocumentChunk:
    chunk = DocumentChunk(
        file_id=file_id,
        user_id=user_id,
        index_version=index_version,
        chunk_index=chunk_index,
        chunk_id=chunk_id or f"chunk-{file_id}-{index_version}-{chunk_index}",
        page_start=chunk_index + 1,
        page_end=chunk_index + 1,
        word_start=chunk_index * 100,
        word_end=chunk_index * 100 + 80,
        word_count=80,
        text_checksum=f"sha256-{chunk_index}",
        clean_text=f"Clean text for chunk {chunk_index}",
        extraction_version="1",
        cleaning_version="1",
        chunking_version="1",
        embedding_model="gemini-embedding-2",
        embedding_dimensions=768,
        source_key=f"uploads/file_{file_id}.pdf",
        original_filename="report.pdf",
    )
    db.add(chunk)
    db.commit()
    return chunk


class TestGetIndexStatus:
    def test_owned_file_returns_status(self, db_session):
        _make_file(db_session, fileid=10, userid=1)
        result = get_index_status(db_session, 1, 10)
        assert result is not None
        assert result["file_id"] == 10
        assert result["filename"] == "report.pdf"
        assert result["indexing_status"] == IndexingStatus.INDEXED.value
        assert result["active_index_version"] == 1
        assert result["chunk_count"] == 2
        assert result["indexed_chunk_count"] == 2

    def test_foreign_file_returns_none(self, db_session):
        _make_file(db_session, fileid=10, userid=2)
        assert get_index_status(db_session, 1, 10) is None

    def test_absent_file_returns_none(self, db_session):
        assert get_index_status(db_session, 1, 999) is None

    def test_progress_maps_lifecycle(self, db_session):
        for fileid, (status, expected) in enumerate(
            [
                (IndexingStatus.PENDING.value, 0.0),
                (IndexingStatus.EXTRACTING.value, 0.1),
                (IndexingStatus.CHUNKED.value, 0.35),
                (IndexingStatus.EMBEDDING.value, 0.6),
                (IndexingStatus.INDEXING.value, 0.85),
                (IndexingStatus.INDEXED.value, 1.0),
            ],
            start=100,
        ):
            _make_file(db_session, fileid=fileid, userid=1, indexing_status=status)
            result = get_index_status(db_session, 1, fileid)
            assert result["indexing_status"] == status
            assert result["progress"] == expected

    def test_failed_status_falls_back_to_zero(self, db_session):
        _make_file(
            db_session,
            fileid=10,
            userid=1,
            indexing_status=IndexingStatus.FAILED_RETRYABLE.value,
        )
        result = get_index_status(db_session, 1, 10)
        assert result["progress"] == 0.0

    def test_error_fields_present(self, db_session):
        fm = _make_file(
            db_session,
            fileid=10,
            userid=1,
            indexing_status=IndexingStatus.FAILED_RETRYABLE.value,
        )
        fm.rag_error_code = "QDRANT_UPSERT_FAILED"
        fm.rag_error_message = "Upsert failed 2/3 chunks"
        db_session.commit()
        result = get_index_status(db_session, 1, 10)
        assert result["rag_error_code"] == "QDRANT_UPSERT_FAILED"
        assert result["rag_error_message"] == "Upsert failed 2/3 chunks"


class TestProgressFor:
    def test_unknown_status_zero(self):
        assert _progress_for("UNKNOWN") == 0.0

    def test_known_status_values(self):
        assert _progress_for("PENDING") == 0.0
        assert _progress_for("EXTRACTING") == 0.1
        assert _progress_for("CHUNKED") == 0.35
        assert _progress_for("EMBEDDING") == 0.6
        assert _progress_for("INDEXING") == 0.85
        assert _progress_for("INDEXED") == 1.0


class TestGetChunks:
    def test_owned_file_returns_chunks_in_order(self, db_session):
        _make_file(db_session, fileid=10, userid=1)
        _make_chunk(db_session, file_id=10, user_id=1, index_version=1, chunk_index=0)
        _make_chunk(db_session, file_id=10, user_id=1, index_version=1, chunk_index=1)
        result = get_chunks(db_session, 1, 10)
        assert result is not None
        assert len(result) == 2
        assert [c["chunk_index"] for c in result] == [0, 1]
        assert result[0]["page_start"] == 1
        assert result[0]["word_count"] == 80
        assert "Clean text" in result[0]["clean_text"]

    def test_foreign_file_returns_none(self, db_session):
        _make_file(db_session, fileid=10, userid=2)
        _make_chunk(db_session, file_id=10, user_id=2, index_version=1, chunk_index=0)
        assert get_chunks(db_session, 1, 10) is None

    def test_explicit_index_version_scopes(self, db_session):
        _make_file(db_session, fileid=10, userid=1, active_index_version=2)
        _make_chunk(db_session, file_id=10, user_id=1, index_version=1, chunk_index=0)
        _make_chunk(db_session, file_id=10, user_id=1, index_version=2, chunk_index=0)
        result = get_chunks(db_session, 1, 10, index_version=1)
        assert len(result) == 1
        assert result[0]["index_version"] == 1

    def test_defaults_to_active_index_version(self, db_session):
        _make_file(db_session, fileid=10, userid=1, active_index_version=2)
        _make_chunk(db_session, file_id=10, user_id=1, index_version=1, chunk_index=0)
        _make_chunk(db_session, file_id=10, user_id=1, index_version=2, chunk_index=0)
        result = get_chunks(db_session, 1, 10)
        assert len(result) == 1
        assert result[0]["index_version"] == 2

    def test_empty_chunk_list_returns_empty_list(self, db_session):
        _make_file(db_session, fileid=10, userid=1, chunk_count=0, indexed_chunk_count=0)
        result = get_chunks(db_session, 1, 10)
        assert result == []

    def test_chunks_are_user_scoped(self, db_session):
        _make_file(db_session, fileid=10, userid=1)
        _make_chunk(db_session, file_id=10, user_id=1, index_version=1, chunk_index=0)
        _make_file(db_session, fileid=20, userid=2)
        _make_chunk(
            db_session,
            file_id=20,
            user_id=2,
            index_version=1,
            chunk_index=0,
            chunk_id="chunk-20-1-0",
        )
        result = get_chunks(db_session, 1, 10)
        assert len(result) == 1
        assert result[0]["chunk_index"] == 0
        assert get_chunks(db_session, 1, 20) is None