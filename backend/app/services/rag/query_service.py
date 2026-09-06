"""
backend/app/services/rag/query_service.py

Phase 4 tenant-isolated Qdrant query service.

- Mandatory user_id filter on every search (security invariant)
- Optional file_ids filtered via Qdrant (resolved from MySQL ownership upstream)
- Preserves Qdrant rank for MySQL hydration ordering
- Uses RETRIEVAL_QUERY embeddings
"""

import logging
from typing import Any

from qdrant_client.models import FieldCondition, Filter, MatchAny, MatchValue

from app.core.config import settings
from app.services.rag.config import QDRANT_COLLECTION
from app.services.rag.embedding import embed_query
from app.services.rag.qdrant_service import get_qdrant_client

logger = logging.getLogger(__name__)


def _build_tenant_filter(
    user_id: int,
    file_ids: list[int] | None = None,
) -> Filter:
    """Build Qdrant Filter with mandatory user_id + optional file_ids.

    Args:
        user_id: Authenticated owner (mandatory).
        file_ids: Optional list of file IDs already validated against MySQL ownership.
                 If provided, results are restricted to those files.

    Returns:
        Qdrant Filter with must conditions.
    """
    must = [
        FieldCondition(key="user_id", match=MatchValue(value=user_id)),
    ]

    if file_ids:
        # Use MatchAny for multi-file, MatchValue for single to keep index usage optimal
        if len(file_ids) == 1:
            must.append(
                FieldCondition(key="file_id", match=MatchValue(value=file_ids[0])),
            )
        else:
            must.append(
                FieldCondition(key="file_id", match=MatchAny(any=file_ids)),
            )

    return Filter(must=must)


def search_similar_chunks(
    user_id: int,
    query_text: str,
    file_ids: list[int] | None = None,
    top_k: int | None = None,
    score_threshold: float | None = None,
) -> list[dict[str, Any]]:
    """Search Qdrant for similar chunks with mandatory tenant isolation.

    Flow:
        1. Embed query with RETRIEVAL_QUERY (768d)
        2. Build Filter(must=[user_id] + optional file_ids)
        3. Query Qdrant (query_points) with threshold/limit
        4. Preserve rank (SQL IN has no order guarantee)

    Args:
        user_id: Authenticated user ID — always filtered.
        query_text: User question (non-empty).
        file_ids: Optional subset of owned file IDs to restrict search.
                 Caller must validate ownership before passing.
        top_k: Max hits (defaults to RAG_DEFAULT_TOP_K=6, capped by RAG_MAX_TOP_K=20).
        score_threshold: Cosine similarity floor (defaults to 0.35).

    Returns:
        List of dicts sorted by Qdrant rank:
        {chunk_id, file_id, index_version, chunk_index, score, rank}
        chunk_id falls back to point ID string if payload missing it.

    Raises:
        ValueError: If query_text empty/whitespace.
        RuntimeError: If embedding fails.
    """
    if top_k is None:
        top_k = settings.RAG_DEFAULT_TOP_K
    # Cap to configured max to prevent abuse
    top_k = max(1, min(int(top_k), settings.RAG_MAX_TOP_K))

    if score_threshold is None:
        score_threshold = settings.RAG_SCORE_THRESHOLD

    # Step 1: embed query (validates non-empty + 768d)
    query_vector = embed_query(query_text)

    # Step 2: build mandatory tenant filter
    qfilter = _build_tenant_filter(user_id=user_id, file_ids=file_ids)

    # Step 3: query Qdrant — prefer query_points (modern), fallback to search if mocked
    client = get_qdrant_client()

    # Use query_points (QdrantClient modern API). Some test mocks expose 'search',
    # so we handle both.
    if hasattr(client, "query_points"):
        response = client.query_points(
            collection_name=QDRANT_COLLECTION,
            query=query_vector,
            query_filter=qfilter,
            limit=top_k,
            score_threshold=score_threshold,
            with_payload=True,
        )
        # QueryResponse has .points
        points = getattr(response, "points", response)
        # If response is list (mock), unwrap
        if isinstance(points, dict) and "points" in points:
            points = points["points"]
    elif hasattr(client, "search"):
        # Legacy mock path (phase-4 doc style)
        points = client.search(
            collection_name=QDRANT_COLLECTION,
            query_vector=query_vector,
            query_filter=qfilter,
            limit=top_k,
            score_threshold=score_threshold,
        )
    else:
        raise RuntimeError("Qdrant client has no query method")

    # Step 4: preserve rank and extract payload
    hits: list[dict[str, Any]] = []
    for rank, point in enumerate(points or []):
        payload = getattr(point, "payload", None) or {}
        # Handle dict mock vs object
        if isinstance(point, dict):
            payload = point.get("payload", {})
            score = point.get("score", 0.0)
            pid = point.get("id", "")
        else:
            score = getattr(point, "score", 0.0)
            pid = getattr(point, "id", "")

        hits.append(
            {
                "chunk_id": payload.get("chunk_id", str(pid)),
                "file_id": payload.get("file_id"),
                "index_version": payload.get("index_version"),
                "chunk_index": payload.get("chunk_index"),
                "score": float(score) if score is not None else 0.0,
                "rank": rank,
            }
        )

    logger.info(
        "Qdrant search user_id=%s file_ids=%s top_k=%s threshold=%.2f returned %d hits",
        user_id,
        file_ids,
        top_k,
        score_threshold,
        len(hits),
    )
    return hits


def hydrate_chunks(
    user_id: int,
    ranked_hits: list[dict[str, Any]],
    db_session: Any,
) -> list[dict[str, Any]]:
    """One-query MySQL hydration preserving Qdrant rank.

    Placeholder for Phase 5 — included here so query_service owns the full
    retrieve→hydrate contract. Validates active_index_version and
    indexing_status=INDEXED.

    This function is *not* called in Phase 4 tests; it documents the intended
    pattern for Phase 5 integration.

    Args:
        user_id: Authenticated user.
        ranked_hits: Output of search_similar_chunks (must contain chunk_id/score/rank).
        db_session: SQLAlchemy Session.

    Returns:
        Hydrated rows sorted by original Qdrant rank, each with clean_text,
        page_start, page_end, original_filename, score.
    """
    if not ranked_hits:
        return []

    # Build rank map before SQL (SQL IN unordered)
    ranks = {
        hit["chunk_id"]: (hit["rank"], hit["score"])
        for hit in ranked_hits
        if hit.get("chunk_id")
    }
    if not ranks:
        return []

    from sqlalchemy import bindparam, text as sa_text

    HYDRATE = sa_text(
        """
        SELECT dc.chunk_id, dc.file_id, dc.index_version, dc.chunk_index,
               dc.clean_text, dc.page_start, dc.page_end, dc.original_filename
        FROM document_chunks AS dc
        JOIN file_metadata AS fm ON fm.fileid = dc.file_id
        WHERE dc.user_id = :user_id
          AND dc.chunk_id IN :chunk_ids
          AND dc.index_version = fm.active_index_version
          AND fm.indexing_status = 'INDEXED'
        """
    ).bindparams(bindparam("chunk_ids", expanding=True))

    rows = db_session.execute(
        HYDRATE, {"user_id": user_id, "chunk_ids": list(ranks)}
    ).mappings()

    hydrated = []
    for row in rows:
        chunk_id = row["chunk_id"]
        rank, score = ranks.get(chunk_id, (9999, 0.0))
        hydrated.append(dict(row) | {"score": score, "rank": rank})

    # Preserve Qdrant rank in application code
    hydrated.sort(key=lambda r: r["rank"])
    return hydrated
