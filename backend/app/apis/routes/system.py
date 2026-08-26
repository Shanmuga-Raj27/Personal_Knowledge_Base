"""
backend/app/apis/routes/system.py

API routes for system checks and diagnostics.
"""
from fastapi import APIRouter

router = APIRouter(prefix="/system", tags=["system"])


@router.get("/ping")
async def ping():
    """Simple health check endpoint to verify backend connectivity."""
    return {"status": "ok", "message": "pong"}
