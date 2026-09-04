"""
backend/tests/unit/core/test_config.py

Unit tests for RAG configuration settings and startup model validation.
"""
import pytest
from pydantic import ValidationError
from app.core.config import Settings


def test_settings_load_defaults(monkeypatch):
    """Test that Settings loads default RAG values and passes validation cleanly."""
    settings = Settings()
    assert settings.GEMINI_EMBEDDING_MODEL == "gemini-embedding-2"
    assert settings.GEMINI_GENERATION_MODEL == "gemini-3.6-flash"
    assert settings.EMBEDDING_DIMENSIONS == 768
    assert settings.QDRANT_RAG_COLLECTION_NAME == "document_chunks_v1"
    assert settings.QDRANT_DISTANCE == "COSINE"
    assert settings.RAG_CHUNK_WORDS == 800
    assert settings.RAG_CHUNK_OVERLAP_WORDS == 100
    assert settings.RAG_DEFAULT_TOP_K <= settings.RAG_MAX_TOP_K
    assert settings.RAG_SCORE_THRESHOLD == 0.35


def test_invalid_embedding_dimensions():
    """Test that an invalid EMBEDDING_DIMENSIONS value raises a ValidationError."""
    with pytest.raises(ValidationError) as exc_info:
        Settings(EMBEDDING_DIMENSIONS=1536)
    assert "EMBEDDING_DIMENSIONS must be 768" in str(exc_info.value)


def test_invalid_chunk_overlap():
    """Test that RAG_CHUNK_OVERLAP_WORDS >= RAG_CHUNK_WORDS raises a ValidationError."""
    with pytest.raises(ValidationError) as exc_info:
        Settings(RAG_CHUNK_WORDS=500, RAG_CHUNK_OVERLAP_WORDS=500)
    assert "RAG_CHUNK_OVERLAP_WORDS must be smaller than RAG_CHUNK_WORDS" in str(exc_info.value)


def test_invalid_top_k():
    """Test that RAG_DEFAULT_TOP_K > RAG_MAX_TOP_K raises a ValidationError."""
    with pytest.raises(ValidationError) as exc_info:
        Settings(RAG_DEFAULT_TOP_K=25, RAG_MAX_TOP_K=20)
    assert "RAG_DEFAULT_TOP_K must be <= RAG_MAX_TOP_K" in str(exc_info.value)


def test_invalid_qdrant_distance():
    """Test that QDRANT_DISTANCE != COSINE raises a ValidationError."""
    with pytest.raises(ValidationError) as exc_info:
        Settings(QDRANT_DISTANCE="EUCLIDEAN")
    assert "QDRANT_DISTANCE must be COSINE" in str(exc_info.value)
