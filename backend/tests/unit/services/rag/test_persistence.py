"""
backend/tests/unit/services/rag/test_persistence.py

Unit tests for RAG persistence service.
"""
import pytest
from datetime import datetime, timezone
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.database.db_models import DocumentChunk, FileMetadata, UserCorpusState, User
from app.schemas.enums import FileStatus, IndexingStatus
from app.services.rag.document_processor import (
    NoExtractableTextError,
    PdfExtractionError,
    ProcessedDocument,
    TextChunk,
)
from app.services.rag.persistence import (
    activate_rag_index_version,
    mark_rag_failure,
    map_rag_exception,
    next_rag_index_version,
    stage_document_chunks,
    ERROR_OBJECT_NOT_FOUND,
    ERROR_PDF_TOO_LARGE,
    ERROR_PDF_READ_FAILED,
    ERROR_PDF_PARSE_FAILED,
    ERROR_NO_EXTRACTABLE_TEXT,
    ERROR_CHUNKING_FAILED,
)
from app.services.rag.ids import build_chunk_id
from botocore.exceptions import BotoCoreError, ClientError


# In-memory SQLite engine for unit tests
SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"
engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture
def db_session():
    """Create a fresh database session for each test."""
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)


def _make_file_metadata(fileid=1, userid=1, active_index_version=0) -> FileMetadata:
    """Create a minimal FileMetadata instance for testing."""
    file = FileMetadata(
        fileid=fileid,
        s3_key="uploads/test.pdf",
        filename="test.pdf",
        content_type="application/pdf",
        status=FileStatus.ACTIVE.value,
        userid=userid,
        active_index_version=active_index_version,
        corpus_revision=0,
        indexing_status=IndexingStatus.PENDING.value,
        index_version=1,
    )
    return file


def _make_processed_document(chunk_count=3, page_count=2, word_count=2400) -> ProcessedDocument:
    """Create a ProcessedDocument with test chunks."""
    chunks = []
    for i in range(chunk_count):
        chunks.append(
            TextChunk(
                chunk_index=i,
                clean_text=f"chunk {i} text " * 100,
                page_start=1 if i < 2 else 2,
                page_end=2,
                word_start=i * 800,
                word_end=(i + 1) * 800 - 1,
                word_count=800,
                text_checksum="a" * 64,
            )
        )
    return ProcessedDocument(
        page_count=page_count,
        extracted_word_count=word_count,
        chunks=chunks,
    )


class TestNextRagIndexVersion:
    def test_returns_one_for_zero_active_version(self):
        file = _make_file_metadata(active_index_version=0)
        assert next_rag_index_version(file) == 1

    def test_returns_incremented_version(self):
        file = _make_file_metadata(active_index_version=5)
        assert next_rag_index_version(file) == 6

    def test_handles_none_active_version(self):
        file = _make_file_metadata(active_index_version=None)
        assert next_rag_index_version(file) == 1


class TestMapRagException:
    def test_file_not_found(self):
        exc = FileNotFoundError("not found")
        code, msg, retryable = map_rag_exception(exc)
        assert code == ERROR_OBJECT_NOT_FOUND
        assert retryable is False

    def test_pdf_too_large(self):
        exc = ValueError("Object is too large: 60000000 bytes")
        code, msg, retryable = map_rag_exception(exc)
        assert code == ERROR_PDF_TOO_LARGE
        assert retryable is False

    def test_pdf_extraction_error(self):
        exc = PdfExtractionError("parse failed")
        code, msg, retryable = map_rag_exception(exc)
        assert code == ERROR_PDF_PARSE_FAILED
        assert retryable is False

    def test_no_extractable_text(self):
        exc = NoExtractableTextError("scanned pdf")
        code, msg, retryable = map_rag_exception(exc)
        assert code == ERROR_NO_EXTRACTABLE_TEXT
        assert retryable is False

    def test_boto_core_error(self):
        exc = BotoCoreError()
        code, msg, retryable = map_rag_exception(exc)
        assert code == ERROR_PDF_READ_FAILED
        assert retryable is True

    def test_client_error(self):
        exc = ClientError({"Error": {}, "ResponseMetadata": {}}, "GetObject")
        code, msg, retryable = map_rag_exception(exc)
        assert code == ERROR_PDF_READ_FAILED
        assert retryable is True

    def test_unknown_exception(self):
        exc = RuntimeError("something else")
        code, msg, retryable = map_rag_exception(exc)
        assert code == ERROR_CHUNKING_FAILED
        assert retryable is False


class TestMarkRagFailure:
    def test_retryable_sets_failed_retryable(self, db_session: Session):
        file = _make_file_metadata()
        db_session.add(file)
        db_session.commit()

        mark_rag_failure(db_session, file, "TEST_CODE", "test message", retryable=True)
        db_session.refresh(file)

        assert file.indexing_status == IndexingStatus.FAILED_RETRYABLE.value
        assert file.rag_error_code == "TEST_CODE"
        assert file.rag_error_message == "test message"

    def test_terminal_sets_failed_terminal(self, db_session: Session):
        file = _make_file_metadata()
        db_session.add(file)
        db_session.commit()

        mark_rag_failure(db_session, file, "TEST_CODE", "test message", retryable=False)
        db_session.refresh(file)

        assert file.indexing_status == IndexingStatus.FAILED_TERMINAL.value

    def test_truncates_code_to_64(self, db_session: Session):
        file = _make_file_metadata()
        db_session.add(file)
        db_session.commit()

        long_code = "X" * 100
        mark_rag_failure(db_session, file, long_code, "msg", retryable=False)
        db_session.refresh(file)

        assert len(file.rag_error_code) == 64

    def test_truncates_message_to_500(self, db_session: Session):
        file = _make_file_metadata()
        db_session.add(file)
        db_session.commit()

        long_msg = "X" * 1000
        mark_rag_failure(db_session, file, "CODE", long_msg, retryable=False)
        db_session.refresh(file)

        assert len(file.rag_error_message) == 500


class TestStageDocumentChunks:
    def test_inserts_all_chunks(self, db_session: Session):
        file = _make_file_metadata()
        db_session.add(file)
        db_session.commit()

        processed = _make_processed_document(chunk_count=3)
        version = stage_document_chunks(db_session, file, processed)

        assert version == 1
        db_session.refresh(file)
        assert file.chunk_count == 3
        assert file.indexing_status == IndexingStatus.CHUNKED.value

        chunks = db_session.query(DocumentChunk).filter(
            DocumentChunk.file_id == file.fileid
        ).all()
        assert len(chunks) == 3

    def test_sets_correct_fields_on_chunks(self, db_session: Session):
        file = _make_file_metadata(fileid=42, userid=7)
        db_session.add(file)
        db_session.commit()

        processed = _make_processed_document(chunk_count=1)
        stage_document_chunks(db_session, file, processed)

        chunk = db_session.query(DocumentChunk).first()
        assert chunk.file_id == 42
        assert chunk.user_id == 7
        assert chunk.index_version == 1
        assert chunk.chunk_index == 0
        assert chunk.page_start == 1
        assert chunk.page_end == 2
        assert chunk.word_start == 0
        assert chunk.word_end == 799
        assert chunk.word_count == 800
        assert chunk.text_checksum == "a" * 64
        assert chunk.clean_text.startswith("chunk 0 text")
        assert chunk.source_key == "uploads/test.pdf"
        assert chunk.original_filename == "test.pdf"

    def test_sets_version_metadata_on_file(self, db_session: Session):
        file = _make_file_metadata()
        db_session.add(file)
        db_session.commit()

        processed = _make_processed_document(chunk_count=2)
        stage_document_chunks(db_session, file, processed)
        db_session.refresh(file)

        assert file.extraction_version == "pdf-text-v1"
        assert file.cleaning_version == "clean-v1"
        assert file.chunking_version == "words-800-overlap-100-v1"
        assert file.embedding_model == "gemini-embedding-2"
        assert file.embedding_dimensions == 768

    def test_does_not_activate_version(self, db_session: Session):
        file = _make_file_metadata()
        db_session.add(file)
        db_session.commit()

        processed = _make_processed_document(chunk_count=1)
        stage_document_chunks(db_session, file, processed)
        db_session.refresh(file)

        assert file.active_index_version == 0  # unchanged

    def test_clears_error_fields(self, db_session: Session):
        file = _make_file_metadata()
        file.rag_error_code = "OLD_ERROR"
        file.rag_error_message = "old message"
        db_session.add(file)
        db_session.commit()

        processed = _make_processed_document(chunk_count=1)
        stage_document_chunks(db_session, file, processed)
        db_session.refresh(file)

        assert file.rag_error_code is None
        assert file.rag_error_message is None

    def test_retry_same_version_deletes_old_chunks(self, db_session: Session):
        file = _make_file_metadata()
        db_session.add(file)
        db_session.commit()

        processed = _make_processed_document(chunk_count=2)
        stage_document_chunks(db_session, file, processed)

        # Simulate retry with same version (by forcing version=1 again)
        processed2 = _make_processed_document(chunk_count=1)
        # Manually set active_index_version to 0 so next_rag_index_version returns 1 again
        file.active_index_version = 0
        db_session.commit()

        stage_document_chunks(db_session, file, processed2)

        chunks = db_session.query(DocumentChunk).filter(
            DocumentChunk.file_id == file.fileid,
            DocumentChunk.index_version == 1,
        ).all()
        assert len(chunks) == 1  # old chunks deleted, new ones inserted

    def test_returns_new_version(self, db_session: Session):
        file = _make_file_metadata(active_index_version=0)
        db_session.add(file)
        db_session.commit()

        processed = _make_processed_document(chunk_count=1)
        version = stage_document_chunks(db_session, file, processed)
        assert version == 1

        file.active_index_version = 1
        db_session.commit()

        processed2 = _make_processed_document(chunk_count=1)
        version2 = stage_document_chunks(db_session, file, processed2)
        assert version2 == 2


class TestActivateRagIndexVersion:
    def test_activates_valid_version(self, db_session: Session):
        file = _make_file_metadata(active_index_version=0)
        db_session.add(file)
        db_session.commit()

        processed = _make_processed_document(chunk_count=3)
        stage_document_chunks(db_session, file, processed)

        # Get or create UserCorpusState
        state = UserCorpusState(user_id=file.userid, corpus_revision=5)
        db_session.add(state)
        db_session.commit()

        activate_rag_index_version(db_session, file, index_version=1, indexed_chunk_count=3)
        db_session.refresh(file)
        db_session.refresh(state)

        assert file.active_index_version == 1
        assert file.indexing_status == IndexingStatus.INDEXED.value
        assert file.indexed_chunk_count == 3
        assert file.corpus_revision == 6
        assert state.corpus_revision == 6

    def test_creates_user_corpus_state_if_missing(self, db_session: Session):
        file = _make_file_metadata(userid=99, active_index_version=0)
        db_session.add(file)
        db_session.commit()

        processed = _make_processed_document(chunk_count=1)
        stage_document_chunks(db_session, file, processed)

        # No UserCorpusState exists for userid=99
        activate_rag_index_version(db_session, file, index_version=1, indexed_chunk_count=1)
        db_session.refresh(file)

        state = db_session.get(UserCorpusState, 99)
        assert state is not None
        assert state.corpus_revision == 1
        assert file.corpus_revision == 1

    def test_fails_on_zero_chunks(self, db_session: Session):
        file = _make_file_metadata(active_index_version=0)
        db_session.add(file)
        db_session.commit()

        # No chunks staged
        with pytest.raises(ValueError, match="zero chunks"):
            activate_rag_index_version(db_session, file, index_version=1, indexed_chunk_count=0)

    def test_fails_on_count_mismatch(self, db_session: Session):
        file = _make_file_metadata(active_index_version=0)
        db_session.add(file)
        db_session.commit()

        processed = _make_processed_document(chunk_count=3)
        stage_document_chunks(db_session, file, processed)

        with pytest.raises(ValueError, match="every chunk is indexed"):
            activate_rag_index_version(db_session, file, index_version=1, indexed_chunk_count=2)

    def test_fails_on_wrong_version(self, db_session: Session):
        file = _make_file_metadata(active_index_version=0)
        db_session.add(file)
        db_session.commit()

        processed = _make_processed_document(chunk_count=3)
        stage_document_chunks(db_session, file, processed)

        with pytest.raises(ValueError, match="zero chunks"):
            activate_rag_index_version(db_session, file, index_version=999, indexed_chunk_count=0)

    def test_sets_indexing_completed_at(self, db_session: Session):
        file = _make_file_metadata(active_index_version=0)
        db_session.add(file)
        db_session.commit()

        processed = _make_processed_document(chunk_count=1)
        stage_document_chunks(db_session, file, processed)

        before = datetime.now(timezone.utc).replace(tzinfo=None)
        activate_rag_index_version(db_session, file, index_version=1, indexed_chunk_count=1)
        after = datetime.now(timezone.utc).replace(tzinfo=None)

        db_session.refresh(file)
        assert file.indexing_completed_at is not None
        assert before <= file.indexing_completed_at <= after


class TestBuildChunkIdIntegration:
    def test_chunk_id_matches_deterministic_generation(self, db_session: Session):
        file = _make_file_metadata(fileid=100, userid=1)
        db_session.add(file)
        db_session.commit()

        processed = _make_processed_document(chunk_count=2)
        stage_document_chunks(db_session, file, processed)

        chunks = db_session.query(DocumentChunk).order_by(DocumentChunk.chunk_index).all()
        assert chunks[0].chunk_id == str(build_chunk_id(100, 1, 0))
        assert chunks[1].chunk_id == str(build_chunk_id(100, 1, 1))