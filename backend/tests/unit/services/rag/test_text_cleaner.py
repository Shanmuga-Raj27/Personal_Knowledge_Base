"""
backend/tests/unit/services/rag/test_text_cleaner.py

Unit tests for text normalization and repeated header/footer margin stripping.
"""
from app.services.rag.schemas import ExtractedPage
from app.services.rag.text_cleaner import (
    clean_extracted_pages,
    normalize_text,
    page_lines,
    strip_repeated_margins,
)


def test_normalize_text_unicode_and_whitespace():
    raw_text = "  Chapter\t1\r\n\r\n\r\n\r\nThis\u00a0is   text.\x07  "
    cleaned = normalize_text(raw_text)
    assert cleaned == "Chapter 1\n\nThis is text."


def test_normalize_text_empty():
    assert normalize_text("") == ""
    assert normalize_text("   ") == ""


def test_page_lines():
    text = "Line 1\n  \nLine 2\n\t\nLine 3"
    lines = page_lines(text)
    assert lines == ["Line 1", "Line 2", "Line 3"]


def test_strip_repeated_margins_below_threshold():
    # 2 pages -> threshold = max(3, ceil(2 * 0.6)) = 3
    # Candidate headers/footers appear 2 times (< 3 threshold), so none stripped
    pages = [
        ["Project Architecture", "Intro text", "Page 1"],
        ["Project Architecture", "More content", "Page 2"],
    ]
    cleaned = strip_repeated_margins(pages)
    assert cleaned == pages


def test_strip_repeated_margins_above_threshold():
    # 5 pages -> threshold = max(3, ceil(5 * 0.6)) = 3
    # "Project Architecture" header appears 4 times (>= 3 threshold) -> stripped
    # Footer "Page X" is distinct per page -> preserved
    pages = [
        ["Project Architecture", "Content page 1", "Page 1"],
        ["Project Architecture", "Content page 2", "Page 2"],
        ["Project Architecture", "Content page 3", "Page 3"],
        ["Project Architecture", "Content page 4", "Page 4"],
        ["Different Title", "Content page 5", "Page 5"],
    ]
    cleaned = strip_repeated_margins(pages)
    assert cleaned == [
        ["Content page 1", "Page 1"],
        ["Content page 2", "Page 2"],
        ["Content page 3", "Page 3"],
        ["Content page 4", "Page 4"],
        ["Different Title", "Content page 5", "Page 5"],
    ]


def test_strip_repeated_margins_case_insensitive():
    # 4 pages -> threshold = max(3, ceil(4 * 0.6)) = 3
    # Header appears with varying case: "PROJECT ARCHITECTURE", "project architecture"
    pages = [
        ["PROJECT ARCHITECTURE", "Content page 1", "Footer A"],
        ["project architecture", "Content page 2", "Footer B"],
        ["Project Architecture", "Content page 3", "Footer C"],
        ["Another Header", "Content page 4", "Footer D"],
    ]
    cleaned = strip_repeated_margins(pages)
    assert cleaned == [
        ["Content page 1", "Footer A"],
        ["Content page 2", "Footer B"],
        ["Content page 3", "Footer C"],
        ["Another Header", "Content page 4", "Footer D"],
    ]



def test_clean_extracted_pages_pipeline():
    raw_pages = [
        ExtractedPage(page_number=1, text="  HEADER TITLE  \r\n\r\n  Body text on page 1.  \r\nFOOTER"),
        ExtractedPage(page_number=2, text="HEADER TITLE\nBody text on page 2.\nFOOTER"),
        ExtractedPage(page_number=3, text="HEADER TITLE\nBody text on page 3.\nFOOTER"),
    ]

    cleaned = clean_extracted_pages(raw_pages)

    assert len(cleaned) == 3
    assert cleaned[0].page_number == 1
    assert cleaned[0].text == "Body text on page 1."
    assert cleaned[1].page_number == 2
    assert cleaned[1].text == "Body text on page 2."
    assert cleaned[2].page_number == 3
    assert cleaned[2].text == "Body text on page 3."
