"""
backend/app/core/config.py

Application settings loaded from environment variables.
Uses Pydantic Settings for validation and type safety.
"""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file="../others/.env", extra="ignore")

    AWS_ACCESS_KEY_ID: str
    AWS_SECRET_ACCESS_KEY: str
    AWS_REGION: str = "ap-south-1"
    S3_BUCKET_NAME: str
    S3_PRESIGNED_URL_EXPIRY: int = 3600


settings = Settings()
