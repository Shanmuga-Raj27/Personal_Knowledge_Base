"""
backend/app/core/config.py

Application settings loaded from environment variables.
Uses Pydantic Settings for validation and type safety.
"""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file="../others/.env", extra="ignore")

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


settings = Settings()

