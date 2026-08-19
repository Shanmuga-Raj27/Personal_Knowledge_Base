"""
backend/app/db_models.py

SQLAlchemy ORM models.
Each class maps to a database table.
These models are also used by Alembic to detect schema changes for migrations.
"""
from sqlalchemy import Column
from sqlalchemy import Integer, String

from app.database import Base


class User(Base):
    """User table for storing registered account information.

    Passwords are stored as bcrypt hashes, never in plain text.
    """
    __tablename__ = "users"

    # Primary key — unique identifier for each user
    id = Column(Integer, primary_key=True, index=True)

    # Username — must be unique, used for login
    username = Column(String(100), unique=True, index=True)

    # Email — must be unique, used for contact/recovery
    email = Column(String(100), unique=True, index=True)

    # Hashed password — bcrypt hash of the plain-text password
    hashed_password = Column(String(100), nullable=False)
    