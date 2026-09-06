"""RAG services package — Phase 4 exports."""

from app.services.rag.embedding import embed_document, embed_query
from app.services.rag.qdrant_service import (
    cleanup_old_version_vectors,
    ensure_collection,
    upsert_document_chunks,
    upsert_with_resume,
    verify_qdrant_index,
)
from app.services.rag.query_service import search_similar_chunks
from app.services.rag.indexing_service import run_full_indexing

__all__ = [
    "embed_document",
    "embed_query",
    "ensure_collection",
    "upsert_document_chunks",
    "upsert_with_resume",
    "verify_qdrant_index",
    "cleanup_old_version_vectors",
    "search_similar_chunks",
    "run_full_indexing",
]
