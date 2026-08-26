# Phase 4 Project Plan: File Lifecycle & Metadata Management

Welcome to Phase 4! In this phase, we will implement complete **CRUD (Create, Read, Update, Delete) operations** for our files and manage custom metadata stored in our MySQL database. We are focusing purely on file lifecycle operations, deferring authentication and user ownership checks to a later phase.

---

## 1. Executive Summary & Objective

The objective of Phase 4 is to build a robust document management dashboard. 
* **The Goal**: Allow users to view uploaded files, edit metadata (titles, descriptions, tags), open files securely, and delete files.
* **The Architecture**: FastAPI coordinates operations between Backblaze B2 (object storage) and MySQL (metadata database).
* **The Constraint**: S3/B2 and MySQL are separate systems and cannot participate in atomic transactions. FastAPI will act as the coordinator, managing partial failures and reporting inconsistencies.

---

## 2. Core Workflows & Concepts

### A. Two-Step Upload Verification Flow
To prevent the frontend from claiming an upload succeeded when no file was actually stored, we implement a two-step handshake:
1. **Initiate (`POST /files/upload-url`)**: React requests an upload URL. FastAPI creates a database record with a `pending` status, generates a presigned PUT URL, and returns both to React.
2. **Direct Upload**: React uploads the file bytes directly to Backblaze B2 using the presigned URL.
3. **Complete (`POST /files/upload-complete`)**: React notifies FastAPI that the upload is finished. FastAPI calls B2 (`head_object`) to **verify the file actually exists** in storage. If verified, the database status changes to `active`. If it does not exist, the status is set to `failed`.

### B. High-Performance View/Read Flow
To keep the backend server fast and avoid bottlenecking bandwidth:
1. React requests a download link from FastAPI.
2. FastAPI generates a short-lived **presigned GET URL** (e.g. 2-minute expiry) and returns it.
3. The browser downloads/views the file bytes directly from Backblaze B2.

### C. Deletion & Versioning Strategy
1. React makes a single `DELETE /files/{id}` call to FastAPI.
2. FastAPI deletes the object from Backblaze B2 according to the project's chosen B2 versioning/deletion policy. If the B2 deletion succeeds, FastAPI deletes the metadata record from MySQL.
   * *Note:* Before implementing permanent deletion, verify Backblaze B2's current S3-compatible versioning/delete semantics and configure the desired cleanup policy.
3. **Partial Failure Handling**: If B2 deletion succeeds but MySQL deletion fails, FastAPI will log a critical error indicating the database-storage desynchronization, which can be picked up by administrators or reconciliation scripts.

---

## 3. Database Schema Design (MySQL)

We will define the `file_metadata` table using SQLAlchemy. We will keep tags simple as a comma-separated string for this phase and postpone user ownership fields until authentication is built.

| Column Name | Data Type | Key / Index | Description |
| :--- | :--- | :--- | :--- |
| `fileid` | `Integer` | Primary Key | Unique auto-incrementing ID |
| `s3_key` | `String(255)` | Unique, Indexed | The S3 object key (e.g., `uploads/uuid_name.pdf`) |
| `filename` | `String(255)` | None | The original name of the file |
| `content_type` | `String(100)` | None | MIME type (e.g., `application/pdf`) |
| `size_bytes` | `BIGINT` | None | File size in bytes (uses `BIGINT` for large files) |
| `status` | `String(20)` | None | Lifecycle state: `pending`, `active`, `failed` |
| `title` | `String(255)` | None | Custom title given by the user |
| `description` | `String(1000)`| None | Custom description of the file |
| `tags` | `String(255)` | None | Comma-separated search tags |
| `created_at` | `DateTime` | None | Date and time uploaded |
| `updated_at` | `DateTime` | None | Date and time last updated |

---

## 4. Step-by-Step Implementation Roadmap

### Step 1: Database Model & Alembic Migration
1. Define the `Document` model in `backend/app/database/db_models.py` with the `status` column and `BIGINT` for `size_bytes`.
2. Generate and apply the migration:
   ```powershell
   cd backend
   alembic revision --autogenerate -m "create_documents_table"
   alembic upgrade head
   ```

### Step 2: Backend S3 & Router API Implementation
1. Add `delete_s3_object(key)` and `check_object_exists(key)` functions in `backend/app/services/AWS/s3_service.py`.
2. Create `backend/app/apis/routes/documents.py` to define:
   * `POST /files/upload-url`: Creates a `pending` row and returns the presigned PUT URL.
   * `POST /files/upload-complete`: Verifies S3 file existence and updates status to `active` or `failed`.
   * `GET /files`: Lists all `active` files and metadata.
   * `GET /files/{id}/view`: Generates a short-lived presigned GET URL.
   * `PATCH /files/{id}`: Updates custom metadata (`title`, `description`, `tags`) in MySQL.
   * `DELETE /files/{id}`: Deletes B2 object, then deletes MySQL record. If S3 fails, returns `500`. If S3 succeeds but MySQL fails, logs critical desync error.
3. Include the router in `backend/main.py`.

### Step 3: Frontend Client & Dashboard UI
1. Implement client API calls in `frontend/src/apis/documentApi.js`.
2. Update `frontend/src/App.jsx` to build the document list dashboard, metadata editing modals, and action triggers.

---

## 5. Verification & Testing Plan

### Automated Testing Scope
To ensure production readiness, we will write tests that explicitly cover edge cases and failure modes:

* **Success Cases**:
  * Complete lifecycle test (Create -> Upload -> Confirm -> Read -> Update -> Delete).
* **Failure & Edge Cases**:
  * **Failed S3 Deletion**: Verify the API returns `500` and does *not* delete the MySQL record if the S3 delete call fails.
  * **Failed MySQL Deletion**: Mock database failures and verify critical warning logs are raised when B2 delete succeeds but DB delete fails.
  * **Missing B2 Object**: Verify `upload-complete` sets database status to `failed` if React claims upload succeeded but B2 does not contain the file.
  * **Invalid/Expired URLs**: Test that S3 denies access if the client attempts to use an expired presigned GET/PUT URL.
  * **Nonexistent Document IDs**: Verify that requests to view, update, or delete a document ID that does not exist return a proper `404 Not Found` response.

### Manual Verification
1. Test uploads, edit metadata, open links, and delete files via the UI. Verify DB and Backblaze states at each step.
