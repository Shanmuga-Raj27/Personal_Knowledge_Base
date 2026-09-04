import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

from app.core.config import settings
from app.apis.routes.auth_routes import router as auth_router
from app.apis.routes.document_routes import router as document_router
from app.apis.routes.search_routes import router as search_router
from app.apis.routes.system import router as system_router
from contextlib import asynccontextmanager
from app.services.AI.vector_service import init_qdrant_collection, close_qdrant_client
from app.services.AI.rag_vector_service import ensure_rag_collection
from app.services.cache.redis_cache import ping_redis, close_redis_client
from app.workers.indexing_worker import recover_and_backfill_unindexed_files

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """FastAPI application lifespan event handler for startup setup, RAG guard, Redis guard, and legacy backfill."""
    try:
        await init_qdrant_collection()
        await ensure_rag_collection()
        await ping_redis()
        await recover_and_backfill_unindexed_files()
    except Exception as exc:
        logger.critical("Lifespan startup initialization failed: %s", str(exc), exc_info=True)
        raise
    yield
    await close_qdrant_client()
    await close_redis_client()


app = FastAPI(title="Personal Knowledge Base", lifespan=lifespan)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(document_router)
app.include_router(search_router)
app.include_router(system_router)


from urllib.parse import urlparse

if __name__ == "__main__":
    port = 8000
    try:
        parsed = urlparse(settings.VITE_API_URL)
        if parsed.port:
            port = parsed.port
    except Exception:
        pass

    uvicorn.run(app=app, host="127.0.0.1", port=port)

