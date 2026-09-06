"""
backend/app/services/rag/config.py

Phase 4 RAG embedding and Qdrant constants.
Centralizes model/dimension/distance contracts so embedding and qdrant services
share a single source of truth. Values are derived from app.core.config.settings.
"""

from qdrant_client.models import Distance, VectorParams

from app.core.config import settings

# ── Gemini embedding contract ─────────────────────────────────────────────
EXPECTED_VECTOR_SIZE: int = 768
GEMINI_EMBEDDING_MODEL: str = settings.GEMINI_EMBEDDING_MODEL  # "gemini-embedding-2"
EMBEDDING_DIMENSIONS: int = settings.EMBEDDING_DIMENSIONS  # 768

# ── Qdrant collection contract ────────────────────────────────────────────
QDRANT_COLLECTION: str = settings.QDRANT_RAG_COLLECTION_NAME  # "document_chunks_v1"
# Alias names used in Phase 4 docs (typo-tolerant)
RAG_QDRANT_COLLECTION: str = QDRANT_COLLECTION
RAG_QDANT_COLLECTION: str = QDRANT_COLLECTION

EXPECTED_QDRANT_VECTOR_PARAMS = VectorParams(
    size=EXPECTED_VECTOR_SIZE,
    distance=Distance.COSINE,
)

# ── Batch / retry / scoring defaults (mirrors settings) ───────────────────
RAG_EMBEDDING_BATCH_SIZE: int = settings.RAG_EMBEDDING_BATCH_SIZE  # 64, max 128
RAG_EMBEDDING_CONCURRENCY: int = settings.RAG_EMBEDDING_CONCURRENCY  # 4
RAG_MAX_RETRIES: int = settings.RAG_MAX_RETRIES  # 5
RAG_BACKOFF_BASE: float = settings.RAG_BACKOFF_BASE  # 1.0
RAG_DEFAULT_TOP_K: int = settings.RAG_DEFAULT_TOP_K  # 6
RAG_SCORE_THRESHOLD: float = settings.RAG_SCORE_THRESHOLD  # 0.35
