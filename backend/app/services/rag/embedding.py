"""
backend/app/services/rag/embedding.py

Phase 4 Gemini embedding utilities.

Generates 768-dimensional vectors via `gemini-embedding-2` with strict
task-type separation: RETRIEVAL_DOCUMENT for chunks, RETRIEVAL_QUERY for
user questions. Every vector is validated before return.
"""

import logging
from typing import List

from google import genai
from google.genai import types

from app.core.config import settings
from app.services.rag.config import (
    EMBEDDING_DIMENSIONS,
    EXPECTED_VECTOR_SIZE,
    GEMINI_EMBEDDING_MODEL,
)

logger = logging.getLogger(__name__)

# ── Gemini client singleton ────────────────────────────────────────────────
_gemini_client: genai.Client | None = None


def _get_gemini_client() -> genai.Client:
    """Return singleton Gemini client; raise if API key missing.

    Separated for testability — tests patch this helper or the underlying
    genai.Client.
    """
    global _gemini_client
    if _gemini_client is not None:
        return _gemini_client
    if not settings.GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY is not configured")
    _gemini_client = genai.Client(api_key=settings.GEMINI_API_KEY)
    return _gemini_client


def _validate_vector(vector: List[float]) -> List[float]:
    """Ensure vector is exactly 768 floats; else raise RuntimeError."""
    if len(vector) != EXPECTED_VECTOR_SIZE:
        raise RuntimeError(
            f"Unexpected embedding dimension: got {len(vector)}, expected {EXPECTED_VECTOR_SIZE}"
        )
    return vector


def _validate_non_empty(text: str, label: str) -> str:
    """Guard against empty / whitespace-only input."""
    if not text or not text.strip():
        raise ValueError(f"{label} is empty or whitespace-only")
    return text


# ── Public API ─────────────────────────────────────────────────────────────


def embed_document(chunk_text: str) -> List[float]:
    """Embed a single chunk text using Gemini RETRIEVAL_DOCUMENT.

    Args:
        chunk_text: Cleaned chunk text (must be non-empty).

    Returns:
        768-dimensional embedding vector.

    Raises:
        ValueError: If chunk_text is empty/whitespace.
        RuntimeError: If Gemini returns wrong dimensions or no embedding.
    """
    _validate_non_empty(chunk_text, "Chunk text")

    client = _get_gemini_client()
    result = client.models.embed_content(
        model=GEMINI_EMBEDDING_MODEL,
        contents=chunk_text,
        config=types.EmbedContentConfig(
            task_type="RETRIEVAL_DOCUMENT",
            output_dimensionality=EMBEDDING_DIMENSIONS,
        ),
    )

    # Validate response shape
    if not result.embeddings or len(result.embeddings) == 0:
        raise RuntimeError("Gemini returned no embeddings")
    vector = result.embeddings[0].values
    if vector is None:
        raise RuntimeError("Gemini returned None vector")
    return _validate_vector(list(vector))


def embed_query(question_text: str) -> List[float]:
    """Embed a user question using Gemini RETRIEVAL_QUERY.

    Args:
        question_text: User question (must be non-empty).

    Returns:
        768-dimensional embedding vector.

    Raises:
        ValueError: If question_text is empty/whitespace.
        RuntimeError: If Gemini returns wrong dimensions or no embedding.
    """
    _validate_non_empty(question_text, "Question text")

    client = _get_gemini_client()
    result = client.models.embed_content(
        model=GEMINI_EMBEDDING_MODEL,
        contents=question_text,
        config=types.EmbedContentConfig(
            task_type="RETRIEVAL_QUERY",
            output_dimensionality=EMBEDDING_DIMENSIONS,
        ),
    )

    if not result.embeddings or len(result.embeddings) == 0:
        raise RuntimeError("Gemini returned no embeddings")
    vector = result.embeddings[0].values
    if vector is None:
        raise RuntimeError("Gemini returned None vector")
    return _validate_vector(list(vector))


def _reset_gemini_client_for_tests() -> None:
    """Test helper: clear singleton so next call re-creates client."""
    global _gemini_client
    _gemini_client = None
