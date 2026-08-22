from fastapi import FastAPI
import uvicorn

from app.apis.routes.upload_file import router as upload_router

app = FastAPI(title="Personal Knowledge Base")

app.include_router(upload_router)


if __name__ == "__main__":
    uvicorn.run(app=app, host="127.0.0.1", port=8000)
