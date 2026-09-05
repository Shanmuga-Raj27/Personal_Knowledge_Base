"""
backend/app/services/rag/document_processor.py

Orchestration service for the RAG Phase 2 pipeline.

Connects S3 byte reader → PDF extraction → text cleaning → word stream → chunking
into a single callable that returns a ProcessedDocument ready for Phase 3 persistence.

Does NOT write to disk, does NOT persist to MySQL, does NOT call Qdrant or Gemini.
"""
from dataclasses import dataclass
import logging

from app.core.config import settings
from app.services.AWS.s3_service import read_object_bytes_limited
from app.services.rag.chunker import build_word_stream, chunk_words
from app.services.rag.pdf_extractor import PdfExtractionError, extract_pdf_pages
from app.services.rag.schemas import TextChunk
from app.services.rag.text_cleaner import (
    clean_extracted_pages,
    normalize_text,
    page_lines,
    strip_repeated_margins,
)

logger = logging.getLogger(__name__)


class NoExtractableTextError(Exception):
    """Raised when a PDF has no usable text layer (e.g. scanned/image-only PDF)."""


@dataclass(frozen=True)
class ProcessedDocument:
    """Output of Phase 2 pipeline — in-memory only, ready for Phase 3 MySQL persistence."""

    page_count: int
    extracted_word_count: int
    chunks: list[TextChunk]


def process_pdf_from_storage(s3_key: str) -> ProcessedDocument:
    """Run the full Phase 2 pipeline for a PDF object stored in S3/B2.

    Flow:
        1. Read bounded PDF bytes from S3 (max = settings.RAG_MAX_PDF_BYTES).
        2. Extract text page by page with PyMuPDF (no local disk writes).
        3. Normalize each page's text (NFKC, whitespace cleanup, control chars).
        4. Strip structural repeated header/footer margins across pages.
        5. Build a flat page-aware word stream.
        6. Emit overlapping 800/100-word chunks with SHA-256 checksums.

    :param s3_key: The S3/B2 object key for the uploaded PDF.
    :returns: :class:`ProcessedDocument` with page_count, extracted_word_count, chunks.
    :raises FileNotFoundError: If the object does not exist in storage.
    :raises ValueError: If the object exceeds RAG_MAX_PDF_BYTES.
    :raises PdfExtractionError: If PyMuPDF cannot parse the PDF bytes.
    :raises NoExtractableTextError: If the PDF has no text layer (scanned/image-only).
    """
    # ── Step 1: Read PDF bytes from S3 with hard size limit ─────────────────
    pdf_bytes = read_object_bytes_limited(
        key=s3_key,
        max_bytes=settings.RAG_MAX_PDF_BYTES,
    )
    logger.debug("RAG Phase 2: read %d bytes for key=%s", len(pdf_bytes), s3_key)

    # ── Step 2: Extract text page by page ────────────────────────────────────
    # PdfExtractionError propagates as-is; caller decides on retry strategy.
    raw_pages = extract_pdf_pages(pdf_bytes)
    logger.debug("RAG Phase 2: extracted %d pages", len(raw_pages))

    # ── Step 3+4: Normalize and strip repeated margins ───────────────────────
    # clean_extracted_pages runs normalize_text → page_lines → strip_repeated_margins
    # and returns the same ExtractedPage DTOs with cleaned text.
    cleaned_pages = clean_extracted_pages(raw_pages)

    # ── Step 5: Build page-aware word stream ─────────────────────────────────
    page_tuples = [(p.page_number, p.text) for p in cleaned_pages]
    words = build_word_stream(page_tuples)

    if not words:
        logger.info("RAG Phase 2: no extractable words for key=%s (scanned/image-only)", s3_key)
        raise NoExtractableTextError(
            f"PDF '{s3_key}' has no extractable text layer. "
            "It may be a scanned or image-only document."
        )

    # ── Step 6: Generate overlapping chunks ──────────────────────────────────
    chunks = chunk_words(words)
    logger.debug(
        "RAG Phase 2: produced %d chunks from %d words for key=%s",
        len(chunks),
        len(words),
        s3_key,
    )

    return ProcessedDocument(
        page_count=len(raw_pages),
        extracted_word_count=len(words),
        chunks=chunks,
    )
