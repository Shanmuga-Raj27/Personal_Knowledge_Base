"""
backend/tests/unit/services/rag/test_ids.py

Unit tests for deterministic chunk ID generation.
"""
import pytest
from uuid import UUID

from app.services.rag.ids import build_chunk_id


class TestBuildChunkId:
    def test_same_inputs_produce_same_uuid(self):
        """Same file_id, index_version, chunk_index -> same UUID every time."""
        id1 = build_chunk_id(10, 1, 0)
        id2 = build_chunk_id(10, 1, 0)
        assert id1 == id2

    def test_different_file_id_produces_different_uuid(self):
        """Different file_id -> different UUID."""
        id1 = build_chunk_id(10, 1, 0)
        id2 = build_chunk_id(11, 1, 0)
        assert id1 != id2

    def test_different_index_version_produces_different_uuid(self):
        """Different index_version -> different UUID."""
        id1 = build_chunk_id(10, 1, 0)
        id2 = build_chunk_id(10, 2, 0)
        assert id1 != id2

    def test_different_chunk_index_produces_different_uuid(self):
        """Different chunk_index -> different UUID."""
        id1 = build_chunk_id(10, 1, 0)
        id2 = build_chunk_id(10, 1, 1)
        assert id1 != id2

    def test_uuid_is_valid_v5(self):
        """Generated UUID should be a valid UUIDv5."""
        uid = build_chunk_id(42, 3, 5)
        assert isinstance(uid, UUID)
        assert uid.version == 5

    def test_uuid_string_format(self):
        """UUID string should be standard 36-char format."""
        uid = build_chunk_id(1, 1, 0)
        uid_str = str(uid)
        assert len(uid_str) == 36
        assert uid_str.count("-") == 4

    def test_deterministic_across_calls(self):
        """Multiple calls with same args produce identical results."""
        results = [build_chunk_id(100, 5, 10) for _ in range(10)]
        assert all(r == results[0] for r in results)

    def test_large_numbers_work(self):
        """Large file_id and version numbers should work."""
        uid = build_chunk_id(999999, 999999, 999999)
        assert isinstance(uid, UUID)
        assert uid.version == 5

    def test_zero_values_work(self):
        """Zero chunk_index and index_version=1 should work."""
        uid = build_chunk_id(1, 1, 0)
        assert isinstance(uid, UUID)
        assert uid.version == 5