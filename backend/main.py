from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

from app.core.config import settings
from app.apis.routes.auth import router as auth_router
from contextlib import asynccontextmanager
from app.services.AI.vector_service import init_qdrant_collection
from app.apis.routes.upload_file import backfill_unindexed_files, router as upload_router
from app.apis.routes.system import router as system_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """FastAPI application lifespan event handler for startup setup and legacy backfill."""
    try:
        await init_qdrant_collection()
        await backfill_unindexed_files()
    except Exception:
        pass
    yield


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
app.include_router(upload_router)
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

