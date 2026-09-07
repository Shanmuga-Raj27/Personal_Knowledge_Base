"""
backend/app/apis/routes/system.py

API routes for system checks and diagnostics.
"""
from fastapi import APIRouter, Depends, HTTPException

from app.auth.auth_dependencies import get_current_user
from app.core.config import settings
from app.database.db_models import User
from app.services.rag import runtime_metrics

router = APIRouter(prefix="/system", tags=["system"])


@router.get("/ping")
async def ping():
    """Simple health check endpoint to verify backend connectivity."""
    return {"status": "ok", "message": "pong"}


@router.get("/rag-metrics")
async def rag_metrics(current_user: User = Depends(get_current_user)):
    """Expose in-process RAG runtime metrics (per-stage latency + counters).

    Gated at two levels, consistent with the Phase 7 plan:
      - Authentication: only a logged-in user may read the surface.
      - Feature flag: when RAG_METRICS_ENABLED is False (the default) the
        endpoint reports as disabled rather than returning live data, so the
        surface is never accidentally live in production.
    """
    if not settings.RAG_METRICS_ENABLED:
        raise HTTPException(status_code=404, detail="RAG metrics are disabled.")
    return runtime_metrics.snapshot()