"""
backend/app/database.py

Database configuration for SQLAlchemy and Alembic.
Loads environment variables, creates the engine, session factory,
and provides Base metadata for migration autogeneration.
"""
from fastapi import FastAPI
from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import sessionmaker, declarative_base
from app.core.config import settings

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

