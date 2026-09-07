"""
backend/app/services/rag/runtime_metrics.py

Phase 7 in-process RAG runtime instrumentation (per-stage latency + counters).

A tiny, dependency-free, process-local store that the orchestrator writes to
and GET /system/rag-metrics reads from. No persistence, no external service.

Everything is gateable: when settings.RAG_METRICS_ENABLED is False (default)
all recorders are cheap no-ops so instrumentation can never change behaviour,
and snapshot() reports {"enabled": false}.

Stages recorded by rag_orchestrator.run_rag_query:
    validate  cache_read  search  hydrate  postprocess  generate
    citation  cache_write  total

Counters:
    queries.total  queries.cache_hit  queries.cache_miss  queries.abstain
    citations.valid

(Errors surfacing mid-stream are already logged by the SSE route, so the
store deliberately has no separate error counter.)
"""
import threading
import time
from dataclasses import dataclass

from app.core.config import settings

_LOCK = threading.Lock()
_COUNTERS: dict[str, int] = {}
_STAGES: dict[str, dict] = {}


def enabled() -> bool:
    """True when the RAG_METRICS_ENABLED switch is on."""
    return settings.RAG_METRICS_ENABLED


def increment(name: str, delta: int = 1) -> None:
    """Add ``delta`` to a named counter (no-op when metrics disabled)."""
    if not settings.RAG_METRICS_ENABLED:
        return
    with _LOCK:
        _COUNTERS[name] = _COUNTERS.get(name, 0) + delta


def record_stage(name: str, elapsed_ms: float) -> None:
    """Accumulate a stage sample (no-op when metrics disabled).

    Stores aggregate shape {calls, total_ms, max_ms} so avg/mean can be
    derived without keeping every sample.
    """
    if not settings.RAG_METRICS_ENABLED:
        return
    with _LOCK:
        entry = _STAGES.setdefault(name, {"calls": 0, "total_ms": 0.0, "max_ms": 0.0})
        entry["calls"] += 1
        entry["total_ms"] += elapsed_ms
        entry["max_ms"] = max(entry["max_ms"], elapsed_ms)


def _stage_mean(entry: dict) -> float:
    if entry["calls"] == 0:
        return 0.0
    return entry["total_ms"] / entry["calls"]


def snapshot() -> dict:
    """Thread-safe copy of all recorded metrics (+ enabled flag).

    Returns:
        {
          "enabled": bool,
          "uptime_seconds": float,
          "counters": {name: int},
          "stages": {name: {calls, total_ms, avg_ms, max_ms}},
        }
    """
    with _LOCK:
        counters = dict(_COUNTERS)
        stages = {
            name: {
                "calls": entry["calls"],
                "total_ms": round(entry["total_ms"], 2),
                "avg_ms": round(_stage_mean(entry), 2),
                "max_ms": round(entry["max_ms"], 2),
            }
            for name, entry in _STAGES.items()
        }
    return {
        "enabled": settings.RAG_METRICS_ENABLED,
        "counters": counters,
        "stages": stages,
    }


def reset() -> None:
    """Clear all metrics (test isolation only — not part of the API surface)."""
    with _LOCK:
        _COUNTERS.clear()
        _STAGES.clear()


# ── Stage timing helper for the orchestrator ────────────────────────────────


@dataclass
class _StageTimer:
    """Records an elapsed sample for one stage when it goes out of scope.

    Usage:
        timer = stage_timer("search")
        ... work ...
        timer.stop()
    """

    name: str
    _started: float

    def stop(self) -> None:
        record_stage(self.name, (time.monotonic() - self._started) * 1000)


def stage_timer(name: str) -> _StageTimer:
    return _StageTimer(name=name, _started=time.monotonic())