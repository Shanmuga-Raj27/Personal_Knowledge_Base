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
from dotenv import load_dotenv
import os

# Load variables from .env file (DATABASE_URL)
load_dotenv()

# Read database URL from environment
DATABASE_URL = os.getenv("DATABASE_URL")

# Create SQLAlchemy engine — manages DB connections
engine = create_engine(DATABASE_URL)

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

