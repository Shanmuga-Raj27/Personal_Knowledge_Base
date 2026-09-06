"""
backend/tests/unit/services/rag/test_query_service.py

Tenant isolation, filter, and rank tests (RAG-phase-4.md:658-664)
"""
import pytest
from unittest.mock import MagicMock, patch

from app.services.rag.query_service import _build_tenant_filter, search_similar_chunks


def _mock_vector():
    return [0.1] * 768


class TestBuildTenantFilter:
    def test_mandatory_user_id(self):
        filt = _build_tenant_filter(user_id=5)
        assert len(filt.must) == 1
        assert filt.must[0].key == "user_id"
        assert filt.must[0].match.value == 5

    def test_single_file_id(self):
        filt = _build_tenant_filter(user_id=5, file_ids=[42])
        assert len(filt.must) == 2
        assert filt.must[1].match.value == 42

    def test_multi_file_ids(self):
        filt = _build_tenant_filter(user_id=5, file_ids=[1, 2, 3])
        assert filt.must[1].match.any == [1, 2, 3]

    def test_none_file_ids_no_extra(self):
        filt = _build_tenant_filter(user_id=1, file_ids=None)
        assert len(filt.must) == 1

    def test_empty_list_no_extra(self):
        filt = _build_tenant_filter(user_id=1, file_ids=[])
        assert len(filt.must) == 1


class TestSearchSimilarChunks:
    def test_search_returns_hits_with_rank(self):
        mock_q = MagicMock()
        mock_q.query_points.return_value = MagicMock(
            points=[
                MagicMock(payload={"chunk_id": "uuid-1", "file_id": 10, "index_version": 1, "chunk_index": 0}, score=0.9, id="uuid-1"),
                MagicMock(payload={"file_id": 10, "index_version": 1, "chunk_index": 1}, score=0.8, id="uuid-2"),
            ]
        )
        with patch("app.services.rag.query_service.get_qdrant_client", return_value=mock_q):
            with patch("app.services.rag.query_service.embed_query", return_value=_mock_vector()):
                hits = search_similar_chunks(user_id=5, query_text="hello")
                assert len(hits) == 2
                assert hits[0]["rank"] == 0
                assert hits[1]["rank"] == 1
                # chunk_id fallback to point id
                assert hits[1]["chunk_id"] == "uuid-2"

    def test_mandatory_user_id_filter_sent_to_qdrant(self):
        mock_q = MagicMock()
        mock_q.query_points.return_value = MagicMock(points=[])
        with patch("app.services.rag.query_service.get_qdrant_client", return_value=mock_q):
            with patch("app.services.rag.query_service.embed_query", return_value=_mock_vector()):
                search_similar_chunks(user_id=99, query_text="test")
                filt = mock_q.query_points.call_args[1]["query_filter"]
                assert filt.must[0].key == "user_id"
                assert filt.must[0].match.value == 99

    def test_file_ids_forwarded_to_qdrant(self):
        mock_q = MagicMock()
        mock_q.query_points.return_value = MagicMock(points=[])
        with patch("app.services.rag.query_service.get_qdrant_client", return_value=mock_q):
            with patch("app.services.rag.query_service.embed_query", return_value=_mock_vector()):
                search_similar_chunks(user_id=1, query_text="hi", file_ids=[10, 20])
                filt = mock_q.query_points.call_args[1]["query_filter"]
                assert len(filt.must) == 2

    def test_cross_tenant_isolation(self):
        mock_q = MagicMock()
        mock_q.query_points.return_value = MagicMock(points=[])
        with patch("app.services.rag.query_service.get_qdrant_client", return_value=mock_q):
            with patch("app.services.rag.query_service.embed_query", return_value=_mock_vector()):
                search_similar_chunks(user_id=1, query_text="hello")
                f1 = mock_q.query_points.call_args[1]["query_filter"]
                search_similar_chunks(user_id=2, query_text="hello")
                f2 = mock_q.query_points.call_args[1]["query_filter"]
                assert f1.must[0].match.value != f2.must[0].match.value

    def test_empty_query_raises(self):
        with pytest.raises(ValueError, match="empty or whitespace"):
            search_similar_chunks(user_id=1, query_text="   ")

    def test_top_k_capped_to_max(self):
        mock_q = MagicMock()
        mock_q.query_points.return_value = MagicMock(points=[])
        with patch("app.services.rag.query_service.get_qdrant_client", return_value=mock_q):
            with patch("app.services.rag.query_service.embed_query", return_value=_mock_vector()):
                search_similar_chunks(user_id=1, query_text="hi", top_k=999)
                assert mock_q.query_points.call_args[1]["limit"] == 20

    def test_default_threshold_used(self):
        mock_q = MagicMock()
        mock_q.query_points.return_value = MagicMock(points=[])
        with patch("app.services.rag.query_service.get_qdrant_client", return_value=mock_q):
            with patch("app.services.rag.query_service.embed_query", return_value=_mock_vector()):
                search_similar_chunks(user_id=1, query_text="hi")
                # Default 0.35 from config
                assert mock_q.query_points.call_args[1]["score_threshold"] == 0.35

    def test_uses_retrieval_query_embedding(self):
        mock_q = MagicMock()
        mock_q.query_points.return_value = MagicMock(points=[])
        with patch("app.services.rag.query_service.get_qdrant_client", return_value=mock_q):
            with patch("app.services.rag.query_service.embed_query", return_value=_mock_vector()) as m_emb:
                search_similar_chunks(user_id=1, query_text="my question")
                m_emb.assert_called_once_with("my question")
