"""
backend/tests/unit/services/rag/test_qdrant_service.py

Phase 4 Qdrant upsert, retry, and collection guard tests
(RAG-phase-4.md:639-646)
"""
import pytest
from unittest.mock import MagicMock, patch

from app.services.rag.qdrant_service import (
    _batch_chunks,
    cleanup_old_version_vectors,
    ensure_collection,
    filter_pending_chunks,
    get_existing_chunk_indexes,
    upsert_document_chunks,
    upsert_with_resume,
    verify_qdrant_index,
)
from app.services.rag.ids import build_chunk_id


def _mock_vector():
    return [0.1] * 768


class TestBatchChunks:
    def test_yields_batches(self):
        chunks = list(range(10))
        batches = list(_batch_chunks(chunks, 3))
        assert batches == [[0, 1, 2], [3, 4, 5], [6, 7, 8], [9]]

    def test_exact_batch(self):
        batches = list(_batch_chunks([1, 2, 3, 4], 2))
        assert batches == [[1, 2], [3, 4]]


class TestUpsertDocumentChunks:
    def test_upsert_batch_with_deterministic_ids(self):
        mock_q = MagicMock()
        mock_q.upsert.return_value = MagicMock()
        with patch("app.services.rag.qdrant_service.get_qdrant_client", return_value=mock_q):
            with patch("app.services.rag.qdrant_service.embed_document", return_value=_mock_vector()):
                chunks = [
                    {"chunk_index": 0, "clean_text": "hello world"},
                    {"chunk_index": 1, "clean_text": "second chunk"},
                ]
                result = upsert_document_chunks(user_id=1, file_id=42, index_version=1, chunks=chunks, batch_size=64)
                assert result["upserted"] == 2
                assert result["failed"] == 0
                assert len(result["batch_progress"]) == 2
                # Deterministic IDs
                assert result["batch_progress"][0]["point_id"] == str(build_chunk_id(42, 1, 0))
                # Payload has only 4 fields
                payload = mock_q.upsert.call_args[1]["points"][0].payload
                assert set(payload.keys()) == {"user_id", "file_id", "index_version", "chunk_index"}
                assert "clean_text" not in str(payload)

    def test_idempotent_upsert_same_id_overwrites(self):
        mock_q = MagicMock()
        mock_q.upsert.return_value = MagicMock()
        with patch("app.services.rag.qdrant_service.get_qdrant_client", return_value=mock_q):
            with patch("app.services.rag.qdrant_service.embed_document", return_value=_mock_vector()):
                chunks = [{"chunk_index": 0, "clean_text": "text"}]
                r1 = upsert_document_chunks(user_id=1, file_id=1, index_version=1, chunks=chunks)
                r2 = upsert_document_chunks(user_id=1, file_id=1, index_version=1, chunks=chunks)
                assert r1["batch_progress"][0]["point_id"] == r2["batch_progress"][0]["point_id"]

    def test_respects_batch_size(self):
        mock_q = MagicMock()
        mock_q.upsert.return_value = MagicMock()
        with patch("app.services.rag.qdrant_service.get_qdrant_client", return_value=mock_q):
            with patch("app.services.rag.qdrant_service.embed_document", return_value=_mock_vector()):
                chunks = [{"chunk_index": i, "clean_text": f"chunk {i}"} for i in range(5)]
                result = upsert_document_chunks(user_id=1, file_id=1, index_version=1, chunks=chunks, batch_size=2)
                # 5 chunks with batch 2 -> 3 upsert calls
                assert mock_q.upsert.call_count == 3
                assert result["upserted"] == 5

    def test_batch_size_clamped_to_128(self):
        mock_q = MagicMock()
        mock_q.upsert.return_value = MagicMock()
        with patch("app.services.rag.qdrant_service.get_qdrant_client", return_value=mock_q):
            with patch("app.services.rag.qdrant_service.embed_document", return_value=_mock_vector()):
                chunks = [{"chunk_index": i, "clean_text": "x"} for i in range(2)]
                result = upsert_document_chunks(user_id=1, file_id=1, index_version=1, chunks=chunks, batch_size=999)
                assert result["upserted"] == 2  # clamped, not rejected

    def test_retry_on_429_with_jitter(self):
        mock_q = MagicMock()
        calls = []

        def flaky(*a, **kw):
            calls.append(1)
            if len(calls) == 1:
                e = Exception("429 Too Many Requests")
                e.status_code = 429
                raise e
            return MagicMock()

        mock_q.upsert.side_effect = flaky
        with patch("app.services.rag.qdrant_service.get_qdrant_client", return_value=mock_q):
            with patch("app.services.rag.qdrant_service.embed_document", return_value=_mock_vector()):
                with patch("app.services.rag.qdrant_service.time.sleep", return_value=None):
                    result = upsert_document_chunks(user_id=1, file_id=1, index_version=1, chunks=[{"chunk_index": 0, "clean_text": "hi"}])
                    assert result["upserted"] == 1
                    assert len(calls) == 2

    def test_non_retryable_fails_fast(self):
        mock_q = MagicMock()

        def fail(*a, **kw):
            raise RuntimeError("validation failed - dimension mismatch")

        mock_q.upsert.side_effect = fail
        with patch("app.services.rag.qdrant_service.get_qdrant_client", return_value=mock_q):
            with patch("app.services.rag.qdrant_service.embed_document", return_value=_mock_vector()):
                result = upsert_document_chunks(user_id=1, file_id=1, index_version=1, chunks=[{"chunk_index": 0, "clean_text": "hi"}])
                assert result["failed"] == 1
                assert result["upserted"] == 0

    def test_supports_textchunk_objects(self):
        from app.services.rag.schemas import TextChunk

        mock_q = MagicMock()
        mock_q.upsert.return_value = MagicMock()
        chunk = TextChunk(chunk_index=0, clean_text="hello", page_start=1, page_end=1, word_start=0, word_end=10, word_count=10, text_checksum="a" * 64)
        with patch("app.services.rag.qdrant_service.get_qdrant_client", return_value=mock_q):
            with patch("app.services.rag.qdrant_service.embed_document", return_value=_mock_vector()):
                result = upsert_document_chunks(user_id=1, file_id=1, index_version=1, chunks=[chunk])
                assert result["upserted"] == 1


class TestEnsureCollection:
    def test_creates_when_missing(self):
        mock_q = MagicMock()
        mock_q.collection_exists.return_value = False
        mock_q.create_collection.return_value = None
        mock_q.create_payload_index.return_value = None
        with patch("app.services.rag.qdrant_service.get_qdrant_client", return_value=mock_q):
            ensure_collection()
            mock_q.create_collection.assert_called_once()
            assert mock_q.create_payload_index.call_count == 3

    def test_validates_existing_768_cosine(self):
        mock_q = MagicMock()
        mock_q.collection_exists.return_value = True
        mock_q.get_collection.return_value = MagicMock(config=MagicMock(params=MagicMock(vectors=MagicMock(size=768, distance="Cosine"))))
        with patch("app.services.rag.qdrant_service.get_qdrant_client", return_value=mock_q):
            ensure_collection()  # should not raise

    def test_rejects_dimension_mismatch(self):
        mock_q = MagicMock()
        mock_q.collection_exists.return_value = True
        mock_q.get_collection.return_value = MagicMock(config=MagicMock(params=MagicMock(vectors=MagicMock(size=1536, distance="Cosine"))))
        with patch("app.services.rag.qdrant_service.get_qdrant_client", return_value=mock_q):
            with pytest.raises(RuntimeError, match="vector size 1536"):
                ensure_collection()

    def test_rejects_distance_mismatch(self):
        mock_q = MagicMock()
        mock_q.collection_exists.return_value = True
        from qdrant_client.models import Distance

        mock_q.get_collection.return_value = MagicMock(config=MagicMock(params=MagicMock(vectors=MagicMock(size=768, distance=Distance.EUCLID))))
        with patch("app.services.rag.qdrant_service.get_qdrant_client", return_value=mock_q):
            with pytest.raises(RuntimeError, match="distance metric"):
                ensure_collection()


class TestVerifyAndCleanup:
    def test_verify_true_when_count_matches(self):
        mock_q = MagicMock()
        mock_q.count.return_value = MagicMock(count=5)
        with patch("app.services.rag.qdrant_service.get_qdrant_client", return_value=mock_q):
            assert verify_qdrant_index(user_id=1, file_id=1, index_version=1, expected_chunk_count=5) is True

    def test_verify_false_when_mismatch(self):
        mock_q = MagicMock()
        mock_q.count.return_value = MagicMock(count=3)
        with patch("app.services.rag.qdrant_service.get_qdrant_client", return_value=mock_q):
            assert verify_qdrant_index(user_id=1, file_id=1, index_version=1, expected_chunk_count=5) is False

    def test_cleanup_calls_delete_with_tenant_filter(self):
        mock_q = MagicMock()
        with patch("app.services.rag.qdrant_service.get_qdrant_client", return_value=mock_q):
            cleanup_old_version_vectors(user_id=1, old_index_version=1)
            filt = mock_q.delete.call_args[1]["points_selector"]
            assert any(c.key == "user_id" for c in filt.must)
            assert any(c.key == "index_version" for c in filt.must)

    def test_cleanup_with_file_id_narrows_filter(self):
        mock_q = MagicMock()
        with patch("app.services.rag.qdrant_service.get_qdrant_client", return_value=mock_q):
            cleanup_old_version_vectors(user_id=1, old_index_version=1, file_id=42)
            filt = mock_q.delete.call_args[1]["points_selector"]
            assert len(filt.must) == 3


class TestResume:
    def test_filter_pending(self):
        all_chunks = [{"chunk_index": 0, "clean_text": "a"}, {"chunk_index": 1, "clean_text": "b"}, {"chunk_index": 2, "clean_text": "c"}]
        pending = filter_pending_chunks(all_chunks, {0, 2})
        assert pending == [{"chunk_index": 1, "clean_text": "b"}]

    def test_get_existing_via_scroll(self):
        mock_q = MagicMock()
        mock_q.scroll.return_value = ([MagicMock(payload={"chunk_index": 0}), MagicMock(payload={"chunk_index": 1})], None)
        with patch("app.services.rag.qdrant_service.get_qdrant_client", return_value=mock_q):
            existing = get_existing_chunk_indexes(user_id=1, file_id=1, index_version=1)
            assert existing == {0, 1}

    def test_upsert_with_resume_skips_existing(self):
        all_chunks = [{"chunk_index": i, "clean_text": f"c{i}"} for i in range(3)]
        with patch("app.services.rag.qdrant_service.get_existing_chunk_indexes", return_value={0}):
            with patch("app.services.rag.qdrant_service.upsert_document_chunks", return_value={"upserted": 2, "failed": 0, "batch_progress": []}) as m:
                upsert_with_resume(user_id=1, file_id=1, index_version=1, all_chunks=all_chunks)
                assert len(m.call_args[1]["chunks"]) == 2

    def test_upsert_with_resume_already_complete(self):
        all_chunks = [{"chunk_index": 0, "clean_text": "a"}]
        with patch("app.services.rag.qdrant_service.get_existing_chunk_indexes", return_value={0}):
            result = upsert_with_resume(user_id=1, file_id=1, index_version=1, all_chunks=all_chunks)
            assert result["upserted"] == 0
            assert result["skipped"] == 1
