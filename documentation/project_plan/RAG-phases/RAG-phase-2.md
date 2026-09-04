# RAG Phase 2 - Safe PDF Extraction, Cleaning, and Chunking

## 1. Phase Goal

Phase 2 converts an uploaded PDF stored in S3/B2 into deterministic, page-aware text chunks.

This phase is about **text preparation**, not vector indexing yet.

By the end of Phase 2, the backend should be able to:

- safely read a PDF object from S3/B2 with a maximum byte limit
- extract page text using PyMuPDF without writing local files
- normalize messy PDF text into cleaner plain text
- remove repeated headers and footers carefully
- split text into 800-word chunks with 100-word overlap
- track page ranges and word offsets for every chunk
- return clear errors for scanned PDFs or unreadable PDFs
- unit test the extraction and chunking behavior

The output of Phase 2 is an in-memory list of chunks ready for Phase 3 persistence.

```text
S3/B2 PDF object
    |
    v
bounded byte reader
    |
    v
PyMuPDF page extraction
    |
    v
text normalization
    |
    v
repeated header/footer stripping
    |
    v
page-aware word stream
    |
    v
800-word chunks, 100-word overlap
    |
    v
Chunk DTOs ready for MySQL in Phase 3
```

## 2. What Phase 2 Does Not Do

Keep this phase focused. Do not mix it with later responsibilities.

```text
+------------------------------+-------------+----------------+
| Work item                    | Phase 2?    | Later phase    |
+------------------------------+-------------+----------------+
| Read PDF bytes from S3/B2    | Yes         | -              |
| Extract text using PyMuPDF   | Yes         | -              |
| Clean text                   | Yes         | -              |
| Chunk text                   | Yes         | -              |
| Store chunks in MySQL        | No          | Phase 3        |
| Generate Gemini embeddings   | No          | Phase 4        |
| Upsert chunk vectors         | No          | Phase 4        |
| Query RAG answers            | No          | Phase 5        |
| Streamlit playground         | No          | Phase 6        |
+------------------------------+-------------+----------------+
```

Reason: extraction and chunking need their own tests. If persistence, embeddings, and generation are added at the same time, bugs become much harder to isolate.

## 3. Existing Project Context

Relevant current files:

```text
backend/app/
|-- core/config.py
|   `-- Phase 1 should contain RAG_MAX_PDF_BYTES, chunk size, overlap, versions
|
|-- services/AWS/s3_service.py
|   `-- already has _get_s3_client(), head_object helpers, presigned URLs
|
|-- workers/indexing_worker.py
|   `-- currently indexes metadata vectors, not chunk-level RAG yet
|
|-- services/AI/vector_service.py
|   `-- existing Gemini/Qdrant metadata vector service
|
`-- schemas/enums.py
    `-- currently has PENDING, INDEXING, INDEXED, FAILED
```

Phase 2 should add text-processing code without breaking the existing metadata-search worker.

Recommended new files:

```text
backend/app/services/rag/
|-- __init__.py
|-- pdf_extractor.py        # PyMuPDF extraction from bytes
|-- text_cleaner.py         # normalization and repeated margin removal
|-- chunker.py              # page-aware 800/100 word windows
`-- schemas.py              # internal DTOs for pages and chunks

backend/tests/services/rag/
|-- test_text_cleaner.py
|-- test_chunker.py
`-- test_pdf_extractor.py
```

If the project does not yet have a `tests/` folder under `backend`, create it in the existing pytest style.

## 4. Design Principles

### 4.1 MySQL Will Own Text Later

Phase 2 returns chunk objects, but Phase 3 will store them in MySQL.

Qdrant must not receive chunk text.

```text
Phase 2 output:
    clean_text
    page_start
    page_end
    word_start
    word_end
    word_count
    checksum

Phase 3 stores it:
    MySQL document_chunks table

Phase 4 indexes it:
    Qdrant vector + tiny payload only
```

### 4.2 No Local Disk Files

Do not download PDFs into a local temp file just to open them.

Use:

```python
fitz.open(stream=pdf_bytes, filetype="pdf")
```

Not:

```text
download to D:\temp\file.pdf
open path
delete later
```

Why:

- fewer cleanup problems
- safer for concurrent workers
- less risk of leaking private user documents on disk
- simpler tests

### 4.3 Bounded Memory

The backend should not read unlimited object data.

```text
head_object ContentLength
    |
    +-- larger than RAG_MAX_PDF_BYTES -> fail before download
    |
    `-- acceptable size -> stream read with a hard limit
```

Even after `head_object`, enforce the limit while reading the stream. Object metadata can be wrong or the object can change between calls.

### 4.4 Deterministic Output

For the same PDF bytes and same settings, Phase 2 should produce the same chunks every time.

That means:

- no random chunk boundaries
- no time-dependent text cleanup
- no model calls
- no database IDs
- stable word offsets
- stable page ranges

This matters because Phase 3 and Phase 4 use versioned indexing. Re-runs must be predictable.

## 5. End-to-End Phase 2 Flow

```text
Worker receives file_metadata row
    |
    v
Validate file is PDF
    |
    v
Read object bytes from S3/B2
    |
    v
Open PDF from bytes with PyMuPDF
    |
    v
Extract text page by page
    |
    +-- no usable text -> NO_EXTRACTABLE_TEXT
    |
    v
Normalize page text
    |
    v
Split pages into lines
    |
    v
Strip repeated headers/footers
    |
    v
Build page-aware word stream
    |
    v
Emit overlapping chunks
    |
    v
Return chunk list and extraction stats
```

## 6. Step 1 - Add a Safe S3/B2 Byte Reader

### 6.1 Where to Put It

Extend:

```text
backend/app/services/AWS/s3_service.py
```

Add a synchronous function first because Boto3 is synchronous:

```python
def read_object_bytes_limited(key: str, max_bytes: int) -> bytes:
    ...
```

Then add an async wrapper:

```python
async def async_read_object_bytes_limited(key: str, max_bytes: int) -> bytes:
    return await run_in_threadpool(read_object_bytes_limited, key, max_bytes)
```

### 6.2 Required Behavior

```text
read_object_bytes_limited(key, max_bytes)
    |
    v
head_object
    |
    +-- not found -> FileNotFoundError
    |
    +-- ContentLength > max_bytes -> ValueError
    |
    v
get_object
    |
    v
read StreamingBody in chunks
    |
    +-- bytes_read > max_bytes -> ValueError
    |
    v
close body in finally
    |
    v
return bytes
```

### 6.3 Suggested Implementation Shape

```python
def read_object_bytes_limited(key: str, max_bytes: int) -> bytes:
    s3_client = _get_s3_client()
    body = None

    try:
        metadata = s3_client.head_object(
            Bucket=settings.S3_BUCKET_NAME,
            Key=key,
        )
        size_bytes = int(metadata.get("ContentLength") or 0)
        if size_bytes > max_bytes:
            raise ValueError(f"Object is too large: {size_bytes} bytes")

        response = s3_client.get_object(
            Bucket=settings.S3_BUCKET_NAME,
            Key=key,
        )
        body = response["Body"]

        chunks: list[bytes] = []
        total = 0
        while True:
            part = body.read(1024 * 1024)
            if not part:
                break
            total += len(part)
            if total > max_bytes:
                raise ValueError(f"Object exceeded max read size: {max_bytes} bytes")
            chunks.append(part)

        return b"".join(chunks)
    except ClientError as exc:
        status_code = exc.response.get("ResponseMetadata", {}).get("HTTPStatusCode", 0)
        error_code = exc.response.get("Error", {}).get("Code", "")
        if error_code in ("404", "NoSuchKey", "NotFound") or status_code == 404:
            raise FileNotFoundError(f"File object with key '{key}' does not exist.") from exc
        raise RuntimeError("Failed to read object bytes from storage.") from exc
    except BotoCoreError as exc:
        raise RuntimeError("Failed to read object bytes from storage.") from exc
    finally:
        if body is not None:
            body.close()
```

### 6.4 Fresher Notes

`head_object` is like asking storage, "How big is this file?" before downloading it.

`get_object` is the actual download.

The second size check while reading is still needed:

```text
head_object says 49 MB
    |
    v
download starts
    |
    v
stream unexpectedly passes 50 MB
    |
    v
stop immediately
```

## 7. Step 2 - Create Internal RAG DTOs

Create:

```text
backend/app/services/rag/schemas.py
```

Use simple dataclasses for internal service objects. These are not API response schemas yet.

```python
from dataclasses import dataclass


@dataclass(frozen=True)
class ExtractedPage:
    page_number: int
    text: str


@dataclass(frozen=True)
class PageWord:
    text: str
    page_number: int
    absolute_word_index: int


@dataclass(frozen=True)
class TextChunk:
    chunk_index: int
    clean_text: str
    page_start: int
    page_end: int
    word_start: int
    word_end: int
    word_count: int
    text_checksum: str
```

Why dataclasses:

- easy to test
- no database dependency
- no FastAPI dependency
- stable shape for later persistence

Page numbering decision:

```text
Use 1-based page numbers for user-facing citations.

PDF library internal page index: 0, 1, 2
Stored page_number:          1, 2, 3
```

## 8. Step 3 - Extract Text with PyMuPDF

Create:

```text
backend/app/services/rag/pdf_extractor.py
```

### 8.1 Required Behavior

```text
extract_pdf_pages(pdf_bytes)
    |
    v
fitz.open(stream=pdf_bytes, filetype="pdf")
    |
    v
for each page:
    page.get_text("text")
    store page number and text
    |
    v
close document in finally
    |
    v
return list[ExtractedPage]
```

### 8.2 Suggested Implementation Shape

```python
import fitz

from app.services.rag.schemas import ExtractedPage


class PdfExtractionError(Exception):
    pass


def extract_pdf_pages(pdf_bytes: bytes) -> list[ExtractedPage]:
    if not pdf_bytes:
        raise PdfExtractionError("PDF is empty.")

    doc = None
    try:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        pages: list[ExtractedPage] = []
        for page_index in range(doc.page_count):
            page = doc.load_page(page_index)
            text = page.get_text("text") or ""
            pages.append(
                ExtractedPage(
                    page_number=page_index + 1,
                    text=text,
                )
            )
        return pages
    except Exception as exc:
        raise PdfExtractionError("Failed to extract text from PDF.") from exc
    finally:
        if doc is not None:
            doc.close()
```

### 8.3 Scanned PDF Handling

A scanned PDF often contains images but no text layer.

Do not mark it as successfully indexed with zero chunks.

Phase 2 should identify this situation:

```text
PDF has pages
    |
    v
PyMuPDF extracts only empty/whitespace text
    |
    v
raise or return NO_EXTRACTABLE_TEXT
```

Suggested error code for later database storage:

```text
NO_EXTRACTABLE_TEXT
```

OCR is not part of this phase. It can become a separate feature later.

## 9. Step 4 - Normalize Text

Create:

```text
backend/app/services/rag/text_cleaner.py
```

### 9.1 What to Normalize

PDF text often contains strange spacing and invisible characters.

Normalize:

- Unicode compatibility characters
- Windows line endings
- non-breaking spaces
- tabs and repeated horizontal spaces
- control characters
- too many blank lines
- leading/trailing whitespace per line

Recommended function:

```python
def normalize_text(text: str) -> str:
    ...
```

### 9.2 Suggested Implementation Shape

```python
import re
import unicodedata


CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
HORIZONTAL_SPACE = re.compile(r"[ \t\f\v]+")
MANY_BLANK_LINES = re.compile(r"\n{3,}")


def normalize_text(text: str) -> str:
    text = unicodedata.normalize("NFKC", text or "")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = text.replace("\u00a0", " ")
    text = CONTROL_CHARS.sub("", text)

    lines = []
    for line in text.split("\n"):
        cleaned = HORIZONTAL_SPACE.sub(" ", line).strip()
        lines.append(cleaned)

    text = "\n".join(lines)
    text = MANY_BLANK_LINES.sub("\n\n", text)
    return text.strip()
```

### 9.3 Before and After

```text
Before:
    "  Chapter\t1\r\n\r\n\r\nThis\u00a0is   text.  "

After:
    "Chapter 1\n\nThis is text."
```

## 10. Step 5 - Strip Repeated Headers and Footers

### 10.1 Why This Needs Care

Many PDFs repeat the same first or last line on every page:

```text
Personal Knowledge Base Architecture
...
Page 12
```

Those repeated lines hurt retrieval because they appear in many chunks but do not answer user questions.

But do not blindly remove every first and last line. Sometimes those lines are real content.

### 10.2 Rule from Main RAG Plan

Detect candidate first/last lines on every page after normalization.

Remove a candidate only when it appears in at least:

```text
max(3, ceil(page_count * 0.6))
```

That means:

```text
2-page PDF  -> threshold 3, so remove nothing
5-page PDF  -> threshold 3
10-page PDF -> threshold 6
20-page PDF -> threshold 12
```

### 10.3 Suggested Functions

```python
from collections import Counter
from math import ceil


def page_lines(text: str) -> list[str]:
    return [line for line in text.split("\n") if line.strip()]


def strip_repeated_margins(pages: list[list[str]]) -> list[list[str]]:
    threshold = max(3, ceil(len(pages) * 0.6))

    candidates = []
    for lines in pages:
        if lines:
            candidates.append(lines[0].strip().casefold())
            candidates.append(lines[-1].strip().casefold())

    counts = Counter(candidates)
    repeated = {line for line, count in counts.items() if count >= threshold}

    cleaned_pages = []
    for lines in pages:
        cleaned_pages.append([
            line for line in lines
            if line.strip().casefold() not in repeated
        ])
    return cleaned_pages
```

### 10.4 Example

Input:

```text
Page 1:
Project Plan
Introduction text...
Page 1

Page 2:
Project Plan
More content...
Page 2

Page 3:
Project Plan
More content...
Page 3
```

Repeated candidate:

```text
Project Plan appears 3 times -> remove
Page 1/Page 2/Page 3 are different -> keep unless separately detected later
```

Later you may add a page-number pattern rule, but Phase 2 should first implement structural repeated-line detection safely.

## 11. Step 6 - Build a Page-Aware Word Stream

After pages are normalized and repeated margins are removed, convert text into words while keeping page information.

```text
Page 1 lines
    |
    v
words tagged page_number=1

Page 2 lines
    |
    v
words tagged page_number=2

All words
    |
    v
absolute indexes 0, 1, 2, 3...
```

Suggested function:

```python
import re

from app.services.rag.schemas import PageWord

WORD_PATTERN = re.compile(r"\S+")


def build_word_stream(pages: list[tuple[int, str]]) -> list[PageWord]:
    words: list[PageWord] = []
    for page_number, text in pages:
        for match in WORD_PATTERN.finditer(text):
            words.append(
                PageWord(
                    text=match.group(0),
                    page_number=page_number,
                    absolute_word_index=len(words),
                )
            )
    return words
```

Fresher note:

```text
"page-aware" means every word remembers which PDF page it came from.
This is how a chunk can later cite pages 4-5 accurately.
```

## 12. Step 7 - Create 800/100 Word Chunks

### 12.1 Chunking Rule

Use:

```text
chunk size    = 800 words
overlap       = 100 words
step          = 700 words
start offsets = 0, 700, 1400, 2100...
```

Diagram:

```text
words:      0 ------------------------------------------------------ 799
chunk 0:    [0 .................................................... 799]

words:                                  700 ---------------------- 1499
chunk 1:                                [700 ..................... 1499]

overlap:                                [700 ..................... 799]
```

### 12.2 Edge Cases

```text
0 words   -> NO_EXTRACTABLE_TEXT
1 word    -> one chunk
799 words -> one chunk
800 words -> one chunk
801 words -> two chunks: 0-799 and 700-800
```

The 801-word case is expected because the final unread words after 800 still need coverage.

### 12.3 Suggested Chunker

Create:

```text
backend/app/services/rag/chunker.py
```

Suggested function:

```python
from hashlib import sha256

from app.core.config import settings
from app.services.rag.schemas import PageWord, TextChunk


def chunk_words(
    words: list[PageWord],
    size: int = settings.RAG_CHUNK_WORDS,
    overlap: int = settings.RAG_CHUNK_OVERLAP_WORDS,
) -> list[TextChunk]:
    if not words:
        return []
    if overlap < 0 or overlap >= size:
        raise ValueError("overlap must be smaller than size")

    step = size - overlap
    chunks: list[TextChunk] = []

    for start in range(0, len(words), step):
        batch = words[start:start + size]
        if not batch:
            break

        clean_text = " ".join(word.text for word in batch).strip()
        chunks.append(
            TextChunk(
                chunk_index=len(chunks),
                clean_text=clean_text,
                page_start=batch[0].page_number,
                page_end=batch[-1].page_number,
                word_start=batch[0].absolute_word_index,
                word_end=batch[-1].absolute_word_index,
                word_count=len(batch),
                text_checksum=sha256(clean_text.encode("utf-8")).hexdigest(),
            )
        )

        if start + len(batch) == len(words):
            break

    return chunks
```

### 12.4 Word Offset Decision

Use inclusive offsets:

```text
word_start = first word index in chunk
word_end   = last word index in chunk
```

Example:

```text
800-word chunk:
word_start = 0
word_end   = 799
word_count = 800
```

This is easier to inspect manually than half-open ranges.

## 13. Step 8 - Orchestrate Extraction to Chunks

Create a small service that connects the pieces:

```text
backend/app/services/rag/document_processor.py
```

Suggested flow:

```python
from dataclasses import dataclass

from app.core.config import settings
from app.services.AWS.s3_service import read_object_bytes_limited
from app.services.rag.chunker import build_word_stream, chunk_words
from app.services.rag.pdf_extractor import extract_pdf_pages
from app.services.rag.text_cleaner import normalize_text, page_lines, strip_repeated_margins
from app.services.rag.schemas import PageWord, TextChunk


class NoExtractableTextError(Exception):
    pass


@dataclass(frozen=True)
class ProcessedDocument:
    page_count: int
    extracted_word_count: int
    chunks: list[TextChunk]


def process_pdf_from_storage(s3_key: str) -> ProcessedDocument:
    pdf_bytes = read_object_bytes_limited(
        key=s3_key,
        max_bytes=settings.RAG_MAX_PDF_BYTES,
    )
    pages = extract_pdf_pages(pdf_bytes)

    normalized = [
        (page.page_number, normalize_text(page.text))
        for page in pages
    ]

    lines_by_page = [page_lines(text) for _, text in normalized]
    cleaned_lines = strip_repeated_margins(lines_by_page)

    page_texts = [
        (page_number, "\n".join(lines))
        for (page_number, _), lines in zip(normalized, cleaned_lines)
    ]

    words: list[PageWord] = build_word_stream(page_texts)
    if not words:
        raise NoExtractableTextError("PDF has no extractable text layer.")

    chunks = chunk_words(words)
    return ProcessedDocument(
        page_count=len(pages),
        extracted_word_count=len(words),
        chunks=chunks,
    )
```

Implementation note: `build_word_stream` can live in `chunker.py` or `text_cleaner.py`. Prefer `chunker.py` if it produces `PageWord` objects.

## 14. Step 9 - Connect to Existing Worker Carefully

The existing worker currently does this:

```text
FileMetadata row
    |
    v
build metadata text
    |
    v
Gemini metadata embedding
    |
    v
Qdrant file-level point
```

Do not replace that path accidentally in Phase 2 unless you are intentionally turning off metadata search.

For Phase 2, add a separate worker/service path:

```text
sync_vector_in_background()
    Existing metadata indexing path

process_pdf_from_storage()
    New RAG extraction/chunking path
```

Near-term integration options:

```text
Option A: Add a separate test-only script/function
    Best for Phase 2 isolation.

Option B: Call process_pdf_from_storage() from worker, log stats only
    Useful to validate real uploaded PDFs.

Option C: Add temporary internal endpoint for development
    Only if protected by auth and removed/replaced in Phase 6.
```

Recommended for this project:

```text
Use Option A first, then Option B once tests pass.
```

Why:

- Phase 3 still needs database schema for `document_chunks`
- logging chunk stats is safe
- no partial RAG data is persisted yet
- existing document upload/search behavior remains stable

Example logging-only integration:

```python
try:
    if filename.lower().endswith(".pdf"):
        processed = await run_in_threadpool(process_pdf_from_storage, db_file.s3_key)
        logger.info(
            "RAG Phase 2 processed file_id=%s pages=%s words=%s chunks=%s",
            file_id,
            processed.page_count,
            processed.extracted_word_count,
            len(processed.chunks),
        )
except NoExtractableTextError:
    logger.info("PDF file_id=%s has no extractable text layer.", file_id)
except Exception as exc:
    logger.warning("RAG Phase 2 processing failed for file_id=%s: %s", file_id, exc)
```

Do not mark `indexing_status=INDEXED` based only on Phase 2 chunking. True RAG indexing is not complete until embeddings and Qdrant upserts happen in Phase 4.

## 15. Error Handling Plan

Use explicit error categories. They make logs, retries, and future UI messages much easier.

```text
+----------------------+--------------------------------------+------------------+
| Error code           | Meaning                              | Retry?           |
+----------------------+--------------------------------------+------------------+
| OBJECT_NOT_FOUND     | S3/B2 object missing                 | No, investigate  |
| PDF_TOO_LARGE        | Object exceeds RAG_MAX_PDF_BYTES     | No               |
| PDF_READ_FAILED      | Storage read failed                  | Maybe            |
| PDF_PARSE_FAILED     | PyMuPDF could not open/read PDF      | No/Maybe         |
| NO_EXTRACTABLE_TEXT  | Scanned/image-only PDF               | No, needs OCR    |
| CHUNKING_FAILED      | Bug or invalid chunk settings        | No, fix code     |
+----------------------+--------------------------------------+------------------+
```

Phase 2 can raise typed exceptions internally. Phase 3 can later map them to `rag_error_code` and `rag_error_message` columns.

Important:

```text
No extractable text is not a successful index.
It is a terminal RAG extraction failure unless OCR is added later.
```

## 16. Testing Plan

Phase 2 should have focused unit tests. These tests are more valuable than broad end-to-end tests at this stage.

### 16.1 Text Normalization Tests

Test:

- CRLF becomes LF
- non-breaking spaces become normal spaces
- repeated horizontal spaces collapse
- control characters are removed
- too many blank lines collapse

Example:

```text
Input:  "A\r\nB\u00a0 C\t\tD\n\n\n\nE"
Output: "A\nB C D\n\nE"
```

### 16.2 Repeated Margin Tests

Test:

```text
2 pages:
same title appears twice
expected: not removed because threshold is 3

5 pages:
same title appears on all pages
expected: removed

10 pages:
line appears on 5 pages
expected: not removed because threshold is 6
```

### 16.3 Chunk Boundary Tests

Test word counts:

```text
0 words   -> []
1 word    -> 1 chunk
799 words -> 1 chunk
800 words -> 1 chunk
801 words -> 2 chunks
1500 words -> 2 chunks
```

Check:

- chunk indexes start at 0
- chunk 1 starts at word 700
- overlap is exactly 100 words
- `page_start` and `page_end` are correct
- checksum is stable

### 16.4 PDF Extraction Tests

Use tiny generated test PDFs if possible. Keep fixtures small.

Test:

- valid text PDF returns pages
- empty bytes raises extraction error
- invalid bytes raises extraction error
- scanned/no-text PDF leads to `NO_EXTRACTABLE_TEXT` in processor

### 16.5 S3 Reader Tests

Mock the Boto3 client.

Test:

- `head_object` too large raises `ValueError`
- missing object raises `FileNotFoundError`
- stream closes in `finally`
- stream exceeding limit during read raises `ValueError`
- successful object returns exact bytes

## 17. Manual Smoke Test

After implementing Phase 2, use a small local script or `uv run python -c` to process a known uploaded PDF key.

Suggested temporary script:

```text
backend/app/scripts/rag_phase2_smoke.py
```

Example:

```python
import sys

from app.services.rag.document_processor import process_pdf_from_storage


if __name__ == "__main__":
    s3_key = sys.argv[1]
    result = process_pdf_from_storage(s3_key)
    print(f"pages={result.page_count}")
    print(f"words={result.extracted_word_count}")
    print(f"chunks={len(result.chunks)}")
    for chunk in result.chunks[:3]:
        print("-" * 80)
        print(f"chunk={chunk.chunk_index} pages={chunk.page_start}-{chunk.page_end}")
        print(f"words={chunk.word_start}-{chunk.word_end} count={chunk.word_count}")
        print(chunk.clean_text[:500])
```

Run:

```powershell
cd D:\Personal_Knowledge_Base\backend
uv run python -m app.scripts.rag_phase2_smoke uploads/example.pdf
```

Expected output shape:

```text
pages=12
words=6420
chunks=10
--------------------------------------------------------------------------------
chunk=0 pages=1-2
words=0-799 count=800
...
```

Do not commit a script that prints private document text unless it is clearly development-only and protected from production use.

## 18. Development Order

Recommended implementation sequence:

```text
1. Confirm Phase 1 dependencies/settings exist
2. Add internal RAG dataclasses
3. Add text normalization tests and implementation
4. Add repeated margin tests and implementation
5. Add chunk boundary tests and implementation
6. Add PyMuPDF extraction tests and implementation
7. Add S3 bounded byte reader tests and implementation
8. Add document_processor orchestration
9. Add smoke script or logging-only worker integration
10. Run tests and smoke check with a small PDF
```

Why this order works:

```text
Pure text functions first
    |
    v
Easy tests, fast feedback
    |
    v
PDF and S3 integration later
    |
    v
Fewer moving parts when debugging
```

## 19. Commands

From the backend folder:

```powershell
cd D:\Personal_Knowledge_Base\backend
```

Run tests:

```powershell
uv run pytest
```

Run only RAG service tests:

```powershell
uv run pytest tests/services/rag
```

Check imports:

```powershell
uv run python -c "import fitz; from app.core.config import settings; print(settings.RAG_CHUNK_WORDS, settings.RAG_CHUNK_OVERLAP_WORDS)"
```

Expected:

```text
800 100
```

## 20. Code Review Checklist

Before marking Phase 2 complete, review these items:

```text
[ ] S3 object reads are bounded by RAG_MAX_PDF_BYTES
[ ] StreamingBody is closed in finally
[ ] PyMuPDF document is closed in finally
[ ] No local PDF files are written to disk
[ ] Text cleanup is deterministic
[ ] Header/footer removal uses threshold max(3, ceil(page_count * 0.6))
[ ] Chunk size comes from settings, not hardcoded everywhere
[ ] Overlap is validated as smaller than chunk size
[ ] Chunks include page_start and page_end
[ ] Chunks include word_start, word_end, and word_count
[ ] text_checksum is SHA-256 of clean_text
[ ] Scanned PDFs produce NO_EXTRACTABLE_TEXT behavior
[ ] Existing metadata vector search still works
[ ] No chunk text is sent to Qdrant in this phase
[ ] Tests cover 799/800/801 word edge cases
```

## 21. Phase 2 Definition of Done

Phase 2 is complete when:

- backend can read a PDF object from S3/B2 with a hard byte limit
- PyMuPDF extracts text page by page from bytes
- extraction does not require local files
- text normalization handles common PDF whitespace issues
- repeated headers/footers are removed only when structurally repeated
- chunking emits deterministic 800/100 word windows
- each chunk contains clean text, checksum, page range, and word offsets
- no-text PDFs are treated as `NO_EXTRACTABLE_TEXT`
- unit tests cover cleaner, margin stripping, chunking, PDF extraction, and S3 reader behavior
- existing upload and metadata vector indexing behavior is not broken

## 22. Handoff to Phase 3

Phase 2 hands this shape to Phase 3:

```text
ProcessedDocument
|
+-- page_count
+-- extracted_word_count
`-- chunks[]
    |
    +-- chunk_index
    +-- clean_text
    +-- page_start
    +-- page_end
    +-- word_start
    +-- word_end
    +-- word_count
    `-- text_checksum
```

Phase 3 will add:

```text
document_chunks table
file_metadata RAG tracking columns
index_version handling
transactional chunk persistence
active version cutover later in the pipeline
```

Think of Phase 2 as building the document preparation machine. It should produce clean, cited, predictable chunks every time. Once that machine is trustworthy, storing and embedding those chunks becomes much safer.
