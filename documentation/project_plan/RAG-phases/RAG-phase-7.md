# RAG Phase 7 - Tests, Metrics, Security, and Rollout

## 1. Phase Goal

Phases 1-6 built the RAG engine (extraction → chunking → persistence → embeddings → Qdrant → generation → cache), exposed it through an authenticated FastAPI surface (`POST /rag/query` SSE, `POST /documents`, status, and chunk endpoints), and (per the Phase 8 plan) will integrate it into the React "Knowledge Base" chat.

Phase 6 already shipped **unit + integration tests** as part of its own development order (see "8. Testing Plan" and "8.1-8.4"). Phase 7 does **not** re-do that. Instead it systematically closes the remaining verification gaps the master plan calls out, adds **security testing**, introduces **quality and operability metrics**, formalizes a **rollout plan**, and produces **runbooks** for production operations.

```text
Existing Phase 1-6 tests (unit + integration)
    |
    v
Phase 7 hardens:
    +-- additional unit tests (chunk boundaries/attribution, retry boundaries)
    +-- integration tests (real SQLite/MySQL, Redis, Qdrant mocks, re-index, outage)
    +-- security tests (guessed file IDs, payload tampering, cache collisions, cross-tenant)
    |       |
    |       v
    +-- metrics pipeline (recall@K/MRR/nDCG, citation support, abstention, cache hit, latency p50/p95/p99)
    |       |
    |       v
    +-- rollout plan (internal tenants -> small corpus -> reconcile -> evaluate -> ramp)
    |       |
    |       v
    +-- operational runbooks (re-index, collection rebuild, user purge, quota, rollback)
```

The central architecture rule for Phase 7:

```text
A RAG feature is complete only when correctness, grounding, and tenant isolation
are proven by tests, and its behavior is observable through metrics and runbooks.
```

By the end of Phase 7, the project should be able to:

- enumerate and run unit tests covering every Phase 1-6 contract (chunk boundaries, UUIDs, retries, cache fail-open, filters, state claims)
- run integration tests against real SQLite for MySQL-backed behavior and mocked B2/Qdrant/Redis/Gemini for IO-backed behavior
- run security tests proving no cross-tenant leak, no guessed file-ID access, no Qdrant payload tampering, and no cache-key collision
- emit and reason about retrieval quality metrics (recall@K, MRR, nDCG), citation support, abstention precision, indexing backlog, Gemini 429 rate, Qdrant/MySQL mismatch rate, and cache hit rate
- report per-stage latency percentiles (p50/p95/p99) for the RAG query path
- follow a documented rollout sequence from internal tenants to full ramp
- follow runbooks for re-index, collection rebuild, user purge, quota exhaustion, and rollback

Phase 7 does **not** add:

```text
New retrieval/generation/chunking algorithms       - Phases 2/4/5
New backend endpoints or schemas                   - Phase 6
Frontend React integration                          - Phase 8 (Knowledge Base chat)
New data models or migrations                       - Phase 3
```

## 2. Phase 6 Status Check

Before writing this plan, the current test suite and RAG services were checked.

### Existing test inventory (Phase 1-6, already present)

```text
backend/tests/unit/services/rag/
|-- test_text_cleaner.py       - normalize_text, repeated-margin stripping
|-- test_chunker.py            - 799/800/801-word windows, overlap, checksums, page ranges
|-- test_pdf_extractor.py      - pages, empty/invalid/scanned bytes, doc close-on-error
|-- test_document_processor.py - S3 read -> extract -> clean -> chunk (mocked IO)
|-- test_ids.py                - deterministic UUIDv5 chunk IDs
|-- test_embedding.py          - Gemini response validation, dimensions, ordering
|-- test_retry.py              - retry policy (429/5xx/timeout, backoff+jitter)
|-- test_persistence.py        - stage_document_chunks, activate_rag_index_version, state claims
|-- test_qdrant_service.py     - upsert batches, verify index, cleanup old versions
|-- test_indexing_service.py   - build/verify/cutover
|-- test_query_utils.py        - validate_file_ids, cache-key identity, filter/dedup/cap
|-- test_query_service.py      - search_similar_chunks, tenant filter
|-- test_answer_cache.py       - fail-open cache get/set
|-- test_generation.py         - source blocks, prompt split, citation validation, stream retry
|-- test_orchestrator.py       - cache miss/hit, abstain paths, diagnostics

backend/tests/integration/routes/
|-- test_rag_routes.py         - (Phase 6) rag/query SSE auth/framing/errors
|-- test_rag_document_routes.py- (Phase 6) upload/status/chunks
|-- test_upload_file.py, test_pagination.py, test_semantic_search.py, test_system.py
```

Baseline verified gate:

```text
uv run pytest      # 290 passed (pre-Phase 6) + Phase 6 additions
```

### Gaps Phase 7 closes

The master plan Phase 7 introduces four categories that current tests only partially cover:

1. **Unit-test depth** — several boundary/attribution cases exist but can be tightened (e.g. multi-page chunk attribution, partial-write retry idempotency, cache-key collision resistance).
2. **Integration breadth** — most external IO is mocked at the unit level; Phase 7 adds scenario-level integration tests (re-index during query, outage behavior, deletion/access revocation).
3. **Security** — no dedicated security tests yet (guessed file IDs, payload tampering, cross-tenant hydration, cache-key collision).
4. **Metrics / rollout / runbooks** — none of these are code; they are new scripts, a metrics schema, and documentation.

## 3. What Phase 7 Adds

```text
+-------------------------------+----------------------------------------------+
| Area                          | Phase 7 work                                 |
+-------------------------------+----------------------------------------------+
| Hardened unit tests           | Multi-page attribution, retry idempotency,    |
|                               |   cache-key collision resistance              |
| Scenario integration tests    | Re-index during query, outage, revocation     |
| Security tests                | Guessed IDs, payload tampering, cross-tenant  |
| Metrics schema                | JSON/table for RAG evaluation runs            |
| Evaluation script             | recall@K / MRR / nDCG / citation / abstention |
| Backend metrics endpoints     | Per-stage latency + counters (p50/p95/p99)    |
| Rollout plan                  | Internal tenants -> reconcile -> ramp         |
| Operational runbooks          | re-index / rebuild / purge / quota / rollback |
+-------------------------------+----------------------------------------------+
```

## 4. Existing Project Context

Relevant files Phase 7 builds on:

```text
backend/app/services/rag/
|-- retry.py               - with_retry / with_retry_async (429/5xx/timeout policy)
|-- ids.py                 - build_chunk_id() deterministic UUIDv5
|-- persistence.py         - stage_document_chunks, activate_rag_index_version
|-- query_utils.py         - validate_file_ids, build_cache_key, filter/dedup/cap
|-- answer_cache.py        - fail-open get/set
|-- generation.py          - validate_citations, generate_answer_stream
|-- rag_orchestrator.py    - run_rag_query (SSE event stream + diagnostics)
|-- schemas.py             - RAGQueryRequest, RAGQueryDiagnostics, RAGSourceResponse
|
backend/app/core/config.py - RAG_* and GEMINI_* settings (thresholds, top-k, batch, retry)
backend/app/scripts/rag_phase5_smoke.py - existing end-to-end smoke tool (reused for eval harness)
backend/tests/unit/services/rag/  - existing test suite (extend, don't duplicate)
```

## 5. Design Principles

### 5.1 Tests Prove Contract, Not Implementation

Every test asserts an externally observable contract (state transition, cache-key determinism, tenant filter, abstain-on-no-evidence). Tests avoid reaching into private internals. If a test requires mocking, it mocks at the boundary (S3/Boto3, Redis client, Qdrant client, Gemini SDK), never re-implements the service.

### 5.2 Real Storage for DB Tests, Mocks for IO

MySQL-backed logic (persistence, hydration, state claims, tenant isolation) is tested against **real SQLite** (`Base.metadata.create_all` + `StaticPool`) — the proven repo pattern that catches real SQL bugs. External systems (S3/B2, Gemini, Qdrant, Redis) are always **mocked** so tests are fast, deterministic, and offline-safe.

### 5.3 Security Is a First-Class Test Category

Phase 7 treats tenant isolation as a security property to be attacked, not just a filter to be exercised. Tests attempt cross-tenant reads, guessed file IDs, Qdrant payload tampering, and cache-key collisions, and assert the system rejects them.

### 5.4 Metrics Report Reality, Not Aspiration

Metrics are computed from real evaluated runs (the smoke/eval script), persisted, and rendered as simple tables so before/after comparisons are possible. Latency percentiles come from process-level timing already produced by the orchestrator's `query_time_ms` diagnostics, aggregated per stage.

### 5.5 Rollout and Runbooks Are Code-Reviewed Artifacts

The rollout plan and runbooks live with the code so they stay in sync with the actual implementation. They are plain, step-wise, and safe to execute without guesswork.

## 6. Implementation Steps

### Step 1 - Harden Unit Tests

Extend the existing unit suite (do not duplicate covered cases). Add targeted tests:

**1a. Multi-page chunk attribution** (`test_chunker.py`):
- a chunk spanning pages reports the correct `page_start`/`page_end`
- boundary word exactly at a page break is attributed to the correct page
- a chunk wholly inside one page reports `page_start == page_end`

**1b. Retry idempotency and classification** (`test_retry.py`):
- `with_retry` classifies 429, timeouts, and retryable 5xx as retryable; 400/404 as non-retryable
- on success after N failures, `fn` is called exactly N+1 times
- `with_retry_async` does not block the event loop between attempts (uses `asyncio.sleep`)
- generation stream retry opens the stream before the first token but does **not** re-open mid-stream (existing behavior, pin with a test)

**1c. Cache-key collision resistance** (`test_query_utils.py`):
- distinct questions, top_k, thresholds, file sets, prompt versions, model versions, and corpus revisions all produce distinct keys
- same canonical input (including ==-ordered file_ids) produces the same key
- very different inputs never collide (hash the output set and assert uniqueness over a representative sample)

**1d. State-claim exclusivity** (`test_persistence.py`):
- only one concurrent `stage_document_chunks` claim succeeds for a given file/version
- `activate_rag_index_version` rejects a zero-chunk or mismatched-count cutover

**Verification:** run the extended suite; expect all prior tests plus the new ones to pass.

```powershell
uv run pytest tests/unit/services/rag
```

### Step 2 - Scenario Integration Tests

Create:

```text
backend/tests/integration/scenarios/
|-- test_reindex_during_query.py
|-- test_outage_behavior.py
|-- test_revocation.py
```

Use real SQLite where MySQL logic is involved; mock Gemini/Qdrant/Redis at the boundary and drive the orchestrator (`run_rag_query`) or the relevant services.

- **Re-index during query:** while one version is active, stage + index a newer version; assert a concurrent query still sees only the previous complete active version, then the new one after cutover — never a mix.
- **Partial-write retry:** simulate a Qdrant upsert that fails mid-batch; assert `upsert_with_resume` re-uses identical UUIDv5 point IDs so a retry overwrites rather than duplicates, and that cutover is refused until verification passes.
- **Outage behavior:** with Redis down (mock `get_redis_client` raising), assert `run_rag_query` still returns a full answer and never 500s (fail-open). With Gemini down transiently, assert retry then clean failure, and with Qdrant down, assert graceful abstain/error — never a half-stream.
- **Deletion / access revocation:** delete a file (S3 + Qdrant + DB per the existing `/files/{id}` delete flow); assert a subsequent query/hydration returns no chunks for the deleted file and cache keys referencing the old corpus revision are unreachable on next corpus revision.

**Verification:**

```powershell
uv run pytest tests/integration/scenarios
```

### Step 3 - Security Tests

Create:

```text
backend/tests/integration/security/
|-- test_tenant_isolation.py
|-- test_guessed_file_ids.py
|-- test_payload_tampering.py
|-- test_cache_key_collision.py
```

Assert each attack is rejected:

- **Guessed file IDs:** user B requests `file_ids=[A's id]`; `validate_file_ids` drops it and raises (or the endpoint returns 400). Hydration never returns B content to A.
- **Qdrant payload tampering:** craft Qdrant payload with a `user_id` for another tenant; assert the MySQL hydration JOIN on `user_id` + `active_index_version` still filters it out (defense-in-depth in the authoritative store).
- **Cross-tenant hydration:** user A's `hydrate_chunks` never returns a `document_chunks` row belonging to user B, regardless of the chunk IDs passed.
- **Cache-key collision:** different users (different `user_id`) can never share an answer cache entry; assert keys differ even for identical questions.
- **SSE no-auth:** `POST /rag/query` without a bearer token returns 401 (already covered in Phase 6; keep in the security group for completeness).

**Verification:**

```powershell
uv run pytest tests/integration/security
```

### Step 4 - Metrics: Evaluation Script

Create:

```text
backend/app/scripts/rag_evaluate.py
```

A deterministic evaluation harness that measures retrieval and generation quality on a small labelled corpus.

Inputs:

- a list of `(question, golden_chunk_id | golden_file_id)` pairs
- an optional answer ground truth for citation/abstention checks

Outputs (printed + optionally written to a JSON/CSV under `backend/rag_metrics/`):

```text
recall@K         - fraction of golden chunks retrieved in top-K
MRR              - mean reciprocal rank of the first relevant hit
nDCG@K           - normalized discounted cumulative gain over top-K
citation_support - fraction of answers whose citations all validate against retrieved IDs
abstention       - fraction of no-evidence questions correctly abstained (precision)
```

Reuse `run_rag_query`/`search_similar_chunks` directly (real or mocked Gemini at the caller's discretion) so the metric measures the real pipeline. The script must not require manual S3 key entry per run — it reads a corpus manifest of already-indexed `file_ids`, mirroring the Phase 5 smoke tool's "no secrets on the CLI" rule.

Add small config settings if needed (e.g. `RAG_EVAL_TOP_K_LIST: list[int] = [1, 3, 5, 10]`) to `backend/app/core/config.py`.

**Verification:** run on a small labelled corpus and confirm all four metrics are computed and printed with sensible values.

```powershell
uv run python -m app.scripts.rag_evaluate
```

### Step 5 - Metrics: Operability Counters and Latency Percentiles

Add lightweight, dependency-free instrumentation (no Prometheus required — keep it simple for an individual project):

- A module:

```text
backend/app/services/rag/metrics.py
```

capturing per-stage counters and latencies in-process:

```text
Counter: rag_queries_total, rag_cache_hits, rag_cache_miss,
         rag_insufficient_evidence, rag_generation_calls,
         rag_qdrant_searches, rag_mysql_mismatch, gemini_429s,
         rag_indexing_started, rag_indexing_completed
Histogram-like: rag_stage_latency_ms { stage: retrieve|hydrate|filter|generate|total }
Percentiles: p50, p95, p99 computed at read time
```

- A thin read-only endpoint (or reuse an existing system route pattern) to expose a plain-JSON snapshot, gated behind a development/admin flag:

```text
GET /system/rag-metrics   (Phase 6-style thin route; returns counters + percentiles)
```

Follow the existing thin-route rule: the route just serializes `metrics.py`, which owns all recording.

Integrate `rag_orchestrator.py` to record `rag_stage_latency_ms` and the counters at the existing measurement points (it already times the total; add stage timestamps around retrieve/hydrate/generate).

**Verification:** run a few orchestrator calls, then hit `GET /system/rag-metrics` and confirm counters increment and p50/p95/p99 are populated.

### Step 6 - Rollout Plan

Write a rollout runbook (markdown in `documentation/project_plan/` or `docs/`), step-wise:

```text
1. Internal tenants only   - enable RAG for a small trusted set; real user queries
2. Small corpus            - index a representative small corpus; reconcile stores
3. Reconcile stores        - verify MySQL chunk_count == Qdrant point_count; fix drift
4. Quality evaluation      - run rag_evaluate, compare against baseline metrics
5. Load check              - observe Gemini 429s, cache hit rate, latency p95; confirm within budget
6. Ramp                    - widen tenant pool gradually (e.g. 10% -> 50% -> 100%)
7. Halt/rollback criteria  - defined thresholds (e.g. abstention < X, latency p95 > Y, mismatch > 0)
```

This is a planning artifact — it references, but does not implement, the metrics from Steps 4-5.

### Step 7 - Operational Runbooks

Write runbooks (markdown) covering:

```text
re-index a document          - force-rebuild via run_full_indexing (smoke tool --force-reindex)
collection rebuild           - create new Qdrant collection, re-embed, point index, cutover
user purge                   - delete file_metadata + document_chunks + Qdrant points + cache; bump corpus_revision
quota exhaustion             - Gemini 429 surges: raise RAG_MAX_RETRIES/backoff, reduce concurrency, back off batch
rollback                     - revert active_index_version to prior verified version
```

Each runbook states: when to use it, exact commands, side effects, and the verification step after completion.

### Step 8 - Wire Metrics into Orchestrator

> Editorial position note: an updated orchestration that records stage timings belongs in Phase 7 since metrics are a Phase 7 concern. Keep the edit minimal and non-behavioral so existing orchestrator tests still pass (they assert event shape, not timing).

Edit `backend/app/services/rag/rag_orchestrator.py` (and register the `/system/rag-metrics` thin route) to:

- record `rag_queries_total`, `rag_cache_hits`, `rag_cache_miss`, `rag_insufficient_evidence`, `rag_generation_calls`
- time the `retrieve`, `hydrate`, `filter`, `generate` sub-stages into the metrics histogram
- leave the SSE event contract exactly unchanged

**Verification:** rerun `uv run pytest tests/unit/services/rag/test_orchestrator.py` — event shape assertions must still pass unchanged.

## 7. Error Handling Plan

```text
+------------------------------+------------------------------------------------+-------------+
| Condition                    | Handling                                       | Layer       |
+------------------------------+------------------------------------------------+-------------+
| Merge/upsert mid-batch fail  | Retry with same UUIDv5 ids (idempotent), halt cutover | integration |
| Redis outage                 | Fail open: full answer, no 500                 | integration |
| Gemini transient 5xx          | with_retry_async, bounded backoff, then clean fail | unit/integ |
| Qdrant down                  | Graceful abstain/error, never half-stream      | integration |
| Guessed/tampered IDs          | Rejected (400 / dropped / filtered)            | security    |
| Cross-tenant hydration        | JOIN filters on user_id + active version       | security    |
| Metrics endpoint unauthorized | 401/403 (admin flag off)                      | security    |
+------------------------------+------------------------------------------------+-------------+
```

## 8. Testing Plan

### 8.1 Unit (hardened)

chunk attribution, retry classification/idempotency, cache-key collision resistance, state-claim exclusivity.

### 8.2 Scenario Integration

re-index during query, partial-write retry idempotency, Redis/Gemini/Qdrant outage, deletion/revocation.

### 8.3 Security

guessed IDs, payload tampering, cross-tenant hydration, cache-key collision, no-auth SSE.

### 8.4 Metrics

- `rag_evaluate` computes recall@K/MRR/nDCG/citation/abstention on a small corpus
- `/system/rag-metrics` returns counters + p50/p95/p99
- orchestrator still passes its event-shape tests after instrumentation

### 8.5 Regression

```powershell
uv run pytest
```

## 9. Development Order

```text
1. Harden unit tests (attribution, retry, cache-key, state claims)
2. Scenario integration tests (re-index, partial-write, outage, revocation)
3. Security tests (tenant isolation, guessed IDs, tampering, collisions)
4. Metrics engine + rag_evaluate script
5. Orchestrator instrumentation + /system/rag-metrics route
6. Rollout plan (planning artifact, depends on metrics)
7. Operational runbooks
8. Full regression
```

Why this order:

```text
Unit hardening first |  cheapest place to catch contract bugs
    v                |
Scenario integration |  proves multi-step flows hold under interference
    v                |
Security next        |  must be proven before any wider access
    v                |
Metrics + eval       |  needed to set rollout go/no-go thresholds
    v                |
Rollout + runbooks   |  consume metrics thresholds and test-verified behavior
```

## 10. Commands

From backend:

```powershell
cd D:\Personal_Knowledge_Base\backend
```

Run the full suite:

```powershell
uv run pytest
```

Run the new hardening/security/scenario groups:

```powershell
uv run pytest tests/unit/services/rag
uv run pytest tests/integration/security
uv run pytest tests/integration/scenarios
```

Run the evaluation harness (on a small labelled corpus):

```powershell
uv run python -m app.scripts.rag_evaluate
```

Inspect live metrics (with backend running):

```powershell
# (dev-only) GET /system/rag-metrics
```

## 11. Code Review Checklist

```text
[ ] Unit tests assert external contracts, not private internals
[ ] MySQL-backed logic tested against real SQLite; IO mocked at the boundary
[ ] Retry classified correctly: 429/timeout/retryable-5xx vs 400/404
[ ] Retry uses same UUIDv5 point ids (idempotent upsert), cutover refused on failure
[ ] Cache-key collision: distinct inputs -> distinct keys; identical -> identical
[ ] State claims are exclusive (single-claim) and count-validated
[ ] Re-index during query never serves a mixed version
[ ] Redis outage -> fail open, no 500; Gemini/Qdrant down -> clean, no half-stream
[ ] Security: guessed IDs rejected, payload tampering filtered, no cross-tenant hydration
[ ] Authentication still enforced on the SSE endpoint (401)
[ ] rag_evaluate computes recall@K, MRR, nDCG, citation support, abstention
[ ] /system/rag-metrics returns counters + p50/p95/p99, gated behind admin flag
[ ] Orchestrator instrumentation changes only metrics, never the SSE event shape
[ ] Orchestrator event-shape tests still pass unchanged
[ ] Rollout plan and runbooks are written and referenced, with go/no-go thresholds
[ ] Full regression passes (uv run pytest)
```

## 12. Phase 7 Definition of Done

Phase 7 is complete when:

- the unit suite is hardened for chunk attribution, retry classification/idempotency, cache-key collisions, and state-claim exclusivity, and all pass
- scenario integration tests prove re-index-during-query consistency, partial-write retry idempotency, and Redis/Gemini/Qdrant outage behavior, and all pass
- security tests prove no cross-tenant leak, no guessed file-ID access, no payload-tampering bypass, and no cache-key collision across users, and all pass
- `rag_evaluate.py` computes recall@K / MRR / nDCG / citation support / abstention on a labelled corpus
- the orchestrator records per-stage latency and counters, exposed read-only via `/system/rag-metrics` (admin-gated) with p50/p95/p99
- the orchestrator's SSE event contract and its event-shape tests are unchanged and passing
- a rollout plan with go/no-go thresholds and internal-tenant-first sequencing exists
- operational runbooks exist for re-index, collection rebuild, user purge, quota exhaustion, and rollback
- the full backend suite passes (`uv run pytest`)

## 13. Handoff to Phase 8

Phase 8 integrates the React "Knowledge Base" chat. Phase 7 hands it a verified, secure, observable backend:

```text
Proven correctness: hardened unit + scenario integration tests
Proven tenant isolation: security tests
Proven operability: /system/rag-metrics + rag_evaluate + upcoming rollout/runbooks
Stable wire contract: POST /rag/query (SSE token + final events)
```

Phase 7's metrics thresholds are the acceptance criteria Phase 8's live chat should keep meeting (e.g. cache hit rate up, p95 latency within budget, abstention on no-evidence). That is the handoff: Phase 7 proves the engine is correct, secure, and measurable; Phase 8 builds the user-facing client on top of that proven surface.
