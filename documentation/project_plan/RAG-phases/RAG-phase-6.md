# RAG Phase 6 - FastAPI Contracts and Streamlit Integration

## 1. Phase Goal

Phase 6 is the **productization** phase. Phases 1-5 built the full RAG engine as pure services and one script-driven orchestrator. Phase 6 gives that engine a **safe, authenticated HTTP surface** and a **working client** (the Streamlit playground) so a real user can upload a document, watch it index, inspect its chunks, and stream a grounded answer — all without ever touching MySQL, Qdrant, Redis, B2/S3, or Gemini directly.

Phase 5 delivered this in-process contract:

```text
RAGQueryRequest  →  run_rag_query(RAGRequest, db)  →  SSE event dicts
     { "type": "token", "text": "..." }
     { "type": "final", "sources": [...], "diagnostics": {...} }
```

Phase 6 exposes that contract over the wire and adds the ingestion/status/inspection surface it needs:

```text
Streamlit playground (thin client)
    |
    v  Bearer token
+---------------------------- FastAPI ----------------------------+
| POST    /rag/query                  -> SSE answer stream        |
| POST    /documents                  -> multipart upload + index |
| GET     /documents/{id}/index-status-> indexing progress        |
| GET     /documents/{id}/chunks      -> chunk inspection         |
+-----------------------------------------------------------------+
    |
    v  services own all infra
MySQL / Qdrant / Redis / B2/S3 / Gemini
```

The central architecture rule for Phase 6:

```text
Routes are thin: authenticate, validate, delegate.
Services own every piece of infrastructure.
Streamlit is a development/playground client — never a production trust boundary.
```

By the end of Phase 6, the backend should be able to:

- stream a grounded RAG answer to an authenticated client via Server-Sent Events
- accept a PDF upload and drive it through the full ingestion pipeline (staging → embedding → Qdrant cutover) asynchronously
- report a document's indexing status and progress to the client
- let an authorized client inspect the raw vs cleaned text of individual chunks for a given version
- host a self-contained Streamlit playground that exercises all four endpoints with the user's own bearer token
- keep every route tenant-isolated (all queries scoped by the authenticated user's ID)

## 2. Phase 5 Status Check

Before writing this plan, the current Phase 5 implementation was checked against the codebase.

Present and ready for Phase 6:

```text
backend/app/services/rag/
|-- rag_orchestrator.py   - run_rag_query() async generator (SSE event dicts)
|-- rag_orchestrator.py   - RAGRequest, RAGDiagnostics
|-- query_utils.py        - validate_file_ids, build_cache_key, filter/dedup/cap
|-- generation.py         - SourceBlock, generate_answer_stream, validate_citations
|-- answer_cache.py       - get/set_cached_answer (fail-open Redis)
|-- query_service.py      - search_similar_chunks, hydrate_chunks (fully implemented)
|-- schemas.py            - RAGQueryRequest, RAGQueryDiagnostics, RAGSourceResponse, RAGFinalEvent
|-- indexing_service.py   - run_full_indexing(), build_new_version_vectors()
|-- persistence.py        - stage_document_chunks, activate_rag_index_version
|-- __init__.py           - facade exporting all Phase 4/5 public names
|
backend/app/workers/rag_worker.py
|-- sync_rag_chunks_in_background(file_id, user_id)  - Phase 2/3 staging (see note below)
|
backend/app/core/config.py
|-- GEMINI_GENERATION_MODEL, RAG_CACHE_ENABLED, RAG_CONTEXT_BUDGET_TOKENS, etc.
```

Existing route + auth infrastructure (reuse, do not duplicate):

```text
backend/app/auth/auth_dependencies.py
|-- get_current_user  - JWT bearer dependency returning the User ORM row

backend/app/apis/routes/
|-- document_routes.py  - /files/* presigned-upload surface (legacy frontend flow)
|-- search_routes.py
|-- auth_routes.py
|-- system.py

backend/main.py
|-- app.include_router(...)  - router registration point (add the new router here)
```

Verified Phase 5 gates passed:

```text
uv run pytest tests/unit/services/rag   (58 passed in the RAG suite)
uv run pytest                          (290 passed overall)
```

### Critical gap to close before Phase 6

`sync_rag_chunks_in_background` currently performs **Phase 2 + Phase 3 only** — it extracts, cleans, chunks, and stages the chunks to MySQL, leaving the file in `CHUNKED` state. It does **not** run `run_full_indexing` (the Phase 4 embed + upsert + cutover). The Phase 5 smoke script called `run_full_indexing` explicitly. For a real user upload to reach `INDEXED`, Phase 6 must **extend the RAG worker** to invoke `run_full_indexing` after staging succeeds (respecting the existing `MAX_CONCURRENT_EMBEDDING_TASKS` semaphore guard).

Phase 6 does **not** add:

```text
New embedding / Qdrant / generation algorithms        - Phases 4/5
Document chunking or cleaning logic                   - Phase 2
New MySQL schema (document_chunks already exists)      - Phase 3
Metrics / evaluation / rollback runbooks               - Phase 7
```

## 3. What Phase 6 Adds

```text
+-------------------------------+----------------------------------------------+
| Area                          | Phase 6 work                                 |
+-------------------------------+----------------------------------------------+
| POST /rag/query endpoint      | Authenticated SSE streaming of run_rag_query |
| Document RAG endpoints        | Upload, index-status, chunk inspection        |
| PDF ingestion trigger         | Multipart upload -> worker -> full indexing   |
| RAG worker completion         | Extend worker to run_full_indexing            |
| SSE framing helper            | Stream JSON events with proper headers        |
| RAG status/chunk schemas      | Pydantic response models for new endpoints    |
| Streamlit playground          | Thin client: upload, status, chunks, query    |
| Route tests                   | Index-status, chunks, rag/query SSE           |
+-------------------------------+----------------------------------------------+
```

### Reconciliation note (existing `/files/*` vs new `/documents/*`)

The repository already has a `/files/*` presigned-upload flow used by the production React frontend. The master plan's **Phase 6 contract** and the **Streamlit client** use a different, simpler surface: `POST /documents` (multipart), `GET /documents/{id}/index-status`, `GET /documents/{id}/chunks`, plus `POST /rag/query`.

**Decision:** create the new RAG-facing endpoints on a dedicated `/documents` router that delegates to the same `FileMetadata`/`DocumentChunk` models and the same `rag_worker`/`run_full_indexing` services the existing code already uses. Do **not** modify the existing `/files/*` presigned flow or the React frontend. The `/documents` router is the RAG playground's server contract and is thin by construction. If a future consolidation is wanted, it is a separate refactor and out of scope.

## 4. Existing Project Context

Relevant files Phase 6 builds on (from Phases 1-5):

```text
backend/app/services/rag/schemas.py
|-- RAGQueryRequest    - wire model (no user_id; injected from auth in the route)
|-- RAGQueryDiagnostics, RAGSourceResponse, RAGFinalEvent

backend/app/services/rag/rag_orchestrator.py
|-- run_rag_query(RAGRequest, db) -> AsyncIterator[dict]
      yields {"type": "token", "text": ...}
      yields {"type": "final", "sources": [...], "diagnostics": {...}}

backend/app/services/rag/indexing_service.py
|-- run_full_indexing(db, file, index_version=None) -> {"success": bool, ...}

backend/app/workers/rag_worker.py
|-- sync_rag_chunks_in_background(file_id, user_id)   - needs Phase 6 extension

backend/app/auth/auth_dependencies.py
|-- get_current_user  - JWT dependency; returns User with .id for tenant scoping

backend/app/database/db_models.py
|-- FileMetadata  (active_index_version, indexing_status, corpus_revision, ...)
|-- DocumentChunk (chunk_index, page_start, page_end, clean_text, ...)
```

## 5. Design Principles

### 5.1 Routes Are Thin, Services Are Fat

A Phase 6 route must only: authenticate (`get_current_user`), validate the request body/query (Pydantic), and delegate to a service. No route may construct Qdrant filters, call Gemini, open a Redis client, or build raw SQL. This keeps the API surface auditable and the services independently testable.

### 5.2 Tenant Isolation Is Injected, Never Client-Passed

The authenticated user's ID comes **only** from `get_current_user`, never from the request body. `POST /rag/query` maps `current_user.id` into `RAGRequest(user_id=...)` at the boundary — this is exactly the split between `RAGQueryRequest` (wire, no identity) and `RAGRequest` (service, trusted identity) that Phase 5 designed. Every status/chunk/query lookup must filter on `current_user.id`.

### 5.3 SSE As a Contract, Not an Afterthought

`run_rag_query` yields plain dicts. The endpoint's only job is framing:

```text
data: {"type": "token", "text": "Hello"}\n\n
data: {"type": "final", "sources": [...], "diagnostics": {...}}\n\n
```

Correct SSE requires explicit `Cache-Control: no-cache`, `Connection: keep-alive`, and a start-of-stream comment to flush proxies. The endpoint must stream one event at a time and close cleanly when the generator is exhausted.

### 5.4 Fail-Open / Abstain Semantics Reach the Client

The orchestrator already abstains cleanly (emits a `final` event with `insufficient_evidence: true`) and never throws on Redis problems. The endpoint must **forward** the orchestrator's event stream unchanged and map only genuine service errors (e.g. invalid file IDs → 400, internal failures → 500) to HTTP status codes. It must not invent its own event shapes on top of the orchestrator's contract.

### 5.5 Indexing Is Asynchronous and Non-Blocking

`POST /documents` returns as soon as the file is accepted and a worker is scheduled. Indexing runs in the background (`BackgroundTasks` + the semaphore-guarded worker). The client poll `GET /documents/{id}/index-status` to observe progress. This matches the existing architecture (the `/files/upload-complete` route already schedules background tasks) and keeps upload latency independent of embedding time.

### 5.6 Playground Diagnostics Stay Separate

The Streamlit client renders the `sources` table and `diagnostics` JSON only inside collapsed/development sections. Normal user-facing output is the answer text and its citations. The backend never returns vectors, B2 keys, raw internal errors, or cross-tenant source text.

## 6. Implementation Steps

### Step 1 - Extend the RAG Worker to Complete Indexing

Edit:

```text
backend/app/workers/rag_worker.py
```

**Current behavior** `sync_rag_chunks_in_background` ends after `stage_document_chunks`, leaving `document_chunks` staged but the file in `CHUNKED` state and `active_index_version` unchanged. No vectors exist in Qdrant yet.

**Required change**: after the `stage_document_chunks` call succeeds and the session is closed (releasing the DB lock), run the Phase 4 cutover and update the file's status using `run_full_indexing`:

```python
from app.services.rag.indexing_service import run_full_indexing

# after staging, in a NEW session (Phase 4 does its own short transactions):
stage_db = SessionLocal()
try:
    stage_file = stage_db.query(FileMetadata).filter(
        FileMetadata.fileid == file_id
    ).first()
    if stage_file is None:
        logger.error("RAG worker: file %s missing for indexing.", file_id)
        return
    result = await run_in_threadpool(
        run_full_indexing,
        stage_db,
        stage_file,
    )
    logger.info(
        "RAG worker: file_id=%s indexing success=%s active_version=%s",
        file_id,
        result.get("success"),
        result.get("active_index_version"),
    )
finally:
    stage_db.close()
```

Preserve these guarantees:

- The whole pipeline stays inside `async with _embedding_semaphore:` so `MAX_CONCURRENT_EMBEDDING_TASKS` still caps concurrent Gemini load.
- `run_full_indexing` uses its own short transactions and `with_retry`-wrapped Gemini/Qdrant calls; no long transaction is held open.
- S3/PDF extraction, Gemini, and Qdrant all run via `run_in_threadpool` (they are CPU/IO-bound, not async).
- Do **not** re-claim the row; the claim happened at the top of the function. Guard the indexing block with its own try/except and route failures to `mark_rag_failure` so the file lands in `FAILED_RETRYABLE` instead of vanishing.

**Fresher note:**
```text
The worker is the only place (other than the smoke script) that ties
Phase 2+3 (staging) to Phase 4 (indexing). Making it call run_full_indexing
turns a manually-orchestrated pipeline into an automatic one. Keep the
semaphore around the whole body so we do not double the Gemini concurrency
that Phase 4 already budgets.
```

**Verification:**
- Run the RAG unit suite — nothing in `tests/unit/services/rag` depends on the worker internals beyond what exists, so no regression expected.
- Manual smoke: `uv run python -m app.scripts.rag_phase5_smoke <user_id> <s3_key>` still passes and reaches `INDEXED` end-to-end via the same `run_full_indexing` path.

### Step 2 - Add RAG Status / Chunk Inspection Schemas

Create or extend:

```text
backend/app/services/rag/schemas.py
```

Append Pydantic models for the two inspection endpoints (keep them in the same module as the existing Phase 5 RAG schemas for cohesion):

```python
class RAGIndexVersionInfo(BaseModel):
    """One indexed version's stats for the status endpoint."""
    index_version: int
    chunk_count: int
    indexed_chunk_count: int
    status: str
    progress: float = Field(ge=0.0, le=1.0)


class RAGIndexStatusResponse(BaseModel):
    """Response for GET /documents/{id}/index-status."""
    file_id: int
    filename: str
    indexing_status: str
    active_index_version: int
    corpus_revision: int
    progress: float = Field(ge=0.0, le=1.0)   # 0..1, derived from lifecycle
    chunk_count: int
    indexed_chunk_count: int
    rag_error_code: str | None = None
    rag_error_message: str | None = None


class RAGChunkInspection(BaseModel):
    """One chunk for GET /documents/{id}/chunks."""
    chunk_id: str
    chunk_index: int
    index_version: int
    page_start: int
    page_end: int
    word_count: int
    word_start: int
    word_end: int
    clean_text: str
    # raw_text is backend-derived from clean_text only when a raw source is
    # available; for RAG chunks we store no raw_text column, so this is
    # optional and omitted unless explicitly reconstructed.
    raw_text: str | None = None


class RAGChunkListResponse(BaseModel):
    """Response for GET /documents/{id}/chunks."""
    file_id: int
    index_version: int
    chunks: list[RAGChunkInspection] = Field(default_factory=list)
    total: int
```

Do **not** expose `source_key`, `user_id`, or `embedding_model`/`embedding_dimensions` in the client-facing model; they are internal.

**Verification:**
- `uv run python -c "from app.services.rag.schemas import RAGIndexStatusResponse, RAGChunkListResponse; print('ok')"`

### Step 3 - Add Thin Query Helpers for Status and Chunks

Create:

```text
backend/app/services/rag/inspection.py
```

A small service module (not a route) with two functions. This keeps the route to a few lines and lets the DB access be unit-tested against real SQLite, matching the Phase 5 pattern.

```python
from sqlalchemy.orm import Session

from app.database.db_models import DocumentChunk, FileMetadata


def get_index_status(db: Session, user_id: int, file_id: int) -> dict | None:
    """Return status dict for a file owned by user_id, or None if absent."""
    fm = (
        db.query(FileMetadata)
        .filter(
            FileMetadata.fileid == file_id,
            FileMetadata.userid == user_id,
        )
        .first()
    )
    if fm is None:
        return None

    progress = _progress_for(fm.indexing_status)
    return {
        "file_id": fm.fileid,
        "filename": fm.filename,
        "indexing_status": fm.indexing_status,
        "active_index_version": fm.active_index_version,
        "corpus_revision": fm.corpus_revision,
        "progress": progress,
        "chunk_count": fm.chunk_count,
        "indexed_chunk_count": fm.indexed_chunk_count,
        "rag_error_code": fm.rag_error_code,
        "rag_error_message": fm.rag_error_message,
    }


def _progress_for(status: str) -> float:
    """Map lifecycle -> 0..1 progress for the client progress bar."""
    order = {
        "PENDING": 0.0,
        "EXTRACTING": 0.1,
        "CHUNKED": 0.35,
        "EMBEDDING": 0.6,
        "INDEXING": 0.85,
        "INDEXED": 1.0,
    }
    return order.get(status, 0.0)


def get_chunks(
    db: Session,
    user_id: int,
    file_id: int,
    index_version: int | None = None,
) -> list[dict] | None:
    """Return chunk inspection rows for an owned file.

    index_version defaults to the file's active_index_version.
    Returns None if the file is not owned by user_id; returns [] if no chunks.
    """
    fm = (
        db.query(FileMetadata)
        .filter(
            FileMetadata.fileid == file_id,
            FileMetadata.userid == user_id,
        )
        .first()
    )
    if fm is None:
        return None

    target = index_version if index_version is not None else fm.active_index_version
    rows = (
        db.query(DocumentChunk)
        .filter(
            DocumentChunk.file_id == file_id,
            DocumentChunk.user_id == user_id,
            DocumentChunk.index_version == target,
        )
        .order_by(DocumentChunk.chunk_index)
        .all()
    )
    return [
        {
            "chunk_id": r.chunk_id,
            "chunk_index": r.chunk_index,
            "index_version": r.index_version,
            "page_start": r.page_start,
            "page_end": r.page_end,
            "word_count": r.word_count,
            "word_start": r.word_start,
            "word_end": r.word_end,
            "clean_text": r.clean_text,
        }
        for r in rows
    ]
```

**Fresher note:**
```text
inspection.py separates 'load data' from 'serialize HTTP'. The route calls
get_index_status / get_chunks and wraps the dicts in the Pydantic response
models from Step 2. Never embed a SQLAlchemy query inside a route handler.
```

**Verification:**
- Write `backend/tests/unit/services/rag/test_inspection.py` covering: owned-file status, non-owned file returns `None`, progress mapping for each lifecycle state, chunk listing scoped by `user_id` + version, default-to-active-version behavior, and empty-chunk handling. Use real in-memory SQLite (the Phase 5 pattern: `Base.metadata.create_all` + `StaticPool`).

### Step 4 - Add the `/rag/query` SSE Endpoint

Create:

```text
backend/app/apis/routes/rag_routes.py
```

**Route contract** (matches the master plan Phase 6 + the Streamlit client):

```python
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.auth.auth_dependencies import get_current_user
from app.database import get_db
from app.database.db_models import User
from app.services.rag.rag_orchestrator import RAGRequest, run_rag_query
from app.services.rag.schemas import RAGQueryRequest

router = APIRouter(prefix="/rag", tags=["rag"])


async def _event_stream(request: Request, user_id: int, payload: RAGQueryRequest, db: Session):
    # Drain the orchestrator's dict events and frame them as SSE.
    # Yield a leading comment line so proxies flush headers immediately.
    yield ": connected\n\n"
    rag_request = RAGRequest(
        user_id=user_id,
        question=payload.question,
        file_ids=payload.file_ids,
        top_k=payload.top_k,
        score_threshold=payload.score_threshold,
    )
    async for event in run_rag_query(rag_request, db):
        if await request.is_disconnected():
            break
        # json.dumps keeps the exact orchestrator contract
        import json
        yield f"data: {json.dumps(event)}\n\n"


@router.post("/query")
async def rag_query(
    payload: RAGQueryRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Stream a grounded RAG answer via Server-Sent Events."""
    return StreamingResponse(
        _event_stream(request, current_user.id, payload, db),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
```

Key points:

- `RAGQueryRequest` (wire model) has **no `user_id`**; the `current_user.id` is injected at the boundary when constructing `RAGRequest`. This is the Phase 5 design intent made concrete.
- **Error handling:** wrap the orchestrator call so that a `ValueError` from `validate_file_ids` becomes an HTTP 400, and unexpected exceptions become HTTP 500 — without breaking the SSE stream mid-frame. Recommended: build a small try/except around the generator call site so the client receives a clean failure rather than a truncated stream. Because `StreamingResponse` streams lazily, validation errors that happen inside the generator are surfaced as an SSE error event or an aborted response; prefer **validating `file_ids` ownership before returning the StreamingResponse** by calling `validate_file_ids` up front (see below).

**Defensive up-front validation** (recommended so bad requests fail fast with a JSON 400, not mid-stream):

```python
from app.services.rag.query_utils import validate_file_ids

# inside the route, before returning the StreamingResponse:
try:
    validate_file_ids(current_user.id, payload.file_ids, db)
except ValueError as exc:
    raise HTTPException(status_code=400, detail=str(exc)) from exc
```

This makes invalid/mixed-ownership `file_ids` a clean 400 while the orchestrator still re-validates inside the stream as defense-in-depth.

**Register the router** in `backend/main.py`:

```python
from app.apis.routes.rag_routes import router as rag_router
app.include_router(rag_router)
```

**Verification:**
- Manual smoke with the existing `rag_phase5_smoke.py` remains green (it calls the orchestrator directly, unaffected).
- Route integration test with mocked `run_rag_query` (an async generator yielding a token then a final event) asserting the SSE body contains the correctly framed `data: {...}` lines.
- Test that an unauthenticated request to `POST /rag/query` returns 401.

### Step 5 - Add the `/documents` RAG Endpoints

Create:

```text
backend/app/apis/routes/rag_document_routes.py
```

**Router prefix:** `/documents`, `tags=["rag-documents"]`.

**5a. `POST /documents` — multipart upload + index trigger**

```python
import uuid
from fastapi import APIRouter, Depends, UploadFile, File, BackgroundTasks, HTTPException

from app.auth.auth_dependencies import get_current_user
from app.database import get_db
from app.database.db_models import FileMetadata, User
from app.schemas.enums import FileStatus, IndexingStatus
from app.workers.rag_worker import sync_rag_chunks_in_background

router = APIRouter(prefix="/documents", tags=["rag-documents"])


@router.post("", status_code=202)
async def upload_document(
    file: UploadFile = File(...),
    background_tasks: BackgroundTasks = BackgroundTasks(),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if file.content_type != "application/pdf":
        raise HTTPException(status_code=415, detail="Only PDF uploads are supported.")

    # Bounded read so we do not buffer an unbounded file in memory.
    blob = await file.read(settings.RAG_MAX_PDF_BYTES + 1)
    if len(blob) > settings.RAG_MAX_PDF_BYTES:
        raise HTTPException(status_code=413, detail="PDF exceeds the size limit.")

    s3_key = f"uploads/{uuid.uuid4()}_{file.filename}"
    # Stream the bytes to S3/B2 via the existing service (owned by current_user).
    await run_in_threadpool(put_object, bucket=..., key=s3_key, body=blob,
                            content_type="application/pdf")

    db_file = FileMetadata(
        s3_key=s3_key,
        filename=file.filename or "document.pdf",
        content_type="application/pdf",
        status=FileStatus.ACTIVE.value,
        size_bytes=len(blob),
        userid=current_user.id,
        indexing_status=IndexingStatus.PENDING.value,
    )
    db.add(db_file)
    db.commit()
    db.refresh(db_file)

    background_tasks.add_task(
        sync_rag_chunks_in_background,
        file_id=db_file.fileid,
        user_id=current_user.id,
    )
    return {"id": db_file.fileid, "filename": db_file.filename,
            "indexing_status": db_file.indexing_status}
```

> **Implementation note:** `put_object` should delegate to the existing `app/services/AWS/s3_service.py` Boto3 helpers (the AWS skill covers presigned URL generation and object operations). Use the exact helper available in that module; if only presigned-URL helpers exist, add a small bounded `put_object` service method there rather than duplicating Boto3 logic in the route. Keep `RAG_MAX_PDF_BYTES` as the authoritative size cap (default 50 MiB).

**5b. `GET /documents/{id}/index-status`**

```python
@router.get("/{file_id}/index-status", response_model=RAGIndexStatusResponse)
async def index_status(
    file_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    result = get_index_status(db, current_user.id, file_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Document not found or access denied.")
    return result
```

**5c. `GET /documents/{id}/chunks`**

```python
@router.get("/{file_id}/chunks", response_model=RAGChunkListResponse)
async def list_chunks(
    file_id: int,
    index_version: int | None = Query(default=None, ge=0),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    chunks = get_chunks(db, current_user.id, file_id, index_version)
    if chunks is None:
        raise HTTPException(status_code=404, detail="Document not found or access denied.")
    fm = get_index_status(db, current_user.id, file_id)
    resolved_version = index_version if index_version is not None else fm["active_index_version"]
    return RAGChunkListResponse(
        file_id=file_id,
        index_version=resolved_version,
        chunks=[RAGChunkInspection(**c) for c in chunks],
        total=len(chunks),
    )
```

Register both routers (rag + rag-document) in `main.py`.

**Fresher note (Step 5):**
```text
The /documents router is thin — it reads blob bytes, persists the row, schedules
a worker, and delegates inspection to Step 3's helper. No Qdrant/Gemini/SQL
lives here. Tenant isolation is guaranteed because every query filters on
current_user.id.
```

**Verification:**
- `uv run python -c "from app.apis.routes.rag_document_routes import router; print('ok')"`
- Integration tests: upload 202 + worker scheduled; non-PDF returns 415; oversized returns 413; status returns 200 for owned file and 404 for another user's file; chunks returns 200/404 accordingly and respects `index_version`.

### Step 6 - Build the Streamlit Playground

Create:

```text
streamlit_app/
|-- app.py
|-- requirements.txt   (-or-) add streamlit + requests to a project-level dev requirement
```

The playground is a **thin client**. It reads `RAG_API_BASE_URL` (default `http://localhost:8000`), stores the user's bearer token in `st.session_state`, and calls the four backend endpoints using the `requests` library. It must **never** connect to MySQL, Qdrant, Redis, B2, or Gemini directly.

Implement three tabs (mirroring the master plan §4 contract):

1. **Upload & status** — `POST /documents` multipart, then poll `GET /documents/{id}/index-status` and render `progress` + `indexing_status`.
2. **Chunk inspector** — `GET /documents/{id}/chunks`; show each chunk's pages/word count and its `clean_text` (and `raw_text` when present). Never render model output as raw HTML; use `st.text_area`/`st.markdown` with escaping.
3. **Query playground** — `POST /rag/query` with `stream=True`; parse each `data: ` line, accumulate `{type: "token"}` text into a markdown box, and on `{type: "final"}` render `sources` as a dataframe and `diagnostics` inside an expander.

Sidebar: bearer-token input, `top_k` slider (1–20), and similarity-threshold slider (0.0–1.0), matching the request schema.

**Fresher note:**
```text
Streamlit is explicitly a development tool here. Its session state is NOT
authorization — the real gate is the backend JWT check. The client just holds
the token the user supplies and forwards it. All confidential output (scores,
timings, chunk internals) is gated behind the same endpoint ownership checks.
```

**Verification:**
- `pip install streamlit requests` then `streamlit run streamlit_app/app.py`.
- Point it at a running backend, log in with a real bearer token, upload a small PDF, watch status reach `INDEXED`, inspect a chunk, and stream a grounded answer with sources.
- Confirm no credentials are written into code — the token lives only in `st.session_state` / the sidebar input.

### Step 7 - Wire CORS for the Playground

The backend already configures `CORSMiddleware` from `settings.CORS_ORIGINS`. Streamlit serves on `http://localhost:8501` by default. If the playground runs from a browser against the API on a different origin, ensure `localhost:8501` (or the relevant origin) is in `CORS_ORIGINS`. Verify in `backend/app/core/config.py` and `.env`.

**Verification:**
- With the backend running, open the Streamlit playground, execute a query, and confirm no CORS error in the browser console. (If the playground runs server-side via `requests` rather than a browser fetch, CORS is not involved — confirm which mode is in use before changing origins.)

### Step 8 - Add Integration Tests for the New Routes

Create:

```text
backend/tests/integration/routes/test_rag_routes.py
backend/tests/integration/routes/test_rag_document_routes.py
```

Follow the existing `test_upload_file.py` conventions — `TestClient(app)`, dependency overrides for `get_db` and `get_current_user`, `unittest.mock` at the service boundary.

Cover:

- `test_rag_query_requires_auth` — no bearer token → 401.
- `test_rag_query_streams_token_and_final` — mock `app.apis.routes.rag_routes.run_rag_query` as an async generator yielding one `token` then one `final`; assert the response body frames both as `data: {...}` lines.
- `test_rag_query_invalid_file_ids_returns_400` — mock `validate_file_ids` to raise `ValueError`; assert 400 before any streaming.
- `test_rag_query_generation_error_maps_to_500` — mock `run_rag_query` to raise; assert clean failure (either SSE error frame or aborted with 500) and no partial garbage leaking as a 200.
- `test_upload_document_202` — mock the S3 `put_object` + worker; assert 202, row fields, and that `sync_rag_chunks_in_background` was scheduled.
- `test_upload_document_non_pdf_415` and `test_upload_document_oversized_413`.
- `test_index_status_owned_200` / `test_index_status_foreign_404`.
- `test_chunks_owned_200` (respects `index_version`) / `test_chunks_foreign_404`.

**Fresher note:**
```text
SSE tests read the raw `client.post(... , stream=True)` text and assert on the
`data: `-prefixed JSON lines — not on `response.json()` — because a streaming
response body is not a single JSON document.
```

## 7. Error Handling Plan

```text
+---------------------------------+-----------------------------------------------+----------+
| Error                           | Meaning                                       | Mapping  |
+---------------------------------+-----------------------------------------------+----------+
| FILE_ID_VALIDATION_FAILED       | Requested file_ids not owned/active/indexed  | 400      |
| DOCUMENT_NOT_FOUND_OR_DENIED    | id not owned by current_user                  | 404      |
| UNSUPPORTED_CONTENT_TYPE        | Upload not application/pdf                    | 415      |
| PAYLOAD_TOO_LARGE               | PDF exceeds RAG_MAX_PDF_BYTES                 | 413      |
| S3_PUT_FAILED                   | B2/S3 write of uploaded bytes failed          | 500, no row|
| RAG_INTERNAL                    | Unexpected orchestrator/service failure       | 500      |
| GENERATION_FAILED               | Gemini stream broke mid-answer                | SSE close |
| CACHE_READ/WRITE_FAILED         | Redis problem                                 | fail-open |
+---------------------------------+-----------------------------------------------+----------+
```

Guidelines:

- 404 always precedes internal errors for a foreign/unknown document.
- If the S3 `put_object` for `POST /documents` fails, **do not** create the `FileMetadata` row — the object and its metadata must be consistent. Return 500 with no side effects.
- Never let an SSE stream return HTTP 200 with an SQLAlchemy/driver traceback body. Map exceptions to a clean error frame or an appropriate status code.
- The orchestrator's abstain/fail-open semantics pass through unchanged — do not convert `insufficient_evidence` into an error.

## 8. Testing Plan

### 8.1 Worker Completion Tests

Test that the staging sequence is followed by `run_full_indexing` and that failures mark `FAILED_RETRYABLE` (mock S3/PDF/Gemini/Qdrant at the boundary). Assert the semaphore still wraps the whole body.

### 8.2 Inspection Helper Tests

Unit-test `get_index_status` / `get_chunks` against real SQLite:

- owned file returns correct status + progress mapping for every lifecycle state
- non-owned file returns `None`
- chunks are tenant-scoped (`user_id`), version-scoped, and ordered by `chunk_index`
- `index_version=None` defaults to `active_index_version`
- empty chunk list returns `[]` (not `None`) for an owned, unindexed file

### 8.3 SSE Endpoint Tests

- token + final framing is `data: {...}\n\n`
- leading `: connected` comment is emitted
- 401 without auth
- 400 on invalid `file_ids` (up-front validation)
- clean 500 / aborted response on generator exception

### 8.4 Document Endpoint Tests

- upload 202 + worker scheduled; non-PDF 415; oversized 413; S3 failure → 500 with no row
- status: owned 200, foreign 404
- chunks: owned 200 (with `index_version`), foreign 404

### 8.5 Streamlit Smoke (manual)

- full loop: upload → status reaches `INDEXED` → inspect chunk → stream an answer with sources
- no credentials in the repo, diagnostics gated behind expansion

### 8.6 Regression

```text
uv run pytest
```

Expect the full suite (290 tests pre-Phase 6 plus the new route/helper tests) to pass.

## 9. Development Order

```text
1. Extend rag_worker to run_full_indexing           (ingestion must auto-complete)
2. Add inspection.py helper + RAG status/chunk schemas
3. Add rag_routes.py with POST /rag/query (SSE)
4. Add rag_document_routes.py (upload / status / chunks)
5. Register both routers in main.py
6. Build streamlit_app/ playground
7. Verify CORS for the playground origin
8. Write unit tests (inspection) + integration tests (routes)
9. Full regression + manual smoke via Streamlit
```

Why this order works:

```text
Worker first       |  upload can't reach INDEXED until run_full_indexing is wired
    v              |
Helpers + schemas  |  routes have typed response models and clean data access
    v              |
Rag/query SSE      |  depends only on Phase 5 orchestrator (already done)
    v              |
Document routes    |  depend on worker + helpers + schemas
    v              |
Playground last    |  consumes all four endpoints together
```

If the worker is wrong, no upload reaches `INDEXED` and every downstream test fails confusingly — so fix ingestion first.

## 10. Commands

From backend:

```powershell
cd D:\Personal_Knowledge_Base\backend
```

Run new unit tests:

```powershell
uv run pytest tests/unit/services/rag/test_inspection.py
```

Run new integration tests:

```powershell
uv run pytest tests/integration/routes/test_rag_routes.py tests/integration/routes/test_rag_document_routes.py
```

Run the complete regression:

```powershell
uv run pytest
```

Imports check:

```powershell
uv run python -c "from app.apis.routes.rag_routes import router as r1; from app.apis.routes.rag_document_routes import router as r2; from app.services.rag.inspection import get_index_status, get_chunks; print('Phase 6 imports ok')"
```

Expected:

```text
Phase 6 imports ok
```

Start the backend (from `backend`):

```powershell
uv run uvicorn main:app --reload
```

Run the Streamlit playground (from repo root):

```powershell
python -m streamlit run streamlit_app/app.py
```

## 11. Code Review Checklist

```text
[ ] rag_worker calls run_full_indexing after staging, inside the semaphore
[ ] run_full_indexing runs in a new session, guarded, failures -> FAILED_RETRYABLE
[ ] Routes are thin: no Qdrant/Gemini/Redis/raw-SQL in handlers
[ ] /rag/query injects current_user.id into RAGRequest at the boundary
[ ] /rag/query frames orchestrator events exactly as: data: {json}\n\n
[ ] /rag/query sends Cache-Control: no-cache + leading :connected comment
[ ] /rag/query returns 400 on invalid file_ids before streaming
[ ] /documents rejects non-PDF (415) and oversized PDFs (413)
[ ] /documents does not create a row when the S3 put fails
[ ] GET /documents/{id}/index-status and /chunks filter on current_user.id
[ ] /chunks defaults index_version to active_index_version when omitted
[ ] Inspection models never expose source_key, user_id, or vectors
[ ] Streamlit holds the token only in session state; never in source
[ ] Playground never connects directly to MySQL/Qdrant/Redis/B2/Gemini
[ ] Playground renders sources/diagnostics inside expandable sections only
[ ] CORS origin for the Streamlit host is configured if browser-based
[ ] No cross-user data leak in any new endpoint
[ ] Existing /files/* presigned flow and React frontend are untouched
[ ] Integration tests cover auth, SSE framing, and status/chunk 200/404
```

## 12. Phase 6 Definition of Done

Phase 6 is complete when:

- the RAG worker automatically completes indexing (staging → embedding → Qdrant cutover → `INDEXED`) for a newly uploaded file
- `POST /rag/query` streams a grounded answer over SSE to an authenticated client, with `token` + `final` events framed exactly per the Phase 5 contract
- invalid `file_ids` return a clean 400; unauthenticated calls return 401; internal failures never leak a traceback as a 200
- `POST /documents` accepts a PDF, bounds its size, persists metadata owned by the user, schedules the worker, and returns 202
- `GET /documents/{id}/index-status` and `GET /documents/{id}/chunks` return tenant-isolated data for owned documents and 404 otherwise
- chunk inspection defaults to the current active version and supports an explicit `index_version`
- the Streamlit playground (in `streamlit_app/`) can upload, observe indexing progress, inspect chunks, and stream a grounded answer using only the four endpoints
- no route, schema, or playground output exposes vectors, B2 keys, source keys, or cross-tenant content
- the existing `/files/*` presigned flow, React frontend, and all Phases 1-5 services remain untouched and their tests still pass
- the full backend test suite passes (`uv run pytest`) including the new route and inspection tests

## 13. Handoff to Phase 7

Phase 6 provides the runnable, authenticated, end-to-end RAG surface. Phase 7 receives:

```text
A thin, authenticated FastAPI surface:
    POST /rag/query              (SSE answer stream)
    POST /documents              (multipart upload -> async index)
    GET  /documents/{id}/index-status
    GET  /documents/{id}/chunks

A full ingestion worker path:
    upload -> stage (Phases 2/3) -> run_full_indexing (Phase 4) -> INDEXED

A Streamlit playground client:
    upload / status / chunk inspection / grounded query, all via the API
```

Phase 7 will add:

```text
Unit + integration test hardening across the whole pipeline
Security tests (guessed file IDs, Qdrant payload tampering, cross-tenant hydration)
Metrics: recall@K/MRR/nDCG, citation support, abstention precision, cache hit rate
Rollout: internal tenants, small corpus, reconcile stores, runbooks
```

### SSE contract note for the React frontend (Phase 8)

`POST /rag/query` is the **production wire contract** and it **streams SSE**, not plain JSON:

```text
data: {"type": "token", "text": "Hello"}\n\n
data: {"type": "final", "sources": [...], "diagnostics": {...}}\n\n
```

The existing `queryRagPipeline()` in `frontend/src/apis/documentApi.js` currently assumes a plain-JSON response (`{ answer, sources, diagnostics }`). That assumption is **stale and does not match this endpoint**. Phase 8 rewrites the React RAG client to consume the SSE stream above (accumulate `token` text, resolve on `final`). Do not reintroduce a non-streaming JSON response for the chat; streaming is the intended production behavior.

That is the handoff: Phase 6 turns the Phase 5 engine into a usable product surface; Phase 7 proves it is correct, tenant-safe, and ready to operate at production scale; Phase 8 wires the React "Knowledge Base" chat to the `POST /rag/query` SSE contract.
