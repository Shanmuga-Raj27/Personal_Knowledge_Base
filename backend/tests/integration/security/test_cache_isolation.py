"""
backend/tests/integration/security/test_cache_isolation.py

Phase 7 security group — answer-cache tenant isolation.

Proves no user can read or overwrite ANOTHER tenant's cached answer:
    - cache keys are prefixed with the owning user_id and corpus revision; the
      query_hash payload also includes top_k / threshold / prompt / model;
    - the same natural question across two tenants NEVER shares a key;
    - a mixed file set cannot be used to reach another tenant's fragment (the
      orchestrator keys on the VALIDATED file set, not the raw request).
"""
from app.services.rag.query_utils import build_cache_key
from app.services.rag.rag_orchestrator import run_rag_query
from tests.integration.security.conftest import authenticated


class TestCacheIsolation:
    def test_same_question_different_tenants_distinct_keys(self):
        k_alice = build_cache_key(user_id=1, corpus_revision=5, question="how refunds work",
                                  file_ids=None, top_k=6, score_threshold=0.35)
        k_bob = build_cache_key(user_id=2, corpus_revision=5, question="how refunds work",
                                file_ids=None, top_k=6, score_threshold=0.35)
        assert k_alice != k_bob
        assert k_alice.startswith("1:")
        assert k_bob.startswith("2:")

    def test_same_user_different_file_sets_distinct_keys(self):
        k_all = build_cache_key(1, 5, "q", None, 6, 0.35)
        k_owned = build_cache_key(1, 5, "q", [10], 6, 0.35)
        k_with_foreign = build_cache_key(1, 5, "q", [10, 20], 6, 0.35)
        assert k_all != k_owned != k_with_foreign

    def test_corpus_revision_invalidates_same_user_key(self):
        k_old = build_cache_key(1, 4, "q", None, 6, 0.35)
        k_new = build_cache_key(1, 5, "q", None, 6, 0.35)
        assert k_old != k_new

    def test_all_key_components_encoded(self):
        """Distinct top_k / threshold /\u200b prompt /\u200b model must all change
        the key — otherwise a tenant could read a 'wrong' cached answer."""
        k = build_cache_key(1, 5, "q", None, 6, 0.35)
        assert k != build_cache_key(1, 5, "q", None, 7, 0.35)
        assert k != build_cache_key(1, 5, "q", None, 6, 0.4)
        assert k != build_cache_key(1, 5, "q", None, 6, 0.35, prompt_version="v2")
        assert k != build_cache_key(1, 5, "q", None, 6, 0.35, model_version="m2")

    def test_orchestrator_keys_on_validated_scope(self, authenticated):
        """The orchestrator builds the cache key from validated_file_ids, so a
        request carrying [10, 20] is cached under [10] — never under a key that
        embeds Bob's fragment."""
        import asyncio
        from unittest.mock import AsyncMock, patch
        from app.services.rag.rag_orchestrator import RAGRequest

        db = authenticated["db"]

        def fake_search(user_id, query_text, file_ids=None, top_k=None, score_threshold=None):
            return [
                {"chunk_id": "c-a", "file_id": 10, "index_version": 1,
                 "chunk_index": 0, "score": 0.9, "rank": 0},
            ]

        with patch("app.services.rag.rag_orchestrator.get_cached_answer",
                   AsyncMock(return_value=None)) as m_get, \
             patch("app.services.rag.rag_orchestrator.set_cached_answer",
                   AsyncMock(return_value=None)) as m_set, \
             patch("app.services.rag.rag_orchestrator.search_similar_chunks",
                   side_effect=fake_search), \
             patch("app.services.rag.rag_orchestrator.hydrate_chunks",
                   return_value=[
                       {"chunk_id": "c-a", "file_id": 10, "index_version": 1,
                        "chunk_index": 0, "clean_text": "text " * 50,
                        "page_start": 1, "page_end": 1,
                        "original_filename": "f10.pdf", "score": 0.9, "rank": 0},
                   ]), \
             patch("app.services.rag.rag_orchestrator.generate_answer_stream",
                   side_effect=lambda q, s: _yield()):
            req = RAGRequest(user_id=1, question="q", file_ids=[10, 20])
            asyncio.run(_collect_events(req, db))

        # Cache key embeds ONLY the validated scope [10] — never the foreign 20.
        assert m_get.await_args.args[0] == build_cache_key(1, 0, "q", [10], 6, 0.35)
        assert m_set.await_args.args[0] == build_cache_key(1, 0, "q", [10], 6, 0.35)


async def _gen():
    yield "answer"


def _yield():
    return _gen()


async def _collect_events(req, db):
    return [ev async for ev in run_rag_query(req, db)]