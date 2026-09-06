# RAG Phase 4 - Gemini Embeddings and Qdrant Index

## 1. Phase Goal

Phase 4 takes the durable, versioned chunks from Phase 3 and makes them searchable by:

- Generating valid Gemini `gemini-embedding-2` vectors (768-dimensional, cosine distance)
- Upserting points into a tenant-isolated Qdrant collection with deterministic IDs
- Building the index with zero-downtime cutover semantics
- Providing retry logic, batch boundaries, and validation gates

By the end of Phase 4, the backend should be able to:

- Embed document chunks with `RETRIEVAL_DOCUMENT` task type and `output_dimensionality=768`
- Upsert Qdrant points in bounded batches with idempotent deterministic UUIDv5 point IDs
- Validate every embedding response (non-empty, correct length, proper ordering)
- Search Qdrant with mandatory `user_id` filter plus optional file/version filters from MySQL
- Handle retryable errors (timeouts, 429s, 5xx) with exponential backoff and jitter
- Cut over the active index version only after Qdrant count/mapping verification
- Keep old vectors alive until the new version is verified, then clean asynchronously

The central architecture rule:

```text
A query must only ever use a complete active version.
Never expose a half-written chunk version to retrieval.
```

## 2. Phase 3 Status Check

Before writing this plan, the current Phase 3 implementation was checked.

Present files:

```text
backend/app/services/rag/
|-- __init__.py
|-- schemas.py
|-- pdf_extractor.py
|-- text_cleaner.py
|-- chunker.py
|-- document_processor.py
|-- ids.py
|-- persistence.py
```

Focused verification passed:

```text
uv run pytest tests/unit/services/rag tests/unit/services/test_s3_service.py
58 passed
```

So Phase 4 can assume these are available:

- `process_pdf_from_storage(s3_key)` - Phase 2 extraction
- `ProcessedDocument` - Phase 2 output shape
- `TextChunk` - Phase 2 chunk DTO
- `text_checksum` - SHA-256 of clean text
- Bounded S3/B2 reads with byte limits
- PyMuPDF page extraction from bytes
- Deterministic chunking with 800/100 word windows
- SQLAlchemy models: `DocumentChunk`, `UserCorpusState`, `FileMetadata` RAG columns
- Alembic migration applied with `document_chunks`, `user_corpus_state`, updated `file_metadata`
- Deterministic chunk IDs via `build_chunk_id()` using UUIDv5
- `stage_document_chunks()` persistence service
- `activate_rag_index_version()` cutover helper
- Indexing lifecycle: `PENDING → EXTRACTING → CHUNKED → EMBEDDING → INDEXING → INDEXED`
- Failure states: `FAILED_RETRYABLE`, `FAILED_TERMINAL`
- Chunk ID format: `uuid5(NAMESPACE_URL, "rag-chunk:{file_id}:{index_version}:{chunk_index}")`

## 3. What Phase 4 Adds

```text
+-------------------------------+--------------------------------------------+
| Area                          | Phase 4 work                               |
+-------------------------------+--------------------------------------------+
| Gemini embedding generation   | RETRIEVAL_DOCUMENT and RETRIEVAL_QUERY     |
| Qdrant upserts                | Bounded batches, deterministic point IDs    |
| Vector validation             | Length check, non-empty, response ordering  |
| Tenant isolation              | Mandatory user_id filter in all queries     |
| Retry logic                   | Exponential backoff with jitter for 429/5xx  |
| Batch progress persistence    | Track which batches succeeded               |
| Index version cutover         | Verify then activate active_index_version   |
| Asynchronous cleanup          | Delete old version vectors after cutover     |
+-------------------------------+--------------------------------------------+
```

Phase 4 does **not** add:

```text
PDF extraction or text normalization          - Phase 2
MySQL schema or persistence                     - Phase 3
RAG query endpoints, answer generation          - Phase 5/6
Redis answer cache, Streamlit UI                - Phase 5/6
```

## 4. Existing Project Context

Relevant current files (from Phases 2 & 3):

```text
backend/app/services/rag/
|-- __init__.py
|-- schemas.py          - TextChunk, ProcessedDocument DTOs
|-- pdf_extractor.py    - PyMuPDF extraction from bytes
|-- text_cleaner.py     - normalize_text, strip_repeated_margins
|-- chunker.py          - build_word_stream, chunk_words
|-- document_processor.py - process_pdf_from_storage, ProcessedDocument
|-- ids.py              - build_chunk_id() UUIDv5 generator
|-- persistence.py      - stage_document_chunks(), activate_rag_index_version()
|-- config.py           - RAG embedding settings
|
backend/app/database/db_models.py
|-- FileMetadata, DocumentChunk, UserCorpusState SQLAlchemy models
|
backend/app/core/config.py
|-- RAG_MAX_PDF_BYTES, RAG_CHUNK_WORDS, RAG_CHUNK_OVERLAP_WORDS
|-- GEMINI_EMBEDDING_MODEL=gemini-embedding-2
|-- EMBEDDING_DIMENSIONS=768
|-- RAG_QDANT_COLLECTION=document_chunks_v1
|-- RAG_BATCH_SIZE, RAG_MAX_RETRIES, RAG_BACKOFF_BASE, etc.
|
services/AI/vector_service.py  - existing Gemini/Qdrant metadata service (do not replace)
```

Phase 4 should add embedding generation and Qdrant upsert code without breaking the existing metadata vector service.

## 5. Design Principles

### 5.1 Gemini Embedding Model Contract

- Model: `gemini-embedding-2` (never `text-embedding-004`; retired Jan 2026)
- Dimensions: always `output_dimensionality=768`
- Task types: `RETRIEVAL_DOCUMENT` for chunks, `RETRIEVAL_QUERY` for questions
- Validation: every vector must be exactly 768 floats; reject and retry on mismatch
- Non-empty content guard: raise on empty/whitespace-only input before calling API

### 5.2 Qdrant Collection Contract

- Collection name: `document_chunks_v1` (created in Phase 1 startup guard)
- Vector size: 768, distance: `Distance.COSINE`
- Payload: only the 4 fields from `ChunkPayload` (`user_id`, `file_id`, `index_version`, `chunk_index`)
- Never store chunk text in Qdrant payload; MySQL is the source of truth
- Point ID: deterministic UUIDv5 `uuid5(NAMESPACE_URL, "rag-chunk:{file_id}:{index_version}:{chunk_index}")`

### 5.3 Tenant Isolation

- **Every** Qdrant search must include a mandatory `user_id` filter
- File/version filters must be resolved from MySQL first, then passed to Qdrant
- Cross-tenant result leakage is a security violation; always validate ownership
- Corpus revision (`user_corpus_state.corpus_revision`) invalidates answer cache keys

### 5.4 Batch and Concurrency Bounds

- Batch size configured via `RAG_EMBEDDING_BATCH_SIZE` (default 64, max 128)
- Worker concurrency bounded by `RAG_EMBEDDING_CONCURRENCY` (default 4)
- Progress tracked per-file: which chunk index ranges have been upserted
- Persist batch progress after each successful upsert so retries resume where left off

### 5.5 Retry Policy

- Retry only on: timeouts, 429 Too Many Requests, retryable 5xx responses
- Exponential backoff with jitter: `base_delay * (2 ** attempt) + random_jitter`
- Maximum retries: `RAG_MAX_RETRIES` (default 5)
- On non-retryable errors (validation failure, schema mismatch), fail fast and log

## 6. Implementation Steps

### Step 1 - Add Embedding Utility Functions

Create/Q update:

```text
backend/app/services/rag/embedding.py
```

**Required functions:**

```python
from google.genai import types
from qdrant_client.models import PointStruct, VectorParams, Distance
from uuid import UUID, uuid5
from hashlib import sha256
from app.core.config import settings
from app.services.rag.ids import build_chunk_id

EXPECTED_VECTOR_SIZE = 768
GEMINI_EMBEDDING_MODEL = settings.GEMINI_EMBEDDING_MODEL  # "gemini-embedding-2"
EMBEDDING_DIMENSIONS = settings.EMBEDDING_DIMENSIONS     # 768

def embed_document(chunk_text: str) -> list[float]:
    """Embed a single chunk text using Gemini RETRIEVAL_DOCUMENT."""
    if not chunk_text or not chunk_text.strip():
        raise ValueError("Chunk text is empty or whitespace-only")
    
    from google.genai import client as gemini_client
    result = gemini_client.models.embed_content(
        model=GEMINI_EMBEDDING_MODEL,
        contents=chunk_text,
        config=types.EmbedContentConfig(
            task_type="RETRIEVAL_DOCUMENT",
            output_dimensionality=EMBEDDING_DIMENSIONS,
        ),
    )
    
    vector = result.embeddings[0].values
    if len(vector) != EXPECTED_VECTOR_SIZE:
        raise RuntimeError(
            f"Unexpected embedding dimension: got {len(vector)}, expected {EXPECTED_VECTOR_SIZE}"
        )
    return vector

def embed_query(question_text: str) -> list[float]:
    """Embed a user question using Gemini RETRIEVAL_QUERY."""
    if not question_text or not question_text.strip():
        raise ValueError("Question text is empty or whitespace-only")
    
    from google.genai import client as gemini_client
    result = gemini_client.models.embed_content(
        model=GEMINI_EMBEDDING_MODEL,
        contents=question_text,
        config=types.EmbedContentConfig(
            task_type="RETRIEVAL_QUERY",
            output_dimensionality=EMBEDDING_DIMENSIONS,
        ),
    )
    
    vector = result.embeddings[0].values
    if len(vector) != EXPECTED_VECTOR_SIZE:
        raise RuntimeError(
            f"Unexpected embedding dimension: got {len(vector)}, expected {EXPECTED_VECTOR_SIZE}"
        )
    return vector
```

**Junior developer pitfalls:**

- "800 words" is not a Gemini token limit; handle model request rejection cleanly (trim or split if API returns 400)
- Never accept vectors without validating length == 768
- Always use `RETRIEVAL_DOCUMENT` for chunks, `RETRIEVAL_QUERY` for questions

### Step 2 - Add Qdrant Upsert Service

Create:

```text
backend/app/services/rag/qdrant_service.py
```

**Required functions:**

```python
from qdrant_client import QdrantClient
from qdrant_client.models import PointStruct, VectorParams, Distance
from uuid import UUID
from app.core.config import settings
from app.services.rag.ids import build_chunk_id
from app.services.rag.embedding import embed_document, embed_query
import asyncio
import time
import random

QDANT_COLLECTION = settings.RAG_QDANT_COLLECTION  # "document_chunks_v1"

# Ensured by Phase 1 startup; see plan Section 201-207
# EXPECTED = VectorParams(size=768, distance=Distance.COSINE)

def get_qdrant_client() -> QdrantClient:
    """Return configured Qdrant client instance."""
    ...

def ensure_collection() -> None:
    """Create collection if not exists; reject dimension/distance mismatch."""
    client = get_qdrant_client()
    coll = client.get_collection(collection_name=QDANT_COLLECTION)
    # Inspect config.params.vectors and fail on mismatch
    ...

def upsert_document_chunks(
    user_id: int,
    file_id: int,
    index_version: int,
    chunks: list[dict],  # {chunk_index: int, clean_text: str}
    batch_size: int = None,
) -> dict:
    """Upsert chunk vectors into Qdrant in bounded batches.
    
    Returns {"upserted": int, "failed": int, "batch_progress": list}.
    """
    ...
```

**Detailed implementation:**

```python
def _batch_chunks(chunks: list, size: int):
    """Yield successive n-sized chunks from list."""
    for i in range(0, len(chunks), size):
        yield chunks[i:i + size]

def _qdrant_upsert_batch(points: list[PointStruct]) -> int:
    """Upsert one batch to Qdrant; return number of points upserted."""
    client = get_qdrant_client()
    client.upsert(
        collection_name=QDANT_COLLECTION,
        points=points,
    )
    return len(points)

def upsert_document_chunks(
    user_id: int,
    file_id: int,
    index_version: int,
    chunks: list[dict],
    batch_size: int = None,
) -> dict:
    """Upsert chunk vectors into Qdrant in bounded batches."""
    if batch_size is None:
        batch_size = settings.RAG_EMBEDDING_BATCH_SIZE  # default 64, max 128
    
    points = []
    for chunk in chunks:
        chunk_index = chunk["chunk_index"]
        point_id = build_chunk_id(file_id, index_version, chunk_index)
        vector = embed_document(chunk["clean_text"])
        
        from app.services.rag.schemas import ChunkPayload
        payload = ChunkPayload(
            user_id=user_id,
            file_id=file_id,
            index_version=index_version,
            chunk_index=chunk_index,
        ).model_dump()
        
        point = PointStruct(id=point_id, vector=vector, payload=payload)
        points.append(point)
    
    total_upserted = 0
    total_failed = 0
    batch_progress = []
    
    for batch in _batch_chunks(points, batch_size):
        attempt = 0
        success = False
        while attempt < settings.RAG_MAX_RETRIES and not success:
            try:
                _qdrant_upsert_batch(batch)
                success = True
                for point in batch:
                    batch_progress.append({
                        "chunk_index": point.payload["chunk_index"],
                        "point_id": str(point.id),
                    })
                total_upserted += len(batch)
            except Exception as exc:
                # Retry only on timeouts, 429, 5xx
                status_code = getattr(getattr(exc, 'response', None), 'status_code', None)
                if status_code in (429,) or _is_timeout(exc):
                    attempt += 1
                    delay = (settings.RAG_BACKOFF_BASE ** attempt) + random.random()
                    time.sleep(delay)
                    continue
                else:
                    total_failed += len(batch)
                    break
    
    return {
        "upserted": total_upserted,
        "failed": total_failed,
        "batch_progress": batch_progress,
    }
```

**Junior developer pitfalls:**

- Never search Qdrant without an owner filter (always `user_id` in query filter)
- Never accept vectors without validating length == 768
- Retries must use the same UUIDs so an upsert overwrites rather than duplicates
- Bounding batch size and worker concurrency with configuration

### Step 3 - Add Query Service with Tenant Filters

Create:

```text
backend/app/services/rag/query_service.py
```

**Required functions:**

```python
from qdrant_client import QdrantClient
from qdrant_client.models import Filter, FieldCondition, VectorParams
from app.core.config import settings
from app.services.rag.embedding import embed_query

def search_similar_chunks(
    user_id: int,
    query_text: str,
    file_ids: list[int] | None = None,
    top_k: int = None,
    score_threshold: float = None,
) -> list[dict]:
    """Search Qdrant for similar chunks with mandatory user_id filter.
    
    Returns list of dicts with: chunk_id, score, file_id, index_version, chunk_index
    always filtered by user ownership via MySQL hydration later.
    """
    ...
```

**Implementation:**

```python
def search_similar_chunks(
    user_id: int,
    query_text: str,
    file_ids: list[int] | None = None,
    top_k: int = None,
    score_threshold: float = None,
) -> list[dict]:
    """Search Qdrant for similar chunks with mandatory user_id filter."""
    if top_k is None:
        top_k = settings.RAG_TOP_K  # default 6
    if score_threshold is None:
        score_threshold = settings.RAG_SCORE_THRESHOLD  # default 0.35
    
    query_vector = embed_query(query_text)
    
    # Build Qdrant filter: mandatory user_id + optional file/version filters
    qfilter = Filter(
        must=[
            FieldCondition(
                key="user_id",
                match=Filter(value_equal=user_id),
            ),
        ],
    )
    
    # Add file ID filters if provided (resolved from MySQL ownership)
    if file_ids:
        if len(file_ids) == 1:
            qfilter.must.append(
                FieldCondition(
                    key="file_id",
                    match=Filter(value_equal=file_ids[0]),
                ),
            )
        else:
            qfilter.must.append(
                FieldCondition(
                    key="file_id",
                    match=Filter(any=file_ids),
                ),
            )
    
    client = get_qdrant_client()
    result = client.search(
        collection_name=settings.RAG_QDANT_COLLECTION,
        query_vector=query_vector,
        limit=top_k,
        score_threshold=score_threshold,
        query_filter=qfilter,
    )
    
    hits = []
    for rank, point in enumerate(result):
        hits.append({
            "chunk_id": point.payload.get("chunk_id", str(point.id)),
            "file_id": point.payload.get("file_id"),
            "index_version": point.payload.get("index_version"),
            "chunk_index": point.payload.get("chunk_index"),
            "score": point.score,
            "rank": rank,
        })
    
    return hits
```

**Junior developer pitfalls:**

- Never search Qdrant without an owner filter - this is a security requirement
- Always validate file IDs against MySQL ownership before passing to Qdrant
- Preserve Qdrant rank in application code because SQL `IN` has no ordering guarantee

### Step 4 - Add Batch Progress and Resume Logic

Update `qdrant_service.py` to track per-file batch progress in MySQL:

```text
Add columns to document_chunks or a separate batch_progress table:
- batch_upserted_at DATETIME(6) - when last batch was upserted
- batch_status ENUM('pending', 'upserted', 'failed') 
```

Or simpler: since point IDs are deterministic and upserts are idempotent, we can simply re- upsert any chunks not yet marked as done. Track progress by checking which chunk_index ranges have been successfully upserted.

Simpler approach: after each successful upsert batch, update `document_chunks.indexed` or add a `upserted_at` timestamp. Since we already have `document_chunks` with `embedding_model` and `embedding_dimensions`, we can query for chunks where embeddings exist but Qdrant may not yet have them.

Simplest approach for Phase 4: rely on idempotent upserts. If a batch fails partway, re-run the same upsert and Qdrant will overwrite existing points. Track progress by simply re-upserting chunks for the given `index_version` and `file_id`.

## 7. Versioned Index Cutover

### 7.1 Build New Version Vectors

In Phase 4, after chunks are staged in MySQL (Phase 3 `stage_document_chunks` sets `index_version` but Qdrant is not yet updated):

```text
Phase 4 workflow:
1. Read chunks for file where index_version = new_version (not yet active)
2. Embed each chunk with embed_document()
3. Upsert Qdrant points with deterministic point_ids
4. Verify Qdrant count matches MySQL chunk_count
5. If verification passes, call activate_rag_index_version() from Phase 3
6. After commit, queries see new version via active_index_version
7. If verification fails, log error and do not cut over
```

### 7.2 Verification Helper

```python
def verify_qdrant_index(user_id: int, file_id: int, index_version: int,
                       expected_chunk_count: int) -> bool:
    """Verify Qdrant has the expected number of points for a version."""
    from qdrant_client import QdrantClient
    from qdrant_client.models import Filter, FieldCondition
    
    client = get_qdrant_client()
    count = client.count(
        collection_name=settings.RAG_QDANT_COLLECTION,
        query_filter=Filter(
            must=[
                FieldCondition(key="user_id", match=Filter(value_equal=user_id)),
                FieldCondition(key="file_id", match=Filter(value_equal=file_id)),
                FieldCondition(key="index_version", match=Filter(value_equal=index_version)),
            ],
        ),
    ).count
    
    return count == expected_chunk_count
```

### 7.3 Cutover Flow

```text
Before commit:
    active_index_version = 1
    queries see v1

Phase 4 builds v2:
    - Chunks v2 in document_chunks (Phase 3 already done)
    - Vectors upserted to Qdrant for v2
    - active_index_version still 1

Single commit (activate_rag_index_version):
    active_index_version = 2
    corpus_revision += 1

After commit:
    queries see v2 (filter by active_index_version=2)
```

### 7.4 Asynchronous Old Version Cleanup

After cutover, old version vectors can be deleted asynchronously:

```python
def cleanup_old_version_vectors(user_id: int, old_index_version: int) -> None:
    """Delete old version vectors after graceful cutover period."""
    client = get_qdrant_client()
    client.delete_points(
        collection_name=settings.RAG_QDANT_COLLECTION,
        points_selector=Filter(
            must=[
                FieldCondition(key="user_id", match=Filter(value_equal=user_id)),
                FieldCondition(key="index_version", match=Filter(value_equal=old_index_version)),
            ],
        ),
    )
```

## 8. Error Handling and Retries

### 8.1 Error Categories (Phase 4 specific)

```text
+----------------------+--------------------------------------+------------------+
| Error code           | Meaning                              | Retry?           |
+----------------------+--------------------------------------+------------------+
| EMBEDDING_TIMEOUT    | Gemini API timeout                   | Yes, exponential |
| EMBEDDING_429        | Gemini rate limit 429                 | Yes, with jitter |
| EMBEDDING_5XX        | Gemini server error 5xx               | Yes, exponential |
| EMBEDDING_DIM_MISMATCH | Vector length != 768                  | No, log and skip |
| QDRANT_UPSERT_FAILED | Qdrant upsert error                   | Maybe, depends   |
| QDRANT_COLLECTION_MISMATCH | Dimension/distance mismatch      | No, investigate  |
+----------------------+--------------------------------------+------------------+
```

### 8.2 Retry Logic

Exponential backoff with jitter:

```python
import random
import time

def _with_retry(fn, max_retries=5, base_delay=1.0):
    """Execute fn with exponential backoff and jitter."""
    for attempt in range(max_retries + 1):
        try:
            return fn()
        except Exception as exc:
            status_code = getattr(getattr(exc, 'response', None), 'status_code', None)
            is_retryable = (
                status_code == 429
                or _is_timeout(exc)
                or (hasattr(exc, 'code') and exc.code >= 500 and exc.code < 600)
            )
            if not is_retryable or attempt >= max_retries:
                raise
            delay = (base_delay * (2 ** attempt)) + random.random()
            time.sleep(delay)
```

## 9. Testing Plan

### 9.1 Embedding Validation Tests

Test:

- `embed_document()` returns 768-dim vector for valid text
- `embed_document()` raises ValueError for empty/whitespace text
- `embed_document()` raises RuntimeError for dimension mismatch (simulated)
- `embed_query()` uses `task_type="RETRIEVAL_QUERY"`
- Dimension validation catches wrong-sized responses

### 9.2 Qdrant Upsert Tests

Test:

- Upsert batch of points with deterministic IDs
- Idempotent upsert: same point ID twice overwrites, not duplicates
- Mandatory `user_id` filter in search
- Collection creation rejection on dimension mismatch
- Batch progress tracking and resume

### 9.3 Cutover Tests

Test:

- `activate_rag_index_version()` with zero chunks raises ValueError
- `activate_rag_index_version()` with mismatched counts raises ValueError
- `activate_rag_index_version()` increments corpus_revision
- After cutover, queries filter by new `active_index_version`
- Old version vectors remain until explicitly cleaned

### 9.4 Tenant Isolation Tests

Test:

- User A cannot see User B's chunks even with same file_id
- Cross-tenant search returns empty results
- Filter by user_id + file_id + index_version is exclusive

### 9.5 Integration Tests

Test (with mocked or real Qdrant/MySQL):

- End-to-end: Phase 3 stage → Phase 4 embed → cutover → query
- Retry behavior for 429 and timeout errors
- Batch size respecting `RAG_EMBEDDING_BATCH_SIZE`
- Cache invalidation when corpus_revision increments

Run tests:

```powershell
uv run pytest tests/services/rag/test_embedding.py tests/services/rag/test_qdrant.py tests/services/rag/test_cutover.py
```

## 10. Development Order

Recommended implementation order:

```text
1. Add embedding.py with embed_document() and embed_query() utilities
2. Add qdrant_service.py with ensure_collection(), upsert_document_chunks(), search_similar_chunks()
3. Add query_service.py with tenant-isolated search
4. Add batch progress tracking and resume logic
5. Add verification helper and cutover integration with activate_rag_index_version()
6. Add error handling and retry utility
7. Write unit tests: embedding validation, UUID determinism, filter logic
8. Write integration tests: stage → embed → upsert → cutover → query
9. Run existing backend tests to confirm no regression
10. Manual smoke: upload a small PDF, verify it becomes searchable
```

Why this order works:

```text
Embedding utilities first     |
    v                         |
Qdrant upsert second          |  MySQL is already ready from Phase 3
    v                         |
Search with filters third     |  Tenant isolation is the new capability
    v                         |
Cutover integration last      |  Needs both embedding and Qdrant working
```

If the embedding utility is wrong, it is cheaper to fix before worker code depends on it.

## 11. Commands

From backend:

```powershell
cd D:\Personal_Knowledge_Base\backend
```

Run targeted tests:

```powershell
uv run pytest tests/services/rag/test_embedding.py tests/services/rag/test_qdrant.py tests/services/rag/test_cutover.py
```

Run broader backend tests:

```powershell
uv run pytest
```

Check imports:

```powershell
uv run python -c "from app.services.rag.embedding import embed_document, embed_query; from app.services.rag.qdrant_service import upsert_document_chunks, search_similar_chunks; from app.services.rag.query_service import search_similar_chunks; print('Phase 4 imports ok')"
```

Expected:

```text
Phase 4 imports ok
```

## 12. Code Review Checklist

Before marking Phase 4 complete, review these items:

```text
[ ] embed_document() validates non-empty text and returns 768-dim vector
[ ] embed_query() uses task_type="RETRIEVAL_QUERY" 
[ ] Every vector length validated == 768 before Qdrant upsert
[ ] Chunk IDs are deterministic UUIDv5: uuid5(NAMESPACE_URL, "rag-chunk:{file_id}:{index_version}:{chunk_index}")
[ ] Qdrant collection has VectorParams(size=768, distance=Distance.COSINE)
[ ] Upsert uses acknowledged batches (wait for success before proceeding)
[ ] Batch size respecting RAG_EMBEDDING_BATCH_SIZE (default 64, max 128)
[ ] Worker concurrency bounded by RAG_EMBEDDING_CONCURRENCY
[ ] All Qdrant searches include mandatory user_id filter
[ ] File/version filters resolved from MySQL before passing to Qdrant
[ ] Retry only on timeouts, 429, retryable 5xx with exponential backoff + jitter
[ ] Max retries RAG_MAX_RETRIES (default 5)
[ ] Idempotent upsert: same point_id overwrites, not duplicates
[ ] activate_rag_index_version() verifies chunk count before cutover
[ ] activate_rag_index_version() increments corpus_revision in same transaction
[ ] After cutover, queries filter by active_index_version
[ ] Old version vectors cleaned up asynchronously after grace period
[ ] No chunk text stored in Qdrant payload (only user_id, file_id, index_version, chunk_index)
[ ] Corpus revision increment invalidates answer cache keys
[ ] Cross-tenant isolation: User A cannot see User B's results
[ ] Existing metadata vector search still works
[ ] Tests cover embedding validation, UUID determinism, filter logic, cutover, tenant isolation
```

## 13. Phase 4 Definition of Done

Phase 4 is complete when:

- `embed_document(chunk_text)` returns 768-dim Gemini `gemini-embedding-2` vector
- `embed_query(question_text)` returns 768-dim vector with `task_type="RETRIEVAL_QUERY"`
- Upsert Qdrant points in bounded batches with deterministic UUIDv5 point IDs
- Every vector length validated == 768 before Qdrant upsert
- All Qdrant searches include mandatory `user_id` filter (tenant isolation)
- File/version filters resolved from MySQL before passing to Qdrant
- Retry only on timeouts, 429, retryable 5xx with exponential backoff and jitter
- Max retries bounded by `RAG_MAX_RETRIES`
- Idempotent upsert: same point ID overwrites, not duplicates
- `activate_rag_index_version()` verifies chunk count before cutover
- `activate_rag_index_version()` increments corpus_revision in same transaction
- After cutover, queries filter by `active_index_version` correctly
- Old version vectors remain until explicitly cleaned asynchronously
- No chunk text stored in Qdrant payload (only 4 fields: user_id, file_id, index_version, chunk_index)
- `corpus_revision` increment invalidates answer cache keys
- Cross-tenant isolation: User A cannot see User B's results
- Unit tests cover: embedding validation, UUID determinism, filter logic, retry, cutover
- Integration tests prove stage → embed → upsert → cutover → query flow
- Existing metadata vector search is not broken
- Streamlit can upload, observe progress, and query grounded answers

## 14. Handoff to Phase 5

Phase 4 hands Phase 5 this searchable state:

```text
Qdrant collection document_chunks_v1
|
+-- 768-dimensional Gemini gemini-embedding-2 vectors
+-- Deterministic point IDs: uuid5(NAMESPACE_URL, "rag-chunk:{file_id}:{index_version}:{chunk_index}")
+-- Tiny payloads: {user_id, file_id, index_version, chunk_index}
+-- Tenant-isolated: every point has user_id, filtered in all queries
+-- Active version: file_metadata.active_index_version points to current version

Phase 5 will:
1. Authenticate and validate optional file IDs against MySQL ownership/current versions
2. Normalize request for cache identity: {user_id}:{corpus_revision}:{query_hash}
3. Redis calls with short timeouts; on error continue (fail open)
4. On cache miss: embed with RETRIEVAL_QUERY, retrieve bounded candidate pool,
   hydrate with one-query pattern, score-filter, deduplicate, cap per-file contribution,
   fit fixed context budget
5. If no usable chunks remain, return insufficiency response without calling generation
6. Otherwise label each source with chunk_id, filename, and pages;
   validate each generated citation against retrieved IDs before caching
7. Stream Gemini generation with SSE token stream + final diagnostics event
```

That is the handoff: Phase 4 makes chunks searchable in Qdrant; Phase 5 returns grounded answers with citations.