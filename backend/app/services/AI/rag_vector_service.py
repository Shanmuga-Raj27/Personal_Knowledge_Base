"""
backend/app/services/AI/rag_vector_service.py

Service module for RAG document chunk vector collection operations in Qdrant.
Includes startup schema validation guard and multi-tenant payload indexing.
"""
import logging
from qdrant_client import models
from app.core.config import settings
from app.services.AI.vector_service import get_qdrant_client

logger = logging.getLogger(__name__)


async def ensure_rag_collection() -> None:
    """Startup schema guard for the chunk-level RAG Qdrant collection.

    Validates that the target collection exists, has matching vector dimensionality (768d),
    and Cosine distance metric. Creates the collection and integer payload indexes
    if missing; raises RuntimeError if existing collection schema is incompatible.
    """
    q_client = get_qdrant_client()
    collection_name = settings.QDRANT_RAG_COLLECTION_NAME
    expected_distance = models.Distance.COSINE

    try:
        existing = await q_client.collection_exists(collection_name=collection_name)

        if not existing:
            logger.info("Creating RAG Qdrant collection '%s' (768d, Cosine)...", collection_name)
            await q_client.create_collection(
                collection_name=collection_name,
                vectors_config=models.VectorParams(
                    size=settings.EMBEDDING_DIMENSIONS,
                    distance=expected_distance,
                ),
            )
            # Create payload indexes for multi-tenant isolation, file mapping, and index versioning
            for field_name in ("user_id", "file_id", "index_version"):
                await q_client.create_payload_index(
                    collection_name=collection_name,
                    field_name=field_name,
                    field_schema=models.PayloadSchemaType.INTEGER,
                )
            logger.info("RAG Qdrant collection '%s' created with payload indexes successfully.", collection_name)
            return

        # Collection exists: validate vector size and distance metric
        info = await q_client.get_collection(collection_name=collection_name)
        vectors_params = info.config.params.vectors

        if isinstance(vectors_params, dict):
            vector_size = vectors_params.get("size")
            vector_distance = vectors_params.get("distance")
        else:
            vector_size = getattr(vectors_params, "size", None)
            vector_distance = getattr(vectors_params, "distance", None)

        if vector_size != settings.EMBEDDING_DIMENSIONS:
            raise RuntimeError(
                f"Qdrant collection '{collection_name}' has vector size {vector_size}; "
                f"expected {settings.EMBEDDING_DIMENSIONS}"
            )

        if vector_distance != expected_distance:
            raise RuntimeError(
                f"Qdrant collection '{collection_name}' has distance metric '{vector_distance}'; "
                f"expected '{expected_distance}'"
            )

        logger.info(
            "RAG Qdrant collection '%s' schema validated successfully (%sd, %s).",
            collection_name,
            vector_size,
            vector_distance,
        )
    except RuntimeError:
        raise
    except Exception as exc:
        logger.error("Failed to validate or create RAG Qdrant collection '%s': %s", collection_name, str(exc))
        raise RuntimeError(f"Qdrant RAG collection guard failed: {str(exc)}") from exc
