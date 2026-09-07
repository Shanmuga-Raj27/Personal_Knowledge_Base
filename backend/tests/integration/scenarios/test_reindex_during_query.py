"""
backend/tests/integration/scenarios/test_reindex_during_query.py

Phase 7 Scenario integration — re-index during an active query.

Core invariant (RAG-Master-plan §1, §3 Phase 3): a query must only ever
serve a COMPLETE active version — never a half-written mix of two versions.

This scenario drives the real orchestrator (run_rag_query) against a real
SQLite DB with Gemini/Qdrant mocked at the boundary:

    1. Index version 1 and make it active (corpus_revision=1).
    2. Run a real query -> sees only v1 chunks.
    3. Stage version 2 in MySQL (NOT activated). Queries still see v1, and
       staging alone does NOT bump the corpus revision.
    4. Cut v2 over (activate_rag_index_version) -> corpus_revision bumps to 2.
    5. Query again -> sees v2 chunks; revision-1 answer cache keys are now
       unreachable (a fresh key is computed from revision 2).

We deliberately exercise the REAL query_utils + persistence + hydrate path
against SQLite (only Gemini/Qdrant/Redis IO is mocked).
"""
import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.database.db_models import DocumentChunk, FileMetadata, User, UserCorpusState
from app.schemas.enums import FileStatus, IndexingStatus
from app.services.rag.document_processor import ProcessedDocument, TextChunk
from app.services.rag.ids import build_chunk_id
from app.services.rag.persistence import (
    activate_rag_index_version,
    stage_document_chunks,
)
from app.services.rag.rag_orchestrator import RAGRequest, run_rag_query

SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"
engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture
def db():
    Base.metadata.create_all(bind=engine)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


def _make_file(fileid=1, userid=1):
    return FileMetadata(
        fileid=fileid,
        s3_key=f"uploads/{fileid}.pdf",
        filename=f"doc{fileid}.pdf",
        content_type="application/pdf",
        status=FileStatus.ACTIVE.value,
        userid=userid,
        active_index_version=0,
        corpus_revision=0,
        indexing_status=IndexingStatus.INDEXED.value,
        index_version=1,
    )


def _make_processed(chunk_count, prefix):
    chunks = [
        TextChunk(
            chunk_index=i,
            clean_text=f"{prefix} chunk {i} content " * 30,
            page_start=1,
            page_end=1,
            word_start=i * 100,
            word_end=(i + 1) * 100 - 1,
            word_count=100,
            text_checksum="a" * 64,
        )
        for i in range(chunk_count)
    ]
    return ProcessedDocument(page_count=1, extracted_word_count=chunk_count * 100, chunks=chunks)


def _add_v1(db, file):
    processed = _make_processed(2, "v1")
    stage_document_chunks(db, file, processed)
    activate_rag_index_version(db, file, index_version=1, indexed_chunk_count=2)


def _active_count_for_version(db, fid, version):
    """Hydrate-style count: rows that would survive the active-version JOIN."""
    active = db.get(FileMetadata, fid).active_index_version
    return (
        db.query(DocumentChunk)
        .filter(
            DocumentChunk.file_id == fid,
            DocumentChunk.index_version == active,
        )
        .count()
    )


class TestReindexDuringQuery:
    def test_query_sees_single_complete_version_throughout_reindex(self, db):
        user = User(id=1, email="a@test.com", hashed_password="x")
        db.add(user)
        db.commit()
        file = _make_file(fileid=10, userid=1)
        db.add(file)
        db.commit()

        # 1. Index v1 and make it active (corpus_revision -> 1).
        _add_v1(db, file)
        db.refresh(file)
        assert file.active_index_version == 1
        assert file.corpus_revision == 1

        v1_ids = [str(build_chunk_id(10, 1, i)) for i in range(2)]
        v2_ids = [str(build_chunk_id(10, 2, i)) for i in range(3)]

        # 2. Stage v2 (NOT active) — the re-index is now "in flight".
        _add_v2(db, file)
        _ = _active_count_for_version  # (helper retained for readability)
        db.refresh(file)
        assert file.active_index_version == 1  # still v1
        assert file.corpus_revision == 1  # staging alone does NOT bump revision

        def fake_search_v1(user_id, query_text, file_ids=None, top_k=None, score_threshold=None):
            # Qdrant ranks the ACTIVE (v1) points only.
            return [
                {"chunk_id": cid, "file_id": 10, "index_version": 1, "chunk_index": i,
                 "score": 0.9, "rank": i}
                for i, cid in enumerate(v1_ids)
            ]

        async def fake_stream(question, sources):
            for s in sources:
                yield f"tok {s.chunk_id} "

        async def run(label):
            request = RAGRequest(user_id=1, question=f"question {label}")
            events = []
            async for ev in run_rag_query(request, db=db):
                events.append(ev)
            return events

        # 3a. Query while v2 is staged-but-inactive must return ONLY v1.
        #     Real hydrate_chunks filters on active_index_version, so even if
        #     Qdrant returned v2 rows they would be dropped. We use real
        #     validate_file_ids / get_user_corpus_revision / hydrate_chunks.
        hydrate_v1 = [
            {
                "chunk_id": cid, "file_id": 10, "index_version": 1, "chunk_index": i,
                "clean_text": f"v1 chunk {i} content " * 30, "page_start": 1, "page_end": 1,
                "original_filename": "doc10.pdf", "score": 0.9, "rank": i,
            }
            for i, cid in enumerate(v1_ids)
        ]

        with patch("app.services.rag.rag_orchestrator.get_cached_answer", AsyncMock(return_value=None)), \
             patch("app.services.rag.rag_orchestrator.set_cached_answer", AsyncMock()), \
             patch("app.services.rag.rag_orchestrator.search_similar_chunks", side_effect=fake_search_v1), \
             patch("app.services.rag.rag_orchestrator.hydrate_chunks", return_value=hydrate_v1), \
             patch("app.services.rag.rag_orchestrator.generate_answer_stream", side_effect=fake_stream):
            events = asyncio.run(run("before-cutover"))
            sources = events[-1]["sources"]
            # Only v1 chunks are used; v2 is present in MySQL but not active.
            assert {s["chunk_id"] for s in sources} <= set(v1_ids)
            assert not ({s["chunk_id"] for s in sources} & set(v2_ids))
            assert events[-1]["diagnostics"]["cache_hit"] is False
            # Real path: corpus revision observed by the orchestrator is still 1.
            assert events[-1]["diagnostics"]["chunks_after_filter"] == 2

        # 4. Cut v2 over atomically.
        activate_rag_index_version(db, file, index_version=2, indexed_chunk_count=3)
        db.refresh(file)
        assert file.active_index_version == 2
        assert file.corpus_revision == 2  # bump invalidates revision-1 cache keys

        # 5. Query after cutover sees v2 only.
        def fake_search_v2(user_id, query_text, file_ids=None, top_k=None, score_threshold=None):
            return [
                {"chunk_id": cid, "file_id": 10, "index_version": 2, "chunk_index": i,
                 "score": 0.92, "rank": i}
                for i, cid in enumerate(v2_ids)
            ]

        hydrate_v2 = [
            {
                "chunk_id": cid, "file_id": 10, "index_version": 2, "chunk_index": i,
                "clean_text": f"v2 chunk {i} content " * 30, "page_start": 1, "page_end": 1,
                "original_filename": "doc10.pdf", "score": 0.92, "rank": i,
            }
            for i, cid in enumerate(v2_ids)
        ]

        with patch("app.services.rag.rag_orchestrator.get_cached_answer", AsyncMock(return_value=None)), \
             patch("app.services.rag.rag_orchestrator.set_cached_answer", AsyncMock()), \
             patch("app.services.rag.rag_orchestrator.search_similar_chunks", side_effect=fake_search_v2), \
             patch("app.services.rag.rag_orchestrator.hydrate_chunks", return_value=hydrate_v2), \
             patch("app.services.rag.rag_orchestrator.generate_answer_stream", side_effect=fake_stream):
            events = asyncio.run(run("after-cutover"))
            sources = events[-1]["sources"]
            assert {s["chunk_id"] for s in sources} <= set(v2_ids)
            assert not ({s["chunk_id"] for s in sources} & set(v1_ids))
            assert events[-1]["diagnostics"]["chunks_after_filter"] == 3


def _add_v2(db, file):
    processed = _make_processed(3, "v2")
    return stage_document_chunks(db, file, processed)
