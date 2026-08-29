# Phase B: Integrating AI Semantic Search with MySQL & Qdrant

Welcome to the design spec and implementation plan for **Phase B**. 

In **Phase A**, we played around with scripts to understand how embeddings (coordinates) and Qdrant (the coordinate map database) work in isolation. In this phase, we are going to wire these two technologies directly into our active FastAPI backend, database models, and upload routes.

By the end of this phase, whenever a user completes a file upload or updates a file's tags/description, our app will automatically generate vector coordinates using Gemini and index them in Qdrant—completely isolated per user.

---

## 🗺️ High-Level Request Flow

When you search for something in your vault, this is the round-trip that happens:

```text
               1. GET /files/search?q="cloud servers"
   Client (React) ───────────────────────────────────► FastAPI Backend
                                                          │
                                                          │ 2. Call Gemini API
                                                          │    (Generate search vector)
                                                          ▼
                                                   Google GenAI Service
                                                          │
                                                          │ 3. Return Float Vector (768d)
                                                          ▼
                                                   FastAPI Backend
                                                          │
                                                          │ 4. Query Qdrant with Filter:
                                                          │    - Match similarity
                                                          │    - Strict condition: user_id == current_user.id
                                                          ▼
                                                   Qdrant Vector DB
                                                          │
                                                          │ 5. Return matched Point IDs (file_ids)
                                                          ▼
                                                   FastAPI Backend
                                                          │
                                                          │ 6. SELECT * FROM file_metadata
                                                          │    WHERE fileid IN (...) AND userid = current_user.id
                                                          ▼
               7. Sorted List of Metadata rows     MySQL Database
   Client (React) ◄───────────────────────────────────┘
```

---

## 🛠️ Step 1: Environment & Client Configurations

To connect to Gemini and Qdrant, our FastAPI backend needs credentials and configuration settings.

### 1. Update the Environment Configurations
Ensure your local `others/.env` file contains the required endpoints:
```env
GEMINI_API_KEY="your-google-studio-api-key"
QDRANT_HOST="http://localhost:6333"
```

Configure these settings inside `backend/app/core/config.py` using Pydantic Settings:
```python
class Settings(BaseSettings):
    # Existing settings...
    GEMINI_API_KEY: str
    QDRANT_HOST: str = "http://localhost:6333"
```

### 2. Configure Shared Async Clients
Create clients inside `backend/app/services/AI/` or direct helper classes to initialize the services asynchronously:

* **Qdrant Client Setup**:
  ```python
  from qdrant_client import AsyncQdrantClient
  
  # Singleton async client to share connection pool across requests
  qdrant_client = AsyncQdrantClient(url=settings.QDRANT_HOST)
  ```

* **Google GenAI Client Setup**:
  ```python
  from google import genai
  
  # Modern GenAI client wrapper
  gemini_client = genai.Client(api_key=settings.GEMINI_API_KEY)
  ```

---

## 🗄️ Step 2: Database Model Expansion (`is_indexed`)

We need a way to track if a file was successfully added to Qdrant. If the Gemini API goes down or Qdrant fails, we want the file to still exist in MySQL, but have a flag telling us it needs indexing later.

### 1. Update `db_models.py`
Add the `is_indexed` column to the `FileMetadata` class:
```python
# app/database/db_models.py
class FileMetadata(Base):
    __tablename__ = "file_metadata"
    
    fileid: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    userid: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    # ... existing fields ...
    
    # NEW: Track indexing status (defaults to False on creation)
    is_indexed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
```

### 2. Generate and Apply Database Migration
Generate a new Alembic migration script to apply the changes to your MySQL database:
```bash
alembic revision --autogenerate -m "add_is_indexed_to_files"
alembic upgrade head
```

---

## ⚙️ Step 3: Wire Sync Logic to CRUD Endpoints

We will modify the endpoints in `backend/app/apis/routes/upload_file.py` to synchronize vector coordinates automatically.

### Helper: Text Representation Builder
Before embedding, we compile the fields into a readable paragraph. This is what the AI "reads" to understand the file:
```python
def build_file_text_representation(filename: str, title: str | None, description: str | None, tags: str | None) -> str:
    parts = [
        f"Filename: {filename}",
        f"Title: {title or 'Untitled'}",
        f"Description: {description or 'No description provided.'}",
        f"Tags: {tags or ''}"
    ]
    return "\n".join(parts)
```

---

### 1. Hooking into File Activation (`POST /files/upload-complete`)
When a file is uploaded to S3, the client hits this route. Once storage is verified:
1. Compile the text representation.
2. Request the vector coordinates from Gemini asynchronously.
3. Upsert the point (Point ID = `fileid`) into the `document_vault` Qdrant collection containing the vector and a payload (`file_id`, `user_id`, `filename`, etc.).
4. If successful, set `is_indexed = True` in MySQL.

```python
# Inside upload_complete()
# 1. Standard storage verification succeeds...
db_file.status = "active"

# 2. Build text and get vector coordinates
try:
    text_content = build_file_text_representation(
        filename=db_file.filename,
        title=db_file.title,
        description=db_file.description,
        tags=db_file.tags
    )
    
    response = await gemini_client.aio.models.embed_content(
        model="gemini-embedding-2",
        contents=text_content,
        config=types.EmbedContentConfig(output_dimensionality=768)
    )
    vector = response.embeddings[0].values

    # 3. Upsert to Qdrant Async
    await qdrant_client.upsert(
        collection_name="document_vault",
        points=[
            PointStruct(
                id=db_file.fileid,
                vector=vector,
                payload={
                    "file_id": db_file.fileid,
                    "user_id": current_user.id,
                    "filename": db_file.filename,
                    "title": db_file.title,
                    "tags": db_file.tags,
                    "description": db_file.description
                }
            )
        ]
    )
    db_file.is_indexed = True
except Exception as exc:
    logger.error(f"Indexing failed for file {db_file.fileid}: {str(exc)}")
    # We do NOT fail the upload. The file remains active, but is_indexed = False
    db_file.is_indexed = False

db.commit()
```

---

### 2. Hooking into Metadata Updates (`PATCH /files/{fileid}`)
If the user edits the description or tags, the coordinates become outdated (stale). We must recalculate:

```python
# Inside update_metadata()
# 1. Update MySQL columns...
db_file.title = payload.title
# ... update descriptions/tags ...
db.commit()

# 2. Re-embed and update Qdrant point
try:
    text_content = build_file_text_representation(...)
    response = await gemini_client.aio.models.embed_content(...)
    vector = response.embeddings[0].values
    
    # Qdrant upsert automatically overwrites the point with matching ID
    await qdrant_client.upsert(
        collection_name="document_vault",
        points=[
            PointStruct(
                id=db_file.fileid,
                vector=vector,
                payload={ ... updated payload ... }
            )
        ]
    )
    db_file.is_indexed = True
except Exception as exc:
    logger.error(f"Re-indexing failed: {str(exc)}")
    db_file.is_indexed = False

db.commit()
```

---

### 3. Hooking into Deletions (`DELETE /files/{fileid}`)
When a file is deleted from S3 and MySQL, we must also clean up the vector database so we don't query dead pointers:

```python
# Inside delete_file()
# 1. Delete S3 object...
# 2. Delete Qdrant Vector point asynchronously
try:
    await qdrant_client.delete(
        collection_name="document_vault",
        points_selector=[fileid]
    )
except Exception as exc:
    # Log this warning. An admin script can reconcile this later if it remains an orphan.
    logger.warning(f"Failed to delete Qdrant point {fileid}: {str(exc)}")

# 3. Delete MySQL row
db.delete(db_file)
db.commit()
```

---

## 🔍 Step 4: Implementing the Search Endpoint (`GET /files/search`)

Create a brand new route `/files/search?q={query_string}` inside `upload_file.py`:

```python
@router.get("/search", response_model=list[FileMetadataSchema])
async def semantic_search(
    q: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    if not q.strip():
        # Fallback: if query is empty, return standard list
        return await list_files(current_user, db)
        
    # Step 1: Generate Embedding Vector for the Search Term
    try:
        response = await gemini_client.aio.models.embed_content(
            model="gemini-embedding-2",
            contents=q,
            config=types.EmbedContentConfig(output_dimensionality=768)
        )
        query_vector = response.embeddings[0].values
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"AI Service is unavailable: {str(exc)}"
        )

    # Step 2: Query Qdrant with Strict User Isolation Pre-filtering
    try:
        hits = await qdrant_client.query_points(
            collection_name="document_vault",
            query=query_vector,
            query_filter=Filter(
                must=[
                    FieldCondition(
                        key="user_id",
                        match=MatchValue(value=current_user.id)
                    )
                ]
            ),
            limit=15
        )
    except Exception as exc:
         raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Vector index query failed: {str(exc)}"
        )

    # Extract point IDs
    matched_ids = [hit.id for hit in hits.points]
    if not matched_ids:
        return []

    # Step 3: Fetch Authoritative Rows in a single query from MySQL
    # Crucial: Enforce userid filter on the SQL side as well to double-check security
    files = (
        db.query(FileMetadata)
        .filter(
            FileMetadata.fileid.in_(matched_ids),
            FileMetadata.userid == current_user.id,
            FileMetadata.status == "active"
        )
        .all()
    )

    # Sort results to match the similarity order returned by Qdrant
    id_to_file = {f.fileid: f for f in files}
    sorted_files = [id_to_file[fid] for fid in matched_ids if fid in id_to_file]
    
    return sorted_files
```

---

## 🧪 Verification & Student Checkpoints

To ensure your code works correctly, follow these checkpoints during implementation:

1. **Verify Alembic**: Run `desc file_metadata;` in MySQL database terminal and check that the `is_indexed` column exists with default `0` (or `false`).
2. **Double check Qdrant Logs**: When uploading a new file, check your terminal logs to confirm the `qdrant_client.upsert` function executes without connection issues.
3. **Verify the Multi-Tenant Pre-Filter**:
   * Create two separate test accounts (e.g. User 1 and User 2).
   * Upload files to User 1's vault.
   * Log in as User 2 and hit `/files/search?q=...`.
   * Assert that User 2's search returns **empty results**, guaranteeing User 1's files are secure.
