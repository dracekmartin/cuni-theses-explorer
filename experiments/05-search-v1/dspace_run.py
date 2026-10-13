"""Rank the theses of the corpus with the search of DSpace, as one more run of the set.

Every query goes to the OpenSearch interface of DSpace (the Discovery search of the
repository) as a user would type it, so the run measures what a user gets today. DSpace
searches the whole repository, and the run keeps the theses of the corpus in the order
DSpace gave them. Pages of 100 results are fetched until the run has RESULTS_PER_QUERY theses of
the corpus, the results end, or MAX_DEPTH results were read. With --escaped the
characters of the Solr query syntax are escaped first (a question mark is a wildcard
there, a colon names a field), which gives the run dspace-escaped. A percent sign is
dropped in both runs: OpenSearch answers any query with it by HTTP 500, while the web
search of DSpace answers the same query.

Every answer is stored gzipped under data/05-search-v1/dspace/, so a stopped run
continues and a rerun asks only for new queries. Outages are waited out. A query that
keeps failing while the repository answers other requests gets an empty result and is
counted in the results file. With --limit N the script only probes N queries drawn at
random and prints how deep they went, without writing a run.

Usage:
    python experiments/05-search-v1/dspace_run.py [--version v1] [--escaped] [--limit 20]
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import random
import re
import statistics
import time
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path
from typing import Any

import requests
from common import (
    EXPERIMENT,
    EXPERIMENT_DIR,
    RESULTS_DIR,
    RUNS_DIR,
    WORK_DIR,
    eval_dir,
    load_queries,
    utf8_stdout,
)

OPENSEARCH = "https://dspace.cuni.cz/open-search/discover"
HEALTH_URL = "https://dspace.cuni.cz/oai/request?verb=Identify"
USER_AGENT = (
    "cuni-theses-explorer/experiment-05 (+https://github.com/dracekmartin/cuni-theses-explorer)"
)
ATOM = "{http://www.w3.org/2005/Atom}"
PAGE_SIZE = 100
MAX_DEPTH = 1000
RESULTS_PER_QUERY = 100
SECONDS_BETWEEN_REQUESTS = 1.0
TIMEOUT_S = (30, 120)
# Discovery throws occasional HTTP 500 while the rest of DSpace answers.
ATTEMPTS_PER_QUERY = 5
MAX_PAUSE_S = 600
SOLR_SPECIAL = re.compile(r'([+\-!(){}\[\]^"~*?:\\/]|&&|\|\|)')
CACHE_DIR = WORK_DIR / "dspace"


class QueryFailedError(Exception):
    """One query keeps failing while the repository answers other requests."""


class Client:
    """One session, one request at a time, waiting out outages without a limit."""

    def __init__(self) -> None:
        self.session = requests.Session()
        self.session.headers["User-Agent"] = USER_AGENT
        self.last_start = 0.0
        self.requests = 0

    def _wait_turn(self) -> None:
        pause = self.last_start + SECONDS_BETWEEN_REQUESTS - time.monotonic()
        if pause > 0:
            time.sleep(pause)
        self.last_start = time.monotonic()

    def healthy(self) -> bool:
        self._wait_turn()
        try:
            response = self.session.get(HEALTH_URL, timeout=TIMEOUT_S)
        except requests.RequestException:
            return False
        return response.status_code == 200 and b"<Identify>" in response.content

    def page(self, text: str, start: int) -> bytes:
        failures, pause = 0, 5
        params = {"query": text, "format": "atom", "rpp": PAGE_SIZE, "start": start}
        while True:
            self._wait_turn()
            try:
                response = self.session.get(OPENSEARCH, params=params, timeout=TIMEOUT_S)
            except requests.RequestException as error:
                reason = type(error).__name__
            else:
                self.requests += 1
                if response.status_code == 200 and _is_feed(response.content):
                    return response.content
                reason = f"HTTP {response.status_code}"
            failures += 1
            if failures >= ATTEMPTS_PER_QUERY and self.healthy():
                raise QueryFailedError(f"{reason} after {failures} attempts")
            print(f"{reason} for {text[:60]!r}, failure {failures}, next try in {pause} s")
            time.sleep(pause)
            pause = min(pause * 2, MAX_PAUSE_S)


def _is_feed(content: bytes) -> bool:
    try:
        return ET.fromstring(content).tag == f"{ATOM}feed"
    except ET.ParseError:
        return False


def query_text(text: str, escaped: bool) -> str:
    """What goes to DSpace: the query as typed, without the percent sign OpenSearch fails on."""
    text = " ".join(text.replace("%", " ").split())
    return SOLR_SPECIAL.sub(r"\\\1", text) if escaped else text


def cache_path(text: str, start: int) -> Path:
    digest = hashlib.sha1(text.encode("utf-8")).hexdigest()
    return CACHE_DIR / digest[:2] / f"{digest}.{start}.xml.gz"


def parse_page(content: bytes) -> tuple[list[str], int]:
    """Handles of the results in DSpace order, and the total number of results."""
    root = ET.fromstring(content)
    total = int(root.findtext("{http://a9.com/-/spec/opensearch/1.1/}totalResults") or 0)
    handles = []
    for entry in root.iter(f"{ATOM}entry"):
        identifier = entry.findtext(f"{ATOM}id") or ""
        if "hdl.handle.net/" in identifier:
            handles.append(identifier.split("hdl.handle.net/", 1)[1].strip())
    return handles, total


def search(client: Client, text: str, corpus: set[str]) -> dict[str, Any]:
    """DSpace order of the corpus theses for one query, with how deep it had to go.

    When a later page keeps failing, the theses of the earlier pages stay in the result.
    DSpace counts `start` from 1, so consecutive pages overlap by one result, which the
    check against `ranked` removes.
    """
    ranked: list[str] = []
    total, start, pages = 0, 0, 0
    while start < MAX_DEPTH:
        path = cache_path(text, start)
        if path.exists():
            content = gzip.decompress(path.read_bytes())
        else:
            try:
                content = client.page(text, start)
            except QueryFailedError:
                if not pages:
                    raise
                return {
                    "theses": ranked[:RESULTS_PER_QUERY],
                    "total": total,
                    "depth": start,
                    "pages": pages,
                    "partial": True,
                }
            path.parent.mkdir(parents=True, exist_ok=True)
            partial = path.with_name(path.name + ".part")
            partial.write_bytes(gzip.compress(content))
            partial.replace(path)
        handles, total = parse_page(content)
        pages += 1
        ranked += [handle for handle in handles if handle in corpus and handle not in ranked]
        start += PAGE_SIZE
        if len(ranked) >= RESULTS_PER_QUERY or not handles or start > total:
            break
    return {
        "theses": ranked[:RESULTS_PER_QUERY],
        "total": total,
        "depth": min(start, total),
        "pages": pages,
        "partial": False,
    }


def write_results(name: str, version: str, outcome: dict[str, Any]) -> None:
    """Results file in the form of the search setups, so eval/score.py scores it alike."""
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    path = RESULTS_DIR / f"{name}.json"
    previous = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    escaped = name.endswith("escaped")
    results = {
        "experiment": EXPERIMENT,
        "setup": name,
        "description": "The search of DSpace (OpenSearch over Discovery), restricted to the "
        "theses of the corpus" + (", Solr syntax escaped." if escaped else ", queries as typed."),
        "run": (RUNS_DIR / f"{name}.run").relative_to(EXPERIMENT_DIR.parents[1]).as_posix(),
        "pipeline": {
            "harvest": {"source": "live DSpace search", "date": time.strftime("%Y-%m-%d")},
            "strategy": {
                "sources": ["DSpace OpenSearch"],
                "page_size": PAGE_SIZE,
                "max_depth": MAX_DEPTH,
                "escaped": escaped,
            },
        },
        "cost": outcome["cost"],
        "eval_version": previous.get("eval_version"),
        "metrics": previous.get("metrics", {}),
    }
    path.write_text(json.dumps(results, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--version", default="v1")
    parser.add_argument("--escaped", action="store_true", help="escape the Solr syntax")
    parser.add_argument("--limit", type=int, help="only probe N random queries, write no run")
    args = parser.parse_args()
    utf8_stdout()
    name = "dspace-escaped" if args.escaped else "dspace"
    if args.version != "v1" and not args.limit:
        raise SystemExit(
            "the runs of experiment 05 belong to v1, a run on another version would replace them"
        )
    corpus = set((eval_dir(args.version) / "corpus.txt").read_text(encoding="utf-8").split())
    queries = load_queries(args.version)
    if args.limit:
        queries = random.Random(20261012).sample(queries, args.limit)

    client = Client()
    answers: list[dict[str, Any]] = []
    failed: list[str] = []
    for position, query in enumerate(queries, start=1):
        text = query_text(query["text"], args.escaped)
        try:
            answers.append(search(client, text, corpus))
        except QueryFailedError as failure:
            print(f"{query['id']}: {failure}, empty result")
            answers.append({"theses": [], "total": 0, "depth": 0, "pages": 0, "partial": True})
        if answers[-1]["partial"]:
            failed.append(query["id"])
        if args.limit:
            answer = answers[-1]
            print(
                f"{query['type']:15} total {answer['total']:6d} depth {answer['depth']:4d} "
                f"corpus {len(answer['theses']):3d}  {query['text'][:70]}"
            )
        elif position % 100 == 0:
            print(f"queries: {position}/{len(queries)}, {client.requests} requests")

    depths = [answer["depth"] for answer in answers]
    print(
        f"{len(queries)} queries, {client.requests} new requests, median depth "
        f"{statistics.median(depths):.0f}, no result for "
        f"{sum(answer['total'] == 0 for answer in answers)}, failed {len(failed)}"
    )
    empty = Counter(
        query["type"]
        for query, answer in zip(queries, answers, strict=True)
        if answer["total"] == 0
    )
    print(f"no result by type: {dict(empty)}")
    if args.limit:
        return
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    with (RUNS_DIR / f"{name}.run").open("w", encoding="utf-8", newline="\n") as run_file:
        for query, answer in zip(queries, answers, strict=True):
            for rank, handle in enumerate(answer["theses"], start=1):
                run_file.write(f"{query['id']} Q0 {handle} {rank} {1 / rank:.6f} {name}\n")
    # No latency: most pages come from the cache, and a page of DSpace takes seconds over
    # the network, which compares to nothing the setups measure on this laptop.
    cost = {
        "pages": sum(answer["pages"] for answer in answers),
        "failed_or_partial_queries": failed,
        "zero_result_queries": sum(answer["total"] == 0 for answer in answers),
    }
    write_results(name, args.version, {"cost": cost})
    print(f"run written to {(RUNS_DIR / f'{name}.run').relative_to(EXPERIMENT_DIR.parents[1])}")


if __name__ == "__main__":
    main()
