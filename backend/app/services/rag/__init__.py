"""RAG services package — Phase 4 & 5 exports."""

from app.services.rag.answer_cache import get_cached_answer, set_cached_answer
from app.services.rag.embedding import embed_document, embed_query
from app.services.rag.generation import (
    SourceBlock,
    build_source_blocks,
    generate_answer_stream,
    validate_citations,
)
from app.services.rag.qdrant_service import (
    cleanup_old_version_vectors,
    ensure_collection,
    upsert_document_chunks,
    upsert_with_resume,
    verify_qdrant_index,
)
from app.services.rag.query_service import hydrate_chunks, search_similar_chunks
from app.services.rag.query_utils import (
    build_cache_key,
    cap_per_file_contribution,
    deduplicate_chunks,
    get_user_corpus_revision,
    normalize_score_filtered,
    validate_file_ids,
)
from app.services.rag.indexing_service import run_full_indexing
from app.services.rag.rag_orchestrator import RAGRequest, RAGDiagnostics, run_rag_query

__all__ = [
    # Phase 4
    "embed_document",
    "embed_query",
    "ensure_collection",
    "upsert_document_chunks",
    "upsert_with_resume",
    "verify_qdrant_index",
    "cleanup_old_version_vectors",
    "search_similar_chunks",
    "run_full_indexing",
    # Phase 5
    "hydrate_chunks",
    "validate_file_ids",
    "get_user_corpus_revision",
    "build_cache_key",
    "normalize_score_filtered",
    "deduplicate_chunks",
    "cap_per_file_contribution",
    "get_cached_answer",
    "set_cached_answer",
    "SourceBlock",
    "build_source_blocks",
    "generate_answer_stream",
    "validate_citations",
    "RAGRequest",
    "RAGDiagnostics",
    "run_rag_query",
]