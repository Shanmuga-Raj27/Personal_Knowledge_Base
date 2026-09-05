"""
backend/app/apis/routes/document_routes.py

Route handlers for document management operations:
- Upload presigned URL generation & verification handshake
- View presigned GET URL generation
- Listing user documents with pagination
- Metadata updates with automatic vector re-indexing trigger
- Safe document deletion with S3 & Qdrant consistency checks
"""
import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, status, Depends, BackgroundTasks, Query
from fastapi.concurrency import run_in_threadpool
from sqlalchemy.orm import Session

from app.auth.auth_dependencies import get_current_user
from app.database import get_db
from app.database.db_models import FileMetadata, User
from app.schemas.enums import FileStatus, IndexingStatus
from app.schemas.file import (
    FileUploadRequest,
    PresignedUrlResponse,
    FileUploadCompleteRequest,
    FileUploadCompleteResponse,
    FileViewUrlRequest,
    FileViewUrlResponse,
    FileMetadataSchema,
    FileMetadataUpdateRequest,
    PaginatedFilesResponse,
)
from app.services.AWS.s3_service import (
    create_presigned_put_url,
    create_presigned_get_url,
    get_object_metadata,
    delete_s3_object,
)
from app.services.AI.vector_service import delete_file_vector
from app.workers.indexing_worker import sync_vector_in_background
from app.workers.rag_worker import sync_rag_chunks_in_background

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/files", tags=["files"])


@router.post("/upload-url", response_model=PresignedUrlResponse)
async def get_upload_url(
    payload: FileUploadRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Generate a presigned S3 PUT URL and create a pending metadata record assigned to current user."""
    try:
        result = await run_in_threadpool(
            create_presigned_put_url,
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

    # Insert pending row in database bound to current_user.id
    try:
        db_file = FileMetadata(
            s3_key=result["key"],
            filename=payload.filename,
            content_type=payload.content_type,
            status=FileStatus.PENDING.value,
            size_bytes=0,
            userid=current_user.id,
        )
        db.add(db_file)
        db.commit()
        db.refresh(db_file)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database error creating pending file record: {str(exc)}",
        ) from exc

    result["file_id"] = db_file.fileid
    return PresignedUrlResponse(**result)


@router.post("/upload-complete", response_model=FileUploadCompleteResponse)
async def complete_upload(
    payload: FileUploadCompleteRequest,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Verify that an uploaded file exists in S3 storage and activate its database record for current user."""
    db_file = (
        db.query(FileMetadata)
        .filter(
            FileMetadata.s3_key == payload.key,
            FileMetadata.userid == current_user.id,
        )
        .first()
    )
    if not db_file:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="File record not found in database or access denied.",
        )

    try:
        meta = await run_in_threadpool(get_object_metadata, payload.key)
        # Update database row to active
        db_file.status = FileStatus.ACTIVE.value
        db_file.size_bytes = meta["size_bytes"]
        db_file.indexing_status = IndexingStatus.INDEXING.value
        db.commit()
        db.refresh(db_file)

        # Offload AI vector embedding generation & Qdrant indexing to background worker.
        # s3_key is passed so Phase 2 RAG extraction can also run (logging-only until Phase 3).
        background_tasks.add_task(
            sync_vector_in_background,
            file_id=db_file.fileid,
            user_id=current_user.id,
            filename=db_file.filename,
            title=db_file.title,
            description=db_file.description,
            tags=db_file.tags,
            target_version=db_file.index_version,
            s3_key=db_file.s3_key,
        )

        # Offload RAG chunking pipeline to separate background worker (Phase 3).
        # This runs the full extraction → cleaning → chunking → MySQL staging path.
        # Does NOT call Gemini/Qdrant; those are Phase 4.
        background_tasks.add_task(
            sync_rag_chunks_in_background,
            file_id=db_file.fileid,
            user_id=current_user.id,
        )
    except FileNotFoundError as exc:
        # Mark as failed in DB
        db_file.status = FileStatus.FAILED.value
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="File verification failed. Object not found in storage.",
        ) from exc
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error during file upload verification.",
        ) from exc

    return FileUploadCompleteResponse(
        verified=True,
        key=payload.key,
        message="File upload verified successfully in storage.",
        metadata=db_file,
    )


@router.post("/view-url", response_model=FileViewUrlResponse)
async def get_view_url(
    payload: FileViewUrlRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Generate a short-lived presigned S3 GET URL to view or download a file owned by current user."""
    db_file = (
        db.query(FileMetadata)
        .filter(
            FileMetadata.s3_key == payload.key,
            FileMetadata.userid == current_user.id,
        )
        .first()
    )
    if not db_file:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="File record not found or access denied.",
        )

    try:
        result = await run_in_threadpool(create_presigned_get_url, key=payload.key)
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


@router.get("", response_model=PaginatedFilesResponse)
async def list_files(
    limit: Optional[int] = Query(default=None, ge=1, le=200),
    offset: Optional[int] = Query(default=None, ge=0),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List active files belonging strictly to the authenticated user with optional limit/offset pagination."""
    query = db.query(FileMetadata).filter(
        FileMetadata.status == FileStatus.ACTIVE.value,
        FileMetadata.userid == current_user.id,
    )

    if isinstance(limit, int):
        total = query.count()
        eff_offset = offset if isinstance(offset, int) else 0
        files = (
            query.order_by(FileMetadata.created_at.desc())
            .offset(eff_offset)
            .limit(limit)
            .all()
        )
        return PaginatedFilesResponse(
            items=files,
            total=total,
            limit=limit,
            offset=eff_offset,
        )

    files = query.order_by(FileMetadata.created_at.desc()).all()
    total_count = len(files)
    return PaginatedFilesResponse(
        items=files,
        total=total_count,
        limit=total_count,
        offset=0,
    )


@router.patch("/{fileid}", response_model=FileMetadataSchema)
async def update_metadata(
    fileid: int,
    payload: FileMetadataUpdateRequest,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Update custom metadata fields (title, description, tags) for a file owned by current user."""
    db_file = (
        db.query(FileMetadata)
        .filter(
            FileMetadata.fileid == fileid,
            FileMetadata.userid == current_user.id,
        )
        .first()
    )
    if not db_file:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="File metadata not found or access denied.",
        )

    if payload.title is not None:
        db_file.title = payload.title
    if payload.description is not None:
        db_file.description = payload.description
    if payload.tags is not None:
        db_file.tags = payload.tags

    # Increment index_version and set indexing_status to INDEXING
    db_file.index_version = (db_file.index_version or 1) + 1
    db_file.indexing_status = IndexingStatus.INDEXING.value
    db.commit()
    db.refresh(db_file)

    # Re-index updated metadata vector in Qdrant via background task
    background_tasks.add_task(
        sync_vector_in_background,
        file_id=db_file.fileid,
        user_id=current_user.id,
        filename=db_file.filename,
        title=db_file.title,
        description=db_file.description,
        tags=db_file.tags,
        target_version=db_file.index_version,
    )

    return db_file


@router.delete("/{fileid}", status_code=status.HTTP_200_OK)
async def delete_file(
    fileid: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Delete a document from S3 storage and MySQL database owned by current user with strict external failure handling."""
    db_file = (
        db.query(FileMetadata)
        .filter(
            FileMetadata.fileid == fileid,
            FileMetadata.userid == current_user.id,
        )
        .first()
    )
    if not db_file:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="File record not found or access denied.",
        )

    s3_key = db_file.s3_key

    # Step 1: Delete S3 object first (non-blocking threadpool call)
    try:
        await run_in_threadpool(delete_s3_object, s3_key)
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete object from S3 storage: {str(exc)}",
        ) from exc

    # Step 2: Delete Qdrant vector point and check return status (Issue 2 Fix)
    qdrant_deleted = await delete_file_vector(fileid)
    if not qdrant_deleted:
        logger.error(
            "CRITICAL: Failed to delete Qdrant vector point for file_id=%s. Aborting DB record deletion to maintain consistency.",
            fileid,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to remove document vector embeddings from vector store. Deletion aborted.",
        )

    # Step 3: Delete database record after S3 and Qdrant deletes succeed
    try:
        db.delete(db_file)
        db.commit()
    except Exception as exc:
        logger.critical(
            "DESYNCHRONIZATION DETECTED: Storage object '%s' and Qdrant vector point (id=%s) were deleted, but database record failed to delete: %s",
            s3_key,
            fileid,
            str(exc),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database deletion failed after external storage and vector objects were removed.",
        ) from exc

    return {"success": True, "message": "File deleted successfully.", "fileId": fileid}
