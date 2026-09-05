import os
import hashlib
from typing import List, Tuple

from app.services.rag.schemas import PageWord, TextChunk

# Load chunking parameters from environment (fallback defaults match spec)
_RAG_CHUNK_WORDS = int(os.getenv("RAG_CHUNK_WORDS", "800"))
_RAG_CHUNK_OVERLAP_WORDS = int(os.getenv("RAG_CHUNK_OVERLAP_WORDS", "100"))

# ---------------------------------------------------------------------------
# Step 6 – Build a page‑aware word stream
# ---------------------------------------------------------------------------

def build_word_stream(pages: List[Tuple[int, str]]) -> List[PageWord]:
    """Convert a list of ``(page_number, text)`` tuples into a flat list of
    :class:`PageWord` objects.

    * ``page_number`` is 1‑based (as required by the project spec).
    * Words are identified using a regular expression that matches any
      non‑whitespace sequence.
    * ``absolute_word_index`` is the zero‑based index of the word in the final
      stream.
    """
    import re

    WORD_PATTERN = re.compile(r"\S+")
    words: List[PageWord] = []
    for page_number, text in pages:
        for match in WORD_PATTERN.finditer(text):
            words.append(
                PageWord(
                    text=match.group(0),
                    page_number=page_number,
                    absolute_word_index=len(words),
                )
            )
    return words

# ---------------------------------------------------------------------------
# Step 7 – Chunk the word stream into overlapping text chunks
# ---------------------------------------------------------------------------

def _text_checksum(text: str) -> str:
    """Return a SHA‑256 hex digest of *text*.

    ``text`` is expected to be the cleaned, joined string for a chunk. Using a
    cryptographic hash guarantees a stable identifier across runs and avoids
    collisions that a built‑in ``hash()`` could produce on different interpreter
    sessions.
    """
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def chunk_words(words: List[PageWord]) -> List[TextChunk]:
    """Create overlapping ``TextChunk`` objects from a flat word stream.

    The algorithm uses a sliding window of size ``_RAG_CHUNK_WORDS`` with an
    overlap of ``_RAG_CHUNK_OVERLAP_WORDS`` words. For each chunk we:

    1. Determine the slice of ``PageWord`` objects.
    2. Collapse the word texts into a single string (joined by spaces).
    3. Compute ``word_start`` / ``word_end`` (inclusive indices).
    4. Derive ``page_start`` / ``page_end`` from the first/last words in the
       slice.
    5. Compute ``word_count`` and ``text_checksum``.
    """
    if not words:
        return []

    chunk_size = _RAG_CHUNK_WORDS
    overlap = _RAG_CHUNK_OVERLAP_WORDS
    step = chunk_size - overlap

    chunks: List[TextChunk] = []
    total = len(words)
    chunk_index = 0
    for start in range(0, total, step):
        end = min(start + chunk_size, total)
        slice_words = words[start:end]
        if not slice_words:
            break
        clean_text = " ".join(w.text for w in slice_words)
        chunks.append(
            TextChunk(
                chunk_index=chunk_index,
                clean_text=clean_text,
                page_start=slice_words[0].page_number,
                page_end=slice_words[-1].page_number,
                word_start=slice_words[0].absolute_word_index,
                word_end=slice_words[-1].absolute_word_index,
                word_count=len(slice_words),
                text_checksum=_text_checksum(clean_text),
            )
        )
        chunk_index += 1
        if end == total:
            break
    return chunks
