# Multi-Format Document Ingestion & RAG Architecture Plan

## 1. Technical Audit & System Overview

This document specifies the technical architecture to upgrade the Personal Knowledge Base RAG pipeline from PDF-only ingestion to all common human-readable document formats (`.md`, `.txt`, `.docx`, `.doc`, `.csv`, `.xlsx`, `.xls`).

### 1.1 Alignment with Current Production Stack

An audit of the codebase confirms that this plan integrates directly into the existing architecture without breaking any downstream contracts:

| Layer | Current Codebase Implementation | Multi-Format Compatibility |
| :--- | :--- | :--- |
| **Data Contract** | `ExtractedPage(page_number: int, text: str)` in [`schemas.py`](file:///home/dell/Sun_Development/projects/Personal_Knowledge_Base/backend/app/services/rag/schemas.py#L14-L18) | **100% Compatible**. All extractors emit `list[ExtractedPage]`. |
| **Cleaning & Words** | `clean_extracted_pages()`, `build_word_stream()` in [`chunker.py`](file:///home/dell/Sun_Development/projects/Personal_Knowledge_Base/backend/app/services/rag/chunker.py#L15) | **100% Compatible**. Operates on `(page_number, text)` tuples. |
| **800-Word Chunker** | `chunk_words()` (800 words, 100 overlap, SHA-256) in [`chunker.py`](file:///home/dell/Sun_Development/projects/Personal_Knowledge_Base/backend/app/services/rag/chunker.py#L55) | **100% Compatible**. Produces `TextChunk` DTOs. |
| **MySQL Storage** | `document_chunks` table in [`db_models.py`](file:///home/dell/Sun_Development/projects/Personal_Knowledge_Base/backend/app/database/db_models.py#L156-L220) | **Zero schema migration required**. Already stores `page_start`, `page_end`, `clean_text`. |
| **Vector Engine** | Qdrant `document_chunks_v1` via [`qdrant_service.py`](file:///home/dell/Sun_Development/projects/Personal_Knowledge_Base/backend/app/services/rag/qdrant_service.py) | **Zero Qdrant changes required**. Chunks indexed with deterministic UUIDv5. |
| **Generation Stream** | Multi-model fallback with `google-genai` in [`generation.py`](file:///home/dell/Sun_Development/projects/Personal_Knowledge_Base/backend/app/services/rag/generation.py#L100-L148) | **Zero changes required**. Streams citations from retrieved source blocks. |

---

## 2. Architecture & Data Flow

```
1. S3 Storage
   │ Raw Object Bytes (Bounded by RAG_MAX_PDF_BYTES)
   ▼
2. Central Dispatcher (document_processor.py)
   │ Inspects Path(filename).suffix.lower()
   ├──────────────────┬──────────────────┬──────────────────┐
   ▼                  ▼                  ▼                  ▼
PDF Extractor     Text Extractor     Docx Extractor     Tabular Extractor
(pymupdf)         (.md, .txt)        (.docx)            (.csv, .xlsx)
   │                  │                  │                  │
   └──────────────────┴─────────┬────────┴──────────────────┘
                                │ list[ExtractedPage(page_number, text)]
                                ▼
3. Normalization & Word Stream (text_cleaner.py & chunker.py)
   │ Unicode NFKC, repeated margin filter, word stream
   ▼
4. Sliding Window Chunker (chunker.py)
   │ 800 words / 100-word overlap + SHA-256 checksums
   ▼
5. Versioned Staging (persistence.py)
   │ Writes to MySQL document_chunks as next_rag_index_version
   ▼
6. Embedding & Cutover (indexing_service.py)
   │ Gemini RETRIEVAL_DOCUMENT (768d) -> Qdrant document_chunks_v1
   ▼
7. Document Status: INDEXED
   │ File now selectable in Knowledge Base UI
```

---

## 3. Phase 1: Zero-Dependency Text & Markdown (`.md`, `.txt`, `.log`, `.rtf`)

### 3.1 Objective
Enable immediate support for Markdown and plain text files with zero external package installations. Resolves the error encountered with files like `green_technology_youtube_shorts_script.md`.

### 3.2 Technical Design
* **File Location:** `backend/app/services/rag/extractors/text_extractor.py`
* **Encoding Strategy:** Multi-stage decoding with graceful fallback:
  1. `utf-8`
  2. `utf-8-sig` (removes Windows UTF-8 byte order mark `\xef\xbb\xbf`)
  3. `cp1252` / `latin-1` (guarantees no unhandled decode exceptions on legacy files)
* **Virtual Page Mapping:**
  * **Markdown (`.md`):** Split along section boundaries (`# `, `## `). Each section maps to `page_number = N`. If no headers exist, segment every ~600 words.
  * **Plain Text (`.txt`, `.log`, `.rtf`):** Split into contiguous blocks of ~600 words to provide readable citation page numbers (`Page 1`, `Page 2`, etc.).

### 3.3 Extractor Implementation
```python
# backend/app/services/rag/extractors/text_extractor.py
import re
from app.services.rag.schemas import ExtractedPage

def decode_text_bytes(raw_bytes: bytes) -> str:
    for encoding in ("utf-8", "utf-8-sig", "cp1252", "latin-1"):
        try:
            return raw_bytes.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw_bytes.decode("utf-8", errors="replace")

def extract_text_pages(raw_bytes: bytes, filename: str) -> list[ExtractedPage]:
    text = decode_text_bytes(raw_bytes).strip()
    if not text:
        return []

    # Markdown: partition by headers
    if filename.lower().endswith(".md"):
        header_pattern = re.compile(r"(?=^#{1,3}\s+)", re.MULTILINE)
        sections = [s.strip() for s in header_pattern.split(text) if s.strip()]
        if len(sections) > 1:
            return [ExtractedPage(page_number=i + 1, text=s) for i, s in enumerate(sections)]

    # Plain text / flat markdown: segment into ~600-word blocks
    words = text.split()
    block_size = 600
    pages = []
    for i in range(0, len(words), block_size):
        chunk_text = " ".join(words[i : i + block_size])
        pages.append(ExtractedPage(page_number=len(pages) + 1, text=chunk_text))
        
    return pages
```

### 3.4 Integration Touchpoints
1. [s3_service.py](file:///home/dell/Sun_Development/projects/Personal_Knowledge_Base/backend/app/services/AWS/s3_service.py#L19-L24): Add `"text/plain"`, `"text/markdown"`, `"application/rtf"` to `ALLOWED_MIME_TYPES`.
2. [VaultPage.jsx](file:///home/dell/Sun_Development/projects/Personal_Knowledge_Base/frontend/src/pages/VaultPage.jsx#L33-L38): Add `.md`, `.txt`, `.log`, `.rtf` to `ALLOWED_EXTENSIONS`.
3. [document_processor.py](file:///home/dell/Sun_Development/projects/Personal_Knowledge_Base/backend/app/services/rag/document_processor.py): Dispatch `.md` and `.txt` to `extract_text_pages`.

---

## 4. Phase 2: Tabular & Spreadsheets (`.csv`, `.tsv`, `.xlsx`, `.xls`)

### 4.1 Objective
Allow users to query structured spreadsheets and CSV files. Solves the semantic issue where raw tabular lines lose column context in dense vector spaces.

### 4.2 Technical Design
* **File Location:** `backend/app/services/rag/extractors/tabular_extractor.py`
* **Attribute-Value Serialization:**
  Raw CSV lines like `Product,120,Active` perform poorly in vector search. The extractor serializes each row with its column headers:
  ```text
  Row 1: [Product]: Wireless Headphones | [Price]: $120 | [Status]: Active
  ```
* **Page Mapping:**
  * **Excel Workbooks (`.xlsx`, `.xls`):** Each **Sheet** maps to a `page_number` (`Page 1 = Sheet "Sales"`, `Page 2 = Sheet "Employees"`). The sheet name is injected into the text header so citations reference the exact tab.
  * **CSV (`.csv`, `.tsv`):** Grouped into 50-row blocks per virtual page.

### 4.3 Extractor Implementation
```python
# backend/app/services/rag/extractors/tabular_extractor.py
import io
import pandas as pd
from app.services.rag.schemas import ExtractedPage

def extract_csv_pages(raw_bytes: bytes) -> list[ExtractedPage]:
    df = pd.read_csv(io.BytesIO(raw_bytes))
    if df.empty:
        return []
    
    pages = []
    rows_per_page = 50
    for page_idx, start_idx in enumerate(range(0, len(df), rows_per_page), start=1):
        batch = df.iloc[start_idx : start_idx + rows_per_page]
        rows_text = []
        for row_num, (_, row) in enumerate(batch.iterrows(), start=start_idx + 1):
            row_str = " | ".join(f"[{col}]: {val}" for col, val in row.items() if pd.notna(val))
            rows_text.append(f"Row {row_num}: {row_str}")
        pages.append(ExtractedPage(page_number=page_idx, text="\n".join(rows_text)))
        
    return pages

def extract_excel_pages(raw_bytes: bytes) -> list[ExtractedPage]:
    sheets = pd.read_excel(io.BytesIO(raw_bytes), sheet_name=None)
    pages = []
    for page_idx, (sheet_name, df) in enumerate(sheets.items(), start=1):
        if df.empty:
            continue
        rows_text = [f"Sheet Name: {sheet_name}"]
        for row_num, (_, row) in enumerate(df.iterrows(), start=1):
            row_str = " | ".join(f"[{col}]: {val}" for col, val in row.items() if pd.notna(val))
            rows_text.append(f"Row {row_num}: {row_str}")
        pages.append(ExtractedPage(page_number=page_idx, text="\n".join(rows_text)))
        
    return pages
```

### 4.4 Dependencies & Integration Touchpoints
1. `requirements.txt`: Add `openpyxl==3.1.5` (Pandas is already installed at `pandas==3.0.5`).
2. [s3_service.py](file:///home/dell/Sun_Development/projects/Personal_Knowledge_Base/backend/app/services/AWS/s3_service.py): Add `text/csv`, `application/vnd.openxmlformats-officedocument.spreadsheetml.sheet`, `application/vnd.ms-excel`.
3. [KnowledgeBase.jsx](file:///home/dell/Sun_Development/projects/Personal_Knowledge_Base/frontend/src/pages/KnowledgeBase.jsx#L35-L50): Add `TableChartIcon` for spreadsheet badges in the selection drawer.

---

## 5. Phase 3: Office Documents (`.docx`, `.doc`)

### 5.1 Objective
Extract styled text, nested headings, and embedded tables from Microsoft Word documents.

### 5.2 Technical Design
* **File Location:** `backend/app/services/rag/extractors/docx_extractor.py`
* **Sequential Body Traversal:** Iterates through paragraphs and embedded tables in exact document order:
  * Paragraphs retain plain text.
  * Tables are converted into clean Markdown table representations so columnar relationships are preserved.
* **Page Mapping:** 
  * Hard page breaks (`w:br w:type="page"`) delimit pages.
  * Documents without page breaks are partitioned by major `Heading 1` styles or ~600-word blocks.
* **Legacy `.doc` Support:** Binary Word 97-2003 `.doc` files are detected via magic bytes `\xd0\xcf\x11\xe0`. If unparseable by `python-docx`, the extractor raises `UnsupportedLegacyDocError`, and the worker sets `rag_error_code = "LEGACY_DOC_FORMAT"` prompting the user to save as `.docx`.

### 5.3 Extractor Implementation
```python
# backend/app/services/rag/extractors/docx_extractor.py
import io
from docx import Document
from docx.text.paragraph import Paragraph
from docx.table import Table
from app.services.rag.schemas import ExtractedPage

def table_to_markdown(table: Table) -> str:
    lines = []
    for i, row in enumerate(table.rows):
        cells = [cell.text.replace("\n", " ").strip() for cell in row.cells]
        lines.append("| " + " | ".join(cells) + " |")
        if i == 0:
            lines.append("| " + " | ".join(["---"] * len(cells)) + " |")
    return "\n".join(lines)

def extract_docx_pages(raw_bytes: bytes) -> list[ExtractedPage]:
    doc = Document(io.BytesIO(raw_bytes))
    pages = []
    current_text = []
    page_number = 1

    for child in doc.element.body:
        if child.tag.endswith("p"):
            p = Paragraph(child, doc)
            if any(run.text == "\f" for run in p.runs):
                if current_text:
                    pages.append(ExtractedPage(page_number=page_number, text="\n".join(current_text)))
                    page_number += 1
                    current_text = []
            if p.text.strip():
                current_text.append(p.text.strip())
        elif child.tag.endswith("tbl"):
            t = Table(child, doc)
            current_text.append(table_to_markdown(t))

    if current_text:
        pages.append(ExtractedPage(page_number=page_number, text="\n".join(current_text)))
        
    return pages
```

### 5.4 Dependencies & Integration Touchpoints
1. `requirements.txt`: Add `python-docx==1.1.2`.
2. [s3_service.py](file:///home/dell/Sun_Development/projects/Personal_Knowledge_Base/backend/app/services/AWS/s3_service.py): Whitelist `application/vnd.openxmlformats-officedocument.wordprocessingml.document`.

---

## 6. Central Dispatcher & Worker Integration

### 6.1 Updated Dispatcher in [`document_processor.py`](file:///home/dell/Sun_Development/projects/Personal_Knowledge_Base/backend/app/services/rag/document_processor.py)
```python
# backend/app/services/rag/document_processor.py
from pathlib import Path
from app.services.rag.extractors.text_extractor import extract_text_pages
from app.services.rag.extractors.tabular_extractor import extract_csv_pages, extract_excel_pages
from app.services.rag.extractors.docx_extractor import extract_docx_pages
from app.services.rag.pdf_extractor import extract_pdf_pages

def process_document_from_storage(s3_key: str, filename: str) -> ProcessedDocument:
    raw_bytes = read_object_bytes_limited(key=s3_key, max_bytes=settings.RAG_MAX_PDF_BYTES)
    ext = Path(filename).suffix.lower()

    if ext == ".pdf":
        raw_pages = extract_pdf_pages(raw_bytes)
    elif ext in (".md", ".txt", ".log", ".rtf"):
        raw_pages = extract_text_pages(raw_bytes, filename)
    elif ext in (".csv", ".tsv"):
        raw_pages = extract_csv_pages(raw_bytes)
    elif ext in (".xlsx", ".xls"):
        raw_pages = extract_excel_pages(raw_bytes)
    elif ext == ".docx":
        raw_pages = extract_docx_pages(raw_bytes)
    else:
        raise ValueError(f"Unsupported file format: '{ext}'")

    if not raw_pages:
        raise NoExtractableTextError(f"Document '{filename}' has no extractable text layer.")

    cleaned_pages = clean_extracted_pages(raw_pages)
    page_tuples = [(p.page_number, p.text) for p in cleaned_pages]
    words = build_word_stream(page_tuples)
    chunks = chunk_words(words)

    return ProcessedDocument(
        page_count=len(raw_pages),
        extracted_word_count=len(words),
        chunks=chunks,
    )
```

### 6.2 Worker Call in [`rag_worker.py`](file:///home/dell/Sun_Development/projects/Personal_Knowledge_Base/backend/app/workers/rag_worker.py#L104-L107)
```python
# Step 3 in sync_rag_chunks_in_background():
processed = await run_in_threadpool(
    process_document_from_storage,
    s3_key=db_file.s3_key,
    filename=db_file.filename,
)
```

### 6.3 Error Mapping in [`persistence.py`](file:///home/dell/Sun_Development/projects/Personal_Knowledge_Base/backend/app/services/rag/persistence.py#L39-L56)
Expand `map_rag_exception` to categorize non-PDF extraction errors cleanly:
```python
def map_rag_exception(exc: Exception) -> tuple[str, str, bool]:
    if isinstance(exc, FileNotFoundError):
        return ERROR_OBJECT_NOT_FOUND, "S3 object not found", False
    if isinstance(exc, ValueError) and "unsupported" in str(exc).lower():
        return "UNSUPPORTED_FORMAT", str(exc)[:500], False
    if isinstance(exc, NoExtractableTextError):
        return ERROR_NO_EXTRACTABLE_TEXT, "Document contains no readable text", False
    if isinstance(exc, (BotoCoreError, ClientError)):
        return "STORAGE_READ_FAILED", "Storage read failed", True
    return "CHUNKING_FAILED", f"Extraction error: {str(exc)[:450]}", False
```

---

## 7. Verification Checklist for Production Readiness

- [ ] **Phase 1 Validation:** Upload `green_technology_youtube_shorts_script.md`, check that MySQL records `indexing_status = INDEXED`, and query it via Knowledge Base.
- [ ] **Phase 2 Validation:** Upload `.csv` or multi-tab `.xlsx` financial report, query specific numerical rows, and verify citations map to Sheet tabs.
- [ ] **Phase 3 Validation:** Upload `.docx` containing embedded tables, verify tables are retained as markdown grids in chunks.
- [ ] **Concurrency & Safety:** Verify `RAG_EMBEDDING_CONCURRENCY = 4` prevents Gemini rate limits during multi-document batch indexing.
- [ ] **Zero-Downtime Guarantee:** Verify that indexing a new document format never interferes with active queries on already-indexed PDFs.
