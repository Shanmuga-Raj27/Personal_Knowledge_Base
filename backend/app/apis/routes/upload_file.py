import logging

from fastapi import APIRouter, HTTPException, status, Depends, BackgroundTasks, Response
from sqlalchemy.orm import Session
from app.database.database import SessionLocal

from app.auth.auth import get_current_user
from app.database import get_db
from app.database.db_models import FileMetadata, User
from app.schemas.file import (
    FileUploadRequest,
    PresignedUrlResponse,
    FileUploadCompleteRequest,
    FileUploadCompleteResponse,
    FileViewUrlRequest,
    FileViewUrlResponse,
    FileMetadataSchema,
    FileMetadataUpdateRequest,
)
from app.services.AWS.s3_service import (
    create_presigned_put_url,
    create_presigned_get_url,
    get_object_metadata,
    delete_s3_object,
)
from app.services.AI.vector_service import (
    upsert_file_vector,
    delete_file_vector,
    search_file_vectors,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/files", tags=["files"])


async def sync_vector_in_background(
    file_id: int,
    user_id: int,
    filename: str,
    title: str | None,
    description: str | None,
    tags: str | None,
):
    """Background worker task to compute Gemini embeddings and update Qdrant point asynchronously."""
    indexed_success = await upsert_file_vector(
        file_id=file_id,
        user_id=user_id,
        filename=filename,
        title=title,
        description=description,
        tags=tags,
    )
    db = SessionLocal()
    try:
        db_file = db.query(FileMetadata).filter(FileMetadata.fileid == file_id).first()
        if db_file:
            db_file.is_indexed = indexed_success
            db.commit()
    except Exception as exc:
        logger.error("Background task error updating is_indexed for file %s: %s", file_id, str(exc))
    finally:
        db.close()


@router.post("/upload-url", response_model=PresignedUrlResponse)
async def get_upload_url(
    payload: FileUploadRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Generate a presigned S3 PUT URL and create a pending metadata record assigned to current user."""
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

    # Insert pending row in database bound to current_user.id
    try:
        db_file = FileMetadata(
            s3_key=result["key"],
            filename=payload.filename,
            content_type=payload.content_type,
            status="pending",
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
        meta = get_object_metadata(payload.key)
        # Update database row to active
        db_file.status = "active"
        db_file.size_bytes = meta["size_bytes"]
        db.commit()
        db.refresh(db_file)

        # Offload AI vector embedding generation & Qdrant indexing to background worker
        background_tasks.add_task(
            sync_vector_in_background,
            file_id=db_file.fileid,
            user_id=current_user.id,
            filename=db_file.filename,
            title=db_file.title,
            description=db_file.description,
            tags=db_file.tags,
        )
    except FileNotFoundError as exc:
        # Mark as failed in DB
        db_file.status = "failed"
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


@router.get("", response_model=list[FileMetadataSchema])
async def list_files(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List all active files belonging strictly to the authenticated user."""
    files = (
        db.query(FileMetadata)
        .filter(
            FileMetadata.status == "active",
            FileMetadata.userid == current_user.id,
        )
        .order_by(FileMetadata.created_at.desc())
        .all()
    )
    return files


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
    )

    return db_file


@router.get("/search", response_model=list[FileMetadataSchema])
async def search_files(
    q: str = "",
    response: Response = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Perform multi-tenant scoped semantic AI file search with automatic MySQL keyword fallback."""
    search_term = q.strip()
    if not search_term:
        return await list_files(current_user=current_user, db=db)

    matched_ids = []
    try:
        matched_ids = await search_file_vectors(
            query_text=search_term,
            user_id=current_user.id,
            limit=15,
        )
    except Exception as exc:
        logger.warning("Semantic vector search error, falling back to SQL search: %s", str(exc))
        matched_ids = []

    if matched_ids:
        files = (
            db.query(FileMetadata)
            .filter(
                FileMetadata.fileid.in_(matched_ids),
                FileMetadata.userid == current_user.id,
                FileMetadata.status == "active",
            )
            .all()
        )
        if files:
            file_map = {f.fileid: f for f in files}
            sorted_files = [file_map[fid] for fid in matched_ids if fid in file_map]
            return sorted_files

    # Fallback Trigger: Set X-Search-Fallback header and perform MySQL SQL substring search
    if response:
        response.headers["X-Search-Fallback"] = "true"

    pattern = f"%{search_term}%"
    fallback_files = (
        db.query(FileMetadata)
        .filter(
            FileMetadata.userid == current_user.id,
            FileMetadata.status == "active",
            (
                FileMetadata.title.ilike(pattern)
                | FileMetadata.description.ilike(pattern)
                | FileMetadata.tags.ilike(pattern)
                | FileMetadata.filename.ilike(pattern)
            ),
        )
        .order_by(FileMetadata.created_at.desc())
        .all()
    )
    return fallback_files


@router.delete("/{fileid}", status_code=status.HTTP_200_OK)
async def delete_file(
    fileid: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Delete a document from S3 storage and MySQL database owned by current user."""
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

    # Step 1: Delete S3 object first
    try:
        delete_s3_object(s3_key)
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete object from S3 storage: {str(exc)}",
        ) from exc

    # Step 2: Delete Qdrant vector point
    await delete_file_vector(fileid)

    # Step 3: Delete database record after S3 delete succeeds
    try:
        db.delete(db_file)
        db.commit()
    except Exception as exc:
        logger.critical(
            "DESYNCHRONIZATION DETECTED: Storage object '%s' was deleted from S3, but database record (id=%s) failed to delete: %s",
            s3_key,
            fileid,
            str(exc),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database deletion failed after storage object was removed.",
        ) from exc

    return {"success": True, "message": "File deleted successfully.", "fileId": fileid}
