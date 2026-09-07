"""
backend/tests/unit/services/rag/test_metrics.py

Unit tests for the Phase 7 dependency-free metrics engine.

Pins the ranking-metric primitives against hand-computed values, the
k-clamping / division-by-zero edge cases, and the evaluation aggregator.
"""
import pytest

from app.services.rag.metrics import (
    EvalCase,
    RAGEvaluationResult,
    abstention_rate,
    abstention_rate_from_events,
    citation_accuracy,
    dcg_at_k,
    evaluate_cases,
    mrr,
    ndcg_at_k,
    precision_at_k,
    recall_at_k,
    reciprocal_rank,
)

RELEVANT = {"a", "b", "c"}
PERFECT = ["a", "b", "c", "d", "e"]
MISSING_ONE = ["b", "c", "x", "y", "a"]  # a at rank 5
WORSE = ["x", "y", "z", "a", "b"]        # 2/3 relevant but ranks 4 and 5


class TestRecallAtK:
    def test_perfect_retrieval_is_1(self):
        assert recall_at_k(RELEVANT, PERFECT, k=3) == 1.0

    def test_half_recall(self):
        assert recall_at_k(RELEVANT, ["a", "z", "w"], k=3) == pytest.approx(1 / 3)

    def test_k_clamping(self):
        assert recall_at_k(RELEVANT, PERFECT, k=2) == pytest.approx(2 / 3)

    def test_no_relevant_returns_zero(self):
        assert recall_at_k(set(), PERFECT, k=3) == 0.0
        assert recall_at_k(None, PERFECT, k=3) == 0.0

    def test_empty_retrieved(self):
        assert recall_at_k(RELEVANT, [], k=3) == 0.0

    def test_k_none_uses_entire_list(self):
        assert recall_at_k(RELEVANT, PERFECT, k=None) == 1.0


class TestPrecisionAtK:
    def test_perfect(self):
        assert precision_at_k(RELEVANT, PERFECT, k=3) == 1.0

    def test_two_of_five(self):
        assert precision_at_k(RELEVANT, WORSE, k=4) == pytest.approx(1 / 4)

    def test_empty_top_is_zero(self):
        assert precision_at_k(RELEVANT, [], k=5) == 0.0


class TestReciprocalRankAndMRR:
    def test_first_rank_is_one(self):
        assert reciprocal_rank(RELEVANT, ["a", "w", "e"]) == 1.0

    def test_third_rank_is_one_third(self):
        assert reciprocal_rank(RELEVANT, ["x", "y", "a"]) == pytest.approx(1 / 3)

    def test_no_hit_zero(self):
        assert reciprocal_rank(RELEVANT, ["x", "y", "z"]) == 0.0

    def test_empty_relevant_zero(self):
        assert reciprocal_rank(set(), ["a", "b"]) == 0.0

    def test_mrr_mean(self):
        pairs = [
            (RELEVANT, ["a", "b"]),   # 1.0
            (RELEVANT, ["x", "a"]),   # 0.5
            (RELEVANT, ["x", "y"]),   # 0.0
        ]
        assert mrr(pairs) == pytest.approx(0.5)

    def test_mrr_empty(self):
        assert mrr([]) == 0.0


class TestNDCG:
    def test_perfect_ranking_is_one(self):
        assert ndcg_at_k(RELEVANT, PERFECT, k=None) == pytest.approx(1.0)
        assert ndcg_at_k(RELEVANT, PERFECT, k=3) == pytest.approx(1.0)

    def test_binary_dcg_matches_hand_formula(self):
        # gains [1, 1, 1, 0, 1]; DCG = 1 + 1/log2(3) + 1/log2(4) + 0 + 1/log2(6)
        dcg = dcg_at_k([1.0, 1.0, 1.0, 0.0, 1.0], k=None)
        expected = (
            1.0
            + 1.0 / __import__("math").log2(3)
            + 1.0 / __import__("math").log2(4)
            + 1.0 / __import__("math").log2(6)
        )
        assert dcg == pytest.approx(expected)

    def test_downranked_ndcg_below_one(self):
        nd = ndcg_at_k(RELEVANT, WORSE, k=10)
        assert 0.0 < nd < 1.0
        assert ndcg_at_k(RELEVANT, PERFECT, k=10) > nd

    def test_no_relevant_is_zero(self):
        assert ndcg_at_k(set(), PERFECT, k=10) == 0.0

    def test_none_relevant_zero(self):
        assert ndcg_at_k(RELEVANT, ["x", "y", "z"], k=10) == 0.0


class TestCitationAccuracy:
    def test_all_valid(self):
        assert citation_accuracy(["a", "b"], {"a", "b", "c"}) == 1.0

    def test_half_valid(self):
        assert citation_accuracy(["a", "ghost"], {"a", "b", "c"}) == 0.5

    def test_none_valid(self):
        assert citation_accuracy(["ghost1", "ghost2"], {"a"}) == 0.0

    def test_empty_cited_is_one(self):
        assert citation_accuracy([], {"a"}) == 1.0
        assert citation_accuracy(None, {"a"}) == 1.0


class TestAbstention:
    def test_rate(self):
        assert abstention_rate([True, False, True]) == pytest.approx(2 / 3)

    def test_empty_is_zero(self):
        assert abstention_rate([]) == 0.0

    def test_from_final_events(self):
        events = [
            {"type": "final", "diagnostics": {"insufficient_evidence": True}},
            {"type": "final", "diagnostics": {"insufficient_evidence": False}},
            {"type": "final", "diagnostics": {"cache_hit": True}},
        ]
        assert abstention_rate_from_events(events) == pytest.approx(1 / 3)


class TestEvaluateCases:
    def test_aggregate_means(self):
        cases = [
            EvalCase(question="q1", retrieved=PERFECT, relevant=RELEVANT,
                     cited=["a", "ghost"], abstained=False),
            EvalCase(question="q2", retrieved=["x", "a", "b"], relevant=RELEVANT,
                     cited=["a", "b"], abstained=False),
            EvalCase(question="q3", retrieved=[], relevant=RELEVANT,
                     cited=None, abstained=True),
        ]
        result = evaluate_cases(cases)
        assert isinstance(result, RAGEvaluationResult)
        assert result.num_queries == 3
        # recall@5: q1 1.0, q2 2/3, q3 0.0
        assert result.recall_at_5 == pytest.approx((1.0 + 2 / 3 + 0.0) / 3)
        # mrr: q1 1.0, q2 0.5, q3 0.0
        assert result.mrr == pytest.approx(0.5)
        # abstention: only q3
        assert result.abstention_rate == pytest.approx(1 / 3)
        # citation accuracy only over q1+q2 (q3 had cited=None)
        assert result.citation_accuracy == pytest.approx((0.5 + 1.0) / 2)
        assert len(result.per_query) == 3

    def test_empty_input(self):
        result = evaluate_cases([])
        assert result.num_queries == 0
        assert result.citation_accuracy is None
        assert result.as_dict()["recall_at_5"] == 0.0

    def test_as_dict_shape(self):
        result = evaluate_cases([EvalCase("q", PERFECT, RELEVANT)])
        d = result.as_dict()
        assert set(d) == {
            "num_queries", "recall_at_5", "recall_at_10", "precision_at_10",
            "mrr", "ndcg_at_10", "citation_accuracy", "abstention_rate",
        }
        assert d["mrr"] == 1.0