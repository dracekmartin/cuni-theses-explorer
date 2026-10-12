"""Harvest the metadata and body texts of all theses of the university repository.

Three steps run in order, and each skips the work already done, so a restart is the same
command:

1. catalog: every page of OAI-PMH ListRecords (xoai) for the thesis collections, stored
   raw in data/04-full-harvest/oai/<set>/;
2. parse: the pages turned into catalog.jsonl.gz, one thesis per line, with the chosen body
   text file;
3. texts: the body texts, checked against size and MD5 from the catalog, gzipped into
   texts/.

Usage:
    python -u experiments/04-full-harvest/harvest.py [--sets SPEC ...] [--rate 3]
        [--first FILE] [--retry-failed]
    python experiments/04-full-harvest/harvest.py status
"""

from __future__ import annotations

import argparse
import gzip
import json
import logging
import sys
import time
from collections import Counter
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from common import (
    CATALOG_META_PATH,
    CATALOG_PATH,
    DATA_DIR,
    LOCK_PATH,
    LOG_PATH,
    OAI_DIR,
    SETS_PATH,
    TEXTS_DIR,
    check_disk,
    stem,
    utf8_stdout,
    write_atomic,
)
from oai import OAI_NS, Client, harvest_set, list_sets, read_page, set_pages
from texts import download_texts, load_failures, read_first
from xoai import parse_record

THESIS_COLLECTIONS = ("Kvalifikační práce", "Kvalifikační práce obhajované před rokem 2006")
# About one second of pause after each page, which takes the server up to a second.
CATALOG_REQUESTS_PER_SECOND = 0.5
# Raised when parsing changes, so the catalog is rebuilt from the same pages.
CATALOG_FORMAT = 2

log = logging.getLogger("harvest")


def setup_logging() -> None:
    """Log to the console and append to harvest.log, so a restart keeps the history."""
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(message)s", "%Y-%m-%d %H:%M:%S")
    for handler in (logging.FileHandler(LOG_PATH, encoding="utf-8"), logging.StreamHandler()):
        handler.setFormatter(formatter)
        log.addHandler(handler)
    log.setLevel(logging.INFO)


@contextmanager
def single_instance() -> Iterator[None]:
    """Refuse to start next to a running harvest. The OS drops the lock when a process dies.

    A PID file would need a liveness check, and os.kill(pid, 0) terminates the process on
    Windows instead of probing it.
    """
    lock = LOCK_PATH.open("a+")
    lock.seek(0)
    try:
        if sys.platform == "win32":
            import msvcrt

            msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        lock.close()
        raise SystemExit(f"another harvest holds {LOCK_PATH}") from None
    try:
        yield
    finally:
        lock.close()


def keep_awake() -> None:
    """Stop Windows from sleeping on idle while the harvest runs. Closing the lid still
    follows the power settings."""
    if sys.platform == "win32":
        import ctypes

        es_continuous, es_system_required = 0x80000000, 0x00000001
        ctypes.windll.kernel32.SetThreadExecutionState(es_continuous | es_system_required)


def thesis_sets(client: Client, only: list[str] | None) -> list[str]:
    """setSpecs of the thesis collections, listed once and then read from sets.json."""
    if SETS_PATH.exists():
        sets = json.loads(SETS_PATH.read_text(encoding="utf-8"))
    else:
        sets = [
            {"spec": spec, "name": name}
            for spec, name in list_sets(client)
            if spec.startswith("col_") and name in THESIS_COLLECTIONS
        ]
        write_atomic(SETS_PATH, json.dumps(sets, ensure_ascii=False, indent=1).encode("utf-8"))
        log.info("found %d thesis collections", len(sets))
    specs = [item["spec"] for item in sets]
    if only:
        unknown = sorted(set(only) - set(specs))
        if unknown:
            raise SystemExit(f"not a thesis collection: {', '.join(unknown)}")
        specs = [spec for spec in specs if spec in only]
    return specs


def build_catalog(specs: list[str]) -> dict[str, Any]:
    """catalog.jsonl.gz from the stored pages, rebuilt only when the pages changed.

    A thesis listed twice (mapped into two collections, or shifted between pages while the
    harvest ran) is written once. Deleted records are counted and left out.
    """
    pages = {spec: len(set_pages(spec)) for spec in specs}
    if CATALOG_PATH.exists() and CATALOG_META_PATH.exists():
        meta = json.loads(CATALOG_META_PATH.read_text(encoding="utf-8"))
        if meta.get("pages") == pages and meta.get("format") == CATALOG_FORMAT:
            log.info("catalog: up to date, %d theses", meta["theses"])
            return meta
    started = time.monotonic()
    counts: Counter[str] = Counter()
    seen: set[str] = set()
    text_bytes = 0
    partial = CATALOG_PATH.with_name(CATALOG_PATH.name + ".part")
    with gzip.open(partial, "wt", encoding="utf-8", newline="\n", compresslevel=6) as out:
        for spec in specs:
            in_set: set[str] = set()
            for page in set_pages(spec):
                for record in read_page(page).iter(f"{OAI_NS}record"):
                    entry = parse_record(record)
                    in_set.add(entry["handle"])
                    if entry["deleted"]:
                        counts["deleted"] += 1
                        continue
                    if entry["handle"] in seen:
                        counts["listed twice"] += 1
                        continue
                    seen.add(entry["handle"])
                    body = entry["body"]
                    counts[f"body: {entry['body_missing'] or 'text to download'}"] += 1
                    if body is not None:
                        counts[f"body chosen by {body['rule']}"] += 1
                        counts["body differs from the rule of experiment 01"] += not body[
                            "same_as_largest"
                        ]
                        if entry["body_missing"] is None:
                            text_bytes += body["size"]
                    out.write(json.dumps(entry, ensure_ascii=False) + "\n")
            done = OAI_DIR / spec / "done"
            if done.exists():
                announced = json.loads(done.read_text(encoding="utf-8"))["records"]
                if announced != len(in_set):
                    log.warning(
                        "%s: %d distinct records, the server announced %d",
                        spec,
                        len(in_set),
                        announced,
                    )
            else:
                log.warning("%s: incomplete, the catalog holds only its stored pages", spec)
    partial.replace(CATALOG_PATH)
    meta = {
        "format": CATALOG_FORMAT,
        "pages": pages,
        "theses": len(seen),
        "text_bytes": text_bytes,
        "counts": dict(sorted(counts.items())),
        "built": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    write_atomic(CATALOG_META_PATH, json.dumps(meta, ensure_ascii=False, indent=1).encode())
    log.info(
        "catalog: %d theses, %.1f GB of text to download, built in %.0f s",
        len(seen),
        text_bytes / 1024**3,
        time.monotonic() - started,
    )
    for name, count in meta["counts"].items():
        log.info("catalog:   %s: %d", name, count)
    return meta


def run(args: argparse.Namespace) -> None:
    keep_awake()
    check_disk()
    log.info("harvest started, sets %s", " ".join(args.sets) if args.sets else "all")
    client = Client(CATALOG_REQUESTS_PER_SECOND)
    specs = thesis_sets(client, args.sets)
    incomplete = [spec for spec in specs if not harvest_set(client, spec)]
    if incomplete:
        log.warning("incomplete sets, a rerun tries them again: %s", " ".join(incomplete))
    build_catalog(specs)
    outcome = download_texts(Client(args.rate), read_first(args.first), args.retry_failed)
    log.info(
        "harvest finished: %d texts downloaded (%.1f GB before gzip), %d failed",
        outcome["downloaded"],
        outcome["bytes"] / 1024**3,
        sum(count for name, count in outcome.items() if name.startswith("failed")),
    )


def print_status() -> None:
    """What is on disk now, readable while a harvest runs."""
    sets = json.loads(SETS_PATH.read_text(encoding="utf-8")) if SETS_PATH.exists() else []
    complete = sum((OAI_DIR / item["spec"] / "done").exists() for item in sets)
    pages = sum(len(set_pages(item["spec"])) for item in sets)
    print(f"sets: {complete}/{len(sets)} complete, {pages} pages stored")
    if CATALOG_META_PATH.exists():
        meta = json.loads(CATALOG_META_PATH.read_text(encoding="utf-8"))
        print(f"catalog: {meta['theses']} theses, built {meta['built']}")
        for name, count in meta["counts"].items():
            print(f"  {name}: {count}")
    texts = list(TEXTS_DIR.rglob("*.txt.gz")) if TEXTS_DIR.exists() else []
    size = sum(path.stat().st_size for path in texts)
    print(f"texts: {len(texts)} files, {size / 1024**3:.2f} GB")
    done = {path.name.removesuffix(".txt.gz") for path in texts}
    failures = Counter(
        failure.kind for handle, failure in load_failures().items() if stem(handle) not in done
    )
    for kind, count in sorted(failures.items()):
        print(f"  failed, {kind}: {count}")
    if LOG_PATH.exists():
        lines = LOG_PATH.read_text(encoding="utf-8").splitlines()
        print(f"last log line: {lines[-1] if lines else ''}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument("command", nargs="?", choices=["run", "status"], default="run")
    parser.add_argument("--sets", nargs="+", help="only these setSpecs, for a trial run")
    parser.add_argument("--rate", type=float, default=3.0, help="text requests per second")
    parser.add_argument("--first", type=Path, help="file of handles whose texts come first")
    parser.add_argument(
        "--retry-failed", action="store_true", help="also retry texts the server refused"
    )
    args = parser.parse_args()
    utf8_stdout()
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if args.command == "status":
        print_status()
        return
    with single_instance():
        setup_logging()
        try:
            run(args)
        except KeyboardInterrupt:
            log.info("stopped by the user")
        except SystemExit as stop:
            log.error("stopped: %s", stop)
            raise
        except Exception:
            log.exception("stopped by an unexpected error")
            raise


if __name__ == "__main__":
    main()
