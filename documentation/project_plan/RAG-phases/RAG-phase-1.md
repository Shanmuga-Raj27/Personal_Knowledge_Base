# RAG Phase 1 - Configuration, Dependencies, Redis, and Qdrant Guard

## 1. Phase Goal

Phase 1 prepares the existing Personal Knowledge Base backend for the production RAG pipeline.

This phase does **not** implement full PDF chunking, document embeddings, retrieval, or answer generation yet. It creates the foundation that those later phases depend on:

- backend dependencies are installed with `uv`
- environment variables are explicit and documented
- Redis is available for future answer caching
- `config.py` exposes validated RAG settings
- Qdrant collection setup is guarded so wrong vector dimensions cannot silently corrupt the index
- the existing metadata search code can continue working while the new chunk-level RAG path is developed

The most important architectural rule in this phase:

```text
Do not write chunk vectors into Qdrant until the backend has verified that the
target collection uses exactly 768-dimensional cosine vectors.
```

Gemini `gemini-embedding-2` must be used with `output_dimensionality=768`.

## 2. Current Project Context

The current backend already has these important pieces:

```text
backend/
|-- pyproject.toml              # canonical Python dependency manifest
|-- uv.lock                     # uv lock file
|-- requirements.txt            # pinned export / compatibility file
`-- app/
    |-- core/config.py          # Pydantic settings
    |-- database/db_models.py   # SQLAlchemy User and FileMetadata
    |-- services/AWS/s3_service.py
    |-- services/AI/vector_service.py
    |-- workers/indexing_worker.py
    `-- apis/routes/
```

Existing vector search is metadata-level:

```text
File metadata
    |
    v
Gemini embedding of filename/title/tags/description
    |
    v
Qdrant point id = file_id
Qdrant payload = file_id, user_id, filename, title, tags, description
```

Production RAG will become chunk-level:

```text
PDF bytes from S3/B2
    |
    v
page text extraction
    |
    v
clean chunks stored in MySQL
    |
    v
Gemini 768d chunk embeddings
    |
    v
Qdrant point id = deterministic chunk UUID
Qdrant payload = user_id, file_id, index_version, chunk_index only
```

Phase 1 prepares both paths to coexist while the new path is built.

## 3. Target Phase 1 Architecture

```text
Developer machine
|
+-- FastAPI backend
|   |
|   +-- config.py
|   |   `-- reads others/.env
|   |
|   +-- vector_service.py
|   |   `-- checks Qdrant collection shape at startup/service init
|   |
|   +-- future RAG services
|       |-- PDF extraction uses PyMuPDF
|       |-- Redis cache uses redis-py
|       `-- Qdrant chunk collection uses 768d cosine vectors
|
+-- MySQL
|
+-- Qdrant
|
+-- Redis
|
`-- S3/B2 and Gemini external APIs
```

Phase 1 responsibility boundaries:

```text
+----------------------+-----------------------------+
| Component            | Phase 1 responsibility      |
+----------------------+-----------------------------+
| pyproject.toml       | Add RAG dependencies        |
| uv.lock              | Lock dependency versions    |
| requirements.txt     | Optional export for deploy  |
| others/.env          | Add runtime RAG settings    |
| config.py            | Validate settings centrally |
| Redis                | Install and smoke test      |
| Qdrant               | Create/check collection     |
| FastAPI routes       | No RAG route required yet   |
+----------------------+-----------------------------+
```

## 4. Dependencies to Install with uv

### 4.1 Required New Backend Packages

Run these commands from the backend folder:

```powershell
cd D:\Personal_Knowledge_Base\backend
uv add pymupdf redis
```

What they are for:

```text
+------------+---------------------------------------------------------+
| Package    | Why Phase 1 needs it                                   |
+------------+---------------------------------------------------------+
| pymupdf    | Provides the `fitz` module for future PDF text extraction |
| redis      | Official Redis Python client for future answer cache      |
+------------+---------------------------------------------------------+
```

The project already has these important RAG dependencies in `pyproject.toml`:

```text
fastapi
sqlalchemy / alembic / pymysql
boto3
google-genai
qdrant-client
tenacity
httpx
pydantic-settings
python-multipart
uvicorn
```

Do not add LangChain or LlamaIndex for this project. The RAG pipeline is intentionally native-SDK based.

### 4.2 Keep requirements.txt in Sync

`pyproject.toml` should be treated as the source of truth. If deployment still uses `requirements.txt`, regenerate it after `uv add`:

```powershell
cd D:\Personal_Knowledge_Base\backend
uv export --format requirements-txt --no-hashes --output-file requirements.txt
```

Expected result:

```text
backend/pyproject.toml includes pymupdf and redis
backend/uv.lock is updated
backend/requirements.txt includes pinned versions for pymupdf and redis
```

## 5. Redis Setup

Redis is used later as a fail-open answer cache. In Phase 1 we only install it, configure it, and confirm the backend can connect.

Future cache key shape:

```text
rag:answer:{user_id}:{corpus_revision}:{query_hash}
```

If Redis is down in later phases, RAG must still work by skipping cache and doing live retrieval.

### 5.1 Recommended Local Setup: Docker

If Docker Desktop is available, this is the simplest setup on Windows:

```powershell
docker run --name pkb-redis -p 6379:6379 -d redis:7-alpine
```

Check that Redis is running:

```powershell
docker ps
```

Smoke test:

```powershell
docker exec -it pkb-redis redis-cli ping
```

Expected output:

```text
PONG
```

Stop Redis when needed:

```powershell
docker stop pkb-redis
```

Start it again:

```powershell
docker start pkb-redis
```

### 5.2 Alternative Setup: Windows Package Manager

If Docker is not available, install Redis-compatible local server using Memurai or another Redis-compatible distribution.

For development, the backend only needs a Redis server reachable at:

```text
redis://localhost:6379/0
```

The exact server implementation is less important than using the official Python `redis` package from the backend.

### 5.3 Redis Settings for Development

Recommended values:

```env
REDIS_URL=redis://localhost:6379/0
REDIS_SOCKET_TIMEOUT_SECONDS=1.0
REDIS_CONNECT_TIMEOUT_SECONDS=1.0
RAG_CACHE_TTL_SECONDS=3600
RAG_CACHE_ENABLED=true
```

Why the timeouts are short:

```text
User asks a question
    |
    v
Try Redis cache
    |
    +-- Redis responds quickly --> use cached answer if valid
    |
    `-- Redis unavailable/slow --> skip cache and continue live retrieval
```

Redis should never be allowed to make a normal RAG request hang for many seconds.

## 6. Update others/.env

The backend currently loads environment variables from:

```python
SettingsConfigDict(env_file="../others/.env", extra="ignore")
```

That means when the backend runs from the `backend` folder, it reads:

```text
D:\Personal_Knowledge_Base\others\.env
```

Add these Phase 1 values to `others/.env`.

Do not commit real API keys or secrets.

```env
# RAG embedding settings
GEMINI_EMBEDDING_MODEL=gemini-embedding-2
GEMINI_GENERATION_MODEL=gemini-2.5-flash
EMBEDDING_DIMENSIONS=768

# Qdrant RAG collection
QDRANT_RAG_COLLECTION_NAME=document_chunks_v1
QDRANT_DISTANCE=COSINE

# PDF extraction limits
RAG_MAX_PDF_BYTES=52428800
RAG_EXTRACTION_VERSION=pdf-text-v1

# Text cleaning and chunking
RAG_CLEANING_VERSION=clean-v1
RAG_CHUNKING_VERSION=words-800-overlap-100-v1
RAG_CHUNK_WORDS=800
RAG_CHUNK_OVERLAP_WORDS=100

# Retrieval controls
RAG_DEFAULT_TOP_K=6
RAG_MAX_TOP_K=20
RAG_SCORE_THRESHOLD=0.35

# Redis cache
RAG_CACHE_ENABLED=true
REDIS_URL=redis://localhost:6379/0
REDIS_SOCKET_TIMEOUT_SECONDS=1.0
REDIS_CONNECT_TIMEOUT_SECONDS=1.0
RAG_CACHE_TTL_SECONDS=3600

# Gemini reliability controls
GEMINI_EMBEDDING_BATCH_SIZE=16
GEMINI_EMBEDDING_MAX_RETRIES=3
MAX_CONCURRENT_EMBEDDING_TASKS=5
```

Keep the existing values too:

```env
DATABASE_URL=...
AWS_ACCESS_KEY_ID=...
AWS_SECRET_ACCESS_KEY=...
AWS_REGION=...
AWS_ENDPOINT_URL=...
S3_BUCKET_NAME=...
GEMINI_API_KEY=...
QDRANT_HOST=http://localhost:6333
SECRET_KEY=...
```

Recommended Qdrant naming decision:

```text
QDRANT_COLLECTION_NAME=document_vault
    Existing metadata-level search collection.

QDRANT_RAG_COLLECTION_NAME=document_chunks_v1
    New chunk-level production RAG collection.
```

Keeping two names avoids mixing old file-level vectors and new chunk-level vectors.

## 7. Update backend/app/core/config.py

### 7.1 Design Rule

All RAG settings should be read from `settings`.

Do not scatter magic numbers like `768`, `800`, `100`, or `document_chunks_v1` across service files.

Bad:

```python
await client.create_collection(
    collection_name="document_chunks_v1",
    vectors_config=VectorParams(size=768, distance=Distance.COSINE),
)
```

Better:

```python
await client.create_collection(
    collection_name=settings.QDRANT_RAG_COLLECTION_NAME,
    vectors_config=VectorParams(
        size=settings.EMBEDDING_DIMENSIONS,
        distance=Distance.COSINE,
    ),
)
```

### 7.2 Proposed Settings Fields

Add these fields to the `Settings` class:

```python
    # RAG embedding settings
    GEMINI_EMBEDDING_MODEL: str = "gemini-embedding-2"
    GEMINI_GENERATION_MODEL: str = "gemini-2.5-flash"
    EMBEDDING_DIMENSIONS: int = 768

    # Qdrant RAG collection
    QDRANT_RAG_COLLECTION_NAME: str = "document_chunks_v1"
    QDRANT_DISTANCE: str = "COSINE"

    # PDF extraction limits
    RAG_MAX_PDF_BYTES: int = 50 * 1024 * 1024
    RAG_EXTRACTION_VERSION: str = "pdf-text-v1"

    # Text cleaning and chunking
    RAG_CLEANING_VERSION: str = "clean-v1"
    RAG_CHUNKING_VERSION: str = "words-800-overlap-100-v1"
    RAG_CHUNK_WORDS: int = 800
    RAG_CHUNK_OVERLAP_WORDS: int = 100

    # Retrieval controls
    RAG_DEFAULT_TOP_K: int = 6
    RAG_MAX_TOP_K: int = 20
    RAG_SCORE_THRESHOLD: float = 0.35

    # Redis cache
    RAG_CACHE_ENABLED: bool = True
    REDIS_URL: str = "redis://localhost:6379/0"
    REDIS_SOCKET_TIMEOUT_SECONDS: float = 1.0
    REDIS_CONNECT_TIMEOUT_SECONDS: float = 1.0
    RAG_CACHE_TTL_SECONDS: int = 3600

    # Gemini reliability controls
    GEMINI_EMBEDDING_BATCH_SIZE: int = 16
    GEMINI_EMBEDDING_MAX_RETRIES: int = 3
```

### 7.3 Recommended Validation

Add validation so a wrong environment value fails early.

Example:

```python
from pydantic import Field, model_validator
```

Then tighten the fields:

```python
    EMBEDDING_DIMENSIONS: int = Field(default=768, ge=1)
    RAG_CHUNK_WORDS: int = Field(default=800, ge=1)
    RAG_CHUNK_OVERLAP_WORDS: int = Field(default=100, ge=0)
    RAG_DEFAULT_TOP_K: int = Field(default=6, ge=1)
    RAG_MAX_TOP_K: int = Field(default=20, ge=1)
    RAG_SCORE_THRESHOLD: float = Field(default=0.35, ge=0.0, le=1.0)
```

Add a model validator:

```python
    @model_validator(mode="after")
    def validate_rag_settings(self) -> "Settings":
        if self.EMBEDDING_DIMENSIONS != 768:
            raise ValueError("EMBEDDING_DIMENSIONS must be 768 for gemini-embedding-2")
        if self.RAG_CHUNK_OVERLAP_WORDS >= self.RAG_CHUNK_WORDS:
            raise ValueError("RAG_CHUNK_OVERLAP_WORDS must be smaller than RAG_CHUNK_WORDS")
        if self.RAG_DEFAULT_TOP_K > self.RAG_MAX_TOP_K:
            raise ValueError("RAG_DEFAULT_TOP_K must be <= RAG_MAX_TOP_K")
        if self.QDRANT_DISTANCE.upper() != "COSINE":
            raise ValueError("QDRANT_DISTANCE must be COSINE")
        return self
```

Why this matters:

```text
Wrong .env value
    |
    v
Backend startup fails immediately
    |
    v
Developer fixes configuration before any bad vectors are written
```

This is much safer than discovering bad data after indexing many files.

## 8. Qdrant Collection Guard

### 8.1 Problem

The current `vector_service.py` creates a Qdrant collection if it does not exist. For production RAG, that is not enough.

The backend must also reject an existing collection if it has the wrong shape.

Wrong examples:

```text
collection exists with size 1536        -> reject
collection exists with dot distance     -> reject
collection exists with euclid distance  -> reject
collection stores old file-level points -> use a separate RAG collection
```

### 8.2 Desired Behavior

```text
Backend starts
    |
    v
Check Qdrant collection document_chunks_v1
    |
    +-- missing
    |       |
    |       v
    |   create 768d cosine collection and payload indexes
    |
    +-- exists and matches 768d cosine
    |       |
    |       v
    |   continue startup
    |
    `-- exists but wrong size/distance
            |
            v
        raise RuntimeError and stop
```

### 8.3 Payload Indexes

Create payload indexes for fields used in filters:

```text
user_id          integer
file_id          integer
index_version    integer
```

The new RAG payload should remain small:

```python
{
    "user_id": 123,
    "file_id": 456,
    "index_version": 1,
    "chunk_index": 0,
}
```

Do not store chunk text in Qdrant. MySQL will be the source of truth for text.

### 8.4 Suggested Service Function

Add a new function in `backend/app/services/AI/vector_service.py`, or better, split future RAG vector code into `rag_vector_service.py` to avoid mixing metadata search and chunk search.

Suggested function:

```python
async def ensure_rag_collection() -> None:
    q_client = get_qdrant_client()
    collection_name = settings.QDRANT_RAG_COLLECTION_NAME

    existing = await q_client.collection_exists(collection_name=collection_name)
    expected_distance = models.Distance.COSINE

    if not existing:
        await q_client.create_collection(
            collection_name=collection_name,
            vectors_config=models.VectorParams(
                size=settings.EMBEDDING_DIMENSIONS,
                distance=expected_distance,
            ),
        )
        for field_name in ("user_id", "file_id", "index_version"):
            await q_client.create_payload_index(
                collection_name=collection_name,
                field_name=field_name,
                field_schema=models.PayloadSchemaType.INTEGER,
            )
        return

    info = await q_client.get_collection(collection_name=collection_name)
    vectors = info.config.params.vectors

    if vectors.size != settings.EMBEDDING_DIMENSIONS:
        raise RuntimeError(
            f"Qdrant collection {collection_name} has vector size {vectors.size}; "
            f"expected {settings.EMBEDDING_DIMENSIONS}"
        )

    if vectors.distance != expected_distance:
        raise RuntimeError(
            f"Qdrant collection {collection_name} has distance {vectors.distance}; "
            f"expected {expected_distance}"
        )
```

Note for junior developers:

```text
Qdrant collection shape is like a database column type.
You cannot safely put 768-number vectors into a collection designed for
1536-number vectors. It is a schema mismatch, not a warning.
```

### 8.5 Startup Integration

Wherever the FastAPI app is created, call the guard during startup/lifespan:

```python
from contextlib import asynccontextmanager
from fastapi import FastAPI

from app.services.AI.vector_service import close_qdrant_client, ensure_rag_collection


@asynccontextmanager
async def lifespan(app: FastAPI):
    await ensure_rag_collection()
    yield
    await close_qdrant_client()


app = FastAPI(lifespan=lifespan)
```

If this project later keeps metadata search and RAG collection setup separate, startup can call both:

```python
await init_qdrant_collection()   # existing metadata search collection
await ensure_rag_collection()    # new chunk-level RAG collection
```

## 9. Redis Client Guard

Phase 1 can add a small Redis client factory without using it for answers yet.

Suggested file:

```text
backend/app/services/cache/redis_cache.py
```

Suggested behavior:

```text
get_redis_client()
    |
    v
uses REDIS_URL and short socket/connect timeouts

ping_redis()
    |
    +-- success -> log available
    `-- failure -> log warning, continue backend startup
```

Example:

```python
import logging
from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.core.config import settings

logger = logging.getLogger(__name__)

_redis_client: Redis | None = None


def get_redis_client() -> Redis:
    global _redis_client
    if _redis_client is None:
        _redis_client = Redis.from_url(
            settings.REDIS_URL,
            socket_timeout=settings.REDIS_SOCKET_TIMEOUT_SECONDS,
            socket_connect_timeout=settings.REDIS_CONNECT_TIMEOUT_SECONDS,
            decode_responses=True,
        )
    return _redis_client


async def ping_redis() -> bool:
    if not settings.RAG_CACHE_ENABLED:
        return False
    try:
        await get_redis_client().ping()
        return True
    except RedisError as exc:
        logger.warning("Redis unavailable; RAG cache will be skipped: %s", exc)
        return False
```

Important rule:

```text
Redis failure is not a backend startup failure.
Qdrant schema mismatch is a backend startup failure.
```

Reason:

```text
Redis is an optimization.
Qdrant collection shape is data correctness.
```

## 10. Development Order

Follow this order to develop Phase 1 safely:

```text
1. Create a git branch
2. Install dependencies with uv
3. Update .env values
4. Update config.py settings and validation
5. Add Redis client smoke check
6. Add Qdrant RAG collection guard
7. Wire guard into app startup/lifespan
8. Run smoke checks
9. Export requirements.txt if needed
10. Commit Phase 1
```

Commands:

```powershell
cd D:\Personal_Knowledge_Base
git checkout -b feature/rag-phase-1-foundation

cd backend
uv add pymupdf redis
uv export --format requirements-txt --no-hashes --output-file requirements.txt
```

## 11. Local Smoke Checks

### 11.1 Python Imports

From `backend`:

```powershell
uv run python -c "import fitz, redis, qdrant_client; print('imports ok')"
```

Expected:

```text
imports ok
```

### 11.2 Settings Load

```powershell
uv run python -c "from app.core.config import settings; print(settings.EMBEDDING_DIMENSIONS, settings.QDRANT_RAG_COLLECTION_NAME)"
```

Expected:

```text
768 document_chunks_v1
```

### 11.3 Redis Ping

```powershell
uv run python -c "import asyncio; from redis.asyncio import Redis; r=Redis.from_url('redis://localhost:6379/0'); print(asyncio.run(r.ping())); asyncio.run(r.aclose())"
```

Expected:

```text
True
```

If this one-liner is awkward in PowerShell, use a small temporary script or rely on:

```powershell
docker exec -it pkb-redis redis-cli ping
```

### 11.4 Qdrant Collection Check

After the backend guard runs once, inspect Qdrant:

```powershell
curl http://localhost:6333/collections/document_chunks_v1
```

Expected shape:

```text
vectors.size = 768
vectors.distance = Cosine
```

## 12. Common Mistakes and How to Avoid Them

### Mistake 1: Mixing Metadata Vectors and Chunk Vectors

Do not put new RAG chunk vectors into `document_vault` if that collection is already used for file metadata search.

Use:

```text
document_vault       -> existing metadata search
document_chunks_v1   -> new RAG chunk search
```

### Mistake 2: Changing Embedding Dimensions Without New Collection

If dimensions change, create a new collection.

```text
768d vectors  -> document_chunks_v1
1536d vectors -> different collection required
```

For this project, Phase 1 locks the value at 768.

### Mistake 3: Treating Redis as Required

Redis improves speed. It should not decide whether RAG works.

Later retrieval flow:

```text
try cache
    |
    +-- hit  -> return cached answer
    |
    +-- miss -> retrieve from Qdrant/MySQL and generate
    |
    `-- error -> retrieve from Qdrant/MySQL and generate
```

### Mistake 4: Hardcoding Settings in Services

Keep service code configurable:

```text
.env -> config.py -> service code
```

Not:

```text
service code -> hidden magic number
```

### Mistake 5: Logging Secrets

Never log:

```text
GEMINI_API_KEY
AWS_SECRET_ACCESS_KEY
SECRET_KEY
presigned URLs
Redis passwords
```

## 13. Phase 1 Definition of Done

Phase 1 is complete when:

- `uv add pymupdf redis` has updated `backend/pyproject.toml` and `backend/uv.lock`
- `backend/requirements.txt` is regenerated if the project still uses it for deployment
- `others/.env` contains Redis, RAG, Gemini embedding, chunking, and Qdrant RAG collection settings
- `backend/app/core/config.py` exposes all Phase 1 settings
- invalid RAG settings fail during settings load
- Redis can be started locally and pinged
- Qdrant collection `document_chunks_v1` is created as 768d cosine if missing
- backend startup fails if `document_chunks_v1` exists with wrong vector size or distance
- existing file metadata search is not broken
- no secrets are committed

## 14. What Comes Next in Phase 2

After Phase 1, the project is ready to implement:

```text
S3/B2 PDF read
    |
    v
PyMuPDF page extraction
    |
    v
text normalization
    |
    v
repeated header/footer stripping
    |
    v
800-word chunks with 100-word overlap
    |
    v
chunk rows in MySQL
```

Phase 1 is mostly infrastructure work, but it protects all future RAG data. A strict configuration and collection guard is much cheaper than cleaning up a polluted vector index later.
