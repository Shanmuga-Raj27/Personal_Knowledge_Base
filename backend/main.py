
from fastapi import FastAPI
import uvicorn

app = FastAPI()

# Database tables are now managed by Alembic migrations.
# Run 'alembic upgrade head' to create or update the schema.
# db_models.Base.metadata.create_all(bind=engine)

# Include all API routes

if __name__ == "__main__":
    uvicorn.run(app=app, host="127.0.0.1", port=8000)