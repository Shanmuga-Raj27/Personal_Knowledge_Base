"""
backend/app/db_models.py

SQLAlchemy ORM models.
Each class maps to a database table.
These models are also used by Alembic to detect schema changes for migrations.
"""
from sqlalchemy import Column, Integer, String, BigInteger, DateTime, ForeignKey
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship

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


class FileMetadata(Base):
    """Table for storing uploaded document metadata and tracking lifecycle status."""
    __tablename__ = "file_metadata"

    # Unique auto-incrementing ID
    fileid = Column(Integer, primary_key=True, index=True)

    # The S3 object key (e.g. uploads/uuid_name.pdf)
    s3_key = Column(String(255), unique=True, index=True, nullable=False)

    # The original name of the file
    filename = Column(String(255), nullable=False)

    # MIME type of the file
    content_type = Column(String(100), nullable=True)

    # File size in bytes
    size_bytes = Column(BigInteger, nullable=True)

    # Lifecycle state: pending, active, failed
    status = Column(String(20), default="pending", nullable=False)

    # Custom metadata details
    title = Column(String(255), nullable=True)
    description = Column(String(1000), nullable=True)
    tags = Column(String(255), nullable=True)  # Comma-separated search tags

    # Optional foreign key linking to the User for future authentication
    userid = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    # Automatically managed timestamp records
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # Setup database relationships
    user = relationship("User", backref="files")

    