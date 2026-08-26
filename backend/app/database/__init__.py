"""
backend/app/database/__init__.py

Database package initialization. Exposes Base, get_db, engine, and SessionLocal.
"""
from app.database.database import Base, get_db, engine, SessionLocal
