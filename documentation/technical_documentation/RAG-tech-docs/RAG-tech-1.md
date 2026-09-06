# Phase 4 — Gemini Embeddings and Qdrant Index

**Technical Documentation**

> **The central invariant:** A query must only ever use a complete active version. Never expose a half-written chunk version to retrieval.

---

## Table of Contents

1. [Phase Overview](#1-phase-overview)
2. [Configuration Layer](#2-configuration-layer)
3. [Embedding Utilities](#3-embedding-utilities)
4. [Qdrant Upsert Service](#4-qdrant-upsert-service)
5. [Tenant-Isolated Query Service](#5-tenant-isolated-query-service)
6. [Batch Progress and Resume](#6-batch-progress-and-resume)
7. [Versioned Index Cutover](#7-versioned-index-cutover)
8. [Retry and Error Handling](#8-retry-and-error-handling)
9. [Public API Exports](#9-public-api-exports)
10. [Testing Strategy](#10-testing-strategy)
11. [Phase 4 Definition of Done](#11-phase-4-definition-of-done)

---

## 1. Phase Overview

### What Phase 4 Does

Phase 3 left us with durable, versioned chunks stored in MySQL (`document_chunks` table). Those chunks exist but are **not searchable** — nothing knows their vector representation yet. Phase 4 bridges that gap: it takes those staged chunks, generates Gemini `gemini-embedding-2` vectors (768-dimensional, cosine distance), and makes them searchable in a tenant-isolated Qdrant collection.

### The Invariant

```
BEFORE CUTOVER:          AFTER CUTOVER:
active_index_version = 1     active_index_version = 2
queries see v1               queries see v2
v2 vectors building...       v1 vectors still alive (cleanup later)
                           ^^^ single atomic transaction
```

```
+--------------------------------------------------+
|              QUERY TIME                           |
|                                                   |
|   SELECT * FROM document_chunks                   |
|   WHERE index_version = active_index_version      |
|                                                   |
|   active_index_version = 1  -->  sees v1 (complete)|
|   active_index_version = 2  -->  sees v2 (complete)|
|   NEVER: a mix of v1 and v2 chunks                |
+--------------------------------------------------+
```

### Architecture Flow

```
INGESTION (async worker)
+----------+     +--------------------+    +-------------------+
| Upload / | --> | file_metadata row  | -->| B2/S3 byte stream |
| FastAPI  |     | status=PENDING     |    | bounded in memory |
+----------+     +--------------------+    +-------------------+
                                                             |
                                                    PyMuPDF extraction
                                                             |
                                                    +---------+----------+
                                                    | clean + 800/100    |
                                                    | word chunker        |
                                                    +---------+----------+
                                                             |
                                                    MySQL transaction v
+----------+   active version pointer  +---------------------+         v
| MySQL    | <----------------------- | document_chunks     |  +-------------+
| file     |                           | (full cleaned text) |  | Gemini      |
| metadata |                           +---------------------+  | embeddings  |
| source   |                                           |       +------+------+
| of truth |                                           |              |
+----------+                                           |              v
           |                                    UUIDv5 + minimal payload  |
           +----------------------------------------------------------> +------------------+
                                                                    | Qdrant         |
                                                                    | document_      |
                                                                    | chunks_v1      |
                                                                    | vector index   |
                                                                    +------------------+

RETRIEVAL
+-------------+   authenticated request   +-----------+ cache miss  +------------------+
| Streamlit   | ------------------------> | FastAPI   | -----------> | Gemini query     |
| app.py      | <--- SSE answer stream ---| RAG route |              | embedding        |
+------+------+                           +-----+-----+              +--------+---------+
        |                                        |                             |
        | upload/status/chunks                   | Redis (fail-open)            v
        +----------------------------------------+  answer cache       +------------------+
                                                            |           | Qdrant filter:  |
                                                            v           | user + versions |
                                                     cache hit or       +--------+---------+
                                                     live answer                 |
                                                                            point payloads
                                                                                  v
                                                                      +---------------------+
                                                                      | one MySQL hydration |
                                                                      | query, then Gemini  |
                                                                      +---------------------+
```

### Why Phase 4 Exists

Without this phase, chunks are stored in MySQL but **invisible to search**. Phase 3 guarantees durability and versioning. Phase 4 makes those chunks *findable* by the same user who owns them, while ensuring queries always see a complete, consistent version of the index.

**What happens if you skip this:** Users upload PDFs, chunks get stored, but no search results ever return. The pipeline is incomplete — data exists but is not retrievable.

---

## 2. Configuration Layer

### Files

- `backend/app/core/config.py` — Pydantic `Settings` class, loads from `others/.env`
- `backend/app/services/rag/config.py` — Phase 4 constants derived from `Settings`

### What Was Added

| Setting | Type | Default | Constraint | Purpose |
|---|---|---|---|---|
| `RAG_EMBEDDING_BATCH_SIZE` | int | 64 | `1 <= x <= 128` | Number of chunks per Qdrant upsert batch |
| `RAG_EMBEDDING_CONCURRENCY` | int | 4 | `1 <= x <= 32` | Bounded worker concurrency |
| `RAG_MAX_RETRIES` | int | 5 | `0 <= x <= 10` | Maximum retry attempts per batch |
| `RAG_BACKOFF_BASE` | float | 1.0 | `0.0 <= x <= 10.0` | Base delay for exponential backoff |
| `RAG_QDRANT_COLLECTION` | str | `None` | alias | Typo-tolerant alias for `RAG_QDANT_COLLECTION` |
| `RAG_QDANT_COLLECTION` | str | `None` | alias | Typo-tolerant alias |

Also present from earlier phases (kept): `GEMINI_EMBEDDING_MODEL=gemini-embedding-2`, `EMBEDDING_DIMENSIONS=768`, `QDRANT_RAG_COLLECTION_NAME=document_chunks_v1`, `QDRANT_DISTANCE=COSINE`.

### Why These Defaults

The Phase 4 plan specifies `RAG_EMBEDDING_BATCH_SIZE` default 64, max 128, and `RAG_MAX_RETRIES` default 5. Existing code had `GEMINI_EMBEDDING_BATCH_SIZE=16` and `GEMINI_EMBEDDING_MAX_RETRIES=3`. Batch size 16 is too small — it creates too many network round-trips to Gemini and Qdrant. Retry count 3 may not be enough for transient 429 rate limits during peak loads.

### Legacy-to-Canonical Sync

The `model_validator` in `config.py` keeps old and new fields in sync without breaking existing deployments that set `GEMINI_EMBEDDING_BATCH_SIZE` via `.env`:

```python
@model_validator(mode="after")
def validate_rag_settings(self) -> "Settings":
    # If canonical not explicitly set, derive from legacy env value
    if self.RAG_EMBEDDING_BATCH_SIZE == 64 and self.GEMINI_EMBEDDING_BATCH_SIZE != 64:
        object.__setattr__(self, "RAG_EMBEDDING_BATCH_SIZE", self.GEMINI_EMBEDDING_BATCH_SIZE)
    if self.RAG_MAX_RETRIES == 5 and self.GEMINI_EMBEDDING_MAX_RETRIES != 5:
        object.__setattr__(self, "RAG_MAX_RETRIES", self.GEMINI_EMBEDDING_MAX_RETRIES)
    # Alias collection names for Phase 4 doc compatibility
    alias = self.RAG_QDRANT_COLLECTION or self.RAG_QDANT_COLLECTION
    if alias:
        object.__setattr__(self, "QDRANT_RAG_COLLECTION_NAME", alias)
    return self
```

**Why this matters:** A fresh deploy gets 64/5 defaults. An existing deploy with `GEMINI_EMBEDDING_BATCH_SIZE=16` in `.env` automatically gets `RAG_EMBEDDING_BATCH_SIZE=16` — no manual migration needed.

### `backend/app/services/rag/config.py` — Single Source of Truth

This new file centralizes Phase 4 constants so embedding and qdrant services share the same values without importing from `core.config` repeatedly:

```python
EXPECTED_VECTOR_SIZE: int = 768
GEMINI_EMBEDDING_MODEL: str = settings.GEMINI_EMBEDDING_MODEL  # "gemini-embedding-2"
EMBEDDING_DIMENSIONS: int = settings.EMBEDDING_DIMENSIONS      # 768
QDRANT_COLLECTION: str = settings.QDRANT_RAG_COLLECTION_NAME   # "document_chunks_v1"
EXPECTED_QDRANT_VECTOR_PARAMS = VectorParams(size=768, distance=Distance.COSINE)
RAG_EMBEDDING_BATCH_SIZE: int = settings.RAG_EMBEDDING_BATCH_SIZE
RAG_MAX_RETRIES: int = settings.RAG_MAX_RETRIES
RAG_BACKOFF_BASE: float = settings.RAG_BACKOFF_BASE
```

**What happens if you skip this:** Embedding code hardcodes `768` in multiple places. If Gemini ever changes dimensions, you'd have to grep-and-replace across files instead of changing one constant.

---

## 3. Embedding Utilities

### File

`backend/app/services/rag/embedding.py`

### What It Does

Generates 768-dimensional vectors via Gemini `gemini-embedding-2` with strict task-type separation:

- **`embed_document(chunk_text)`** → `task_type="RETRIEVAL_DOCUMENT"` (for chunk vectors)
- **`embed_query(question_text)`** → `task_type="RETRIEVAL_QUERY"` (for user questions)

### Why Two Separate Functions

Gemini's embedding API treats documents and queries differently. A document embedding is optimized for *content matching* (what is this text about?). A query embedding is optimized for *intent matching* (what is the user looking for?). Using the wrong task type degrades retrieval quality — queries embedded as documents return fewer relevant chunks, and vice versa.

### Guard Chain

Every embedding call follows a strict validation pipeline:

```
text input
    |
    v
_validate_non_empty(text, label)
    |  raises ValueError if empty/whitespace
    v
client.models.embed_content(
    model=GEMINI_EMBEDDING_MODEL,
    contents=text,
    config=EmbedContentConfig(task_type=..., output_dimensionality=768)
)
    |
    v
_validate_vector(vector)
    |  raises RuntimeError if len(vector) != 768
    v
return vector
```

### Why Validate Before and After

- **Before (empty guard):** Gemini charges per API call. An empty string still costs money and returns garbage. Raising `ValueError` before the call saves quota.
- **After (dimension check):** Network issues or Gemini model changes could return a wrong-sized vector. Storing a 1024-dim vector in a 768-dim collection corrupts the index. Raising `RuntimeError` prevents silent corruption.

**What happens if you skip the empty guard:** You waste API quota on empty requests. In a batch of 200 chunks where 5 are empty, that's 5 wasted calls × ~$0.0001 each. Small, but multiplied across thousands of files it adds up.

**What happens if you skip the dimension check:** A corrupted vector gets upserted to Qdrant. When a user searches, cosine similarity with a wrong-dimensional vector either errors or returns garbage results. The user sees no answers and blames the system.

### Singleton Client

```python
_gemini_client: genai.Client | None = None

def _get_gemini_client() -> genai.Client:
    global _gemini_client
    if _gemini_client is not None:
        return _gemini_client
    if not settings.GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY is not configured")
    _gemini_client = genai.Client(api_key=settings.GEMINI_API_KEY)
    return _gemini_client
```

This mirrors the pattern in `app/services/AI/vector_service.py` (lines 26-51) but uses the synchronous `genai.Client` instead of the async version. The singleton avoids creating a new client for every chunk (expensive SSL handshake).

**What happens if you create a new client per chunk:** Each `embed_document` call creates a new `genai.Client`, opening a new HTTP connection to Gemini. For 200 chunks, that's 200 connection handshakes. Latency goes from ~200ms/chunk to ~50ms/chunk + 200ms handshake = 50 seconds instead of ~40 seconds. Worse, rate limits trigger faster because each client is a separate "session."

---

## 4. Qdrant Upsert Service

### Files

- `backend/app/services/rag/schemas.py` — Added `ChunkPayload` model
- `backend/app/services/rag/qdrant_service.py` — New file (~600 lines)

### The Tiny Payload Principle

Qdrant payloads contain **only 4 fields** — never chunk text:

```python
class ChunkPayload(BaseModel):
    """Tiny Qdrant payload — only 4 fields. Text stays in MySQL."""
    user_id: int
    file_id: int
    index_version: int = Field(ge=1)
    chunk_index: int = Field(ge=0)
```

**Why:** Qdrant is a vector index, not a document store. Storing text in payloads wastes memory, increases network transfer, and leaks chunk content if someone queries Qdrant directly. MySQL `document_chunks.clean_text` is the source of truth. Qdrant only needs enough metadata to *find* the right chunk — MySQL hydrates the content.

**What happens if you store text in Qdrant:** Every search returns full chunk text over the network. For 6 results × 800 words each, that's ~4800 words of unnecessary data transfer per query. More importantly, if someone gains Qdrant access, they read all your document content without authentication.

### Deterministic Point IDs

Each Qdrant point gets a deterministic UUIDv5 ID:

```
point_id = uuid5(NAMESPACE_URL, f"rag-chunk:{file_id}:{index_version}:{chunk_index}")
```

This means the same `(file_id=42, index_version=1, chunk_index=0)` always produces the same UUID. For example:

```python
build_chunk_id(42, 1, 0)
# Always returns: UUID('b9bf4553-8637-580e-aa9a-c38b706ee9ed')
```

**Why deterministic IDs matter for retries:** If batch 3 of 5 fails mid-upsert and you retry, the same point IDs are sent again. Qdrant's upsert is idempotent — same ID overwrites the existing point rather than creating a duplicate. Without deterministic IDs, a retry would create a second point with a different ID, corrupting search results.

**What happens if you use random UUIDs:** Retry creates duplicates. User searches and gets the same chunk twice in results. Or worse, Qdrant returns `N` results but `N+1` IDs exist in the collection, confusing downstream pagination.

### Bounded Batches

```python
def _batch_chunks(chunks: list, size: int) -> Iterable[list]:
    """Yield successive n-sized chunks."""
    for i in range(0, len(chunks), size):
        yield chunks[i : i + size]
```

Batches default to `RAG_EMBEDDING_BATCH_SIZE=64`, clamped to max 128. This respects Gemini's per-request limits and Qdrant's upsert performance characteristics. Too large a batch risks timeout on either end; too small creates excessive round-trips.

### Retry Policy

Only three error categories are retryable:

| Status Code | Meaning | Retry? | Backoff |
|---|---|---|---|
| `429` | Rate limit | Yes | `base * 2^attempt + jitter` |
| Timeout | Connection/read timeout | Yes | `base * 2^attempt + jitter` |
| `500-599` | Server error | Yes | `base * 2^attempt + jitter` |
| Dimension mismatch | Vector length != 768 | **No** | Fail fast |
| Collection mismatch | Size/distance wrong | **No** | Fail fast |
| Validation error | Bad input | **No** | Fail fast |

```python
delay = (settings.RAG_BACKOFF_BASE ** (attempt + 1)) + random.random()
time.sleep(delay)
```

**Why exponential backoff with jitter:** If 100 workers all hit a 429 simultaneously and all retry at exactly `base * 2^attempt`, they thunder again at the same instant — making the 429 worse. Adding `random.random()` (0 to 1 second) staggers retries so they don't all collide on the second attempt.

**Why fail fast on dimension mismatch:** A 768-dim vector in a 768-dim collection works. A 1024-dim vector will *never* work no matter how many times you retry. Retrying wastes API calls and delays the entire pipeline. Logging the error and moving on is faster.

**What happens if you retry dimension mismatches:** You burn Gemini quota on vectors that will never fit. For 200 chunks with 10 bad ones, that's 10 extra API calls that always fail. Worse, if the pipeline blocks on the first failure, the entire file's indexing stalls.

### Collection Guard (`ensure_collection`)

At startup (called from `main.py` lifespan), `ensure_collection()` verifies the Qdrant collection matches the expected schema:

```
Collection exists?
    |
    +-- No --> Create with VectorParams(size=768, distance=COSINE) + payload indexes
    |
    +-- Yes --> Get config.params.vectors
                |
                +-- size != 768 --> raise RuntimeError
                +-- distance != COSINE --> raise RuntimeError
                +-- OK --> proceed
```

**Why check at startup, not at write time:** If someone accidentally creates a `document_chunks_v1` collection with `size=1536` (maybe from an old experiment), the system should fail *before* writing any data. Otherwise you'd write 768-dim vectors to a 1536-dim collection and get silent failures or errors at write time with partial data already in the index.

---

## 5. Tenant-Isolated Query Service

### File

`backend/app/services/rag/query_service.py`

### The Security Invariant

**Every** Qdrant search must include a mandatory `user_id` filter. Cross-tenant result leakage is a security violation. Period.

```python
qfilter = Filter(must=[
    FieldCondition(key="user_id", match=MatchValue(value=user_id)),
])
```

No exceptions. No configuration flags to disable it. No "for development only" bypasses.

### How File/Version Filters Work

When a user specifies `file_ids=[10, 20]`, those IDs must already be validated against MySQL ownership *before* reaching Qdrant:

```python
def _build_tenant_filter(user_id: int, file_ids: list[int] | None) -> Filter:
    must = [FieldCondition(key="user_id", match=MatchValue(value=user_id))]
    if file_ids:
        if len(file_ids) == 1:
            must.append(FieldCondition(key="file_id", match=MatchValue(value=file_ids[0])))
        else:
            must.append(FieldCondition(key="file_id", match=MatchAny(any=file_ids)))
    return Filter(must=must)
```

- **Single file:** `MatchValue(value=42)` — uses a simple equality index
- **Multiple files:** `MatchAny(any=[1, 2, 3])` — uses an `any` filter for multi-value matching

### Why MySQL Ownership Validation First

Never trust client-provided `file_ids` directly. A malicious user could send `file_ids=[999]` where file 999 belongs to another user. The calling route must verify `SELECT user_id FROM file_metadata WHERE id = 999` returns the authenticated user's ID *before* passing it to `search_similar_chunks`.

**What happens if you skip MySQL validation:** User A searches with `file_ids=[user_b_file_id]`. Qdrant has a vector for that file (belonging to User B). The search returns User B's chunks to User A. That's a cross-tenant data leak — a security vulnerability.

### Rank Preservation

Qdrant returns results ranked by cosine similarity. SQL `IN (...)` has no ordering guarantee. So we capture rank before hydration and sort after:

```python
# Before DB query — capture rank map
ranks = {hit["chunk_id"]: (hit["rank"], hit["score"]) for hit in ranked_hits}

# After SQL query — sort by original Qdrant rank
hydrated.sort(key=lambda row: ranks[row["chunk_id"]][0])
```

**Why:** Without this, results are sorted by `chunk_id` (alphabetical) or by MySQL row order (arbitrary). The most similar chunks might appear at the bottom of the list. Users see irrelevant answers first.

### Query Parameters

| Parameter | Default | Cap | Purpose |
|---|---|---|---|
| `top_k` | `RAG_DEFAULT_TOP_K=6` | max 20 | Number of results to return |
| `score_threshold` | `RAG_SCORE_THRESHOLD=0.35` | 0.0–1.0 | Minimum cosine similarity |

`top_k` is capped to `RAG_MAX_TOP_K=20` to prevent abuse (a request for `top_k=10000` would scan the entire index).

---

## 6. Batch Progress and Resume

### Files Modified

`backend/app/services/rag/qdrant_service.py` (appended helpers)

### The Resume Problem

Imagine upserting 200 chunks in batches of 64. Batch 1 and 2 succeed. Batch 3 (chunks 128–191) fails with a 429 rate limit that persists after all retries. Without resume logic, the pipeline either:

1. **Fails the entire file** — chunks 0–127 are already in Qdrant, but the file is marked failed. Waste.
2. **Re-upserts everything** — chunks 0–127 get upserted again (safe, since UUIDv5 is idempotent), but Gemini quota is wasted re-embedding 128 chunks that already have vectors.

### The Resume Solution

Three helpers enable smart retry:

```
1. get_existing_chunk_indexes(user_id, file_id, index_version)
   → Scrolls Qdrant with tenant filter, returns {0, 1, 2, ..., 127}

2. filter_pending_chunks(all_chunks, existing_set)
   → Removes already-upserted indexes, returns chunks 128–199

3. upsert_with_resume(user_id, file_id, index_version, all_chunks)
   → Calls get_existing → filter → upsert_document_chunks(pending)
   → If pending is empty → returns {skipped: 128} without re-embedding
```

### Why Scroll with Tenant Filter

`get_existing_chunk_indexes` uses Qdrant's `scroll` API filtered by `(user_id, file_id, index_version)`. This ensures we only check chunks belonging to the current user — a cross-tenant scroll would be a security issue.

**What happens if you skip the resume check:** Every retry re-embeds all chunks. For a 1000-chunk file with a mid-way failure, that's ~500 wasted Gemini embedding calls per retry. At $0.0001/embed, that's $0.05 per retry. For 1000 files × 3 retries each, that's $150 in wasted quota monthly.

**What happens if you skip the idempotency guarantee:** Without deterministic UUIDv5 IDs, re-upserting creates duplicates instead of overwrites. The collection grows unbounded. Search returns duplicate chunks. Pagination breaks.

---

## 7. Versioned Index Cutover

### File

`backend/app/services/rag/indexing_service.py`

### The Three Functions

| Function | Role | Transaction? |
|---|---|---|
| `build_new_version_vectors(db, file, index_version)` | Fetch staged chunks → embed → upsert to Qdrant | No (network calls outside DB) |
| `verify_and_cutover(db, file, index_version, upsert_result)` | Verify count → single TX activate + corpus_revision++ | Yes (short) |
| `run_full_indexing(db, file, index_version)` | Convenience wrapper: build → verify → cutover | Mixed |

### Zero-Downtime Flow

```
Time:  T0          T1          T2          T3          T4
       |           |           |           |           |
       v           v           v           v           v
active=v1     active=v1     active=v1     active=v2     active=v2
v2 in MySQL   v2 in Qdrant  verify count  activate      queries see v2
(staged)     (vectors)     PASS          (single TX)
                                   |
                                   v
                          corpus_revision += 1
                          indexed_chunk_count = total
                          file.indexing_status = INDEXED
```

- **T0–T1:** Chunks staged in MySQL via `stage_document_chunks()` (Phase 3). `active_index_version` still 1. Old version serves queries.
- **T1–T2:** `build_new_version_vectors` embeds + upserts v2 to Qdrant. `active_index_version` still 1. Old version serves queries.
- **T2:** `verify_qdrant_index` checks Qdrant count == MySQL `chunk_count`. If mismatch → fail, no DB change.
- **T2–T3:** `activate_rag_index_version` in a single short transaction:
  - `active_index_version = 2`
  - `indexed_chunk_count = total`
  - `indexing_status = INDEXED`
  - `corpus_revision += 1`
- **T3+:** Queries see v2. Old v2 vectors remain in Qdrant until async cleanup.

### The Activate Transaction

```python
def activate_rag_index_version(db, file, index_version, indexed_chunk_count):
    chunk_count = db.query(DocumentChunk).filter(...).count()
    if chunk_count == 0: raise ValueError("zero chunks")
    if indexed_chunk_count != chunk_count: raise ValueError("count mismatch")

    state = db.get(UserCorpusState, file.userid) or create(corpus_revision=0)
    state.corpus_revision += 1

    file.active_index_version = index_version
    file.indexed_chunk_count = indexed_chunk_count
    file.indexing_status = IndexingStatus.INDEXED.value
    file.indexing_completed_at = datetime.now(timezone.utc)
    file.corpus_revision = state.corpus_revision

    db.commit()
```

**Why validate before committing:** The invariant "complete version or nothing" means we must verify every chunk is in Qdrant *before* making it visible. If Qdrant has 95 of 100 chunks, activating would make 5 chunks invisible to users — they'd see incomplete search results.

**Why increment `corpus_revision`:** This is the key that invalidates Redis answer cache keys. Cache keys follow the pattern `{user_id}:{corpus_revision}:{query_hash}`. Incrementing `corpus_revision` makes all previous cache keys unreachable without scanning Redis. Old keys expire via TTL.

**Why cleanup is async and non-fatal:** After cutover, old version vectors can be deleted. But if Qdrant delete fails (network blip), the old vectors just stay — they're harmless because queries filter by `active_index_version=2`, so old vectors are never returned. Cleanup is logged and retried later.

### What Happens if You Activate Before Verification

Queries suddenly see `active_index_version=2`. But Qdrant only has 90 of 100 vectors. Users search and get incomplete results — some chunks return nothing, others return stale data. They think the system is broken. Trust is lost.

### What Happens if You Skip corpus_revision Increment

Old answer cache keys remain valid. A user's cached answer from v1 is served even though v2 is now active. They get stale, outdated answers. The cache key `{user_id}:{corpus_revision=1}:{query_hash}` still matches — no invalidation occurs.

---

## 8. Retry and Error Handling

### File

`backend/app/services/rag/retry.py`

### Error Code Table

| Error Code | Meaning | Retry? | Example |
|---|---|---|---|
| `EMBEDDING_TIMEOUT` | Gemini API timeout | Yes | `genai.types.TimeOut` |
| `EMBEDDING_429` | Gemini rate limit | Yes | `response.status_code == 429` |
| `EMBEDDING_5XX` | Gemini server error | Yes | `code >= 500 and code < 600` |
| `EMBEDDING_DIM_MISMATCH` | Vector length != 768 | No | `len(vector) != 768` |
| `QDRANT_UPSERT_FAILED` | Qdrant upsert error | Maybe | depends on `is_retryable` |
| `QDRANT_COLLECTION_MISMATCH` | Dimension/distance wrong | No | `size != 768` |

### Classification Order

```python
def classify_error(exc):
    if is_timeout(exc): return ERROR_EMBEDDING_TIMEOUT       # check first
    code = extract_status_code(exc)
    if code == 429: return ERROR_EMBEDDING_429
    if 500 <= code < 600: return ERROR_EMBEDDING_5XX
    # Collection MUST be checked before dimension because
    # "collection size 1536 expected 768" contains BOTH "collection" and "768"
    if "collection" in msg and ("size" in msg or "distance" in msg):
        return ERROR_QDRANT_COLLECTION_MISMATCH
    if "dimension" in msg or "768" in msg:
        return ERROR_EMBEDDING_DIM_MISMATCH
    return ERROR_QDRANT_UPSERT_FAILED
```

**Why collection before dimension:** A message like `"Qdrant collection 'document_chunks_v1' has vector size 1536; expected 768"` contains both `"collection"` and `"768"`. If dimension is checked first, it incorrectly classifies as `EMBEDDING_DIM_MISMATCH` when it's actually a collection configuration problem requiring different action (fix the collection, not the embedding).

### with_retry Implementation

```python
def with_retry(fn, max_retries=None, base_delay=None, jitter=True):
    max_retries = max_retries or settings.RAG_MAX_RETRIES
    base_delay = base_delay or settings.RAG_BACKOFF_BASE

    for attempt in range(max_retries + 1):
        try:
            return fn()
        except Exception as exc:
            if not is_retryable(exc) or attempt >= max_retries:
                raise
            delay = (base_delay * (2 ** attempt)) + (random.random() if jitter else 0)
            time.sleep(delay)
```

**What happens if you retry on 400 errors:** A 400 Bad Request means the request was malformed — the embedding text was too long, or the config was wrong. Retrying sends the same bad request and gets the same 400. You just waste quota and time. Fail fast, fix the input, retry once manually if needed.

**What happens if you retry on dimension mismatch:** Same chunk, same text, same model → same wrong dimension. Every retry produces a 768 check failure. Infinite loop of failures. Fail fast, investigate the root cause (maybe a model version mismatch).

---

## 9. Public API Exports

### File

`backend/app/services/rag/__init__.py`

```python
from app.services.rag.embedding import embed_document, embed_query
from app.services.rag.qdrant_service import (
    cleanup_old_version_vectors,
    ensure_collection,
    upsert_document_chunks,
    upsert_with_resume,
    verify_qdrant_index,
)
from app.services.rag.query_service import search_similar_chunks
from app.services.rag.indexing_service import run_full_indexing

__all__ = [
    "embed_document", "embed_query",
    "ensure_collection", "upsert_document_chunks", "upsert_with_resume",
    "verify_qdrant_index", "cleanup_old_version_vectors",
    "search_similar_chunks", "run_full_indexing",
]
```

### Why a Public API

Without this, every module that needs embedding imports from `embedding.py` directly, every module needing Qdrant imports from `qdrant_service.py`, etc. If internal structure changes (e.g., splitting `qdrant_service.py` into two files), every import path breaks. The `__init__.py` acts as a facade — internal structure can change without affecting consumers.

**What happens without it:** Each file has its own import path. Refactoring requires updating imports across 10+ files. Adding a new service means updating every consumer that imports from the rag package.

---

## 10. Testing Strategy

### Unit Tests (76 tests)

| Test File | What It Covers |
|---|---|
| `test_embedding.py` | Empty guard, 768 validation, `RETRIEVAL_DOCUMENT` vs `RETRIEVAL_QUERY`, dimension mismatch, no-embeddings case |
| `test_qdrant_service.py` | Deterministic UUIDv5, idempotent upsert, batch size clamp, 429 retry with jitter, non-retryable fail-fast, collection guard (768/COSINE), verify/cleanup filters, resume (`get_existing_chunk_indexes`, `filter_pending_chunks`, `upsert_with_resume`) |
| `test_query_service.py` | Mandatory `user_id` filter, `MatchValue` vs `MatchAny`, rank preservation, `top_k` cap to 20, empty query guard, cross-tenant isolation, `RETRIEVAL_QUERY` task type |
| `test_indexing_service.py` | Zero chunks guard, `verify_and_cutover` success/failure, corpus_revision increment, cleanup failure non-fatal, full `run_full_indexing` flow |
| `test_retry.py` | Status code extraction, timeout detection, retryable classification, `with_retry` success after retry, non-retryable fail fast |

### Integration Test (3 tests)

`test_phase4_integration.py` uses **real SQLite** for MySQL logic + **mocked Gemini/Qdrant** for external services:

| Test | Flow |
|---|---|
| `test_stage_embed_upsert_cutover_query` | Stage → build vectors → verify → cutover → search (same user) → search (cross-tenant empty) |
| `test_reindex_zero_downtime` | v1 active → stage v2 → verify v2 not active → cutover → verify v2 active + corpus_revision incremented |
| `test_batch_size_respected` | 5 chunks with batch_size=2 → verify 3 Qdrant upsert calls |

### Why Mock Gemini/Qdrant but Use Real SQLite

- **Mock external services:** No API keys in tests, fast execution (~ms per test), deterministic results. You control what Gemini returns (768-dim vector, 10-dim vector, timeout exception) without hitting the real API.
- **Real SQLite for MySQL:** The hydration SQL (`JOIN document_chunks ON file_metadata`), `activate_rag_index_version` validation (`chunk_count == indexed_chunk_count`), and `stage_document_chunks` logic need real SQL to verify correctness. Mocking SQL would hide bugs in query construction.

**What happens if you mock everything including SQLite:** You test that your mocks work, not that your SQL is correct. A typo in the `JOIN` clause would pass tests but fail in production with `OperationalError`.

---

## 11. Phase 4 Definition of Done

| Requirement | Implementation | Verification |
|---|---|---|
| `embed_document()` returns 768-dim vector | `embedding.py` with `_validate_vector` | `test_embedding.py` |
| `embed_query()` uses `RETRIEVAL_QUERY` | `embedding.py` task_type check | `test_embedding.py` |
| Every vector validated == 768 before upsert | `embed_document` + `upsert_document_chunks` double-check | `test_embedding.py`, `test_qdrant_service.py` |
| Deterministic UUIDv5 point IDs | `build_chunk_id()` via `ids.py` | `test_qdrant_service.py` |
| Qdrant collection `VectorParams(768, COSINE)` | `ensure_collection()` guard | `test_qdrant_service.py` |
| Bounded batches (64, max 128) | `RAG_EMBEDDING_BATCH_SIZE` + clamp | `test_qdrant_service.py` |
| Mandatory `user_id` filter in all searches | `_build_tenant_filter` in `query_service.py` | `test_query_service.py` |
| File/version filters resolved from MySQL | Route validates before calling `search_similar_chunks` | `test_phase4_integration.py` |
| Retry only on 429/timeout/5xx with backoff+jitter | `retry.py` `is_retryable` + `with_retry` | `test_retry.py` |
| Idempotent upsert (same ID overwrites) | UUIDv5 determinism + Qdrant upsert | `test_qdrant_service.py` |
| `activate_rag_index_version()` verifies count | `persistence.py` chunk_count == indexed_chunk_count | `test_persistence.py`, `test_indexing_service.py` |
| `corpus_revision` incremented in same TX | `persistence.py:191` | `test_indexing_service.py` |
| Old version vectors cleaned asynchronously | `cleanup_old_version_vectors` after cutover | `test_indexing_service.py` |
| No chunk text in Qdrant payload | `ChunkPayload` has only 4 fields | `test_qdrant_service.py` |
| Cross-tenant isolation | `user_id` mandatory filter | `test_query_service.py` |
| 232 tests pass | Full test suite | `uv run pytest -q` |
| `Phase 4 imports ok` | All public API imports | `uv run python -c "..."` |
