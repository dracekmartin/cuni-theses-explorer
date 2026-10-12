"""Download the body texts listed in the catalog.

A text is done when its file exists: it was checked against the size and MD5 from the
catalog before it was written. Texts the catalog marks as not openly accessible are not
requested. A failed text goes to texts-failed.jsonl with its reason. A transient failure
is retried on the next run. One with an answer from the server (HTTP 4xx, a redirect to
the restricted-resource page, a wrong checksum) only with --retry-failed.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import logging
import random
import time
from collections import Counter
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from common import (
    CATALOG_PATH,
    FAILED_PATH,
    TEXTS_DIR,
    check_disk,
    stem,
    text_path,
    write_atomic,
)
from oai import Client, ItemFailedError, duration

SHUFFLE_SEED = 20261011
MAX_FAILURES_IN_A_ROW = 50
PROGRESS_EVERY = 500
PROGRESS_EVERY_S = 120

log = logging.getLogger("harvest")


@dataclass
class Failure:
    kind: str
    reason: str

    @property
    def transient(self) -> bool:
        return self.kind == "transient"


def iter_catalog() -> Iterator[dict[str, Any]]:
    with gzip.open(CATALOG_PATH, "rt", encoding="utf-8") as catalog:
        for line in catalog:
            yield json.loads(line)


def load_failures() -> dict[str, Failure]:
    """The last recorded failure of each thesis."""
    failures: dict[str, Failure] = {}
    if FAILED_PATH.exists():
        for line in FAILED_PATH.read_text(encoding="utf-8").splitlines():
            if line.strip():
                record = json.loads(line)
                failures[record["handle"]] = Failure(record["kind"], record["reason"])
    return failures


def record_failure(handle: str, failure: Failure) -> None:
    line = {
        "handle": handle,
        "kind": failure.kind,
        "reason": failure.reason,
        "time": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    with FAILED_PATH.open("a", encoding="utf-8", newline="\n") as file:
        file.write(json.dumps(line, ensure_ascii=False) + "\n")


def downloaded() -> set[str]:
    """Stems of the texts on disk, after removing .part files of an interrupted run."""
    if not TEXTS_DIR.exists():
        return set()
    for partial in TEXTS_DIR.rglob("*.part"):
        partial.unlink()
    return {path.name.removesuffix(".txt.gz") for path in TEXTS_DIR.rglob("*.txt.gz")}


def read_first(path: Path | None) -> list[str]:
    if path is None:
        return []
    return [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def fetch(client: Client, handle: str, body: dict[str, Any]) -> Failure | None:
    """Download one body text and write it when size and MD5 match the catalog."""
    try:
        response = client.get(body["url"])
    except ItemFailedError as failure:
        return Failure("transient", str(failure))
    if response.status_code != 200:
        return Failure("http", f"HTTP {response.status_code}")
    if "restricted-resource" in response.url:
        return Failure("restricted", "redirected to the restricted-resource page")
    data = response.content
    if len(data) != body["size"] or hashlib.md5(data).hexdigest() != body["md5"]:
        return Failure("checksum", f"{len(data)} bytes, the catalog says {body['size']}")
    write_atomic(text_path(handle), gzip.compress(data, 6))
    return None


def plan(first: list[str], retry_failed: bool) -> tuple[list[tuple[str, Any]], Counter[str]]:
    """Texts still to download: the handles given first, then the rest in a fixed random
    order, so whatever part is on disk is a random sample of the university."""
    done = downloaded()
    failures = load_failures()
    counts: Counter[str] = Counter()
    todo: dict[str, Any] = {}
    for entry in iter_catalog():
        handle, body = entry["handle"], entry["body"]
        if entry["body_missing"] is not None:
            counts[f"skipped, {entry['body_missing']}"] += 1
        elif stem(handle) in done:
            counts["already on disk"] += 1
        elif handle in failures and not failures[handle].transient and not retry_failed:
            counts[f"failed before, {failures[handle].kind}"] += 1
        else:
            todo[handle] = body
    rest = sorted(set(todo) - set(first))
    random.Random(SHUFFLE_SEED).shuffle(rest)
    order = [handle for handle in first if handle in todo] + rest
    return [(handle, todo[handle]) for handle in order], counts


def download_texts(client: Client, first: list[str], retry_failed: bool) -> Counter[str]:
    """Download what is missing. Stops when the server refuses too many texts in a row."""
    todo, counts = plan(first, retry_failed)
    for name, count in sorted(counts.items()):
        log.info("texts: %s: %d", name, count)
    given = set(first)
    first_count = sum(handle in given for handle, _ in todo)
    log.info("texts: %d to download, %d of them given first", len(todo), first_count)
    outcome: Counter[str] = Counter()
    started = last_report = time.monotonic()
    in_a_row = 0
    for position, (handle, body) in enumerate(todo, start=1):
        if position % PROGRESS_EVERY == 0:
            check_disk()
        failure = fetch(client, handle, body)
        if failure is None:
            outcome["downloaded"] += 1
            outcome["bytes"] += body["size"]
            in_a_row = 0
        else:
            outcome[f"failed, {failure.kind}"] += 1
            record_failure(handle, failure)
            log.warning("%s: %s (%s)", handle, failure.kind, failure.reason)
            in_a_row = 0 if failure.transient else in_a_row + 1
            if in_a_row >= MAX_FAILURES_IN_A_ROW:
                raise SystemExit(
                    f"{in_a_row} texts in a row refused, which looks like a block or a change "
                    "of URLs. Check texts-failed.jsonl before running again"
                )
        now = time.monotonic()
        if position % PROGRESS_EVERY == 0 or now - last_report >= PROGRESS_EVERY_S:
            last_report = now
            rate = position / (now - started)
            latency = client.median_latency()
            log.info(
                "texts: %d/%d (%.1f %%), %.1f per s, %s left, %d failed, latency %s",
                position,
                len(todo),
                100 * position / len(todo),
                rate,
                duration((len(todo) - position) / rate),
                sum(count for name, count in outcome.items() if name.startswith("failed")),
                f"{latency:.2f} s" if latency is not None else "?",
            )
    return outcome
