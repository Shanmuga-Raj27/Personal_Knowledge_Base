"""
backend/app/services/AWS/s3_service.py

S3 service for generating presigned PUT URLs.
Keeps AWS logic isolated from API routes.
"""
import os
import uuid
import re
from urllib.parse import unquote

import boto3
from botocore.exceptions import ClientError, BotoCoreError

from app.core.config import settings

ALLOWED_MIME_TYPES = {
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "text/plain",
    "text/markdown",
}


def _sanitize_filename(filename: str) -> str:
    """Strip path components and replace unsafe characters."""
    filename = os.path.basename(filename)
    filename = unquote(filename)
    filename = re.sub(r"[^a-zA-Z0-9_.-]", "_", filename)
    return filename.strip("._") or "file"


def generate_safe_key(filename: str) -> str:
    """Create a unique S3 object key from the original filename."""
    safe_name = _sanitize_filename(filename)
    unique_id = uuid.uuid4().hex
    return f"uploads/{unique_id}_{safe_name}"


def validate_mime_type(content_type: str) -> bool:
    """Check if the content type is allowed."""
    return content_type in ALLOWED_MIME_TYPES


_s3_client_instance = None


def _get_s3_client():
    """Retrieve or initialize the singleton boto3 S3 client with connection pooling."""
    global _s3_client_instance
    if _s3_client_instance is None:
        _s3_client_instance = boto3.client(
            "s3",
            region_name=settings.AWS_REGION,
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
            endpoint_url=settings.AWS_ENDPOINT_URL,
        )
    return _s3_client_instance


def create_presigned_put_url(filename: str, content_type: str) -> dict:
    """Generate a presigned PUT URL for direct S3 upload."""
    if not validate_mime_type(content_type):
        raise ValueError(f"Unsupported file type: {content_type}")

    key = generate_safe_key(filename)
    s3_client = _get_s3_client()

    try:
        response = s3_client.generate_presigned_url(
            ClientMethod="put_object",
            Params={
                "Bucket": settings.S3_BUCKET_NAME,
                "Key": key,
                "ContentType": content_type,
            },
            ExpiresIn=settings.S3_PRESIGNED_URL_EXPIRY,
        )
    except (ClientError, BotoCoreError) as exc:
        raise RuntimeError("Failed to generate presigned URL.") from exc

    return {
        "upload_url": response,
        "key": key,
        "expires_in": settings.S3_PRESIGNED_URL_EXPIRY,
    }


def check_object_exists(key: str) -> bool:
    """Check if an object exists in the S3 bucket using head_object."""
    s3_client = _get_s3_client()
    try:
        s3_client.head_object(Bucket=settings.S3_BUCKET_NAME, Key=key)
        return True
    except ClientError as exc:
        error_code = exc.response.get("Error", {}).get("Code", "")
        status_code = exc.response.get("ResponseMetadata", {}).get("HTTPStatusCode", 0)
        if error_code in ("404", "NoSuchKey", "NotFound") or status_code == 404:
            return False
        raise RuntimeError(f"Failed to check S3 object existence: {str(exc)}") from exc
    except BotoCoreError as exc:
        raise RuntimeError("Failed to check S3 object existence.") from exc


def create_presigned_get_url(key: str, expires_in: int = 300) -> dict:
    """Generate a short-lived presigned GET URL to view/download an object from S3."""
    if not check_object_exists(key):
        raise FileNotFoundError(f"File object with key '{key}' does not exist in storage.")

    s3_client = _get_s3_client()
    try:
        response = s3_client.generate_presigned_url(
            ClientMethod="get_object",
            Params={
                "Bucket": settings.S3_BUCKET_NAME,
                "Key": key,
            },
            ExpiresIn=expires_in,
        )
    except (ClientError, BotoCoreError) as exc:
        raise RuntimeError("Failed to generate presigned GET URL.") from exc

    return {
        "view_url": response,
        "key": key,
        "expires_in": expires_in,
    }


def get_object_metadata(key: str) -> dict:
    """Fetch object metadata from S3 bucket using head_object."""
    s3_client = _get_s3_client()
    try:
        response = s3_client.head_object(Bucket=settings.S3_BUCKET_NAME, Key=key)
        return {
            "size_bytes": response.get("ContentLength", 0),
            "content_type": response.get("ContentType"),
        }
    except ClientError as exc:
        status_code = exc.response.get("ResponseMetadata", {}).get("HTTPStatusCode", 0)
        error_code = exc.response.get("Error", {}).get("Code", "")
        if error_code in ("404", "NoSuchKey", "NotFound") or status_code == 404:
            raise FileNotFoundError(f"File object with key '{key}' does not exist in storage.") from exc
        raise RuntimeError(f"Failed to fetch S3 object metadata: {str(exc)}") from exc
    except BotoCoreError as exc:
        raise RuntimeError("Failed to fetch S3 object metadata.") from exc


def delete_s3_object(key: str) -> None:
    """Delete an object from S3/Backblaze B2 storage bucket."""
    s3_client = _get_s3_client()
    try:
        s3_client.delete_object(Bucket=settings.S3_BUCKET_NAME, Key=key)
    except (ClientError, BotoCoreError) as exc:
        raise RuntimeError(f"Failed to delete S3 object '{key}': {str(exc)}") from exc



