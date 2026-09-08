# RAG Phase 8 — React Knowledge Base Chat Integration

**Technical Documentation** — written incrementally as development progresses.

> Scope: frontend React implementation files only. All content reflects current, implemented reality. No planned features, no speculation.

---

## Phase 8 Goal (One Paragraph)

Phases 1–7 built the complete RAG engine, exposed it through an authenticated FastAPI SSE surface, and proved it safe and measurable. **Phase 8 is a pure frontend phase**: it integrates RAG into the existing React + Material UI frontend as a dedicated **"Knowledge Base"** chat page. An authenticated user selects up to 5 of their already-indexed documents by friendly name, sends a question, and watches a grounded answer stream in live with verifiable citations. No backend endpoints are added; no custom CSS is written; network / logic / view layers stay strictly decoupled.

```
Phase 6 backend contract (POST /rag/query SSE)
    |
    v
Phase 8 frontend integration (this document):
    +-- ragApi.js            [network: SSE wire client + pure parser]
    +-- ragService.js        [logic: max-5, INDEXED filter, file_id mapping]
    +-- DocumentMultiSelect  [view: MUI chips/autocomplete, no checkboxes]
    +-- RagMessageBubble     [view: live answer + citations + diagnostics]
    +-- KnowledgeBase page   [composition: wires everything together]
    +-- VaultPage extraction [App.jsx refactor: clean page separation]
    +-- MUI Tabs             [navigation: vault ↔ knowledge base]
    +-- Vitest unit tests    [parser + service rules coverage]
```

---

## Progress Tracker (live state)

| # | Task | Files | Status | Documented |
|---|------|-------|--------|------------|
| 1 | SSE-Aware RAG API Client | `src/apis/ragApi.js` | Done | Section 1 |
| 2 | RAG Business Logic Service | `src/services/ragService.js` | Done | Section 2 |
| 3 | DocumentMultiSelect Component | `src/components/DocumentMultiSelect.jsx` | Done | Section 3 |
| 4 | RagMessageBubble Component | `src/components/RagMessageBubble.jsx` | Done | Section 4 |
| 5 | KnowledgeBase Page | `src/pages/KnowledgeBase.jsx` | Done | Section 5 |
| 6 | VaultPage extraction + MUI Tabs | `src/pages/VaultPage.jsx`, `src/App.jsx` | Done | Section 6 |
| 7 | Unit tests (Vitest) + stale code cleanup | `src/apis/__tests__/`, `src/services/__tests__/` | Done | Section 7 |
| 8 | Final verification (lint + test + build + dev server) | — | Done | Section 8 |

---

## 1. Step 1 — SSE-Aware RAG API Client

### How We Integrated It

**Created:** `frontend/src/apis/ragApi.js`
**Modified:** `frontend/src/apis/documentApi.js` (removed stale `queryRagPipeline`)

Phase 6 left a gap: the existing `queryRagPipeline()` in `documentApi.js` sends `POST /rag/query` but expects the response as a single JSON object (`{ answer, sources, diagnostics }`). The backend actually streams an SSE text response — `data: {"type":"token","text":"..."}\n\n` lines followed by `data: {"type":"final",...}\n\n`. `queryRagPipeline` would silently fail on a real SSE body. Step 1 closes this gap.

**What `ragApi.js` exports:**

| Export | Type | Purpose |
|--------|------|---------|
| `parseRagSse(body)` | Pure function | Takes raw SSE text, returns `{ answer, sources, diagnostics, error? }` |
| `streamRagQuery(payload, onToken, signal)` | Async function | Network call + progressive `onToken` callback driver |
| `parseSseEvents(body)` | Pure helper | Splits SSE text into an array of parsed JSON event objects |

**What was removed:**

`queryRagPipeline()` was deleted from `documentApi.js:99-112` and replaced with a comment pointing to `ragApi.js`. The function was never imported or called anywhere in the codebase — it was dead code from Phase 6's handoff that assumed the wrong response contract.

### Why Built This Way (Architectural Trade-offs)

**Trade-off 1: Fire-and-forget vs genuine incremental streaming**

The SSE client uses a fire-and-forget model: `axiosClient.post()` with `responseType: 'text'` buffers the entire SSE body, then `parseSseEvents()` iterates through all lines synchronously, calling `onToken(accumulatedAnswer)` as each token is encountered. The full answer appears in the UI only after the HTTP response is fully received and parsed.

Genuine incremental streaming (fetch + ReadableStream reader parsing chunks as they arrive from the network) would give true ChatGPT-style token-by-token rendering but adds complexity: browser ReadableStream API handling, chunk boundary splitting (an SSE `data:` line may straddle two TCP chunks), and AbortController wiring. The Phase 8 plan explicitly endorses the simpler model as an MVP. If progressive rendering is later desired, `streamRagQuery` is the single place to swap in a ReadableStream approach — the `onToken` callback contract stays identical.

**Trade-off 2: `parseRagSse` vs `parseSseEvents` separation**

The public `parseRagSse(body)` is the full answer: it iterates events and assembles `{ answer, sources, diagnostics }`. But `streamRagQuery` needs the same event-level parsing *without* the final assembly (it does the assembly itself while driving `onToken`). Rather than duplicating the line-splitting and JSON.parse logic, both functions share a common `parseSseEvents(body)` helper that does the raw SSE → event-object[] split. This keeps the parser single-source-of-truth and independently unit-testable.

**Trade-off 3: `axiosClient` response interceptor compatibility**

The `axiosClient.js` response interceptor unwraps to `response.data` directly. For `responseType: 'text'`, this means `streamRagQuery`'s `response` variable is already the raw SSE text string — no separate axios instance needed. This is confirmed by inspecting `axiosClient.js:41-43`. No override or extra `transformResponse` config was necessary.

### Data/State Flow

```
User types question, selects files, clicks Send
           |
           v
  KnowledgeBase.jsx  (Step 5)
    sends { question, file_ids }
           |
           v
  streamRagQuery(payload, onToken, signal)   <--- ragApi.js
    |  POST /rag/query   (axios, responseType: 'text', timeout: 60s)
    |  Waits for full SSE body to arrive
    v
  parseSseEvents(body)
    |  Split on \r?\n
    |  Skip non-"data: " lines (": connected\n\n" comments, blanks)
    |  JSON.parse each "data: {...}" payload
    |  Skip malformed lines (tolerant parsing)
    v
  Iterate parsed events:
    |
    +-- { type: "token", text: "..." }
    |       answer += event.text
    |       onToken(answer)  ----->  React re-renders assistant message
    |
    +-- { type: "final", sources: [...], diagnostics: {...} }
    |       sources = event.sources
    |       diagnostics = event.diagnostics
    |
    +-- { type: "error", detail: "..." }
            error = event.detail
           |
           v
  Returns { answer, sources, diagnostics, error? }
           |
           v
  KnowledgeBase.jsx updates final message in messages[] state
```

### Key Frontend/RAG Concepts Learned

**1. Axios `responseType: 'text'` + interceptor = clean SSE text**

The backend sends `Content-Type: text/event-stream`. Axios with `responseType: 'text'` will buffer the entire stream and give you a string. The `axiosClient` interceptor returns `response.data` directly, so the string lands in `streamRagQuery`'s `response` variable with no extra unwrapping needed.

**2. SSE comment lines are meaningful but ignorable**

The backend's `_event_stream()` in `rag_routes.py:45` emits a leading `: connected\n\n` — an SSE comment that flushes proxy headers immediately. The parser skips lines not starting with `data: ` by spec.

**3. `type: "error"` mid-stream events**

The backend emits `{"type":"error","detail":"Internal error during answer generation."}` if the orchestrator throws. The parser captures this as `result.error` so the UI can display a meaningful message instead of a partial/empty answer.

**4. Dead code removal prevents future confusion**

`queryRagPipeline` was defined in `documentApi.js` since Phase 6 but never called. Leaving it in place would confuse future developers into thinking it's the correct RAG client. Removing it now (with a comment pointing to `ragApi.js`) eliminates that ambiguity entirely.

---

## 2. Step 2 — RAG Business Logic Service

### How We Integrated It

**Created:** `frontend/src/services/ragService.js`

This is a pure logic layer with zero dependencies — no React, no JSX, no network calls, no MUI imports. It sits between the API client (Step 1) and the components (Steps 3–4), enforcing the selection contract that the UI obeys.

**What `ragService.js` exports:**

| Export | Type | Purpose |
|--------|------|---------|
| `MAX_SELECTED_FILES` | Constant (`5`) | Hard cap, single source of truth |
| `isIndexed(doc)` | Predicate | Returns true when `indexingStatus` or `indexing_status` is `'INDEXED'` |
| `selectableDocuments(documents)` | Filter | Returns only INDEXED docs from the full list |
| `addToSelection(selection, doc)` | State updater | Appends a doc, throws `Error` on 6th selection |
| `removeFromSelection(selection, fileId)` | State updater | Filters out by `fileId` |
| `toFileIds(selection)` | Mapper | `[...selection].map(d => d.fileId)` → `number[]` |
| `formatSelectionLabel(doc)` | Formatter | `doc.title \|\| doc.filename` |

**Backend field name discovery:** The `FileMetadataSchema` in `backend/app/schemas/file.py` uses Pydantic `alias` fields — `fileid` is aliased to `fileId`, `indexing_status` is aliased to `indexingStatus`. The frontend therefore receives camelCase keys. The `isIndexed` function handles both conventions defensively, since the `FileRow` component already checks `doc.indexingStatus \|\| doc.indexing_status`.

### Why Built This Way (Architectural Trade-offs)

**Trade-off 1: Separate service file vs hooks**

The max-5 rule and INDEXED filter are pure business logic, not React state. Placing them in a standalone service file (not a hook) means they are:
- Independently unit-testable with plain function calls (no `renderHook` or React testing library needed)
- Reusable if the selection logic is ever needed outside React (e.g., a future CLI or SSR path)
- Separated from React lifecycle concerns, keeping them easy to reason about

The KnowledgeBase page (Step 5) will call these functions from its own state management; the service itself knows nothing about `useState` or `useCallback`.

**Trade-off 2: Throw vs return error on 6th selection**

`addToSelection` throws `Error` rather than returning `{ ok: false, error }` or a sentinel. The plan (§5.3) specifies: "Attempted 6th is rejected with a snackbar/inline message." Throwing is the idiomatic JS pattern for "caller should not have reached this state" — the page catches the error and surfaces it via `Snackbar`. An `{ ok, error }` tuple would be over-engineering for a hard cap that is already guarded by the UI disabling the 6th chip.

**Trade-off 3: Immutable updates**

All functions return new arrays (`[...selection, doc]`, `selection.filter(...)`) rather than mutating in place. This is a React convention that ensures `useMemo` / `useEffect` dependency arrays see reference changes and re-render correctly. Since the service has no React dependency, immutability also makes the functions side-effect-free and trivially testable.

### Data/State Flow

```
fetchFiles() response (documents[])
          |
          v
selectableDocuments(documents)  <-- filters to INDEXED only
          |
          v
DocumentMultiSelect (Step 3)
  renders MUI Autocomplete with selectable options
  user clicks a chip
          |
          v
KnowledgeBase (Step 5) calls addToSelection(selection, doc)
  |  success: selected[] updates, Chip appears
  |  throws: caught by page, snackbar shows "max 5"
          |
          v
User types question + clicks Send
          |
          v
KnowledgeBase calls toFileIds(selected) -> number[]
  passes to streamRagQuery({ question, file_ids })
          |
          v
ragApi.js sends POST /rag/query (Step 1)
```

### Key Frontend/RAG Concepts Learned

**1. Backend alias layer means camelCase on the frontend**

FastAPI + Pydantic v2 `alias="fileId"` means the JSON response key is `fileId`, not `file_id`. The `isIndexed` check must handle both because the `FileRow` component (existing) already defensively checks `doc.indexingStatus || doc.indexing_status`. The service matches this convention.

**2. Max-5 is a backend + frontend contract**

The backend's `RAGQueryRequest` has `file_ids: Optional[list[int]]` with no explicit cap. The 5-file cap is enforced by the frontend UX (Phase 8 §5.3) to keep retrieval fast and answer quality high. The backend still validates ownership and INDEXED status via `validate_file_ids`, providing defense-in-depth if the frontend cap is bypassed.

**3. No "All documents" option by design**

The plan explicitly prohibits an "ask all documents" mode. This is because across a large corpus, top-K retrieval with score_threshold filtering may miss relevant chunks, producing low-quality answers. Scoping to 1–5 known-relevant documents keeps the retrieval focused and the answers grounded.

---

## 3. Step 3 — DocumentMultiSelect Component

### How We Integrated It

**Created:** `frontend/src/components/DocumentMultiSelect.jsx`

A purely presentational MUI picker. It receives `documents` (all), `selected` (the page's chosen docs), and `onToggle(value)` (the page's state-update callback). It internally derives the INDEXED subset and renders an `Autocomplete multiple` — MUI's checkbox-free native picker that renders each selection as a **removable chip** plus a filterable dropdown.

**Props contract:**

| Prop | Type | Description |
|------|------|-------------|
| `documents` | `Array<object>` | Full list from `fetchFiles()` |
| `selected` | `Array<object>` | Currently selected docs (owned by the page) |
| `onToggle(value)` | `(Array<object>) => void` | Called with the new selection array on every change |

**MUI primitives used:** `Box`, `Autocomplete`, `TextField`, `Typography`. No `Checkbox`, no custom CSS, no `styled-components`.

### Why Built This Way (Architectural Trade-offs)

**Trade-off 1: Autocomplete multiple vs a raw Chip row**

The Phase 8 implementation note (§3, Step 3) explicitly endorses either an `Autocomplete multiple` or a scrollable Chip row. `Autocomplete multiple` was chosen because it is:
- MUI-native, filtering built-in for large vaults (a Chip row would need custom "search" logic)
- Each selection renders as a standard removable Chip (matches "no checkboxes" requirement)
- Controllable: `value` stays bound to the page's `selected` state, so the page can reject a 6th selection and the UI remains consistent

**Trade-off 2: INDEXED filter re-implemented or delegated?**

The plan's sketch filtered inside the component via `documents.filter(...)`, but Phase 8 §5.1 and Step 2 state **"components never re-implement the rules."** So this component imports `selectableDocuments`, `formatSelectionLabel`, and `MAX_SELECTED_FILES` from `ragService` instead of hand-rolling the filter. The service remains the single source of truth; the component only composes it.

**Trade-off 3: Max-5 described but not enforced here**

The component deliberately does **not** disable the picker at 5 selections. Phase 8 §5.3 wants the 6th attempt to be *rejected with clear feedback* (a Snackbar). That rejection happens in the page's `onToggle` handler, which routes through `ragService.addToSelection` — the value array is reconstructed against the previous selection and the rule trips on the true 6th addition. `React.memo` keeps the component pure so re-renders only happen when `documents`/`selected` references change.

### Data/State Flow

```
KnowledgeBase.page  (Step 5)
  |  documents[]  (from fetchFiles)
  |  selected[]   (owned state)
  |  onToggle(value)  -> diff vs prev -> addToSelection/removeFromSelection
  |                        -> Snackbar on 6th
  v
DocumentMultiSelect  (presentational only)
  |  selectableDocumentst(documents)   <- ragService provides INDEXED filter
  |  Autocomplete multiple (chips, no checkboxes)
  |  user picks -> onChange -> onToggle(newValue)
  v
KnowledgeBase page state updates -> re-renders DocumentMultiSelect
```

### Key Frontend/RAG Concepts Learned

**1. MUI Autocomplete `multiple` is a chip factory with zero custom CSS**

Setting `multiple` makes MUI render each selected option as a removable `Chip` inside the field and provides a keyboard-searchable dropdown. `isOptionEqualToValue={(a, b) => a.fileId === b.fileId}` is required so MUI can match selected options by identity (options are object references; the page may hold different object instances for the same `fileId`).

**2. Controlled value + page-owned state = single undo point for rule violations**

Because `value` is always the page's authoritative `selected` array, an illegal 6th selection is simply never committed — the Autocomplete collapses back to its previous 5 chips while the page shows the Snackbar message.

**3. `filterSelectedOptions` UX nicety**

Setting `filterSelectedOptions` hides already-selected docs from the dropdown, so the user sees only what they can still add — a clean, MUI-native touch that needs no extra state.

---

## 4. Step 4 — RagMessageBubble Component

### How We Integrated It

**Created:** `frontend/src/components/RagMessageBubble.jsx`

A chat message bubble that renders both roles from the page's `messages` array (`{ role, text, sources?, diagnostics?, streaming?, error? }`):

| Branch | Rendered content |
|--------|------------------|
| `role: 'user'` | Right-aligned dark pill (primary `#0A192F`), question text pre-wrap |
| `role: 'assistant'` | Left-aligned white bubble, live answer text, optional streaming caret `▌` while `streaming`, collapsible citations, gated Developer diagnostics |
| `message.error` | `Alert severity="error"` (network / mid-stream failure) |
| `diagnostics.insufficient_evidence` | `Alert severity="info"` abstain message — no fabricated answer |

**Source citation shape consumed** (from the backend `RAGSourceResponse`, `schemas.py:78`):

```
{ chunk_id: string, filename: string, page_start: int, page_end: int }
```

Each source renders as an outlined `Chip` with `filename` and a computed page range (`Page 3` or `Pages 1–3`), with the `chunk_id` as a hover `Tooltip`. The citations block is wrapped in MUI `Collapse`, toggled by an `ExpandMoreIcon` rotate.

**MUI primitives used:** `Box`, `Typography`, `Collapse`, `IconButton`, `Stack`, `Chip`, `Divider`, `Alert`, `Tooltip`. No custom CSS, no styled-components.

### Why Built This Way (Architectural Trade-offs)

**Trade-off 1: Local collapse state vs lifting to the page**

Open/close for citations and diagnostics is purely view state, so `useState` lives inside the component. This keeps the page's `messages` array free of UI flags and keeps the bubble self-contained and reusable. The component remains wrapped in `React.memo`, so it only re-renders when the `message` object reference changes — which is exactly when streaming appends a new token.

**Trade-off 2: Three mutually-exclusive answer branches**

Error → abstain → normal-answer are rendered as exclusive branches (`Alert`, `Alert`, bubble). This mirrors the orchestrator's three real paths (`rag_orchestrator.py:196-256`): no hits / no budget → abstain; mid-stream exception → `{"type":"error",...}`; success → tokens + final. Rendering the abstain/error message without fabricating an answer is a direct Phase 8 §5.4 requirement.

**Trade-off 3: Diagnostics behind an expander, never alongside the answer**

`diagnostics` render only when a developer opens the labelled expander. In the normal answer flow, users see citations and nothing else — matching "diagnostics appear only inside a developer expander" (§5.4). The block is `JSON.stringify(diagnostics, null, 2)` inside an MUI `Box component="pre"`, styled monospace via theme-adjacent sx (no CSS file).

### Data/State Flow

```
KnowledgeBase.page (Step 5) holds messages[]:
  { role: 'user', text: question }
  { role: 'assistant', text: '', streaming: true, sources: [], diagnostics: {} }
        |
        v  onToken(answer) updates messages.at(-1).text  => new object ref
RagMessageBubble  (presentational)
  |  message.error            -> Alert error
  |  diagnostics.insufficient_evidence -> Alert info (abstain)
  |  else -> answer text (pre-wrap) + streaming caret ▌
  |  sources.length > 0       -> Collapsible "Sources (N)" chips
  |  diagnostics present      -> "Developer diagnostics" Collapse (gated)
  |
  v  (streaming resumes)      -> page re-renders with new message ref, bubble animates tokens
```

### Key Frontend/RAG Concepts Learned

**1. Token streaming is animation via re-render, not CSS**

The typewriter effect comes purely from the page appending tokens to the message object's `text` on each `onToken` callback and letting React re-render. The caret `▌` indicates "more coming" and disappears when `streaming` flips false after the `final` event. No timers, no CSS animations required.

**2. The ablative pipeline has a typed abstain contract**

The orchestorator has `_abstain()` (`rag_orchestrator.py:66`) which emits `sources: []` + `diagnostics.insufficient_evidence: true` with **no token events**. The frontend surfaces this as a polite "couldn't find enough evidence" note. This is safer than a hallucinated guess — grounding requires at least one retrieved chunk.

**3. Citation pagination (`page_start`/`page_end`) is user-facing, chunk_id is not**

`filename` + page range are safe, meaningful anchors for the user. `chunk_id` is an internal Qdrant identifier that is only useful to a developer — hence the Tooltip rather than visible label. Keys (S3) never enter this render path.

---

## 5. Step 5 — KnowledgeBase Page

### How We Integrated It

**Created:** `frontend/src/pages/KnowledgeBase.jsx`

The composition root. The page owns all conversation state and wires the layers together — it contains **no** business-rule re-implementations and **no** raw MUI layout for picker/bubble internals (those live in the components). It orchestrates:

| Concern | Source of truth |
|---------|-----------------|
| Document list loading | `fetchFiles()` (paginated loop, page size 200 — backend max) |
| Selection rules (max-5, INDEXED) | `ragService.addToSelection` |
| `file_ids` mapping | `ragService.toFileIds` |
| SSE stream consumption | `streamRagQuery()` + `onToken` callback |
| Conversation state | page-local `useState` (`messages`, `selected`, `question`, `sending`) |

**Layout (MUI `Stack`/`Box`/`Paper`):**

```
Typography "Knowledge Base" (title + subtitle)
  [ Paper: DocumentMultiSelect ]
  [ Paper: chat thread — RagMessageBubble list, auto-scroll ]
  [ Paper: TextField (multiline) + Send IconButton ]
  [ Snackbar: max-5 errors / request errors ]
```

**Send flow:** Enter to send (Shift+Enter newline), button disabled unless a doc is selected, a question is typed, and not already sending.

### Why Built This Way (Architectural Trade-offs)

**Trade-off 1: Page fetches its own documents on mount**

The plan's Step 6 uses conditional render for the Tabs, so the Knowledge Base **unmounts** when hidden and remounts when opened — reloading its document list fresh each entry, so newly-indexed documents appear without a manual refresh. A focused `ragService` loader could wrap this, but fetchFiles is already the vault's API; a pagination loop (Page 200 items, backend `le=200` cap per `document_routes.py:209`) guarantees all INDEXED docs reach the picker without unbounded single requests.

**Trade-off 2: State-update orchestration for the streaming message**

Messages are `{ role, text, sources?, diagnostics?, streaming?, error? }`. On send, the page appends the user message + an assistant placeholder (`streaming: true`) via one `setMessages`. The `onToken` callback targets **any** message still flagged `streaming` — so the placeholder updates as tokens arrive. The final `setMessages` uses the captured `asstIndex` to attach `sources`, `diagnostics`, drop `streaming`, and (on a mid-stream `error` event) the `error` field. The `messagesRef` keeps a safe index baseline because React state updates are asynchronous.

**Trade-off 3: Errors surfaced per-message AND via Snackbar**

A failed request marks the assistant bubble with an error `Alert` (so the user sees which question failed) *and* pops a Snackbar for a summary. Aborts (`CanceledError`) are silently swallowed because the page will be remounted/unmounted on tab switch; there is no state to update.

**Trade-off 4: `insufficient_evidence` is data, not an error**

An abstain final event resolves the promise normally with `sources: []` and empty `answer`. The page stores it as a normal message; the bubble renders the abstain `Alert` (Step 4). It is never treated as an exception.

### Data/State Flow

```
Mount (Tabs selected)
  |
  v
fetchFiles(200, 0) -> pages loop until total          -> documents[]
  |
  v
DocumentMultiSelect (INDEXED subset, chips, no checkboxes)
  |  user picks/deselects
  v
handleDocumentToggle(value):
  diff vs selected -> addToSelection (throws on 6th -> Snackbar)
                    -> removeFromSelection
  -> setSelected(newSelection)
  |
  v
User types question, presses Enter / Send
  |
  v
handleSend():
  messages += [user, assistant{streaming:true, text:''}]
  streamRagQuery({ question, file_ids: toFileIds(selected) }, onToken)
    |  token events -> onToken(acc) -> texts set on streaming message
    |  final event  -> resolve { answer, sources, diagnostics }
    |  error event  -> result.error -> message.error + Snackbar
  |
  v
Final message update -> RagMessageBubble renders answer + citations + diagnostics
```

### Key Frontend/RAG Concepts Learned

**1. `onToken` must land on the *in-progress* message only**

Token callbacks arrive while React may have batched earlier updates. Targeting "any message with `streaming === true`" is robust against index drift and queued state updates; the final event then pins all fields by exact index.

**2. `file_ids` is the only tenant-safe identifier the client sends**

`toFileIds(selected)` produces `number[]` from the user's own list. Ownership + INDEXED status are re-validated server-side (`validate_file_ids`, 400 on violation). No S3 key, vector, or foreign id ever leaves the browser in the RAG payload — Phase 8 §5.6.

**3. AbortController gives free unmount safety**

The fetch loop, per-query stream, and cleanup all share `AbortController` signals. When the Tabs unmount the page mid-stream, axios rejects with `CanceledError` and the page quietly returns — no orphaned state updates, no snackbars during navigation.

---

## 6. Step 6 — VaultPage Extraction + MUI Tabs

### How We Integrated It

**Created:** `frontend/src/pages/VaultPage.jsx`
**Rewritten:** `frontend/src/App.jsx`

Before Phase 8, `App.jsx` was a 660-line monolith holding *everything*: auth gate, backend ping, upload, search, pagination, metadata edit, delete, alerts, dialogs, theme, and footer. Phase 8 §3 Step 6 splits it into layers so the vault and the Knowledge Base are sibling pages.

**New `App.jsx` responsibilities (composition root only):**

```
App.jsx
 |-- session state (token / currentUser) + auth gate
 |-- backendStatus ping (feeds Header dot)
 |-- MUI Tabs:  <Tab label="Vault" value="vault" />
 |--            <Tab label="Knowledge Base" value="knowledge" />
 |-- conditional render:  view === 'vault' ? <VaultPage/> : <KnowledgeBase/>
 |-- theme (unchanged) + Header + Footer
```

**New `VaultPage.jsx` responsibilities (everything that moved):**

| Moved from App.jsx | Into VaultPage.jsx |
|--------------------|--------------------|
| Upload / verify / progress state + `handleUpload` | `SearchHeader` + XHR S3 upload |
| Search state + `executeSearch`, debounce effect | keyword/vector search + fallback alert |
| Pagination state + `handlePageChange` / `handleRowsPerPageChange` | `FileList` + `TablePagination` |
| Metadata edit modal state + handlers | `EditMetadataDialog` |
| Delete confirm modal state + handlers | `DeleteConfirmDialog` |
| Error/success alert banners + view-file action | Alerts at top of the page |

### Why Built This Way (Architectural Trade-offs)

**Trade-off 1: MUI Tabs, not React Router**

The project has no router dependency, and Phase 8 §3 Step 6 explicitly says no new router library is required. MUI `Tabs` with **conditional render** (not `keepMounted`) unmounts the hidden page, so `KnowledgeBase` re-runs its mount effect (fetch documents) and `VaultPage` re-fetches its list each time the tab is opened. Newly-indexed documents therefore appear in the picker without a manual refresh.

**Trade-off 2: Side-effect cleanup — the `set-state-in-effect` fix**

Moving the vault logic surfaced a pre-existing React-hooks lint error: the old `App.jsx:233` called `executeSearch` synchronously inside an effect triggered by `[page, rowsPerPage]`. Rather than suppressing it, the search re-execution moved **into** `handlePageChange` / `handleRowsPerPageChange` (event handlers): when a search is active, pagination re-runs `executeSearch(searchTerm, newPage, rowsPerPage)`, otherwise it reloads the list. This removes the effect entirely (and its `isNavMountRef` skip-first-run guard), making the code both lint-clean and easier to reason about.

**Trade-off 3: `value`-keyed Tabs vs index-keyed**

The new `Tabs` use explicit `value="vault"` / `value="knowledge"` on the `Tab` components and a matching `value` on `Tabs`. String keys read better than `0/1` indexes and keep the conditional render (`view === 'vault'`) and the state in lock-step.

**Trade-off 4: Header/Footer/theme stay top-level**

`Header`, `Footer`, and `createTheme` remain in `App.jsx` because they frame every view (auth + both tabs). The backend-status ping also stays top-level so the Header dot is correct regardless of which tab is open. Neither page needs access to them.

### Data/State Flow

```
App.jsx
  |  token / currentUser / backendStatus / view
  |  view = 'vault' | 'knowledge'
  v
MUI Tabs (Vault | Knowledge Base)
  |
  +-- view === 'vault'    -> <VaultPage/> (mounted)
  |       mount -> loadDocuments() -> Fetch list from GET /files
  |       user can upload / search / edit / delete (all page-local state)
  +-- view === 'knowledge' -> <KnowledgeBase/> (mounted)
          mount -> fetchFiles loop -> documents[]
          user picks docs -> asks question -> streamRagQuery (Steps 1-5)
  |
  v
Hidden page is unmounted => state resets on switch => fresh data each entry
```

### Key Frontend/RAG Concepts Learned

**1. Unmount-on-hide is a deliberate refresh mechanism**

Conditional render gives "reload on tab entry" for free. This is exactly what Phase 8 needs (fresh INDEXED document list) and what any pull-to-refresh UX would re-implement with extra code. The trade-off is scroll position / conversation state is lost on tab switch — acceptable for this scope, and conversations persist only while the page is mounted.

**2. Event handlers beat effects for "respond to a change" logic**

The old pagination effect existed only to re-run a search when `page` changed. Moving that decision into the click/change handler removes a render cycle, avoids cascading setState-in-effect lint failures, and makes the trigger explicit at the call site. This is the rule the React docs now push: *effects synchronize with external systems; user-event responses belong in handlers.*

**3. Component/page boundary that emerged**

`App.jsx` is now ~190 lines and purely structural — it doesn't know how uploads or file lists work. Any future page (settings, analytics) is one `Tab` + conditional render away. The layout seams (`pages/`, `components/`, `apis/`, `services/`) line up exactly with Phase 8 §5.1.

### Build Verification

`npm run build` succeeds. One icon-name fix was required: MUI icons v9 renamed `ChatBubbleOutline` → `ChatBubbleOutlineOutlined` (the plain name no longer exists in `@mui/icons-material@9.3.1`); `RagMessageBubble.jsx` imports the correct named export. The sole remaining build warning (`chunk > 500 kB`) is pre-existing — all of MUI bundles into one chunk before Phase 8.

---

## 7. Step 7 — Unit Tests + Test Infrastructure

### How We Integrated It

**Installed:** `vitest` (dev dependency `^5.0.0`)
**Modified:** `frontend/package.json` — added `"test": "vitest run"` script
**Created:**
- `frontend/src/apis/__tests__/ragApi.test.js` (SSE parser, Phase 8 §8.2)
- `frontend/src/services/__tests__/ragService.test.js` (selection rules, Phase 8 §8.1)

```
12 tests  |  ragApi.test.js
15 tests  |  ragService.test.js
------------------------
27 passed , 2 files   (vitest run)
```

**Why Vitest:** Vite is already the build tool, so Vitest reuses the same Vite config/transform pipeline with near-zero setup — no separate Jest/Babel/MockDOM config, no ts-jest, no test-env.js brain. Pure-function tests (no DOM, no React) need no `jsdom` environment at all, keeping the run fast (~2.3s) and dependency-light.

### Test coverage mapped to the plan

**`ragApi.test.js` (parseRagSse / parseSseEvents):**

| Plan requirement (§8.2) | Test |
|--------------------------|------|
| token-only body accumulates full answer | accumulates "The answer is grounded." |
| token + final populates sources + diagnostics | enriches all three return fields |
| comments like `: connected` are ignored | interspersed-comment test |
| malformed line skipped without throwing | `not-json` between tokens doesn't throw/lose |
| `final` with empty sources yields `[]` | empty-sources abstain final event |
| *extension:* mid-stream `type:"error"` captured | returns `result.error` |
| *extension:* CRLF + empty-body tolerance | line-ending + empty input handling |

**`ragService.test.js` (selection rules, §8.1):**

| Rule | Test |
|------|------|
| `isIndexed` true/false across casing | uppercase, lowercase, snake_case field, PENDING/FAILED/missing |
| `addToSelection` adds unique, rejects 6th (throws), unchanged for dupes | append, same-ref-on-duplicate, throws at 6th, allows exactly 5 |
| `removeFromSelection` removes by fileId | removes + keeps order; no-op on absent id |
| `toFileIds` maps to numbers | `[7,42]`; empty for no selection |
| `selectableDocuments` filters non-INDEXED | filters mixed list; empty when none / on `[]` |
| `formatSelectionLabel` title-preferred | title over filename; filename fallback |

### Why Built This Way (Architectural Trade-offs)

**Trade-off 1: Pure functions need no DOM — keep them free of it**

`parseRagSse`, `parseSseEvents`, and every `ragService` export are pure JS. Placing their tests as sibling `__tests__/*.test.js` mirrors the existing `apis` / `services` folder layout, and Vitest runs them in Node with zero browser/JSDOM dependency. This is why Steps 1–2 were built as frameworks-agnostic functions: they are trivial to test without React test-utils.

**Trade-off 2: Nested `describe`/`it` organized by contract, not file**

Each top-level `describe` maps to one public function (`isIndexed`, `addToSelection`, …). This makes a failing test's intent obvious and keeps the suite a near-prose spec of Phase 8's rules — a readable contract document that also executes.

**Trade-off 3: `test` script scoped to `vitest run`**

`vitest run` (single-pass, no watch) is the CI-friendly default for `npm test`. Interactive watch mode is still available via `npx vitest` if a developer wants it during development. Test files under `src/**/__tests__/` are auto-discovered; none are type definitions so the Vite build ignores them.

### Data/State Flow (test perspective)

```
npm test -> vitest run
        -> discovers src/**/__tests__/*.test.js
        -> ragApi.test.js: feed raw SSE bodies -> assert { answer, sources, diagnostics, error? }
        -> ragService.test.js: build selection -> assert add/remove/cap/mapping
```

### Key Frontend/RAG Concepts Learned

**1. Parsing SSE text is deterministic — the ideal unit target**

Because the backend contract is line-based (`data: {...}\n\n`), every parse outcome is a pure function of the input string. Encoding the exact backend framing (`: connected`, CRLF, `{"type":"error"}`) in tests locks the frontend to the real Phase 6 contract without needing a live backend or network mock.

**2. The max-5 / INDEXED rules are the enforceable UX contract**

Testing `addToSelection` throwing at the 6th and `isIndexed` returning false for `PENDING` makes regressions impossible to reintroduce silently. These now serve as the frontend's source of truth that mirrors the backend's `validate_file_ids` ownership checks — each layer proves its own guarantee.

**3. Vitest + Vite = zero-config modern unit testing**

For a Vite project, Vitest removes the historical friction of Jest+Babel. The full Phase 8 unit suite (27 tests across parser + service) runs in ~2.3s with no `jsdom`/`happy-dom`, no mocks, and no setup file — evidence that keeping logic in pure non-UI functions pays off directly in test simplicity.

### Verification

```
npm test   -> 27 passed (2 files, ~2.3s)
npx eslint src --fix scope -> Phase 8 files clean; test files clean
npm run build -> succeeds (only pre-existing chunk-size warning)
```

---

## 8. Step 8 — Final Verification & Phase 8 Wrap-up

### Full gate

The entire Phase 8 gate ran from a clean working tree after Step 7:

```
npx eslint src/ <7 Phase 8 modules>   -> LINT_PASS (0 errors, 0 warnings)
npm test                              -> 2 files, 27 tests, all passed (775 ms)
npm run build                         -> vite build success (993 modules, 640.96 kB / gzip 201.09 kB)
npm run dev                           -> VITE ready in ~426 ms; HTTP GET / -> 200
```

| Check | Result | Meaning |
|-------|--------|---------|
| Lint | ✅ 0 errors | Hooks rules (incl. the extracted setState-in-effect fix) hold |
| Unit tests | ✅ 27/27 | Parser + selection contracts identical to Step 7 |
| Production build | ✅ | Bundles cleanly; only the **pre-existing** chunk-size warning |
| Dev server | ✅ HTTP 200 | Serves `index.html`; Vite re-optimized deps after Vitest install |

The chunk-size warning is unchanged from before Phase 8 — a single 641 kB module that is essentially all of MUI; it is out of scope and existed at the start of this phase.

### Stale-code cleanup performed

| Location | Change |
|----------|--------|
| `frontend/src/apis/documentApi.js` | removed dead `queryRagPipeline` (pre-SSE REST stub) — superseded by `ragApi.streamRagQuery` |
| `frontend/src/App.jsx` | vault state/handlers moved to `pages/VaultPage.jsx`; deletion of `isNavMountRef` skip-first-run hack |
| Replaced effect 2 (pagination re-search) | now in `handlePageChange` / `handleRowsPerPageChange` event handlers |
| Pre-existing lint errors in `Header.jsx`, `AuthPage.jsx`, `EditMetadataDialog.jsx`, `DeleteConfirmDialog.jsx` | left untouched (out of Phase 8 scope) |

### What Phase 8 shipped (recap)

1. **`src/apis/ragApi.js`** — `streamRagQuery` (fire-and-forget POST + buffer) and pure `parseRagSse` / `parseSseEvents` implementing the exact Step 6 SSE framing on the wire: `: connected`, `data:` objects, CRLF tolerance, malformed-line skip, `type:"error"` capture.
2. **`src/services/ragService.js`** — hard UI rules: `MAX_SELECTED_FILES = 5`, `isIndexed` (casing + `indexing_status` tolerant), `selectableDocuments`, `addToSelection` (caps + throws at 6th), `removeFromSelection`, `toFileIds`, `formatSelectionLabel`.
3. **`src/components/DocumentMultiSelect.jsx`** — MUI Autocomplete `multiple` chips (no checkboxes) restricted to INDEXED docs; renders inline chip for the sole backend-story detail.
4. **`src/components/RagMessageBubble.jsx`** — user/assistant bubbles, streaming caret preview, collapsible citation chips, gated diagnostics, abstain/error alerts.
5. **`src/pages/KnowledgeBase.jsx`** — composition root: paginated doc loading, selection, send→`streamRagQuery`, auto-scroll, Snackbar errors, claim-before-load guard.
6. **`src/pages/VaultPage.jsx` + `src/App.jsx`** — clean page split with MUI `Tabs`; conditional render so hidden pages unmount and re-fetch on tab entry.
7. **`frontend/package.json`** — `vitest ^5.0.0` devDep + `npm test` script.
8. **Unit tests** — 27 tests pinning §8.1 selection rules and §8.2 SSE parse contract.

### Final architecture at a glance

```
App.jsx (Tabs: vault | knowledge)
 ├── VaultPage            upload / search / paginate / edit / delete  (unchanged behavior)
 └── KnowledgeBasePage
      ├── fetchFiles paging loop  ->  selectableDocuments(INDEXED filter)
      ├── DocumentMultiSelect     (chips picker, ≤5)
      └── send(question) -> streamRagQuery -> onToken/onFinal/onError
             └── RagMessageBubble (answer + citations + diagnostics)
Tests: vitest run
  ├── ragApi.test.js    — parse tuple { answer, sources, diagnostics, error }
  └── ragService.test.js— selection rules (max-5, INDEXED, file_id mapping)
```

Phase 8 is complete. The web UI now ships a functional RAG chat surface that is testable, lint-clean, network/logic/view-decoupled, and fully aligned with the Phase 6 SSE contract.
