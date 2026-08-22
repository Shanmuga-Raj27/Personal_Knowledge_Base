"""
backend/app/schemas/file.py

Pydantic schemas for file upload requests and presigned URL responses.
"""
# backend/app/schemas/file.py
from pydantic import BaseModel, Field, HttpUrl
from pydantic.config import ConfigDict

class FileUploadRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    filename: str = Field(..., min_length=1, max_length=255)
    content_type: str = Field(..., alias="contentType")

class PresignedUrlResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    upload_url: HttpUrl = Field(..., alias="uploadUrl")
    key: str
    expires_in: int
