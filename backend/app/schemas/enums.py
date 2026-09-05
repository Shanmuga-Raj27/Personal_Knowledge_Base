"""
backend/app/schemas/enums.py

Standard Enumerations for document lifecycle status and AI vector indexing status.
"""
from enum import Enum


class FileStatus(str, Enum):
    """File lifecycle state stored in MySQL file_metadata table."""
    PENDING = "pending"
    ACTIVE = "active"
    FAILED = "failed"


class IndexingStatus(str, Enum):
    """Vector indexing status for Qdrant vector synchronization."""
    PENDING = "PENDING"
    EXTRACTING = "EXTRACTING"
    CHUNKED = "CHUNKED"
    EMBEDDING = "EMBEDDING"
    INDEXING = "INDEXING"
    INDEXED = "INDEXED"
    FAILED = "FAILED"
    FAILED_RETRYABLE = "FAILED_RETRYABLE"
    FAILED_TERMINAL = "FAILED_TERMINAL"
