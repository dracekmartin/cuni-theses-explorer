"""Compare search setups on one version of the evaluation set, against a baseline.

Prints two Markdown tables: the main metrics per setup, and Success@10 per query type.
Values marked with * differ from the baseline with p < 0.05 in a paired randomization
test over queries.

Usage:
    python eval/compare.py --version v0 --baseline 01-baseline \\
        experiments/03-search-setups/results/*.json
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from metrics import randomization_test
from score import (
    KNOWN_ITEM_TYPES,
    REPO_ROOT,
    load_qrels,
    load_queries,
    load_run,
    per_query,
    score,
    utf8_stdout,
)

SIGNIFICANCE = 0.05
PerQuery = dict[str, dict[str, float | None]]


def cell(value: float | None, marked: bool = False) -> str:
    if value is None:
        return "n/a"
    return f"{value:.3f}{'*' if marked else ''}"


def differs(values: PerQuery, baseline: PerQuery, ids: list[str], name: str) -> bool:
    """Whether the per-query values of one metric differ from the baseline significantly."""
    if not ids:
        return False
    first = [float(values[query_id][name] or 0.0) for query_id in ids]
    second = [float(baseline[query_id][name] or 0.0) for query_id in ids]
    return randomization_test(first, second) < SIGNIFICANCE


def main_row(name: str, summary: dict[str, Any], marks: dict[str, bool]) -> list[str]:
    item = summary["known_item"] or {}
    overall = item.get("all") or {}
    cross = item.get("cross_lingual") or {}
    topic = (summary["topic"] or {}).get("all") or {}
    consistency = (summary["consistency"] or {}).get("all") or {}
    return [
        name,
        cell(overall.get("mrr@10"), marks["mrr@10"]),
        cell(overall.get("success@1")),
        cell(overall.get("success@10"), marks["success@10"]),
        cell(overall.get("success@100")),
        cell(cross.get("success@10"), marks["cross success@10"]),
        cell(topic.get("ndcg@10"), marks["ndcg@10"]),
        cell(consistency.get("rbo")),
    ]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", required=True)
    parser.add_argument("--baseline", required=True, help="setup name of the baseline")
    parser.add_argument("results", nargs="+", type=Path)
    args = parser.parse_args()
    utf8_stdout()

    queries = load_queries(args.version)
    qrels = load_qrels(args.version)
    known = [query for query in queries if query["type"] in KNOWN_ITEM_TYPES]
    known_ids = [query["id"] for query in known]
    cross_ids = [query["id"] for query in known if query["lang"] != query["target_lang"]]
    topic_ids = [query["id"] for query in queries if query["type"] not in KNOWN_ITEM_TYPES]

    setups: list[tuple[str, dict[str, Any], PerQuery]] = []
    for path in args.results:
        results_path = path if path.is_absolute() else REPO_ROOT / path
        results = json.loads(results_path.read_text(encoding="utf-8"))
        run = load_run(REPO_ROOT / results["run"])
        setups.append((results["setup"], score(args.version, run), per_query(queries, qrels, run)))
    by_name = {name: values for name, _, values in setups}
    if args.baseline not in by_name:
        raise SystemExit(f"baseline {args.baseline} is not among the results")
    baseline = by_name[args.baseline]

    print("| Setup | MRR@10 | S@1 | S@10 | S@100 | S@10 cross-lingual | nDCG@10 | RBO |")
    print("| --- | --- | --- | --- | --- | --- | --- | --- |")
    for name, summary, values in setups:
        other = name != args.baseline
        marks = {
            "mrr@10": other and differs(values, baseline, known_ids, "mrr@10"),
            "success@10": other and differs(values, baseline, known_ids, "success@10"),
            "cross success@10": other and differs(values, baseline, cross_ids, "success@10"),
            "ndcg@10": other and differs(values, baseline, topic_ids, "ndcg@10"),
        }
        print("| " + " | ".join(main_row(name, summary, marks)) + " |")

    print("\nSuccess@10 by query type:\n")
    print("| Setup | " + " | ".join(KNOWN_ITEM_TYPES) + " |")
    print("| --- |" + " --- |" * len(KNOWN_ITEM_TYPES))
    for name, summary, _ in setups:
        by_type = (summary["known_item"] or {}).get("by_type") or {}
        cells = [cell((by_type.get(kind) or {}).get("success@10")) for kind in KNOWN_ITEM_TYPES]
        print(f"| {name} | " + " | ".join(cells) + " |")
    print(
        f"\n* differs from {args.baseline} with p < {SIGNIFICANCE} "
        "(paired randomization test over queries)"
    )


if __name__ == "__main__":
    main()
