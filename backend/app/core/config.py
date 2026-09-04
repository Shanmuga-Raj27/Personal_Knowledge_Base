"""
backend/app/core/config.py

Application settings loaded from environment variables.
Uses Pydantic Settings for validation and type safety.
"""
from pathlib import Path
from pydantic import Field, model_validator
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

    # Redis cache
    RAG_CACHE_ENABLED: bool = True
    REDIS_URL: str = "redis://localhost:6379/0"
    REDIS_SOCKET_TIMEOUT_SECONDS: float = 1.0
    REDIS_CONNECT_TIMEOUT_SECONDS: float = 1.0
    RAG_CACHE_TTL_SECONDS: int = 3600

    # Gemini reliability controls
    GEMINI_EMBEDDING_BATCH_SIZE: int = 16
    GEMINI_EMBEDDING_MAX_RETRIES: int = 3

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


settings = Settings()

