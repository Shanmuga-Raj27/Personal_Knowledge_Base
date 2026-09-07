# RAG Phase 8 - React Knowledge Base Chat Integration

## 1. Phase Goal

Phases 1-6 built the complete RAG engine and exposed it through a thin, authenticated FastAPI surface (`POST /rag/query` SSE, `POST /documents`, status, and chunk endpoints). Phase 7 owned testing and metrics. **Phase 8 is a pure frontend phase**: it integrates RAG into the existing **React + Material UI** frontend as a dedicated **"Knowledge Base"** chat page.

The user selects which of their already-indexed documents to ask about (by friendly name — never an S3 key), sends a question, and watches a grounded answer **stream in live** with verifiable citations.

The central architecture rules for Phase 8:

```text
RAG is a client of the backend — no client ever talks to MySQL/Qdrant/Redis/B2/Gemini.
The wire contract is SSE (token + final events) from POST /rag/query.
UI is 100% Material UI — no custom CSS, no third-party styling.
Layers stay separate: apis (network) / services (logic) / components (view) / pages (composition).
Users select documents by title/filename -> file_id; S3 keys are never shown.
```

By the end of Phase 8, the frontend should be able to:

- navigate to a dedicated "Knowledge Base" page alongside the existing document vault
- load the authenticated user's `INDEXED` documents and present them for selection by friendly name
- let the user select **up to 5 documents** (chips, no checkboxes) for a conversation; there is **no "ask all documents"** option
- send a question and consume the `POST /rag/query` SSE stream, rendering answer tokens live
- render each answer's `sources` as collapsible citations (filename + page range) and its `diagnostics` behind a development expander only
- keep `indexingStatus !== 'INDEXED'` documents from being selectable, with clear feedback
- keep API calls, business logic, and UI components in separate layers

Phase 8 does **not** add:

```text
Backend endpoints, schemas, or services                 - Phases 5/6
Streamlit playground                                    - Phase 6
Testing / metrics / security hardening / rollout        - Phase 7
New styling dependencies or custom CSS                  - prohibited by design
Upload / status / chunk inspection UI changes           - out of scope (existing vault keeps them)
```

## 2. Phase 6/7 Status Check

Before writing this plan, the current frontend and backend state was checked.

### Backend (ready, no changes needed)

```text
backend/app/services/rag/rag_orchestrator.py
|-- run_rag_query(RAGRequest, db) -> AsyncIterator[dict]  (SSE event dicts)

backend/app/apis/routes/rag_routes.py            (Phase 6)
|-- POST /rag/query  -> SSE stream:
        data: {"type": "token", "text": "..."}\n\n
        data: {"type": "final", "sources": [...], "diagnostics": {...}}\n\n

backend/app/services/rag/query_utils.py
|-- validate_file_ids(user_id, file_ids, db)  - rejects non-owned / non-INDEXED files (400)
```

The backend contract is stable. Phase 8 makes **no backend edits**.

### Frontend (current state)

```text
frontend/src/apis/
|-- axiosClient.js        - configured axios instance with auth interceptor
|-- documentApi.js        - fetchFiles(), getUploadUrl(), completeUpload(), etc.
|-- documentApi.js        - queryRagPipeline()  <-- STALE: expects plain JSON { answer, sources, diagnostics }
|-- search_routes-equivalents are backend; frontend uses documentApi.searchDocuments()

frontend/src/services/
|-- authService.js        - token storage / decode / isAuthenticated

frontend/src/components/
|-- Header.jsx, SearchHeader.jsx, FileList.jsx, FileRow.jsx, dialogs...

frontend/src/pages/
|-- AuthPage.jsx          - login view

frontend/src/App.jsx       - single view: Header + SearchHeader + FileList (NO router/tabs yet)
```

Key finding: `queryRagPipeline()` in `documentApi.js` sends `POST /rag/query` but parses `response.data` as a single JSON object. Because the endpoint streams SSE, this **does not work** and must be replaced by an SSE-aware client in Phase 8 (Phase 6's handoff note flags exactly this). The picker can reuse the existing `fetchFiles()` response, whose items already carry `fileId`, `filename`, `title`, `tags`, `indexingStatus`, and `status` — enough to drive selection without any S3 key.

So Phase 8 can assume these are available:

- `fetchFiles()` returns the user's documents, each with `fileId`, `filename`, `title`, `indexingStatus`, `status`
- a configured `axiosClient` with the bearer-token interceptor already in place
- the existing `createTheme` design system (Outfit font, `#0A192F` primary, MUI `sx` prop) to match
- `POST /rag/query` streaming SSE with the `token`/`final` event contract

## 3. What Phase 8 Adds

```text
+-------------------------------+----------------------------------------------+
| Area                          | Phase 8 work                                 |
+-------------------------------+----------------------------------------------+
| SSE RAG API client            | ragApi.js: streamRagQuery() parses SSE         |
| RAG business logic            | ragService.js: indexed docs, max-5 selection,  |
|                               |   file_id mapping, stream orchestration        |
| DocumentMultiSelect component | MUI chips (no checkboxes), max 5, INDEXED only |
| RagMessageBubble component    | Live token text + collapsible citations        |
| KnowledgeBase page            | Composes selector + chat thread + input        |
| App navigation                | MUI Tabs between vault and Knowledge Base      |
| SSE parser unit test          | Pure parser test for token/final framing       |
+-------------------------------+----------------------------------------------+
```

## 4. Existing Project Context

Relevant current files Phase 8 builds on:

```text
frontend/src/apis/axiosClient.js   - auth interceptor; base URL already configured
frontend/src/apis/documentApi.js   - fetchFiles(limit, offset) -> items with fileId/filename/title/indexingStatus
frontend/src/apis/documentApi.js   - queryRagPipeline()  (REPLACE with SSE client; do not reuse)
frontend/src/services/authService.js - isAuthenticated(), getToken()
frontend/src/App.jsx               - single-view app; add MUI Tabs to switch views
```

Backend endpoints Phase 8 consumes:

```text
GET  /files            -> the user's documents (for the selector)
POST /rag/query        -> SSE answer stream (token + final events)
```

## 5. Design Principles

### 5.1 Network, Logic, and View Stay Separate

- `src/apis/ragApi.js` — **only** HTTP + SSE framing parsing. No React, no state.
- `src/services/ragService.js` — **only** business/state logic (which docs are selectable, the max-5 rule, mapping selections to `file_ids`, orchestrating a stream into an answer object). No JSX.
- `src/components/` — **only** presentational MUI components.
- `src/pages/KnowledgeBase.jsx` — composes components + service, holds conversation state.

This mirrors the existing `apis` / `services` split already used for auth and documents.

### 5.2 SSE Is a Stream, Not a JSON Body

`streamRagQuery()` must:

- call `axiosClient.post('/rag/query', body, { responseType: 'text' })`
- read the body as a stream of lines
- keep only lines that start with `data: `
- strip the `data: ` prefix and `JSON.parse` each payload
- forward `{"type":"token","text":...}` events to a live-updating callback
- resolve the outer promise on `{"type":"final", ...}` with `{ answer, sources, diagnostics }`
- abort/error cleanly if the request fails or disconnects

### 5.3 Selection: Maximum 5, INDEXED Only, No Checkboxes

- Populate the picker from `fetchFiles()` filtered to `indexingStatus === 'INDEXED'`.
- Selection is by friendly **title or filename**; the mapping to `file_id` happens in the service, invisible to the user.
- **Exactly one interaction model:** clicking a document's MUI `Chip` toggles it selected/deselected (selected chips render filled). **No MUI Checkbox, no CheckboxList.**
- Enforce a hard **max of 5** selected files per conversation. Attempting a 6th is rejected with a snackbar/inline message and the chip does not select.
- **No "All documents" option.** The user must pick at least one file; the send button is disabled until `file_ids.length >= 1` and a question is typed.

### 5.4 Live Streaming Feedback

Answer tokens render progressively as they arrive (a `typewriter`-style caret is optional). The `final` event's `sources` render as collapsible citations and `diagnostics` appear only inside a developer expander. This mirrors the Phase 6 SSE contract exactly and gives the ChatGPT-like UX.

### 5.5 Material UI Only

Every visual element is a Material UI component styled through the `sx` prop and the existing theme tokens. No CSS files, no styled-components, no Tailwind. If MUI lacks a primitive, compose MUI primitives — do not hand-roll CSS.

### 5.6 Tenant Isolation Is Preserved by the Backend

The client sends only `file_ids` (numbers) drawn from the user's own list. The backend re-validates ownership + `INDEXED` status via `validate_file_ids` and rejects any foreign file with 400. The client does not need (and must not attempt) its own authorization.

## 6. Implementation Steps

### Step 1 - SSE-Aware RAG API Client

Create:

```text
frontend/src/apis/ragApi.js
```

Expose a single function. Keep it pure network + parsing (no React state):

```js
import axiosClient from './axiosClient'

/**
 * Stream a RAG answer from POST /rag/query over SSE.
 * @param {{ question: string, file_ids: number[], top_k?: number, score_threshold?: number }} payload
 * @param {(text: string) => void} onToken  Called with each accumulated token text (or each raw token).
 * @param {AbortSignal} [signal]
 * @returns {Promise<{ answer: string, sources: Array<object>, diagnostics: object }>}
 */
export async function streamRagQuery(payload, onToken, signal) {
  const response = await axiosClient.post('/rag/query', payload, {
    responseType: 'text',
    timeout: 60000,
    signal,
  })

  // response.data is the raw SSE body (one or more lines).
  // Parse every line, keep only "data: {...}".
  const lines = String(response.data).split(/\r?\n/)
  let answer = ''
  let sources = []
  let diagnostics = {}

  for (const line of lines) {
    if (!line.startsWith('data: ')) continue
    const payloadJson = line.slice('data: '.length).trim()
    if (!payloadJson) continue
    const event = JSON.parse(payloadJson)
    if (event.type === 'token') {
      answer += event.text
      onToken(answer)
    } else if (event.type === 'final') {
      sources = event.sources || []
      diagnostics = event.diagnostics || {}
    }
  }

  return { answer, sources, diagnostics }
}
```

> **Implementation note:** if the axios setup buffers the whole body (as above), this is a **fire-and-forget** model — `onToken(answer)` updates the UI as each line is parsed, which still renders tokens progressively once the call resolves. For genuine incremental network streaming, use `axios` with `AdapterFn`/`fetch` + a `ReadableStream` reader; the loop above over the assembled body is the simplest correct MVP and matches how the Streamlit playground reads lines. Keep the parser as a separate pure function so it is unit-testable (see Step 5).

Refactor for testability — keep the pure parser reusable:

```js
export function parseRagSse(body) {
  // returns { answer, sources, diagnostics } from raw SSE text
}
```

Then `streamRagQuery` becomes `parseRagSse(response.data)` plus the `onToken` callback driver. The pure `parseRagSse` is what Step 5 unit-tests.

**Also:** remove or stop calling the stale `queryRagPipeline()` in `documentApi.js` (it assumes the wrong contract). Reference the replacement from `ragApi.js`.

### Step 2 - RAG Business Logic Service

Create:

```text
frontend/src/services/ragService.js
```

Responsibilities (no JSX, no network calls inside components):

```js
export const MAX_SELECTED_FILES = 5

export const isIndexed = (doc) => (doc.indexingStatus || '').toUpperCase() === 'INDEXED'

export const selectableDocuments = (documents) => documents.filter(isIndexed)

export const addToSelection = (selection, doc) => {
  if (selection.some((d) => d.fileId === doc.fileId)) return selection          // already selected
  if (selection.length >= MAX_SELECTED_FILES) {
    throw new Error(`You can select at most ${MAX_SELECTED_FILES} documents per conversation.`)
  }
  return [...selection, doc]
}

export const removeFromSelection = (selection, fileId) =>
  selection.filter((d) => d.fileId !== fileId)

export const toFileIds = (selection) => selection.map((d) => d.fileId)

export const formatSelectionLabel = (doc) => doc.title || doc.filename
```

All the max-5 and INDEXED rules live here (single source of truth, easily unit-tested). The page calls these; components never re-implement the rules.

### Step 3 - DocumentMultiSelect Component

Create:

```text
frontend/src/components/DocumentMultiSelect.jsx
```

MUI-only. No checkboxes. Toggle by clicking a `Chip`.

```jsx
import React, { useState, useEffect, useMemo } from 'react'
import {
  Box, Chip, Typography, Autocomplete, TextField, Alert, Snackbar
} from '@mui/material'

function DocumentMultiSelect({
  documents,
  selected,
  onToggle,
  onError
}) {
  const selectable = useMemo(
    () => documents.filter((d) => (d.indexingStatus || '').toUpperCase() === 'INDEXED'),
    [documents],
  )

  // MUI Autocomplete bound to the selectable list; selected docs are shown as chips.
  // Toggling happens in the page via onToggle; this component is purely presentational.

  return (
    <Box>
      <Typography variant="overline" color="text.secondary">
        Select documents to ask about (up to 5)
      </Typography>
      <Autocomplete
        multiple
        size="small"
        options={selectable}
        value={selected}
        getOptionLabel={(doc) => doc.title || doc.filename}
        isOptionEqualToValue={(a, b) => a.fileId === b.fileId}
        onChange={(_e, value) => onToggle(value)}
        renderInput={(params) => (
          <TextField {...params} placeholder="Pick documents..." />
        )}
      />
      <Box sx={{ mt: 1, display: 'flex', flexWrap: 'wrap', gap: 0.5 }}>
        {selected.map((doc) => (
          <Chip
            key={doc.fileId}
            label={doc.title || doc.filename}
            color="primary"
            onDelete={() => onToggle(selected.filter((d) => d.fileId !== doc.fileId))}
          />
        ))}
      </Box>
    </Box>
  )
}

export default React.memo(DocumentMultiSelect)
```

> **Implementation note.** MUI `Autocomplete multiple` renders each selection as a removable chip and provides a dropdown — a checkbox-free, MUI-native picker. If autocomplete interaction feels heavy, an alternative is a scrollable row of toggle `Chip`s where `onClick` calls `onToggle`. Whichever is chosen, enforce the **max-5** rule in `ragService.addToSelection` and surface the violation via `onError` (Snackbar/Alert). Do **not** use `Checkbox`.

### Step 4 - RagMessageBubble Component

Create:

```text
frontend/src/components/RagMessageBubble.jsx
```

Render one chat message: the user question and the assistant answer. Answer shows:

- the accumulated answer text (live as tokens stream) — render with `Typography` using `whiteSpace: 'pre-wrap'`
- a **collapsible sources** section (MUI `Box`/`ExpandMore` + `Collapse`) listing each source's `filename` and `pages` (from `sources`)
- a **diagnostics** section gated behind an expander, labelled "Developer diagnostics", never shown in the normal answer flow
- an optional streaming caret (`▌`) while streaming

MUI primitives only: `Box`, `Typography`, `Collapse`, `IconButton`, `Stack`, `Chip`, `Divider`.

### Step 5 - KnowledgeBase Page

Create:

```text
frontend/src/pages/KnowledgeBase.jsx
```

Compose the pieces and hold conversation state:

- `documents` loaded once via `fetchFiles()` (or a focused `ragService` loader)
- `selected` list (max 5), managed through `ragService.addToSelection` / `removeFromSelection`
- `messages` array of `{ role: 'user'|'assistant', text, sources?, diagnostics?, streaming? }`
- `question` input state (MUI `TextField`), `sending` flag
- a **send handler** that calls `streamRagQuery` with `{ question, file_ids: toFileIds(selected), top_k, score_threshold }` and `onToken` updating the in-progress assistant message
- a **snackbar** for the max-5 error and any request errors
- the send button is disabled unless `question.trim()` and `selected.length >= 1` and `!sending`

Layout (MUI `Stack`/`Box`):

```text
Title: "Knowledge Base"
[ DocumentMultiSelect ]
[ Chat thread of RagMessageBubble ]
[ TextField (question)  +  Send button ]
```

### Step 6 - App Navigation (MUI Tabs)

Edit:

```text
frontend/src/App.jsx
```

Replace the flat single-view render with a small MUI `Tabs` view switch between **"Vault"** (the existing `SearchHeader` + `FileList`) and **"Knowledge Base"** (the new page). Keep the existing authenticated layout (Header + Container + Footer) and the same theme. Example:

```jsx
<Box sx={{ borderBottom: 1, borderColor: 'divider', mb: 2 }}>
  <Tabs value={view} onChange={(_e, v) => setView(v)}>
    <Tab label="Vault" />
    <Tab label="Knowledge Base" />
  </Tabs>
</Box>
{view === 'vault' ? (/* existing vault content */) : (<KnowledgeBase />)}
```

Use MUI `Tabs`/`Tab` (already part of the dependency set); no new router library is required for an individual project. Unmount the hidden view (conditional render) so the Knowledge Base reloads its document list on entry.

### Step 7 - SSE Parser Unit Test

Create:

```text
frontend/src/apis/__tests__/ragApi.test.js  (or wherever the project keeps tests)
```

Unit-test the pure `parseRagSse`:

- token-only body accumulates the full answer
- token + final populates `sources` and `diagnostics`
- non-`data:` lines (comments like `: connected`) are ignored
- `final` with empty `sources` yields `[]`
- malformed line is skipped without throwing

## 7. Error Handling Plan

```text
+--------------------------------+------------------------------------------------+---------+
| Condition                      | Handling                                       | Layer   |
+--------------------------------+------------------------------------------------+---------+
| 6th file selected              | addToSelection throws; snackbar "max 5"        | service |
| Document not INDEXED           | excluded from selectable list / disabled chip  | service |
| No file selected + asks        | send disabled until >=1 selected               | page    |
| Empty question                 | send disabled until question trimmed non-empty | page    |
| POST /rag/query 400            | backend auth/ownership reject; show detail     | api->UI |
| POST /rag/query 401            | axios interceptor (existing) -> login redirect | api     |
| SSE stream breaks mid-answer   | resolve with partial answer + error note       | api->UI |
| Gemini abstain (no evidence)   | final event has insufficient_evidence: true    | passthrough |
| Abort (user navigates)         | AbortController cancels; no state update       | api     |
+--------------------------------+------------------------------------------------+---------+
```

Guidelines:

- Never show S3 keys, vectors, or raw service errors to the user.
- Keep `top_k`/`score_threshold` at the backend defaults (6 / 0.35) unless a settings affordance is requested.
- On `insufficient_evidence`, the bubble shows the abstain message from the final event's diagnostics with no fabricated answer.

## 8. Testing Plan

### 8.1 Service Unit Tests (ragService)

- `isIndexed` true/false across status casing
- `addToSelection` adds unique docs, rejects the 6th (throws), returns unchanged for duplicates
- `removeFromSelection` removes by `fileId`
- `toFileIds` maps selection to `file_id` numbers
- `selectableDocuments` filters out non-INDEXED

### 8.2 SSE Parser Unit Tests (parseRagSse)

- token accumulation, final enrichment, comment-line skipping, malformed-line tolerance, empty final sources

### 8.3 Component Tests (optional, if a test runner exists)

- `DocumentMultiSelect` renders only INDEXED options; selected chips appear; no `Checkbox` in the tree
- `RagMessageBubble` renders answer text, collapsible sources, and gated diagnostics

### 8.4 Manual E2E

- sign in → open **Knowledge Base** tab
- select 1-5 INDEXED files; verify a 6th is rejected with the max-5 message
- confirm non-INDEXED files are not selectable
- send a question → watch tokens stream fully → citations appear → diagnostics behind expander
- ask with zero files selected → send disabled
- verify no S3 key is shown anywhere in the UI (devtools network/state)

## 9. Development Order

```text
1. Create ragApi.js (SSE client + pure parseRagSse)
2. Create ragService.js (max-5, INDEXED filter, file_id mapping)
3. Create DocumentMultiSelect.jsx (MUI chips/autocomplete, no checkboxes)
4. Create RagMessageBubble.jsx (answer + citations + diagnostics)
5. Create KnowledgeBase.jsx (page composes everything)
6. Add MUI Tabs navigation in App.jsx
7. Write unit tests for parseRagSse + ragService
8. Manual E2E against a running backend
```

Why this order:

```text
API first      |  everything depends on a working SSE client
    v          |
Service next   |  the max-5 / INDEXED rules are the contract the UI obeys
    v          |
Components     |  presentational only; ready to consume service + api
    v          |
Page           |  wires components + service + api
    v          |
Nav last       |  exposes the page in the app shell
```

## 10. Commands

From frontend:

```powershell
cd D:\Personal_Knowledge_Base\frontend
```

Install deps (first time only):

```powershell
npm install
```

Run the unit tests (adjust if the project uses a different runner):

```powershell
npm test
```

Start the dev server:

```powershell
npm run dev
```

With the backend running (`uv run uvicorn main:app --reload` from `backend`), sign in via the vault, open the **Knowledge Base** tab, and run the manual E2E in §8.4.

## 11. Code Review Checklist

```text
[ ] streamRagQuery returns { answer, sources, diagnostics } from the SSE stream
[ ] parseRagSse is a pure function, unit-tested
[ ] Stale queryRagPipeline() in documentApi.js is removed or superseded
[ ] ui is 100% Material UI via sx + theme tokens; zero CSS files / styled-components
[ ] No MUI Checkbox anywhere in the selection UI
[ ] Selection hard-capped at 5 via ragService (single source of truth)
[ ] No "All documents" option exists
[ ] Non-INDEXED documents are not selectable
[ ] S3 keys never appear in the UI or the sent payload (only file_ids)
[ ] apis / services / components / pages layers are cleanly separated
[ ] RagMessageBubble renders sources, gated diagnostics, and quote pre-wrap
[ ] App navigation uses MUI Tabs; theme consistent
[ ] Send disabled when no file selected or question empty
[ ] 400/401/stream-break handled without crashing the page
```

## 12. Phase 8 Definition of Done

Phase 8 is complete when:

- a dedicated **"Knowledge Base"** page is reachable from the app shell via MUI `Tabs`
- the page loads the user's `INDEXED` documents and presents them for selection by **title/filename** (no S3 keys)
- the user can select **up to 5** documents per conversation via MUI chips (no checkboxes), and a 6th is rejected with clear feedback
- there is **no** "ask all documents" option, and sending requires at least one selected file plus a non-empty question
- sending a question consumes the `POST /rag/query` **SSE** stream and renders answer tokens progressively
- each answer shows collapsible **citations** from `sources` and **diagnostics** behind a developer expander only
- non-`INDEXED` documents are not selectable
- the frontend is **Material UI only** (no custom CSS, no third-party styling)
- `apis` (network), `services` (logic), `components` (view), and `pages` (composition) remain cleanly separated
- unit tests cover the SSE parser and the max-5 / INDEXED service rules, and pass
- manual E2E succeeds against a running backend with no cross-tenant data or key leakage

## 13. Handoff to Phase 7 (regression) and Production

Phase 8 does not add new backend surface, so the Phase 7 verification plan is unaffected. Before rollout, re-run:

- Phase 7 security tests (guessed file IDs, Qdrant payload tampering, cross-tenant hydration) to confirm the new selector cannot be weaponized
- the full backend suite to confirm no regression

That is the handoff: Phase 6 defined the SSE contract, Phase 7 proved it safe and measured, and Phase 8 delivers a polished, MUI-only "Knowledge Base" chat where an authenticated user picks up to five of their indexed documents and receives a live, cited, grounded answer.
