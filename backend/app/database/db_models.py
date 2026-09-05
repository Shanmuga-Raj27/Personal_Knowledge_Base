"""
backend/app/database/db_models.py

SQLAlchemy ORM models.
Each class maps to a database table.
These models are also used by Alembic to detect schema changes for migrations.
"""
from sqlalchemy import Column, Integer, String, BigInteger, DateTime, ForeignKey, Boolean, Index, SmallInteger, Text, UniqueConstraint
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship

try:
    from sqlalchemy.dialects.mysql import MEDIUMTEXT, BIGINT
    # Use Text with MySQL variant for SQLite compatibility
    ChunkTextType = Text().with_variant(MEDIUMTEXT, "mysql")
    # Use Integer for SQLite, BigInteger for MySQL
    ChunkIdType = Integer().with_variant(BIGINT, "mysql")
except ImportError:
    ChunkTextType = Text
    ChunkIdType = Integer

from app.database import Base
from app.schemas.enums import FileStatus, IndexingStatus


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
    status = Column(String(20), default=FileStatus.PENDING.value, nullable=False, index=True)

    # Custom metadata details (tightened column limits)
    title = Column(String(100), nullable=True)
    description = Column(String(255), nullable=True)
    tags = Column(String(50), nullable=True)  # Comma-separated search tags

    # Vector indexing lifecycle status, optimistic concurrency, retry tracking, and exponential backoff
    is_indexed = Column(Boolean, default=False, nullable=False, index=True)
    indexing_status = Column(String(20), default=IndexingStatus.PENDING.value, nullable=False, index=True)
    index_version = Column(Integer, default=1, nullable=False)
    retry_count = Column(Integer, default=0, nullable=False)
    next_retry_at = Column(DateTime(timezone=True), nullable=True)
    last_error = Column(String(500), nullable=True)

    # Mandatory foreign key linking to the User owning the document
    userid = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # RAG chunk indexing metadata
    active_index_version = Column(Integer, default=0, nullable=False)
    corpus_revision = Column(BigInteger, default=0, nullable=False)
    extraction_version = Column(String(32), nullable=True)
    cleaning_version = Column(String(32), nullable=True)
    chunking_version = Column(String(32), nullable=True)
    embedding_model = Column(String(100), nullable=True)
    embedding_dimensions = Column(SmallInteger, nullable=True)
    page_count = Column(Integer, default=0, nullable=False)
    extracted_word_count = Column(Integer, default=0, nullable=False)
    chunk_count = Column(Integer, default=0, nullable=False)
    indexed_chunk_count = Column(Integer, default=0, nullable=False)
    indexing_started_at = Column(DateTime(timezone=True), nullable=True)
    indexing_completed_at = Column(DateTime(timezone=True), nullable=True)
    rag_error_code = Column(String(64), nullable=True)
    rag_error_message = Column(String(500), nullable=True)

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
        Index("idx_user_status_fileid", "userid", "status", "fileid"),
        Index("idx_indexing_recovery", "status", "is_indexed", "indexing_status"),
    )

    # Setup database relationships
    user = relationship("User", backref="files")
    chunks = relationship(
        "DocumentChunk",
        back_populates="file",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class UserCorpusState(Base):
    """Per-user corpus revision used to invalidate RAG answer cache keys."""

    __tablename__ = "user_corpus_state"

    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    corpus_revision = Column(BigInteger, default=0, nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    user = relationship("User", backref="corpus_state")


class DocumentChunk(Base):
    """Durable source-of-truth text chunks for RAG retrieval."""

    __tablename__ = "document_chunks"

    id = Column(ChunkIdType, primary_key=True, autoincrement=True)
    file_id = Column(
        Integer,
        ForeignKey("file_metadata.fileid", ondelete="CASCADE"),
        nullable=False,
    )
    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    index_version = Column(Integer, nullable=False)
    chunk_index = Column(Integer, nullable=False)
    chunk_id = Column(String(36), nullable=False)

    page_start = Column(Integer, nullable=False)
    page_end = Column(Integer, nullable=False)
    word_start = Column(Integer, nullable=False)
    word_end = Column(Integer, nullable=False)
    word_count = Column(Integer, nullable=False)

    text_checksum = Column(String(64), nullable=False)
    clean_text = Column(ChunkTextType, nullable=False)

    extraction_version = Column(String(32), nullable=False)
    cleaning_version = Column(String(32), nullable=False)
    chunking_version = Column(String(32), nullable=False)
    embedding_model = Column(String(100), nullable=False)
    embedding_dimensions = Column(SmallInteger, nullable=False, default=768)

    source_key = Column(String(1024), nullable=False)
    original_filename = Column(String(255), nullable=False)

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    file = relationship("FileMetadata", back_populates="chunks")
    user = relationship("User")

    __table_args__ = (
        UniqueConstraint(
            "file_id",
            "index_version",
            "chunk_index",
            name="uq_document_chunks_file_version_index",
        ),
        UniqueConstraint("chunk_id", name="uq_document_chunks_chunk_id"),
        Index("ix_document_chunks_file_version", "file_id", "index_version"),
        Index("ix_document_chunks_hydrate", "user_id", "chunk_id", "index_version"),
        Index("ix_document_chunks_user_file_version", "user_id", "file_id", "index_version"),
    )