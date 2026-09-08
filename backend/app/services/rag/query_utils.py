"""
backend/app/services/rag/query_utils.py

Phase 5 request validation, cache-key identity, and context filtering helpers.

This module owns the "policy" side of a RAG query:
- proving file IDs belong to the authenticated user and are actively indexed
- building deterministic cache keys so an answer is only reused for an
  identical query over an identical corpus
- score filtering, deduplication, and per-file contribution caps so the
  generation context is clean and balanced before it is sent to Gemini
"""
import json
import logging
from hashlib import sha256

from sqlalchemy.orm import Session

from app.core.config import settings
from app.database.db_models import FileMetadata, UserCorpusState
from app.schemas.enums import FileStatus, IndexingStatus

logger = logging.getLogger(__name__)


def validate_file_ids(
    user_id: int,
    file_ids: list[int] | None,
    db: Session,
) -> list[int] | None:
    """Validate file IDs against MySQL ownership and active index status.

    Each requested ID must be a row owned by ``user_id``, have status ACTIVE,
    and have reached the INDEXED lifecycle state. Any ID failing those checks
    is silently dropped.

    Args:
        user_id: Authenticated user who owns the files.
        file_ids: Optional IDs scoping the query. None means "search all files".
        db: SQLAlchemy session.

    Returns:
        Validated list of file IDs, or None when ``file_ids`` was None.

    Raises:
        ValueError: If specific file IDs were requested but none are valid.
    """
    if file_ids is None:
        return None

    validated: list[int] = []
    for fid in file_ids:
        row = (
            db.query(FileMetadata.fileid)
            .filter(
                FileMetadata.fileid == fid,
                FileMetadata.userid == user_id,
                FileMetadata.status == FileStatus.ACTIVE.value,
                FileMetadata.indexing_status == IndexingStatus.INDEXED.value,
            )
            .first()
        )
        if row is not None:
            validated.append(fid)

    if not validated:
        raise ValueError(
            "None of the requested file IDs are owned, active, and indexed for this user."
        )
    return validated


def get_user_corpus_revision(user_id: int, db: Session) -> int:
    """Return the current corpus revision for a user; 0 when no row exists."""
    state = db.get(UserCorpusState, user_id)
    if state is None:
        return 0
    return int(state.corpus_revision)


def build_cache_key(
    user_id: int,
    corpus_revision: int,
    question: str,
    file_ids: list[int] | None,
    top_k: int,
    score_threshold: float,
    prompt_version: str | None = None,
    model_version: str | None = None,
) -> str:
    """Build a deterministic cache key for a RAG answer.

    The key must change whenever the answer could change, so it includes the
    question, the selected file set, top_k, score threshold, prompt version,
    and generation-model version -- not just the question text. The corpus
    revision is prepended so re-indexing a document invalidates every prior
    answer without scanning Redis.

    Returns:
        Cache key of the form ``{user_id}:{corpus_revision}:{query_hash}``.
    """
    prompt_version = prompt_version or settings.RAG_PROMPT_VERSION
    model_version = model_version or settings.GEMINI_GENERATION_MODEL

    # Normalize question so the same query with different casing/whitespace
    # hits the same cache key across browser sessions.
    normalized_q = " ".join(question.strip().lower().split())
    canonical = {
        "q": normalized_q,
        "f": sorted(file_ids) if file_ids else "all",
        "k": int(top_k),
        "t": float(score_threshold),
        "p": prompt_version,
        "m": model_version,
    }
    query_hash = sha256(
        json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return f"{user_id}:{corpus_revision}:{query_hash}"


def normalize_score_filtered(
    hydrated_chunks: list[dict],
    score_threshold: float,
) -> list[dict]:
    """Remove chunks whose Qdrant score is below the cutoff.

    Args:
        hydrated_chunks: Rows from hydrate_chunks (each has a "score" key).
        score_threshold: Minimum cosine similarity to keep.

    Returns:
        Chunks with ``score >= score_threshold``, preserving original order.
    """
    return [c for c in hydrated_chunks if c["score"] >= score_threshold]


def deduplicate_chunks(hydrated_chunks: list[dict]) -> list[dict]:
    """Keep the highest-scored chunk per (file_id, chunk_index).

    Overlapping chunks (800-100-word windows) can match the same passage;
    holding multiple near-identical windows wastes context budget. Only the
    best-scoring copy of each window survives.

    Args:
        hydrated_chunks: Hydrated rows sorted by Qdrant rank.

    Returns:
        Deduplicated chunks, re-sorted by original Qdrant rank.
    """
    seen: dict[tuple[int, int], dict] = {}
    for chunk in hydrated_chunks:
        key = (chunk["file_id"], chunk["chunk_index"])
        if key not in seen or chunk["score"] > seen[key]["score"]:
            seen[key] = chunk
    return sorted(seen.values(), key=lambda c: c["rank"])


def cap_per_file_contribution(
    chunks: list[dict],
    max_per_file: int | None = None,
) -> list[dict]:
    """Cap how many chunks any single file can contribute to the context.

    Prevents one dominant document from flooding Gemini with evidence and
    starving the others. Files contribute their highest-ranked chunks first
    because input order follows Qdrant rank.

    Args:
        chunks: Filtered, deduplicated chunks in rank order.
        max_per_file: Per-file allowance (defaults to
            settings.RAG_MAX_PER_FILE_CONTRIBUTION).

    Returns:
        Chunks with at most ``max_per_file`` per file, in input rank order.
    """
    max_per_file = max_per_file or settings.RAG_MAX_PER_FILE_CONTRIBUTION
    file_counts: dict[int, int] = {}
    capped = []
    for chunk in chunks:
        fid = chunk["file_id"]
        count = file_counts.get(fid, 0)
        if count < max_per_file:
            capped.append(chunk)
            file_counts[fid] = count + 1
    return capped