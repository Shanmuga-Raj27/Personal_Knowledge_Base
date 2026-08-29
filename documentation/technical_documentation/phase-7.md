# Phase 7 Technical Documentation: AI Semantic Search & Backend Hardening

Welcome to the technical documentation for **Phase 7** of the Personal Knowledge Base project. This document serves as a comprehensive, production-grade guide explaining the architecture, design choices, database migrations, security hardening, and frontend integrations implemented for the V2 AI Semantic Search system. 

If you are a student learning backend engineering and AI integrations, this guide is designed for you. We will focus not just on *what* was built, but *why* specific software engineering patterns were chosen to solve hard problems like network latency, database connection exhaustion, race conditions, and tenant isolation.

---

## Architecture Diagram: Request & Indexing Flows

The diagram below illustrates how client requests and background indexing jobs flow through the system:

```text
[ React Frontend ]
       │
       │ (1) HTTP PATCH /files/{id} (Metadata Update)
       ▼
[ FastAPI Route Handler ] ──(2) Set indexing_status="INDEXING" & increment index_version──► [ MySQL DB ]
       │
       │ (3) Add background task
       ▼
[ Background Worker (sync_vector_in_background) ]
       │
       │ (4) Get Vector Embedding (Network I/O - OUTSIDE DB Transaction)
       ▼
[ Google Gemini API ]
       │
       │ (5) Upsert Vector Point (Network I/O - OUTSIDE DB Transaction)
       ▼
[ Qdrant Vector DB ]
       │
       │ (6) DB callback: Update status="INDEXED" (Check index_version)
       ▼
[ MySQL DB ]
```

---

## Section 1: Introduction to AI Semantic Search & Vector Databases

### Keyword Search vs. Semantic Search
In traditional database design, searching for text is typically done using SQL `LIKE` queries (e.g., `SELECT * FROM files WHERE description LIKE '%pig%'`) or full-text indexes. While fast, keyword search suffers from a fundamental limitation: **it only matches exact strings**. If a user searches for *"swine"* or *"bacon"*, keyword search will not return a document containing only the word *"pig"*, despite them being semantically related.

**Semantic Search** solves this by matching the **intent** and **meaning** of the query rather than exact characters. It does this by translating words, sentences, or entire documents into mathematical representations called **vector embeddings**.

### What is a Vector Embedding?
An embedding is an array of floating-point numbers (a vector) representing a coordinate in a high-dimensional space. The Google Gemini embedding model (`text-embedding-004`) maps text into a **768-dimensional space**. 

In this space, semantically similar concepts are placed closer together. For example, the vectors for "dog" and "puppy" will have a very small distance between them, while the vectors for "dog" and "microchip" will be much further apart.

```python
# Conceptual example of a 768-dimensional vector embedding returned by Gemini:
embedding = [0.01254, -0.04521, 0.08912, ..., -0.00341]  # Length: 768
```

### Cosine Similarity and Score Thresholds
To measure how similar a user's search query is to our indexed documents, we compute the angle between their respective vectors. This is known as **Cosine Similarity**. The similarity score ranges from `-1.0` (completely opposite) to `1.0` (identical).

In a production search engine, we do not want to display irrelevant documents just because they were the "closest" matches available. We enforce a **score threshold** (configured at `0.55` in our vector service). If the similarity score of a document is below `0.55`, it is filtered out as an irrelevant match.

### What is a Vector Database (Qdrant)?
Traditional databases (like MySQL) are optimized for relational tabular data, not for searching high-dimensional spaces. A **Vector Database** like Qdrant is built specifically to store, index, and query vector points using advanced algorithms like **HNSW (Hierarchical Navigable Small World)**.

In Qdrant, we store **Points**. Each point contains:
1. **ID**: A unique identifier (e.g., the file ID).
2. **Vector**: The 768-dimensional embedding array.
3. **Payload**: Key-value metadata (e.g., `user_id`, `filename`) used for filtering and tenant isolation.

---

## Section 2: Client Lifecycle & FastAPI Lifespan Architecture

### The FastAPI Lifespan Handler
In web frameworks, managing the lifecycle of external connections (like Qdrant and Gemini clients) is critical. A naive implementation creates a new client connection on every HTTP request. However, establishing TCP handshakes and TLS sessions on every request introduces massive latency and risks exhausting system file descriptors.

FastAPI provides a `lifespan` context manager that runs code **exactly once on startup** and **exactly once on shutdown**. We use this to initialize our database connections and clean them up gracefully when the server stops:

```python
# Located in backend/main.py
@asynccontextmanager
async def lifespan(app: FastAPI):
    """FastAPI application lifespan event handler for startup setup and legacy backfill."""
    try:
        # 1. Initialize Qdrant collection and payload indexes
        await init_qdrant_collection()
        # 2. Start the background recovery worker for unindexed files
        await recover_and_backfill_unindexed_files()
    except Exception:
        pass
    yield
    # 3. Clean up client connections on shutdown
    await close_qdrant_client()
```

### Client Singletons
We encapsulate client connections inside [vector_service.py](file:///d:/Personal_Knowledge_Base/backend/app/services/AI/vector_service.py) as module-level singletons:

```python
_qdrant_client: Optional[AsyncQdrantClient] = None
_gemini_client: Optional[genai.Client] = None

def get_qdrant_client() -> AsyncQdrantClient:
    global _qdrant_client
    if _qdrant_client is None:
        _qdrant_client = AsyncQdrantClient(url=settings.QDRANT_HOST)
    return _qdrant_client
```
This ensures the entire application reuses the same connection pool, yielding optimal throughput and low latency.

---

## Section 3: MySQL Database Evolution & Alembic Migrations

To support a robust asynchronous indexing pipeline, we upgraded our relational database schema. The MySQL table `file_metadata` was updated to track the lifecycle of the vector indexing process.

### Schema Fields for Indexing Lifecycle
We added five key columns to [db_models.py](file:///d:/Personal_Knowledge_Base/backend/app/database/db_models.py):

```python
class FileMetadata(Base):
    __tablename__ = "file_metadata"
    # ...
    is_indexed = Column(Boolean, default=False, nullable=False)
    indexing_status = Column(String(20), default="PENDING", nullable=False)
    index_version = Column(Integer, default=1, nullable=False)
    retry_count = Column(Integer, default=0, nullable=False)
    last_error = Column(String(500), nullable=True)
```

1. **`indexing_status`**: Enforces strict lifecycle states:
   * `PENDING`: File uploaded, waiting to be processed.
   * `INDEXING`: Currently computing embeddings or writing to Qdrant.
   * `INDEXED`: Vector generated and upserted successfully.
   * `FAILED`: Indexing failed after exhausting retries.
2. **`index_version`**: An incrementing counter used for **Optimistic Concurrency Control**. If a user updates a file's title twice in rapid succession, two background jobs are spawned. The `index_version` checks ensure that an older slow-running job does not overwrite status updates from a newer job.
3. **`retry_count` & `last_error`**: Tracks execution errors for diagnostics and retry limits.

### Alembic Schema Migration
We use Alembic to manage database schema updates incrementally. The migration script [9b3c2a10d4e5_add_indexing_retry_and_error_fields.py](file:///d:/Personal_Knowledge_Base/backend/alembic/versions/9b3c2a10d4e5_add_indexing_retry_and_error_fields.py) handles adding these fields safely:

```python
def upgrade() -> None:
    op.add_column(
        'file_metadata',
        sa.Column('retry_count', sa.Integer(), nullable=False, server_default='0')
    )
    op.add_column(
        'file_metadata',
        sa.Column('last_error', sa.String(length=500), nullable=True)
    )
```

---

## Section 4: Resilient Indexing Workflows & Decoupled I/O

### The Threat of Open Transactions during Network I/O
A major backend anti-pattern is holding database connections open while waiting for external network calls (such as Gemini APIs or Qdrant endpoints). Network calls are slow and unpredictable. If your server receives multiple requests and all of them are blocked waiting on network I/O while holding MySQL transactions open, the database connection pool will exhaust quickly, causing the entire application to crash.

### Decoupling Database Transactions
To solve this, we decoupled our background task [sync_vector_in_background](file:///d:/Personal_Knowledge_Base/backend/app/apis/routes/upload_file.py#L38-L82). The network calls happen **outside** of any database transaction. We only open a brief database connection at the very end to write the final status:

```python
# Network I/O happens OUTSIDE the database session:
try:
    indexed_success = await upsert_file_vector(
        file_id=file_id, user_id=user_id, filename=filename, title=title, description=description, tags=tags
    )
except Exception as exc:
    indexed_success = False
    error_msg = str(exc)

# Only now do we open a database session for a quick, isolated transaction:
db = SessionLocal()
try:
    db_file = db.query(FileMetadata).filter(FileMetadata.fileid == file_id).first()
    if db_file and db_file.index_version == target_version:
        db_file.is_indexed = indexed_success
        db_file.indexing_status = "INDEXED" if indexed_success else "FAILED"
        if not indexed_success:
            db_file.retry_count += 1
            db_file.last_error = error_msg[:500]
        db.commit()
finally:
    db.close()
```

### Startup Recovery Worker
If the application crashes midway through indexing, files can get stuck in the `INDEXING` or `PENDING` state. To ensure no data is lost, a background recovery worker runs once on application startup. It scans for stuck files and triggers a retry up to 3 times:

```python
# Located in backend/app/apis/routes/upload_file.py
async def recover_and_backfill_unindexed_files():
    db = SessionLocal()
    try:
        unindexed_files = db.query(FileMetadata).filter(
            FileMetadata.status == "active",
            ((FileMetadata.indexing_status.in_(["PENDING", "FAILED", "INDEXING"])) & (FileMetadata.retry_count < 3))
            | (FileMetadata.is_indexed == False)
        ).limit(50).all()
        
        for db_file in unindexed_files:
            db_file.indexing_status = "INDEXING"
            db.commit()
            await sync_vector_in_background(
                file_id=db_file.fileid, user_id=db_file.userid, filename=db_file.filename,
                title=db_file.title, description=db_file.description, tags=db_file.tags,
                target_version=db_file.index_version
            )
    finally:
        db.close()
```

---

## Section 5: The Search API Contract & Error Boundaries

### Standardized Search Contract
To maintain a strict API boundary, `GET /files/search` returns a structured contract schema [SearchResponseSchema](file:///d:/Personal_Knowledge_Base/backend/app/schemas/file.py#L82-L88). Crucially, the similarity score is preserved and returned to the caller:

```json
{
  "results": [
    {
      "file": {
        "fileId": 42,
        "filename": "quarterly_report.pdf",
        "title": "Q3 Financial Report",
        "indexingStatus": "INDEXED"
      },
      "score": 0.8954
    }
  ],
  "searchMode": "semantic",
  "total": 1
}
```

### Strict Validation (HTTP 422)
We prevent spam and malformed requests at the API gateway level. If a user submits a query exceeding 100 characters or consisting only of spaces, we reject it immediately with `422 Unprocessable Entity`:

```python
if len(q) > 100 or (q != "" and not q.strip()):
    raise HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail="Search query exceeds maximum length of 100 characters or contains only whitespace."
    )
```

### Error Boundaries (HTTP 503)
If the Gemini API or the Qdrant database is down, the system should not fail silently or return partial fallback results without informing the client. Instead, it raises an explicit `503 Service Unavailable`:

```python
except Exception as exc:
    logger.error("Vector search infrastructure failure: %s", str(exc))
    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="Vector search service is currently unavailable."
    )
```

### Multi-Tenant Scoped Isolation
In cloud applications, User A must never see User B's files. We enforce this boundary at the vector database level by attaching a filter key `user_id` to every query:

```python
# Located in backend/app/services/AI/vector_service.py
hits = await q_client.query_points(
    collection_name=collection_name,
    query=query_vector,
    query_filter=Filter(
        must=[
            FieldCondition(
                key="user_id",
                match=MatchValue(value=user_id),
            )
        ]
    ),
    limit=limit,
    score_threshold=0.55,
)
```

---

## Section 6: Frontend Request Synchronization & Score Badges

### The Problem: Search Input Race Conditions
When a user types quickly into a search bar, a network request is triggered for every keystroke. Because network requests resolve at variable times, a request sent for the letter "a" might finish *after* a request sent for the word "apple". If unhandled, the older search result will overwrite the newer search result, displaying incorrect data.

### The Solution: Axios AbortController
We solved this by integrating `AbortController` in [App.jsx](file:///d:/Personal_Knowledge_Base/frontend/src/App.jsx). Before spawning a new search request, we cancel any in-flight request:

```javascript
// Search request cancellation reference
const abortControllerRef = useRef(null)

useEffect(() => {
  const timer = setTimeout(async () => {
    // 1. Abort previous request
    if (abortControllerRef.current) {
      abortControllerRef.current.abort()
    }
    
    const controller = new AbortController()
    abortControllerRef.current = controller

    try {
      const response = await searchDocuments(searchTerm, controller.signal)
      // 2. Map and set documents ...
    } catch (err) {
      if (err.name === 'CanceledError') return // Silent discard
    }
  }, 350) // Debounce delay
  return () => clearTimeout(timer)
}, [searchTerm])
```

### Score Badge Rendering
We map the search response results to extract the cosine similarity score. In [FileRow.jsx](file:///d:/Personal_Knowledge_Base/frontend/src/components/FileRow.jsx), if `doc.score` is present, we render a styled visual chip showing the match percentage:

```jsx
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

## Section 7: Lessons Learned & Common Defect Root Causes

1. **Vector DB Unbounded Matches**: By default, vector databases return the closest neighbors even if they are not related. Enforcing `score_threshold = 0.55` stopped irrelevant queries (e.g., searching for "pig" on a resume list) from yielding spurious hits.
2. **React DOM Prop Leaking**: Passing capital-letter props like `InputProps` directly on custom wrappers causes console warnings. Utilizing MUI's standard `slotProps={{ input: { ... } }}` ensures clean HTML rendering and strict React 19 compliance.
3. **Transaction Connection Leaks**: We learned that keeping DB sessions open during network round-trips quickly starves database pools. Explicitly scoping database access block-by-block eliminates pool exhaustion entirely.
