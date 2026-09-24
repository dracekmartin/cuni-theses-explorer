"""Score one run against a version of the evaluation set.

Reads the run named in a results file, computes the metrics defined in eval/README.md
and writes them into the same results file, next to the pipeline and cost the experiment
wrote there.

Usage:
    python eval/score.py --version v0 --results experiments/03-search-setups/results/<setup>.json
"""

from __future__ import annotations

import argparse
import io
import json
import statistics
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path
from typing import Any

from metrics import judged, ndcg, precision, rbo, recall, reciprocal_rank, success

REPO_ROOT = Path(__file__).resolve().parents[1]
KNOWN_ITEM_TYPES = ("title", "about-short", "about-sentence", "detail")
KNOWN_ITEM_METRICS = ("mrr@10", "success@1", "success@10", "success@100")
TOPIC_METRICS = ("ndcg@10", "p@10", "recall@100", "judged@10")


def load_queries(version: str) -> list[dict[str, Any]]:
    path = REPO_ROOT / "eval" / version / "queries.jsonl"
    with path.open(encoding="utf-8") as file:
        return [json.loads(line) for line in file if line.strip()]


def load_qrels(version: str) -> dict[str, dict[str, int]]:
    qrels: dict[str, dict[str, int]] = defaultdict(dict)
    path = REPO_ROOT / "eval" / version / "qrels.txt"
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            query_id, _, handle, grade = line.split()
            qrels[query_id][handle] = int(grade)
    return qrels


def load_run(path: Path) -> dict[str, list[str]]:
    """Ranked handles per query, ordered by the rank column."""
    rows: dict[str, list[tuple[int, str]]] = defaultdict(list)
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            query_id, _, handle, rank, *_ = line.split()
            rows[query_id].append((int(rank), handle))
    return {query_id: [handle for _, handle in sorted(pairs)] for query_id, pairs in rows.items()}


def per_query(
    queries: list[dict[str, Any]], qrels: dict[str, dict[str, int]], run: dict[str, list[str]]
) -> dict[str, dict[str, float | None]]:
    """Every metric of every query; the unit the averages and the significance tests use."""
    values: dict[str, dict[str, float | None]] = {}
    for query in queries:
        ranking = run.get(query["id"], [])
        judgments = qrels.get(query["id"], {})
        if query["type"] in KNOWN_ITEM_TYPES:
            values[query["id"]] = {
                "mrr@10": reciprocal_rank(ranking, judgments, 10),
                "success@1": success(ranking, judgments, 1),
                "success@10": success(ranking, judgments, 10),
                "success@100": success(ranking, judgments, 100),
            }
        else:
            values[query["id"]] = {
                "ndcg@10": ndcg(ranking, judgments, 10),
                "p@10": precision(ranking, judgments, 10),
                "recall@100": recall(ranking, judgments, 100),
                "judged@10": judged(ranking, judgments, 10),
            }
    return values


def average(
    values: dict[str, dict[str, float | None]], ids: list[str], names: tuple[str, ...]
) -> dict[str, float | int | None] | None:
    """Mean of each metric over the queries where it is defined; None where it never is."""
    if not ids:
        return None
    summary: dict[str, float | int | None] = {"queries": len(ids)}
    for name in names:
        present = [value for query_id in ids if (value := values[query_id][name]) is not None]
        summary[name] = round(statistics.fmean(present), 4) if present else None
    return summary


def consistency(queries: list[dict[str, Any]], run: dict[str, list[str]]) -> dict[str, Any] | None:
    """Rank-biased overlap between the two language versions of each query group."""
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for query in queries:
        groups[query["group"]].append(query)
    scores: dict[str, list[float]] = defaultdict(list)
    for members in groups.values():
        if len(members) != 2:
            continue
        value = rbo(run.get(members[0]["id"], []), run.get(members[1]["id"], []))
        if value is not None:
            scores[members[0]["type"]].append(value)
    everything = [value for values in scores.values() for value in values]
    if not everything:
        return None
    return {
        "all": {"rbo": round(statistics.fmean(everything), 4), "groups": len(everything)},
        "by_type": {
            kind: {"rbo": round(statistics.fmean(values), 4), "groups": len(values)}
            for kind, values in sorted(scores.items())
        },
    }


def judged_topics(queries: list[dict[str, Any]], qrels: dict[str, dict[str, int]]) -> list[str]:
    """Topic queries that have judgments; a topic without any cannot be scored yet."""
    return [
        query["id"]
        for query in queries
        if query["type"] not in KNOWN_ITEM_TYPES and qrels.get(query["id"])
    ]


def score(version: str, run: dict[str, list[str]]) -> dict[str, Any]:
    queries = load_queries(version)
    qrels = load_qrels(version)
    values = per_query(queries, qrels, run)
    known = [query for query in queries if query["type"] in KNOWN_ITEM_TYPES]
    topics = judged_topics(queries, qrels)

    def ids(selected: list[dict[str, Any]]) -> list[str]:
        return [query["id"] for query in selected]

    by_lang: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for query in known:
        by_lang[f"{query['lang']}->{query['target_lang']}"].append(query)
    known_item = None
    if known:
        known_item = {
            "all": average(values, ids(known), KNOWN_ITEM_METRICS),
            "cross_lingual": average(
                values,
                ids([query for query in known if query["lang"] != query["target_lang"]]),
                KNOWN_ITEM_METRICS,
            ),
            "same_language": average(
                values,
                ids([query for query in known if query["lang"] == query["target_lang"]]),
                KNOWN_ITEM_METRICS,
            ),
            "by_type": {
                kind: average(
                    values,
                    ids([query for query in known if query["type"] == kind]),
                    KNOWN_ITEM_METRICS,
                )
                for kind in KNOWN_ITEM_TYPES
            },
            "by_lang": {
                pair: average(values, ids(members), KNOWN_ITEM_METRICS)
                for pair, members in sorted(by_lang.items())
            },
        }
    return {
        "known_item": known_item,
        "topic": {"all": average(values, topics, TOPIC_METRICS)} if topics else None,
        "consistency": consistency(queries, run),
    }


def utf8_stdout() -> None:
    if isinstance(sys.stdout, io.TextIOWrapper):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", required=True)
    parser.add_argument("--results", required=True, type=Path)
    args = parser.parse_args()
    utf8_stdout()

    results_path = args.results if args.results.is_absolute() else REPO_ROOT / args.results
    results = json.loads(results_path.read_text(encoding="utf-8"))
    run = load_run(REPO_ROOT / results["run"])
    results["eval_version"] = args.version
    results["scored_at"] = date.today().isoformat()
    results["metrics"] = score(args.version, run)
    results_path.write_text(
        json.dumps(results, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    known = results["metrics"]["known_item"]
    if known:
        overall = known["all"]
        print(
            f"{results['setup']}: MRR@10 {overall['mrr@10']:.3f}, "
            f"Success@10 {overall['success@10']:.3f} over {overall['queries']} known-item queries"
        )
    topic = results["metrics"]["topic"]
    if topic:
        print(f"{results['setup']}: nDCG@10 {topic['all']['ndcg@10']:.3f} over topics")


if __name__ == "__main__":
    main()
