"""
backend/app/services/rag/text_cleaner.py

Text normalization and structural repeated header/footer margin stripping for PDF text.
"""
from collections import Counter
from math import ceil
import re
import unicodedata

from app.services.rag.schemas import ExtractedPage

CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
HORIZONTAL_SPACE = re.compile(r"[ \t\f\v]+")
MANY_BLANK_LINES = re.compile(r"\n{3,}")


def normalize_text(text: str) -> str:
    """
    Normalize messy raw PDF text.

    - Unicode NFKC compatibility normalization
    - Line endings unified to \\n
    - Non-breaking spaces converted to ' '
    - Control characters stripped
    - Repeated horizontal spaces and per-line leading/trailing spaces stripped
    - Excessive blank lines collapsed to double newlines
    """
    text = unicodedata.normalize("NFKC", text or "")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = text.replace("\u00a0", " ")
    text = CONTROL_CHARS.sub("", text)

    lines: list[str] = []
    for line in text.split("\n"):
        cleaned = HORIZONTAL_SPACE.sub(" ", line).strip()
        lines.append(cleaned)

    text = "\n".join(lines)
    text = MANY_BLANK_LINES.sub("\n\n", text)
    return text.strip()


def page_lines(text: str) -> list[str]:
    """Split text into non-empty stripped line strings."""
    return [line for line in text.split("\n") if line.strip()]


def strip_repeated_margins(pages: list[list[str]]) -> list[list[str]]:
    """
    Detect and remove repeated candidate header/footer margin lines across pages.

    Threshold formula: max(3, ceil(len(pages) * 0.6))
    Only lines appearing in at least threshold number of pages are stripped.
    """
    if not pages:
        return []

    threshold = max(3, ceil(len(pages) * 0.6))

    candidates: list[str] = []
    for lines in pages:
        if lines:
            candidates.append(lines[0].strip().casefold())
            candidates.append(lines[-1].strip().casefold())

    counts = Counter(candidates)
    repeated = {line for line, count in counts.items() if count >= threshold}

    cleaned_pages: list[list[str]] = []
    for lines in pages:
        cleaned_pages.append([
            line for line in lines
            if line.strip().casefold() not in repeated
        ])
    return cleaned_pages


def clean_extracted_pages(pages: list[ExtractedPage]) -> list[ExtractedPage]:
    """
    High-level pipeline function to normalize text and strip repeated margin headers/footers
    from a list of ExtractedPage DTOs.
    """
    if not pages:
        return []

    # Step 1: Normalize text per page and extract non-empty lines
    normalized_pages_lines: list[list[str]] = []
    for page in pages:
        norm_text = normalize_text(page.text)
        normalized_pages_lines.append(page_lines(norm_text))

    # Step 2: Strip repeated header/footer margins across pages
    cleaned_pages_lines = strip_repeated_margins(normalized_pages_lines)

    # Step 3: Re-assemble ExtractedPage DTOs maintaining page numbers
    result: list[ExtractedPage] = []
    for orig_page, lines in zip(pages, cleaned_pages_lines):
        result.append(
            ExtractedPage(
                page_number=orig_page.page_number,
                text="\n".join(lines),
            )
        )
    return result
