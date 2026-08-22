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


def create_presigned_put_url(filename: str, content_type: str) -> dict:
    """Generate a presigned PUT URL for direct S3 upload."""
    if not validate_mime_type(content_type):
        raise ValueError(f"Unsupported file type: {content_type}")

    key = generate_safe_key(filename)

    s3_client = boto3.client(
        "s3",
        region_name=settings.AWS_REGION,
        aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
        aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
    )

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
