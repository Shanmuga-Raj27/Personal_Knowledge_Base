"""
backend/app/scripts/rag_evaluate.py

Phase 7 RAG evaluation harness — dependency-free.

Reads a labeled evaluation dataset (JSON Lines) where each line is ONE query:

    {
        "question": "What is the refund policy?",
        "retrieved": ["<chunk_uuid>", ...],   # ordered best-first (Qdrant order)
        "relevant":  ["<chunk_uuid>", ...],   # chunk IDs that SHOULD be found
        "cited":     ["<chunk_uuid>", ...],   # optional: citations in the answer
        "abstained": false                    # optional: final event abstention
    }

and reports aggregate quality metrics via app.services.rag.metrics:

    recall@5 / recall@10, precision@10, MRR, nDCG@10,
    citation accuracy, abstention rate.

Usage:
    uv run python -m app.scripts.rag_evaluate path/to/cases.jsonl [--top-k 10]
    uv run python -m app.scripts.rag_evaluate --demo [--top-k 10]

Options:
    --top-k 10        nDCG/precision cutoff for each case (recall is reported
                      at fixed caps 5 and 10, clamped to each retrieved list).
    --json out.json   also write the aggregate + per-query report as JSON.
"""
import argparse
import json
import sys
from pathlib import Path

from app.services.rag.metrics import EvalCase, evaluate_cases

DEMO_CASES = [
    {
        "question": "What is the 30-day refund window?",
        "retrieved": ["a1", "b2", "c3", "d4", "e5"],
        "relevant": ["a1", "b2"],
        "cited": ["a1", "b2"],
        "abstained": False,
    },
    {
        "question": "Are shipping costs refundable?",
        "retrieved": ["x1", "a1", "y2", "z3", "w4"],
        "relevant": ["a1"],
        "cited": ["a1", "ghost"],
        "abstained": False,
    },
    {
        "question": "What happens to returns after 60 days?",
        "retrieved": ["m1", "n2"],
        "relevant": ["q9"],
        "cited": None,
        "abstained": True,
    },
]


def _load_cases(path: Path) -> list[dict]:
    """Parse a JSONL dataset into raw case dicts."""
    cases: list[dict] = []
    # utf-8-sig tolerates a UTF-8 BOM (common when the file is created on
    # Windows) while remaining a plain UTF-8 reader for BOM-less files.
    with open(path, encoding="utf-8-sig") as handle:
        for lineno, line in enumerate(handle, start=1):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError as exc:
                raise SystemExit(f"{path}:{lineno}: invalid JSON: {exc}") from exc
            if "question" not in obj or "retrieved" not in obj or "relevant" not in obj:
                raise SystemExit(
                    f"{path}:{lineno}: each case needs 'question', 'retrieved'"
                    " (ordered) and 'relevant' keys."
                )
            cases.append(obj)
    return cases


def _to_cases(raw: list[dict]) -> list[EvalCase]:
    return [
        EvalCase(
            question=c["question"],
            retrieved=[str(i) for i in c["retrieved"]],
            relevant=[str(i) for i in c["relevant"]],
            cited=(
                [str(i) for i in c["cited"]] if c.get("cited") is not None else None
            ),
            abstained=bool(c.get("abstained", False)),
        )
        for c in raw
    ]


def _print_report(result) -> None:
    header = f"{'query':<50} {'R@5':>6} {'R@10':>6} {'P@10':>6} {'RR':>6} {'nDCG@10':>8} {'abs':>5}"
    print(header)
    print("-" * len(header))
    for row in result.per_query:
        print(
            f"{row['question'][:50]:<50} {row['recall_at_5']:>6.2f} "
            f"{row['recall_at_10']:>6.2f} {row['precision_at_10']:>6.2f} "
            f"{row['reciprocal_rank']:>6.2f} {row['ndcg_at_10']:>8.2f} "
            f"{int(row['abstained']):>5}"
        )
    print("-" * len(header))
    print(f"cases: {result.num_queries}")
    for key, value in result.as_dict().items():
        if key == "num_queries":
            continue
        print(f"  {key:<18} {value}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Phase 7 RAG evaluation harness")
    parser.add_argument("dataset", nargs="?", help="JSONL file of labeled cases")
    parser.add_argument("--top-k", type=int, default=10, help="cutoff for nDCG/precision")
    parser.add_argument("--demo", action="store_true", help="run the built-in demo dataset")
    parser.add_argument("--json", help="optional path to write the report as JSON")
    args = parser.parse_args()

    if (args.dataset is None) == (not args.demo):
        parser.error("provide either a dataset path or --demo (not both / neither)")

    raw = DEMO_CASES if args.demo else _load_cases(Path(args.dataset))
    cases = _to_cases(raw)
    result = evaluate_cases(cases, top_k=max(1, args.top_k))

    _print_report(result)

    if args.json:
        report = {
            "model": None,  # filled by the operator when comparing variants
            "dataset": args.dataset or "demo",
            "ics": {"top_k": args.top_k},
            "aggregate": result.as_dict(),
            "per_query": result.per_query,
        }
        with open(args.json, "w", encoding="utf-8") as handle:
            json.dump(report, handle, indent=2, ensure_ascii=False)
        print(f"\nreport written to {args.json}")

    if result.num_queries == 0:
        print("warning: no cases were evaluated", file=sys.stderr)


if __name__ == "__main__":
    main()