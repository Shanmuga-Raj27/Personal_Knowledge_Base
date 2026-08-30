# Data Pipeline & Architecture Specifications

## 1. Data Pipeline Overview & Architecture

The **Personal Knowledge Base** data pipeline is built around a hybrid storage model that decouples relational metadata management, binary file persistence, and high-dimensional AI vector search. 

### Core Purpose of the Data Layer
1. **Zero Server Memory Bottlenecks:** Files are streamed directly from client browsers to S3-compatible cloud storage using presigned PUT URLs, preventing raw file content from entering the Python application memory.
2. **Strict Multi-Tenant Isolation:** Relational integrity in MySQL links every metadata record and storage object key to a verified user primary key (`users.id`).
3. **Decoupled Asynchronous Indexing:** Heavy operations—such as text formatting, Gemini embedding generation, and vector indexing—are executed asynchronously via FastAPI `BackgroundTasks`, isolating write latencies from user API response times.
4. **Resilient Vector Retrieval:** Vector similarity queries in Qdrant use strict `user_id` payload filters and score thresholds (`0.55`), guaranteeing multi-tenant isolation and clean fallbacks.

### End-to-End ASCII System Data Architecture

```
+-----------------------------------------------------------------------------------+
|                                  PRESENTATION TIER                                |
|                                                                                   |
|  +-----------------------------------------------------------------------------+  |
|  |                     React SPA Client (Vite + Material UI)                   |  |
|  +-----------------------------------------------------------------------------+  |
|         |                                 |                             |         |
|         | (1) POST /files/upload-url      | (3) Direct PUT Upload       | (5) GET |
|         v                                 v                             v         |
+---------|---------------------------------|-----------------------------|---------+
          |                                 |                             |
          |                                 |                             |
+---------|---------------------------------|-----------------------------|---------+
|         v                                 |                             v         |
|  +------------------------------+         |              +---------------------+  |
|  |   FastAPI REST API Server    |         |              | Backblaze B2 / S3   |  |
|  |   (Uvicorn ASGI Engine)      |         |              | (Object Storage)    |  |
|  +------------------------------+         |              +---------------------+  |
|       |         |          |              |                         ^             |
|       |         |          +--------------|-------------------------+             |
|       |         |                         | (2) S3 Presigned URL                  |
|       |         |                         +---------------------------------------+
|       |         |
|       | (4) Async Background Task (sync_vector_in_background)
|       |         |
|       |         +------------------------------------+
|       |                                              |
|       v                                              v
|  +------------------------------+         +------------------------------------+  |
|  | MySQL 8.0 Relational DB      |         | Google Gemini Embedding API        |  |
|  | (Users & FileMetadata)       |         | (gemini-embedding-2 / 768-dim)     |  |
|  +------------------------------+         +------------------------------------+  |
|                                                      |                            |
|                                                      | Vector Array [768]         |
|                                                      v                            |
|                                           +------------------------------------+  |
|                                           | Qdrant Vector Search Engine        |  |
|                                           | (Collection: document_vault)       |  |
|                                           +------------------------------------+  |
|                                                                                   |
|                                  PERSISTENCE TIER                                 |
+-----------------------------------------------------------------------------------+
```

---

## 2. Storage Roles & Responsibilities

The data architecture splits data storage duties across three specialized infrastructure tiers:

### 2.1 MySQL (Relational Persistence Layer)
MySQL acts as the single source of truth for user credentials, account permissions, document metadata, lifecycle statuses, and vector indexing tracking.

#### Active Schemas & Database Tables
Defined in [db_models.py](file:///d:/Personal_Knowledge_Base/backend/app/database/db_models.py):

##### Table 1: `users`
Stores user registration data and authentication statuses.

| Field Name | Data Type | Nullable | Default | Constraints & Description |
| :--- | :--- | :--- | :--- | :--- |
| `id` | `INTEGER` | No | Auto-Increment | Primary Key, Unique user ID. |
| `email` | `VARCHAR(255)` | No | None | Unique Key, Index. User login email address. |
| `hashed_password` | `VARCHAR(255)` | No | None | Argon2id encrypted password string. |
| `status` | `VARCHAR(20)` | No | `"active"` | Account state (`"active"`, `"disabled"`). |
| `created_at` | `DATETIME` | No | `func.now()` | UTC account creation timestamp. |

##### Table 2: `file_metadata`
Tracks physical storage keys, MIME types, custom metadata fields, and vector synchronization states.

| Field Name | Data Type | Nullable | Default | Constraints & Description |
| :--- | :--- | :--- | :--- | :--- |
| `fileid` | `INTEGER` | No | Auto-Increment | Primary Key, Unique document record ID. |
| `s3_key` | `VARCHAR(255)` | No | None | Unique Key, Index. Storage key in S3 bucket. |
| `filename` | `VARCHAR(255)` | No | None | Original uploaded file name. |
| `content_type` | `VARCHAR(100)` | Yes | `None` | MIME type string (`"application/pdf"`, etc.). |
| `size_bytes` | `BIGINT` | Yes | `None` | Verified binary file size in bytes. |
| `status` | `VARCHAR(20)` | No | `"pending"` | Document status (`"pending"`, `"active"`, `"failed"`). |
| `title` | `VARCHAR(100)` | Yes | `None` | User custom title attribute. |
| `description` | `VARCHAR(255)` | Yes | `None` | User custom summary text description. |
| `tags` | `VARCHAR(50)` | Yes | `None` | Comma-separated search tag keywords. |
| `is_indexed` | `BOOLEAN` | No | `False` | True if vector point is present in Qdrant. |
| `indexing_status`| `VARCHAR(20)` | No | `"PENDING"` | Lifecycle status (`"PENDING"`, `"INDEXING"`, `"INDEXED"`, `"FAILED"`). |
| `index_version` | `INTEGER` | No | `1` | Optimistic versioning counter for concurrent syncs. |
| `retry_count` | `INTEGER` | No | `0` | Failed indexing attempt count (max 3). |
| `last_error` | `VARCHAR(500)` | Yes | `None` | Truncated error traceback message. |
| `userid` | `INTEGER` | No | None | Foreign Key referencing `users.id` (`ON DELETE CASCADE`). |
| `created_at` | `DATETIME` | No | `func.now()` | Record creation timestamp. |
| `updated_at` | `DATETIME` | No | `func.now()` | Auto-updated modification timestamp. |

---

### 2.2 S3 / Backblaze B2 (Object Storage Tier)
S3-compatible object storage holds raw document assets.

- **Bucket Name:** Configured via `S3_BUCKET_NAME` in [config.py](file:///d:/Personal_Knowledge_Base/backend/app/core/config.py) (`personal-knowledge-base`).
- **Allowed MIME Types:** Enforced in [s3_service.py](file:///d:/Personal_Knowledge_Base/backend/app/services/AWS/s3_service.py):
  - `application/pdf` (.pdf)
  - `application/vnd.openxmlformats-officedocument.wordprocessingml.document` (.docx)
  - `text/plain` (.txt)
  - `text/markdown` (.md)
- **Object Key Naming Convention:** Objects are stored using randomized UUID hex prefixes to eliminate filename collisions and path traversal risks:
  ```python
  # Code snippet from app/services/AWS/s3_service.py
  def generate_safe_key(filename: str) -> str:
      safe_name = _sanitize_filename(filename)
      unique_id = uuid.uuid4().hex
      return f"uploads/{unique_id}_{safe_name}"
  ```

---

### 2.3 Qdrant (Vector Search Tier)
Qdrant stores dense vector representations of documents for semantic similarity queries.

- **Collection Name:** `document_vault` (configured in `QDRANT_COLLECTION_NAME`).
- **Vector Dimension:** `768` float dimensions matching `gemini-embedding-2` model output.
- **Distance Metric:** Cosine Similarity (`models.Distance.COSINE`).
- **Payload Indexing:** Constructed during collection initialization in [vector_service.py](file:///d:/Personal_Knowledge_Base/backend/app/services/AI/vector_service.py):
  - `user_id` payload field -> Indexed as `INTEGER` schema for multi-tenant filtering.
  - `tags` payload field -> Indexed as `KEYWORD` schema for tag filtering.
- **Payload Structure Table:**

| Field Key | Type | Description |
| :--- | :--- | :--- |
| `file_id` | `INTEGER` | Primary key matching MySQL `file_metadata.fileid`. |
| `user_id` | `INTEGER` | Foreign key matching MySQL `users.id` for tenant scoping. |
| `filename` | `STRING` | Original name of the document. |
| `title` | `STRING` | Custom user-supplied title or empty string. |
| `description` | `STRING` | Custom user-supplied description or empty string. |
| `tags` | `STRING` | Custom comma-separated tags or empty string. |

---

## 3. Ingestion & Write Pipeline (Step-by-Step)

The data ingestion process uses a two-phase upload handshake followed by asynchronous vector indexing.

### ASCII Ingestion & Write Pipeline Flow

```
[ User Browser / Client ]
           |
           | (1) POST /files/upload-url (filename, contentType)
           v
[ FastAPI Router: get_upload_url() ]
           |
           |-- Enforces ALLOWED_MIME_TYPES in app/services/AWS/s3_service.py
           |-- Generates unique key: uploads/{uuid}_{safe_name}
           |-- Requests presigned PUT URL from Boto3 client
           |-- Inserts pending record into MySQL: FileMetadata(status="pending", userid=user.id)
           v
[ User Browser / Client ]
           |
           | (2) Direct HTTP PUT [Binary Content] to S3 Presigned URL
           v
[ Backblaze B2 / S3 Object Storage ]
           |
           | (3) HTTP 200 OK Response
           v
[ User Browser / Client ]
           |
           | (4) POST /files/upload-complete (key, filename)
           v
[ FastAPI Router: complete_upload() ]
           |
           |-- Executes head_object via s3_service.get_object_metadata()
           |-- Updates MySQL: status="active", size_bytes=Length, indexing_status="INDEXING"
           |-- Schedules sync_vector_in_background via FastAPI BackgroundTasks
           v
[ FastAPI Background Task: sync_vector_in_background() ]
           |
           |-- Formats text string: build_file_text_representation(filename, title, description, tags)
           |-- Calls Google Gemini API: generate_embedding(text) -> [768 floats]
           |-- Upserts point to Qdrant: PointStruct(id=file_id, vector=vector, payload=payload_dict)
           |-- Evaluates index_version optimistic concurrency check
           \--> Updates MySQL: is_indexed=True, indexing_status="INDEXED"
```

### Detailed Write Step Lifecycle

1. **Upload Presigned URL Generation:**
   - The user selects a file in [App.jsx](file:///d:/Personal_Knowledge_Base/frontend/src/App.jsx).
   - The frontend calls `getUploadUrl()` in [documentApi.js](file:///d:/Personal_Knowledge_Base/frontend/src/apis/documentApi.js).
   - The endpoint `get_upload_url()` in [upload_file.py](file:///d:/Personal_Knowledge_Base/backend/app/apis/routes/upload_file.py) validates the file's MIME type using `validate_mime_type()`.
   - `create_presigned_put_url()` in [s3_service.py](file:///d:/Personal_Knowledge_Base/backend/app/services/AWS/s3_service.py) generates a key `uploads/{uuid.hex}_{safe_name}` and returns an S3 presigned PUT URL (valid for 3600 seconds).
   - A new row is inserted into MySQL `file_metadata` with `status="pending"`, `size_bytes=0`, and `userid=current_user.id`.

2. **Direct Storage Upload:**
   - The browser streams binary file content directly to S3 via HTTP PUT without passing through Python memory.

3. **Upload Verification & Handshake:**
   - On completion, the frontend posts to `/files/upload-complete`.
   - `complete_upload()` invokes `get_object_metadata(key)` in [s3_service.py](file:///d:/Personal_Knowledge_Base/backend/app/services/AWS/s3_service.py) to run `s3_client.head_object()`.
   - If found, MySQL is updated to `status="active"`, `size_bytes=response["ContentLength"]`, and `indexing_status="INDEXING"`.
   - If missing, MySQL is updated to `status="failed"` and an HTTP 404 exception is returned.

4. **Async Embedding & Vector Upsert:**
   - `background_tasks.add_task(sync_vector_in_background, ...)` schedules vector indexing.
   - The background worker constructs a text string:
     ```python
     # Code snippet from app/services/AI/vector_service.py
     def build_file_text_representation(filename, title, description, tags):
         parts = [
             f"Filename: {filename}",
             f"Title: {title or 'Untitled'}",
             f"Description: {description or 'No description provided.'}",
             f"Tags: {tags or ''}",
         ]
         return "\n".join(parts)
     ```
   - Embeddings are generated via Google Gemini: `g_client.aio.models.embed_content(model="gemini-embedding-2", contents=text, config=EmbedContentConfig(output_dimensionality=768))`.
   - Vector points are upserted into Qdrant using `q_client.upsert()`.
   - On success, MySQL is updated to `is_indexed=True` and `indexing_status="INDEXED"`.

---

## 4. Retrieval & Query Pipeline (Step-by-Step)

The retrieval pipeline handles document listing, metadata updates, file views via presigned GET URLs, and multi-tenant semantic AI searches.

### ASCII Retrieval & Semantic Search Pipeline Flow

```
[ User Search Input ]
           |
           | (1) GET /files/search?q=query (JWT Bearer Token)
           v
[ FastAPI Router: search_files() in app/apis/routes/upload_file.py ]
           |
           |-- Stage 1: Validate Query Length (len(q) <= 100 and non-whitespace check)
           |    |-- If invalid -> Raise HTTP 422 Unprocessable Entity
           |
           |-- Stage 2: Empty Query Check (q.strip() == "")
           |    |-- If empty -> Return all active files for current_user.id from MySQL
           |
           |-- Stage 3: Generate Query Vector Embedding
           |    |-- Calls generate_embedding(query_text) via Gemini API -> [768 floats]
           |
           |-- Stage 4: Multi-Tenant Vector Search in Qdrant
           |    |-- Executed in search_file_vectors() in app/services/AI/vector_service.py
           |    |-- Applies Filter(must=[FieldCondition(key="user_id", match=MatchValue(value=user_id))])
           |    |-- Sets score_threshold=0.55 and limit=15
           |
           |-- Stage 5: Relational Metadata Enrichment
           |    |-- Extracts matched file_ids from Qdrant hits
           |    |-- Queries MySQL: FileMetadata.fileid.in_(matched_ids) & userid == user.id & status == "active"
           |
           v
[ Search Response Formatter ]
           |
           \--> Returns SearchResponseSchema(results=[SearchResultItem(file, score)], searchMode="semantic", total=N)
```

### Detailed Retrieval Step Lifecycle

1. **Query Pre-Processing & Validation:**
   - Queries are debounced on the frontend by 350ms in [App.jsx](file:///d:/Personal_Knowledge_Base/frontend/src/App.jsx).
   - `search_files()` in [upload_file.py](file:///d:/Personal_Knowledge_Base/backend/app/apis/routes/upload_file.py) validates inputs: queries over 100 characters or whitespace-only inputs trigger an HTTP 422 error.
   - Blank queries bypass vector searches and return user files directly from MySQL.

2. **Query Embedding Generation:**
   - `search_file_vectors()` sends the text query to Google Gemini API to produce a 768-dimension query vector.
   - Infrastructure errors during embedding generation trigger an HTTP 503 Service Unavailable exception.

3. **Multi-Tenant Scoped Vector Search:**
   - The query vector is submitted to Qdrant using `AsyncQdrantClient.query_points()`:
     ```python
     # Code snippet from app/services/AI/vector_service.py
     hits = await q_client.query_points(
         collection_name=collection_name,
         query=query_vector,
         query_filter=Filter(
             must=[FieldCondition(key="user_id", match=MatchValue(value=user_id))]
         ),
         limit=15,
         score_threshold=0.55,
     )
     ```
   - Matches with similarity scores below `0.55` are discarded.

4. **Relational Enrichment & Response Mapping:**
   - The system retrieves matched `file_ids` from Qdrant hits and queries MySQL for document metadata records owned by `current_user.id`.
   - Results are mapped into `SearchResponseSchema` containing file metadata and similarity scores.

5. **Document Viewing via Presigned GET URLs:**
   - When a user clicks "View File", the frontend calls `getViewUrl()` in [documentApi.js](file:///d:/Personal_Knowledge_Base/frontend/src/apis/documentApi.js).
   - The endpoint `get_view_url()` in [upload_file.py](file:///d:/Personal_Knowledge_Base/backend/app/apis/routes/upload_file.py) verifies file ownership in MySQL.
   - `create_presigned_get_url()` in [s3_service.py](file:///d:/Personal_Knowledge_Base/backend/app/services/AWS/s3_service.py) generates a presigned GET URL (valid for 300 seconds).

---

## 5. Data Synchronization, Consistency & Failure Handling

Maintaining consistency across relational databases (MySQL), object storage (S3), and vector stores (Qdrant) is handled through several mechanisms:

### 5.1 Optimistic Concurrency Control (`index_version`)
When users update document metadata (titles, descriptions, tags) via `PATCH /files/{fileid}`, vector re-indexing is triggered. To prevent stale background tasks from overwriting newer updates:

1. The `index_version` integer column in MySQL is incremented by 1 during every `PATCH` request.
2. The target version is passed to `sync_vector_in_background()`.
3. Before committing vector indexing statuses (`INDEXED` or `FAILED`), the worker compares `db_file.index_version` with `target_version`:
   ```python
   # Code snippet from app/apis/routes/upload_file.py
   if db_file.index_version == target_version:
       db_file.is_indexed = indexed_success
       db_file.indexing_status = "INDEXED" if indexed_success else "FAILED"
       db.commit()
   else:
       logger.info("Skipping stale background indexing task for file %s", file_id)
   ```

### 5.2 Startup Recovery & Backfill Worker
If the application crashes during background vector indexing, unindexed files are recovered during server startup via a lifespan context manager in [main.py](file:///d:/Personal_Knowledge_Base/backend/main.py):

```python
# Code snippet from app/apis/routes/upload_file.py
async def recover_and_backfill_unindexed_files():
    db = SessionLocal()
    try:
        unindexed_files = (
            db.query(FileMetadata)
            .filter(
                FileMetadata.status == "active",
                (
                    (FileMetadata.indexing_status.in_(["PENDING", "FAILED", "INDEXING"])) &
                    (FileMetadata.retry_count < 3)
                ) | (FileMetadata.is_indexed == False),
            )
            .limit(50)
            .all()
        )
        for db_file in unindexed_files:
            db_file.indexing_status = "INDEXING"
            db.commit()
            await sync_vector_in_background(...)
    finally:
        db.close()
```

### 5.3 Safe Deletion Sequence & Desynchronization Logging
Deleting a document follows a 3-step sequence in `delete_file()` inside [upload_file.py](file:///d:/Personal_Knowledge_Base/backend/app/apis/routes/upload_file.py):

1. **Step 1: Delete S3 Object:** Call `delete_s3_object(s3_key)`. If S3 deletion fails, raise an HTTP 500 error and abort before modifying database records.
2. **Step 2: Delete Qdrant Vector:** Call `delete_file_vector(file_id)` to remove the vector point from Qdrant.
3. **Step 3: Delete MySQL Record:** Remove the row from MySQL and commit. If database deletion fails after S3 object deletion succeeds, log a critical desynchronization alert:
   ```python
   logger.critical(
       "DESYNCHRONIZATION DETECTED: Storage object '%s' was deleted from S3, but database record (id=%s) failed to delete: %s",
       s3_key, fileid, str(exc)
   )
   ```

---

## 6. Configuration & Connection Setup

### 6.1 Environment Variable Mapping
Application configurations are managed in [config.py](file:///d:/Personal_Knowledge_Base/backend/app/core/config.py) using Pydantic Settings, loading from [others/.env](file:///d:/Personal_Knowledge_Base/others/.env):

```python
# Code snippet from app/core/config.py
class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file="../others/.env", extra="ignore")

    AWS_ACCESS_KEY_ID: str
    AWS_SECRET_ACCESS_KEY: str
    AWS_REGION: str = "ap-south-1"
    AWS_ENDPOINT_URL: str | None = None
    S3_BUCKET_NAME: str
    S3_PRESIGNED_URL_EXPIRY: int = 3600
    CORS_ORIGINS: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]
    GEMINI_API_KEY: str | None = None
    QDRANT_HOST: str = "http://localhost:6333"
    QDRANT_COLLECTION_NAME: str = "document_vault"
    VITE_API_URL: str = "http://localhost:8000"
    SECRET_KEY: str
```

### 6.2 Connection Lifecycle & Client Singleton Patterns

#### MySQL Connection Management
SQLAlchemy engine connections are pooled in [database.py](file:///d:/Personal_Knowledge_Base/backend/app/database/database.py). FastAPI endpoints inject database sessions using the `get_db` generator:

```python
# Code snippet from app/database/database.py
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_db():
    database = SessionLocal()
    try:
        yield database
    finally:
        database.close()
```

#### Qdrant Async Client Singleton
`AsyncQdrantClient` is managed using a singleton pattern in [vector_service.py](file:///d:/Personal_Knowledge_Base/backend/app/services/AI/vector_service.py):

```python
# Code snippet from app/services/AI/vector_service.py
_qdrant_client: Optional[AsyncQdrantClient] = None

def get_qdrant_client() -> AsyncQdrantClient:
    global _qdrant_client
    if _qdrant_client is None:
        _qdrant_client = AsyncQdrantClient(url=settings.QDRANT_HOST)
    return _qdrant_client

async def close_qdrant_client() -> None:
    global _qdrant_client
    if _qdrant_client is not None:
        await _qdrant_client.close()
        _qdrant_client = None
```

#### Google GenAI Client Singleton
`genai.Client` instances are lazily initialized using the configured `GEMINI_API_KEY`:

```python
# Code snippet from app/services/AI/vector_service.py
_gemini_client: Optional[genai.Client] = None

def get_gemini_client() -> Optional[genai.Client]:
    global _gemini_client
    if _gemini_client is None and settings.GEMINI_API_KEY:
        _gemini_client = genai.Client(api_key=settings.GEMINI_API_KEY)
    return _gemini_client
```
