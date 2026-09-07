"""
backend/tests/unit/services/rag/test_query_utils.py

Unit tests for Phase 5 query_utils:
- validate_file_ids: ownership, ACTIVE status, INDEXED state
- get_user_corpus_revision + build_cache_key: deterministic cache identity
- score filtering, deduplication, per-file contribution cap
"""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.database.db_models import FileMetadata, UserCorpusState
from app.schemas.enums import FileStatus, IndexingStatus
from app.services.rag.query_utils import (
    build_cache_key,
    cap_per_file_contribution,
    deduplicate_chunks,
    get_user_corpus_revision,
    normalize_score_filtered,
    validate_file_ids,
)

SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"
engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture
def db_session():
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)


def _make_file(
    db: Session,
    fileid: int,
    userid: int = 1,
    status: str = FileStatus.ACTIVE.value,
    indexing_status: str = IndexingStatus.INDEXED.value,
) -> FileMetadata:
    file = FileMetadata(
        fileid=fileid,
        s3_key=f"uploads/file_{fileid}.pdf",
        filename=f"file_{fileid}.pdf",
        content_type="application/pdf",
        status=status,
        userid=userid,
        active_index_version=1,
        corpus_revision=0,
        indexing_status=indexing_status,
        index_version=1,
    )
    db.add(file)
    db.commit()
    return file


class TestValidateFileIds:
    def test_none_returns_none(self, db_session):
        assert validate_file_ids(1, None, db_session) is None

    def test_owned_indexed_file_kept(self, db_session):
        _make_file(db_session, fileid=10, userid=1)
        assert validate_file_ids(1, [10], db_session) == [10]

    def test_file_not_owned_dropped_raises(self, db_session):
        _make_file(db_session, fileid=10, userid=2)
        with pytest.raises(ValueError, match="None of the requested file IDs"):
            validate_file_ids(1, [10], db_session)

    def test_non_indexed_file_dropped_raises(self, db_session):
        _make_file(
            db_session,
            fileid=10,
            userid=1,
            indexing_status=IndexingStatus.PENDING.value,
        )
        with pytest.raises(ValueError, match="None of the requested file IDs"):
            validate_file_ids(1, [10], db_session)

    def test_inactive_file_dropped_raises(self, db_session):
        _make_file(db_session, fileid=10, userid=1, status=FileStatus.PENDING.value)
        with pytest.raises(ValueError, match="None of the requested file IDs"):
            validate_file_ids(1, [10], db_session)

    def test_mixed_valid_and_invalid(self, db_session):
        _make_file(db_session, fileid=10, userid=1)
        _make_file(db_session, fileid=20, userid=2)  # other user
        assert validate_file_ids(1, [10, 20, 999], db_session) == [10]

    def test_all_invalid_raises_value_error(self, db_session):
        _make_file(db_session, fileid=10, userid=2)
        with pytest.raises(ValueError, match="None of the requested file IDs"):
            validate_file_ids(1, [10], db_session)


class TestGetUserCorpusRevision:
    def test_no_row_returns_zero(self, db_session):
        assert get_user_corpus_revision(1, db_session) == 0

    def test_returns_row_value(self, db_session):
        db_session.add(UserCorpusState(user_id=7, corpus_revision=12))
        db_session.commit()
        assert get_user_corpus_revision(7, db_session) == 12


class TestBuildCacheKey:
    def test_same_inputs_same_key(self):
        k1 = build_cache_key(1, 0, "  what is x?  ", None, 6, 0.35)
        k2 = build_cache_key(1, 0, "what is x?", None, 6, 0.35)
        assert k1 == k2  # question is stripped

    def test_different_question_different_key(self):
        assert build_cache_key(1, 0, "a", None, 6, 0.35) != build_cache_key(
            1, 0, "b", None, 6, 0.35
        )

    def test_different_top_k_different_key(self):
        assert build_cache_key(1, 0, "a", None, 6, 0.35) != build_cache_key(
            1, 0, "a", None, 8, 0.35
        )

    def test_different_threshold_different_key(self):
        assert build_cache_key(1, 0, "a", None, 6, 0.35) != build_cache_key(
            1, 0, "a", None, 6, 0.40
        )

    def test_different_corpus_revision_different_key(self):
        assert build_cache_key(1, 0, "a", None, 6, 0.35) != build_cache_key(
            1, 1, "a", None, 6, 0.35
        )

    def test_different_user_different_key(self):
        assert build_cache_key(1, 0, "a", None, 6, 0.35) != build_cache_key(
            2, 0, "a", None, 6, 0.35
        )

    def test_none_vs_specific_file_ids_different_key(self):
        assert build_cache_key(1, 0, "a", None, 6, 0.35) != build_cache_key(
            1, 0, "a", [10, 20], 6, 0.35
        )

    def test_file_id_order_insensitive(self):
        assert build_cache_key(1, 0, "a", [10, 20], 6, 0.35) == build_cache_key(
            1, 0, "a", [20, 10], 6, 0.35
        )

    def test_format_is_user_corpus_hash(self):
        key = build_cache_key(42, 3, "q", None, 6, 0.35)
        assert key.startswith("42:3:")
        assert len(key.split(":")) == 3

    def test_different_prompt_version_different_key(self):
        assert build_cache_key(1, 0, "a", None, 6, 0.35, prompt_version="v1") != build_cache_key(
            1, 0, "a", None, 6, 0.35, prompt_version="v2"
        )

    def test_different_model_version_different_key(self):
        assert build_cache_key(1, 0, "a", None, 6, 0.35, model_version="m1") != build_cache_key(
            1, 0, "a", None, 6, 0.35, model_version="m2"
        )

    def test_collision_resistance_over_sample(self):
        """Phase 7 1c: a representative set of distinct canonical inputs must
        never collide — the hash suffix must be unique across the sample."""
        questions = ["what is refund policy?", "how do I file a claim?", "hello",
                     "summarize the contract", "x", "y", "a longer ambiguous question about policy"]
        thresholds = [0.1, 0.35, 0.5, 0.9]
        top_ks = [1, 6, 20]
        users = [1, 2, 42, 99]
        revisions = [0, 1, 5]
        # Note: [1,2] and [2,1] intentionally produce the SAME key (file_ids
        # are sorted before hashing), and [] is equivalent to None ("search all"),
        # so here we only use genuinely distinct sets.
        file_sets = [None, [1], [2], [1, 2], [7, 8]]

        def keys_for(user, rev, q, f, k, t, p, m):
            return build_cache_key(user, rev, q, f, k, t, p, m)

        hashes = set()
        # Full cartesian product would be huge; sample representative tuples.
        tuples = []
        for q in questions:
            for t in thresholds:
                for k in top_ks:
                    for u in users:
                        for r in revisions:
                            tuples.append((u, r, q, None, k, t, "v1", "gemini-3.6-flash"))
        for u in users:
            for f in file_sets:
                tuples.append((u, 0, "shared question", f, 6, 0.35, "v1", "gemini-3.6-flash"))

        for tup in tuples:
            hashes.add(keys_for(*tup))

        # Every distinct canonical input must map to a distinct cache key.
        assert len(hashes) == len(tuples)


class TestNormalizeScoreFiltered:
    def _chunk(self, score):
        return {"chunk_id": f"c{score}", "score": score, "rank": 0}

    def test_drops_below_threshold(self):
        chunks = [self._chunk(0.9), self._chunk(0.2)]
        assert normalize_score_filtered(chunks, 0.35) == [chunks[0]]

    def test_keeps_equal_to_threshold(self):
        chunks = [self._chunk(0.35)]
        assert normalize_score_filtered(chunks, 0.35) == chunks

    def test_empty_input(self):
        assert normalize_score_filtered([], 0.35) == []


class TestDeduplicateChunks:
    def _chunk(self, cid, fid, index, score, rank):
        return {
            "chunk_id": cid,
            "file_id": fid,
            "chunk_index": index,
            "score": score,
            "rank": rank,
        }

    def test_keeps_highest_scored_copy(self):
        chunks = [
            self._chunk("c1", 1, 0, 0.5, 0),
            self._chunk("c1", 1, 0, 0.9, 1),  # duplicate, higher score
        ]
        result = deduplicate_chunks(chunks)
        assert len(result) == 1
        assert result[0]["score"] == 0.9

    def test_distinct_chunks_all_kept(self):
        chunks = [
            self._chunk("c1", 1, 0, 0.9, 0),
            self._chunk("c2", 1, 1, 0.8, 1),
        ]
        assert len(deduplicate_chunks(chunks)) == 2

    def test_preserves_rank_order(self):
        chunks = [
            self._chunk("c1", 1, 5, 0.8, 0),
            self._chunk("c2", 1, 2, 0.9, 1),
        ]
        result = deduplicate_chunks(chunks)
        assert [c["chunk_id"] for c in result] == ["c1", "c2"]
        assert result[0]["rank"] == 0


class TestCapPerFileContribution:
    def _chunk(self, cid, fid, index, rank):
        return {
            "chunk_id": cid,
            "file_id": fid,
            "chunk_index": index,
            "score": 0.8,
            "rank": rank,
        }

    def test_caps_single_file(self):
        chunks = [
            self._chunk(f"c{i}", 1, i, i) for i in range(5)
        ]
        result = cap_per_file_contribution(chunks, max_per_file=3)
        assert len(result) == 3
        # keeps the highest ranked (first 3)
        assert [c["chunk_id"] for c in result] == ["c0", "c1", "c2"]

    def test_multiple_files_balanced(self):
        chunks = [
            self._chunk("a0", 1, 0, 0),
            self._chunk("b0", 2, 0, 1),
            self._chunk("a1", 1, 1, 2),
            self._chunk("c0", 3, 0, 3),
        ]
        result = cap_per_file_contribution(chunks, max_per_file=2)
        assert len(result) == 4  # no file exceeds cap

    def test_default_uses_settings_value(self):
        chunks = [self._chunk(f"c{i}", 1, i, i) for i in range(5)]
        result = cap_per_file_contribution(chunks)  # default = 3
        assert len(result) == 3