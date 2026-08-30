"""
backend/app/database/db_models.py

SQLAlchemy ORM models.
Each class maps to a database table.
These models are also used by Alembic to detect schema changes for migrations.
"""
from sqlalchemy import Column, Integer, String, BigInteger, DateTime, ForeignKey, Boolean, Index
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
    status = Column(String(20), default="pending", nullable=False, index=True)

    # Custom metadata details (tightened column limits)
    title = Column(String(100), nullable=True)
    description = Column(String(255), nullable=True)
    tags = Column(String(50), nullable=True)  # Comma-separated search tags

    # Vector indexing lifecycle status, optimistic concurrency, and retry tracking
    is_indexed = Column(Boolean, default=False, nullable=False, index=True)
    indexing_status = Column(String(20), default="PENDING", nullable=False, index=True)
    index_version = Column(Integer, default=1, nullable=False)
    retry_count = Column(Integer, default=0, nullable=False)
    last_error = Column(String(500), nullable=True)

    # Mandatory foreign key linking to the User owning the document
    userid = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
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

    __table_args__ = (
        Index("idx_user_status", "userid", "status"),
        Index("idx_indexing_recovery", "status", "is_indexed", "indexing_status"),
    )

    # Setup database relationships
    user = relationship("User", backref="files")