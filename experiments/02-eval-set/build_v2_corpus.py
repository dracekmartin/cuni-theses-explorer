"""Build the corpus and the dev part of evaluation version v2 from v1.

The corpus of v2 is the corpus of v1 without the theses that have no abstract, in the
metadata or in the text (abstracts.py), and without the records that do not represent their
group of records of one thesis (groups.py). Its metadata carry the completed and cleaned
abstracts. The texts are those of v1, so the embeddings of their chunks stay valid.

Both parts of v2 rank the same corpus. The dev part takes all known-item queries of v1 with
their targets, and the 25 topics of v1 without judgments, since experiment 05 chose the
number of summed chunks on both. The test part gets new targets and topics later.

Outputs: eval/v2/dev/corpus.txt, queries.jsonl and qrels.txt, eval/v2/test/corpus.txt,
data/eval-v2/corpus.jsonl and data/eval-v2/texts/<stem>.txt.

Usage:
    EVAL_VERSION=v2 python experiments/02-eval-set/build_v2_corpus.py
"""

from __future__ import annotations

import json
import shutil
from collections import Counter
from dataclasses import replace
from pathlib import Path
from typing import Any

from common import (
    CORPUS_META_PATH,
    DATA_DIR,
    EVAL_DIR,
    REPO_ROOT,
    TEXTS_DIR,
    Thesis,
    read_theses,
    require_version,
    utf8_stdout,
    write_theses,
)

V1_DIR = REPO_ROOT / "eval" / "v1"
V1_DATA_DIR = REPO_ROOT / "data" / "eval-v1"
ABSTRACTS_PATH = DATA_DIR / "abstracts.jsonl"
GROUPS_PATH = EVAL_DIR / "groups.txt"
PARTS = ("dev", "test")


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as file:
        return [json.loads(line) for line in file if line.strip()]


def write_text(path: Path, lines: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(f"{line}\n" for line in lines), encoding="utf-8", newline="\n")


def read_groups() -> dict[str, str]:
    """The representative of every record that belongs to a group."""
    pairs = (line.split() for line in GROUPS_PATH.read_text(encoding="utf-8").splitlines())
    return {member: representative for member, representative in pairs}


def with_abstracts(thesis: Thesis, record: dict[str, Any]) -> Thesis:
    """The metadata of a thesis with the abstracts of v2 and where they came from."""
    slots = {slot: record[slot] for slot in ("cs", "en")}
    return replace(
        thesis,
        abstract_cs=slots["cs"]["text"] if slots["cs"] else None,
        abstract_en=slots["en"]["text"] if slots["en"] else None,
        abstract_source={slot: item["source"] for slot, item in slots.items() if item},
    )


def copy_texts(corpus: list[Thesis]) -> tuple[int, int]:
    """The texts of v1 for the corpus of v2, and how many were copied and removed. A text
    copied before is not copied again, a text of a thesis that left the corpus is removed."""
    TEXTS_DIR.mkdir(parents=True, exist_ok=True)
    copied = 0
    for thesis in corpus:
        source = V1_DATA_DIR / "texts" / f"{thesis.stem}.txt"
        destination = TEXTS_DIR / f"{thesis.stem}.txt"
        if destination.exists() and destination.stat().st_size == source.stat().st_size:
            continue
        partial = destination.with_name(destination.name + ".part")
        shutil.copyfile(source, partial)
        partial.replace(destination)
        copied += 1
    kept = {f"{thesis.stem}.txt" for thesis in corpus}
    stale = [path for path in TEXTS_DIR.glob("*.txt") if path.name not in kept]
    for path in stale:
        path.unlink()
    return copied, len(stale)


def read_judged(path: Path) -> set[str]:
    if not path.exists():
        return set()
    lines = path.read_text(encoding="utf-8").splitlines()
    return {line.split()[2] for line in lines if line.strip()}


def topic_text(query: dict[str, Any]) -> str:
    return " ".join(query["text"].casefold().split())


def check_parts(eval_dir: Path = EVAL_DIR) -> None:
    """Stop when the parts of v2 break the rules of a version: one corpus for both parts,
    targets and judged theses in it, query ids unique, and no target or topic in both
    parts. A topic counts as the same by its group or by its text."""
    corpora = {part: (eval_dir / part / "corpus.txt").read_text(encoding="utf-8") for part in PARTS}
    if len(set(corpora.values())) != 1:
        raise SystemExit("the parts of v2 have different corpora")
    corpus = set(corpora["dev"].split())
    ids: Counter[str] = Counter()
    owners: dict[str, set[str]] = {}
    for part in PARTS:
        queries = read_jsonl(eval_dir / part / "queries.jsonl")
        ids.update(query["id"] for query in queries)
        targets = {query["target"] for query in queries if query["target"]}
        topics = [query for query in queries if not query["target"]]
        owners[part] = targets | {query["group"] for query in topics} | set(map(topic_text, topics))
        outside = (targets | read_judged(eval_dir / part / "qrels.txt")) - corpus
        if outside:
            raise SystemExit(
                f"{part}: targets or judged theses not in the corpus: {sorted(outside)[:5]}"
            )
    if repeated := [query_id for query_id, count in ids.items() if count > 1]:
        raise SystemExit(f"query ids in both parts or twice: {repeated[:5]}")
    if shared := owners["dev"] & owners["test"]:
        raise SystemExit(f"targets or topics in both parts: {sorted(shared)[:5]}")
    print(f"parts checked: {len(corpus)} theses, {sum(ids.values())} queries")


def print_summary(corpus: list[Thesis], without: set[str], twins: set[str]) -> None:
    print(f"corpus: {len(corpus)} theses, left out {len(without)} without an abstract")
    print(f"  and {len(twins)} records that do not represent their group")
    for label, counter in (
        ("faculty", Counter(thesis.faculty for thesis in corpus)),
        ("language", Counter(thesis.language or "?" for thesis in corpus)),
        (
            "abstracts",
            Counter(
                f"{slot} {source}" for t in corpus for slot, source in t.abstract_source.items()
            ),
        ),
    ):
        print(f"by {label}: {dict(counter.most_common())}")


def main() -> None:
    utf8_stdout()
    require_version("v2")
    abstracts = {record["handle"]: record for record in read_jsonl(ABSTRACTS_PATH)}
    if not abstracts or not GROUPS_PATH.exists():
        raise SystemExit("run abstracts.py and groups.py with EVAL_VERSION=v2 first")
    groups = read_groups()
    v1 = read_theses(V1_DATA_DIR / "corpus.jsonl")
    without = {thesis.handle for thesis in v1 if "no-abstract" in abstracts[thesis.handle]["flags"]}
    twins = {
        thesis.handle for thesis in v1 if groups.get(thesis.handle, thesis.handle) != thesis.handle
    }
    corpus = [
        with_abstracts(thesis, abstracts[thesis.handle])
        for thesis in v1
        if thesis.handle not in without | twins
    ]
    corpus.sort(key=lambda thesis: thesis.handle)
    handles = {thesis.handle for thesis in corpus}
    queries = read_jsonl(V1_DIR / "queries.jsonl")
    known = {query["id"] for query in queries if query["target"]}
    qrels = [
        line
        for line in (V1_DIR / "qrels.txt").read_text(encoding="utf-8").splitlines()
        if line.strip() and line.split()[0] in known
    ]
    if lost := {query["target"] for query in queries if query["target"]} - handles:
        raise SystemExit(f"targets of v1 not in the corpus of v2: {sorted(lost)}")

    copied, removed = copy_texts(corpus)
    write_theses(CORPUS_META_PATH, corpus)
    for part in PARTS:
        write_text(EVAL_DIR / part / "corpus.txt", [thesis.handle for thesis in corpus])
    write_text(
        EVAL_DIR / "dev" / "queries.jsonl",
        [json.dumps(query, ensure_ascii=False) for query in queries],
    )
    write_text(EVAL_DIR / "dev" / "qrels.txt", qrels)
    print(f"{copied} texts copied, {removed} removed")
    print(f"dev: {len(queries)} queries and {len(qrels)} judgments")
    print_summary(corpus, without, twins)
    check_parts()


if __name__ == "__main__":
    main()
