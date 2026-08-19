# AI Personal Knowledge Base — Production-Ready Technical Project Plan

**Project type:** Personal knowledge base / AI file workspace  
**Primary backend:** FastAPI + Python  
**Storage:** AWS S3  
**Relational database:** MySQL  
**LLM:** Google Gemini API  
**Frontend:** React + Material UI (optional)  
**Authentication:** Already implemented  
**Future vector database:** Qdrant  
**Future integrations:** Google Drive, GitHub, connector/plugin architecture  
**Future AI:** RAG, MCP, agents

---

## 1. Executive Summary

Build a personal knowledge-base application where an authenticated user can upload files directly from the browser to AWS S3, maintain custom metadata in MySQL, perform file CRUD operations, and generate AI summaries with Gemini.

The architecture must intentionally avoid becoming a Google Drive clone. AWS S3 is the file storage layer; the application owns metadata, permissions, AI processing state, and the user experience.

The system must also be designed so that later versions can add:

1. **V2 — semantic search:** document extraction, chunking, embeddings, Qdrant, metadata filtering.
2. **V3 — external connectors:** Google Drive, GitHub repositories, and a connector abstraction.
3. **V4 — RAG:** retrieve content from S3 and connected sources and answer questions with citations.
4. **V5 — MCP/agents:** expose knowledge-base operations as tools and allow an agent to orchestrate searches, document reads, summaries, comparisons, and other workflows.

### Core architectural principle

Separate these responsibilities:

```text
S3                -> binary file storage
MySQL             -> application state + file metadata
FastAPI            -> business logic + API
AI service         -> Gemini calls + prompt management
Future Qdrant      -> vectors/chunks for semantic retrieval
Future connectors  -> Google Drive / GitHub / other sources
Frontend           -> user experience
```

Do not store vector embeddings, large document content, or raw files in MySQL.

---

# 2. Product Scope

## 2.1 V1 — AI File Workspace

### Required features

- Authenticated user access
- Upload a file to S3 using a presigned upload URL
- Create a metadata record in MySQL
- List the current user's files
- Get a file's metadata
- Update editable metadata
- Delete a file
- Generate a temporary download URL
- Generate an AI summary using Gemini
- Store the resulting summary and AI-processing status
- Basic file search/filtering by MySQL metadata
- API validation, authentication, authorization, error handling, logging, tests

### User-customizable metadata

Minimum fields:

- `title`
- `label`
- `description`

Recommended additional fields:

- `folder`
- `is_favorite`
- `created_at`
- `updated_at`

The application should distinguish between:

1. **User metadata** — title, label, description, etc.
2. **System metadata** — S3 key, MIME type, size, checksum, processing state, timestamps.

Users should not be allowed to change system-owned storage fields directly.

---

# 3. Version Roadmap

| Version | Scope | Main technical learning |
|---|---|---|
| V1 | S3 + MySQL + Gemini summarizer | Backend architecture, S3, CRUD, LLM |
| V2 | Semantic search + Qdrant | Embeddings, chunking, vector search |
| V3 | Google Drive + GitHub connectors | OAuth, external APIs, adapter design |
| V4 | RAG + citations | Retrieval, grounding, context assembly |
| V5 | MCP + agents | Tool design, orchestration, agent workflows |

### V1 definition of done

A user can:

```text
Login
  -> Upload file
  -> File goes directly to S3
  -> Metadata saved in MySQL
  -> View files
  -> Edit title/label/description
  -> Download file
  -> Delete file
  -> Click "Summarize"
  -> Backend reads the file
  -> Gemini summarizes it
  -> Summary is saved and displayed
```

---

# 4. High-Level Architecture

## 4.1 V1 logical architecture

```text
                         ┌──────────────────┐
                         │   React + MUI    │
                         │    (optional)    │
                         └────────┬─────────┘
                                  │ HTTPS / REST
                                  ▼
                         ┌──────────────────┐
                         │     FastAPI      │
                         │      API         │
                         └────────┬─────────┘
                                  │
                ┌─────────────────┼─────────────────┐
                │                 │                 │
                ▼                 ▼                 ▼
        ┌──────────────┐  ┌──────────────┐  ┌──────────────┐
        │    MySQL     │  │   S3 Service │  │  Gemini API  │
        │ metadata     │  │ file storage │  │  summarizer  │
        └──────────────┘  └──────────────┘  └──────────────┘
```

## 4.2 V1 upload architecture

Do not send large files through FastAPI unless there is a specific reason.

Preferred flow:

```text
Browser
   |
   | 1. POST /files/upload-url
   v
FastAPI
   |
   | 2. Validate metadata + create pending record
   | 3. Create S3 presigned PUT URL
   v
Browser
   |
   | 4. PUT file directly to S3
   v
S3
   |
   | 5. Upload completes
   v
Browser
   |
   | 6. POST /files/{id}/complete
   v
FastAPI
   |
   | 7. Verify object exists / size where appropriate
   | 8. Mark file READY
   v
MySQL
```

AWS documents presigned URLs as a mechanism for temporary access to S3 objects and supports presigned uploads, which fits this architecture.

---

# 5. Why Direct-to-S3 Upload

Avoid this for normal uploads:

```text
Browser -> FastAPI -> FastAPI memory/disk -> S3
```

Prefer:

```text
Browser -> FastAPI (authorization only)
Browser -> S3 (actual bytes)
```

Benefits:

- Lower FastAPI memory pressure
- Better support for large files
- Less API-server bandwidth consumption
- Cleaner separation between application and storage
- Easier scaling

FastAPI should authorize the upload and issue a short-lived presigned URL. The browser then uploads directly to S3.

Use:

- Short expiration
- Fixed object key
- Content-Type constraints
- Maximum expected size
- Private S3 bucket
- No public bucket objects

---

# 6. S3 Storage Design

## 6.1 Bucket

Use one private bucket for the application, for example:

```text
myapp-production-files
```

Do not create one bucket per user.

## 6.2 Object key strategy

Do not use:

```text
john/resume.pdf
```

because filenames and user-editable metadata are mutable.

Prefer stable IDs:

```text
users/{user_id}/files/{file_id}/original/{safe_filename}
```

Example:

```text
users/98a.../files/7bd.../original/resume.pdf
```

Use `file_id` as the stable application identity.

If later adding derived artifacts:

```text
users/{user_id}/files/{file_id}/original/{filename}
users/{user_id}/files/{file_id}/extracted/content.txt
users/{user_id}/files/{file_id}/preview/...
```

Do not expose internal S3 keys as the public identifier of a file.

## 6.3 S3 object properties

Store private objects with:

- Content-Type
- Content-Length
- Optional ETag/checksum where useful
- Server-side encryption
- Application object key

The canonical metadata still lives in MySQL.

---

# 7. Database Design

## 7.1 Existing authentication table

Authentication already exists.

Do not create a duplicate authentication system.

Assume an existing:

```text
users
-----
id (PK)
...
```

Your file table references `users.id`.

If the existing table uses a different name or UUID type, adapt foreign keys to the existing identity model.

---

## 7.2 `files` table

Recommended production-oriented schema:

```sql
CREATE TABLE files (
    id                CHAR(36) PRIMARY KEY,
    user_id           CHAR(36) NOT NULL,

    -- User editable metadata
    title             VARCHAR(255) NOT NULL,
    label             VARCHAR(100) NULL,
    description       TEXT NULL,

    -- Original file information
    original_filename VARCHAR(255) NOT NULL,
    mime_type         VARCHAR(150) NOT NULL,
    file_size_bytes   BIGINT UNSIGNED NOT NULL,

    -- Storage information
    storage_provider  VARCHAR(30) NOT NULL DEFAULT 's3',
    bucket_name       VARCHAR(255) NOT NULL,
    object_key        VARCHAR(1024) NOT NULL,

    -- Processing lifecycle
    status            VARCHAR(30) NOT NULL DEFAULT 'PENDING',
    summary_status    VARCHAR(30) NOT NULL DEFAULT 'NOT_STARTED',
    summary           LONGTEXT NULL,
    summary_model     VARCHAR(100) NULL,
    summary_generated_at DATETIME NULL,

    -- Integrity / synchronization metadata
    checksum          VARCHAR(255) NULL,

    -- Timestamps
    created_at        DATETIME NOT NULL,
    updated_at        DATETIME NOT NULL,
    deleted_at        DATETIME NULL,

    CONSTRAINT fk_files_user
        FOREIGN KEY (user_id) REFERENCES users(id)
);
```

### Recommended indexes

```sql
CREATE INDEX idx_files_user_created
ON files(user_id, created_at);

CREATE INDEX idx_files_user_status
ON files(user_id, status);

CREATE INDEX idx_files_user_label
ON files(user_id, label);

CREATE INDEX idx_files_user_deleted
ON files(user_id, deleted_at);

CREATE UNIQUE INDEX uq_files_storage_key
ON files(storage_provider, bucket_name(190), object_key(190));
```

The exact index strategy should be adjusted for the actual MySQL version and identifier data types.

---

# 8. File Lifecycle State Machine

Avoid an uncontrolled collection of booleans.

Use explicit states.

## Upload status

```text
PENDING
   |
   +----> UPLOADED
   |
   +----> FAILED
```

For future processing:

```text
UPLOADED
   |
   v
PROCESSING
   |
   +----> READY
   |
   +----> FAILED
```

A practical V1 state model:

```text
PENDING
UPLOADED
PROCESSING
READY
FAILED
DELETED
```

Do not overload `status` with AI status.

Keep AI-processing state separate:

```text
summary_status:
NOT_STARTED
PROCESSING
COMPLETED
FAILED
```

This separation will help V2/V4 when multiple AI pipelines exist.

---

# 9. Future Database Tables

Do not create all of these in V1 unless needed.

Design the system so they can be added by migrations.

## V2: `document_chunks`

```text
document_chunks
---------------
id
file_id
chunk_index
content_hash
text
token_count
created_at
updated_at
```

Important:

- Qdrant stores vectors.
- MySQL stores canonical application/chunk metadata if needed.
- Never make MySQL the primary vector engine when Qdrant is planned.

## V3: `external_connections`

```text
external_connections
--------------------
id
user_id
provider
status
external_account_id
encrypted_access_token
encrypted_refresh_token
token_expires_at
scopes
created_at
updated_at
```

Possible `provider` values:

```text
google_drive
github
```

Never store OAuth tokens as plain text.

## V3: `external_files`

```text
external_files
--------------
id
connection_id
provider
external_file_id
parent_external_id
name
mime_type
web_url
modified_at
sync_state
last_synced_at
```

This allows external files to participate in a unified knowledge model without pretending they are S3 objects.

---

# 10. Recommended Backend Project Structure

Use a modular structure rather than placing everything in `main.py`.

Suggested structure:

```text
backend/
├── app/
│   ├── __init__.py
│   ├── main.py
│   │
│   ├── core/
│   │   ├── __init__.py
│   │   ├── config.py
│   │   ├── logging.py
│   │   ├── security.py
│   │   └── exceptions.py
│   │
│   ├── db/
│   │   ├── __init__.py
│   │   ├── session.py
│   │   ├── base.py
│   │   └── models/
│   │       ├── __init__.py
│   │       └── file.py
│   │
│   ├── api/
│   │   ├── __init__.py
│   │   ├── deps.py
│   │   └── v1/
│   │       ├── __init__.py
│   │       ├── router.py
│   │       └── files.py
│   │
│   ├── schemas/
│   │   ├── __init__.py
│   │   ├── file.py
│   │   └── common.py
│   │
│   ├── repositories/
│   │   ├── __init__.py
│   │   └── file_repository.py
│   │
│   ├── services/
│   │   ├── __init__.py
│   │   ├── file_service.py
│   │   ├── storage/
│   │   │   ├── __init__.py
│   │   │   └── s3_service.py
│   │   └── ai/
│   │       ├── __init__.py
│   │       ├── gemini_service.py
│   │       └── prompts.py
│   │
│   ├── workers/
│   │   ├── __init__.py
│   │   └── file_processing_worker.py
│   │
│   └── utils/
│       ├── __init__.py
│       ├── file_validation.py
│       └── identifiers.py
│
├── alembic/
│   ├── versions/
│   ├── env.py
│   └── script.py.mako
│
├── tests/
│   ├── unit/
│   │   ├── services/
│   │   └── utils/
│   ├── integration/
│   │   ├── api/
│   │   ├── db/
│   │   └── storage/
│   └── conftest.py
│
├── .env.example
├── alembic.ini
├── pyproject.toml
├── requirements.txt
└── README.md
```

---

# 11. Why This Structure

This is intentionally close to the style of FastAPI's official guidance for larger applications: routers are separated from application entry points and dependencies, while the application is split across Python packages.

The official FastAPI full-stack template also demonstrates a production-oriented separation of API/backend concerns, database access, settings, testing, Docker, CI/CD, and frontend concerns.

Do not blindly copy a large template. Borrow its architectural principles and keep your project appropriate for your scope.

---

# 12. Layer Responsibilities

## `api/`

HTTP concerns only:

- request parsing
- authentication dependency
- calling services
- response models
- HTTP status codes

Avoid putting business logic here.

Bad:

```python
@router.delete("/files/{file_id}")
async def delete_file(...):
    # 50 lines of S3 + DB logic
```

Better:

```python
await file_service.delete_file(
    user_id=current_user.id,
    file_id=file_id,
)
```

## `services/`

Business logic.

Examples:

```text
FileService
S3Service
GeminiService
```

This is the most important application layer.

## `repositories/`

Database access.

Examples:

```text
get_by_id()
create()
update_metadata()
soft_delete()
list_by_user()
```

Do not put S3 or Gemini logic here.

## `schemas/`

Pydantic request/response models.

## `db/models/`

SQLAlchemy ORM models.

## `core/`

Application-wide configuration/security/logging.

---

# 13. V1 API Design

Base path:

```text
/api/v1
```

## File endpoints

### Create upload session

```http
POST /api/v1/files/upload-url
```

Request:

```json
{
  "filename": "resume.pdf",
  "content_type": "application/pdf",
  "file_size": 182934,
  "title": "2026 Resume",
  "label": "career",
  "description": "Current resume"
}
```

Response:

```json
{
  "file_id": "uuid",
  "upload_url": "https://...",
  "object_key": "users/.../files/.../original/resume.pdf",
  "expires_in": 900
}
```

### Complete upload

```http
POST /api/v1/files/{file_id}/complete
```

### List files

```http
GET /api/v1/files
```

Query parameters:

```text
page
page_size
label
status
search
sort_by
sort_order
```

### Get file

```http
GET /api/v1/files/{file_id}
```

### Update metadata

```http
PATCH /api/v1/files/{file_id}
```

Example:

```json
{
  "title": "Backend Developer Resume",
  "label": "jobs",
  "description": "Resume tailored for Python backend roles"
}
```

### Get download URL

```http
POST /api/v1/files/{file_id}/download-url
```

### Delete

```http
DELETE /api/v1/files/{file_id}
```

Use soft deletion in MySQL and perform physical S3 deletion as a controlled operation.

### Summarize

```http
POST /api/v1/files/{file_id}/summary
```

Potential response:

```json
{
  "file_id": "uuid",
  "summary_status": "PROCESSING"
}
```

Do not keep a long Gemini call open if the processing path becomes expensive.

---

# 14. Authorization Rules

Every file operation must be scoped to the authenticated user.

Never do:

```python
file = repository.get(file_id)
```

and trust the result.

Instead:

```python
file = repository.get_by_id_and_user(
    file_id=file_id,
    user_id=current_user.id,
)
```

This prevents horizontal privilege escalation.

Rule:

```text
Authenticated user
       |
       v
file.user_id == current_user.id
       |
   allowed
```

For V3 external resources, permissions must also be checked against the source connection and provider.

---

# 15. Pydantic Schema Design

Keep request and response schemas separate.

Example:

```python
class FileMetadataUpdate(BaseModel):
    title: str | None = Field(None, max_length=255)
    label: str | None = Field(None, max_length=100)
    description: str | None = Field(None, max_length=5000)
```

Do not expose internal fields in an update model:

```text
bucket_name
object_key
user_id
status
checksum
```

Those are server-owned.

Example response:

```python
class FileResponse(BaseModel):
    id: UUID
    title: str
    label: str | None
    description: str | None

    original_filename: str
    mime_type: str
    file_size_bytes: int

    status: str
    summary_status: str
    summary: str | None

    created_at: datetime
    updated_at: datetime
```

---

# 16. S3 Service Design

Create a dedicated service:

```python
class S3StorageService:
    async def create_upload_url(...):
        ...

    async def object_exists(...):
        ...

    async def create_download_url(...):
        ...

    async def delete_object(...):
        ...

    async def get_object_bytes(...):
        ...
```

Keep boto3/AWS-specific code here.

The rest of the application should not need to know how boto3 works.

This is important for V3.

Later:

```text
StorageService
      |
      +-- S3StorageService
      +-- GoogleDriveStorageAdapter
      +-- GithubContentAdapter
```

---

# 17. S3 Security

Minimum production baseline:

- S3 bucket is private
- Block public access
- Use IAM instead of hard-coded AWS access keys
- Use least-privilege permissions
- Use short-lived presigned URLs
- Never return raw permanent object URLs to clients
- Validate content type
- Validate file size
- Sanitize filename for display only
- Generate application-owned object keys
- Enable server-side encryption
- Add lifecycle rules where appropriate
- Log suspicious or failed access

For uploads, the frontend receives only a short-lived presigned URL.

---

# 18. File Validation

Validate before issuing the upload URL:

```text
Allowed:
PDF
TXT
DOCX
PPTX
(optional images later)
```

Validate:

- filename length
- extension
- MIME type
- maximum size
- user quota if quotas are introduced

Do not trust extension alone.

For production hardening later:

- inspect file signatures/magic bytes
- malware scanning
- archive-bomb protection
- content extraction limits

V1 can keep this simple, but the architecture should allow validation to become stricter later.

---

# 19. AI Summarization Design

Create one AI service abstraction.

```python
class LLMService(Protocol):
    async def summarize_document(self, text: str) -> SummaryResult:
        ...
```

Then:

```text
services/ai/
├── gemini_service.py
└── prompts.py
```

This prevents Gemini-specific logic from spreading through the application.

---

# 20. Prompt Engineering Strategy

Do not hard-code a giant prompt inside an API route.

Create versioned prompt templates.

Example:

```text
prompts/
    summarize_v1.txt
```

Prompt goals:

- concise but useful summary
- identify key topics
- identify important entities
- preserve factual meaning
- do not invent information
- state when content is insufficient
- use predictable structure

Recommended output contract:

```json
{
  "summary": "...",
  "key_points": [
    "...",
    "..."
  ],
  "document_type": "...",
  "topics": [
    "..."
  ]
}
```

Use structured output where supported instead of asking the frontend to parse free-form text.

Store:

```text
summary_model
prompt_version
summary_generated_at
```

This gives you traceability when prompts or models change.

---

# 21. Document Extraction Boundary

For V1, keep document extraction isolated:

```text
services/
    document/
        extractor.py
        pdf_extractor.py
        docx_extractor.py
```

Possible interface:

```python
class DocumentExtractor(Protocol):
    async def extract(self, file_bytes: bytes, mime_type: str) -> str:
        ...
```

Later:

```text
PDF extractor
DOCX extractor
TXT extractor
GitHub source extractor
Google Drive extractor
```

This is important because V2/V3 will reuse extraction.

---

# 22. AI Processing Flow

Recommended initial flow:

```text
POST /files/{id}/summary
          |
          v
Verify ownership
          |
          v
Check file status
          |
          v
Create processing job
          |
          v
Worker:
   download from S3
          |
          v
   extract text
          |
          v
   call Gemini
          |
          v
   save summary
          |
          v
   update summary_status
```

Do not put heavy extraction and AI calls directly in the main HTTP request path once the feature becomes non-trivial.

---

# 23. Background Processing Strategy

### Beginner V1 implementation

A lightweight background task is acceptable for a prototype.

### Production-oriented V1

Use a dedicated worker process and a durable queue.

A simple progression is:

```text
V1:
MySQL processing_jobs + worker process

Later:
AWS SQS + worker
```

Avoid adding Celery/Redis merely because they are popular. Add a queue when there is an actual background workload.

The important architectural separation is:

```text
HTTP request
    ≠
long-running AI/document processing
```

---

# 24. Processing Job Table

Future-friendly:

```sql
CREATE TABLE processing_jobs (
    id                CHAR(36) PRIMARY KEY,
    user_id           CHAR(36) NOT NULL,
    file_id           CHAR(36) NOT NULL,

    job_type          VARCHAR(50) NOT NULL,
    status             VARCHAR(30) NOT NULL,

    attempts           INT NOT NULL DEFAULT 0,
    error_code         VARCHAR(100) NULL,
    error_message      TEXT NULL,

    started_at         DATETIME NULL,
    completed_at       DATETIME NULL,
    created_at         DATETIME NOT NULL,

    INDEX idx_jobs_status_created(status, created_at),
    INDEX idx_jobs_file(file_id)
);
```

Possible `job_type`:

```text
SUMMARIZE
EXTRACT_TEXT
EMBED_DOCUMENT
SYNC_EXTERNAL_FILE
```

This makes V2/V3 much easier.

---

# 25. V2 — Semantic Search

V2 should reuse all V1 foundations.

## Pipeline

```text
S3 file
  |
  v
Document extraction
  |
  v
Text normalization
  |
  v
Chunking
  |
  v
Embedding model
  |
  v
Qdrant
```

Each vector should carry payload such as:

```json
{
  "user_id": "user-id",
  "file_id": "file-id",
  "chunk_id": "chunk-id",
  "title": "FastAPI Notes",
  "label": "learning",
  "mime_type": "application/pdf",
  "chunk_index": 3
}
```

The `user_id` and `file_id` payloads enable security and file-level filtering.

Always enforce application-level authorization in FastAPI as well. Do not rely only on a vector payload filter.

---

# 26. Qdrant Design

Recommended initial collection:

```text
knowledge_chunks
```

Payload:

```text
user_id
file_id
chunk_id
title
label
source_type
source_id
```

Where:

```text
source_type =
    s3
    google_drive
    github
```

This is the first major step toward a unified knowledge layer.

Qdrant's official Python client supports both synchronous and asynchronous APIs and provides local mode for development. Use local mode only for simple development/testing and a real Qdrant service/cloud deployment for persistent environments.

---

# 27. V2 Search API

```http
GET /api/v1/search
```

Example:

```text
?q=python backend authentication
&top_k=10
&label=career
```

Response:

```json
{
  "query": "...",
  "results": [
    {
      "file_id": "...",
      "title": "...",
      "score": 0.87,
      "snippet": "...",
      "chunk_id": "..."
    }
  ]
}
```

Do not expose raw internal vector IDs as your user-facing resource IDs.

---

# 28. V3 — External Connector Architecture

Do not create:

```text
google_drive.py
github.py
random API calls
```

inside file routes.

Create a connector abstraction.

Suggested structure:

```text
services/
├── connectors/
│   ├── base.py
│   ├── registry.py
│   ├── google_drive/
│   │   ├── client.py
│   │   ├── auth.py
│   │   ├── mapper.py
│   │   └── connector.py
│   └── github/
│       ├── client.py
│       ├── auth.py
│       ├── mapper.py
│       └── connector.py
```

Base interface:

```python
class KnowledgeConnector(Protocol):
    provider: str

    async def connect(self, user_id: UUID) -> None:
        ...

    async def list_items(self, connection_id: UUID) -> list[ExternalItem]:
        ...

    async def fetch_item(
        self,
        connection_id: UUID,
        external_id: str,
    ) -> ExternalContent:
        ...

    async def disconnect(self, connection_id: UUID) -> None:
        ...
```

This is a plugin-ready design.

---

# 29. Google Drive Integration

V3 flow:

```text
User
  |
  v
Connect Google Drive
  |
  v
Google OAuth
  |
  v
Authorization code
  |
  v
FastAPI callback
  |
  v
Store encrypted token data
  |
  v
Google Drive connector
  |
  +--> list files
  +--> fetch content/metadata
  +--> detect changed items
```

Google's official Drive quickstart demonstrates enabling the Drive API, configuring OAuth credentials, installing the Python Google API libraries, and making Drive API requests.

Production implementation must use appropriate OAuth consent, scopes, credential storage, refresh handling, and error handling.

---

# 30. GitHub Integration

For repositories:

```text
Connect GitHub
   |
   v
OAuth / GitHub App
   |
   v
Choose repositories
   |
   v
List files / source tree
   |
   v
Fetch source content
   |
   v
Normalize as knowledge items
```

Do not treat a GitHub repository as one huge text document.

Model it as:

```text
Repository
   |
   +-- README.md
   +-- docs/
   +-- src/
   +-- config files
   +-- selected source files
```

Later, allow include/exclude patterns.

---

# 31. Unified Source Model

V3/V4 should make different sources look similar internally.

Example conceptual model:

```text
KnowledgeSource
    |
    +-- S3 file
    +-- Google Drive file
    +-- GitHub repository/file
```

Every source should have:

```text
source_type
source_id
display_name
mime_type / content_type
owner/user
modified_at
access information
sync status
```

Then downstream AI does not need to know whether content came from S3 or Google Drive.

---

# 32. V4 — RAG

RAG should reuse V2.

```text
User question
      |
      v
Question embedding
      |
      v
Qdrant similarity search
      |
      v
Top relevant chunks
      |
      v
Build grounded prompt
      |
      v
Gemini
      |
      v
Answer + citations
```

For a user's personal data, always filter retrieval by:

```text
user_id == current_user.id
```

and any selected source/file constraints.

---

# 33. Citation Design

Each retrieved chunk should retain enough provenance:

```text
file_id
chunk_id
title
source_type
source_url / web URL when available
page number when available
chunk index
```

Response example:

```json
{
  "answer": "...",
  "citations": [
    {
      "file_id": "...",
      "title": "FastAPI Notes.pdf",
      "page": 7,
      "snippet": "..."
    }
  ]
}
```

This makes RAG trustworthy and debuggable.

---

# 34. V5 — MCP / Agents

Only introduce this after V4 works.

Expose safe tools such as:

```text
search_knowledge()
get_file_metadata()
read_document()
summarize_file()
compare_documents()
find_similar_files()
list_connected_sources()
search_github()
search_google_drive()
```

Example agent workflow:

```text
User:
"Compare my resume with the backend job description and tell me what is missing."

Agent:
  1. search_knowledge("latest backend resume")
  2. search_knowledge("Python backend job description")
  3. read_document(resume)
  4. read_document(job description)
  5. compare_documents(...)
  6. generate recommendation
```

The agent should not receive arbitrary S3 credentials.

Give it narrow tools that enforce authorization.

---

# 35. API Versioning

Use:

```text
/api/v1/...
```

From the beginning.

Later:

```text
/api/v2/...
```

Do not version every internal service class.

Only external API contracts need explicit versioning.

---

# 36. Configuration

Use environment-based configuration.

Example `.env.example`:

```env
APP_ENV=development
APP_NAME=KnowledgeBase
DEBUG=false

DATABASE_URL=mysql+pymysql://user:password@localhost:3306/knowledge_base

AWS_REGION=ap-south-1
AWS_S3_BUCKET=your-private-bucket

GEMINI_API_KEY=replace-me
GEMINI_MODEL=replace-me

MAX_UPLOAD_SIZE_BYTES=104857600
PRESIGNED_URL_EXPIRES_SECONDS=900

LOG_LEVEL=INFO
```

Do not commit `.env`.

Use a secret manager in production.

---

# 37. Database Migration Strategy

Use Alembic from the beginning.

Commands:

```bash
alembic revision --autogenerate -m "create files table"
alembic upgrade head
alembic downgrade -1
```

Rules:

- every schema change is a migration
- never manually edit production tables
- inspect autogenerated migrations before running them
- keep migration names meaningful
- test both upgrade and downgrade where practical

---

# 38. Error Handling

Define application errors.

Examples:

```text
FileNotFoundError
FileOwnershipError
InvalidFileTypeError
UploadExpiredError
S3ObjectNotFoundError
AIServiceError
DocumentExtractionError
ProcessingFailedError
```

Map them centrally to HTTP responses.

Example:

```json
{
  "detail": {
    "code": "FILE_NOT_FOUND",
    "message": "File not found."
  }
}
```

Do not leak AWS, SQL, or provider internals to clients.

---

# 39. Logging

Log structured events.

Useful fields:

```text
request_id
user_id
file_id
job_id
operation
provider
duration_ms
status
error_code
```

Never log:

- Gemini API keys
- OAuth access tokens
- OAuth refresh tokens
- presigned URLs
- raw document content

---

# 40. Testing Strategy

## Unit tests

Test:

- filename validation
- metadata validation
- S3 key generation
- ownership checks
- service logic
- prompt construction
- status transitions

## Integration tests

Test:

- MySQL repository
- API + database
- S3 test environment/local mock where appropriate
- upload lifecycle
- summary workflow

## API tests

Minimum:

```text
POST /files/upload-url
POST /files/{id}/complete
GET /files
GET /files/{id}
PATCH /files/{id}
POST /files/{id}/download-url
DELETE /files/{id}
POST /files/{id}/summary
```

Test both successful and unauthorized access.

Critical security test:

```text
User A must not access User B's file.
```

---

# 41. Frontend Structure (Optional React + Material UI)

Suggested:

```text
frontend/
├── src/
│   ├── api/
│   │   ├── client.ts
│   │   └── files.ts
│   ├── components/
│   │   ├── files/
│   │   │   ├── FileList.tsx
│   │   │   ├── FileRow.tsx
│   │   │   ├── FileUpload.tsx
│   │   │   ├── FileMetadataDialog.tsx
│   │   │   └── SummaryPanel.tsx
│   ├── pages/
│   │   └── FilesPage.tsx
│   ├── hooks/
│   │   └── useFiles.ts
│   ├── theme/
│   │   └── theme.ts
│   ├── types/
│   │   └── file.ts
│   └── App.tsx
```

The frontend should:

1. call FastAPI for the presigned URL
2. upload directly to S3
3. notify FastAPI that upload completed
4. refresh the metadata list
5. display summary state

Do not put AWS credentials in React.

---

# 42. Frontend Upload Sequence

```text
Select file
   |
   v
POST /upload-url
   |
   v
Receive signed URL
   |
   v
PUT directly to S3
   |
   v
POST /complete
   |
   v
Show "Uploaded"
```

Material UI can remain a presentation layer. Avoid coupling UI components directly to business logic.

---

# 43. Security Checklist

## Authentication

- Existing authentication is the source of truth
- Protect all file endpoints
- Validate current user identity through FastAPI dependencies

## Authorization

- Every file query must include current user ownership
- Never trust a `user_id` supplied by the client
- Never allow clients to set ownership fields

## S3

- private bucket
- public access blocked
- least-privilege IAM
- presigned URL
- short expiration
- server-side encryption

## Database

- parameterized ORM/queries
- migrations through Alembic
- database credentials through secrets
- no raw credentials in Git

## AI

- never send data to Gemini without an explicit product reason
- avoid logging raw user documents
- control maximum document size
- consider redaction/privacy controls in a future version

## External integrations

- OAuth scopes limited to the required resources
- encrypt tokens
- rotate/revoke credentials
- isolate connector permissions
- handle provider rate limits

---

# 44. Observability

Minimum V1:

```text
application logs
request IDs
error logging
processing status
```

Later:

```text
metrics
tracing
S3 metrics
AI latency/cost
Qdrant latency
connector sync failures
```

Useful AI metrics:

```text
summaries_generated
summary_failures
average_summary_latency
tokens_used
estimated_cost
```

---

# 45. Performance Strategy

## V1

- direct S3 upload
- pagination for file list
- indexes on user_id/status/created_at
- no full-table scan for normal requests
- asynchronous AI processing
- limit input size

## V2

- batch embedding where possible
- Qdrant payload filters
- chunk limits
- top-k controls
- caching where useful

## V3

- incremental sync
- do not re-index unchanged external content
- maintain provider sync cursors/checkpoints

## V4

- retrieve only relevant chunks
- context size limits
- optionally rerank
- return citations with provenance

---

# 46. Idempotency and Reliability

Upload completion should be safe to retry.

Example:

```text
POST /files/{file_id}/complete
```

If already completed:

```text
return current state
```

rather than creating duplicate metadata.

Background jobs should also be retry-safe.

Example:

```text
SUMMARY job
attempt 1 -> fails
attempt 2 -> succeeds
```

Do not create duplicate summaries or duplicate vector points.

Use deterministic IDs for chunks/vector points where practical:

```text
hash(file_id + version + chunk_index)
```

---

# 47. File Version Strategy

Do not build full version history in V1.

But reserve the architecture.

Current V1:

```text
files
  -> one current S3 object
```

Future V2+:

```text
files
   |
   +-- file_versions
          |
          +-- version 1 -> S3 object
          +-- version 2 -> S3 object
          +-- version 3 -> S3 object
```

Semantic indexing should reference a file version, not only a file.

This prevents stale vectors after a document changes.

---

# 48. Recommended V1 Development Phases

## Phase 0 — Foundation

Tasks:

- repository initialization
- `.gitignore`
- settings
- database connection
- SQLAlchemy models
- Alembic
- existing auth integration
- global error handling
- logging
- health endpoint
- API versioning

Deliverable:

```http
GET /health
GET /api/v1/health
```

---

## Phase 1 — File Metadata

Tasks:

- `files` ORM model
- migration
- Pydantic schemas
- repository
- service
- list/get/update/delete APIs
- ownership checks
- pagination

Deliverable:

```text
Authenticated user can manage file metadata.
```

---

## Phase 2 — S3 Integration

Tasks:

- AWS SDK client
- bucket configuration
- IAM permissions
- presigned upload endpoint
- upload completion endpoint
- download URL endpoint
- deletion
- S3 error handling

Deliverable:

```text
Browser -> S3 upload
FastAPI -> metadata
```

---

## Phase 3 — File CRUD Completion

Tasks:

- React upload UI
- file list
- edit metadata
- delete confirmation
- download button
- loading/error states

Deliverable:

```text
Usable file workspace.
```

---

## Phase 4 — Document Extraction

Tasks:

- extraction interface
- PDF implementation
- DOCX implementation
- TXT implementation
- extraction size limits
- extraction error states

Deliverable:

```text
S3 document -> normalized text
```

---

## Phase 5 — Gemini Summarization

Tasks:

- Gemini service
- prompt versioning
- structured output
- summary storage
- summary status
- background processing
- retry/error state
- summary UI

Deliverable:

```text
file -> extracted text -> Gemini -> summary
```

---

## Phase 6 — V1 Hardening

Tasks:

- unit tests
- integration tests
- authorization tests
- security review
- pagination
- structured logs
- health/readiness endpoints
- API documentation cleanup
- `.env.example`
- production configuration
- deployment

Deliverable:

**V1 production-ready portfolio milestone.**

---

# 49. V2 Development Phases

## Phase V2.1 — Chunking

Tasks:

- chunking strategy
- chunk overlap
- token/character limits
- chunk metadata
- chunk versioning

## Phase V2.2 — Embeddings

Choose one embedding approach and make it replaceable.

Interface:

```python
class EmbeddingService(Protocol):
    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        ...

    async def embed_query(self, text: str) -> list[float]:
        ...
```

## Phase V2.3 — Qdrant

Tasks:

- collection setup
- vector dimension configuration
- payload schema
- deterministic point IDs
- upsert
- delete by file/version
- filtered search

## Phase V2.4 — Semantic Search API

Tasks:

- search endpoint
- filtering
- pagination/top-k
- snippets
- result provenance

---

# 50. V3 Development Phases

## Phase V3.1 — Connector abstraction

- `KnowledgeConnector`
- source registry
- external connection records
- sync states

## Phase V3.2 — Google Drive

- OAuth
- token management
- file listing
- metadata mapping
- content download/export
- sync

## Phase V3.3 — GitHub

- GitHub authentication
- repository selection
- tree listing
- source-file retrieval
- include/exclude rules
- sync

## Phase V3.4 — Unified indexing

```text
S3
Google Drive
GitHub
   |
   v
Normalized content model
   |
   v
Extraction
   |
   v
Chunking
   |
   v
Embeddings
   |
   v
Qdrant
```

---

# 51. V4 RAG Development Phases

## Phase V4.1

- retrieval service
- top-k
- source filtering
- context assembly

## Phase V4.2

- grounded Gemini prompt
- citations
- refusal when evidence is insufficient

## Phase V4.3

- multi-document questions
- conversation history
- selected-file scope
- source filters

---

# 52. V5 MCP / Agent Development Phases

Start with deterministic tools.

```text
search_knowledge
get_file
read_file
summarize_file
compare_files
list_sources
```

Then:

- tool schemas
- authorization middleware
- audit logs
- agent loop
- tool-call limits
- timeout handling
- failure recovery

Agent permissions must always be a subset of the user's permissions.

---

# 53. Production Deployment Architecture

A practical AWS-oriented architecture:

```text
                      Internet
                         |
                         v
                    HTTPS / CDN
                         |
                   Reverse proxy
                         |
          ┌──────────────┴──────────────┐
          v                             v
      React app                     FastAPI API
                                          |
                      ┌───────────────────┼───────────────────┐
                      v                   v                   v
                    MySQL                S3                Gemini
                      |
                      v
                Processing jobs
                      |
                      v
                 Worker process
                      |
                      v
             Future Qdrant / SQS
```

For a fresher project, do not over-engineer infrastructure on day one.

A single FastAPI deployment + managed MySQL + S3 is enough for V1.

---

# 54. Recommended AWS IAM Permissions

Application role should only have required S3 permissions.

Conceptually:

```text
s3:GetObject
s3:PutObject
s3:DeleteObject
```

restricted to:

```text
arn:aws:s3:::YOUR_BUCKET/users/*
```

Avoid:

```text
s3:*
```

for the application.

Use IAM roles where the hosting environment supports them instead of embedding AWS keys.

---

# 55. CI/CD

Minimum GitHub Actions pipeline:

```text
Pull Request
    |
    +--> lint
    +--> type checks
    +--> tests
    +--> build
```

Main branch:

```text
merge
  |
  v
CI
  |
  v
deploy
```

Possible quality tools:

```text
pytest
ruff
mypy (optional)
```

Do not add tools solely for resume keyword value.

---

# 56. Documentation Requirements

Repository should contain:

```text
README.md
ARCHITECTURE.md
API.md
DEVELOPMENT.md
SECURITY.md
```

README should explain:

- problem
- architecture
- features
- setup
- environment variables
- local development
- deployment
- screenshots
- API docs
- roadmap

ARCHITECTURE should explain why:

- S3 for files
- MySQL for metadata
- Qdrant later
- connectors later
- Gemini service abstraction

---

# 57. Open-Source Architectural References

Use these as reference projects/documentation, not as code to copy blindly.

## FastAPI official multi-file application structure

FastAPI's "Bigger Applications" documentation demonstrates splitting routers, dependencies, packages, and application entry points instead of putting everything into one file.

Reference:

- FastAPI Bigger Applications:
  https://fastapi.tiangolo.com/tutorial/bigger-applications/

## FastAPI official full-stack template

The official template demonstrates a broader production-style architecture including FastAPI, SQL database access, Pydantic, React, testing, Docker, CI/CD, and deployment concepts.

Reference:

- https://github.com/fastapi/full-stack-fastapi-template

Do not copy the entire template for this project. Your application is smaller; use the structural principles.

## AWS Boto3 S3

AWS's Python SDK documentation demonstrates normal S3 upload operations and presigned URLs.

References:

- https://docs.aws.amazon.com/boto3/latest/guide/s3-uploading-files.html
- https://docs.aws.amazon.com/boto3/latest/guide/s3-presigned-urls.html

## Qdrant

Qdrant's official Python client supports synchronous and asynchronous API usage, filtering/payloads, local development mode, and cloud/server connections.

Reference:

- https://github.com/qdrant/qdrant-client

## Google Drive API

Google's official Python quickstart demonstrates enabling the Drive API, configuring OAuth, installing the client libraries, and making Drive API calls.

Reference:

- https://developers.google.com/workspace/drive/api/quickstart/python

---

# 58. What NOT to Build in V1

Avoid these:

- Full Google Drive clone
- Nested folder system
- File sharing
- Public links
- Team collaboration
- Realtime notifications
- WebSockets
- Microservices
- Kubernetes
- Elasticsearch
- Qdrant
- Google Drive OAuth
- GitHub integration
- MCP
- Autonomous agents
- Complex RBAC
- Full document versioning

They are future capabilities, not V1 requirements.

---

# 59. Recommended V1 Scope for a Fresher

If the project is becoming too large, this is the minimum acceptable professional version:

```text
Authentication (already done)
        |
        v
FastAPI
        |
   ┌────┴────┐
   v         v
 MySQL      S3
   |         |
metadata    files
   |
   v
Gemini summarization
   |
   v
React + Material UI
```

Required capabilities:

- direct S3 upload
- file metadata CRUD
- owner-based authorization
- download/delete
- document extraction
- Gemini summary
- migration
- tests
- error handling
- logging
- clean architecture

That alone is already a strong backend/AI portfolio project.

---

# 60. Project Success Criteria

## Technical success

- no business logic in routers
- all database changes through Alembic
- all file operations ownership-scoped
- private S3 bucket
- no AWS credentials in frontend
- no raw Gemini secrets in Git
- API versioned
- test coverage for critical flows
- AI processing isolated from HTTP request path
- clear service boundaries

## V2 compatibility

The V1 design must allow:

```text
Document -> extraction -> chunking -> embedding -> Qdrant
```

without rewriting the existing file service.

## V3 compatibility

The system must allow:

```text
S3
Google Drive
GitHub
```

to enter the same normalized knowledge pipeline.

## V4 compatibility

RAG should consume:

```text
Retriever
  -> normalized chunks
  -> provenance
  -> Gemini
```

rather than directly depending on S3.

This separation is the most important architectural requirement in the entire roadmap.

---

# 61. Final Recommended Build Order

Follow this exact implementation sequence:

```text
1. Project foundation
2. MySQL connection
3. Alembic
4. File model
5. File repository
6. File service
7. File CRUD API
8. S3 service
9. Presigned upload
10. Upload completion
11. Download URL
12. S3 deletion
13. React file UI
14. Document extraction interface
15. PDF/DOCX/TXT extraction
16. Gemini service
17. Prompt versioning
18. Summary processing
19. Job/worker boundary
20. Tests
21. Security hardening
22. Deployment
23. V1 complete

Then:

24. Chunking
25. Embeddings
26. Qdrant
27. Semantic search
28. Google Drive connector
29. GitHub connector
30. Unified source model
31. RAG
32. Citations
33. MCP tools
34. Agent workflows
```

---

# 62. Senior Developer Recommendation

The most important design decision is **not** choosing a fashionable library.

It is keeping the boundaries clean:

```text
HTTP
  ↓
Service
  ↓
Repository / Provider
```

and:

```text
Source
  ↓
Normalized content
  ↓
Extraction
  ↓
Chunking
  ↓
Embedding
  ↓
Retrieval
  ↓
LLM
```

If those boundaries are maintained from V1, the project can evolve from a simple S3 file organizer into a genuine personal knowledge platform without rewriting the core backend.

**Build V1 as a strong modular monolith, not as microservices.**

