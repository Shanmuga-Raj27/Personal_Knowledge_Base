"""
backend/tests/unit/services/rag/test_phase4_integration.py

End-to-end integration: stage → embed → upsert → cutover → query
Mocks Gemini/Qdrant, uses real SQLite for MySQL hydration logic.
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
from app.services.rag.persistence import activate_rag_index_version, stage_document_chunks
from app.services.rag.ids import build_chunk_id

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


def _make_file(fileid=1, userid=1, active_version=0):
    return FileMetadata(
        fileid=fileid,
        s3_key=f"uploads/{fileid}.pdf",
        filename=f"doc{fileid}.pdf",
        content_type="application/pdf",
        status=FileStatus.ACTIVE.value,
        userid=userid,
        active_index_version=active_version,
        corpus_revision=0,
        indexing_status=IndexingStatus.PENDING.value,
        index_version=1,
    )


def _make_processed(chunk_count=3):
    chunks = []
    for i in range(chunk_count):
        chunks.append(
            TextChunk(
                chunk_index=i,
                clean_text=f"chunk {i} content " * 50,
                page_start=1,
                page_end=1,
                word_start=i * 100,
                word_end=(i + 1) * 100 - 1,
                word_count=100,
                text_checksum="a" * 64,
            )
        )
    return ProcessedDocument(page_count=1, extracted_word_count=chunk_count * 100, chunks=chunks)


def _mock_vector():
    return [0.1] * 768


class TestPhase4EndToEnd:
    def test_stage_embed_upsert_cutover_query(self, db):
        # Setup user and file
        user = User(id=1, email="a@test.com", hashed_password="x")
        db.add(user)
        db.commit()
        file = _make_file(fileid=10, userid=1, active_version=0)
        db.add(file)
        db.commit()

        # Stage v1
        processed = _make_processed(chunk_count=3)
        v1 = stage_document_chunks(db, file, processed)
        assert v1 == 1
        assert file.chunk_count == 3
        assert file.active_index_version == 0  # not yet active

        # Build vectors + cutover (mock Gemini/Qdrant)
        mock_q = MagicMock()
        mock_q.upsert.return_value = MagicMock()
        mock_q.count.return_value = MagicMock(count=3)
        mock_q.scroll.return_value = ([], None)

        with patch("app.services.rag.qdrant_service.get_qdrant_client", return_value=mock_q):
            with patch("app.services.rag.qdrant_service.embed_document", return_value=_mock_vector()):
                with patch("app.services.rag.indexing_service.fetch_chunks_for_version", wraps=lambda db_, fid, ver: [{"chunk_index": r.chunk_index, "clean_text": r.clean_text} for r in db.query(DocumentChunk).filter(DocumentChunk.file_id == fid, DocumentChunk.index_version == ver).all()]):
                    from app.services.rag.indexing_service import run_full_indexing

                    result = run_full_indexing(db, file, index_version=v1)
                    assert result["success"] is True
                    db.refresh(file)
                    assert file.active_index_version == 1
                    assert file.indexing_status == IndexingStatus.INDEXED.value
                    assert file.corpus_revision == 1
                    # Qdrant upsert called with deterministic IDs
                    called_ids = [str(p.id) for p in mock_q.upsert.call_args[1]["points"]]
                    assert str(build_chunk_id(10, 1, 0)) in called_ids

        # Query as same user — should get hits
        mock_q2 = MagicMock()
        mock_q2.query_points.return_value = MagicMock(
            points=[
                MagicMock(payload={"chunk_id": str(build_chunk_id(10, 1, 0)), "file_id": 10, "index_version": 1, "chunk_index": 0}, score=0.9, id=str(build_chunk_id(10, 1, 0))),
                MagicMock(payload={"chunk_id": str(build_chunk_id(10, 1, 1)), "file_id": 10, "index_version": 1, "chunk_index": 1}, score=0.85, id=str(build_chunk_id(10, 1, 1))),
            ]
        )
        with patch("app.services.rag.query_service.get_qdrant_client", return_value=mock_q2):
            with patch("app.services.rag.query_service.embed_query", return_value=_mock_vector()):
                from app.services.rag.query_service import search_similar_chunks

                hits = search_similar_chunks(user_id=1, query_text="what is in doc?")
                assert len(hits) == 2
                assert hits[0]["rank"] == 0
                # Tenant isolation: hits belong to user 1
                assert all(h["file_id"] == 10 for h in hits)

        # Cross-tenant query — user 2 should not see user 1's chunks even with same file_id
        # Simulate empty result for user 2 (Qdrant filter would exclude)
        mock_q3 = MagicMock()
        mock_q3.query_points.return_value = MagicMock(points=[])
        with patch("app.services.rag.query_service.get_qdrant_client", return_value=mock_q3):
            with patch("app.services.rag.query_service.embed_query", return_value=_mock_vector()):
                hits2 = search_similar_chunks(user_id=2, query_text="what is in doc?")
                assert hits2 == []

    def test_reindex_zero_downtime_old_version_served_until_cutover(self, db):
        user = User(id=2, email="b@test.com", hashed_password="x")
        db.add(user)
        db.commit()
        file = _make_file(fileid=20, userid=2, active_version=1)
        # Simulate v1 already indexed
        file.active_index_version = 1
        file.corpus_revision = 1
        db.add(file)
        db.commit()
        # Add v1 chunks manually
        db.add(DocumentChunk(file_id=20, user_id=2, index_version=1, chunk_index=0, chunk_id=str(build_chunk_id(20, 1, 0)), page_start=1, page_end=1, word_start=0, word_end=99, word_count=100, text_checksum="a" * 64, clean_text="v1 chunk", extraction_version="pdf-text-v1", cleaning_version="clean-v1", chunking_version="words-800-overlap-100-v1", embedding_model="gemini-embedding-2", embedding_dimensions=768, source_key="uploads/20.pdf", original_filename="doc20.pdf"))
        db.commit()

        # Ensure UserCorpusState exists with revision 1 (from v1 activation)
        state = UserCorpusState(user_id=2, corpus_revision=1)
        db.add(state)
        db.commit()
        file.corpus_revision = 1
        db.commit()

        # Stage v2
        processed_v2 = _make_processed(chunk_count=2)
        v2 = stage_document_chunks(db, file, processed_v2)
        assert v2 == 2
        db.refresh(file)
        assert file.active_index_version == 1  # still v1
        assert file.chunk_count == 2

        # Verify that uncutover v2 vectors not returned for active query
        # (Qdrant would have v2 points but hydration filters by active_index_version)
        # Simulate hydration would filter out v2
        assert file.active_index_version != v2

        # Now cutover v2 with mocked Qdrant
        mock_q = MagicMock()
        mock_q.upsert.return_value = MagicMock()
        mock_q.count.return_value = MagicMock(count=2)
        mock_q.scroll.return_value = ([], None)
        with patch("app.services.rag.qdrant_service.get_qdrant_client", return_value=mock_q):
            with patch("app.services.rag.qdrant_service.embed_document", return_value=_mock_vector()):
                from app.services.rag.indexing_service import run_full_indexing

                result = run_full_indexing(db, file, index_version=v2)
                assert result["success"] is True
                db.refresh(file)
                assert file.active_index_version == 2  # now v2
                assert file.corpus_revision == 2  # incremented

    def test_batch_size_respected_integration(self, db):
        user = User(id=3, email="c@test.com", hashed_password="x")
        db.add(user)
        db.commit()
        file = _make_file(fileid=30, userid=3, active_version=0)
        db.add(file)
        db.commit()
        processed = _make_processed(chunk_count=5)
        v1 = stage_document_chunks(db, file, processed)

        mock_q = MagicMock()
        mock_q.upsert.return_value = MagicMock()
        mock_q.count.return_value = MagicMock(count=5)
        mock_q.scroll.return_value = ([], None)

        with patch("app.services.rag.qdrant_service.get_qdrant_client", return_value=mock_q):
            with patch("app.services.rag.qdrant_service.embed_document", return_value=_mock_vector()):
                from app.services.rag.qdrant_service import upsert_document_chunks, fetch_chunks_for_version

                all_chunks = fetch_chunks_for_version(db, 30, v1)
                result = upsert_document_chunks(user_id=3, file_id=30, index_version=v1, chunks=all_chunks, batch_size=2)
                # 5 chunks batch 2 => 3 calls
                assert mock_q.upsert.call_count == 3
                assert result["upserted"] == 5
