"""
backend/app/apis/routes/upload_file.py

API route for generating presigned S3 upload URLs.
"""
from fastapi import APIRouter, HTTPException, status

from app.schemas.file import (
    FileUploadRequest,
    PresignedUrlResponse,
    FileUploadCompleteRequest,
    FileUploadCompleteResponse,
    FileViewUrlRequest,
    FileViewUrlResponse,
)
from app.services.AWS.s3_service import (
    create_presigned_put_url,
    check_object_exists,
    create_presigned_get_url,
)

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


@router.post("/upload-complete", response_model=FileUploadCompleteResponse)
async def complete_upload(payload: FileUploadCompleteRequest):
    """Verify that an uploaded file exists in S3 object storage."""
    try:
        exists = check_object_exists(payload.key)
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error during file upload verification.",
        ) from exc

    if not exists:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="File verification failed. Object not found in storage.",
        )

    return FileUploadCompleteResponse(
        verified=True,
        key=payload.key,
        message="File upload verified successfully in storage.",
    )


@router.post("/view-url", response_model=FileViewUrlResponse)
async def get_view_url(payload: FileViewUrlRequest):
    """Generate a short-lived presigned S3 GET URL to view or download a file."""
    try:
        result = create_presigned_get_url(key=payload.key)
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate view URL.",
        ) from exc

    return FileViewUrlResponse(**result)

