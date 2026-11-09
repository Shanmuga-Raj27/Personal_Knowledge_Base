"""
backend/app/services/rag/extractors/text_extractor.py

Phase 1 Extractor: Plain text, Markdown, Logs, and basic RTF files.
Zero external dependencies (pure Python standard library).
"""
import re
from app.services.rag.schemas import ExtractedPage


def decode_text_bytes(raw_bytes: bytes) -> str:
    """Decode raw bytes into a string using multi-tier encoding fallback."""
    for encoding in ("utf-8", "utf-8-sig", "cp1252", "latin-1"):
        try:
            return raw_bytes.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw_bytes.decode("utf-8", errors="replace")


def _strip_rtf_formatting(text: str) -> str:
    """Strip basic RTF tags and control words if text is RTF."""
    if text.startswith(r"{\rtf"):
        # Remove RTF control words (\par, \b, \i, \fonttbl, etc.)
        text = re.sub(r"\\[a-zA-Z]+(-?\d+)? ?|\\[{}\\]", " ", text)
        text = re.sub(r"[{}]", "", text)
    return text


def extract_text_pages(raw_bytes: bytes, filename: str = "") -> list[ExtractedPage]:
    """Extract page-by-page text from text-based documents.

    - For Markdown (.md): Partitions by heading hierarchy (# , ## ).
    - For Plain Text (.txt, .log, .rtf): Partitions into ~600-word blocks.
    """
    text = decode_text_bytes(raw_bytes).strip()
    if not text:
        return []

    text = _strip_rtf_formatting(text)
    name_lower = (filename or "").lower()

    # Markdown structure: partition by section headers (#, ##, ###)
    if name_lower.endswith(".md"):
        header_pattern = re.compile(r"(?=^#{1,3}\s+)", re.MULTILINE)
        raw_sections = [s.strip() for s in header_pattern.split(text) if s.strip()]
        if len(raw_sections) > 1:
            pages: list[ExtractedPage] = []
            for section in raw_sections:
                words = section.split()
                # If a section is very long (> 800 words), sub-chunk into ~600-word virtual pages
                if len(words) > 800:
                    for i in range(0, len(words), 600):
                        sub_text = " ".join(words[i : i + 600])
                        pages.append(ExtractedPage(page_number=len(pages) + 1, text=sub_text))
                else:
                    pages.append(ExtractedPage(page_number=len(pages) + 1, text=section))
            return pages

    # Plain text / log / single markdown: partition into ~600-word virtual pages
    words = text.split()
    block_size = 600
    pages = []
    for i in range(0, len(words), block_size):
        chunk_text = " ".join(words[i : i + block_size])
        pages.append(ExtractedPage(page_number=len(pages) + 1, text=chunk_text))

    return pages
