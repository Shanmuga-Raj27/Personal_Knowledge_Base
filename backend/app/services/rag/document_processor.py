"""
backend/app/services/rag/document_processor.py

Orchestration service for the RAG Phase 2 pipeline.

Connects S3 byte reader → PDF extraction → text cleaning → word stream → chunking
into a single callable that returns a ProcessedDocument ready for Phase 3 persistence.

Does NOT write to disk, does NOT persist to MySQL, does NOT call Qdrant or Gemini.
"""
from dataclasses import dataclass
import logging
from pathlib import Path

from app.core.config import settings
from app.services.AWS.s3_service import read_object_bytes_limited
from app.services.rag.chunker import build_word_stream, chunk_words
from app.services.rag.pdf_extractor import PdfExtractionError, extract_pdf_pages
from app.services.rag.extractors import (
    extract_text_pages,
    extract_csv_pages,
    extract_excel_pages,
    extract_docx_pages,
)
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


def process_document_from_storage(s3_key: str, filename: str = "") -> ProcessedDocument:
    """Run the multi-format extraction and chunking pipeline for any supported document.

    Routes to:
        - .pdf: PyMuPDF extractor
        - .md, .txt, .log, .rtf: TextExtractor
        - .csv, .tsv: TabularExtractor (CSV)
        - .xlsx, .xls: TabularExtractor (Excel)
        - .docx, .doc: DocxExtractor (Word)
    """
    raw_bytes = read_object_bytes_limited(
        key=s3_key,
        max_bytes=settings.RAG_MAX_PDF_BYTES,
    )
    logger.debug("RAG Ingestion: read %d bytes for key=%s", len(raw_bytes), s3_key)

    name = filename or s3_key
    ext = Path(name).suffix.lower()

    if ext == ".pdf":
        raw_pages = extract_pdf_pages(raw_bytes)
    elif ext in (".md", ".txt", ".log", ".rtf") or not ext:
        raw_pages = extract_text_pages(raw_bytes, filename=name)
    elif ext in (".csv", ".tsv"):
        raw_pages = extract_csv_pages(raw_bytes, filename=name)
    elif ext in (".xlsx", ".xls"):
        raw_pages = extract_excel_pages(raw_bytes, filename=name)
    elif ext in (".docx", ".doc"):
        raw_pages = extract_docx_pages(raw_bytes, filename=name)
    else:
        # Fallback to text extractor for any plain human-readable extension
        raw_pages = extract_text_pages(raw_bytes, filename=name)

    logger.debug("RAG Ingestion: extracted %d pages for key=%s (ext=%s)", len(raw_pages), s3_key, ext)

    if not raw_pages:
        raise NoExtractableTextError(
            f"Document '{name}' has no extractable text layer."
        )

    cleaned_pages = clean_extracted_pages(raw_pages)
    page_tuples = [(p.page_number, p.text) for p in cleaned_pages]
    words = build_word_stream(page_tuples)

    if not words:
        logger.info("RAG Ingestion: no extractable words for key=%s", s3_key)
        raise NoExtractableTextError(
            f"Document '{name}' has no extractable words."
        )

    chunks = chunk_words(words)
    logger.debug(
        "RAG Ingestion: produced %d chunks from %d words for key=%s",
        len(chunks),
        len(words),
        s3_key,
    )

    return ProcessedDocument(
        page_count=len(raw_pages),
        extracted_word_count=len(words),
        chunks=chunks,
    )


def process_pdf_from_storage(s3_key: str) -> ProcessedDocument:
    """Backward compatibility alias for process_document_from_storage."""
    return process_document_from_storage(s3_key=s3_key, filename=s3_key)
