"""
backend/app/schemas/file.py

Pydantic schemas for file upload requests, metadata updates, and presigned URL responses.
"""
from typing import Any, Optional
from datetime import datetime
from pydantic import BaseModel, Field, HttpUrl, field_validator
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
    file_id: int = Field(..., alias="fileId")


class FileUploadCompleteRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    key: str = Field(..., min_length=1, max_length=500)
    filename: str = Field(default="", max_length=255)


class FileMetadataSchema(BaseModel):
    model_config = ConfigDict(populate_by_name=True, from_attributes=True)

    fileid: int = Field(..., alias="fileId")
    s3_key: str = Field(..., alias="s3Key")
    filename: str
    content_type: Optional[str] = Field(None, alias="contentType")
    size_bytes: Optional[int] = Field(None, alias="sizeBytes")
    status: str
    title: Optional[str] = None
    description: Optional[str] = None
    tags: Optional[str] = Field(None, max_length=50)
    is_indexed: bool = Field(False, alias="isIndexed")
    indexing_status: str = Field("pending", alias="indexingStatus")
    index_version: int = Field(1, alias="indexVersion")
    userid: int = Field(..., alias="userId")
    created_at: datetime = Field(..., alias="createdAt")
    updated_at: datetime = Field(..., alias="updatedAt")

    @field_validator("is_indexed", mode="before")
    @classmethod
    def default_is_indexed(cls, v: Any) -> bool:
        if v is None:
            return False
        return bool(v)

    @field_validator("indexing_status", mode="before")
    @classmethod
    def default_indexing_status(cls, v: Any) -> str:
        if not v or v is None:
            return "pending"
        return str(v)

    @field_validator("index_version", mode="before")
    @classmethod
    def default_index_version(cls, v: Any) -> int:
        if v is None:
            return 1
        return int(v)


class SearchResponseSchema(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    results: list[FileMetadataSchema]
    search_mode: str = Field(..., alias="searchMode")
    status: str = Field(...)


class FileUploadCompleteResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    verified: bool
    key: str
    message: str
    metadata: Optional[FileMetadataSchema] = None


class FileViewUrlRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    key: str = Field(..., min_length=1, max_length=500)


class FileViewUrlResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    view_url: HttpUrl = Field(..., alias="viewUrl")
    key: str
    expires_in: int


class FileMetadataUpdateRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    title: Optional[str] = Field(None, max_length=100)
    description: Optional[str] = Field(None, max_length=255)
    tags: Optional[str] = Field(None, max_length=50)
