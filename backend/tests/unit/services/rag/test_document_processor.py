"""
backend/tests/unit/services/rag/test_document_processor.py

Unit tests for the RAG Phase 2 document orchestration pipeline.

All external I/O (S3, PyMuPDF) is mocked so tests remain fast and isolated.
"""
from unittest.mock import patch, MagicMock
import pytest

from app.services.rag.document_processor import (
    NoExtractableTextError,
    ProcessedDocument,
    process_pdf_from_storage,
)
from app.services.rag.pdf_extractor import PdfExtractionError
from app.services.rag.schemas import ExtractedPage


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_page(number: int, text: str) -> ExtractedPage:
    return ExtractedPage(page_number=number, text=text)


def _patch_s3(pdf_bytes: bytes):
    return patch(
        "app.services.rag.document_processor.read_object_bytes_limited",
        return_value=pdf_bytes,
    )


def _patch_extractor(pages: list[ExtractedPage]):
    return patch(
        "app.services.rag.document_processor.extract_pdf_pages",
        return_value=pages,
    )


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


def test_process_pdf_returns_processed_document():
    """Full happy path: S3 bytes → pages → words → chunks → ProcessedDocument."""
    fake_pages = [
        _make_page(1, " ".join(f"word{i}" for i in range(400))),
        _make_page(2, " ".join(f"word{i}" for i in range(400, 900))),
    ]

    with _patch_s3(b"fake-pdf-bytes"), _patch_extractor(fake_pages):
        result = process_pdf_from_storage("uploads/test.pdf")

    assert isinstance(result, ProcessedDocument)
    assert result.page_count == 2
    assert result.extracted_word_count == 900
    # 900 words → 2 chunks (0-799, 700-899)
    assert len(result.chunks) == 2
    assert result.chunks[0].chunk_index == 0
    assert result.chunks[1].chunk_index == 1


def test_process_pdf_single_small_document():
    """A small PDF with fewer than 800 words should produce exactly one chunk."""
    fake_pages = [_make_page(1, "The quick brown fox jumps over the lazy dog")]

    with _patch_s3(b"tiny"), _patch_extractor(fake_pages):
        result = process_pdf_from_storage("uploads/tiny.pdf")

    assert result.page_count == 1
    assert len(result.chunks) == 1
    assert result.chunks[0].page_start == 1
    assert result.chunks[0].page_end == 1


def test_process_pdf_chunk_has_correct_fields():
    """Spot-check that chunk DTOs carry all required metadata fields."""
    text = " ".join(f"w{i}" for i in range(100))
    fake_pages = [_make_page(1, text)]

    with _patch_s3(b"fake"), _patch_extractor(fake_pages):
        result = process_pdf_from_storage("uploads/doc.pdf")

    chunk = result.chunks[0]
    assert chunk.chunk_index == 0
    assert chunk.page_start == 1
    assert chunk.page_end == 1
    assert chunk.word_count == 100
    assert len(chunk.text_checksum) == 64  # SHA-256 hex


# ---------------------------------------------------------------------------
# Error propagation
# ---------------------------------------------------------------------------


def test_process_pdf_file_not_found_propagates():
    with patch(
        "app.services.rag.document_processor.read_object_bytes_limited",
        side_effect=FileNotFoundError("Object not found"),
    ):
        with pytest.raises(FileNotFoundError, match="Object not found"):
            process_pdf_from_storage("uploads/missing.pdf")


def test_process_pdf_too_large_propagates():
    with patch(
        "app.services.rag.document_processor.read_object_bytes_limited",
        side_effect=ValueError("Object is too large"),
    ):
        with pytest.raises(ValueError, match="too large"):
            process_pdf_from_storage("uploads/big.pdf")


def test_process_pdf_extraction_error_propagates():
    with _patch_s3(b"bad-bytes"), patch(
        "app.services.rag.document_processor.extract_pdf_pages",
        side_effect=PdfExtractionError("Failed to parse"),
    ):
        with pytest.raises(PdfExtractionError, match="Failed to parse"):
            process_pdf_from_storage("uploads/corrupt.pdf")


def test_process_pdf_scanned_pdf_raises_no_extractable_text():
    """Pages with only whitespace text should raise NoExtractableTextError."""
    blank_pages = [
        _make_page(1, "   \n   "),
        _make_page(2, "\t\t"),
    ]

    with _patch_s3(b"scanned"), _patch_extractor(blank_pages):
        with pytest.raises(NoExtractableTextError):
            process_pdf_from_storage("uploads/scanned.pdf")


# ---------------------------------------------------------------------------
# Chunk correctness
# ---------------------------------------------------------------------------


def test_process_pdf_chunks_have_stable_checksums():
    """Running the same input twice must produce identical checksums (deterministic)."""
    text = " ".join(f"stable{i}" for i in range(200))
    fake_pages = [_make_page(1, text)]

    with _patch_s3(b"fake"), _patch_extractor(fake_pages):
        result_a = process_pdf_from_storage("uploads/stable.pdf")
    with _patch_s3(b"fake"), _patch_extractor(fake_pages):
        result_b = process_pdf_from_storage("uploads/stable.pdf")

    assert result_a.chunks[0].text_checksum == result_b.chunks[0].text_checksum


def test_process_pdf_page_count_matches_raw_extracted_pages():
    """page_count must reflect the number of raw pages, not cleaned pages."""
    # Even after cleaning, page_count is taken from raw extraction.
    pages = [_make_page(i, f"content page {i}") for i in range(1, 6)]

    with _patch_s3(b"five-pages"), _patch_extractor(pages):
        result = process_pdf_from_storage("uploads/fivepages.pdf")

    assert result.page_count == 5
