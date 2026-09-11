"""
backend/app/core/config.py

Application settings loaded from environment variables.
Uses Pydantic Settings for validation and type safety.
"""
from pathlib import Path
from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_ENV_FILE = Path(__file__).resolve().parents[3] / "others" / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=[
            str(_ENV_FILE),
            "../others/.env",
            "others/.env",
        ],
        extra="ignore",
    )

    DATABASE_URL: str
    AWS_ACCESS_KEY_ID: str
    AWS_SECRET_ACCESS_KEY: str
    AWS_REGION: str = "ap-south-1"
    AWS_ENDPOINT_URL: str | None = None
    S3_BUCKET_NAME: str
    S3_PRESIGNED_URL_EXPIRY: int = 3600
    CORS_ORIGINS: list[str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]
    GEMINI_API_KEY: str | None = None
    QDRANT_HOST: str = "http://localhost:6333"
    QDRANT_COLLECTION_NAME: str = "document_vault"
    VITE_API_URL: str = "http://localhost:8000"
    SECRET_KEY: str

    # Performance & Reliability Pool & Concurrency Controls
    DATABASE_POOL_SIZE: int = 20
    DATABASE_MAX_OVERFLOW: int = 40
    DATABASE_POOL_TIMEOUT: int = 30
    DATABASE_POOL_RECYCLE: int = 1800
    GEMINI_API_TIMEOUT_SECONDS: float = 15.0
    MAX_CONCURRENT_EMBEDDING_TASKS: int = 5

    # RAG embedding settings
    GEMINI_EMBEDDING_MODEL: str = "gemini-embedding-2"
    GEMINI_GENERATION_MODEL: str = "gemini-3.6-flash"
    EMBEDDING_DIMENSIONS: int = Field(default=768, ge=1)

    # Qdrant RAG collection
    QDRANT_RAG_COLLECTION_NAME: str = "document_chunks_v1"
    QDRANT_DISTANCE: str = "COSINE"

    # PDF extraction limits
    RAG_MAX_PDF_BYTES: int = Field(default=50 * 1024 * 1024, ge=1024)
    RAG_EXTRACTION_VERSION: str = "pdf-text-v1"

    # Text cleaning and chunking
    RAG_CLEANING_VERSION: str = "clean-v1"
    RAG_CHUNKING_VERSION: str = "words-800-overlap-100-v1"
    RAG_CHUNK_WORDS: int = Field(default=800, ge=1)
    RAG_CHUNK_OVERLAP_WORDS: int = Field(default=100, ge=0)

    # Retrieval controls
    RAG_DEFAULT_TOP_K: int = Field(default=6, ge=1)
    RAG_MAX_TOP_K: int = Field(default=20, ge=1)
    RAG_SCORE_THRESHOLD: float = Field(default=0.35, ge=0.0, le=1.0)

    # Redis cache — TTL extended to 24h so same query/file hits across
    # browser sessions within a day; corpus_revision still invalidates on re-index.
    RAG_CACHE_ENABLED: bool = True
    REDIS_URL: str = "redis://localhost:6379/0"
    REDIS_SOCKET_TIMEOUT_SECONDS: float = 1.0
    REDIS_CONNECT_TIMEOUT_SECONDS: float = 1.0
    RAG_CACHE_TTL_SECONDS: int = 86400

    # Phase 5 - Generation and context budget
    RAG_CONTEXT_BUDGET_TOKENS: int = Field(default=3000, ge=500)
    RAG_PROMPT_VERSION: str = "v1"
    RAG_MAX_PER_FILE_CONTRIBUTION: int = Field(default=3, ge=1)
    RAG_GENERATION_TEMPERATURE: float = Field(default=0.2, ge=0.0, le=2.0)

    # Phase 7 - Metrics and evaluation
    # Master switch for the admin-writeable /system/rag-metrics surface and
    # the in-process metric counters. Default OFF: observability is opt-in and
    # never changes behaviour. The batch evaluation script reads this flag to
    # decide whether to write the local JSON report.
    RAG_METRICS_ENABLED: bool = False

    # Gemini reliability controls (Phase 4 canonical defaults)
    GEMINI_EMBEDDING_BATCH_SIZE: int = Field(default=64, ge=1, le=128)
    GEMINI_EMBEDDING_MAX_RETRIES: int = Field(default=5, ge=0, le=10)
    RAG_EMBEDDING_BATCH_SIZE: int = Field(default=64, ge=1, le=128)
    RAG_EMBEDDING_CONCURRENCY: int = Field(default=4, ge=1, le=32)
    RAG_MAX_RETRIES: int = Field(default=5, ge=0, le=10)
    RAG_BACKOFF_BASE: float = Field(default=1.0, ge=0.0, le=10.0)
    # Aliases for RAG-phase-4 doc naming (typo-tolerant)
    RAG_QDRANT_COLLECTION: str | None = None
    RAG_QDANT_COLLECTION: str | None = None

    @field_validator("AWS_ENDPOINT_URL", mode="before")
    @classmethod
    def empty_endpoint_to_none(cls, v):
        """Convert empty/whitespace endpoint values to None so boto3 uses the default AWS endpoint."""
        if isinstance(v, str) and not v.strip():
            return None
        return v

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
        # Phase 4: keep legacy and canonical batch/retry fields in sync
        if self.RAG_EMBEDDING_BATCH_SIZE == 64 and self.GEMINI_EMBEDDING_BATCH_SIZE != 64:
            object.__setattr__(self, "RAG_EMBEDDING_BATCH_SIZE", self.GEMINI_EMBEDDING_BATCH_SIZE)
        if self.RAG_MAX_RETRIES == 5 and self.GEMINI_EMBEDDING_MAX_RETRIES != 5:
            object.__setattr__(self, "RAG_MAX_RETRIES", self.GEMINI_EMBEDDING_MAX_RETRIES)
        if self.RAG_EMBEDDING_CONCURRENCY == 4 and self.MAX_CONCURRENT_EMBEDDING_TASKS != 5:
            # legacy default was 5, new canonical is 4 — propagate only if user changed legacy
            if self.MAX_CONCURRENT_EMBEDDING_TASKS != 5:
                object.__setattr__(self, "RAG_EMBEDDING_CONCURRENCY", self.MAX_CONCURRENT_EMBEDDING_TASKS)
        # Alias collection names for Phase 4 doc compatibility
        alias = self.RAG_QDRANT_COLLECTION or self.RAG_QDANT_COLLECTION
        if alias:
            object.__setattr__(self, "QDRANT_RAG_COLLECTION_NAME", alias)
        return self

    # ── Phase 4 compatibility properties ──────────────────────────────────
    @property
    def RAG_TOP_K(self) -> int:
        """Alias for RAG_DEFAULT_TOP_K (Phase 4 doc naming)."""
        return self.RAG_DEFAULT_TOP_K

    @property
    def RAG_SCORE_THRESHOLD_ALIAS(self) -> float:
        return self.RAG_SCORE_THRESHOLD

    @property
    def RAG_QDRANT_COLLECTION_RESOLVED(self) -> str:
        return self.QDRANT_RAG_COLLECTION_NAME


settings = Settings()

