"""
backend/app/services/rag/schemas.py

Internal Data Transfer Objects (DTOs) for RAG PDF extraction and chunking pipeline.
"""
from dataclasses import dataclass

from pydantic import BaseModel, Field


@dataclass(frozen=True)
class ExtractedPage:
    page_number: int
    text: str


@dataclass(frozen=True)
class PageWord:
    text: str
    page_number: int
    absolute_word_index: int


@dataclass(frozen=True)
class TextChunk:
    chunk_index: int
    clean_text: str
    page_start: int
    page_end: int
    word_start: int
    word_end: int
    word_count: int
    text_checksum: str


class ChunkPayload(BaseModel):
    """Tiny Qdrant payload — only 4 fields. Text stays in MySQL."""

    user_id: int
    file_id: int
    index_version: int = Field(ge=1)
    chunk_index: int = Field(ge=0)
