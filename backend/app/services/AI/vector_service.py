"""
backend/app/services/AI/vector_service.py

Service layer for embedding generation using Google GenAI SDK and
vector storage/retrieval using Qdrant.
"""
import asyncio
import logging
import threading
from typing import List, Optional

from qdrant_client import AsyncQdrantClient
from qdrant_client import models
from qdrant_client.models import PointStruct, Filter, FieldCondition, MatchValue

from google import genai
from google.genai import types
from google.genai.errors import APIError, ClientError

from app.core.config import settings

logger = logging.getLogger(__name__)

# Global singleton client instances and thread locks
_qdrant_client: Optional[AsyncQdrantClient] = None
_gemini_client: Optional[genai.Client] = None
_qdrant_lock = threading.Lock()
_gemini_lock = threading.Lock()


def get_qdrant_client() -> AsyncQdrantClient:
    """Retrieve or initialize the singleton AsyncQdrantClient instance with thread lock safety."""
    global _qdrant_client
    if _qdrant_client is None:
        with _qdrant_lock:
            if _qdrant_client is None:
                _qdrant_client = AsyncQdrantClient(
                    url=settings.QDRANT_HOST,
                    check_compatibility=False,
                )
    return _qdrant_client


def get_gemini_client() -> Optional[genai.Client]:
    """Retrieve or initialize the singleton Google GenAI client instance with thread lock safety."""
    global _gemini_client
    if _gemini_client is None and settings.GEMINI_API_KEY:
        with _gemini_lock:
            if _gemini_client is None and settings.GEMINI_API_KEY:
                _gemini_client = genai.Client(api_key=settings.GEMINI_API_KEY)
    return _gemini_client


async def close_qdrant_client() -> None:
    """Close the global AsyncQdrantClient instance cleanly on application shutdown."""
    global _qdrant_client
    if _qdrant_client is not None:
        try:
            await _qdrant_client.close()
        except Exception as exc:
            logger.warning("Error closing Qdrant client connection: %s", str(exc))
        finally:
            _qdrant_client = None


async def init_qdrant_collection() -> bool:
    """Ensure the target Qdrant collection and payload indexes exist."""
    q_client = get_qdrant_client()
    collection_name = settings.QDRANT_COLLECTION_NAME
    try:
        collections_response = await q_client.get_collections()
        existing_names = [col.name for col in collections_response.collections]

        if collection_name not in existing_names:
            logger.info("Creating Qdrant collection '%s'...", collection_name)
            await q_client.create_collection(
                collection_name=collection_name,
                vectors_config=models.VectorParams(
                    size=settings.EMBEDDING_DIMENSIONS,
                    distance=models.Distance.COSINE,
                ),
            )

            # Create payload indexes
            await q_client.create_payload_index(
                collection_name=collection_name,
                field_name="user_id",
                field_schema=models.PayloadSchemaType.INTEGER,
            )
            await q_client.create_payload_index(
                collection_name=collection_name,
                field_name="tags",
                field_schema=models.PayloadSchemaType.KEYWORD,
            )
            logger.info("Qdrant collection '%s' created successfully.", collection_name)
        return True
    except Exception as exc:
        logger.warning("Failed to initialize Qdrant collection '%s': %s", collection_name, str(exc))
        return False


def build_file_text_representation(
    filename: str,
    title: Optional[str],
    description: Optional[str],
    tags: Optional[str],
) -> str:
    """Format file metadata into a standard text representation for embedding."""
    parts = [
        f"Filename: {filename}",
        f"Title: {title or 'Untitled'}",
        f"Description: {description or 'No description provided.'}",
        f"Tags: {tags or ''}",
    ]
    return "\n".join(parts)


async def generate_embedding(
    text: str, task_type: Optional[str] = "RETRIEVAL_DOCUMENT"
) -> Optional[List[float]]:
    """Generate dense vector embedding from text using Gemini API with timeout guard."""
    g_client = get_gemini_client()
    if not g_client:
        logger.warning("Gemini client is not initialized (GEMINI_API_KEY missing).")
        return None

    try:
        response = await asyncio.wait_for(
            g_client.aio.models.embed_content(
                model=settings.GEMINI_EMBEDDING_MODEL,
                contents=text,
                config=types.EmbedContentConfig(
                    output_dimensionality=settings.EMBEDDING_DIMENSIONS,
                    task_type=task_type,
                ),
            ),
            timeout=settings.GEMINI_API_TIMEOUT_SECONDS,
        )
        if response and response.embeddings and len(response.embeddings) > 0:
            return response.embeddings[0].values
        return None
    except asyncio.TimeoutError:
        logger.error("Gemini API call timed out after %s seconds.", settings.GEMINI_API_TIMEOUT_SECONDS)
        return None
    except (APIError, ClientError) as exc:
        status_code = getattr(exc, "code", getattr(exc, "status_code", None))
        if status_code == 429 or "429" in str(exc):
            logger.warning("Gemini API Rate Limit (429) encountered. Applying 30s backoff delay...")
            await asyncio.sleep(30)
            return None
        logger.error("Gemini API error during embedding generation: %s", str(exc))
        return None
    except Exception as exc:
        logger.error("Unexpected error generating Gemini embedding: %s", str(exc))
        return None


async def upsert_file_vector(
    file_id: int,
    user_id: int,
    filename: str,
    title: Optional[str],
    description: Optional[str],
    tags: Optional[str],
) -> bool:
    """Generate embedding for file metadata and upsert vector point to Qdrant."""
    text_content = build_file_text_representation(
        filename=filename, title=title, description=description, tags=tags
    )
    vector = await generate_embedding(
        text_content, task_type="RETRIEVAL_DOCUMENT"
    )
    if vector is None:
        logger.warning("Skipping Qdrant vector upsert for file %s (embedding generation returned None).", file_id)
        return False

    q_client = get_qdrant_client()
    collection_name = settings.QDRANT_COLLECTION_NAME

    try:
        await init_qdrant_collection()
        await q_client.upsert(
            collection_name=collection_name,
            points=[
                PointStruct(
                    id=file_id,
                    vector=vector,
                    payload={
                        "file_id": file_id,
                        "user_id": user_id,
                        "filename": filename,
                        "title": title or "",
                        "tags": tags or "",
                        "description": description or "",
                    },
                )
            ],
        )
        logger.info("Successfully upserted Qdrant vector point for file_id=%s, user_id=%s.", file_id, user_id)
        return True
    except Exception as exc:
        logger.error("Failed to upsert Qdrant vector point for file_id=%s: %s", file_id, str(exc))
        return False


async def delete_file_vector(file_id: int) -> bool:
    """Delete a vector point from Qdrant by file_id."""
    q_client = get_qdrant_client()
    collection_name = settings.QDRANT_COLLECTION_NAME
    try:
        await q_client.delete(
            collection_name=collection_name,
            points_selector=[file_id],
        )
        logger.info("Successfully deleted Qdrant vector point for file_id=%s.", file_id)
        return True
    except Exception as exc:
        logger.warning("Failed to delete Qdrant vector point for file_id=%s: %s", file_id, str(exc))
        return False


async def search_file_vectors(
    query_text: str, user_id: int, limit: int = 15, score_threshold: Optional[float] = None, offset: int = 0
) -> List[tuple[int, float]]:
    """Perform multi-tenant scoped semantic vector similarity search on Qdrant.

    Returns:
        List of tuples (file_id, similarity_score).
    """
    if not query_text.strip():
        return []

    effective_threshold = score_threshold if score_threshold is not None else settings.RAG_SCORE_THRESHOLD

    query_vector = await generate_embedding(
        query_text, task_type="RETRIEVAL_QUERY"
    )
    if query_vector is None:
        logger.warning("Semantic vector search fallback: unable to generate query embedding.")
        raise RuntimeError("Embedding generation failed.")

    q_client = get_qdrant_client()
    collection_name = settings.QDRANT_COLLECTION_NAME

    # Oversample candidate points from Qdrant to prevent candidate starvation after filtering
    fetch_limit = min(1000, max(100, offset + limit * 2))

    try:
        hits = await q_client.query_points(
            collection_name=collection_name,
            query=query_vector,
            query_filter=Filter(
                must=[
                    FieldCondition(
                        key="user_id",
                        match=MatchValue(value=user_id),
                    )
                ]
            ),
            limit=fetch_limit,
            score_threshold=effective_threshold,
        )
        matched_results = [
            (hit.id, hit.score) for hit in hits.points if isinstance(hit.id, int)
        ]
        logger.info(
            "Qdrant oversampling fetched %d candidate points; %d points passed score threshold >= %.2f.",
            fetch_limit,
            len(matched_results),
            effective_threshold,
        )
        return matched_results
    except Exception as exc:
        logger.error("Qdrant query error for user_id=%s: %s", user_id, str(exc))
        raise RuntimeError(f"Vector search failed: {str(exc)}") from exc
