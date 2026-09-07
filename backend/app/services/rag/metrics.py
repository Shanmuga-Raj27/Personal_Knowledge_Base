"""
backend/app/services/rag/metrics.py

Phase 7 metrics engine — dependency-free (stdlib only) retrieval/quality
metrics for the RAG evaluation harness.

Everything here is a pure function of (relevant, retrieved) pairs plus the
generation flags exposed by the orchestrator's final events, so the metrics
can be unit-tested in isolation and shared by:

    - app/scripts/rag_evaluate.py   (batch evaluation report)
    - the /system/rag-metrics route that Task 5 adds

Contract notes:
    * Empty/None `relevant` is scored 0.0 (nothing to retrieve) — never NaN.
    * k is 1-based and clamped; k=None means "use the whole retrieved list".
    * ndcg uses binary relevance: gain = 1 if the item is relevant else 0.
    * citation accuracy on an empty cited set is 1.0 (nothing to be false).
"""
from dataclasses import dataclass, field
from math import log2
from typing import Collection, Iterable, Sequence


def _top_k(retrieved: Sequence, k: int | None) -> list:
    """First k items (1-based cap); None keeps everything."""
    if k is None:
        return list(retrieved)
    return list(retrieved)[: max(0, int(k))]


def recall_at_k(
    relevant: Collection[str] | None,
    retrieved: Sequence[str],
    k: int | None = None,
) -> float:
    """Proportion of relevant items present in the top-k retrieved list.

    A query is scored 0.0 when it has no known relevant items (we cannot
    prove retrieval quality) — the eval script reports recall separately.
    """
    relevant = set(relevant or ())
    if not relevant:
        return 0.0
    top = _top_k(retrieved, k)
    hits = sum(1 for item in top if item in relevant)
    return hits / len(relevant)


def precision_at_k(
    relevant: Collection[str] | None,
    retrieved: Sequence[str],
    k: int | None = None,
) -> float:
    """Share of the top-k retrieved items that are relevant."""
    relevant = set(relevant or ())
    top = _top_k(retrieved, k)
    if not top:
        return 0.0
    hits = sum(1 for item in top if item in relevant)
    return hits / len(top)


def reciprocal_rank(
    relevant: Collection[str] | None,
    retrieved: Sequence[str],
) -> float:
    """1/rank of the first relevant item; 0.0 when none is retrieved."""
    relevant = set(relevant or ())
    for index, item in enumerate(retrieved, start=1):
        if item in relevant:
            return 1.0 / index
    return 0.0


def mrr(queries: Iterable[tuple[Collection[str] | None, Sequence[str]]]) -> float:
    """Mean Reciprocal Rank across (relevant, retrieved) query pairs."""
    ranks = [reciprocal_rank(rel, ret) for rel, ret in queries]
    if not ranks:
        return 0.0
    return sum(ranks) / len(ranks)


def dcg_at_k(gains: Sequence[float], k: int | None = None) -> float:
    """Discounted cumulative gain: sum gain_i / log2(i + 2) over the top k."""
    top = _top_k(gains, k)
    return sum(gain / log2(i + 2) for i, gain in enumerate(top))


def _idcg(relevant_count: int, k: int | None = None) -> float:
    """Best possible DCG: the relevance-1 gains sorted first."""
    n = relevant_count
    if k is not None:
        n = min(n, max(0, int(k)))
    return sum(1.0 / log2(i + 2) for i in range(n))


def ndcg_at_k(
    relevant: Collection[str] | None,
    retrieved: Sequence[str],
    k: int | None = None,
) -> float:
    """Normalized DCG with binary relevance (ideal = all relevant first)."""
    relevant = set(relevant or ())
    if not relevant:
        return 0.0
    gains = [1.0 if item in relevant else 0.0 for item in retrieved]
    ideal = _idcg(len(relevant), k)
    if ideal <= 0:
        return 0.0
    return dcg_at_k(gains, k) / ideal


def citation_accuracy(
    cited: Sequence[str] | None,
    valid_chunk_ids: Collection[str] | None,
) -> float:
    """Share of cited chunk IDs that reference a real retrieved source.

    Empty cited set -> 1.0 (the answer made no citation claim to be wrong).
    """
    cited = list(cited or ())
    if not cited:
        return 1.0
    valid = set(valid_chunk_ids or ())
    return sum(1 for c in cited if c in valid) / len(cited)


def abstention_rate(flags: Iterable[bool]) -> float:
    """Share of queries that ended in an abstention."""
    flags = list(flags)
    if not flags:
        return 0.0
    return sum(1 for f in flags if f) / len(flags)


def abstention_rate_from_events(final_events: Sequence[dict]) -> float:
    """Derive abstention from orchestrator final-event dicts.

    A query abstains when its final event carries
    ``diagnostics.insufficient_evidence == True``.
    """
    flags = (
        bool((ev.get("diagnostics") or {}).get("insufficient_evidence"))
        for ev in final_events
    )
    return abstention_rate(flags)


@dataclass(frozen=True)
class EvalCase:
    """One labeled evaluation query.

    ``retrieved`` must be ordered best-first (as Qdrant returns it).
    ``relevant`` is the set of chunk IDs that SHOULD have been retrieved.
    ``cited`` and ``abstained`` are optional generation-side observations:
    leave ``cited`` unset when citation quality is out of scope.
    """

    question: str
    retrieved: Sequence[str]
    relevant: Collection[str]
    cited: Sequence[str] | None = None
    abstained: bool = False


@dataclass(frozen=True)
class RAGEvaluationResult:
    """Aggregate metrics across an evaluation dataset."""

    num_queries: int
    recall_at_5: float = 0.0
    recall_at_10: float = 0.0
    precision_at_10: float = 0.0
    mrr: float = 0.0
    ndcg_at_10: float = 0.0
    citation_accuracy: float | None = None
    abstention_rate: float = 0.0
    per_query: list[dict] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "num_queries": self.num_queries,
            "recall_at_5": round(self.recall_at_5, 4),
            "recall_at_10": round(self.recall_at_10, 4),
            "precision_at_10": round(self.precision_at_10, 4),
            "mrr": round(self.mrr, 4),
            "ndcg_at_10": round(self.ndcg_at_10, 4),
            "citation_accuracy": (
                round(self.citation_accuracy, 4)
                if self.citation_accuracy is not None
                else None
            ),
            "abstention_rate": round(self.abstention_rate, 4),
        }


def evaluate_cases(cases: Sequence[EvalCase], top_k: int = 10) -> RAGEvaluationResult:
    """Compute aggregate recall/precision/MRR/nDCG/citation/abstention.

    recall@5 vs recall@10 use fixed caps on top of the caller-provided
    retrieved order; nDCG and precision use ``top_k`` (default 10).
    """
    if not cases:
        return RAGEvaluationResult(num_queries=0)

    recall_5: list[float] = []
    recall_10: list[float] = []
    precision_10: list[float] = []
    ranks: list[float] = []
    ndcg_10: list[float] = []
    citations: list[float] = []
    abstentions: list[bool] = []
    per_query: list[dict] = []

    for case in cases:
        r5 = recall_at_k(case.relevant, case.retrieved, k=5)
        r10 = recall_at_k(case.relevant, case.retrieved, k=10)
        p10 = precision_at_k(case.relevant, case.retrieved, k=10)
        rr = reciprocal_rank(case.relevant, case.retrieved)
        n10 = ndcg_at_k(case.relevant, case.retrieved, k=top_k)
        recall_5.append(r5)
        recall_10.append(r10)
        precision_10.append(p10)
        ranks.append(rr)
        ndcg_10.append(n10)
        abstentions.append(case.abstained)
        if case.cited is not None:
            citations.append(citation_accuracy(case.cited, case.relevant))

        per_query.append(
            {
                "question": case.question,
                "recall_at_5": round(r5, 4),
                "recall_at_10": round(r10, 4),
                "precision_at_10": round(p10, 4),
                "reciprocal_rank": round(rr, 4),
                "ndcg_at_10": round(n10, 4),
                "abstained": case.abstained,
            }
        )

    return RAGEvaluationResult(
        num_queries=len(cases),
        recall_at_5=sum(recall_5) / len(recall_5),
        recall_at_10=sum(recall_10) / len(recall_10),
        precision_at_10=sum(precision_10) / len(precision_10),
        mrr=sum(ranks) / len(ranks),
        ndcg_at_10=sum(ndcg_10) / len(ndcg_10),
        citation_accuracy=(
            sum(citations) / len(citations) if citations else None
        ),
        abstention_rate=sum(abstentions) / len(abstentions),
        per_query=per_query,
    )