"""
backend/tests/unit/services/test_rag_vector_service.py

Unit tests for Qdrant RAG collection guard function and schema validation.
"""
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from qdrant_client import models

from app.services.AI.rag_vector_service import ensure_rag_collection


def test_ensure_rag_collection_creates_new():
    """Test creating a new RAG collection with payload indexes when collection does not exist."""
    async def _run():
        mock_q_client = MagicMock()
        mock_q_client.collection_exists = AsyncMock(return_value=False)
        mock_q_client.create_collection = AsyncMock()
        mock_q_client.create_payload_index = AsyncMock()

        with patch("app.services.AI.rag_vector_service.get_qdrant_client", return_value=mock_q_client):
            await ensure_rag_collection()

            mock_q_client.create_collection.assert_called_once()
            assert mock_q_client.create_payload_index.call_count == 3

    asyncio.run(_run())


def test_ensure_rag_collection_valid_existing():
    """Test startup validation when existing collection matches 768d Cosine schema."""
    async def _run():
        mock_q_client = MagicMock()
        mock_q_client.collection_exists = AsyncMock(return_value=True)

        mock_info = MagicMock()
        mock_info.config.params.vectors.size = 768
        mock_info.config.params.vectors.distance = models.Distance.COSINE
        mock_q_client.get_collection = AsyncMock(return_value=mock_info)

        with patch("app.services.AI.rag_vector_service.get_qdrant_client", return_value=mock_q_client):
            await ensure_rag_collection()

    asyncio.run(_run())


def test_ensure_rag_collection_size_mismatch():
    """Test that a RuntimeError is raised if existing collection vector size is not 768."""
    async def _run():
        mock_q_client = MagicMock()
        mock_q_client.collection_exists = AsyncMock(return_value=True)

        mock_info = MagicMock()
        mock_info.config.params.vectors.size = 1536
        mock_info.config.params.vectors.distance = models.Distance.COSINE
        mock_q_client.get_collection = AsyncMock(return_value=mock_info)

        with patch("app.services.AI.rag_vector_service.get_qdrant_client", return_value=mock_q_client):
            with pytest.raises(RuntimeError) as exc_info:
                await ensure_rag_collection()
            assert "vector size 1536" in str(exc_info.value)

    asyncio.run(_run())


def test_ensure_rag_collection_distance_mismatch():
    """Test that a RuntimeError is raised if existing collection distance metric is not Cosine."""
    async def _run():
        mock_q_client = MagicMock()
        mock_q_client.collection_exists = AsyncMock(return_value=True)

        mock_info = MagicMock()
        mock_info.config.params.vectors.size = 768
        mock_info.config.params.vectors.distance = models.Distance.EUCLID
        mock_q_client.get_collection = AsyncMock(return_value=mock_info)

        with patch("app.services.AI.rag_vector_service.get_qdrant_client", return_value=mock_q_client):
            with pytest.raises(RuntimeError) as exc_info:
                await ensure_rag_collection()
            assert "distance metric" in str(exc_info.value)

    asyncio.run(_run())
