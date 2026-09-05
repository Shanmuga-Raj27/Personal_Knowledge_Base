"""
backend/tests/unit/services/rag/test_schemas.py

Unit tests for internal RAG DTO dataclasses (ExtractedPage, PageWord, TextChunk).
"""
from dataclasses import FrozenInstanceError
import pytest

from app.services.rag.schemas import ExtractedPage, PageWord, TextChunk


def test_extracted_page_dataclass():
    page = ExtractedPage(page_number=1, text="Hello world")
    assert page.page_number == 1
    assert page.text == "Hello world"

    with pytest.raises(FrozenInstanceError):
        page.page_number = 2  # type: ignore


def test_page_word_dataclass():
    word = PageWord(text="test", page_number=3, absolute_word_index=42)
    assert word.text == "test"
    assert word.page_number == 3
    assert word.absolute_word_index == 42

    with pytest.raises(FrozenInstanceError):
        word.text = "modified"  # type: ignore


def test_text_chunk_dataclass():
    chunk = TextChunk(
        chunk_index=0,
        clean_text="Sample chunk content.",
        page_start=1,
        page_end=2,
        word_start=0,
        word_end=150,
        word_count=151,
        text_checksum="a1b2c3d4e5f6",
    )
    assert chunk.chunk_index == 0
    assert chunk.clean_text == "Sample chunk content."
    assert chunk.page_start == 1
    assert chunk.page_end == 2
    assert chunk.word_start == 0
    assert chunk.word_end == 150
    assert chunk.word_count == 151
    assert chunk.text_checksum == "a1b2c3d4e5f6"

    with pytest.raises(FrozenInstanceError):
        chunk.clean_text = "new text"  # type: ignore
