import asyncio
import logging
import random
import time
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict

from fastapi import APIRouter, HTTPException, status, Depends, BackgroundTasks, Response, Query
from fastapi.concurrency import run_in_threadpool
from sqlalchemy import or_
from sqlalchemy.orm import Session
from app.database.database import SessionLocal

from app.core.config import settings
from app.auth.auth import get_current_user
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
    SearchResponseSchema,
    SearchResultItem,
    PaginatedFilesResponse,
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

# In-memory rate limiter for search route (30 requests/min per user ID)
SEARCH_REQUESTS: Dict[int, list[float]] = defaultdict(list)
MAX_SEARCH_REQUESTS = 30
SEARCH_RATE_LIMIT_WINDOW_SECONDS = 60.0


def check_search_rate_limit(user_id: int) -> None:
    """Enforce search endpoint rate limiting (30 requests per minute per user ID)."""
    now = time.time()
    if len(SEARCH_REQUESTS) > 2000:
        stale_keys = [
            k for k, v in SEARCH_REQUESTS.items()
            if not v or (now - v[-1] >= SEARCH_RATE_LIMIT_WINDOW_SECONDS)
        ]
        for k in stale_keys:
            del SEARCH_REQUESTS[k]

    SEARCH_REQUESTS[user_id] = [
        t for t in SEARCH_REQUESTS[user_id] if now - t < SEARCH_RATE_LIMIT_WINDOW_SECONDS
    ]
    if len(SEARCH_REQUESTS[user_id]) >= MAX_SEARCH_REQUESTS:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded. Maximum 30 search requests per minute allowed.",
        )
    SEARCH_REQUESTS[user_id].append(now)


# Global semaphore to enforce concurrent rate limiting on background embedding operations
_embedding_semaphore = asyncio.Semaphore(settings.MAX_CONCURRENT_EMBEDDING_TASKS)


async def sync_vector_in_background(
    file_id: int,
    user_id: int,
    filename: str,
    title: str | None,
    description: str | None,
    tags: str | None,
    target_version: int,
):
    """Background worker task to compute Gemini embeddings and update Qdrant point asynchronously with semaphore rate limiting."""
    async with _embedding_semaphore:
        indexed_success = False
        error_msg = None
        try:
            indexed_success = await upsert_file_vector(
                file_id=file_id,
                user_id=user_id,
                filename=filename,
                title=title,
                description=description,
                tags=tags,
            )
            if not indexed_success:
                error_msg = "Embedding generation or Qdrant vector upsert failed."
        except Exception as exc:
            indexed_success = False
            error_msg = str(exc)

        db = SessionLocal()
        try:
            db_file = db.query(FileMetadata).filter(FileMetadata.fileid == file_id).first()
            if db_file:
                # Optimistic versioning check: commit status only if version matches target_version
                if db_file.index_version == target_version:
                    db_file.is_indexed = indexed_success
                    if indexed_success:
                        db_file.indexing_status = IndexingStatus.INDEXED.value
                        db_file.last_error = None
                        db_file.next_retry_at = None
                    else:
                        db_file.indexing_status = IndexingStatus.FAILED.value
                        current_retries = (db_file.retry_count or 0) + 1
                        db_file.retry_count = current_retries
                        db_file.last_error = (error_msg or "Indexing failed")[:500]
                        # Exponential backoff calculation with jitter (max 300 seconds)
                        backoff_delay = min(300, (2 ** current_retries) + random.uniform(0, 1))
                        db_file.next_retry_at = datetime.now(timezone.utc) + timedelta(seconds=backoff_delay)
                    db.commit()
                else:
                    logger.info(
                        "Skipping stale background indexing task for file %s (current version %s != target %s).",
                        file_id, db_file.index_version, target_version
                    )
        except Exception as exc:
            logger.error("Background task error updating indexing_status for file %s: %s", file_id, str(exc))
        finally:
            db.close()


async def recover_and_backfill_unindexed_files():
    """Startup task to scan and queue unindexed/failed active files for background vector indexing in chunked batches."""
    db = SessionLocal()
    try:
        now_utc = datetime.now(timezone.utc)
        unindexed_files = (
            db.query(FileMetadata)
            .filter(
                FileMetadata.status == FileStatus.ACTIVE.value,
                FileMetadata.retry_count < 3,
                or_(
                    FileMetadata.indexing_status.in_([
                        IndexingStatus.PENDING.value,
                        IndexingStatus.FAILED.value,
                        IndexingStatus.INDEXING.value,
                    ]),
                    FileMetadata.is_indexed == False,
                ),
                or_(
                    FileMetadata.next_retry_at == None,
                    FileMetadata.next_retry_at <= now_utc,
                )
            )
            .limit(25)
            .all()
        )
        if unindexed_files:
            logger.info("Found %d unindexed or failed active records for recovery backfill...", len(unindexed_files))
            file_ids = [db_file.fileid for db_file in unindexed_files]
            db.query(FileMetadata).filter(FileMetadata.fileid.in_(file_ids)).update(
                {FileMetadata.indexing_status: IndexingStatus.INDEXING.value}, synchronize_session=False
            )
            db.commit()

            tasks = [
                sync_vector_in_background(
                    file_id=db_file.fileid,
                    user_id=db_file.userid,
                    filename=db_file.filename,
                    title=db_file.title,
                    description=db_file.description,
                    tags=db_file.tags,
                    target_version=db_file.index_version,
                )
                for db_file in unindexed_files
            ]
            await asyncio.gather(*tasks, return_exceptions=True)
    except Exception as exc:
        logger.warning("Recovery worker warning: %s", str(exc))
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

        # Offload AI vector embedding generation & Qdrant indexing to background worker
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


@router.get("/search", response_model=SearchResponseSchema)
async def search_files(
    q: str = "",
    limit: Optional[int] = Query(default=None, ge=1, le=200),
    offset: Optional[int] = Query(default=None, ge=0),
    response: Response = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Perform multi-tenant scoped semantic AI file search with strict 422 error boundary and graceful SQL keyword fallback."""
    check_search_rate_limit(current_user.id)

    if len(q) > 100 or (q != "" and not q.strip()):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Search query exceeds maximum length of 100 characters or contains only whitespace.",
        )

    search_term = q.strip()
    if not search_term:
        active_files = await list_files(limit=limit, offset=offset, current_user=current_user, db=db)
        if isinstance(active_files, PaginatedFilesResponse):
            items = [SearchResultItem(file=f, score=None) for f in active_files.items]
            total = active_files.total
        else:
            items = [SearchResultItem(file=f, score=None) for f in active_files]
            total = len(items)
        return SearchResponseSchema(
            results=items,
            search_mode="none",
            is_fallback_search=False,
            total=total,
            limit=limit,
            offset=offset if isinstance(limit, int) else None,
        )

    eff_offset = offset if isinstance(offset, int) else 0
    eff_limit = limit if isinstance(limit, int) else 15

    start_time = time.time()
    matched_tuples = []
    try:
        matched_tuples = await search_file_vectors(
            query_text=search_term,
            user_id=current_user.id,
            limit=eff_limit,
            offset=eff_offset,
        )
    except Exception as exc:
        vector_latency = time.time() - start_time
        logger.warning("Vector search failed after %.2fs, falling back to SQL search. Error: %s", vector_latency, str(exc))

        sql_start_time = time.time()
        # Security Note: SQLAlchemy automatically parameterizes ILIKE bind variables via SQL expression compiler,
        # ensuring complete protection against SQL injection vulnerabilities when handling user-provided search terms.
        query = db.query(FileMetadata).filter(
            FileMetadata.userid == current_user.id,
            FileMetadata.status == FileStatus.ACTIVE.value,
            or_(
                FileMetadata.filename.ilike(f"%{search_term}%"),
                FileMetadata.title.ilike(f"%{search_term}%"),
                FileMetadata.tags.ilike(f"%{search_term}%"),
                FileMetadata.description.ilike(f"%{search_term}%"),
            )
        )
        total = query.count()
        if isinstance(limit, int):
            fallback_files = (
                query.order_by(FileMetadata.created_at.desc())
                .offset(eff_offset)
                .limit(limit)
                .all()
            )
        else:
            fallback_files = query.order_by(FileMetadata.created_at.desc()).all()

        sql_latency = time.time() - sql_start_time
        logger.info("SQL fallback search completed in %.2fs returning %d matches.", sql_latency, total)

        results = [SearchResultItem(file=f, score=None) for f in fallback_files]
        return SearchResponseSchema(
            results=results,
            search_mode="fallback",
            is_fallback_search=True,
            total=total,
            limit=limit,
            offset=eff_offset if isinstance(limit, int) else None,
        )

    if matched_tuples:
        matched_ids = [t[0] for t in matched_tuples]
        score_map = {t[0]: t[1] for t in matched_tuples}
        files = (
            db.query(FileMetadata)
            .filter(
                FileMetadata.fileid.in_(matched_ids),
                FileMetadata.userid == current_user.id,
                FileMetadata.status == FileStatus.ACTIVE.value,
            )
            .all()
        )
        if files:
            file_map = {f.fileid: f for f in files}
            user_matched_tuples = [t for t in matched_tuples if t[0] in file_map]
            total_matched = len(user_matched_tuples)

            if isinstance(limit, int):
                paginated_tuples = user_matched_tuples[eff_offset : eff_offset + eff_limit]
            else:
                paginated_tuples = user_matched_tuples

            search_results = [
                SearchResultItem(file=file_map[t[0]], score=t[1])
                for t in paginated_tuples
            ]
            return SearchResponseSchema(
                results=search_results,
                search_mode="semantic",
                total=total_matched,
                limit=limit,
                offset=eff_offset if isinstance(limit, int) else None,
            )

    return SearchResponseSchema(
        results=[],
        search_mode="semantic",
        total=0,
        limit=limit,
        offset=eff_offset if isinstance(limit, int) else None,
    )


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

    # Step 1: Delete S3 object first (non-blocking threadpool call)
    try:
        await run_in_threadpool(delete_s3_object, s3_key)
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
