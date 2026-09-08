"""
backend/app/services/rag/schemas.py

Internal Data Transfer Objects (DTOs) for the RAG pipeline:
- Phase 1-4: PDF extraction and chunking DTOs
- Phase 5: API-facing RAG query request/response models
"""
from dataclasses import dataclass
from typing import Optional

from pydantic import BaseModel, Field


@dataclass(frozen=True)
class ExtractedPage:
    page_number: int
    text: str


@dataclass(frozen=True)
class PageWord:
    text: str
    page_number: int
    absolute_word_index: int


@dataclass(frozen=True)
class TextChunk:
    chunk_index: int
    clean_text: str
    page_start: int
    page_end: int
    word_start: int
    word_end: int
    word_count: int
    text_checksum: str


class ChunkPayload(BaseModel):
    """Tiny Qdrant payload — only 4 fields. Text stays in MySQL."""

    user_id: int
    file_id: int
    index_version: int = Field(ge=1)
    chunk_index: int = Field(ge=0)


# ── Phase 5 API-facing RAG query models ───────────────────────────────────


class RAGQueryRequest(BaseModel):
    """API request body for the RAG query endpoint (Phase 6).

    ``file_ids`` is optional: None means "search the whole corpus".
    """

    question: str = Field(..., min_length=1, max_length=5000)
    top_k: int = Field(default=6, ge=1, le=20)
    score_threshold: float = Field(default=0.35, ge=0.0, le=1.0)
    file_ids: Optional[list[int]] = Field(
        default=None,
        min_length=1,
        max_length=5,
        description="Optional file IDs scoping the query; None searches all. When provided, 1-5 IDs only.",
    )


class RAGQueryDiagnostics(BaseModel):
    """Retrieval/generation counters attached to the final SSE event."""

    cache_hit: bool = False
    chunks_retrieved: int = 0
    chunks_hydrated: int = 0
    chunks_after_filter: int = 0
    sources_used: int = 0
    citations_valid: list[str] = Field(default_factory=list)
    query_time_ms: float = 0.0


class RAGSourceResponse(BaseModel):
    """Source chunk reference returned in the final SSE event."""

    chunk_id: str
    filename: str
    page_start: int
    page_end: int


class RAGFinalEvent(BaseModel):
    """Shape of the final SSE event in the RAG answer stream."""

    type: str = "final"
    sources: list[RAGSourceResponse] = Field(default_factory=list)
    diagnostics: RAGQueryDiagnostics = Field(default_factory=RAGQueryDiagnostics)


# ── Phase 6 RAG inspection models ─────────────────────────────────────────


class RAGIndexVersionInfo(BaseModel):
    """One indexed version's stats for the status endpoint."""

    index_version: int
    chunk_count: int
    indexed_chunk_count: int
    status: str
    progress: float = Field(ge=0.0, le=1.0)


class RAGIndexStatusResponse(BaseModel):
    """Response for GET /documents/{id}/index-status."""

    file_id: int
    filename: str
    indexing_status: str
    active_index_version: int
    corpus_revision: int
    progress: float = Field(ge=0.0, le=1.0)  # 0..1, derived from lifecycle
    chunk_count: int
    indexed_chunk_count: int
    rag_error_code: str | None = None
    rag_error_message: str | None = None


class RAGChunkInspection(BaseModel):
    """One chunk for GET /documents/{id}/chunks."""

    chunk_id: str
    chunk_index: int
    index_version: int
    page_start: int
    page_end: int
    word_count: int
    word_start: int
    word_end: int
    clean_text: str
    # raw_text is backend-derived from clean_text only when a raw source is
    # available; for RAG chunks we store no raw_text column, so this is
    # optional and omitted unless explicitly reconstructed.
    raw_text: str | None = None


class RAGChunkListResponse(BaseModel):
    """Response for GET /documents/{id}/chunks."""

    file_id: int
    index_version: int
    chunks: list[RAGChunkInspection] = Field(default_factory=list)
    total: int
