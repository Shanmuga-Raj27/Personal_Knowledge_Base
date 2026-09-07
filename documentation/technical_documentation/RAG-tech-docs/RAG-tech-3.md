# RAG Phase 6 — FastAPI Contracts, Worker Completion & Streamlit Playground

**Technical Documentation** — written incrementally as development progresses.

> Scope: backend RAG / AI implementation files only. All content reflects current, implemented reality. No planned features, no speculation.

---

## Phase 6 Goal (One Paragraph)

Phases 1–5 built the RAG engine as pure services and a script-driven orchestrator. Phase 6 gives it a **safe, authenticated HTTP surface** and a working client (the Streamlit playground) so a real user can upload a document, watch it index, inspect its chunks, and stream a grounded answer — without ever touching MySQL, Qdrant, Redis, B2/S3, or Gemini directly. The two biggest structural changes are: (1) the background worker now carries ingestion all the way to `INDEXED` (embed + Qdrant cutover), and (2) four new FastAPI endpoints expose the Phase 5 SSE event contract over HTTP.

```
Streamlit playground (thin client)
    |
    v  Bearer token
+---------------------------- FastAPI ----------------------------+
| POST    /rag/query                 -> SSE answer stream         |
| POST    /documents                 -> trigger indexing (202)    |
| GET     /documents/{id}/index-status -> indexing progress       |
| GET     /documents/{id}/chunks     -> chunk inspection          |
+-----------------------------------------------------------------+
    |
    v  services own all infra
MySQL / Qdrant / Redis / B2/S3 / Gemini
```

---

## Progress Tracker (live state)

| # | Task | Files | Status | Documented |
|---|------|-------|--------|------------|
| 1 | Extend worker: auto-complete indexing via `run_full_indexing` | `backend/app/workers/rag_worker.py` | Done | Section 1 |
| 2 | RAG status / chunk inspection schemas | `backend/app/services/rag/schemas.py` | Done | Section 2 |
| 3 | Inspection service (`get_index_status` / `get_chunks`) | `backend/app/services/rag/inspection.py` | Done | Section 3 |
| 4 | `/rag/query` SSE endpoint | `backend/app/apis/routes/rag_routes.py` | Done | Section 4 |
| 5 | `/documents` upload / status / chunks endpoints | `backend/app/apis/routes/rag_document_routes.py` | Done | Section 5 |
| 6 | Router registration | `backend/main.py` | Done | Section 6 |
| 7 | Streamlit playground | `backend/streamlit_app/app.py` | Done | Section 7 |
| 8 | Unit tests (inspection) | `tests/unit/services/rag/test_inspection.py` | Done | Section 8 |
| 9 | Integration tests (routes) | `tests/integration/routes/` | Done | Section 9 |
| 10 | Full regression | `uv run pytest` | Done | Section 10 |
| 11 | Semantic answer cache (paraphrase-aware) | not built yet | Planned | Section 11 |

---

## 1. Task 1 — Worker Completion: Staging + `run_full_indexing`

### How We Built It

Modified `backend/app/workers/rag_worker.py`. Before this change, `sync_rag_chunks_in_background` ended its life after `stage_document_chunks` — chunks were in MySQL (`CHUNKED` status) but no vectors existed in Qdrant, and `active_index_version` was unchanged. The only way to reach `INDEXED` was to manually call the Phase 5 smoke script.

The change adds **Step 6** after Step 5 (session close):

```
Step 1  atomic claim (PENDING/FAILED_RETRYABLE → EXTRACTING)
Step 2  load FileMetadata row
Step 3  process_pdf_from_storage() in threadpool   (Phase 2)
Step 4  stage_document_chunks()                     (Phase 3)
Step 5  commit + close session       ← releases DB lock
Step 6  NEW session:
        run_full_indexing(index_db, index_file)     (Phase 4)
        errors  → mark_rag_failure → FAILED_RETRYABLE
```

New import added:

```python
from app.services.rag.indexing_service import run_full_indexing
```

And a fresh `SessionLocal()` block guarded by try/except/finally, matching how the rest of the worker handles failure (`map_rag_exception` → `mark_rag_failure`).

### Why We Implemented It

The task list for Phase 6 says it plainly: "if the worker is wrong, no upload reaches INDEXED and every downstream test fails confusingly — so fix ingestion first."

The reason is architectural. `run_full_indexing` is deliberately **not** called inside the same transaction that stages chunks:

- **Short transactions keep the DB happy.** `run_full_indexing` internally runs embed + Qdrant upsert + verification + an atomic cutover transaction. Gemini calls can take seconds; holding a MySQL transaction across network I/O risks lock contention and long-running transactions.
- **A worker claimed the row already.** The status is `EXTRACTING` → `CHUNKED` before Step 6. If Step 6 crashes, the file must land in `FAILED_RETRYABLE` (not vanish silently) so a later run can pick it up — that's what the exception handler does via `mark_rag_failure`.
- **No double concurrency.** `run_full_indexing` calls Gemini embedding in bounded batches, and the whole worker body stays inside the existing `async with _embedding_semaphore:`. So even though we now run Phase 4 inside the worker, the `MAX_CONCURRENT_EMBEDDING_TASKS` cap still applies to the overall embedding load.

Design trade-offs considered:

| Option | Chosen? | Why not |
|---|---|---|
| Return `CHUNKED` and leave indexing to a separate runner | No | Would need a new scheduler/cron; manual orchestration defeats the "upload → INDEXED" goal |
| Run `run_full_indexing` inside the same `db` session | No | Long DB transaction held over Gemini/Qdrant calls |
| `run_full_indexing` in a fresh session | Yes | Short transactions; previous session already closed and committed |

### How It Works

At runtime, after the staging commit:

`index_db.query(FileMetadata).filter(FileMetadata.fileid == file_id).first()` re-reads the row (the new session has a fresh identity map). Then `run_in_threadpool(run_full_indexing, index_db, index_file)` runs the Phase 4 pipeline off the event loop — embedding makes sequential network calls with retries, so it must not block the async loop.

Two outcome paths:

```
success=True  →  file.INDEXED, active_index_version bumped, corpus_revision++
                     Qdrant verified == MySQL chunk_count
success=False →  run_full_indexing already set FAILED_RETRYABLE
                     (QDRANT_UPSERT_FAILED / QDRANT_VERIFY_FAILED codes)
exception     →  mark_rag_failure() with map_rag_exception() output
                     (FAILD_RETRYABLE / FAILED_TERMINAL depending on code)
```

The `finally: index_db.close()` guarantees the session always closes, even on exception — no leaked connections.

### Verification

- `uv run pytest tests/unit/services/rag/` → **216 passed** (existing suite; nothing depends on worker internals beyond what exists).
- `uv run python -c "from app.workers.rag_worker import sync_rag_chunks_in_background; ..."` → imports cleanly.

### Key Learnings

- **A worker is a pipeline, not a step.** The original worker was "Phase 2+3 only" by contract. Extending it to Phase 4 makes ingestion fully automatic — but only because `run_full_indexing`'s short-transaction design lets us call it from a fresh session safely.
- **Close-before-network, always.** Committing and closing the staging session before Phase 4 means the DB never holds a lock across Gemini/Qdrant I/O. The comment in the original code ("Do NOT call Qdrant/Gemini work here") was about *transaction scope*, not about forbidding it entirely.
- **Re-fetch after failure.** When the exception handler runs, the loaded `index_file` object may be in a stale/rolled-back state; re-querying by `file_id` before `mark_rag_failure` is safest.
- **Fail-stop beats silent success.** `mark_rag_failure` writes `FAILED_RETRYABLE` + an error code so the file is visible to the indexing recovery path instead of wedged in `EXTRACTING` forever.
- **Post-review fix (first end-to-end run):** the Step 5→6 log line read `db_file.active_index_version` *after* `db.commit()` + `db.close()`. Commit expires every loaded attribute and close detaches the instance, so that read raised `DetachedInstanceError` ("not bound to a Session"), killing the worker before Step 6 — files stayed `CHUNKED` forever, and `POST /rag/query` then 400'd on them (`validate_file_ids` requires `INDEXED`). Fix: capture `staged_version = db_file.active_index_version` *before* commit/close and log the captured int. Golden rule this exposed: **post-close reads on ORM instances are the same bug as post-close writes — capture what you need before releasing the session.**

---

## 2. Task 2 — RAG Status / Chunk Inspection Schemas

### How We Built It

Appended four Pydantic models to `backend/app/services/rag/schemas.py`, keeping them in the same module as the existing Phase 5 RAG schemas for cohesion:

| Model | Purpose |
|---|---|
| `RAGIndexVersionInfo` | Stats for one indexed version (used by status endpoint) |
| `RAGIndexStatusResponse` | Response body for `GET /documents/{id}/index-status` |
| `RAGChunkInspection` | One chunk view for `GET /documents/{id}/chunks` |
| `RAGChunkListResponse` | Response body for `GET /documents/{id}/chunks` |

Key fields:

```
RAGIndexStatusResponse
  ├── file_id, filename            identity
  ├── indexing_status              lifecycle: PENDING → … → INDEXED
  ├── active_index_version          current active version
  ├── corpus_revision               for cache-invalidation visibility
  ├── progress  (0.0–1.0)           derived from lifecycle (filled by inspection.py)
  ├── chunk_count / indexed_chunk_count
  └── rag_error_code / rag_error_message   (nullable)

RAGChunkInspection
  ├── chunk_id, chunk_index, index_version
  ├── page_start, page_end          (page range in the source PDF)
  ├── word_count, word_start, word_end
  ├── clean_text                     the normalized chunk text
  └── raw_text  (optional/nullable)  RAG stores NO raw_text column — optional
```

### Why We Implemented It

Phase 6 adds two "inspection" endpoints that did not exist before. They need **typed response envelopes** so that:

- **Routes stay thin.** A route that returns `RAGIndexStatusResponse` gives FastAPI validation + OpenAPI schema documentation for free; the handler just returns a dict and FastAPI validates/coerces it.
- **Tenant & internal data stay hidden.** The phase plan is explicit: do **not** expose `source_key`, `user_id`, or `embedding_model`/`embedding_dimensions` on the wire. The models contain only what a client with the document's `id` legitimately needs to see (pages, word counts, clean text).
- **The client progress bar gets a number.** `progress` is `0..1` with `Field(ge=0.0, le=1.0)` — a predictable value for the Streamlit progress bar; it's not stored, it's *derived* from `indexing_status` by `inspection.py` (Task 3).

Design choices:

- `raw_text` is `str | None = None` because the RAG pipeline stores only a `clean_text` column (Phase 3 design). The field exists for API-shape symmetry so clients can rely on the key being present even when always `None` today.
- `progress` is validated at the Pydantic boundary (`ge=0.0, le=1.0`), so a future bug in the lifecycle-mapping that produced `1.5` would fail fast at the route layer instead of rendering a broken bar.

### How It Works

```
GET /documents/{id}/index-status   ──▶ inspection.py get_index_status()   ──▶ RAGIndexStatusResponse
GET /documents/{id}/chunks         ──▶ inspection.py get_chunks()         ──▶ RAGChunkListResponse
                                            (data access)                     (typed wire envelope)
```

The schemas are pure Pydantic — no data access, no logic. They serialize the dicts that `inspection.py` (Task 3) returns, and they coerce/validate at the HTTP boundary.

### Verification

- `uv run python -c "from app.services.rag.schemas import RAGIndexStatusResponse, RAGChunkListResponse; print('ok')"` → **ok**
- Existing schema tests still pass: `tests/unit/services/rag/test_schemas.py` → **3 passed** (additive change, no regressions).

### Key Learnings

- **Response models are a security surface too.** What you *leave out* of a response model is as important as what you include. `source_key`, `user_id`, and embedding internals are deliberately absent — removing them at the model layer prevents accidental leaks even if a route later returns a full ORM object.
- **"Optional because it doesn't exist" is a deliberate contract.** `raw_text: str | None = None` tells clients "this key always exists; it may be null" — far more robust than omitting the field and forcing clients to handle `KeyError`.
- **Schema-first, service-second.** Defining the wire shape *before* writing `inspection.py` gives the data-access layer a target contract, so ordering bugs (missing field name, wrong type) surface at import/test time rather than at runtime. This matches how Phase 5 split `RAGQueryRequest` (wire) from `RAGRequest` (service).

---

## 3. Task 3 — Inspection Service (`inspection.py`)

### How We Built It

Created `backend/app/services/rag/inspection.py` — a small, infra-free module with two public functions plus one private helper:

```
inspection.py
├── get_index_status(db, user_id, file_id) -> dict | None
├── _progress_for(status) -> float              (private helper)
└── get_chunks(db, user_id, file_id, index_version=None) -> list[dict] | None
```

Design rule enforced by every function: **assign `None` to a query result before asserting on it**, because the module's contract is *"None means not-owned / not-found"* — which the routes translate into a 404.

### Why We Implemented It

The `/documents` inspection endpoints need to:

1. **Prove ownership before revealing anything.** Both functions filter `FileMetadata.fileid == file_id` **and** `FileMetadata.userid == user_id`. A foreign `file_id` returns `None`, so the route can return 404 *without leaking whether the file exists at all*.
2. **Keep route handlers thin.** If a route had to write SQLAlchemy queries inline, every new inspection surface would duplicate tenancy logic and drift. Centralizing it means the routes stay 3–5 lines and the SQL is unit-tested once.
3. **Derive, don't store, progress.** `progress` is not a column — it's mapped from the lifecycle string by `_progress_for()`. The client progress bar reads `0.0 … 1.0` no matter which state the file is in.

### How It Works

```
get_index_status(db, user_id, file_id)
  1  query FileMetadata WHERE fileid=file_id AND userid=user_id
  2  ── no row ──▶ return None            (route → 404)
  3  progress = _progress_for(indexing_status)
  4  return dict of the ten status fields (matches RAGIndexStatusResponse)

get_chunks(db, user_id, file_id, index_version=None)
  1  ownership check (same as above) ──▶ None if not owned
  2  target version = index_version  OR  fm.active_index_version
  3  query DocumentChunk WHERE file_id AND user_id AND index_version=target
  4  ORDER BY chunk_index  → list of dicts (raw_text intentionally omitted)
```

Lifecycle → progress map:

```
PENDING 0.0 · EXTRACTING 0.1 · CHUNKED 0.35
EMBEDDING 0.6 · INDEXING 0.85 · INDEXED 1.0
unknown/failed  → 0.0
```

`index_version=None` (the common client case) resolves to `active_index_version` — so chunk inspection always shows the **live** version unless the caller explicitly asks for an older one.

### Verification — Unit Tests

Created `backend/tests/unit/services/rag/test_inspection.py` (14 tests) using the repo's proven in-memory SQLite pattern:
- owned file returns correct status dict + all ten fields
- foreign file → `None`; absent file → `None`
- progress mapping for every lifecycle state + failed/unknown fallback → 0.0
- `rag_error_code` / `rag_error_message` surface when set
- chunks returned ordered by `chunk_index`, tenant-scoped, version-scoped
- `index_version=None` defaults to `active_index_version`
- owned-but-unindexed file returns `[]` (not `None`)
- user-2 file with its own chunks is invisible to user 1

Result: `uv run pytest tests/unit/services/rag/test_inspection.py` → **14 passed**.

> Two initial test failures were fixed during development: (1) a test-ID bug (`fileid=status + 100` concatenated a string), and (2) a real DB constraint — `document_chunks` has a unique `(file_id, index_version, chunk_index)` constraint, so "a foreign user's chunk on the same file" cannot exist; the tenant-scoping test now uses a second file owned by the second user.

### Key Learnings

- **`None` is a 3-in-1 sentinel.** Return value does triple duty: *not found*, *not owned*, and (for chunks) *no inspection available*. The route can map it to a single 404 without distinguishing — which is exactly what you want publicly.
- **Test against real schema constraints.** The unique `(file_id, index_version, chunk_index)` constraint silently invalidated my original "foreign chunk, same file" test scenario — a reminder that the DB enforces invariants tests should respect, not bypass.
- **Progress is presentation, not data.** Mapping a lifecycle string to a float keeps the status row clean and lets the client render a bar without logic of its own.
- **Version resolution defaulting is a fetch-away.** Reading `active_index_version` in the same ownership query means "give me the current chunks" costs exactly one extra WHERE clause, not a second round-trip.

---

## 4. Task 4 — `POST /rag/query` (SSE Streaming Endpoint)

### How We Built It

Created `backend/app/apis/routes/rag_routes.py` plus registered the router in `backend/main.py`:

```
rag_routes.py
├── router = APIRouter(prefix="/rag", tags=["rag"])
├── _event_stream(request, user_id, payload, db)   async generator → SSE frames
└── @router.post("/query")  rag_query()            auth + validate + StreamingResponse
```

Router registration (in `main.py`):

```python
from app.apis.routes.rag_routes import router as rag_router
app.include_router(rag_router)          # adds POST /rag/query
```

The endpoint is thin by construction — it authenticates, validates, and delegates. No Qdrant/Gemini/Redis/raw-SQL anywhere in the handler.

### Why We Implemented It

Phase 5 built `run_rag_query()` as an async generator producing `{type:"token"}` / `{type:"final"}` dicts, but nothing exposed that contract over HTTP. This endpoint is the production wire contract Phase 8's React chat will consume. Three requirements drove the design:

1. **Streaming, not buffered JSON.** A RAG answer takes seconds. Feeding Qdrant-search → Gemini-generation into a single JSON blob would make users stare at a spinner. SSE pipes each token out the moment Gemini produces it.
2. **Identity must never arrive from the body.** `RAGQueryRequest` (wire model) has no `user_id`. The route injects `current_user.id` into the service `RAGRequest` at the boundary — the Phase 5 split made concrete.
3. **Fail fast, fail clean.** Bad `file_ids` should 400 *before* the stream starts, and mid-stream failures must not leak an SQLAlchemy traceback as a "successful" 200 body.

### How It Works

```
POST /rag/query  (bearer token + {question, top_k, score_threshold, file_ids})
  1  get_current_user               JWT → User row (401 if missing/invalid)
  2  validate_file_ids(user_id, file_ids, db)   pre-stream
        └ raises ValueError ──▶ 400 immediately   (no stream ever starts)
  3  return StreamingResponse(...)
        ├─ headers: Cache-Control: no-cache, Connection: keep-alive,
        │           X-Accel-Buffering: no
        └─ body generator:
              ": connected\n\n"                  ← flush headers through proxies
              async for event in run_rag_query(RAGRequest(...)):
                    "data: {json.dumps(event)}\n\n"
              exception ──▶ "data: {"type":"error","detail":"Internal error..."}\n\n"
```

Key framing decisions:

- **`ensure_ascii=False`** in `json.dumps` — non-ASCII answer tokens (e.g. Hindi, Tamil) stream as readable UTF-8 instead of `\uXXXX` escapes.
- **`await request.is_disconnected()`** — if the client closes mid-answer, the loop stops producing events instead of burning Gemini tokens on a dead connection.
- **Led-comment frame** — `: connected\n\n` is the standard SSE way to force proxies to flush headers instantly so the client sees "connected" before the first token.
- **The orchestrator's abstain/fail-open semantics pass through unchanged** — `insufficient_evidence` final events are NOT errors, they stream as normal final events.

### Verification — Integration Tests

Created `backend/tests/integration/routes/test_rag_routes.py` (5 tests) following the existing `TestClient(app)` + dependency-override pattern (`get_db` and `get_current_user` overridden; `run_rag_query` mocked at the module boundary):

| Test | Asserts |
|---|---|
| `test_rag_query_requires_auth` | no token → **401** |
| `test_rag_query_streams_token_and_final` | `data: {"type":"token"...}` + `data: {"type":"final"...}` lines, `: connected` comment, SSE content-type + no-cache headers |
| `test_rag_query_invalid_file_ids_returns_400` | mocked `validate_file_ids` raising `ValueError` → clean **400** before streaming |
| `test_rag_query_generation_error_frames_clean_error` | mocked generator raising → SSE error frame, no traceback in body |
| `test_rag_query_search_all_when_no_file_ids` | `file_ids=None` flows to orchestrator; `top_k`/`score_threshold` preserved |

Result: `uv run pytest tests/integration/routes/test_rag_routes.py` → **5 passed**.

> The tests initially 404'd because the router wasn't registered in `main.py` yet — registration is required before any route test can run. (Task 6 for `/documents` still pending.)

### Key Learnings

- **SSE framing is a contract, not an afterthought.** `data: {json}\n\n` (double newline) is how SSE separates events; a single `\n` corrupts the stream. Read the raw body lines in tests, never `response.json()`.
- **Up-front validation converts a mid-stream failure into a clean 400.** Validating `file_ids` *before* returning the `StreamingResponse` means bad input dies with a normal JSON error, not an aborted stream.
- **The wire model and service model are the security boundary.** `RAGQueryRequest` (no `user_id`) → route-injected `RAGRequest(user_id=current_user.id)` is the exact seam where client identity becomes trusted identity.
- **`is_disconnected()` is a cost-control lever.** Checking it per-event stops generating into a void when the client navigates away — an easy win for token spend.
- **Cache hits are corpus-scoped, not question-scoped.** `build_cache_key` prefixes `{user_id}:{corpus_revision}:` and hashes question + file set + top_k + threshold + prompt/model versions. **Any** completed re-index bumps `corpus_revision`, so the *first* identical query after re-triggering `POST /documents` will be a cache miss (it regenerates and re-caches), and only the *second* identical query is a hit. That is deliberate invalidation, not a bug the user should distrust.
- **A plain coroutine is not an async generator.** For a mocked failing stream, the fake must be an actual `async def` generator (with a `yield` somewhere) or `async for` raises `TypeError` instead of surfacing the intended failure.

---

## 5. Task 5 — `/documents` Router (Index Trigger, Status, Chunk Inspection)

### How We Built It

Created `backend/app/apis/routes/rag_document_routes.py` with three endpoints and registered it in `backend/main.py`:

```
rag_document_routes.py
├── POST  /documents                       trigger RAG indexing (202)
├── GET   /documents/{id}/index-status     indexing progress (200/404)
└── GET   /documents/{id}/chunks           chunk inspection (200/404)
```

**Design decision (differs from the phase plan):** this repo uploads files **directly to S3 via presigned URLs** (`POST /files/upload-url` → client PUTs bytes to S3 → `POST /files/upload-complete`), and that existing flow already schedules `sync_rag_chunks_in_background`. So `POST /documents` is **not** a multipart upload endpoint. Instead it accepts a body referencing an already-uploaded file the user owns:

```python
class RAGDocumentTriggerRequest(BaseModel):
    file_id: int | None = None   # select by file_id
    s3_key:  str | None = None   # OR select by S3 object key
```

Exactly one must be present (400 otherwise). This reuses the presigned upload + existing worker path end-to-end while giving the playground a clean RAG trigger for files uploaded through the legacy flow, failed retries, or pre-RAG documents.

### Why We Implemented It

The four-endpoint contract needs a way to (a) kick off RAG indexing and (b) let a client *observe and verify* what happened. Three concerns drove each endpoint:

1. **Never re-upload through the backend.** `POST /documents` only points at a file that already exists in S3 — the upload bytes never transit FastAPI (matches the project's architectural guardrail: "never route raw file streams through backend processes").
2. **Tenant isolation is mandatory.** Every endpoint filters on `current_user.id`. A foreign `file_id` or `s3_key` is indistinguishable from a missing one → single 404 message.
3. **Playground needs observability.** `index-status` feeds the progress bar; `chunks` proves the cleaned text a user asked the LLM to answer from actually exists and looks sane.

### How It Works

```
POST /documents  {file_id: 10}  (or {s3_key: "uploads/..."})
  1  exactly-one check ──▶ 400 if both/neither
  2  query file_metadata WHERE userid=current_user.id AND [fileid|s3_key]
       └ no row ──▶ 404  (covers foreign + missing)
  3  status == ACTIVE? ──▶ 400 if pending/failed (upload not completed)
  4  reset indexing lifecycle: status=PENDING, clear started_at + error fields
  5  background_tasks.add_task(sync_rag_chunks_in_background, file_id, user_id)
  6  return 202 {id, filename, indexing_status}
              (worker will claim → EXTRACTING → ... → INDEXED)

GET /documents/{id}/index-status
  get_index_status(db, user_id, id)  ──None──▶ 404
  else 200 with {indexing_status, progress, chunk counts, error fields}

GET /documents/{id}/chunks?index_version=N
  get_chunks(db, user_id, id, N)     ──None──▶ 404
  resolved_version = N  OR  active_index_version   (defaults to live version)
  return {file_id, index_version, total, chunks:[{chunk_id, pages, words, clean_text}]}
```

The worker reset (Step 4) is what makes the trigger idempotent-then-complete: clearing error state and returning to `PENDING` allows the worker's atomic claim to re-acquire the row; if another worker already holds it, the claim fails silently and the run is skipped.

### Verification — Integration Tests

Created `backend/tests/integration/routes/test_rag_document_routes.py` (13 tests) using real in-memory SQLite + dependency overrides:

| Area | Cases |
|---|---|
| Trigger | by `file_id` → 202 + worker scheduled; by `s3_key` → 202; both/neither → 400; foreign & missing → 404; non-active file → 400; no auth → 401 |
| Status | owned → 200 with valid `indexing_status` + `0 ≤ progress ≤ 1`; foreign → 404 |
| Chunks | owned with a seeded chunk → 200 + chunk details; explicit `index_version` respected; foreign → 404 |

Result: `uv run pytest tests/integration/routes/test_rag_document_routes.py` → **13 passed**.

Phase import check also green:

```
uv run python -c "from app.apis.routes.rag_routes import router as r1; \
 from app.apis.routes.rag_document_routes import router as r2; \
 from app.services.rag.inspection import get_index_status, get_chunks; \
 print('Phase 6 imports ok')"                 → Phase 6 imports ok
```

### Key Learnings

- **The plan is a target, not a cage.** The phase document sketched a multipart `POST /documents`; the repo's existing presigned flow made that wasteful and conflicts with the "no bytes through backend" architecture rule, so the endpoint became a *trigger* referencing an S3 object instead. Same contract goal (upload → index), cleaner fit.
- **A single 404 for foreign + missing is a deliberate privacy win.** Endpoints never reveal whether a file exists but isn't yours.
- **Reset-then-claim makes retries work through the existing loop.** Setting `status=PENDING` + clearing error fields before scheduling lets the worker's atomic claim re-run the file — no bespoke retry machinery.
- **Response models enforce the no-leak rule.** `RAGIndexStatusResponse`/`RAGChunkListResponse` shape the wire output so `s3_key`, `user_id`, and embedding internals can never slip out even if a future change returns a full ORM object.

---

## 6. Task 6 — Router Registration (`main.py`)

### How We Built It

`main.py` wires both new routers into the FastAPI app:

```python
from app.apis.routes.rag_routes import router as rag_router
from app.apis.routes.rag_document_routes import router as rag_document_router

app.include_router(rag_router)            # adds POST /rag/query
app.include_router(rag_document_router)   # adds /documents triggers + inspections
```

### Why We Implemented It

A router that is never included is dead code — and worse, its tests fail with confusing 404s. The very first `/rag/query` integration test 404'd until `rag_router` was registered; the `/documents` tests hit the same wall. Registration is the single `main.py` seam that connects the new route modules (Tasks 4–5) to the running application, so it was tracked as its own task rather than buried in either route task.

### How It Works

`app.include_router(router)` mounts every route defined in the module under its declared prefix (`/rag`, `/documents`). Because routers are standalone `APIRouter` instances imported at module scope, `main.py` never needs to know their handlers — only their existence.

### Verification

- With registration live, the combined route suites pass: `tests/integration/routes/test_rag_routes.py` (5) + `test_rag_document_routes.py` (13) → **18 passed**.
- `uv run python -c "from app.apis.routes.rag_routes import router as r1; from app.apis.routes.rag_document_routes import router as r2; print('Phase 6 imports ok')"` → **Phase 6 imports ok**.

### Key Learnings

- **Unregistered routers are invisible.** A route test failing with 404 — while the handler looks perfectly correct — is almost always a missing `include_router`, not a routing bug.
- **Keep routers import-only in `main.py`.** Mounting a pre-built `APIRouter` keeps registration a one-line declarative act; no conditional logic or ordering surprises.

---

## 7. Task 7 — Streamlit Playground

### How We Built It

Created `backend/streamlit_app/app.py` (plus `requirements.txt` for `streamlit` + `requests`) as a **thin client**. It speaks only HTTP(S) to the FastAPI backend and holds no database/vector/LLM credentials; MySQL, Qdrant, Redis, B2/S3, and Gemini are reachable only through the API contract:

```
backend/streamlit_app/app.py
├── helper fns          login · get_active_files · presigned PUT · upload-complete
│                       trigger_indexing · get_index_status · get_chunks
├── sidebar             API base URL (env RAG_API_BASE_URL, default :8000)
│                       login→token · bearer token (st.session_state only)
│                       top_k & similarity-threshold sliders
├── Tab 1 Upload & Status   presigned direct-to-S3 PDF upload + trigger/watch
│                           + list user files & trigger indexing by file
├── Tab 2 Chunk Inspector   pick file → cleaned chunk text + page/word ranges
└── Tab 3 Query Playground  streams POST /rag/query answer token-by-token
```

### Why We Implemented It

Phase 6's goal is a *usable* contract. Before this task the four endpoints existed but were only exercisable via curl. The playground is the reference client that:

1. **Walks the complete happy path.** Upload PDF → presigned PUT to S3 → complete-upload (which schedules the worker) → observe `INDEXED` via `index-status` → inspect chunks → stream a grounded answer. This is exactly the Phase 8 React flow, validated in Streamlit first.
2. **Reuses the presigned upload flow (per user directive).** `POST /files/upload-url` gives a PUT URL; the byte stream goes straight from Streamlit to object storage (`upload_direct_to_s3`), and `POST /files/upload-complete` verifies + activates. The backend never touches the upload bytes — consistent with the repo's architectural guardrail.
3. **Selects files by `file_id` OR `s3_key`** (per user directive). Tab 1 offers both: a dropdown backed by `GET /files` (file ids) plus the `POST /documents` trigger accepting either reference. The dropdown label carries `fileId — filename` so the ID is always visible.
4. **Keeps the token in `st.session_state` only.** Nothing is written to source or disk; the sidebar accepts a pasted token or logs in via `POST /auth/login`.

### How It Works

**Token flow.** `st.sidebar.text_input` is bound to `st.session_state["token"]`; the widget copies into session state on each rerun, so interactions in tabs all reuse the typed token. A guard (`if not token: st.stop()`) halts the app below the sidebar until a token exists, and an explicit `api_token: str = str(token)` gives the analyzer a non-`None` value for the API helpers.

**Presigned upload (Tab 1).**
```
st.file_uploader(pdf) → get_presigned_put_url(token, name, "application/pdf")
     → PUT upload_url directly (requests.put, raw bytes)
     → POST /files/upload-complete {key, filename}
     → worker auto-runs full indexing (Task 1) → INDEXED
```

**Status polling.** `POST /documents` returns 202 + `id`; `get_index_status` then maps the lifecycle to a `0..1` progress value rendered by `st.progress`, and `st.json` shows the full status envelope. Both the "Watch status" button and the "Poll index status" button call one shared `render_status(file_id)` helper.

**Chunk Inspector (Tab 2).** `get_chunks(api_token, file_id, version=None)` defaults to the active index version server-side; each chunk renders page range, word range, and the cleaned text in a `st.text_area` (escaped, never interpreted as HTML) — proof of exactly what Gemini sees.

**Query Playground (Tab 3).** Uses `requests.post(..., stream=True)` on `POST /rag/query` and parses SSE `data:` frames manually:
```
for raw_line in resp.iter_lines(decode_unicode=True):
    data: {json}  → token events accumulate into a placeholder markdown (streamed)
                   final event → sources list + diagnostics
    diagnostics.insufficient_evidence → st.warning
    sources → st.dataframe  ·  diagnostics → st.json
```
The file multiselect is scoped by `file_id` and lists only `INDEXED` files (empty selection sends `file_ids: None` → whole corpus).

### Verification

Task 7 has no unit tests of its own — it is a client, exercised manually via `streamlit run` (validation of its interaction surface is covered by Task 10's full regression on the backend it calls):

```
cd backend
uv run streamlit run streamlit_app/app.py    # then open http://localhost:8501
```

### Key Learnings

- **The client is a contract proof, not a product.** Streamlit sits on the same authenticated surface a future React SPA will use; anything awkward to call from Streamlit (framing, field names, error shapes) is already fixed at the API layer now.
- **Bytes belong in object storage, not the app server.** The playground's upload leg is presigned-URL only; repeating the repo's "never route raw file streams through backends" rule inside the client keeps the architecture honest end-to-end.
- **Keep credentials out of the client entirely.** A bearer token in `st.session_state` (memory-only) + a base URL from an env var is the whole credential surface a RAG client needs — no DB users, no Gemini keys, no Qdrant API secrets.
- **SSE streaming is easy once the framing is documented.** Consuming event-stream was ~15 lines: read raw lines, keep only `data: ` prefixes, JSON-decode, and append tokens to a placeholder. The hard part (event schema) was already solved in Phase 5.
- **Explicitly-typed alias beats fighting the analyzer.** `api_token: str = str(token)` after the `st.stop()` guard removes `None` from the widget's inferred `str | None` union for every closure that captures it — cleaner than per-call `or ""` noise.
- **Wire casing is per-schema, and the client must match it.** `GET /files` serializes `FileMetadataSchema` by alias → camelCase (`fileId`, `indexingStatus`); the Phase 6 endpoints serialize plain snake_case (`file_id`, `indexing_status`). A first pass at filtering the query tab read `indexing_status` from `GET /files` data and silently matched nothing — the "No INDEXED files yet" caption was a false negative and the query actually ran corpus-wide (`file_ids=None`). Fixed by reading `indexingStatus`. When the client reads a raw response, always check the actual wire key; don't assume the schema's Python field name.
- **Post-launch UX fix:** "Watch status" originally just wrote `st.session_state["watch_file_id"]` (pre-filling the poll text box) and rendered nothing, so it looked dead. Both status triggers now share one `render_status(file_id)` helper that fetches `GET /documents/{id}/index-status` and renders progress + JSON.

---

## 8. Task 8 — Unit Tests for the Inspection Service

### How We Built It

Created `backend/tests/unit/services/rag/test_inspection.py` using the repo's proven in-memory SQLite pattern (`StaticPool`, `check_same_thread=False`). It drives `inspection.py` directly through a real `Session`, seeding `FileMetadata` + `DocumentChunk` rows with a test factory — no mocking of SQLAlchemy.

Coverage (14 tests):

| Area | Asserts |
|---|---|
| `get_index_status` | owned file returns the full status dict (ten fields incl. `file_id`, `indexing_status`, `active_index_version`, `corpus_revision`, `progress`) |
| Ownership | foreign file → `None`; absent file → `None` (the 3-in-1 sentinel) |
| `_progress_for` | every lifecycle state maps to its `0..1` value; failed/unknown → `0.0` |
| Error surfacing | `rag_error_code` / `rag_error_message` present when set |
| `get_chunks` | ordered by `chunk_index`, tenant-scoped, version-scoped; `index_version=None` defaults to `active_index_version` |
| Edge cases | owned-but-unindexed file → `[]` (not `None`); a second user's file + chunks invisible to user 1 |

### Why We Implemented It

The `/documents` inspection endpoints depend on ownership proof and version-defaulting logic (Section 3). That logic lives in a service module, so it gets a dedicated unit suite — the 3-in-1 `None` sentinel (missing / foreign / no inspection) and the progress mapping are exactly the kind of behaviors that regress silently if exercised only through routes.

### Verification

```
uv run pytest tests/unit/services/rag/test_inspection.py   →  14 passed
```

> Two initial test failures were fixed during development: (1) a test-ID bug (`fileid=status + 100` concatenated a string), and (2) a real DB constraint — `document_chunks` has a unique `(file_id, index_version, chunk_index)` constraint, so "a foreign user's chunk on the same file" cannot exist; the tenant-scoping test now uses a second file owned by the second user.

### Key Learnings

- **`None` is a 3-in-1 sentinel.** Return value does triple duty: *not found*, *not owned*, and (for chunks) *no inspection available*. The route can map it to a single 404 without distinguishing — exactly what you want publicly.
- **Test against real schema constraints.** The unique `(file_id, index_version, chunk_index)` constraint silently invalidated my original "foreign chunk, same file" scenario — a reminder that the DB enforces invariants tests should respect, not bypass.
- **In-memory SQLite + a seeding factory beats mocks for service tests.** The inheritance pattern used across the existing RAG suite gives real query/constraint behavior with zero external infra.

---

## 9. Task 9 — Integration Tests for the New Routes

### How We Built It

Created two integration suites under `backend/tests/integration/routes/`, following the existing `TestClient(app)` + dependency-override pattern (in-memory SQLite via `get_db` override; `get_current_user` overridden to a fixed user; external resources mocked at the module boundary):

| File | Tests | Coverage |
|---|---|---|
| `test_rag_routes.py` | 5 | `POST /rag/query`: auth 401; token+final SSE frames with `: connected` comment and no-cache headers; `validate_file_ids` ValueError → clean 400 before streaming; generator exception → SSE error frame (no traceback); `file_ids=None` flows through with `top_k`/`score_threshold` preserved |
| `test_rag_document_routes.py` | 13 | `POST /documents` by `file_id` / `s3_key` → 202; both/neither → 400; foreign & missing → 404; non-active file → 400; no auth → 401. `GET /documents/{id}/index-status` owned → 200 + valid `indexing_status` + `0≤progress≤1`; foreign → 404. `GET /documents/{id}/chunks` owned with seeded chunk → 200 + details; explicit `index_version` respected; foreign → 404 |

Mocking note: the failing-stream fake must be a real `async def` generator (contains a `yield`), or `async for` raises `TypeError` and hides the intended failure.

### Why We Implemented It

The new routes are the product's public HTTP surface — upload-trigger semantics, status/progress payloads, and SSE framing are exactly what should survive contract changes. Route-level tests prove auth, tenancy, error mapping, and wire shape together, which unit tests on services deliberately do not.

### Verification

```
uv run pytest tests/integration/routes/test_rag_routes.py           →  5 passed
uv run pytest tests/integration/routes/test_rag_document_routes.py  →  13 passed
```

> The suites initially 404'd because the routers weren't in `main.py` yet — proving Task 6 (router registration) is a hard prerequisite for every route test.

### Key Learnings

- **SSE framing is a contract, not an afterthought.** `data: {json}\n\n` (double newline) separates events; read raw body lines in tests, never `response.json()`.
- **Up-front validation converts a mid-stream failure into a clean 400.** Validating `file_ids` before returning the `StreamingResponse` means bad input dies with a normal JSON error, not an aborted stream.
- **Dependency overrides are the integration-test workhorse.** Swapping `get_db` + `get_current_user` and patching one module symbol exercises the full request lifecycle without external DB/Qdrant/Gemini.
- **A regular coroutine is not an async generator** — for a mocked failing stream the fake must `yield` something or `async for` raises `TypeError` instead of the intended failure.

---

## 10. Task 10 — Full Regression

### How We Built It

Ran the **entire backend suite** after all Phase 6 changes, as the final safety gate:

```
uv run pytest   →  322 passed in ~8s
```

Breakdown of what the 322 covers:
- Section 1: 216 RAG service tests (worker path imports + Phase 4/5 suites, incl. Table-driven indexing tests)
- Section 8: 14 inspection unit tests
- Section 9: 18 route integration tests (`/rag/query` 5 + `/documents` 13)
- All legacy auth / file / search / util suites (pre-Phase 6 baseline)

### Why We Implemented It

A task-based plan accumulates risk at each step; Task 10 clears it. Every earlier task verified *its own* slice; only a full-regression run proves the slices compose — e.g., that router registration (Task 6) didn't shadow a legacy route, or that schema additions (Task 2) didn't break the FileMetadata wire shape used by `/files`.

### Verification

- `uv run pytest` → **322 passed, 0 failures**.
- `uv run python -c "import ast; ..."` syntax checks on changed files → OK.

### Key Learnings

- **Local green is the releaseable definition of done.** With the whole suite green, Tasks 1–9 are provably composed and the Streamlit playground exercises a live-but-consistent backend.
- **Regression is cheap here** (≈8s in-memory) — run it after every route/service change, not just at phase end.

---

## 11. Future Upgrade — Semantic Answer Cache (Not Implemented — Planned)

> Status: **PLANNED, DESIGN ONLY.** Nothing in this section is built. It is recorded here so the next implementer inherits the analysis, decisions, and constraints — not the reasoning gap.

### Problem Being Solved (observed in live use)

The current answer cache keys on the **raw question string** (exact-match hash over `user_id + corpus_revision + question + file set + top_k + threshold + prompt/model`). Two near-identical user questions — *"summarize the pdf"* vs *"summarize this document"* — hash differently, so the second is a guaranteed cache miss even though the user means the same thing. This is **correct, safe behaviour** (an exact key can never return a wrong answer), but it under-serves paraphrases and lowers the hit rate.

### Proposed Architecture (three layers, all corpus-scoped)

**Note:** the whole cache is invalidated by `corpus_revision` (re-index changes it), so all three layers must prove a matching revision before serving.

| Layer | Mechanism | Which paraphrases it catches |
|---|---|---|
| **0 — Intent canonicalization** (deterministic, free) | `canonicalize_question(q)` keyword-rules "document summary" intent (`summarize` / `tl;dr` / `gist` / `overview` / `main points` / `key takeaways` + `this doc/pdf/file`) → canonical `"summarize this document"` | The user-reported class exactly; zero infra, deterministic |
| **1 — Exact Redis key** (existing) | unchanged `build_cache_key` over the **canonicalized** question | Nothing new; still the fastest, zero-false-positive path |
| **2 — Semantic Qdrant cache** (new) | embed the canonicalized question → search a new `rag_answer_cache` collection (768-d/COSINE) filtered by `user_id + corpus_revision + top_k + score_threshold + prompt_version + model_version`, cosine ≥ `RAG_SEMANTIC_THRESHOLD` (default `0.93`); hit ⇒ return stored answer, `cache_tier: "semantic"` | Arbitrary paraphrases beyond keyword intents |

### Constraints & Decisions (already settled)

- **Backend:** Qdrant collection `rag_answer_cache` (reuses existing vector infra; multi-worker safe).
- **Bundle:** add Layer 0 intent canonicalization *and* Layer 2 semantics.
- **Threshold:** default `RAG_SEMANTIC_THRESHOLD = 0.93` (industry-typical; tune via config — lower catches broader paraphrases but raises wrong-answer risk).
- **Fail-open everywhere:** a Qdrant/embedding error must degrade to the normal RAG path, never a 500 (match `answer_cache.py` contract).
- **Safety ordering:** exact key first (deterministic), then semantic (gated by cosine + strict payload equality). Store `answer` + serialized `sources` in the point payload so a semantic hit can still emit normal SSE token+final events.
- **TTL:** match `RAG_CACHE_TTL_SECONDS`; Qdrant has no native TTL → lazy prune of stale points on write (best-effort).

### Planned File Changes (when implemented)

| File | Change |
|---|---|
| `app/services/rag/schemas.py` | add `cache_tier: "exact" \| "semantic" \| None` to `RAGQueryDiagnostics` (backward-compatible, default `None`) |
| `app/services/rag/query_canonicalizer.py` *(new)* | `canonicalize_question(q) -> str` |
| `app/services/rag/embedding.py` | expose `embed_question(text) -> list[float]` (currently buried in retrieval) |
| `app/services/rag/semantic_cache.py` *(new)* | collection guard + get/set + TTL prune, all fail-open |
| `app/services/rag/rag_orchestrator.py` | canonicalize early; Layer-1 hit → tier `exact`; miss → embed → Layer-2 → tier `semantic`; else RAG path + upsert semantic entry |
| `app/core/config.py` | `RAG_SEMANTIC_CACHE_ENABLED` (True), `RAG_SEMANTIC_THRESHOLD` (0.93) |
| tests | `test_query_canonicalizer.py`, `test_semantic_cache.py`, orchestrator tests (paraphrase hit, below-threshold miss, revision/param mismatch miss, fail-open, TTL prune) |

### Expected Verification (when implemented)

- Paraphrase pair *"summarize the pdf"* / *"summarize this document"*: first generates + caches, second → **semantic hit** (`cache_tier: "semantic"` in diagnostics final event).
- Re-index must invalidate both exact and semantic entries (revision mismatch → miss).
- Full regression stays green (existing 322 + new suites).