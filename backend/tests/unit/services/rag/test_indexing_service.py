"""
backend/tests/unit/services/rag/test_indexing_service.py

Cutover, verification, and orchestration tests (RAG-phase-4.md:649-656)
"""
import pytest
from unittest.mock import MagicMock, patch

from app.services.rag.indexing_service import build_new_version_vectors, verify_and_cutover, run_full_indexing


def _make_file(fileid=42, userid=7, active_version=1):
    f = MagicMock(fileid=fileid, userid=userid, active_index_version=active_version, corpus_revision=5)
    f.indexing_status = "PENDING"
    return f


class TestBuildNewVersionVectors:
    def test_builds_with_chunks(self):
        mock_file = _make_file()
        mock_db = MagicMock()
        chunks = [{"chunk_index": 0, "clean_text": "hello"}, {"chunk_index": 1, "clean_text": "world"}]
        with patch("app.services.rag.indexing_service.fetch_chunks_for_version", return_value=chunks):
            with patch("app.services.rag.indexing_service.upsert_with_resume", return_value={"upserted": 2, "failed": 0, "batch_progress": []}):
                res = build_new_version_vectors(mock_db, mock_file, index_version=2)
                assert res["total_chunks"] == 2
                assert res["upserted"] == 2

    def test_raises_on_zero_chunks(self):
        mock_file = _make_file(active_version=0)
        with patch("app.services.rag.indexing_service.fetch_chunks_for_version", return_value=[]):
            with pytest.raises(ValueError, match="zero chunks"):
                build_new_version_vectors(MagicMock(), mock_file, index_version=1)

    def test_sets_indexing_status(self):
        mock_file = _make_file()
        chunks = [{"chunk_index": 0, "clean_text": "hi"}]
        with patch("app.services.rag.indexing_service.fetch_chunks_for_version", return_value=chunks):
            with patch("app.services.rag.indexing_service.upsert_with_resume", return_value={"upserted": 1, "failed": 0, "batch_progress": []}):
                build_new_version_vectors(MagicMock(), mock_file, index_version=2)
                assert mock_file.indexing_status == "INDEXING"


class TestVerifyAndCutover:
    def test_success_activates_and_cleans_old(self):
        mock_file = _make_file(active_version=1)
        mock_db = MagicMock()

        def fake_activate(db, file, index_version, indexed_chunk_count):
            file.active_index_version = index_version
            file.corpus_revision = 6

        with patch("app.services.rag.indexing_service.verify_qdrant_index", return_value=True):
            with patch("app.services.rag.indexing_service.activate_rag_index_version", side_effect=fake_activate) as m_act:
                with patch("app.services.rag.indexing_service.cleanup_old_version_vectors") as m_clean:
                    ok = verify_and_cutover(mock_db, mock_file, index_version=2, upsert_result={"upserted": 2, "failed": 0, "total_chunks": 2})
                    assert ok is True
                    assert mock_file.active_index_version == 2
                    m_clean.assert_called_once()
                    assert m_clean.call_args[1]["old_index_version"] == 1

    def test_verification_failure_no_cutover(self):
        mock_file = _make_file(active_version=1)
        with patch("app.services.rag.indexing_service.verify_qdrant_index", return_value=False):
            with patch("app.services.rag.indexing_service.activate_rag_index_version") as m_act:
                ok = verify_and_cutover(MagicMock(), mock_file, index_version=2, upsert_result={"upserted": 2, "failed": 0, "total_chunks": 2})
                assert ok is False
                m_act.assert_not_called()

    def test_upsert_failure_no_cutover(self):
        mock_file = _make_file(active_version=1)
        with patch("app.services.rag.indexing_service.verify_qdrant_index", return_value=True):
            with patch("app.services.rag.indexing_service.activate_rag_index_version") as m_act:
                ok = verify_and_cutover(MagicMock(), mock_file, index_version=2, upsert_result={"upserted": 1, "failed": 1, "total_chunks": 2})
                assert ok is False
                m_act.assert_not_called()

    def test_corpus_revision_incremented(self):
        mock_file = _make_file(active_version=0)
        mock_file.corpus_revision = 5

        def fake_activate(db, file, index_version, indexed_chunk_count):
            file.active_index_version = index_version
            file.corpus_revision = 6

        with patch("app.services.rag.indexing_service.verify_qdrant_index", return_value=True):
            with patch("app.services.rag.indexing_service.activate_rag_index_version", side_effect=fake_activate):
                with patch("app.services.rag.indexing_service.cleanup_old_version_vectors"):
                    verify_and_cutover(MagicMock(), mock_file, index_version=1, upsert_result={"upserted": 1, "failed": 0, "total_chunks": 1})
                    assert mock_file.corpus_revision == 6

    def test_cleanup_failure_does_not_fail_cutover(self):
        mock_file = _make_file(active_version=1)
        mock_db = MagicMock()

        def fake_activate(db, file, index_version, indexed_chunk_count):
            file.active_index_version = index_version

        with patch("app.services.rag.indexing_service.verify_qdrant_index", return_value=True):
            with patch("app.services.rag.indexing_service.activate_rag_index_version", side_effect=fake_activate):
                with patch("app.services.rag.indexing_service.cleanup_old_version_vectors", side_effect=Exception("qdrant down")):
                    ok = verify_and_cutover(mock_db, mock_file, index_version=2, upsert_result={"upserted": 2, "failed": 0, "total_chunks": 2})
                    assert ok is True  # cutover still succeeded
                    assert mock_file.active_index_version == 2


class TestRunFullIndexing:
    def test_full_flow_success(self):
        mock_file = MagicMock(fileid=1, userid=1, active_index_version=0, corpus_revision=0)
        chunks = [{"chunk_index": 0, "clean_text": "hello"}]
        with patch("app.services.rag.indexing_service.fetch_chunks_for_version", return_value=chunks):
            with patch("app.services.rag.indexing_service.upsert_with_resume", return_value={"upserted": 1, "failed": 0, "batch_progress": []}):
                with patch("app.services.rag.indexing_service.verify_qdrant_index", return_value=True):
                    with patch("app.services.rag.indexing_service.activate_rag_index_version") as m_act:
                        def fake(db, file, index_version, indexed_chunk_count):
                            file.active_index_version = index_version

                        m_act.side_effect = fake
                        with patch("app.services.rag.indexing_service.cleanup_old_version_vectors"):
                            res = run_full_indexing(MagicMock(), mock_file, index_version=1)
                            assert res["success"] is True

    def test_full_flow_upsert_failure_marks_retryable(self):
        mock_file = MagicMock(fileid=1, userid=1, active_index_version=0)
        mock_file.indexing_status = "PENDING"
        mock_db = MagicMock()
        chunks = [{"chunk_index": 0, "clean_text": "hi"}]
        with patch("app.services.rag.indexing_service.fetch_chunks_for_version", return_value=chunks):
            with patch("app.services.rag.indexing_service.upsert_with_resume", return_value={"upserted": 0, "failed": 1, "total_chunks": 1, "batch_progress": []}):
                res = run_full_indexing(mock_db, mock_file, index_version=1)
                assert res["success"] is False
                assert mock_file.indexing_status == "FAILED_RETRYABLE"
