# RAG Phase 7 — Tests, Metrics, Security, and Rollout

**Technical Documentation** — written incrementally as development progresses.

> Scope: backend RAG / AI implementation files only. All content reflects current, implemented reality. No planned features, no speculation.

---

## Phase 7 Goal (One Paragraph)

Phases 1–6 built the RAG engine and hardened its FastAPI surface, shipping a solid unit + integration suite along the way. Phase 7 does **not** re-test that. Its job is to systematically close the remaining verification gaps the master plan calls out and make behavior observable and operable: (1) **harden** the unit tests around boundaries the existing suite only partially pins (multi-page attribution, async retry non-blocking, cache-key collision resistance, state-claim exclusivity), (2) add **scenario integration** tests (re-index-during-query, outage, partial-write retry idempotency, revocation), (3) add a **security** test group (tenant isolation, guessed file IDs, payload tampering, cache-key collision, no-auth), (4) build a dependency-free **metrics** engine plus a recall@K/MRR/nDCG/citation/abstention evaluation script, (5) instrument the orchestrator with per-stage latency and counters exposed via an admin-gated `/system/rag-metrics` route, and (6) produce **rollout plan** and **operational runbooks**. It also documents everything here in real time.

```
Existing Phase 1-6 tests (unit + integration)  <- baseline, all green
    |
    v
Phase 7 — all tasks COMPLETE:
    +-- hardened unit tests   (task 1: chunker / retry / cache-key / claims)  [done]
    +-- scenario integration  (task 2: reindex, outage, partial-write, revoke) [done]
    +-- security tests        (task 3: tenant iso, guessed ids, tamper, collision) [done]
    +-- metrics engine        (task 4: metrics.py + rag_evaluate.py + dataset) [done]
    +-- orchestrator metrics  (task 5: stage timing + /system/rag-metrics)  [done]
    +-- rollout plan          (task 6: internal tenants -> ramp)            [done]
    +-- operational runbooks  (task 7: reindex / rebuild / purge / quota / rollback) [done]
    +-- full regression       (task 8: uv run pytest) -> 428 passed, all green
```

---

## Progress Tracker (live state)

| # | Task | Files | Status | Documented |
|---|------|-------|--------|------------|
| 1 | Harden unit tests (chunker attribution, retry idempotency/async, cache-key collision, state-claim exclusivity) | `tests/unit/services/rag/test_{chunker,retry,query_utils,persistence}.py` | Done (243 unit RAG pass) | Section 1 |
| 2 | Scenario integration tests | `tests/integration/scenarios/` | Done (9 scenario tests) | Section 2 |
| 3 | Security tests | `tests/integration/security/` | Done (34 security tests) | Section 3 |
| 4 | Metrics engine + `rag_evaluate.py` + config | `app/services/rag/metrics.py`, `app/scripts/rag_evaluate.py`, `app/core/config.py`, `backend/data/eval_cases.jsonl` | Done (30 metric tests, demo/eval verified) | Section 4 |
| 5 | Orchestrator instrumentation + `/system/rag-metrics` | `app/services/rag/runtime_metrics.py`, `app/services/rag/rag_orchestrator.py`, `app/apis/routes/system.py` | Done (20 metric tests; 16 unit + 4 route incl. E2E) | Section 5 |
| 6 | Rollout plan | `RAG-tech-4.md` §6 (`backend/data/eval_cases.jsonl` baseline) | Done | Section 6 |
| 7 | Operational runbooks | `RAG-tech-4.md` §7 (reindex / rebuild / purge / quota / rollback) | Done | Section 7 |
| 8 | Full regression | `uv run pytest`, `rag_evaluate --demo`, `rag_evaluate data/eval_cases.jsonl` | Done (428 passed; eval harness reproducible) | Section 8 |

---

## 1. Task 1 — Hardened Unit Tests

### How We Built It

The Phase 6 unit suite already covered the *common* cases well (chunk window sizes 799/800/801, retry classification of 429/5xx/timeout vs 400/404, cache-key determinism for user/corpus/top_k/threshold/file-set, activation zero-chunk and count-mismatch rejection). Task 1 extends four existing files with targeted boundary cases — it does **not** duplicate anything already covered.

| File | Gap closed |
|------|-----------|
| `test_chunker.py` | Multi-page boundary attribution: page_end follows the *last word's* page; a chunk beginning with a page-break word reports the next page; a whole-page chunk reports `page_start == page_end`. |
| `test_retry.py` | `with_retry` calls `fn` exactly N+1 times (N failures + 1 success); added `TestWithRetryAsync` proving `with_retry_async` wakes the event loop via `asyncio.sleep`, never blocking `time.sleep`, and fails fast on non-retryable errors. |
| `test_query_utils.py` | Cache-key collision resistance: distinct prompt versions and model versions yield distinct keys; a large representative sample of distinct canonical inputs maps to a unique key set (via SHA-256 hash uniqueness). |
| `test_persistence.py` | State-claim exclusivity: a second claim for the same version replaces the first (never duplicates); distinct versions may coexist staged but only one is ever active. |

### Why It Was Tested

Phase 7's rule is that a feature is only "complete" when its *contract* is proven by tests. These four boundaries are where silent bugs hide:

- **Page attribution** is user-visible citation correctness. If `page_end` didn't follow the actual last word, citations would point at the wrong page.
- **Retry idempotency** is the difference between a duplicated embedding/answer and a clean one. The async variant must not block the server's event loop, or a 429 storm could stall the whole process.
- **Cache-key collisions** are a correctness and security hazard: two different queries sharing one cache entry serve the wrong answer to a user. Distinct inputs must never collide.
- **State-claim exclusivity** protects the zero-downtime invariant: a file must never hold two complete chunk sets for the same version.

### How It Works

```
Query cache key:  {user_id}:{corpus_revision}:{sha256(canonical_json)}
       canonical = {q, f(sorted)|'all', k, t, p(prompt), m(model)}
       => distinct question / files / top_k / threshold / prompt / model / user / revision
          all produce a distinct key  (collision-resistance test proves it)

Normalized chunk: page_start = first word's page, page_end = last word's page
       => a chunk crossing a page break records both pages; a page-break word
          is attributed to the page it physically sits on.

with_retry      (sync)  -> time.sleep(backoff)        N failures -> N+1 calls
with_retry_async(async) -> asyncio.sleep(backoff)     non-blocking, fails fast on 400/404

stage_document_chunks -> deletes prior rows for (file, version) then inserts
       => a concurrent re-claim replaces rather than accumulates (exclusive)
```

### Key Engineering Learnings

1. **`[]` and `None` file sets intentionally share a cache key.** `build_cache_key` maps `if file_ids else "all"`, so an empty list and "search all" are the same canonical input. That is *correct* semantic behavior — the collision-resistance sample must use genuinely distinct sets or it flags a non-bug.
2. **Retry must happen before the first token, never mid-stream.** The existing generation test already pins this: a retry re-opens the *stream* (so a 429 at open is clean), but once a token is yielded it must never re-open (which would duplicate partial output). Task 1 reinforces the boundary on the primitive (`with_retry_async`) rather than only at the generation layer.
3. **State-claim "exclusivity" here is replacement-based, not lock-based.** The persistence layer has no pessimistic DB lock; it deletes-then-inserts for (file, version). Exclusivity is preserved because `active_index_version` is only flipped by an atomic activation that validates the exact count — so a stale partial set can never be revealed.

### Verification

```powershell
uv run pytest tests/unit/services/rag          # 243 passed (was 230 at baseline)
```

Baseline 230 → 243: **+13 new hardening tests**, all green, no existing test modified incorrectly.

---

*(Sections 2–8 will be appended as Tasks 2–8 complete.)*

---

## 2. Task 2 — Scenario Integration Tests

### How We Built It

Four scenario files under `backend/tests/integration/scenarios/`, each proving a whole slice of the system end-to-end (real SQLite session for MySQL, real persistence/query utils, Qdrant/Gemini/Redis/S3 mocked at the boundary):

| Scenario | File | What it proves |
|----------|------|----------------|
| Re-index during query | `test_reindex_during_query.py` | While a re-index stages a v2 chunk set, every concurrent query sees the *active* v1 set — never a mixture of versions. |
| Outage behavior | `test_outage_behavior.py` | Redis down → query still returns a full answer (fail-open); Gemini 5xx exhausted → clean error, no partial stream; Qdrant down → error propagates before any token. |
| Partial-write retry | `test_partial_write_retry.py` | A mid-batch Qdrant failure retries with **identical deterministic UUIDv5 point IDs** (overwrite, never duplicate); cutover is refused until verification passes. |
| Revocation | `test_revocation.py` | `DELETE /files/{fileid}` removes the S3 object and MySQL record in strict order; the deleted file becomes non-retrievable (validation rejects it, searches never surface it); foreign deletes are 404. |

### Why It Was Tested

Unit tests pin each *function's* contract; scenario tests pin the **runtime behaviours** the master plan's error-handling table and the zero-downtime design actually depend on:

- **Re-index during query** holds the core invariant: an active query must never see a partially-populated new version. This is the behavior that production would notice as "answers changed mid-reindex".
- **Outage behavior** is the section-7 error table in motion — a production dependency going down must degrade to a full answer or a clean error, never a 500 with garbage.
- **Partial-write retry idempotency** is what makes the upsert loop safe to re-run: deterministic point IDs + verification-gated cutover.
- **Revocation** proves the deletion lifecycle: after delete, the document is unreachable through the only retrieval gate (owned + active + indexed validation), and the strict S3→Qdrant→MySQL ordering holds.

### How It Works

```
Re-index during query:
   queries read ONLY active_index_version (FileMetadata)
   stage v2 -> active stays v1 -> query still sees v1
   verify v2 count against MySQL -> swap active to v2 (atomic)
   => never a mixed/partial answer

Outage:
   Redis down   -> get/set_cached_answer catch RedisError, return None  (fail open)
   Gemini 5xx   -> with_retry_async exhausts -> raise -> caller frames SSE error
   Qdrant down  -> search_similar_chunks raises before any token -> clean error

Partial-write retry:
   point_id = uuid5(file_id, index_version, chunk_index)   (deterministic)
   retry re-sends the SAME ids -> Qdrant upsert overwrites, never duplicates
   verify_qdrant_index(count) must equal MySQL chunk_count before activation

Revocation:
   DELETE /files/{id}:  delete_s3_object -> delete_file_vector -> db.delete(file)
   validate_file_ids() requires owned+ACTIVE+INDEXED  => deleted rows rejected
   search_similar_chunks() only returns payloads whose file_id passed validation
```

### Key Engineering Learnings

1. **The retrieval gate is `validate_file_ids`, not Qdrant deletion.** When MySQL's FK cascade is off (as in this SQLite harness), the chunk rows can physically remain after `db.delete(file)`; the *retrievability* contract still holds because no query path reaches Qdrant without first passing ownership + ACTIVE + INDEXED validation. This is deliberate: validation is the always-on gate, making cascade failures non-security events.
2. **`search_similar_chunks` is sync, not async.** The orchestrator calls it without `await`; an `async def` fake silently returns a coroutine and fails later with `TypeError: object of type 'coroutine' has no len()`. Scenario fakes must mirror the real call shape.
3. **The upsert retry loop is per-batch and internal to `upsert_document_chunks`.** Retrying the whole call is wrong for the test too — the realistic driver is a *retryable* error (HTTP 500) inside one batch, proving the SAME point IDs are re-sent. Non-retryable errors (e.g. `TypeError`) would just mark the batch failed.
4. **A successful final event has no `insufficient_evidence` key** — that key only exists on abstain events. Asserting on success must check `sources`/`cache_hit`, not the abstention flag.

### Verification

```powershell
uv run pytest tests/integration/scenarios/    # 9 passed (1 reindex + 3 outage + 2 partial-write + 3 revocation)
uv run pytest                                 # 344 passed — full suite green, no regressions
```

Design note surfaced by the revocation test: the `/files/{id}` delete route removes the `FileMetadata` row via ORM and relies on the MySQL FK `ondelete=CASCADE` to physically clean `document_chunks`. Runtime retrievability is independent of that cleanup. (Tracked — no code change required at Phase 7; the gate is validation.)

---

## 3. Task 3 — Security Tests

### How We Built It

Five files under `backend/tests/integration/security/` sharing one `conftest.py` topology (Alice id 1 / active owns file 10, Bob id 2 / active owns file 20, Zoe id 3 / disabled owns file 30), with real SQLite for MySQL and identity injected either via dependency override (`authenticated`) or through the **real JWT dependency chain** (`real_jwt_db_only` + `create_access_token`):

| File | Proves |
|------|--------|
| `test_auth_no_token.py` | No token → 401 on every protected endpoint; garbage/unknown-subject token → 401; disabled user → 403; valid token → works; Bob's token cannot read Alice's doc. |
| `test_tenant_isolation.py` | Chunks/index-status/trigger are user-filtered (foreign → 404); foreign-only `file_ids` in a query → 400 before streaming; the route injects the **authenticated** user id, never a client claim; `validate_file_ids` strips foreign ids so they never reach Qdrant. |
| `test_guessed_ids.py` | Nonexistent and foreign IDs return the **same** 404 detail (no existence oracle); scoped queries for unknown ids → 400. |
| `test_payload_tampering.py` | Empty/oversized question, out-of-range `top_k` and `score_threshold`, non-integer `file_ids` → 422; mixed-ownership body can't pivot into another tenant. |
| `test_cache_isolation.py` | Cache keys are tenant-prefixed (`{user_id}:{corpus_revision}:…`); same question across tenants never collides; corpus revision invalidates; every key component (top_k/threshold/prompt/model) is encoded; the orchestrator keys on the **validated** scope. |

### Why It Was Tested

Phase 7's rule extends to the security surface: the tenant-isolation and auth contracts are load-bearing for a multi-user system and were only partially pinned before. These tests close the specific vectors the master plan lists:

- **Tenant isolation** — a user must never *see, trigger, delete, or receive retrieval for* another tenant's document, and the vector search must stay scoped even if a client sends a foreign file ID.
- **Guessed file IDs** — enumeration must not be possible: a missing id and a foreign id must be indistinguishable (`404 … access denied` for both).
- **Payload tampering** — the API must reject malformed/oversized input and never let a tampered body override identity or recall parameters beyond their configured caps.
- **Cache collisions** — a cached answer for one tenant must be unreadable by another; a wrong-shape key (e.g. missing `top_k`) would leak a *wrong* answer, and a missing user prefix would leak across tenants.
- **No-auth** — every endpoint must default-closed.

### How It Works

```
Identity is injected at the boundary, never taken from the body:
  rag_query(payload) -> validate_file_ids(current_user.id, payload.file_ids)
                      -> RAGRequest(user_id=current_user.id, …)     [route]
                      -> validate_file_ids(user_id, …)             [orchestrator]
                      -> search_similar_chunks(user_id, validated_file_ids, …)

Cache key:  f"{user_id}:{corpus_revision}:{sha256(canonical{q,f,k,t,p,m})}"
            => tenant prefix + every answer-shaping component
            => different user => different key, always

Auth (real JWT dependency):  signature -> exp -> sub int -> user exists -> status
            401 on missing/garbage/unknown-subject, 403 on disabled account

Guessed IDs: routes filter by fileid AND userid, with one combined message
             "…not found or access denied" for missing and foreign alike
```

### Key Engineering Learnings

1. **System tests need the *real* identity dependency, not only the override.** The `override_get_current_user` fast-path can't test JWT decoding, anonymous access, or the disabled-user 403. Adding `real_jwt_db_only` + `create_access_token` exercises the actual `get_current_user` pipeline against SQLite.
2. **The route validates but forwards the raw `payload.file_ids`; the orchestrator re-validates and forwards the *filtered* set.** Both layers are asserted: the route returns 400 when *no* id is valid, and the orchestrator drops foreign ids from a mixed set so they never reach `search_similar_chunks` (proven by asserting the `file_ids` kwarg).
3. **The existence-oracle guard is symmetric:** `404` with an identical detail for "no such id" vs "not yours". This is tested directly (`test_nonexistent_and_foreign_return_same_detail`) rather than just asserting the status code.
4. **`/files/10/view-url` is not a route** — the route is `POST /files/view-url`. The no-auth sweep must enumerate *actual* routes; guessing a RESTful-but-absent path yields a 404 that masks the real auth result.

### Verification

```powershell
uv run pytest tests/integration/security/      # 34 passed (6 auth/JWT + 7 tenant + 6 guessed-id + 9 tamper + 6 cache)
uv run pytest                                 # 378 passed — full suite green, no regressions
```

---

## 4. Task 4 — Metrics Engine + Evaluation Harness

### How We Built It

Three pieces, all stdlib-only (no numpy/sklearn — every formula is written out):

| File | Role |
|------|------|
| `app/services/rag/metrics.py` | Dependency-free metric primitives + `EvalCase`/`RAGEvaluationResult` + the aggregator `evaluate_cases()`. |
| `app/scripts/rag_evaluate.py` | CLI harness: reads a labeled JSONL dataset (one query per line) and prints per-query + aggregate metrics, optionally writing a JSON report. |
| `app/core/config.py` | Added `RAG_METRICS_ENABLED: bool = False` — the master switch for the observability surface (consumed by Task 5's `/system/rag-metrics` and the in-process counters). |
| `backend/data/eval_cases.jsonl` | Committed labeled dataset (4 cases) in the documented JSONL shape below — the reproducible quality baseline used by the rollout plan (§6). |

Primitives: `recall_at_k`, `precision_at_k`, `reciprocal_rank` + `mrr`, `dcg_at_k`/`ndcg_at_k`, `citation_accuracy`, `abstention_rate`, `abstention_rate_from_events`. The evaluator computes recall@5, recall@10, precision@10, MRR, nDCG@10, mean citation accuracy (over cases that declare citations), and abstention rate.

Dataset shape (JSONL):
```json
{"question": "...", "retrieved": ["<uuid>", ...], "relevant": ["<uuid>", ...],
 "cited": ["<uuid>", ...], "abstained": false}
```

### Why It Was Built

Before Task 4 there was no way to answer "is retrieval actually good?" — only *correct-by-construction* unit tests. The master plan calls for measurable ground truth so a reindex, an embedding-model bump, or a chunking tweak can be compared against a fixed dataset rather than eyeballed:

- **recall@5/10** — did the pipeline fetch the chunks that should answer the query?
- **MRR** — is the right chunk *first* (it drives the top of the context budget)?
- **nDCG@10** — graded ranking quality, robust to the top-K cutoff choice.
- **citation accuracy** — of the chunk IDs the model cited in its answer, how many were real retrieved sources (feeds the hallucination/CVE discussion from Phase 5)?
- **abstention rate** — how often the system correctly *declines* to answer rather than fabricating.

### How It Works

```
recall@k    = |relevant ∩ top_k(retrieved)| / |relevant|      (0.0 when no ground truth)
precision@k = |relevant ∩ top_k(retrieved)| / k
RR          = 1 / rank(first relevant hit)                    (0.0 when absent)
DCG@k       = Σ gain_i / log2(i+2)      gain ∈ {0,1} by relevance
nDCG@k      = DCG / ideal(DCG)          ideal = gains sorted descending
citation_acc= |cited ∩ relevant| / |cited|                    (1.0 when nothing cited)
abstention  = share of cases flagged `abstained` (or from final-event diagnostics)

JSONL -> [EvalCase] -> evaluate_cases(top_k=10) -> RAGEvaluationResult
  -> printed table + optional --json report (model tag left for comparison runs)
```

The engine reads orchestrator final events directly: `abstention_rate_from_events` derives flags from `diagnostics.insufficient_evidence`, and `citation_accuracy` reuses the retrieved set (`relevant` in the dataset) the way `validate_citations` checks against `valid_chunk_ids` in generation.

### Key Engineering Learnings

1. **Empty ground truth must score 0.0, never NaN or a division error.** `recall`/`nDCG` with no relevant items is unproven, not "perfect" — returning 0.0 keeps aggregates finite and honest, and the evaluator still reports `num_queries`.
2. **`cited=None` vs `cited=[]` carry different meaning.** A case *with* `cited` participates in citation accuracy (so a fabricated citation drags it down); a case without it is excluded from the mean rather than counting as 1.0. The dataset contract distinguishes them.
3. **`utf-8-sig` over `utf-8` for the JSONL reader.** Files created on Windows via PowerShell `Set-Content -Encoding utf8` carry a UTF-8 BOM; plain `utf-8` rejected the first line. `utf-8-sig` strips a BOM when present and reads BOM-less files identically — a one-line fix that makes the harness Windows-safe.
4. **Percentages that "feel" wrong expose formula mistakes, not code bugs.** `recall@2` on a 3-relevant set with `[a, b]` retrieved is 2/3, not 1/3 — the first metrics PR had the *test* expectation inverted, not the implementation.

### Verification

```powershell
# from backend/
uv run pytest tests/unit/services/rag/test_metrics.py        # 30 passed
uv run python -m app.scripts.rag_evaluate --demo             # aggregate table printed
uv run python -m app.scripts.rag_evaluate data/eval_cases.jsonl --json data/eval_report.json
#                                                            ^^^^^^^^^^^^^^^^^^^^^^^ plain path, no < > angle brackets:
#                                                            in cmd/PowerShell '<' is input redirection and
#                                                            '>' is output redirection, so <cases.jsonl> is
#                                                            parsed as redirects, not as a file path.
#                                                            'data/eval_cases.jsonl' ships with the repo.
uv run pytest                                                # 408 passed — full suite green
```

---

## 5. Task 5 — Orchestrator Instrumentation + `/system/rag-metrics`

### How We Built It

Three additions, one of which was already wired:

| File | Role |
|------|------|
| `app/services/rag/runtime_metrics.py` | New: a tiny, dependency-free, process-local store (thread-locked dicts) — counters, per-stage latency aggregates, and a defensive `snapshot()`. Every recorder is a **no-op unless `settings.RAG_METRICS_ENABLED` is True**, so instrumentation can never change behaviour. |
| `app/services/rag/rag_orchestrator.py` | Instrumented `run_rag_query` with stage timers (`_record_stage`) and counters around every phase: `validate`, `cache_read`, `search`, `hydrate`, `postprocess`, `generate`, `citation`, `cache_write`, `total`. Counters: `queries.total`, `cache_hit`, `cache_miss`, `abstain`, `citations.valid`. |
| `app/apis/routes/system.py` | Added `GET /system/rag-metrics`. |
| `backend/main.py` | Untouched — `system_router` was already included. |

The endpoint is gated at two levels, per the plan:
- **Authentication** (`get_current_user` JWT chain) — metrics are operational telemetry, never public.
- **Feature flag** — when `RAG_METRICS_ENABLED=False` (default) the route returns **404 "RAG metrics are disabled."** rather than live data, so the surface is never accidentally live. No `role`/`is_admin` column and no migration — the user's explicit choice.

### Why It Was Built

Tasks 1–4 proved correctness and produced quality numbers, but nothing on the live box told you *where a slow P95 query loses its milliseconds*. Phase 7's observability goal: per-stage latency (from a single instrumented orchestrator) plus lifecycle counters, exposed through one authenticated route and gated by a flag that defaults to **off** so production can stage it deliberately.

The store keeps only aggregates (`calls`, `total_ms`, `max_ms`; mean derived) — no sample history, no retention, no external service. It answers "is it slow-now and which stage" at a glance, and pairs with the dataset-driven quality harness (Task 4) for the "is it *good*" question. The stack rounds its own trade-off: a process-local store is the zero-ops option (an operator can read it, a Prometheus scrape can be added later by reading `snapshot()`).

### How It Works

```
run_rag_query (single pass, one generator)
  queries.total+1
  |-- validate   : ownership gate + corpus revision + cache key
  |-- cache_read : Redis get (fail-open)
  |     cache_hit  -> cache_hit+1, total, final, return
  |     else     -> cache_miss+1
  |-- search     : Qdrant retrieval (sync)
  |     no hits  -> abstain+1, total, final, return
  |-- hydrate    : MySQL row hydration
  |     empty    -> abstain+1, total, final, return
  |-- postprocess: score filter -> dedupe -> per-file cap -> budget fit
  |     empty    -> abstain+1, total, final, return
  |-- generate   : Gemini stream (finally-times even on early failure)
  |-- citation   : strip invalid, citations.valid += len(valid)
  |-- cache_write: Redis set (fire-and-forget)
  +-- total      : elapsed for the whole query

GET /system/rag-metrics
  no token      -> 401         (auth gate)
  flag off      -> 404         (feature gate)
  flag on + auth-> snapshot() -> {enabled, counters, stages{calls,total_ms,avg_ms,max_ms}}
```

### Key Engineering Learnings

1. **Instrumentation must be invisible when off.** Every recorder body starts with an `enabled()` check, so a disabled flag has exactly zero overhead and — critically — *zero behavioural surface*. The unit test pins this: with the flag off the orchestrator produces identical events and the store stays empty.
2. **`finally`-guarded stage timers beat post-hoc timing.** A mid-generation failure (consumer disconnect, Gemini 5xx mid-stream) silently skipped the generate sample in the first draft; wrapping the stream consumer in `try/finally` means the timer *always* samples, even when no final event is ever emitted. `test_generate_stage_recorded_even_when_stream_fails_midway` locks this in.
3. **An accumulator store must not allocate per sample.** `(calls, total_ms, max_ms)` captures everything a mean/max report needs and keeps `snapshot()` O(stages) — the durability/persistence trade-off is *your* call to make later, not a library decision.
4. **Route gating reads the flag at request time, not import time.** `settings.RAG_METRICS_ENABLED` is read inside the handler (and inside every recorder), so toggling the flag — or testing it — never needs a reload. That is also why `monkeypatch.setattr(settings, ...)` makes the whole gate trivially testable.
5. **A shared in-memory conftest is per-directory, not global.** The routes group needed the same SQLite + real-JWT fixtures as the security group; pytest scopes conftest files to their directory, so a small `tests/integration/routes/conftest.py` replicates (not imports) the setup. Families stay independent.

### Verification

```powershell
# from backend/
uv run pytest tests/unit/services/rag/test_runtime_metrics.py     # 9 passed
uv run pytest tests/unit/services/rag/test_orchestrator_metrics.py # 7 passed
uv run pytest tests/integration/routes/                          # 46 passed (incl. 4 metrics route tests)
uv run python -m app.scripts.rag_evaluate data/eval_cases.jsonl --json data/eval_report.json
#   sanity-check the quality harness + labeled dataset that Task 6's rollout
#   plan uses as its recall/MRR/citation baseline.
uv run pytest                                                    # 428 passed — full suite green
```

---

## 6. Task 6 — Rollout Plan (Internal Tenants → Ramp)

### Goal

This plan controls how the Phase 7 observability surface ships into the live environment. Rollout is **two-sided**: (a) the runtime telemetry built in Task 5, gated by the single global `RAG_METRICS_ENABLED` flag (default **off**), and (b) the quality harness built in Task 4 (`rag_evaluate.py` + `data/eval_cases.jsonl`) used as the **acceptance baseline** for every ramp decision.

It deliberately follows the master plan's "**internal tenants → ramp**": start with the operator's own account on a non-prod instance, widen to the trusted internal accounts, then make telemetry the default in production.

### Guiding Constraints (from implemented reality — nothing invented)

- **One global flag, no per-user admin.** `RAG_METRICS_ENABLED` is environment-scoped. There is no `role`/`is_admin` column and Phase 7 adds none; "who can read metrics" is therefore controlled by JWT-authenticated access to `GET /system/rag-metrics` plus the flag. Operators use their own valid user token.
- **The flag gates both write and read.** Flag off → every recorder is a no-op *and* the route returns 404, so an un-enabled environment is indistinguishable from pre-Phase 7 behaviour (pinned by the suite).
- **Metrics are process-local and ephemeral.** The store lives only in memory; an app restart resets it. Rollout therefore reads *live* values, never a ledger history.
- **No user-visible change at any stage.** Instrumentation only times branches that already run; query behaviour, SSE contract, and cache semantics are untouched (the 428-test suite locks this).
- **Quality is measured, not assumed.** The labeled dataset `data/eval_cases.jsonl` (4 cases, committed to `backend/data/`) is the reproducible quality gate for recall@5, MRR, citation accuracy, and abstention rate.

### Rollout Stages

**Stage 0 — Baseline (current state, default everywhere).**
`RAG_METRICS_ENABLED` unset/false. Run the harness once against the committed dataset to record the baseline aggregates (current: recall@5 0.75, MRR 0.625, nDCG@10 0.6445, citation accuracy 0.875, abstention 0.25). This snapshot is the comparison point for every later stage. No deployment.

**Stage 1 — Operator / canary instance (non-prod).**
- Set `RAG_METRICS_ENABLED=true` on **one** non-production instance only.
- Verify the gates behave: no token → 401; flag off elsewhere → 404; with your token → 200 `{enabled, counters, stages}` on this instance.
- Issue a few real queries, then read `/system/rag-metrics`: confirm `queries.total/cache_hit/cache_miss/abstain`, `citations.valid`, and per-stage aggregates are present and plausible (each stage `calls` ≥ the number of queries you ran).
- **Exit criteria:** per-stage timings visible and stable across repeated queries; `rag_evaluate` against `data/eval_cases.jsonl` reproduces the Stage 0 aggregates (proves the harness and the live path agree).

**Stage 2 — Internal trusted tenants (staging + first prod user).**
- Promote the flag to the staging instance and to the production instance **for the operator's own account only** (single-user proof before wider ramp).
- Watch the counters for a few days: cache hit ratio rising (warm corpus), abstention rate inside the Stage 0 expectation, `citations.valid` staying non-zero, and no stage (especially `search` + `generate`) drifting out of its Stage 1 envelope.
- The metrics route is authenticated: hand out tokens *only* to the operators who should see telemetry (the existing JWT gives you this for free).

**Stage 3 — General availability (flag on by default).**
- Leave `RAG_METRICS_ENABLED=true` in the production environment; `GET /system/rag-metrics` becomes the standard ops surface.
- **Optional, not built:** scrape `runtime_metrics.snapshot()` into Prometheus and add retention/alerting later — the store's `snapshot()` is already a dump-ready dict, but Phase 7 ships no exporter.

### Rollback & Fail-Safe

- **Instant:** unset/`false` the flag and restart the app. The route returns 404 and every recorder becomes a no-op — functionally identical to pre-Phase 7. Because the flag is read at request time, a restart is the only requirement (no migration, no data rollback).
- **Process-local data loss is by design:** a restart clears the in-memory store. Export `snapshot()` before a planned restart if the numbers matter for trending.
- **Nothing to reverse in the data plane:** rollout never touches MySQL, Qdrant, Redis, or the SSE contract, so rollback has zero residual state beyond the flag.

### Ongoing Cadence

Re-run `uv run python -m app.scripts.rag_evaluate data/eval_cases.jsonl --json data/eval_report.json` whenever the corpus meaningfully changes (reindex policy, chunking, embedding model, prompt version, top-k/threshold defaults). Compare against the Stage 0 baseline; if recall@5 or citation accuracy drops beyond the operator-set tolerance, re-evaluate the change before letting it settle into production answers — the harness is the memory that catches silent degradation.

### What This Plan Does Not Cover

- Per-user metric flags, quota enforcement, alerting rules, Prometheus exporter, dashboards, and metric retention (all listed as future, none implemented).
- Changing the SSE answer contract or query behaviour — this plan is observability-only.

---

## 7. Task 7 — Operational Runbooks

### Runbook map

| Scenario | Primary artifact(s) | Section |
|----------|---------------------|---------|
| A document indexed wrong / user asks to reprocess | `POST /documents`, `GET /documents/{id}/index-status`, `GET /documents/{id}/chunks` | 7.1 |
| Chunking or embedding policy changed → whole corpus | per-file `POST /documents` re-trigger + eval harness | 7.2 |
| Cached answers stale/must go | Redis key scan + del (TTL 3600 also expires them) | 7.3 |
| File must be gone (content + chunks) | `DELETE /files/{id}` (FK cascade) | 7.3 |
| Gemini rate limit / quota pain | `_embedding_semaphore` + concurrency/batch/backoff knobs; recovery backfill | 7.4 |
| Observatory / answers / indexing went sideways | `RAG_METRICS_ENABLED=false`, cache purge, reindex | 7.5 |

Everything below cites only implemented endpoints, functions, and settings. No artifact in this section is speculative.

### 7.1 Reindex a document

**Trigger:** a user reports a wrong answer from one file, or a file must be reprocessed after a pipeline change. **No downtime:** while the new version is staged, queries keep serving the currently-active version.

Steps (operator with the owning user's JWT):
```
1. POST /documents                    body {"file_id": N}
     -> 202, indexing_status becomes "PENDING"
     (worker claims atomically; PENDING/FAILED_RETRYABLE only -> dedup safe)
2. Poll GET /documents/{id}/index-status
     -> terminal states: INDEXED (good) | FAILED_RETRYABLE | FAILED_TERMINAL
3. Inspect content: GET /documents/{id}/chunks
     maybe ?index_version=V to compare staged vs active
4. Confirm cutover: index-status shows active_index_version bumped;
   corpus_revision bump automatically invalidates old answer-cache keys
   (cache key = {user_id}:{corpus_revision}:{query_hash}).
```

On failure: `FAILED_RETRYABLE` codes (e.g. `EMBEDDING_429`, storage read errors) self-heal — `retry_count < 3`, exponential backoff ≤ 300 s via `next_retry_at`, and the startup task `recover_and_backfill_unindexed_files()` re-queues them on the next boot. `FAILED_TERMINAL` codes (`ERROR_PDF_PARSE_FAILED`, `ERROR_NO_EXTRACTABLE_TEXT`, too-large PDF) are non-retryable: inspect `rag_error_message`, fix the source document, and re-trigger.

### 7.2 Full corpus rebuild

**Trigger:** `RAG_CHUNK_WORDS` / `RAG_CHUNK_OVERLAP_WORDS` / `GEMINI_EMBEDDING_MODEL` change, or a global re-chunk. Policy fields (`RAG_EXTRACTION_VERSION`, `RAG_CLEANING_VERSION`, `RAG_CHUNKING_VERSION`) exist precisely so a knob change is identifiable.

```
1. Change settings in others/.env and restart the app (settings load at startup).
2. There is no bulk CLI: enumerate ACTIVE files and re-trigger each:
     for each fileid N: POST /documents {"file_id": N}
   Concurrency is bounded globally (embedding semaphore) so batches are safe.
3. Poll GET /documents/{id}/index-status until each reaches INDEXED.
4. Verify on the corpus revision: reindexing bumps per-file corpus_revision,
   which forces new answer-cache keys — no manual cache flush needed.
5. Measure: uv run python -m app.scripts.rag_evaluate data/eval_cases.jsonl
   --json data/eval_report.json  and compare vs the §6 baseline.
```

**No downtime:** staging + cutover is atomic **per file** (`stage_document_chunks` writes a new version, `activate_rag_index_version` flips only after Qdrant verification). Queries during the rebuild are served entirely from complete old versions.

### 7.3 Purge

**Stale answer cache.** Answers have a 3600 s TTL (`RAG_CACHE_TTL_SECONDS`) and normal corpus changes invalidate keys via the revision component, so a manual purge is only for forced invalidation (a bad answer/prompt shipped). Keys look like `<user_id>:<corpus_revision>:<sha256hex>`:

```
redis-cli --scan --pattern '*:*:*' | ForEach-Object { redis-cli del $_ }
```

**Delete a file entirely (content + RAG chunks).** `DELETE /files/{id}` (as the owning user) removes the S3 object and the chunk rows via the MySQL FK `ON DELETE CASCADE`; the file leaves the retrievable set (`validate_file_ids` gate) immediately and can no longer be searched or cited.

**Old index versions are kept by design.** Non-active versions stay in `document_chunks` for inspection (`/chunks?index_version=V`) and as a rebuild fallback. There is no "prune old versions" endpoint — physical cleanup of a file requires deleting the file itself.

### 7.4 Gemini quota pressure

"Quota" in this system means **provider rate limits on embedding/generation calls** — there is no per-user storage quota to enforce.

**How to tell it is happening:** error codes `EMBEDDING_429` / rate-limit signs in `rag_error_message`, rows sitting at `FAILED_RETRYABLE` with rising `retry_count`, long `next_retry_at`, or `generate`/`cache_write` stage latency spikes in `/system/rag-metrics`.

**Knobs to relax the pressure** (all in `app/core/config.py`, restart after change):
```
MAX_CONCURRENT_EMBEDDING_TASKS  (5)   lower -> fewer parallel embeddings
RAG_EMBEDDING_CONCURRENCY       (4)   lower -> gentler on the API
RAG_EMBEDDING_BATCH_SIZE       (64, ≤128)  lower -> smaller per-call batches
RAG_BACKOFF_BASE               (1.0)  raise -> wider retry spacing (429/5xx/timeout)
RAG_MAX_RETRIES                 (5, ≤10)   cap -> bound total retry time
```

**Recovery:** retryable failures resume automatically — retry counts/heuristics gate re-queuing up to `retry_count < 3`, and the startup task `recover_and_backfill_unindexed_files()` re-queues survivors (max 25/run) on next boot. For an immediate retry, re-trigger per file with `POST /documents`.

### 7.5 Rollback

- **Observability surface:** set `RAG_METRICS_ENABLED=false` and restart → `/system/rag-metrics` returns 404 and all recorders become no-ops. No other state to reverse.
- **Bad answers (prompt/model change):** purge the answer cache (§7.3); every subsequent query regenerates. If a fresh *index* was the cause, reindex the affected files (§7.1) — the revision bump will invalidate keys even without a manual purge.
- **Bad reindex cutover:** the risk window is a single atomic `activate_rag_index_version` after Qdrant verification; there is **no "reactivate previous version" endpoint**. Supported recovery is to re-trigger indexing with corrected source content. Old versions remain readable via `/chunks?index_version=V` for diagnosis.

---

## 8. Task 8 — Full Regression & Phase 7 Wrap-up

### Test growth across Phase 7

| Stage | Suite count | Added |
|-------|------------|-------|
| End of Task 1 (hardened unit tests) | 243 | +boundary cases (chunker attribution, retry idempotency/async, cache-key collision, state-claim exclusivity) |
| End of Task 2 (scenario integration) | 344 | +9 (reindex-during-query, outage: Redis/Gemini/Qdrant, partial-write retry, revocation) |
| End of Task 3 (security) | 378 | +34 (no-auth/JWT, tenant isolation, guessed IDs, payload tampering, cache isolation) |
| End of Task 4 (metrics engine) | 408 | +30 (metric primitives against 10-case edge tables) |
| End of Task 5 (orchestrator metrics) | 428 | +20 (9 runtime-metrics store, 7 orchestrator instrumentation, 4 `/system/rag-metrics` routes incl. E2E) |
| **Final regression (Task 8)** | **428** | — all green, no flake |

Every stage ended green before the next began; the final full run is a clean pass across **all** unit + integration groups (`unit/`, `integration/scenarios/`, `integration/security/`, `integration/routes/`).

### Final verification

```powershell
# from backend/
uv run pytest                          # 428 passed — full Phase 7 regression, all groups green
uv run python -m app.scripts.rag_evaluate --demo             # harness self-check
uv run python -m app.scripts.rag_evaluate data/eval_cases.jsonl --json data/eval_report.json
#   committed labeled baseline, reproducible:
#   recall@5 0.75 | recall@10 0.75 | precision@10 0.3 | MRR 0.625 | nDCG@10 0.6445
#   citation accuracy 0.875 | abstention rate 0.25     (4 cases)
```

### What Phase 7 shipped (recap)

- **Hardened unit coverage** around the boundaries the Phase 6 suite only partially pinned.
- **Scenario + security integration groups** proving the orchestrator's invariants under reindex, outages, partial writes, revocation, and cross-tenant abuse.
- A **dependency-free metrics engine** (`app/services/rag/metrics.py`), a **CLI evaluation harness** (`app/scripts/rag_evaluate.py`), and a **committed labeled dataset** (`backend/data/eval_cases.jsonl`) — the reproducible quality baseline used by the rollout plan.
- **In-process observability**: `app/services/rag/runtime_metrics.py` (per-stage latency + counters, flag-gated) instrumented into `rag_orchestrator.run_rag_query`, surfaced at `GET /system/rag-metrics` behind a two-layer gate (JWT auth + `RAG_METRICS_ENABLED`, default off).
- A **rollout plan** (internal tenants → ramp) and five **operational runbooks** (reindex / rebuild / purge / quota / rollback), every step grounded in implemented endpoints, functions, and settings — this document (§1–§8) is the live record.
