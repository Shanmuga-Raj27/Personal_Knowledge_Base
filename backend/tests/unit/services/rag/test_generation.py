"""
backend/tests/unit/services/rag/test_generation.py

Unit tests for Phase 5 generation:
- SourceBlock construction from hydrated chunks
- SOURCE/END SOURCE prompt formatting (single & multi page)
- system/user prompt separation
- citation extraction & validation
- transient 5xx retry at stream open (async backoff, no token duplication)
"""
import pytest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from google.genai.errors import ServerError

from app.services.rag.generation import (
    SourceBlock,
    build_generation_prompt,
    build_source_blocks,
    format_source_prompt,
    generate_answer_stream,
    validate_citations,
)
import app.services.rag.generation as gen_mod

UUID1 = "a1b2c3d4-1111-2222-3333-444455556666"
UUID2 = "11111111-2222-3333-4444-555555555555"
UUID3 = "00000000-0000-0000-0000-000000000000"


def _chunk(cid, filename="doc.pdf", page_start=2, page_end=3, text="hello world"):
    return {
        "chunk_id": cid,
        "original_filename": filename,
        "page_start": page_start,
        "page_end": page_end,
        "clean_text": text,
        "score": 0.8,
        "rank": 0,
    }


class TestBuildSourceBlocks:
    def test_creates_source_block_per_chunk(self):
        chunks = [_chunk(UUID1), _chunk(UUID2)]
        blocks = build_source_blocks(chunks)
        assert len(blocks) == 2
        assert blocks[0].chunk_id == UUID1
        assert blocks[0].filename == "doc.pdf"
        assert blocks[0].page_start == 2
        assert blocks[0].page_end == 3
        assert blocks[0].clean_text == "hello world"

    def test_empty_input(self):
        assert build_source_blocks([]) == []


class TestFormatSourcePrompt:
    def test_renders_label_and_end_marker(self):
        block = SourceBlock(UUID1, "doc.pdf", 2, 3, "text here")
        text = format_source_prompt([block])
        assert text.startswith(f"SOURCE id={UUID1} file=doc.pdf pages=2-3:")
        assert "text here" in text
        assert text.endswith("END SOURCE")

    def test_single_page_shows_single_number(self):
        block = SourceBlock(UUID1, "doc.pdf", 5, 5, "x")
        assert "pages=5:" in format_source_prompt([block])
        assert "5-5" not in format_source_prompt([block])

    def test_multiple_blocks_joined(self):
        blocks = [
            SourceBlock(UUID1, "a.pdf", 1, 1, "aaa"),
            SourceBlock(UUID2, "b.pdf", 2, 4, "bbb"),
        ]
        text = format_source_prompt(blocks)
        assert text.count("SOURCE id=") == 2
        assert text.count("END SOURCE") == 2


class TestBuildGenerationPrompt:
    def test_returns_system_and_user(self):
        blocks = [SourceBlock(UUID1, "doc.pdf", 1, 1, "evidence")]
        system, user = build_generation_prompt("What is it?", blocks)
        assert "SOURCE blocks" in system
        assert "undetermined" not in system
        assert "QUESTION: What is it?" in user
        assert UUID1 in user

    def test_sources_in_user_turn_not_system(self):
        marker = "ZQX_SOURCE_CONTENT_12345"
        blocks = [SourceBlock(UUID1, "doc.pdf", 1, 1, marker)]
        system, user = build_generation_prompt("Q", blocks)
        # system carries only rules; the untrusted data lives in the user turn
        assert UUID1 not in system
        assert marker not in system
        assert marker in user


class TestValidateCitations:
    def test_returns_valid_ids_only(self):
        answer = f"See id={UUID1} and chunk_id={UUID2}"
        valid = validate_citations(answer, {UUID1, UUID2, UUID3})
        assert set(valid) == {UUID1, UUID2}

    def test_strips_invalid_citations(self):
        answer = f"Uses id={UUID1} but also chunk_id={UUID3}"
        valid = validate_citations(answer, {UUID1})
        assert valid == [UUID1]
        assert UUID3 not in valid

    def test_empty_answer_returns_empty(self):
        assert validate_citations("No citations here.", {UUID1}) == []

    def test_case_insensitive_match(self):
        answer = f"See ID={UUID1.upper()}"
        valid = validate_citations(answer, {UUID1})
        assert valid == [UUID1]

    def test_non_uuid_reference_ignored(self):
        answer = "id=not-a-uuid and id=xxx"
        assert validate_citations(answer, {UUID1}) == []


class _FakeStream:
    """Async iterable over pre-baked text chunks (mimics Gemini stream)."""

    def __init__(self, texts):
        self._texts = texts

    def __aiter__(self):
        return self._aiter()

    async def _aiter(self):
        for text in self._texts:
            yield SimpleNamespace(text=text)


class _FailingStream:
    """Yields some text then fails mid-stream (must NOT trigger a retry)."""

    def __init__(self, first_text, error):
        self._done = False
        self._first = first_text
        self._error = error

    def __aiter__(self):
        return self._aiter()

    async def _aiter(self):
        yield SimpleNamespace(text=self._first)
        raise self._error


def _server_error_503():
    return ServerError(503, {"error": {"message": "high demand", "status": "UNAVAILABLE"}})


@pytest.fixture
def slow_retry(monkeypatch):
    """Keep settings small so tests don't sleep with real 2^n backoff."""
    monkeypatch.setattr(gen_mod.settings, "RAG_MAX_RETRIES", 2)
    monkeypatch.setattr(gen_mod.settings, "RAG_BACKOFF_BASE", 0.01)


class TestGenerationRetry:
    def test_stream_open_retried_before_any_token(self, slow_retry):
        stream_after_retry = _FakeStream(["answer"])
        open_call = AsyncMock(side_effect=[_server_error_503(), stream_after_retry])
        client = MagicMock()
        client.aio.models.generate_content_stream = open_call
        gen_mod._get_generation_client = MagicMock(return_value=client)

        async def consume():
            return [t async for t in generate_answer_stream("Q", [])]

        out = _asyncio_run(consume())
        assert out == ["answer"]
        assert open_call.await_count == 2

    def test_mid_stream_failure_not_retried(self, slow_retry):
        failing = _FailingStream("partial ", _server_error_503())
        open_call = AsyncMock(return_value=failing)
        client = MagicMock()
        client.aio.models.generate_content_stream = open_call
        gen_mod._get_generation_client = MagicMock(return_value=client)

        async def consume():
            out = []
            try:
                async for t in generate_answer_stream("Q", []):
                    out.append(t)
            except Exception:
                pass
            return out

        out = _asyncio_run(consume())
        assert out == ["partial "]          # partial stream surfaced
        assert open_call.await_count == 1   # no re-open (would duplicate text)

    def test_non_retryable_error_propagates_immediately(self, slow_retry):
        invalid = RuntimeError("400: bad request")
        open_call = AsyncMock(side_effect=invalid)
        client = MagicMock()
        client.aio.models.generate_content_stream = open_call
        gen_mod._get_generation_client = MagicMock(return_value=client)

        async def consume():
            return [t async for t in generate_answer_stream("Q", [])]

        with pytest.raises(RuntimeError, match="400"):
            _asyncio_run(consume())
        assert open_call.await_count == 1


def _asyncio_run(awaitable):
    """Run one async block against a fresh event loop."""
    import asyncio
    return asyncio.new_event_loop().run_until_complete(awaitable)