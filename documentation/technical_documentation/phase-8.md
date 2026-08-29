# Phase 8 Technical Documentation: Resiliency, Background Tasks, & Frontend Semantic Search Integration

Welcome to the technical documentation for **Phase 8** of the Personal Knowledge Base project. This document guides you through the advanced patterns implemented to make our AI semantic search pipeline highly resilient, responsive, and production-grade.

We will cover the implementation details of asynchronous tasks, transaction isolation, strict validation, multi-tenant vector security, Axios request aborting, and similarity ranking displays. 

---

## 🗺️ System Data Flow & Architecture

The diagram below outlines the runtime lifecycle of indexing, background tasks, and search flows:

```text
[ React Client ] 
   │
   │ (1) HTTP POST /files/upload-complete
   ▼
[ FastAPI App ] ──(2) Create file metadata in DB (status="active", indexing_status="INDEXING") ──► [ MySQL DB ]
   │
   │ (3) Enqueue background task
   ▼
[ sync_vector_in_background() ] ──(4) Return immediate 200 OK to React Client
   │
   ├─► (5) Call Gemini API (Text Embedding - Outside DB Transaction)
   ├─► (6) Upsert Point into Qdrant Vector DB (Outside DB Transaction)
   │
   ▼ (7) Open quick DB Session (Isolated transaction)
[ Check index_version == target_version ]
   │
   ├─► YES (Current version matches) ──► Commit indexing_status = "INDEXED"
   └─► NO (Stale version skipped)    ──► Log warning (Discard stale job)
```

---

## Section 1: Non-Blocking File Uploads & FastAPI BackgroundTasks

### The Challenge: Synchronous API Blockers
In older or naive implementations of AI web apps, when a user completes a file upload, the server executes the following steps in sequence:
1. Verify S3 storage.
2. Store file metadata in the relational database.
3. Send the file contents to Gemini API for vector embedding generation.
4. Upload the generated 768-dimensional vector into the Qdrant database.
5. Update the MySQL database to mark the file as indexed.
6. Return a `200 OK` response to the client.

Because network calls to external APIs (Gemini and Qdrant) take significant time (often between 1 and 3 seconds), the user is forced to wait on a loading screen. If the connection is slow or the API experiences high latency, the request can timeout, leaving the frontend in an inconsistent state.

### The Solution: Non-Blocking Asynchronous Tasks
To achieve sub-100ms response times, we offload vector computation and database syncing to FastAPI's built-in `BackgroundTasks` queue. The HTTP request cycle completes and returns a response to the client immediately after Step 2, while the heavy lifting runs in the background.

```python
# Located in backend/app/apis/routes/upload_file.py
@router.post("/upload-complete", response_model=FileUploadCompleteResponse)
async def complete_upload(
    payload: FileUploadCompleteRequest,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    # 1. Update database record to 'active' and 'INDEXING' status
    db_file.status = "active"
    db_file.size_bytes = meta["size_bytes"]
    db_file.indexing_status = "INDEXING"
    db.commit()
    db.refresh(db_file)

    # 2. Queue the vector sync worker in the background
    background_tasks.add_task(
        sync_vector_in_background,
        file_id=db_file.fileid,
        user_id=current_user.id,
        filename=db_file.filename,
        title=db_file.title,
        description=db_file.description,
        tags=db_file.tags,
        target_version=db_file.index_version,
    )

    # 3. Return response instantly (Sub-50ms)
    return FileUploadCompleteResponse(
        message="File verified and queued for indexing.",
        file=db_file,
    )
```

---

## Section 2: Concurrency Controls & Optimistic Versioning

### Stale Background Overwrites
Because tasks run asynchronously in the background, a race condition can occur when a user updates a document's metadata (like editing the title) immediately after uploading it.
1. **Job 1 (Upload)** is enqueued to index the original title.
2. **Job 2 (Metadata Edit)** is enqueued to index the new edited title.
3. If the external Gemini API is slow during **Job 2**, **Job 1** might finish *after* **Job 2**. 
4. Without concurrency safeguards, **Job 1** will write the old vector to Qdrant and mark the document status as `INDEXED` based on outdated data, overwriting the new changes.

### The Optimistic Concurrency Protocol
We solve this using an `index_version` column in our database schema [db_models.py](file:///d:/Personal_Knowledge_Base/backend/app/database/db_models.py).
* Every time a user updates a file's metadata, we increment `index_version` by `1` inside the HTTP request database session.
* We pass this `target_version` to the background task.
* When the background task finishes generating the vector embedding, it opens a fresh database session and checks if the version is still current:

```python
# Located in backend/app/apis/routes/upload_file.py
if db_file:
    # Check if the version has changed since the task was queued
    if db_file.index_version == target_version:
        db_file.is_indexed = indexed_success
        db_file.indexing_status = "INDEXED" if indexed_success else "FAILED"
        db_file.last_error = None if indexed_success else error_msg
        db.commit()
    else:
        logger.info(
            "Skipping stale background indexing task for file %s (current %s != target %s).",
            file_id, db_file.index_version, target_version
        )
```

---

## Section 3: API Contracts & Similarity Score Badges

### Structured Search Response Schema
We updated the API response contract to preserve vector similarity scores returned from Qdrant search results. The scores allow the frontend to display match relevance directly to the user.

The Pydantic schemas in [file.py](file:///d:/Personal_Knowledge_Base/backend/app/schemas/file.py) are structured as follows:

```python
class SearchResultItem(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    file: FileMetadataSchema
    score: Optional[float] = None


class SearchResponseSchema(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    results: list[SearchResultItem]
    search_mode: str = Field(..., alias="searchMode")  # "semantic" | "fallback" | "none"
    total: int
```

### Displaying Similarity Badges
When the frontend fetches documents using a search query, it maps the `SearchResultItem` results, extracts the `score`, and renders a styled MUI `Chip` badge.

```jsx
// Located in frontend/src/components/FileRow.jsx
{doc.score !== undefined && doc.score !== null && (
  <Chip
    label={`🎯 ${(doc.score * 100).toFixed(0)}% Match`}
    size="small"
    variant="outlined"
    sx={{
      height: 16,
      fontSize: '0.6rem',
      fontWeight: 700,
      borderColor: '#93C5FD',
      color: '#1E40AF',
      backgroundColor: '#EFF6FF',
      borderRadius: '4px',
      px: 0.5,
      flexShrink: 0
    }}
  />
)}
```

---

## Section 4: Validation Boundaries & Resiliency Fallbacks

### Strict Validation (HTTP 422)
To keep the search engine clean and prevent useless database searches, we enforce limits on input queries. Whitespace-only queries or strings exceeding 100 characters are blocked at the router boundary:

```python
# Located in backend/app/apis/routes/upload_file.py
if len(q) > 100 or (q != "" and not q.strip()):
    raise HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail="Search query exceeds maximum length of 100 characters or contains only whitespace.",
    )
```

### Error Boundaries (HTTP 503)
If Gemini or Qdrant is unreachable due to a network outage or API quota limits, we raise an explicit `HTTP 503 Service Unavailable`. This informs the client that the search system is down:

```python
except Exception as exc:
    logger.error("Vector search infrastructure failure: %s", str(exc))
    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="Vector search service is currently unavailable.",
    )
```

### Zero-Match Responses
If vector search executes successfully but finds no matching points above our cosine similarity threshold of `0.55`, it returns a `200 OK` with an empty result set:

```python
return SearchResponseSchema(
    results=[],
    search_mode="semantic",
    total=0,
)
```

---

## Section 5: Frontend AbortController Request Cancellation

### The Challenge: Search Race Conditions
When a user types "fast" into a search input, multiple HTTP requests are generated in rapid succession:
1. `GET /files/search?q=f`
2. `GET /files/search?q=fa`
3. `GET /files/search?q=fas`
4. `GET /files/search?q=fast`

If the request for `q=fa` encounters high network jitter, it might resolve *after* the request for `q=fast`. The UI will briefly render the correct results for "fast", only to be immediately overwritten by outdated results for "fa".

### The Solution: AbortController
To prevent this, the frontend search effect uses an `AbortController`. When a new request is scheduled, we immediately abort the active in-flight request:

```javascript
// Located in frontend/src/App.jsx
const abortControllerRef = useRef(null)

useEffect(() => {
  if (!token || !isAuthenticated()) return

  const timer = setTimeout(async () => {
    // Abort previous request
    if (abortControllerRef.current) {
      abortControllerRef.current.abort()
    }

    const controller = new AbortController()
    abortControllerRef.current = controller

    try {
      const response = await searchDocuments(searchTerm, controller.signal)
      const rawResults = response?.results || response || []
      // Map results...
      setDocuments(mappedDocs)
    } catch (err) {
      if (err.name === 'CanceledError' || err.code === 'ERR_CANCELED') {
        return // Quietly ignore cancelled requests
      }
      console.error('Search request failed:', err)
    }
  }, 350)

  return () => clearTimeout(timer)
}, [searchTerm, token])
```

---

## Section 6: Testing & Verification Strategy

### Automated Verification
We verify these features using unit and integration tests under `backend/tests/`:

1. **Schema and Contract Validation**: Verifies that `SearchResponseSchema` contains `results` with `score` properties and structured payloads.
2. **Query Input Limits**: Tests that sending query strings >100 characters returns a `422 Unprocessable Entity` status code.
3. **Outage Behavior**: Simulates a vector search backend failure to ensure the client receives a `503 Service Unavailable` status code.
4. **Multi-Tenant Scoped Search**: Asserts that User A cannot search or retrieve vector coordinates for files uploaded by User B.

Run the test suite using this command in your backend directory:
```powershell
.venv\Scripts\python.exe -m pytest
```

### Manual Verification
1. Open the browser console in your local development environment.
2. Search for a term in the document database.
3. Inspect the Network Tab to verify that fast typing triggers request cancellations (showing `canceled` status in red).
4. Verify that relevance percentages (e.g., `🎯 92% Match`) are visible on document cards for vector matches.
