"""Build the corpus of evaluation version v1 from the catalog of the full harvest.

v1 keeps every thesis of v0, so its queries and judgments stay valid, and adds whole
departments drawn from all faculties of the university. The body texts of all theses come
from experiment 04, which chose another file than v0 had for 15 theses of v0. v0 had a
review or an attachment there, and for 8 of them, scans, the text is now empty. A
department is drawn with probability proportional to its size, every faculty gets at least
two, and at most PER_DEPARTMENT theses come from one department. Theses of one department
overlap in topic, so the corpus holds works a search can confuse. Departments of v0 are
not drawn again. A new thesis must be marked as defended or carry no outcome (59 % of the
new theses carry none), must have a department, and an openly accessible body text of at
least MIN_TEXT_BYTES, which leaves out scans.

Outputs: eval/v1/corpus.txt, data/eval-v1/corpus.jsonl, data/eval-v1/texts/<stem>.txt,
data/eval-v1/departments.json (the drawn departments).

Usage:
    EVAL_VERSION=v1 python experiments/02-eval-set/build_v1_corpus.py
"""

from __future__ import annotations

import gzip
import json
import random
from collections import Counter, defaultdict
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from common import (
    CORPUS_META_PATH,
    DATA_DIR,
    EVAL_DIR,
    HARVEST_DIR,
    REPO_ROOT,
    TEXTS_DIR,
    Thesis,
    read_theses,
    require_version,
    utf8_stdout,
    write_theses,
)

V0_CORPUS = REPO_ROOT / "eval" / "v0" / "corpus.txt"
V0_TEXTS_DIR = REPO_ROOT / "data" / "eval-v0" / "texts"
V0_META_PATH = REPO_ROOT / "data" / "eval-v0" / "corpus.jsonl"
NEW_THESES = 4400
PER_DEPARTMENT = 40
MIN_DEPARTMENTS_PER_FACULTY = 2
MIN_TEXT_BYTES = 20_000
SEED = 20261012
Department = tuple[str, str]


def harvested_text(handle: str) -> Path:
    """Where experiment 04 stored the body text of a thesis."""
    number = handle.rsplit("/", 1)[-1]
    shard = str(int(number) // 1000) if number.isdigit() else "other"
    return HARVEST_DIR / "texts" / shard / f"{handle.replace('/', '_')}.txt.gz"


def iter_catalog() -> Iterator[dict[str, Any]]:
    with gzip.open(HARVEST_DIR / "catalog.jsonl.gz", "rt", encoding="utf-8") as catalog:
        for line in catalog:
            yield json.loads(line)


def to_thesis(entry: dict[str, Any], source: str) -> Thesis:
    body = entry.get("body") or {}
    return Thesis(
        handle=entry["handle"],
        uuid="",
        faculty=entry.get("faculty") or "",
        department=entry.get("department"),
        thesis_type=entry.get("thesis_type"),
        year=entry.get("year"),
        language=entry.get("language"),
        title=entry.get("title") or "",
        title_lang=entry.get("title_lang"),
        title_translated=entry.get("title_translated"),
        title_translated_lang=entry.get("title_translated_lang"),
        abstract_cs=entry.get("abstract_cs"),
        abstract_en=entry.get("abstract_en"),
        keywords_cs=entry.get("keywords_cs") or [],
        keywords_en=entry.get("keywords_en") or [],
        defence_status=entry.get("defence_status"),
        text_link=body.get("url"),
        source=source,
    )


def eligible(entry: dict[str, Any]) -> bool:
    body = entry.get("body")
    return (
        entry.get("defence_status") in (None, "O")
        and bool(entry.get("department"))
        and entry.get("body_missing") is None
        and body is not None
        and body["size"] >= MIN_TEXT_BYTES
        and harvested_text(entry["handle"]).exists()
    )


def draw_departments(pool: dict[Department, list[Thesis]], rng: random.Random) -> list[Department]:
    """Departments drawn with probability proportional to size until the new part is full."""
    remaining = set(pool)

    def draw(candidates: set[Department]) -> Department:
        keys = sorted(candidates)
        chosen = rng.choices(keys, weights=[len(pool[key]) for key in keys])[0]
        remaining.discard(chosen)
        return chosen

    drawn: list[Department] = []
    for faculty in sorted({faculty for faculty, _ in pool}):
        for _ in range(MIN_DEPARTMENTS_PER_FACULTY):
            candidates = {key for key in remaining if key[0] == faculty}
            if candidates:
                drawn.append(draw(candidates))
    while remaining and sum(min(len(pool[key]), PER_DEPARTMENT) for key in drawn) < NEW_THESES:
        drawn.append(draw(remaining))
    return drawn


def write_texts(corpus: list[Thesis]) -> int:
    """Unpack the harvested texts. A v0 thesis without one keeps its v0 text."""
    TEXTS_DIR.mkdir(parents=True, exist_ok=True)
    from_v0 = 0
    for thesis in corpus:
        destination = TEXTS_DIR / f"{thesis.stem}.txt"
        if destination.exists():
            continue
        source = harvested_text(thesis.handle)
        if source.exists():
            data = gzip.decompress(source.read_bytes())
        else:
            data = (V0_TEXTS_DIR / f"{thesis.stem}.txt").read_bytes()
            from_v0 += 1
        partial = destination.with_name(destination.name + ".part")
        partial.write_bytes(data)
        partial.replace(destination)
    return from_v0


def print_summary(corpus: list[Thesis]) -> None:
    print(f"\ncorpus: {len(corpus)} theses")
    for label, counter in (
        ("source", Counter(thesis.source for thesis in corpus)),
        ("faculty", Counter(thesis.faculty for thesis in corpus)),
        ("language", Counter(thesis.language or "?" for thesis in corpus)),
        ("type", Counter(thesis.thesis_type or "?" for thesis in corpus)),
    ):
        print(f"by {label}:")
        for value, count in counter.most_common():
            print(f"  {count:5d}  {value}")


def main() -> None:
    utf8_stdout()
    require_version("v1")
    v0_handles = set(V0_CORPUS.read_text(encoding="utf-8").split())
    v0_fallback = {thesis.handle: thesis for thesis in read_theses(V0_META_PATH)}
    v0: dict[str, Thesis] = {}
    pool: dict[Department, list[Thesis]] = defaultdict(list)
    v0_departments: set[Department] = set()
    for entry in iter_catalog():
        if entry["handle"] in v0_handles:
            v0[entry["handle"]] = to_thesis(entry, "v0")
            v0_departments.add((entry.get("faculty") or "", entry.get("department") or ""))
        elif eligible(entry):
            thesis = to_thesis(entry, "catalog")
            pool[(thesis.faculty, thesis.department or "")].append(thesis)
    for handle in v0_handles - set(v0):
        print(f"{handle}: not in the harvest catalog, metadata taken from v0")
        v0[handle] = v0_fallback[handle]
        v0[handle].source = "v0"
    pool = {key: members for key, members in pool.items() if key not in v0_departments}
    print(f"pool: {sum(map(len, pool.values()))} eligible theses in {len(pool)} departments")

    rng = random.Random(SEED)
    drawn = draw_departments(pool, rng)
    new: list[Thesis] = []
    for key in drawn:
        members = sorted(pool[key], key=lambda thesis: thesis.handle)
        new.extend(rng.sample(members, min(PER_DEPARTMENT, len(members))))
    corpus = sorted([*v0.values(), *new], key=lambda thesis: thesis.handle)

    from_v0 = write_texts(corpus)
    write_theses(CORPUS_META_PATH, corpus)
    EVAL_DIR.mkdir(parents=True, exist_ok=True)
    (EVAL_DIR / "corpus.txt").write_text(
        "".join(f"{thesis.handle}\n" for thesis in corpus), encoding="utf-8", newline="\n"
    )
    departments = [
        {"faculty": faculty, "department": department, "theses": len(pool[(faculty, department)])}
        for faculty, department in drawn
    ]
    (DATA_DIR / "departments.json").write_text(
        json.dumps(departments, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    print(f"drawn {len(drawn)} departments, {len(new)} new theses, {from_v0} texts from v0")
    print_summary(corpus)


if __name__ == "__main__":
    main()
