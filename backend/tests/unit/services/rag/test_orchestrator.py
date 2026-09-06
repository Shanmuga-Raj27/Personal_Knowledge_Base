"""
backend/tests/unit/services/rag/test_orchestrator.py

Integration-style unit tests for Phase 5 rag_orchestrator.run_rag_query,
with Gemini/Redis/Qdrant/MySQL all mocked at the orchestrator boundary.

Covers:
- cache miss -> retrieve -> hydrate -> filter -> generate -> cache -> final
- cache hit returns immediately (no search/generation)
- insufficient evidence abstains without calling generation
- invalid file IDs propagate ValueError
- per-file contribution cap reflected in sources
- final diagnostics contain all expected fields
"""
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.rag.rag_orchestrator import RAGRequest, run_rag_query

UUID_A = "aaaaaaaa-1111-2222-3333-444455556666"
UUID_B = "bbbbbbbb-1111-2222-3333-444455556666"
UUID_C = "cccccccc-1111-2222-3333-444455556666"
UUID_D = "dddddddd-1111-2222-3333-444455556666"
UUID_E = "eeeeeeee-1111-2222-3333-444455556666"


def _hit(cid, fid, chunk_index, score, rank):
    return {
        "chunk_id": cid,
        "file_id": fid,
        "index_version": 1,
        "chunk_index": chunk_index,
        "score": score,
        "rank": rank,
    }


def _hydrated(cid, fid, chunk_index, score, rank):
    return {
        "chunk_id": cid,
        "file_id": fid,
        "index_version": 1,
        "chunk_index": chunk_index,
        "clean_text": "refund policy says id=" + cid,
        "page_start": 1,
        "page_end": 2,
        "original_filename": "policy.pdf",
        "score": score,
        "rank": rank,
    }


def _run(request, **extra_patches):
    """Collect events by running run_rag_query with default mocks applied."""
    defaults = {
        "app.services.rag.rag_orchestrator.get_cached_answer": AsyncMock(return_value=None),
        "app.services.rag.rag_orchestrator.set_cached_answer": AsyncMock(),
        "app.services.rag.rag_orchestrator.validate_file_ids": MagicMock(return_value=None),
        "app.services.rag.rag_orchestrator.get_user_corpus_revision": MagicMock(return_value=0),
    }

    class _Contexts:
        def __enter__(self):
            self._stack = [
                patch(target, value)
                for target, value in {**defaults, **extra_patches}.items()
            ]
            for p in self._stack:
                p.start()
            return self

        def __exit__(self, *exc):
            for p in self._stack:
                p.stop()

    events = []

    async def _collect():
        ctx = _Contexts()
        with ctx:
            async for ev in run_rag_query(request, db=object()):
                events.append(ev)

    asyncio.run(_collect())
    return events


class TestOrchestrator:
    def test_cache_miss_full_path(self):
        async def fake_stream(question, sources):
            assert len(sources) == 2
            yield "The refund "
            yield f"policy is id={UUID_A} and id={UUID_B}"

        events = _run(
            RAGRequest(user_id=1, question="What is refund policy?"),
            **{
                "app.services.rag.rag_orchestrator.search_similar_chunks": MagicMock(
                    return_value=[
                        _hit(UUID_A, 10, 0, 0.82, 0),
                        _hit(UUID_B, 10, 1, 0.71, 1),
                    ]
                ),
                "app.services.rag.rag_orchestrator.hydrate_chunks": MagicMock(
                    return_value=[
                        _hydrated(UUID_A, 10, 0, 0.82, 0),
                        _hydrated(UUID_B, 10, 1, 0.71, 1),
                    ]
                ),
                "app.services.rag.rag_orchestrator.generate_answer_stream": fake_stream,
            },
        )

        token_events = [e for e in events if e["type"] == "token"]
        final = events[-1]

        assert [e["text"] for e in token_events] == ["The refund ", "policy is id=aaaaaaaa-1111-2222-3333-444455556666 and id=bbbbbbbb-1111-2222-3333-444455556666"]
        assert final["type"] == "final"
        assert len(final["sources"]) == 2
        assert final["sources"][0]["chunk_id"] == UUID_A
        assert final["sources"][0]["filename"] == "policy.pdf"

        d = final["diagnostics"]
        assert d["cache_hit"] is False
        assert d["chunks_retrieved"] == 2
        assert d["chunks_hydrated"] == 2
        assert d["sources_used"] == 2
        assert set(d["citations_valid"]) == {UUID_A, UUID_B}
        assert isinstance(d["query_time_ms"], float)

    def test_cache_hit_returns_immediately(self):
        mock_search = MagicMock()
        mock_stream = MagicMock()

        events = _run(
            RAGRequest(user_id=1, question="same question"),
            **{
                "app.services.rag.rag_orchestrator.get_cached_answer": AsyncMock(return_value="cached answer"),
                "app.services.rag.rag_orchestrator.search_similar_chunks": mock_search,
                "app.services.rag.rag_orchestrator.generate_answer_stream": mock_stream,
            },
        )

        assert len(events) == 2
        assert events[0]["type"] == "token"
        assert events[0]["text"] == "cached answer"
        assert events[1]["type"] == "final"
        assert events[1]["diagnostics"]["cache_hit"] is True
        assert events[1]["sources"] == []
        mock_search.assert_not_called()
        mock_stream.assert_not_called()

    def test_no_hits_abstains_without_generation(self):
        mock_stream = MagicMock()
        events = _run(
            RAGRequest(user_id=1, question="anything"),
            **{
                "app.services.rag.rag_orchestrator.search_similar_chunks": MagicMock(return_value=[]),
                "app.services.rag.rag_orchestrator.generate_answer_stream": mock_stream,
            },
        )

        assert len(events) == 1
        assert events[0]["diagnostics"]["insufficient_evidence"] is True
        assert events[0]["diagnostics"]["chunks_retrieved"] == 0
        mock_stream.assert_not_called()

    def test_nothing_fits_budget_abstains(self):
        # One huge chunk that exceeds the context budget on its own.
        mock_stream = MagicMock()
        huge = dict(_hydrated(UUID_A, 10, 0, 0.9, 0))
        huge["clean_text"] = "x" * (4 * 10_000)  # ~10k "tokens"
        events = _run(
            RAGRequest(user_id=1, question="q"),
            **{
                "app.services.rag.rag_orchestrator.search_similar_chunks": MagicMock(
                    return_value=[_hit(UUID_A, 10, 0, 0.9, 0)]
                ),
                "app.services.rag.rag_orchestrator.hydrate_chunks": MagicMock(
                    return_value=[huge]
                ),
                "app.services.rag.rag_orchestrator.generate_answer_stream": mock_stream,
            },
        )

        assert events[0]["type"] == "final"
        assert events[0]["diagnostics"]["insufficient_evidence"] is True
        mock_stream.assert_not_called()

    def test_invalid_file_ids_propagate_value_error(self):
        with patch(
            "app.services.rag.rag_orchestrator.validate_file_ids",
            side_effect=ValueError("None of the requested file IDs are owned"),
        ):
            with patch("app.services.rag.rag_orchestrator.get_cached_answer", AsyncMock(return_value=None)):
                with pytest.raises(ValueError, match="None of the requested file IDs"):
                    asyncio.run(
                        run_rag_query(
                            RAGRequest(user_id=1, question="q", file_ids=[999]),
                            db=object(),
                        ).__anext__()
                    )

    def test_per_file_cap_limits_sources(self):
        async def fake_stream(question, sources):
            yield ""  # empty tokens are fine

        hits = [_hit(UUID_A, 10, i, 0.8, i) for i in range(5)]
        hydrated = [_hydrated(UUID_A, 10, i, 0.8, i) for i in range(5)]

        events = _run(
            RAGRequest(user_id=1, question="q"),
            **{
                "app.services.rag.rag_orchestrator.search_similar_chunks": MagicMock(return_value=hits),
                "app.services.rag.rag_orchestrator.hydrate_chunks": MagicMock(return_value=hydrated),
                "app.services.rag.rag_orchestrator.generate_answer_stream": fake_stream,
            },
        )

        final = events[-1]
        # 5 chunks from one file, capped to 3 by RAG_MAX_PER_FILE_CONTRIBUTION
        assert len(final["sources"]) == 3
        assert final["diagnostics"]["chunks_after_filter"] == 3
        assert len({s["filename"] for s in final["sources"]}) == 1

    def test_tenant_isolation_hydration_empty_abstains(self):
        # Cross-tenant: Qdrant returned hits but MySQL hydration drops them
        # because the user_id ownership filter rejects them.
        mock_stream = MagicMock()
        events = _run(
            RAGRequest(user_id=1, question="q"),
            **{
                "app.services.rag.rag_orchestrator.search_similar_chunks": MagicMock(
                    return_value=[_hit(UUID_A, 99, 0, 0.9, 0)]
                ),
                "app.services.rag.rag_orchestrator.hydrate_chunks": MagicMock(return_value=[]),
                "app.services.rag.rag_orchestrator.generate_answer_stream": mock_stream,
            },
        )

        assert events[0]["type"] == "final"
        assert events[0]["diagnostics"]["chunks_hydrated"] == 0
        assert events[0]["diagnostics"]["insufficient_evidence"] is True
        mock_stream.assert_not_called()

    def test_final_event_has_all_diagnostics_fields(self):
        async def fake_stream(question, sources):
            yield "ok id=" + UUID_A

        events = _run(
            RAGRequest(user_id=1, question="q"),
            **{
                "app.services.rag.rag_orchestrator.search_similar_chunks": MagicMock(
                    return_value=[_hit(UUID_A, 10, 0, 0.9, 0)]
                ),
                "app.services.rag.rag_orchestrator.hydrate_chunks": MagicMock(
                    return_value=[_hydrated(UUID_A, 10, 0, 0.9, 0)]
                ),
                "app.services.rag.rag_orchestrator.generate_answer_stream": fake_stream,
            },
        )

        d = events[-1]["diagnostics"]
        expected = {
            "cache_hit",
            "chunks_retrieved",
            "chunks_hydrated",
            "chunks_after_filter",
            "sources_used",
            "citations_valid",
            "query_time_ms",
        }
        assert expected.issubset(d.keys())