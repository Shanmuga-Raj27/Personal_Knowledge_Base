"""
backend/app/utils/rate_limiter.py

In-memory rate limiter utilities for search endpoints.
"""
import time
from collections import defaultdict
from typing import Dict
from fastapi import HTTPException, status

# In-memory rate limiter for search route (30 requests/min per user ID)
SEARCH_REQUESTS: Dict[int, list[float]] = defaultdict(list)
MAX_SEARCH_REQUESTS = 30
SEARCH_RATE_LIMIT_WINDOW_SECONDS = 60.0


def check_search_rate_limit(user_id: int) -> None:
    """Enforce search endpoint rate limiting (30 requests per minute per user ID)."""
    now = time.time()
    if len(SEARCH_REQUESTS) > 2000:
        stale_keys = [
            k for k, v in SEARCH_REQUESTS.items()
            if not v or (now - v[-1] >= SEARCH_RATE_LIMIT_WINDOW_SECONDS)
        ]
        for k in stale_keys:
            del SEARCH_REQUESTS[k]

    SEARCH_REQUESTS[user_id] = [
        t for t in SEARCH_REQUESTS[user_id] if now - t < SEARCH_RATE_LIMIT_WINDOW_SECONDS
    ]
    if len(SEARCH_REQUESTS[user_id]) >= MAX_SEARCH_REQUESTS:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded. Maximum 30 search requests per minute allowed.",
        )
    SEARCH_REQUESTS[user_id].append(now)
