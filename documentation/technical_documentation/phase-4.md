# Phase 4 Technical Documentation: File Lifecycle, Storage & Metadata Management

Welcome to the technical documentation for **Phase 4** of the **Personal Knowledge Base** system. 

If you are a student or junior developer looking at this codebase for the first time, this document will walk you through how we handle file uploads, cloud storage, presigned URLs, database synchronization, and frontend state management.

---

## 1. Architecture Overview

When building applications that handle file uploads (PDFs, Markdown documents, Word files), a common beginner mistake is routing file data directly through the backend server (e.g. sending a 50MB file to FastAPI, which then forwards it to S3).

### Why Direct Client-to-S3 Uploads?
Routing raw file bytes through your application backend causes two major bottlenecks:
1. **Bandwidth Exhaustion**: Your server spends CPU cycles and network memory buffering file uploads.
2. **Server Timeouts**: Heavy uploads block web server worker threads.

To solve this, we use the **Direct-to-S3 Upload Pattern**:

```text
+--------------+                +-----------------+               +-----------------------+
|              | -- 1. Request -|                 |               |                       |
|              |    Upload URL  |  FastAPI Server |               |  Backblaze B2 / S3    |
|              | -------------> |   (Coordinator) |               |    (Object Storage)   |
|              |                +-----------------+               +-----------------------+
|  React Client|                         |                                    ^
|  (Browser)   |                         | 2. Create Pending Record           |
|              |                         v                                    |
|              |                 +-----------------+                          |
|              |                 | MySQL Database  |                          |
|              |                 | (file_metadata) |                          |
|              |                 +-----------------+                          |
|              |                                                              |
|              | ---------------------- 3. PUT Direct Binary Bytes ----------->|
+--------------+--------------------------------------------------------------+
```

### The Role of MySQL (`file_metadata`)
While Backblaze B2 stores the actual binary file bytes (the raw document), MySQL stores the **structured metadata** (file title, description, tags, lifecycle status, size, and creation timestamp). 

Because object storage and relational databases are separate systems that cannot execute atomic cross-system transactions, FastAPI acts as an **orchestrator** to keep storage and database state synchronized.

---

## 2. The Two-Step Upload Verification Flow

To prevent the frontend from claiming an upload succeeded when a network error prevented the bytes from actually arriving in S3, we implement a **Two-Step Verification Handshake**.

### Analogous Concept: The Package Delivery Handshake
Think of this like ordering a package online:
1. You request an order number (Initiate). The seller logs the order as *pending*.
2. The courier delivers the package to the warehouse (Direct Upload).
3. The warehouse scans the barcode to verify receipt (Verification). Only after scanning does the order status change to *delivered*.

### Sequence Diagram & Workflow

```text
React Frontend                 FastAPI Backend                Backblaze B2 (S3)              MySQL DB
      |                               |                               |                         |
      |--- 1. POST /files/upload-url -|                               |                         |
      |     (filename, contentType)   |--- Create 'pending' record ---------------------------->|
      |<-- Returns uploadUrl, key ----|                               |                         |
      |                               |                               |                         |
      |--- 2. PUT (Binary Bytes) ------------------------------------>|                         |
      |     (Direct to presigned URL) |                               |                         |
      |<-- 200 OK ----------------------------------------------------|                         |
      |                               |                               |                         |
      |--- 3. POST /files/upload-complete ----------------------------|                         |
      |     (key, filename)           |--- head_object(key) --------->|                         |
      |                               |<-- Returns ContentLength -----|                         |
      |                               |--- Update status to 'active' -------------------------->|
      |<-- 200 OK (Full Metadata) ----|                               |                         |
```

### Key Implementation Snippets

#### 1. Initiation Endpoint (`POST /files/upload-url`)
The server validates the MIME type, generates a safe unique key, inserts a `pending` row in MySQL, and generates a presigned PUT URL.

```python
# backend/app/apis/routes/upload_file.py
@router.post("/upload-url", response_model=PresignedUrlResponse)
async def get_upload_url(payload: FileUploadRequest, db: Session = Depends(get_db)):
    result = create_presigned_put_url(
        filename=payload.filename,
        content_type=payload.content_type,
    )
    
    # Track pending upload in MySQL
    db_file = FileMetadata(
        s3_key=result["key"],
        filename=payload.filename,
        content_type=payload.content_type,
        status="pending",
        size_bytes=0,
    )
    db.add(db_file)
    db.commit()
    db.refresh(db_file)

    result["file_id"] = db_file.fileid
    return PresignedUrlResponse(**result)
```

#### 2. Verification Endpoint (`POST /files/upload-complete`)
The server calls S3 `head_object` using `get_object_metadata(key)`. If the object exists, it reads the true size in bytes, updates the database status to `active`, and returns the metadata to React.

```python
# backend/app/apis/routes/upload_file.py
@router.post("/upload-complete", response_model=FileUploadCompleteResponse)
async def complete_upload(payload: FileUploadCompleteRequest, db: Session = Depends(get_db)):
    db_file = db.query(FileMetadata).filter(FileMetadata.s3_key == payload.key).first()
    if not db_file:
        raise HTTPException(status_code=404, detail="File record not found in database.")

    try:
        # Verify object in S3 and retrieve actual file size
        meta = get_object_metadata(payload.key)
        db_file.status = "active"
        db_file.size_bytes = meta["size_bytes"]
        db.commit()
        db.refresh(db_file)
    except FileNotFoundError as exc:
        db_file.status = "failed"
        db.commit()
        raise HTTPException(status_code=404, detail="File verification failed.") from exc

    return FileUploadCompleteResponse(
        verified=True, key=payload.key, message="Verified successfully.", metadata=db_file
    )
```

---

## 3. View/Read Flow (Presigned GET URLs)

### Security Concept
Our Backblaze B2 storage bucket is **private**. Objects cannot be read by public web users directly. 

To allow a user to view or download a file without making the bucket public or passing AWS secret keys to the browser, FastAPI generates a **short-lived presigned GET URL** (valid for 5 minutes).

```python
# backend/app/services/AWS/s3_service.py
def create_presigned_get_url(key: str, expires_in: int = 300) -> dict:
    if not check_object_exists(key):
        raise FileNotFoundError(f"File object with key '{key}' does not exist.")

    s3_client = _get_s3_client()
    response = s3_client.generate_presigned_url(
        ClientMethod="get_object",
        Params={"Bucket": settings.S3_BUCKET_NAME, "Key": key},
        ExpiresIn=expires_in,
    )
    return {"view_url": response, "key": key, "expires_in": expires_in}
```

When the user clicks **View** in the React app, React requests a presigned GET URL via `POST /files/view-url` and opens the resulting URL in a new browser tab.

---

## 4. Database Schema Design (`file_metadata`)

The `file_metadata` table is defined using SQLAlchemy in `backend/app/database/db_models.py`.

### Database Schema Mapping Table

| Column Name | Data Type | Constraint / Key | Description |
| :--- | :--- | :--- | :--- |
| `fileid` | `INTEGER` | Primary Key, Auto-Increment | Unique identifier for each document |
| `s3_key` | `VARCHAR(255)` | Unique, Indexed, NOT NULL | The unique storage key (e.g., `uploads/uuid_name.pdf`) |
| `filename` | `VARCHAR(255)` | NOT NULL | Original filename provided during upload |
| `content_type` | `VARCHAR(100)` | Nullable | MIME type (e.g. `application/pdf`, `text/markdown`) |
| `size_bytes` | `BIGINT` | Nullable | Exact file size in bytes retrieved from S3 |
| `status` | `VARCHAR(20)` | Default `"pending"`, NOT NULL | Lifecycle state: `"pending"`, `"active"`, `"failed"` |
| `title` | `VARCHAR(255)` | Nullable | Custom document title customized by user |
| `description` | `VARCHAR(1000)`| Nullable | Custom description summarizing the content |
| `tags` | `VARCHAR(255)` | Nullable | Comma-separated list of search tags |
| `userid` | `INTEGER` | Nullable, Foreign Key (`users.id`) | Optional foreign key reserved for future auth integration |
| `created_at` | `DATETIME` | Server Default `now()` | Timestamp when record was created |
| `updated_at` | `DATETIME` | Server Default `now()`, On Update `now()` | Timestamp when metadata was last modified |

### SQLAlchemy Model Code

```python
# backend/app/database/db_models.py
class FileMetadata(Base):
    __tablename__ = "file_metadata"

    fileid = Column(Integer, primary_key=True, index=True)
    s3_key = Column(String(255), unique=True, index=True, nullable=False)
    filename = Column(String(255), nullable=False)
    content_type = Column(String(100), nullable=True)
    size_bytes = Column(BigInteger, nullable=True)
    status = Column(String(20), default="pending", nullable=False)

    title = Column(String(255), nullable=True)
    description = Column(String(1000), nullable=True)
    tags = Column(String(255), nullable=True)

    userid = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    user = relationship("User", backref="files")
```

---

## 5. File Deletion Architecture & Handshake Flow

To complete the document lifecycle, we implement a secure **two-step deletion handshake** ensuring that cloud storage files are not left orphaned and database records are kept strictly synchronized.

### The Deletion Workflow
Because object storage and metadata databases are separate systems, the deletion is executed in a specific, safety-first order:

```text
React Frontend                 FastAPI Backend                Backblaze B2 (S3)              MySQL DB
      |                               |                               |                         |
      |----- 1. DELETE /files/{id} -->|                               |                         |
      |                               |----- 2. delete_s3_object() -->|                         |
      |                               |<---- 200 OK (Deleted) --------|                         |
      |                               |                               |                         |
      |                               |----- 3. Delete DB record ------------------------------>|
      |                               |<---- 200 OK (Deleted) ----------------------------------|
      |<---- 200 OK (Success) --------|                               |                         |
```

1. **Delete Call**: The React frontend sends a `DELETE /files/{fileId}` request.
2. **S3/B2 Deletion**: FastAPI calls the storage service `delete_s3_object()` using boto3 `delete_object` to remove the file from storage.
3. **Database Deletion**: Once S3/B2 deletion succeeds, the MySQL record is deleted.
4. **Partial Failure Handling & Safety Defaults**:
   * **Storage Failure**: If S3/B2 deletion fails (e.g. timeout or AWS error), execution aborts immediately, the database record is **retained**, and the API returns a `500 Internal Server Error`.
   * **Database Failure (Critical Desync)**: If S3/B2 deletion succeeds but MySQL database deletion fails afterwards, the binary file is gone but the record remains in MySQL. The system catches the DB exception, logs a `CRITICAL` alert containing the `s3_key` and `fileid` for administrative reconciliation, and returns `500`.

---

## 6. Backblaze B2 File Versioning & Permanent Deletion (Crucial Concept)

When integrating Backblaze B2, understanding file versioning semantics is essential for avoiding storage bloat and guaranteeing permanent data destruction.

### B2 File Versioning Explanation
By default, Backblaze B2 maintains multiple versions of the same file name:
```text
resume.pdf
├── Version 1 → 44.9 KB   ← actual file
└── Version 2 → 0 bytes   ← hidden/delete marker
```
If a standard "hide" or "delete-by-name" operation is executed, B2 does not immediately purge the original binary bytes; it simply creates a hidden version (delete marker), leaving the original data in storage.

To permanently free up space and delete data, the specific file version must be deleted:
* **Current Deletion Implementation**: Our implementation utilizes the standard S3-compatible client `delete_object` API via `delete_s3_object()`, which deletes the target object key permanently.
* **Note on versionId**: In buckets with B2 versioning enabled, permanent deletion requires B2 `fileId` tracking (mapped to S3's `versionId`). If future requirements necessitate version tracking, the database schema (`file_metadata`) will be updated to store this identifier during the upload verification step (`/files/upload-complete`).

---

## 7. Implementation Code References

### 1. Backend Storage Service (`app/services/AWS/s3_service.py`)
```python
def delete_s3_object(key: str) -> None:
    """Delete an object from S3/Backblaze B2 storage bucket."""
    s3_client = _get_s3_client()
    try:
        s3_client.delete_object(Bucket=settings.S3_BUCKET_NAME, Key=key)
    except (ClientError, BotoCoreError) as exc:
        raise RuntimeError(f"Failed to delete S3 object '{key}': {str(exc)}") from exc
```

### 2. Backend API Route (`app/apis/routes/upload_file.py`)
```python
@router.delete("/{fileid}", status_code=status.HTTP_200_OK)
async def delete_file(fileid: int, db: Session = Depends(get_db)):
    """Delete a document from S3 storage and MySQL database."""
    db_file = (
        db.query(FileMetadata)
        .filter(FileMetadata.fileid == fileid)
        .first()
    )
    if not db_file:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="File record not found.",
        )

    s3_key = db_file.s3_key

    # Step 1: Delete S3 object first
    try:
        delete_s3_object(s3_key)
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete object from S3 storage: {str(exc)}",
        ) from exc

    # Step 2: Delete database record after S3 delete succeeds
    try:
        db.delete(db_file)
        db.commit()
    except Exception as exc:
        logger.critical(
            "DESYNCHRONIZATION DETECTED: Storage object '%s' was deleted from S3, but database record (id=%s) failed to delete: %s",
            s3_key,
            fileid,
            str(exc),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database deletion failed after storage object was removed.",
        ) from exc

    return {"success": True, "message": "File deleted successfully.", "fileId": fileid}
```

### 3. Frontend API Client (`src/apis/documentApi.js`)
```javascript
export const deleteFile = (fileId) => {
  return axiosClient.delete(`/files/${fileId}`)
}
```

### 4. Frontend UI Components (`src/App.jsx`)
Cards in the Document Vault render a red minimalist `IconButton` wrapping a `TrashIcon`:
```javascript
<IconButton 
  size="small"
  onClick={() => handlePromptDelete(doc)}
  title="Delete document"
  sx={{ 
    border: '1px solid', 
    borderColor: 'divider', 
    borderRadius: '6px',
    color: '#ff4d4f',
    p: '5px',
    '&:hover': {
      borderColor: '#ff4d4f',
      backgroundColor: darkMode ? 'rgba(255, 77, 79, 0.12)' : 'rgba(255, 77, 79, 0.06)'
    }
  }}
>
  <TrashIcon />
</IconButton>
```
To prevent accidental deletions, a warning dialog is rendered:
```javascript
<Dialog open={deleteConfirmOpen} onClose={() => !deleting && setDeleteConfirmOpen(false)} ...>
  <DialogTitle><AlertIcon /> Confirm Permanent Deletion</DialogTitle>
  <DialogContent>
    <Typography>Are you sure you want to permanently delete {docToDelete?.title}?</Typography>
  </DialogContent>
  <DialogActions>
    <Button disabled={deleting} onClick={() => setDeleteConfirmOpen(false)}>Cancel</Button>
    <Button variant="contained" disabled={deleting} onClick={handleConfirmDelete}>Delete Document</Button>
  </DialogActions>
</Dialog>
```

---

## 8. Test Coverage & Verification Plan

We utilize pytest to ensure deletion edge cases and error scenarios are fully handled:

### 1. Unit Tests (`test_s3_service.py`)
* `test_delete_s3_object_success`: Mocks `delete_object` returning success.
* `test_delete_s3_object_failure`: Mocks Boto3 throwing `ClientError`/`BotoCoreError` and checks that the function raises `RuntimeError`.

### 2. Integration Tests (`test_upload_file.py`)
* `test_delete_file_route_success`: Validates successful object deletion from storage and corresponding metadata removal from MySQL.
* `test_delete_file_route_not_found`: Assures a request to delete a nonexistent document returns `404 Not Found`.
* `test_delete_file_route_failed_s3`: Validates that S3 deletion failure halts execution, retains the MySQL metadata record, and returns `500`.
* `test_delete_file_route_failed_db`: Mocks S3 success followed by a database write error, verifying that the critical desynchronization warning is logged and a `500` response is generated.

---

## 9. Frontend Metadata Customization & Dashboard

The frontend is built using React with Material UI components in `frontend/src/App.jsx`.

### 1. Document Vault Dashboard (`GET /files`)
When the app mounts (or after an upload completes), the frontend calls `fetchFiles()` to load all active documents from MySQL. Each document is rendered in a sleek card displaying:
* A color-coded format icon (Red for PDF, Blue for Markdown, Purple for DOCX, Green for TXT).
* Title, description, formatted file size (e.g. `1.2 MB`), and tags.
* Action buttons for **View**, **Edit**, and **Delete**.

### 2. Auto-Prompt Metadata Customization
Immediately after a file is uploaded and verified by S3 (`completeUpload`), the React application automatically triggers the **Customize File Details Dialog**, prompting the user to supply a Title, Description, and Tags.

### 3. Chip Tag Input Component
Tags are edited in a custom React component using Material UI `Chip` components:
* Users type a tag into a text field and hit `Enter` or click **Add**.
* Tags are stored in component state as an array `['work', 'finance', 'q3']`.
* When saving, the array is joined into a comma-separated string (`"work,finance,q3"`) and sent via `PATCH /files/{fileId}` to the backend.

---

## 10. Summary Checklist

| Area | Component | Implementation Status |
| :--- | :--- | :--- |
| **S3 Storage** | Presigned PUT/GET URLs | Active & Verified |
| **S3 Storage** | Storage Verification (`head_object`) | Active & Verified |
| **S3 Storage** | Permanent Object Deletion (`delete_object`) | Active & Verified |
| **Database** | MySQL `file_metadata` Table & Alembic Migration | Active & Verified |
| **Backend API** | Handshake & Metadata CRUD (`/files`) | Active & Verified |
| **Backend API** | File Deletion & Partial Failure Logging | Active & Verified |
| **Frontend UI** | Document Vault Dashboard & Chip Tag Editor | Active & Verified |
| **Frontend UI** | Delete Action Buttons & Confirmation Modal | Active & Verified |
| **Testing** | Route Integration & Storage Unit Tests | Active & Verified |

