"""
backend/app/apis/routes/rag_routes.py

Phase 6 RAG query surface: POST /rag/query streams a grounded answer via
Server-Sent Events (SSE), framing the Phase 5 orchestrator's event dicts
exactly as:

    data: {"type": "token", "text": "..."}\n\n
    data: {"type": "final", "sources": [...], "diagnostics": {...}}\n\n

The route is thin by design: authenticate, validate file_ids up-front
(fast 400 for bad requests), construct RAGRequest with the authenticated
user's ID injected at the boundary, then stream. No Qdrant/Gemini/Redis/raw
SQL lives here.
"""
import json
import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.auth.auth_dependencies import get_current_user
from app.database import get_db
from app.database.db_models import User
from app.services.rag.rag_orchestrator import RAGRequest, run_rag_query
from app.services.rag.schemas import RAGQueryRequest
from app.services.rag.query_utils import validate_file_ids

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/rag", tags=["rag"])


async def _event_stream(
    request: Request,
    user_id: int,
    payload: RAGQueryRequest,
    db: Session,
):
    """Drain the orchestrator's dict events and frame them as SSE.

    A leading comment line flushes headers through proxies immediately.
    """
    yield ": connected\n\n"

    rag_request = RAGRequest(
        user_id=user_id,
        question=payload.question,
        file_ids=payload.file_ids,
        top_k=payload.top_k,
        score_threshold=payload.score_threshold,
    )

    try:
        async for event in run_rag_query(rag_request, db):
            if await request.is_disconnected():
                break
            yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
    except Exception as exc:
        logger.error("RAG query stream failed for user_id=%s: %s", user_id, exc, exc_info=True)
        yield f"data: {json.dumps({'type': 'error', 'detail': 'Internal error during answer generation.'})}\n\n"


@router.post("/query")
async def rag_query(
    payload: RAGQueryRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Stream a grounded RAG answer via Server-Sent Events.

    invalid/mixed-ownership file_ids are rejected up-front with a clean 400
    before any streaming begins (the orchestrator re-validates inside the
    stream as defense-in-depth).
    """
    try:
        validate_file_ids(current_user.id, payload.file_ids, db)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return StreamingResponse(
        _event_stream(request, current_user.id, payload, db),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )