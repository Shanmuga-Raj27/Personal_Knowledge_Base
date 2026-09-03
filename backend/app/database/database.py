"""
backend/app/database.py

Database configuration for SQLAlchemy and Alembic.
Loads environment variables, creates the engine, session factory,
and provides Base metadata for migration autogeneration.
"""
import logging
from fastapi import FastAPI
from sqlalchemy import create_engine, text, event
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import sessionmaker, declarative_base
from app.core.config import settings

logger = logging.getLogger(__name__)

# Read database URL from validated settings
DATABASE_URL = settings.DATABASE_URL

# Create SQLAlchemy engine with connection health pre-ping and parameterized pooling
engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    pool_size=settings.DATABASE_POOL_SIZE,
    max_overflow=settings.DATABASE_MAX_OVERFLOW,
    pool_timeout=settings.DATABASE_POOL_TIMEOUT,
    pool_recycle=settings.DATABASE_POOL_RECYCLE,
)


@event.listens_for(engine, "checkout")
def receive_pool_checkout(dbapi_conn, connection_record, connection_proxy):
    max_overflow = getattr(engine.pool, "_max_overflow", 0)
    total_capacity = engine.pool.size() + max_overflow
    checked_out = engine.pool.checkedout()
    if total_capacity > 0 and (checked_out / total_capacity) >= 0.8:
        logger.warning(
            "DB Connection Pool Capacity Warning: %d/%d connections checked out (>80%% pool utilization).",
            checked_out, total_capacity
        )

# Session factory — creates new DB sessions per request
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base class for all ORM models
Base = declarative_base()


def get_db():
    """Provide a database session for route handlers.

    Yields a session that is automatically closed after the request completes.
    FastAPI injects this into any route that declares it as a dependency.
    """
    database = SessionLocal()
    try:
        yield database
    finally:
        database.close()

