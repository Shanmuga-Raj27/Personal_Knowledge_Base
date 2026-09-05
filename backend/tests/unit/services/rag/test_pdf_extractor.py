"""
backend/tests/unit/services/rag/test_pdf_extractor.py

Unit tests for PyMuPDF PDF page extractor.
"""
from unittest.mock import MagicMock, patch
import pymupdf
import pytest

from app.services.rag.pdf_extractor import PdfExtractionError, extract_pdf_pages


def create_sample_pdf_bytes(pages_text: list[str]) -> bytes:
    """Helper to generate in-memory PDF bytes with given page texts using PyMuPDF."""
    doc = pymupdf.open()
    for text in pages_text:
        page = doc.new_page()
        if text:
            page.insert_text((50, 50), text)
    pdf_bytes = doc.tobytes()
    doc.close()
    return pdf_bytes


def test_extract_pdf_pages_success():
    sample_bytes = create_sample_pdf_bytes([
        "Page one content for testing.",
        "Page two content for testing.",
    ])

    extracted = extract_pdf_pages(sample_bytes)

    assert len(extracted) == 2
    assert extracted[0].page_number == 1
    assert "Page one content" in extracted[0].text
    assert extracted[1].page_number == 2
    assert "Page two content" in extracted[1].text


def test_extract_pdf_pages_empty_bytes():
    with pytest.raises(PdfExtractionError, match="PDF is empty"):
        extract_pdf_pages(b"")


def test_extract_pdf_pages_invalid_bytes():
    with pytest.raises(PdfExtractionError, match="Failed to extract text from PDF"):
        extract_pdf_pages(b"not a valid pdf content")


def test_extract_pdf_pages_scanned_pdf_no_text():
    # PDF with blank pages (0 extractable text)
    blank_pdf_bytes = create_sample_pdf_bytes(["", ""])

    with pytest.raises(PdfExtractionError, match="NO_EXTRACTABLE_TEXT"):
        extract_pdf_pages(blank_pdf_bytes)


def test_extract_pdf_pages_closes_doc_on_error():
    mock_doc = MagicMock()
    mock_doc.page_count = 1
    mock_doc.load_page.side_effect = RuntimeError("Unexpected load error")

    with patch("pymupdf.open", return_value=mock_doc):
        with pytest.raises(PdfExtractionError, match="Failed to extract text from PDF"):
            extract_pdf_pages(b"dummy pdf bytes")

    mock_doc.close.assert_called_once()
