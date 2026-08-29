"""
backend/tests/unit/services/test_vector_service.py

Unit tests for AI vector service utility functions and mock embedding/Qdrant operations.
"""
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.AI.vector_service import (
    build_file_text_representation,
    generate_embedding,
    upsert_file_vector,
    delete_file_vector,
    search_file_vectors,
)


def test_build_file_text_representation_full():
    text = build_file_text_representation(
        filename="notes.pdf",
        title="AWS Notes",
        description="Architecture details",
        tags="aws, cloud",
    )
    assert "Filename: notes.pdf" in text
    assert "Title: AWS Notes" in text
    assert "Description: Architecture details" in text
    assert "Tags: aws, cloud" in text


def test_build_file_text_representation_empty_optionals():
    text = build_file_text_representation(
        filename="data.csv",
        title=None,
        description=None,
        tags=None,
    )
    assert "Filename: data.csv" in text
    assert "Title: Untitled" in text
    assert "Description: No description provided." in text
    assert "Tags: " in text


def test_generate_embedding_no_api_key():
    async def _run():
        with patch("app.services.AI.vector_service.settings.GEMINI_API_KEY", None):
            with patch("app.services.AI.vector_service._gemini_client", None):
                res = await generate_embedding("sample text")
                assert res is None
    asyncio.run(_run())


def test_generate_embedding_success():
    async def _run():
        mock_values = [0.1] * 768
        mock_response = MagicMock()
        mock_embedding = MagicMock()
        mock_embedding.values = mock_values
        mock_response.embeddings = [mock_embedding]

        mock_client = MagicMock()
        mock_client.aio.models.embed_content = AsyncMock(return_value=mock_response)

        with patch("app.services.AI.vector_service.get_gemini_client", return_value=mock_client):
            res = await generate_embedding("sample text")
            assert res == mock_values
    asyncio.run(_run())


def test_upsert_file_vector_success():
    async def _run():
        mock_vector = [0.5] * 768
        mock_q_client = MagicMock()
        mock_q_client.get_collections = AsyncMock(return_value=MagicMock(collections=[]))
        mock_q_client.create_collection = AsyncMock()
        mock_q_client.create_payload_index = AsyncMock()
        mock_q_client.upsert = AsyncMock()

        with patch("app.services.AI.vector_service.generate_embedding", AsyncMock(return_value=mock_vector)), \
             patch("app.services.AI.vector_service.get_qdrant_client", return_value=mock_q_client):
            result = await upsert_file_vector(
                file_id=10,
                user_id=1,
                filename="doc.pdf",
                title="Doc",
                description="Desc",
                tags="tag1",
            )
            assert result is True
            assert mock_q_client.upsert.called
    asyncio.run(_run())


def test_delete_file_vector_success():
    async def _run():
        mock_q_client = MagicMock()
        mock_q_client.delete = AsyncMock()

        with patch("app.services.AI.vector_service.get_qdrant_client", return_value=mock_q_client):
            result = await delete_file_vector(file_id=10)
            assert result is True
            assert mock_q_client.delete.called
    asyncio.run(_run())


def test_search_file_vectors_empty_query():
    async def _run():
        res = await search_file_vectors(query_text="   ", user_id=1)
        assert res == []
    asyncio.run(_run())


def test_search_file_vectors_success():
    async def _run():
        mock_vector = [0.2] * 768
        mock_hit1 = MagicMock()
        mock_hit1.id = 42
        mock_hit1.score = 0.89
        mock_hit2 = MagicMock()
        mock_hit2.id = 15
        mock_hit2.score = 0.85
        mock_hits = MagicMock()
        mock_hits.points = [mock_hit1, mock_hit2]

        mock_q_client = MagicMock()
        mock_q_client.query_points = AsyncMock(return_value=mock_hits)

        with patch("app.services.AI.vector_service.generate_embedding", AsyncMock(return_value=mock_vector)), \
             patch("app.services.AI.vector_service.get_qdrant_client", return_value=mock_q_client):
            results = await search_file_vectors(query_text="cloud architecture", user_id=1)
            assert results == [(42, 0.89), (15, 0.85)]
    asyncio.run(_run())
