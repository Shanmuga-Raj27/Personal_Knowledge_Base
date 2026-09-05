"""
backend/app/services/rag/ids.py

Deterministic UUIDv5 generation for RAG chunk point IDs.

Uses UUIDv5 with NAMESPACE_URL so the same (file_id, index_version, chunk_index)
always produces the same UUID. This enables idempotent Qdrant upserts across retries.
"""
from uuid import NAMESPACE_URL, UUID, uuid5


def build_chunk_id(file_id: int, index_version: int, chunk_index: int) -> UUID:
    """Generate a deterministic UUIDv5 for a chunk.

    Args:
        file_id: The file_metadata.fileid primary key.
        index_version: The RAG index version (>=1).
        chunk_index: The chunk's ordinal index within the file/version (>=0).

    Returns:
        A UUIDv5 that is stable for the same inputs.
    """
    return uuid5(
        NAMESPACE_URL,
        f"rag-chunk:{file_id}:{index_version}:{chunk_index}",
    )