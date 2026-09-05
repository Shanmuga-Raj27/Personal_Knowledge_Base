"""
backend/app/services/rag/pdf_extractor.py

In-memory PDF text extraction using modern PyMuPDF (pymupdf package).
"""
import pymupdf

from app.services.rag.schemas import ExtractedPage


class PdfExtractionError(Exception):
    """Raised when PDF text extraction fails or PDF contains no extractable text."""
    pass


def extract_pdf_pages(pdf_bytes: bytes) -> list[ExtractedPage]:
    """
    Extract page-by-page text from in-memory PDF bytes using PyMuPDF.

    :param pdf_bytes: Raw bytes of the PDF file.
    :return: List of ExtractedPage DTOs with 1-based page numbers.
    :raises PdfExtractionError: If bytes are empty, invalid, or contain no extractable text.
    """
    if not pdf_bytes:
        raise PdfExtractionError("PDF is empty.")

    doc = None
    try:
        doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
        pages: list[ExtractedPage] = []
        total_text_length = 0

        for page_index in range(doc.page_count):
            page = doc.load_page(page_index)
            text = page.get_text("text") or ""
            total_text_length += len(text.strip())
            pages.append(
                ExtractedPage(
                    page_number=page_index + 1,
                    text=text,
                )
            )

        if total_text_length == 0:
            raise PdfExtractionError("NO_EXTRACTABLE_TEXT")

        return pages
    except PdfExtractionError:
        raise
    except Exception as exc:
        raise PdfExtractionError("Failed to extract text from PDF.") from exc
    finally:
        if doc is not None:
            doc.close()
