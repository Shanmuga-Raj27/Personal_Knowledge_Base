"""
backend/app/services/rag/extractors/__init__.py

Modular document format extractors for RAG ingestion.
All extractors produce list[ExtractedPage(page_number, text)].
"""
from app.services.rag.extractors.text_extractor import extract_text_pages
from app.services.rag.extractors.tabular_extractor import extract_csv_pages, extract_excel_pages
from app.services.rag.extractors.docx_extractor import extract_docx_pages

__all__ = [
    "extract_text_pages",
    "extract_csv_pages",
    "extract_excel_pages",
    "extract_docx_pages",
]
