"""
backend/app/apis/routes/upload_file.py

API route for generating presigned S3 upload URLs.
"""
from fastapi import APIRouter, HTTPException, status

from app.schemas.file import FileUploadRequest, PresignedUrlResponse
from app.services.AWS.s3_service import create_presigned_put_url

router = APIRouter(prefix="/files", tags=["files"])


@router.post("/upload-url", response_model=PresignedUrlResponse)
async def get_upload_url(payload: FileUploadRequest):
    """Generate a presigned S3 PUT URL for direct file upload."""
    try:
        result = create_presigned_put_url(
            filename=payload.filename,
            content_type=payload.content_type,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate upload URL.",
        ) from exc

    return PresignedUrlResponse(**result)
