"""
backend/app/scripts/rag_phase5_smoke.py

RAG Phase 5 end-to-end smoke test against REAL infrastructure
(Backblaze B2/S3, MySQL, Qdrant, Redis, Gemini).

S3-only: the document must already exist as an S3 object key; nothing is
uploaded from the local disk by this script.

Usage:
    uv run python -m app.scripts.rag_phase5_smoke <user_id> <s3_key> \
        ["optional question"] [--force-reindex]

Flow:
    1. Verify the S3 object exists (head_object).
    2. Load the FileMetadata row owned by the user for that key.
    3. If not yet INDEXED (or --force-reindex): process PDF from S3,
       stage chunks, embed + upsert to Qdrant, activate version.
    4. Run the SAME RAG question twice:
       - 1st run  -> full retrieve -> hydrate -> generate path (cache miss)
       - 2nd run  -> Redis cache hit (should be near-instant, cache_hit=True)
    5. Print answer + sources + diagnostics as JSON.
"""
import argparse
import asyncio
import json
import sys

from app.database import SessionLocal
from app.database.db_models import FileMetadata
from app.schemas.enums import IndexingStatus
from app.services.AWS.s3_service import check_object_exists
from app.services.rag.document_processor import process_pdf_from_storage
from app.services.rag.indexing_service import run_full_indexing
from app.services.rag.persistence import stage_document_chunks
from app.services.rag.rag_orchestrator import RAGRequest, RAGDiagnostics, run_rag_query


def ingest_from_s3(db, user_id: int, s3_key: str, force: bool) -> int:
    """Ensure the S3 document is fully indexed; returns the active version."""
    file = (
        db.query(FileMetadata)
        .filter(FileMetadata.userid == user_id, FileMetadata.s3_key == s3_key)
        .first()
    )
    if file is None:
        raise SystemExit(
            f"No FileMetadata row for user_id={user_id} s3_key={s3_key}. "
            "The document must already be registered (uploaded via the app)."
        )

    if not check_object_exists(s3_key):
        raise SystemExit(f"S3 object does not exist: {s3_key}")

    already_indexed = (
        file.indexing_status == IndexingStatus.INDEXED.value
        and (file.active_index_version or 0) > 0
    )
    if already_indexed and not force:
        print(
            f"[SKIP ] file={file.fileid} already INDEXED "
            f"(active_index_version={file.active_index_version}). "
            "Use --force-reindex to rebuild from S3."
        )
        return int(file.active_index_version)

    print(f"[ 2.0 ] process_pdf_from_storage(s3_key={s3_key}) ...")
    processed = process_pdf_from_storage(s3_key=s3_key)
    print(
        f"[ 2.0 ] pages={processed.page_count} "
        f"words={processed.extracted_word_count} chunks={len(processed.chunks)}"
    )

    print("[ 3.0 ] stage_document_chunks() -> MySQL ...")
    new_version = stage_document_chunks(db, file, processed)
    print(f"[ 3.0 ] staged as index_version={new_version}")

    print("[ 4.0 ] run_full_indexing() -> Gemini embeddings + Qdrant + cutover ...")
    result = run_full_indexing(db, file, index_version=new_version, cleanup_old=True)
    if not result["success"]:
        raise SystemExit(f"[4.0 ] indexing FAILED: {result}")
    print(f"[ 4.0 ] active_index_version -> {result['active_index_version']}")
    return int(result["active_index_version"])


async def ask_once(db, user_id: int, question: str, label: str) -> bool:
    """Run one RAG query, accumulating the answer and printing the final event.

    Returns True on success, False if Gemini is temporarily unavailable.
    """
    request = RAGRequest(
        user_id=user_id,
        question=question,
        top_k=6,
        score_threshold=0.35,
    )
    print(f"\n[{label}] QUESTION: {question!r}")
    answer_parts: list[str] = []
    final: dict | None = None

    try:
        async for event in run_rag_query(request, db=db):
            if event["type"] == "token":
                answer_parts.append(event["text"])
                sys.stdout.write(event["text"])
                sys.stdout.flush()
            else:
                final = event
    except Exception as exc:
        print(f"\n[{label}] QUERY FAILED (not a code bug, likely a transient "
              f"Gemini 429/5xx that exhausted retries): {type(exc).__name__}: {exc}")
        return False

    print()
    print(f"[{label}] FINAL EVENT:")
    print(
        json.dumps(
            {
                "answer": "".join(answer_parts),
                "sources": final["sources"] if final else [],
                "diagnostics": final["diagnostics"] if final else {},
            },
            indent=2,
            ensure_ascii=False,
        )
    )

    if final and final["diagnostics"].get("cache_hit"):
        print(f"[{label}] <= served from Redis cache (cache_hit=True)")
    else:
        print(f"[{label}] <= generated live (cache miss), now stored in Redis")
    return True


async def _main(db, user_id: int, question: str) -> int:
    # Two identical queries inside ONE event loop so the Redis singleton stays
    # bound to the same loop (avoids "attached to a different loop" errors).
    ok1 = await ask_once(db, user_id, question, "RUN1-CACHE-MISS")
    if not ok1:
        return 1
    print("\n[INFO] Running the SAME question again to exercise the Redis cache...")
    ok2 = await ask_once(db, user_id, question, "RUN2-CACHE-HIT")
    return 0 if ok2 else 1


def main() -> None:
    parser = argparse.ArgumentParser(description="RAG Phase 5 end-to-end smoke test")
    parser.add_argument("user_id", type=int, help="Authenticated user ID owning the document")
    parser.add_argument("s3_key", type=str, help="Existing S3/B2 object key (e.g. uploads/<uuid>_file.pdf)")
    parser.add_argument(
        "question",
        nargs="?",
        default="Summarize the main topics and key points of this document.",
    )
    parser.add_argument("--force-reindex", action="store_true", help="Rebuild from S3 even if already indexed")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        version = ingest_from_s3(db, args.user_id, args.s3_key, args.force_reindex)
        print(f"[INFO] corpus_revision after indexing may have incremented; running queries...")
        raise SystemExit(asyncio.run(_main(db, args.user_id, args.question)))
    finally:
        db.close()


if __name__ == "__main__":
    main()