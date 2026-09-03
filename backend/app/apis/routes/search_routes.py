"""
backend/app/apis/routes/search_routes.py

Route handler for multi-tenant scoped semantic AI file search with strict
error boundaries and graceful SQL keyword search fallback.
"""
import logging
import time
from typing import Optional

from fastapi import APIRouter, HTTPException, status, Depends, Response, Query
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.auth.auth_dependencies import get_current_user
from app.database import get_db
from app.database.db_models import FileMetadata, User
from app.schemas.enums import FileStatus
from app.schemas.file import SearchResponseSchema, SearchResultItem, PaginatedFilesResponse
from app.services.AI.vector_service import search_file_vectors
from app.utils.rate_limiter import check_search_rate_limit
from app.apis.routes.document_routes import list_files

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/files", tags=["files"])


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
