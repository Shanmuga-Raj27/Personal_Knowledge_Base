"""
backend/app/database/db_models.py

SQLAlchemy ORM models.
Each class maps to a database table.
These models are also used by Alembic to detect schema changes for migrations.
"""
from sqlalchemy import Column, Integer, String, BigInteger, DateTime, ForeignKey, Boolean
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship

from app.database import Base


class User(Base):
    """User table for storing registered account information.

    Passwords are stored as Argon2id hashes, never in plain text.
    """
    __tablename__ = "users"

    # Primary key — unique identifier for each user
    id = Column(Integer, primary_key=True, index=True)

    # Email — must be unique, used for login
    email = Column(String(255), unique=True, index=True, nullable=False)

    # Hashed password — Argon2id hash of the plain-text password
    hashed_password = Column(String(255), nullable=False)

    # Account status: active, disabled
    status = Column(String(20), default="active", nullable=False)

    # Automatically managed registration timestamp
    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


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

    # Custom metadata details (tightened column limits)
    title = Column(String(100), nullable=True)
    description = Column(String(255), nullable=True)
    tags = Column(String(50), nullable=True)  # Comma-separated search tags

    # Vector indexing lifecycle status and optimistic concurrency versioning
    is_indexed = Column(Boolean, default=False, nullable=False)
    indexing_status = Column(String(20), default="pending", nullable=False)
    index_version = Column(Integer, default=1, nullable=False)

    # Mandatory foreign key linking to the User owning the document
    userid = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )

    # Automatically managed timestamp records
    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # Setup database relationships
    user = relationship("User", backref="files")