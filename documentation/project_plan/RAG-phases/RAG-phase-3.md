# RAG Phase 3 - Versioned MySQL Persistence and Zero-Downtime Indexing

## 1. Phase Goal

Phase 3 makes the chunk output from Phase 2 durable in MySQL.

Phase 2 already gives the backend this in-memory result:

```text
ProcessedDocument
|
+-- page_count
+-- extracted_word_count
`-- chunks[]
    |
    +-- chunk_index
    +-- clean_text
    +-- page_start
    +-- page_end
    +-- word_start
    +-- word_end
    +-- word_count
    `-- text_checksum
```

Phase 3 stores that result safely:

```text
ProcessedDocument from Phase 2
    |
    v
new RAG index_version for file
    |
    v
insert document_chunks rows
    |
    v
update file_metadata RAG counters/status
    |
    v
prepare for Phase 4 embeddings and Qdrant upsert
```

The central architecture rule:

```text
A query must only ever use a complete active version.
Never expose a half-written chunk version to retrieval.
```

In this project, Phase 3 should **not** yet generate embeddings or write chunk vectors to Qdrant. That belongs to Phase 4. Phase 3 does, however, create the database shape and service methods that make zero-downtime indexing possible.

## 2. Phase 2 Status Check

Before writing this plan, the current Phase 2 implementation was checked.

Present files:

```text
backend/app/services/rag/
|-- __init__.py
|-- schemas.py
|-- pdf_extractor.py
|-- text_cleaner.py
|-- chunker.py
`-- document_processor.py
```

Focused verification passed:

```text
uv run pytest tests/unit/services/rag tests/unit/services/test_s3_service.py

58 passed
```

So Phase 3 can assume these are available:

- `process_pdf_from_storage(s3_key)`
- `ProcessedDocument`
- `TextChunk`
- `text_checksum`
- bounded S3/B2 reads
- PyMuPDF page extraction
- deterministic chunking

Small implementation note for later cleanup:

```text
backend/app/services/rag/chunker.py currently reads chunk settings with os.getenv.
Prefer using app.core.config.settings in a future cleanup so all RAG config flows
through one validated settings object.
```

That cleanup is useful, but it does not block Phase 3.

## 3. What Phase 3 Adds

```text
+-------------------------------+--------------------------------------------+
| Area                          | Phase 3 work                               |
+-------------------------------+--------------------------------------------+
| SQLAlchemy models             | Add DocumentChunk and UserCorpusState      |
| file_metadata                 | Add RAG tracking columns                   |
| Alembic                       | Generate and review migration              |
| RAG persistence service       | Save ProcessedDocument chunks transactionally |
| Versioning                    | Write new versions without exposing them early |
| Error state                   | Store RAG extraction/persistence errors    |
| Tests                         | Model, migration, and service tests        |
+-------------------------------+--------------------------------------------+
```

Phase 3 does not add:

```text
Gemini chunk embeddings
Qdrant chunk upserts
RAG query endpoint
answer generation
Redis answer cache usage
Streamlit UI
```

## 4. Existing Database Reality

The existing `FileMetadata` model uses these names:

```text
file_metadata.fileid   # primary key
file_metadata.userid   # owner user id
```

The main RAG plan uses generic names like `file_metadata.id` and `user_id`. In this repo, use the existing names for foreign keys:

```text
DocumentChunk.file_id -> file_metadata.fileid
DocumentChunk.user_id -> users.id
```

Do not create a second document table just to get cleaner naming. Work with the existing `file_metadata` table.

Current simplified table:

```text
file_metadata
|
+-- fileid
+-- userid
+-- s3_key
+-- filename
+-- content_type
+-- status
+-- is_indexed
+-- indexing_status
+-- index_version
+-- retry_count
+-- next_retry_at
+-- last_error
```

Phase 3 extends it:

```text
file_metadata
|
+-- existing columns
+-- active_index_version
+-- corpus_revision
+-- extraction_version
+-- cleaning_version
+-- chunking_version
+-- embedding_model
+-- embedding_dimensions
+-- page_count
+-- extracted_word_count
+-- chunk_count
+-- indexed_chunk_count
+-- indexing_started_at
+-- indexing_completed_at
+-- rag_error_code
`-- rag_error_message
```

## 5. Target Data Model

### 5.1 Table Relationships

```text
users
|
| 1
|         many
+--------------------+
                     |
                     v
              file_metadata
              |
              | 1
              |         many versions/chunks
              +-----------------------------+
                                            |
                                            v
                                    document_chunks

users
|
| 1
|         1
+--------------------+
                     |
                     v
              user_corpus_state
```

### 5.2 Why `document_chunks` Needs Both `file_id` and `user_id`

`file_id` links the chunk to a document.

`user_id` makes tenant filtering fast and explicit.

```text
Hydration query later:
WHERE document_chunks.user_id = current_user.id
  AND document_chunks.chunk_id IN (...)
```

Even though `file_metadata` also has `userid`, storing `user_id` on the chunk table is a deliberate denormalization for security and query performance.

## 6. RAG Lifecycle States

The current enum has:

```text
PENDING
INDEXING
INDEXED
FAILED
```

Production RAG needs more detail:

```text
PENDING
    |
    v
EXTRACTING
    |
    v
CHUNKED
    |
    v
EMBEDDING
    |
    v
INDEXING
    |
    v
INDEXED
```

Failure states:

```text
FAILED_RETRYABLE
FAILED_TERMINAL
```

Recommended enum update in `backend/app/schemas/enums.py`:

```python
class IndexingStatus(str, Enum):
    PENDING = "PENDING"
    EXTRACTING = "EXTRACTING"
    CHUNKED = "CHUNKED"
    EMBEDDING = "EMBEDDING"
    INDEXING = "INDEXING"
    INDEXED = "INDEXED"
    FAILED = "FAILED"  # keep temporarily for backward compatibility
    FAILED_RETRYABLE = "FAILED_RETRYABLE"
    FAILED_TERMINAL = "FAILED_TERMINAL"
```

Fresher note:

```text
The enum is not just labels for the UI.
It protects the worker from doing the wrong step twice or skipping a step.
```

## 7. Versioning Model

### 7.1 Existing `index_version`

The existing `file_metadata.index_version` is already used by metadata vector re-indexing.

Do not remove it in Phase 3.

To avoid breaking current behavior, use this approach:

```text
file_metadata.index_version
    Existing metadata search version.
    Keep it working.

file_metadata.active_index_version
    New RAG chunk version currently visible to retrieval.

document_chunks.index_version
    Version number of each chunk row.
```

During development, a new RAG version can be calculated as:

```text
new_version = max(file_metadata.active_index_version, 0) + 1
```

Later, if metadata vector versioning and RAG chunk versioning are unified, do it deliberately in a separate migration/refactor.

### 7.2 Serving Rule

Retrieval later must use only this condition:

```text
document_chunks.index_version = file_metadata.active_index_version
```

That means old complete data remains visible while a new version is being prepared.

```text
Current active version = 1
    |
    v
Build version 2 chunks in document_chunks
    |
    v
Do not change active_index_version yet
    |
    v
Queries still read version 1
```

Phase 4 will embed/upsert version 2 vectors. Only after verification should the active pointer move:

```text
active_index_version: 1 -> 2
```

## 8. Corpus Revision

`user_corpus_state.corpus_revision` is used later for Redis answer cache keys.

Future key:

```text
rag:answer:{user_id}:{corpus_revision}:{query_hash}
```

When a user's active corpus changes, increment revision:

```text
document becomes newly active
document is deleted
document is re-indexed and new active version cuts over
```

Important Phase 3 decision:

```text
Do not increment corpus_revision when chunks are merely staged.
Increment it only when the active serving corpus changes.
```

Why:

```text
Staged chunks are not visible to retrieval yet.
If retrieval cannot see them, cache identity should not change yet.
```

Phase 3 should create the table and helper functions. Phase 4/5 will use them during real cutover and deletion flows.

## 9. SQLAlchemy Model Changes

Edit:

```text
backend/app/database/db_models.py
```

### 9.1 Imports

Add the needed SQLAlchemy types:

```python
from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.mysql import MEDIUMTEXT
```

Use `MEDIUMTEXT` for chunk text on MySQL. If tests run on SQLite, add a compatibility fallback if needed:

```python
try:
    from sqlalchemy.dialects.mysql import MEDIUMTEXT
except ImportError:
    MEDIUMTEXT = Text
```

### 9.2 Extend FileMetadata

Add these columns to `FileMetadata`:

```python
    # RAG chunk indexing metadata
    active_index_version = Column(Integer, default=0, nullable=False)
    corpus_revision = Column(BigInteger, default=0, nullable=False)
    extraction_version = Column(String(32), nullable=True)
    cleaning_version = Column(String(32), nullable=True)
    chunking_version = Column(String(32), nullable=True)
    embedding_model = Column(String(100), nullable=True)
    embedding_dimensions = Column(SmallInteger, nullable=True)
    page_count = Column(Integer, default=0, nullable=False)
    extracted_word_count = Column(Integer, default=0, nullable=False)
    chunk_count = Column(Integer, default=0, nullable=False)
    indexed_chunk_count = Column(Integer, default=0, nullable=False)
    indexing_started_at = Column(DateTime(timezone=True), nullable=True)
    indexing_completed_at = Column(DateTime(timezone=True), nullable=True)
    rag_error_code = Column(String(64), nullable=True)
    rag_error_message = Column(String(500), nullable=True)
```

Note:

```text
The main plan lists corpus_revision on file_metadata and also has user_corpus_state.
Keep both only if useful:
    user_corpus_state.corpus_revision = authoritative per-user revision
    file_metadata.corpus_revision = revision value when this file last changed
```

If you want the smallest possible schema, you can omit `file_metadata.corpus_revision` and rely only on `user_corpus_state`. But since the main plan includes it, this Phase 3 plan keeps it as an audit/snapshot field.

### 9.3 Add UserCorpusState

```python
class UserCorpusState(Base):
    """Per-user corpus revision used to invalidate RAG answer cache keys."""

    __tablename__ = "user_corpus_state"

    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    corpus_revision = Column(BigInteger, default=0, nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    user = relationship("User", backref="corpus_state")
```

### 9.4 Add DocumentChunk

```python
class DocumentChunk(Base):
    """Durable source-of-truth text chunks for RAG retrieval."""

    __tablename__ = "document_chunks"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    file_id = Column(
        Integer,
        ForeignKey("file_metadata.fileid", ondelete="CASCADE"),
        nullable=False,
    )
    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    index_version = Column(Integer, nullable=False)
    chunk_index = Column(Integer, nullable=False)
    chunk_id = Column(String(36), nullable=False)

    page_start = Column(Integer, nullable=False)
    page_end = Column(Integer, nullable=False)
    word_start = Column(Integer, nullable=False)
    word_end = Column(Integer, nullable=False)
    word_count = Column(Integer, nullable=False)

    text_checksum = Column(String(64), nullable=False)
    clean_text = Column(MEDIUMTEXT, nullable=False)

    extraction_version = Column(String(32), nullable=False)
    cleaning_version = Column(String(32), nullable=False)
    chunking_version = Column(String(32), nullable=False)
    embedding_model = Column(String(100), nullable=False)
    embedding_dimensions = Column(SmallInteger, nullable=False, default=768)

    source_key = Column(String(1024), nullable=False)
    original_filename = Column(String(255), nullable=False)

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    file = relationship("FileMetadata", back_populates="chunks")
    user = relationship("User")

    __table_args__ = (
        UniqueConstraint(
            "file_id",
            "index_version",
            "chunk_index",
            name="uq_document_chunks_file_version_index",
        ),
        UniqueConstraint("chunk_id", name="uq_document_chunks_chunk_id"),
        Index("ix_document_chunks_file_version", "file_id", "index_version"),
        Index("ix_document_chunks_hydrate", "user_id", "chunk_id", "index_version"),
        Index("ix_document_chunks_user_file_version", "user_id", "file_id", "index_version"),
    )
```

Add the relationship to `FileMetadata`:

```python
    chunks = relationship(
        "DocumentChunk",
        back_populates="file",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
```

## 10. Deterministic Chunk IDs

Phase 3 must generate stable chunk UUIDs before Phase 4 sends points to Qdrant.

Create:

```text
backend/app/services/rag/ids.py
```

Implementation:

```python
from uuid import NAMESPACE_URL, UUID, uuid5


def build_chunk_id(file_id: int, index_version: int, chunk_index: int) -> UUID:
    return uuid5(
        NAMESPACE_URL,
        f"rag-chunk:{file_id}:{index_version}:{chunk_index}",
    )
```

Why UUIDv5:

```text
same file_id + same version + same chunk_index
    |
    v
same UUID every retry
```

That gives Phase 4 idempotent Qdrant upserts:

```text
Retry embedding batch
    |
    v
same point IDs
    |
    v
upsert overwrites, not duplicates
```

## 11. Alembic Migration

### 11.1 Generate Migration

From backend:

```powershell
cd D:\Personal_Knowledge_Base\backend
uv run alembic revision --autogenerate -m "add rag document chunks"
```

Review the generated migration before applying it.

### 11.2 Migration Must Include

```text
file_metadata new columns
user_corpus_state table
document_chunks table
unique constraints
indexes
foreign keys
```

### 11.3 MySQL Column Notes

MySQL indexable strings need explicit lengths:

```text
chunk_id            String(36)
text_checksum       String(64)
source_key          String(1024)
original_filename   String(255)
```

For `clean_text`, prefer:

```text
MEDIUMTEXT
```

Reason:

```text
800 words can fit in TEXT, but MEDIUMTEXT gives comfortable headroom for
extracted PDF weirdness without changing schema later.
```

### 11.4 Apply Migration

```powershell
uv run alembic upgrade head
```

### 11.5 Verify Tables

Use MySQL:

```sql
SHOW COLUMNS FROM file_metadata;
SHOW CREATE TABLE document_chunks;
SHOW CREATE TABLE user_corpus_state;
```

Expected relationship:

```text
document_chunks.file_id -> file_metadata.fileid
document_chunks.user_id -> users.id
```

## 12. RAG Persistence Service

Create:

```text
backend/app/services/rag/persistence.py
```

This service should own database writes for chunks.

Routes and workers should not manually insert chunks field-by-field. They should call a service function.

### 12.1 Main Function

Suggested function:

```python
def stage_document_chunks(
    db: Session,
    file: FileMetadata,
    processed: ProcessedDocument,
) -> int:
    ...
```

Return:

```text
new_index_version
```

### 12.2 Responsibilities

```text
stage_document_chunks()
    |
    v
validate file ownership/status already loaded by caller
    |
    v
calculate new RAG index version
    |
    v
delete abandoned rows for same file/version if retrying same version
    |
    v
insert all chunks for new version
    |
    v
update file_metadata:
        indexing_status = CHUNKED
        page_count
        extracted_word_count
        chunk_count
        extraction_version
        cleaning_version
        chunking_version
        embedding_model
        embedding_dimensions
        rag_error_code = None
        rag_error_message = None
    |
    v
commit
```

Do not update `active_index_version` yet unless this is a development-only mode with no embeddings. Production cutover happens only after Phase 4 verifies Qdrant.

### 12.3 Suggested Implementation Shape

```python
from sqlalchemy.orm import Session

from app.core.config import settings
from app.database.db_models import DocumentChunk, FileMetadata
from app.schemas.enums import IndexingStatus
from app.services.rag.document_processor import ProcessedDocument
from app.services.rag.ids import build_chunk_id


def next_rag_index_version(file: FileMetadata) -> int:
    return int(file.active_index_version or 0) + 1


def stage_document_chunks(
    db: Session,
    file: FileMetadata,
    processed: ProcessedDocument,
) -> int:
    new_version = next_rag_index_version(file)

    # Defensive cleanup for retry before inserting the same build version.
    db.query(DocumentChunk).filter(
        DocumentChunk.file_id == file.fileid,
        DocumentChunk.index_version == new_version,
    ).delete(synchronize_session=False)

    rows = []
    for chunk in processed.chunks:
        rows.append(
            DocumentChunk(
                file_id=file.fileid,
                user_id=file.userid,
                index_version=new_version,
                chunk_index=chunk.chunk_index,
                chunk_id=str(build_chunk_id(file.fileid, new_version, chunk.chunk_index)),
                page_start=chunk.page_start,
                page_end=chunk.page_end,
                word_start=chunk.word_start,
                word_end=chunk.word_end,
                word_count=chunk.word_count,
                text_checksum=chunk.text_checksum,
                clean_text=chunk.clean_text,
                extraction_version=settings.RAG_EXTRACTION_VERSION,
                cleaning_version=settings.RAG_CLEANING_VERSION,
                chunking_version=settings.RAG_CHUNKING_VERSION,
                embedding_model=settings.GEMINI_EMBEDDING_MODEL,
                embedding_dimensions=settings.EMBEDDING_DIMENSIONS,
                source_key=file.s3_key,
                original_filename=file.filename,
            )
        )

    db.add_all(rows)

    file.indexing_status = IndexingStatus.CHUNKED.value
    file.page_count = processed.page_count
    file.extracted_word_count = processed.extracted_word_count
    file.chunk_count = len(processed.chunks)
    file.indexed_chunk_count = 0
    file.extraction_version = settings.RAG_EXTRACTION_VERSION
    file.cleaning_version = settings.RAG_CLEANING_VERSION
    file.chunking_version = settings.RAG_CHUNKING_VERSION
    file.embedding_model = settings.GEMINI_EMBEDDING_MODEL
    file.embedding_dimensions = settings.EMBEDDING_DIMENSIONS
    file.rag_error_code = None
    file.rag_error_message = None

    db.commit()
    return new_version
```

### 12.4 Important Transaction Rule

Phase 3 writes should be one short database transaction.

Do this:

```text
Phase 2 extraction already complete
    |
    v
open DB transaction
    |
    v
insert chunk rows and update file_metadata
    |
    v
commit
```

Do not do this:

```text
open DB transaction
    |
    v
download S3 object
    |
    v
parse PDF
    |
    v
insert chunks
    |
    v
commit
```

Reason:

```text
S3 and PDF extraction can be slow.
Holding a database transaction open during slow work increases locks,
connection pressure, and failure blast radius.
```

## 13. Error Persistence

Create helper:

```python
def mark_rag_failure(
    db: Session,
    file: FileMetadata,
    code: str,
    message: str,
    retryable: bool,
) -> None:
    ...
```

Suggested behavior:

```python
def mark_rag_failure(
    db: Session,
    file: FileMetadata,
    code: str,
    message: str,
    retryable: bool,
) -> None:
    file.indexing_status = (
        IndexingStatus.FAILED_RETRYABLE.value
        if retryable
        else IndexingStatus.FAILED_TERMINAL.value
    )
    file.rag_error_code = code[:64]
    file.rag_error_message = message[:500]
    db.commit()
```

Mapping from Phase 2 exceptions:

```text
FileNotFoundError          -> OBJECT_NOT_FOUND, terminal
ValueError too large       -> PDF_TOO_LARGE, terminal
PdfExtractionError         -> PDF_PARSE_FAILED or NO_EXTRACTABLE_TEXT
NoExtractableTextError     -> NO_EXTRACTABLE_TEXT, terminal
Unexpected storage error   -> PDF_READ_FAILED, retryable
Unexpected bug             -> CHUNKING_FAILED, terminal until fixed
```

Fresher note:

```text
Retryable means "try again later; the same code might work."
Terminal means "trying again will probably fail until something changes."
```

## 14. Claiming Work Safely

When multiple background workers exist, two workers could try to process the same file.

Use a claim step.

```text
Worker A sees file PENDING
Worker B sees file PENDING
    |
    v
Only one should successfully change it to EXTRACTING
```

Suggested SQLAlchemy pattern:

```python
updated = (
    db.query(FileMetadata)
    .filter(
        FileMetadata.fileid == file_id,
        FileMetadata.userid == user_id,
        FileMetadata.indexing_status.in_([
            IndexingStatus.PENDING.value,
            IndexingStatus.FAILED_RETRYABLE.value,
        ]),
    )
    .update(
        {
            FileMetadata.indexing_status: IndexingStatus.EXTRACTING.value,
            FileMetadata.indexing_started_at: datetime.now(timezone.utc),
        },
        synchronize_session=False,
    )
)
db.commit()

if updated != 1:
    return False
```

Why this helps:

```text
The database update is atomic.
Only one worker gets updated == 1.
Other workers back off.
```

## 15. Active Version Cutover Helper

Phase 3 should define the cutover helper, but Phase 4 should call it after embeddings and Qdrant verification.

Suggested function:

```python
def activate_rag_index_version(
    db: Session,
    file: FileMetadata,
    index_version: int,
    indexed_chunk_count: int,
) -> None:
    ...
```

Behavior:

```text
verify chunk_count for file/version
    |
    v
verify indexed_chunk_count == chunk_count
    |
    v
update active_index_version
    |
    v
set indexing_status = INDEXED
    |
    v
increment user corpus revision
    |
    v
commit
```

Suggested implementation shape:

```python
def activate_rag_index_version(
    db: Session,
    file: FileMetadata,
    index_version: int,
    indexed_chunk_count: int,
) -> None:
    chunk_count = db.query(DocumentChunk).filter(
        DocumentChunk.file_id == file.fileid,
        DocumentChunk.index_version == index_version,
    ).count()

    if chunk_count == 0:
        raise ValueError("Cannot activate an index version with zero chunks.")
    if indexed_chunk_count != chunk_count:
        raise ValueError("Cannot activate before every chunk is indexed.")

    state = db.get(UserCorpusState, file.userid)
    if state is None:
        state = UserCorpusState(user_id=file.userid, corpus_revision=0)
        db.add(state)

    state.corpus_revision += 1

    file.active_index_version = index_version
    file.indexed_chunk_count = indexed_chunk_count
    file.indexing_status = IndexingStatus.INDEXED.value
    file.indexing_completed_at = datetime.now(timezone.utc)
    file.corpus_revision = state.corpus_revision

    db.commit()
```

This is the zero-downtime cutover:

```text
Before commit:
    active_index_version = 1
    queries see v1

During build:
    chunks v2 exist
    queries still see v1

Single commit:
    active_index_version = 2
    corpus_revision += 1

After commit:
    queries see v2
```

## 16. Worker Integration Plan

The existing worker currently performs metadata vector indexing. Phase 3 should add a separate RAG staging path.

Suggested worker-level flow:

```text
complete_upload()
    |
    v
background task starts
    |
    v
claim file for RAG extraction
    |
    v
run process_pdf_from_storage(s3_key)
    |
    v
stage_document_chunks(db, file, processed)
    |
    v
status = CHUNKED
    |
    v
Phase 4 will embed and index chunks
```

Keep existing metadata vector indexing until the project intentionally replaces it.

Practical options:

```text
Option A: Add sync_rag_chunks_in_background()
    Cleanest separation. Recommended.

Option B: Extend sync_vector_in_background()
    Faster but can tangle metadata indexing and RAG indexing.
```

Recommended:

```text
Add sync_rag_chunks_in_background() in indexing_worker.py or a new rag_worker.py.
```

Suggested signature:

```python
async def sync_rag_chunks_in_background(file_id: int, user_id: int) -> None:
    ...
```

Inside it:

```text
open DB session
load FileMetadata by fileid + userid
claim EXTRACTING
close/commit before S3/PDF work
run process_pdf_from_storage in threadpool
open DB session or reuse carefully
stage chunks in one transaction
handle typed errors
close session
```

Important:

```text
Do not pass clean_text through FastAPI responses in production yet.
Do not send chunks to Qdrant yet.
```

## 17. Retrieval Preview Query

Phase 5 will hydrate chunks after Qdrant search. Phase 3 can add and test the MySQL side now.

Suggested helper:

```python
def list_active_chunks_for_file(
    db: Session,
    user_id: int,
    file_id: int,
) -> list[DocumentChunk]:
    return (
        db.query(DocumentChunk)
        .join(FileMetadata, FileMetadata.fileid == DocumentChunk.file_id)
        .filter(
            DocumentChunk.user_id == user_id,
            DocumentChunk.file_id == file_id,
            DocumentChunk.index_version == FileMetadata.active_index_version,
            FileMetadata.userid == user_id,
            FileMetadata.status == FileStatus.ACTIVE.value,
            FileMetadata.indexing_status == IndexingStatus.INDEXED.value,
        )
        .order_by(DocumentChunk.chunk_index.asc())
        .all()
    )
```

This function may return an empty list during Phase 3 because active cutover waits for Phase 4. That is fine.

The important part is the filter shape:

```text
chunk.user_id == current user
file.userid == current user
chunk.index_version == file.active_index_version
file.status == active
file.indexing_status == indexed
```

## 18. Tests to Add

### 18.1 Model and Migration Tests

Test that models can be imported:

```powershell
uv run python -c "from app.database.db_models import DocumentChunk, UserCorpusState; print('models ok')"
```

If you have a test database, run:

```powershell
uv run alembic upgrade head
```

### 18.2 Deterministic ID Tests

```text
same file/version/chunk -> same UUID
different version       -> different UUID
different chunk_index   -> different UUID
UUID is valid v5 string
```

### 18.3 Persistence Service Tests

Use a test DB session.

Test:

```text
stage_document_chunks inserts all chunks
stage_document_chunks sets status CHUNKED
stage_document_chunks does not change active_index_version
stage_document_chunks stores source_key and original_filename
stage_document_chunks stores extraction/cleaning/chunking versions
stage_document_chunks stores embedding model/dimensions
retrying same version does not duplicate chunks
```

### 18.4 Failure Tests

Test:

```text
mark_rag_failure retryable -> FAILED_RETRYABLE
mark_rag_failure terminal  -> FAILED_TERMINAL
error code is capped at 64 chars
error message is capped at 500 chars
```

### 18.5 Cutover Tests

Test:

```text
activate with zero chunks fails
activate with indexed_chunk_count < chunk_count fails
activate valid version sets active_index_version
activate increments user_corpus_state.corpus_revision
activate copies revision to file_metadata.corpus_revision
```

### 18.6 Multi-Tenant Tests

Test:

```text
user A cannot list active chunks for user B's file
same file_id lookup with wrong user_id returns empty
hydrate/list helper always filters both chunk.user_id and file.userid
```

## 19. Development Order

Recommended implementation order:

```text
1. Update IndexingStatus enum with RAG lifecycle states
2. Add DocumentChunk and UserCorpusState SQLAlchemy models
3. Add FileMetadata RAG tracking columns
4. Generate Alembic migration
5. Review migration carefully for MySQL compatibility
6. Apply migration locally
7. Add build_chunk_id() helper and tests
8. Add persistence.py with stage_document_chunks()
9. Add failure and cutover helpers
10. Add focused unit/integration tests
11. Add optional worker staging path
12. Run existing file/search tests to confirm no regression
```

Why this order:

```text
Schema first
    |
    v
Persistence service second
    |
    v
Worker integration last
```

If the schema is wrong, it is cheaper to fix before worker code depends on it.

## 20. Commands

From backend:

```powershell
cd D:\Personal_Knowledge_Base\backend
```

Generate migration:

```powershell
uv run alembic revision --autogenerate -m "add rag document chunks"
```

Apply migration:

```powershell
uv run alembic upgrade head
```

Run targeted tests:

```powershell
uv run pytest tests/unit/services/rag tests/unit/services/test_s3_service.py
```

Run database/model tests after adding them:

```powershell
uv run pytest tests/unit/services/rag/test_persistence.py
```

Run broader backend tests:

```powershell
uv run pytest
```

## 21. Common Mistakes

### Mistake 1: Activating Too Early

Bad:

```text
insert chunks
set active_index_version immediately
```

Why bad:

```text
Phase 5 retrieval could see chunks that have no Qdrant vectors yet.
```

Good:

```text
insert chunks
status = CHUNKED
Phase 4 embeds/upserts vectors
verify count
then activate
```

### Mistake 2: Deleting Old Chunks Before New Version Is Ready

Bad:

```text
delete version 1
start building version 2
something fails
no usable version remains
```

Good:

```text
keep version 1 active
build version 2
activate version 2 only after verification
clean old version asynchronously later
```

### Mistake 3: Trusting Qdrant Payload Alone Later

Even though Phase 3 is MySQL work, design it for this later rule:

```text
Qdrant ranks candidates.
MySQL proves ownership, active version, and source text.
```

### Mistake 4: Holding DB Transactions During S3/PDF Work

Keep external work outside DB transactions.

```text
S3/PDF/Gemini/Qdrant = outside long DB transaction
short MySQL writes   = inside transaction
```

### Mistake 5: Forgetting Existing Names

This repo uses:

```text
file_metadata.fileid
file_metadata.userid
```

Do not write migrations assuming:

```text
file_metadata.id
file_metadata.user_id
```

## 22. Code Review Checklist

```text
[ ] FileMetadata has RAG tracking columns
[ ] DocumentChunk uses file_metadata.fileid foreign key
[ ] UserCorpusState uses users.id foreign key
[ ] document_chunks.clean_text is MEDIUMTEXT or equivalent
[ ] chunk_id has a unique constraint
[ ] (file_id, index_version, chunk_index) is unique
[ ] hydration index exists on (user_id, chunk_id, index_version)
[ ] build_chunk_id uses UUIDv5 and stable inputs
[ ] stage_document_chunks does not call S3, Gemini, or Qdrant
[ ] stage_document_chunks does not activate the version
[ ] active cutover helper increments corpus revision in same transaction
[ ] errors are persisted with clear codes/messages
[ ] worker claim step is atomic
[ ] tests cover versioning, failure, cutover, and tenant filters
[ ] existing metadata vector search is not broken
```

## 23. Phase 3 Definition of Done

Phase 3 is complete when:

- Alembic migration adds RAG tracking fields to `file_metadata`
- Alembic migration creates `document_chunks`
- Alembic migration creates `user_corpus_state`
- SQLAlchemy models match the applied schema
- deterministic chunk IDs are generated with UUIDv5
- Phase 2 `ProcessedDocument` chunks can be staged in MySQL
- staged chunks do not change `active_index_version`
- active cutover exists as a guarded transaction helper
- corpus revision increments only when active corpus changes
- RAG failures can be persisted with retryable/terminal status
- tests cover persistence, versioning, cutover, and multi-tenant filtering
- existing upload, metadata indexing, and search behavior still passes tests

## 24. Handoff to Phase 4

Phase 3 hands Phase 4 this durable state:

```text
file_metadata
|
+-- fileid = 10
+-- userid = 3
+-- active_index_version = 0 or old active version
+-- indexing_status = CHUNKED
+-- chunk_count = 12

document_chunks
|
+-- file_id = 10
+-- user_id = 3
+-- index_version = 1
+-- chunk_index = 0..11
+-- chunk_id = deterministic UUIDv5
+-- clean_text = source text
`-- embedding_model = gemini-embedding-2
```

Phase 4 will:

```text
read staged chunks
    |
    v
generate Gemini RETRIEVAL_DOCUMENT embeddings
    |
    v
upsert Qdrant points using chunk_id
    |
    v
verify indexed count
    |
    v
call activate_rag_index_version()
```

That is the handoff: Phase 3 makes chunks durable and versioned; Phase 4 makes them searchable.
