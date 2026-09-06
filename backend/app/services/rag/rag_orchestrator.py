"""
backend/app/services/rag/rag_orchestrator.py

Phase 5 RAG query orchestrator: wires retrieve -> hydrate -> filter ->
generate -> cache into a single async generator of SSE event dicts.

Event contract (consumed by Phase 6's SSE endpoint):
    {"type": "token", "text": "<token>"}      -- streaming answer token
    {"type": "final", "sources": [...],
     "diagnostics": {...}}                     -- sources + timing/summary

Abstains (insufficient evidence) are handled gracefully: no generation call,
no cache write, just a final event flagging the shortfall.
"""
import logging
import time
from dataclasses import dataclass, field
from typing import Any, AsyncIterator

from sqlalchemy.orm import Session

from app.core.config import settings
from app.services.rag.answer_cache import get_cached_answer, set_cached_answer
from app.services.rag.generation import (
    SourceBlock,
    build_source_blocks,
    generate_answer_stream,
    validate_citations,
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

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RAGRequest:
    """Validated RAG query request fields."""
    user_id: int
    question: str
    file_ids: list[int] | None = None
    top_k: int = settings.RAG_DEFAULT_TOP_K
    score_threshold: float = settings.RAG_SCORE_THRESHOLD


@dataclass
class RAGDiagnostics:
    """Summary counters attached to the final SSE event."""
    cache_hit: bool = False
    chunks_retrieved: int = 0
    chunks_hydrated: int = 0
    chunks_after_filter: int = 0
    sources_used: int = 0
    citations_valid: list[str] = field(default_factory=list)
    query_time_ms: float = 0.0


def _abstain(**overrides: Any) -> dict:
    """Build a final event signalling insufficient evidence."""
    diagnostics = RAGDiagnostics(**overrides)
    return {
        "type": "final",
        "sources": [],
        "diagnostics": {
            "cache_hit": diagnostics.cache_hit,
            "chunks_retrieved": diagnostics.chunks_retrieved,
            "chunks_hydrated": diagnostics.chunks_hydrated,
            "chunks_after_filter": diagnostics.chunks_after_filter,
            "sources_used": diagnostics.sources_used,
            "citations_valid": diagnostics.citations_valid,
            "query_time_ms": diagnostics.query_time_ms,
            "insufficient_evidence": True,
        },
    }


def _fit_context_budget(chunks: list[dict]) -> list[dict]:
    """Keep the highest-ranked chunks that fit the token budget.

    Approximates tokens as 4 characters each (rough English/conversational
    density) and adds ~200 chars of labeling overhead per block. Stops at the
    first chunk that would overflow so the best-ranked chunks always remain.
    """
    budget_chars = settings.RAG_CONTEXT_BUDGET_TOKENS * 4
    fitted: list[dict] = []
    chars_used = 0
    for chunk in chunks:
        block_chars = len(chunk["clean_text"]) + 200
        if chars_used + block_chars > budget_chars:
            break
        fitted.append(chunk)
        chars_used += block_chars
    return fitted


def _to_diagnostics_dict(d: RAGDiagnostics) -> dict:
    return {
        "cache_hit": d.cache_hit,
        "chunks_retrieved": d.chunks_retrieved,
        "chunks_hydrated": d.chunks_hydrated,
        "chunks_after_filter": d.chunks_after_filter,
        "sources_used": d.sources_used,
        "citations_valid": d.citations_valid,
        "query_time_ms": d.query_time_ms,
    }


async def run_rag_query(
    request: RAGRequest,
    db: Session,
) -> AsyncIterator[dict]:
    """Execute a full RAG query end-to-end, yielding SSE event dicts.

    Paths:
        cache hit                -> final event (no generation)
        no retrieval hits        -> abstain final event
        no hydrated chunks       -> abstain final event
        nothing fits the budget  -> abstain final event
        otherwise                -> token events + final event (sources)

    Args:
        request: Validated query (user_id, question, scope, params).
        db: SQLAlchemy session for ownership + hydration queries.

    Yields:
        Dicts following the SSE event contract above.
    """
    start = time.monotonic()

    # 1. Prove file IDs belong to the user and are actively indexed.
    validated_file_ids = validate_file_ids(request.user_id, request.file_ids, db)

    # 2. Cache identity: user + corpus revision + canonical request.
    corpus_revision = get_user_corpus_revision(request.user_id, db)
    cache_key = build_cache_key(
        user_id=request.user_id,
        corpus_revision=corpus_revision,
        question=request.question,
        file_ids=validated_file_ids,
        top_k=request.top_k,
        score_threshold=request.score_threshold,
    )

    # 3. Cache check (fail-open: return None on any Redis problem).
    cached = await get_cached_answer(cache_key)
    if cached is not None:
        logger.info(
            "RAG cache HIT user_id=%s key=%s", request.user_id, cache_key[:30]
        )
        diagnostics = RAGDiagnostics(cache_hit=True)
        diagnostics.query_time_ms = round((time.monotonic() - start) * 1000, 1)
        yield {"type": "token", "text": cached}
        yield {
            "type": "final",
            "sources": [],
            "diagnostics": _to_diagnostics_dict(diagnostics),
        }
        return

    # 4. Embed question (RETRIEVAL_QUERY) and retrieve candidates from Qdrant.
    ranked_hits = search_similar_chunks(
        user_id=request.user_id,
        query_text=request.question,
        file_ids=validated_file_ids,
        top_k=request.top_k,
        score_threshold=request.score_threshold,
    )

    if not ranked_hits:
        logger.info("RAG no hits user_id=%s", request.user_id)
        yield _abstain(
            cache_hit=False,
            chunks_retrieved=0,
            chunks_hydrated=0,
            chunks_after_filter=0,
            query_time_ms=round((time.monotonic() - start) * 1000, 1),
        )
        return

    # 5. Hydrate content from MySQL (single query, preserves Qdrant rank).
    hydrated = hydrate_chunks(request.user_id, ranked_hits, db)

    if not hydrated:
        logger.info(
            "RAG hydration empty user_id=%s (stale/foreign hits dropped)",
            request.user_id,
        )
        yield _abstain(
            cache_hit=False,
            chunks_retrieved=len(ranked_hits),
            chunks_hydrated=0,
            chunks_after_filter=0,
            query_time_ms=round((time.monotonic() - start) * 1000, 1),
        )
        return

    # 6. Filter low scores, deduplicate overlaps, cap per-file, fit budget.
    filtered = normalize_score_filtered(hydrated, request.score_threshold)
    deduped = deduplicate_chunks(filtered)
    capped = cap_per_file_contribution(deduped)
    budget_chunks = _fit_context_budget(capped)

    if not budget_chunks:
        logger.info(
            "RAG nothing fits budget user_id=%s (filtered=%d)",
            request.user_id,
            len(filtered),
        )
        yield _abstain(
            cache_hit=False,
            chunks_retrieved=len(ranked_hits),
            chunks_hydrated=len(hydrated),
            chunks_after_filter=0,
            query_time_ms=round((time.monotonic() - start) * 1000, 1),
        )
        return

    # 7. Label sources and stream generation from Gemini.
    sources: list[SourceBlock] = build_source_blocks(budget_chunks)
    valid_chunk_ids = {s.chunk_id for s in sources}

    full_answer = ""
    async for token in generate_answer_stream(request.question, sources):
        full_answer += token
        yield {"type": "token", "text": token}

    # 8. Validate citations against actually-retrieved chunk IDs.
    valid_citations = validate_citations(full_answer, valid_chunk_ids)

    # 9. Cache the final answer (fire-and-forget, never raises).
    await set_cached_answer(cache_key, full_answer)

    # 10. Emit final event with sources + diagnostics.
    diagnostics = RAGDiagnostics(
        cache_hit=False,
        chunks_retrieved=len(ranked_hits),
        chunks_hydrated=len(hydrated),
        chunks_after_filter=len(budget_chunks),
        sources_used=len(sources),
        citations_valid=valid_citations,
        query_time_ms=round((time.monotonic() - start) * 1000, 1),
    )

    source_details = [
        {
            "chunk_id": s.chunk_id,
            "filename": s.filename,
            "page_start": s.page_start,
            "page_end": s.page_end,
        }
        for s in sources
    ]

    yield {
        "type": "final",
        "sources": source_details,
        "diagnostics": _to_diagnostics_dict(diagnostics),
    }