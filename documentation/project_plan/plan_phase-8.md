# Phase C / Phase 8: Resiliency, Background Tasks, & Frontend Semantic Search Integration

Welcome to the specification and implementation plan for **Phase C (Phase 8)**.

In **Phase B (Phase 7)**, we integrated Google Gemini (`gemini-embedding-2`) and Qdrant Vector DB into our FastAPI backend to perform multi-tenant semantic searches.

In **Phase C**, we will make our application **production-grade**, **resilient**, and **lightning-fast** by addressing three key real-world challenges:
1. **Non-blocking Uploads**: Offloading heavy AI embedding and Qdrant upserts to FastAPI `BackgroundTasks` so file uploads return immediately.
2. **Resilient Search Fallbacks**: Automatically falling back to MySQL keyword substring search (`LIKE %q%`) if Gemini or Qdrant is offline or returns no vector matches.
3. **Full Frontend Integration**: Connecting our React MUI client (`SearchHeader`, `App.jsx`, `FileList`, `documentApi.js`) to live semantic search, complete with search debouncing, loading skeletons, indexing status indicators, and fallback alerts.

---

## 🗺️ High-Level Request & Fallback Flow

### 1. Non-Blocking File Upload Flow (FastAPI `BackgroundTasks`)
```text
User Uploads File ──► Verify in S3 ──► Save MySQL Record (status="active", is_indexed=False)
                                            │
                                            ├─► Return 200 OK Response Immediately to React
                                            │
                                            └─► [Background Task]: Generate Gemini Embedding ──► Upsert to Qdrant ──► Update is_indexed=True in MySQL
```

### 2. Resilient Semantic Search Flow
```text
React Search Request (GET /files/search?q="cloud architecture")
                      │
                      ▼
        FastAPI Search Handler
                      │
        ┌─────────────┴─────────────┐
        ▼                           ▼
Try Gemini & Qdrant         If Offline / Error / 0 Matches
(Vector Similarity Match)           │
        │                           ▼
        │             Fallback to MySQL Substring Search
        │             (WHERE title LIKE %q% OR description LIKE %q% OR tags LIKE %q%)
        │                           │
        └─────────────┬─────────────┘
                      ▼
    Return Results + Fallback Header Indicator to React
```

---

## 🛠️ Detailed Implementation Steps

### Step 1: Offload AI Vector Indexing to FastAPI `BackgroundTasks`

Currently, when a user completes an upload, the API waits synchronously for Gemini to generate coordinates and Qdrant to upsert before responding. If the AI network call takes 2 seconds, the user waits 2 seconds.

We will use FastAPI's built-in `BackgroundTasks` to respond instantly to the user while performing AI operations in the background.

#### Backend Changes (`app/apis/routes/upload_file.py`):
```python
from fastapi import BackgroundTasks

async def background_vector_index_task(file_id: int, user_id: int, filename: str, title: str | None, description: str | None, tags: str | None, db_engine):
    """Background worker function that runs outside the HTTP response cycle."""
    # Create an independent DB session for the background thread
    with Session(db_engine) as bg_db:
        success = await upsert_file_vector(
            file_id=file_id,
            user_id=user_id,
            filename=filename,
            title=title,
            description=description,
            tags=tags
        )
        # Update is_indexed status in MySQL
        db_file = bg_db.query(FileMetadata).filter(FileMetadata.fileid == file_id).first()
        if db_file:
            db_file.is_indexed = success
            bg_db.commit()

@router.post("/upload-complete", response_model=FileUploadCompleteResponse)
async def complete_upload(
    payload: FileUploadCompleteRequest,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    # 1. Verify S3 storage...
    db_file.status = "active"
    db.commit()
    db.refresh(db_file)

    # 2. Queue background task and return immediately!
    background_tasks.add_task(
        background_vector_index_task,
        file_id=db_file.fileid,
        user_id=current_user.id,
        filename=db_file.filename,
        title=db_file.title,
        description=db_file.description,
        tags=db_file.tags,
        db_engine=engine
    )

    return FileUploadCompleteResponse(...)
```

---

### Step 2: Implement Keyword Search Fallback on Backend

If Gemini or Qdrant is down, or if vector search returns no hits, our app must never crash or return empty screens. We fall back to a MySQL keyword query across `title`, `description`, `tags`, and `filename`.

#### Backend Changes (`app/apis/routes/upload_file.py`):
```python
def mysql_keyword_fallback_search(db: Session, user_id: int, search_term: str) -> list[FileMetadata]:
    """Fallback search using MySQL SQL LIKE conditions."""
    pattern = f"%{search_term}%"
    return (
        db.query(FileMetadata)
        .filter(
            FileMetadata.userid == user_id,
            FileMetadata.status == "active",
            (
                FileMetadata.title.ilike(pattern) |
                FileMetadata.description.ilike(pattern) |
                FileMetadata.tags.ilike(pattern) |
                FileMetadata.filename.ilike(pattern)
            )
        )
        .order_by(FileMetadata.created_at.desc())
        .all()
    )

@router.get("/search", response_model=list[FileMetadataSchema])
async def search_files(
    q: str = "",
    response: Response = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    search_term = q.strip()
    if not search_term:
        return await list_files(current_user=current_user, db=db)

    # Try Vector Search
    matched_ids = await search_file_vectors(query_text=search_term, user_id=current_user.id, limit=15)

    # If vector search produced matches, fetch and sort them
    if matched_ids:
        files = (
            db.query(FileMetadata)
            .filter(
                FileMetadata.fileid.in_(matched_ids),
                FileMetadata.userid == current_user.id,
                FileMetadata.status == "active",
            )
            .all()
        )
        if files:
            file_map = {f.fileid: f for f in files}
            return [file_map[fid] for fid in matched_ids if fid in file_map]

    # FALLBACK TRIGGER: If Qdrant/Gemini failed or returned 0 hits
    if response:
        response.headers["X-Search-Fallback"] = "true"

    return mysql_keyword_fallback_search(db=db, user_id=current_user.id, search_term=search_term)
```

---

### Step 3: Frontend API Extension (`documentApi.js`)

Add the `searchDocuments` API call function in `frontend/src/apis/documentApi.js`:

```javascript
/**
 * Perform semantic or fallback search on document vault.
 * @param {string} query Search query string.
 * @returns {Promise<Array<object>>}
 */
export const searchDocuments = (query) => {
  return axiosClient.get('/files/search', {
    params: { q: query }
  })
}
```

---

### Step 4: Frontend UI Integration (`SearchHeader`, `App.jsx`, `FileList`)

#### 1. Search Debouncing & Real-time Results in `App.jsx`
Implement a 300ms debounce timer so typing in the search bar executes live requests smoothly without overloading the network:

```javascript
// In App.jsx
const [searchTerm, setSearchTerm] = useState('')
const [isSearching, setIsSearching] = useState(false)
const [isFallbackSearch, setIsFallbackSearch] = useState(false)

useEffect(() => {
  if (!isAuthenticated()) return

  const delayDebounceFn = setTimeout(async () => {
    if (!searchTerm.trim()) {
      setIsFallbackSearch(false)
      loadDocuments()
      return
    }

    setLoadingDocs(true)
    try {
      const response = await axiosClient.get('/files/search', {
        params: { q: searchTerm }
      })
      
      // Check if backend used fallback keyword search
      const fallbackHeader = response.headers['x-search-fallback']
      setIsFallbackSearch(fallbackHeader === 'true')
      setDocuments(response.data)
    } catch (err) {
      console.error('Search failed:', err)
    } finally {
      setLoadingDocs(false)
    }
  }, 350)

  return () => clearTimeout(delayDebounceFn)
}, [searchTerm, token])
```

#### 2. Visual Indicators in `FileList.jsx` and `SearchHeader.jsx`
* **Fallback Alert Banner**: If `isFallbackSearch` is `true`, display an informative MUI Alert banner:
  > *"Semantic AI search returned no vector matches or is offline. Displaying keyword search results instead."*
* **Indexing Status Chip**: Display a subtle status indicator on file cards/rows:
  * 🟢 `Indexed` (Vector coordinates exist in Qdrant)
  * 🟡 `Indexing...` (Background worker is currently embedding text)

---

## 🧪 Student Checkpoints & Testing Strategy

1. **Verify Instant Uploads**: Upload a file in React dashboard. Notice that upload verification returns immediately without waiting 2 seconds for Gemini API response.
2. **Verify Background Indexing**: Check MySQL `file_metadata` table a few seconds after upload; `is_indexed` flips from `0` to `1`.
3. **Verify Search Fallback**:
   * Temporarily stop Qdrant or set invalid `GEMINI_API_KEY`.
   * Type a search query in the search bar.
   * Verify that the app still returns keyword matches from MySQL and shows the `X-Search-Fallback` notice!
