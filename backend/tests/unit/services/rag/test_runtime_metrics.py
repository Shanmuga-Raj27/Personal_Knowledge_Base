"""
backend/tests/unit/services/rag/test_runtime_metrics.py

Phase 7 Runtime-metrics store unit tests.

The store is a tiny process-local accumulator (no I/O, no persistence). The
flag (settings.RAG_METRICS_ENABLED) makes every recorder a no-op by default;
these tests force it on only where recording is under test.
"""
import pytest
from unittest.mock import patch

from app.core.config import settings
from app.services.rag import runtime_metrics


@pytest.fixture(autouse=True)
def _metrics_isolation():
    runtime_metrics.reset()
    yield
    runtime_metrics.reset()


def test_enabled_false_by_default():
    assert runtime_metrics.enabled() is False


def test_increment_is_noop_when_disabled():
    runtime_metrics.increment("queries.total", 5)
    snap = runtime_metrics.snapshot()
    assert snap["enabled"] is False
    assert snap["counters"] == {}
    assert snap["stages"] == {}


def test_record_stage_is_noop_when_disabled():
    runtime_metrics.record_stage("search", 10.0)
    assert runtime_metrics.snapshot()["stages"] == {}


def test_enabled_reflects_settings_flag():
    with patch.object(settings, "RAG_METRICS_ENABLED", True):
        assert runtime_metrics.enabled() is True


def test_increment_accumulates_across_names():
    with patch.object(settings, "RAG_METRICS_ENABLED", True):
        runtime_metrics.increment("queries.total")
        runtime_metrics.increment("queries.total")
        runtime_metrics.increment("queries.abstain", 3)
        snap = runtime_metrics.snapshot()
        assert snap["counters"] == {"queries.total": 2, "queries.abstain": 3}


def test_record_stage_aggregates_calls_totals_and_max():
    with patch.object(settings, "RAG_METRICS_ENABLED", True):
        runtime_metrics.record_stage("search", 12.0)
        runtime_metrics.record_stage("search", 20.0)
        runtime_metrics.record_stage("validate", 4.0)
        snap = runtime_metrics.snapshot()
        search = snap["stages"]["search"]
        assert search["calls"] == 2
        assert search["total_ms"] == 32.0
        assert search["avg_ms"] == 16.0
        assert search["max_ms"] == 20.0
        assert snap["stages"]["validate"] == {
            "calls": 1,
            "total_ms": 4.0,
            "avg_ms": 4.0,
            "max_ms": 4.0,
        }


def test_snapshot_returns_defensive_copies():
    with patch.object(settings, "RAG_METRICS_ENABLED", True):
        runtime_metrics.increment("queries.total")
        snap = runtime_metrics.snapshot()
        snap["counters"]["queries.total"] = 999
        assert runtime_metrics.snapshot()["counters"]["queries.total"] == 1


def test_stage_timer_records_a_single_sample():
    with patch.object(settings, "RAG_METRICS_ENABLED", True):
        timer = runtime_metrics.stage_timer("search")
        timer.stop()
        assert runtime_metrics.snapshot()["stages"]["search"]["calls"] == 1


def test_stage_timer_is_noop_when_disabled():
    timer = runtime_metrics.stage_timer("search")
    timer.stop()
    assert runtime_metrics.snapshot()["stages"] == {}


def test_reset_clears_recorded_metrics():
    with patch.object(settings, "RAG_METRICS_ENABLED", True):
        runtime_metrics.increment("queries.total")
        runtime_metrics.record_stage("search", 5.0)
        runtime_metrics.reset()
        snap = runtime_metrics.snapshot()
        assert snap["counters"] == {}
        assert snap["stages"] == {}