"""
backend/tests/unit/services/rag/test_chunker.py

Unit tests for page-aware word stream building and overlapping chunk generation.
"""
import pytest

from app.services.rag.chunker import build_word_stream, chunk_words
from app.services.rag.schemas import PageWord, TextChunk


# ---------------------------------------------------------------------------
# build_word_stream
# ---------------------------------------------------------------------------


def test_build_word_stream_empty_input():
    assert build_word_stream([]) == []


def test_build_word_stream_single_page():
    pages = [(1, "hello world foo")]
    words = build_word_stream(pages)

    assert len(words) == 3
    assert words[0] == PageWord(text="hello", page_number=1, absolute_word_index=0)
    assert words[1] == PageWord(text="world", page_number=1, absolute_word_index=1)
    assert words[2] == PageWord(text="foo", page_number=1, absolute_word_index=2)


def test_build_word_stream_multiple_pages():
    pages = [(1, "alpha beta"), (2, "gamma delta epsilon")]
    words = build_word_stream(pages)

    assert len(words) == 5
    assert words[0].page_number == 1
    assert words[2].page_number == 2
    assert words[4].page_number == 2
    # absolute indexes are contiguous across pages
    for i, word in enumerate(words):
        assert word.absolute_word_index == i


def test_build_word_stream_whitespace_only_page():
    pages = [(1, "  \n\t  "), (2, "real word")]
    words = build_word_stream(pages)
    assert len(words) == 2
    assert words[0].page_number == 2


def test_build_word_stream_page_number_preserved():
    pages = [(3, "only word")]
    words = build_word_stream(pages)
    assert words[0].page_number == 3


# ---------------------------------------------------------------------------
# chunk_words — edge cases from spec section 12.2
# ---------------------------------------------------------------------------


def _make_words(n: int, page_number: int = 1) -> list[PageWord]:
    """Helper: generate n PageWord objects all on the same page."""
    return [
        PageWord(text=f"w{i}", page_number=page_number, absolute_word_index=i)
        for i in range(n)
    ]


def test_chunk_words_empty():
    assert chunk_words([]) == []


def test_chunk_words_single_word():
    words = _make_words(1)
    chunks = chunk_words(words)
    assert len(chunks) == 1
    assert chunks[0].chunk_index == 0
    assert chunks[0].word_count == 1
    assert chunks[0].word_start == 0
    assert chunks[0].word_end == 0


def test_chunk_words_799_words():
    words = _make_words(799)
    chunks = chunk_words(words)
    assert len(chunks) == 1
    assert chunks[0].word_count == 799


def test_chunk_words_800_words():
    words = _make_words(800)
    chunks = chunk_words(words)
    assert len(chunks) == 1
    assert chunks[0].word_count == 800
    assert chunks[0].word_start == 0
    assert chunks[0].word_end == 799


def test_chunk_words_801_words():
    """801 words must produce two chunks: [0-799] and [700-800]."""
    words = _make_words(801)
    chunks = chunk_words(words)
    assert len(chunks) == 2

    c0 = chunks[0]
    assert c0.chunk_index == 0
    assert c0.word_start == 0
    assert c0.word_end == 799
    assert c0.word_count == 800

    c1 = chunks[1]
    assert c1.chunk_index == 1
    assert c1.word_start == 700
    assert c1.word_end == 800
    assert c1.word_count == 101


def test_chunk_words_1500_words():
    """1500 words → 2 chunks: [0-799] and [700-1499]."""
    words = _make_words(1500)
    chunks = chunk_words(words)
    assert len(chunks) == 2
    assert chunks[0].word_start == 0
    assert chunks[0].word_end == 799
    assert chunks[1].word_start == 700
    assert chunks[1].word_end == 1499


def test_chunk_words_indexes_start_at_zero():
    words = _make_words(900)
    chunks = chunk_words(words)
    assert chunks[0].chunk_index == 0
    assert chunks[1].chunk_index == 1


def test_chunk_words_second_chunk_starts_at_word_700():
    words = _make_words(1000)
    chunks = chunk_words(words)
    # step = 800 - 100 = 700
    assert chunks[1].word_start == 700


def test_chunk_words_checksum_is_stable():
    words = _make_words(800)
    chunks_a = chunk_words(words)
    chunks_b = chunk_words(words)
    assert chunks_a[0].text_checksum == chunks_b[0].text_checksum


def test_chunk_words_checksum_is_sha256():
    """Checksum should be 64-character hex string (SHA-256)."""
    words = _make_words(10)
    chunks = chunk_words(words)
    assert len(chunks[0].text_checksum) == 64
    assert all(c in "0123456789abcdef" for c in chunks[0].text_checksum)


def test_chunk_words_page_range_single_page():
    words = _make_words(800, page_number=3)
    chunks = chunk_words(words)
    assert chunks[0].page_start == 3
    assert chunks[0].page_end == 3


def test_chunk_words_page_range_across_pages():
    """Words span page 1 and page 2; chunk should record both."""
    half = 400
    words_p1 = [PageWord(text=f"a{i}", page_number=1, absolute_word_index=i) for i in range(half)]
    words_p2 = [PageWord(text=f"b{i}", page_number=2, absolute_word_index=half + i) for i in range(half)]
    words = words_p1 + words_p2

    chunks = chunk_words(words)
    assert chunks[0].page_start == 1
    assert chunks[0].page_end == 2


def test_chunk_words_clean_text_is_joined_by_spaces():
    pages = [(1, "alpha beta gamma")]
    words = build_word_stream(pages)
    chunks = chunk_words(words)
    assert chunks[0].clean_text == "alpha beta gamma"
