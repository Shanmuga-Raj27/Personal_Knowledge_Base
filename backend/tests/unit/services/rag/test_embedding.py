"""
backend/tests/unit/services/rag/test_embedding.py

Phase 4 embedding validation tests (RAG-phase-4.md:629-635)
"""
import pytest
from unittest.mock import MagicMock, patch

from app.services.rag.embedding import embed_document, embed_query, _reset_gemini_client_for_tests


def _mock_vector(dim=768, val=0.1):
    return [val] * dim


def _mock_gemini_client(vector):
    mock_client = MagicMock()
    mock_result = MagicMock()
    mock_result.embeddings = [MagicMock(values=vector)]
    mock_client.models.embed_content.return_value = mock_result
    return mock_client


class TestEmbedDocument:
    def test_returns_768_for_valid_text(self):
        _reset_gemini_client_for_tests()
        vector = _mock_vector(768)
        mock_client = _mock_gemini_client(vector)
        with patch("app.services.rag.embedding._get_gemini_client", return_value=mock_client):
            result = embed_document("hello world clean text " * 20)
            assert len(result) == 768
            assert result == vector

    def test_uses_retrieval_document_task_type(self):
        _reset_gemini_client_for_tests()
        mock_client = _mock_gemini_client(_mock_vector())
        with patch("app.services.rag.embedding._get_gemini_client", return_value=mock_client):
            embed_document("some chunk")
            call_kwargs = mock_client.models.embed_content.call_args[1]
            assert call_kwargs["config"].task_type == "RETRIEVAL_DOCUMENT"
            assert call_kwargs["model"] == "gemini-embedding-2"
            assert call_kwargs["config"].output_dimensionality == 768

    def test_raises_on_empty(self):
        for bad in ["", "   ", "\n\t"]:
            with pytest.raises(ValueError, match="empty or whitespace"):
                embed_document(bad)

    def test_raises_on_none_vector(self):
        _reset_gemini_client_for_tests()
        mock_client = MagicMock()
        mock_client.models.embed_content.return_value = MagicMock(embeddings=[MagicMock(values=None)])
        with patch("app.services.rag.embedding._get_gemini_client", return_value=mock_client):
            with pytest.raises(RuntimeError, match="None vector"):
                embed_document("hello")

    def test_raises_on_no_embeddings(self):
        _reset_gemini_client_for_tests()
        mock_client = MagicMock()
        mock_client.models.embed_content.return_value = MagicMock(embeddings=[])
        with patch("app.services.rag.embedding._get_gemini_client", return_value=mock_client):
            with pytest.raises(RuntimeError, match="no embeddings"):
                embed_document("hello")

    def test_raises_on_dimension_mismatch(self):
        _reset_gemini_client_for_tests()
        mock_client = _mock_gemini_client(_mock_vector(10))
        with patch("app.services.rag.embedding._get_gemini_client", return_value=mock_client):
            with pytest.raises(RuntimeError, match="Unexpected embedding dimension: got 10"):
                embed_document("hello")

    def test_raises_on_1536_dimension(self):
        _reset_gemini_client_for_tests()
        mock_client = _mock_gemini_client(_mock_vector(1536))
        with patch("app.services.rag.embedding._get_gemini_client", return_value=mock_client):
            with pytest.raises(RuntimeError):
                embed_document("hello")


class TestEmbedQuery:
    def test_returns_768_for_valid_question(self):
        _reset_gemini_client_for_tests()
        mock_client = _mock_gemini_client(_mock_vector())
        with patch("app.services.rag.embedding._get_gemini_client", return_value=mock_client):
            result = embed_query("what is RAG?")
            assert len(result) == 768

    def test_uses_retrieval_query_task_type(self):
        _reset_gemini_client_for_tests()
        mock_client = _mock_gemini_client(_mock_vector())
        with patch("app.services.rag.embedding._get_gemini_client", return_value=mock_client):
            embed_query("what is RAG?")
            call_kwargs = mock_client.models.embed_content.call_args[1]
            assert call_kwargs["config"].task_type == "RETRIEVAL_QUERY"
            assert call_kwargs["config"].output_dimensionality == 768

    def test_raises_on_empty(self):
        with pytest.raises(ValueError, match="empty or whitespace"):
            embed_query("  ")
        with pytest.raises(ValueError):
            embed_query("")

    def test_dimension_validation(self):
        _reset_gemini_client_for_tests()
        mock_client = _mock_gemini_client(_mock_vector(100))
        with patch("app.services.rag.embedding._get_gemini_client", return_value=mock_client):
            with pytest.raises(RuntimeError, match="Unexpected embedding dimension"):
                embed_query("hello")

    def test_document_and_query_use_different_task_types(self):
        _reset_gemini_client_for_tests()
        mock_client = _mock_gemini_client(_mock_vector())
        with patch("app.services.rag.embedding._get_gemini_client", return_value=mock_client):
            embed_document("chunk")
            assert mock_client.models.embed_content.call_args[1]["config"].task_type == "RETRIEVAL_DOCUMENT"
            embed_query("query")
            assert mock_client.models.embed_content.call_args[1]["config"].task_type == "RETRIEVAL_QUERY"
