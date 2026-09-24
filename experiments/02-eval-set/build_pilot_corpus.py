"""Build the pilot evaluation corpus (eval/v0) from a sample of departments.

Walks the first items of the thesis collection of several faculties through the DSpace
REST API, keeps defended theses with a text layer, groups them by department and draws
whole departments. Theses of one department overlap in topic, so the corpus contains
works that a search can confuse, which a sample spread thinly over the university would
not. The theses of experiment 01 and the showcase thesis on C# are added, so that the
showcase queries have their targets in the corpus. Texts come from the DSpace TEXT
bundle; PDFs are not downloaded.

This is a pilot: the walked items are the first ones of each collection in API order,
not a sample of the whole university. Version v1 will sample from a full catalog.

Outputs: data/eval-v0/catalog/<faculty>.jsonl (every walked item), data/eval-v0/corpus.jsonl
(metadata of the corpus theses), data/eval-v0/texts/<stem>.txt, eval/v0/corpus.txt.

Usage:
    python experiments/02-eval-set/build_pilot_corpus.py [--items-per-faculty 1000]
"""

from __future__ import annotations

import argparse
import json
import random
import shutil
from collections import Counter, defaultdict

from common import (
    CATALOG_DIR,
    CORPUS_META_PATH,
    EVAL_DIR,
    EXPERIMENT_01_DIR,
    TEXTS_DIR,
    Thesis,
    read_theses,
    utf8_stdout,
    write_theses,
)
from dspace import (
    download,
    fetch_item,
    find_theses_collection,
    iter_collection_items,
    new_session,
    parse_item,
)

DEFAULT_FACULTIES = (
    "Matematicko-fyzikální fakulta",
    "Filozofická fakulta",
    "Přírodovědecká fakulta",
    "1. lékařská fakulta",
    "Právnická fakulta",
    "Fakulta sociálních věd",
)
SHOWCASE_HANDLES = ("20.500.11956/192893",)
SEED = 20260924


def slug(name: str) -> str:
    return "".join(char if char.isalnum() else "-" for char in name.lower()).strip("-")


def walk_faculties(faculties: tuple[str, ...], items_per_faculty: int) -> list[Thesis]:
    """Catalog of the walked items, one file per faculty, so that a rerun skips done ones."""
    CATALOG_DIR.mkdir(parents=True, exist_ok=True)
    session = new_session()
    catalog: list[Thesis] = []
    for faculty in faculties:
        path = CATALOG_DIR / f"{slug(faculty)}.jsonl"
        if path.exists():
            catalog.extend(read_theses(path))
            continue
        collection = find_theses_collection(session, faculty)
        if collection is None:
            print(f"{faculty}: no thesis collection found, skipped")
            continue
        theses = [
            parse_item(item, faculty)
            for item in iter_collection_items(session, collection, items_per_faculty)
            if item.get("handle")
        ]
        write_theses(path, theses)
        catalog.extend(theses)
        print(f"{faculty}: {len(theses)} items walked")
    return catalog


def eligible(thesis: Thesis) -> bool:
    """Defended, with a text layer and a known department."""
    return (
        thesis.defence_status in (None, "O")
        and thesis.text_link is not None
        and bool(thesis.department)
    )


def sample_departments(
    catalog: list[Thesis], departments: int, per_department: int, faculties: int
) -> list[Thesis]:
    """Draw whole departments, at most an even share of them per faculty."""
    groups: dict[tuple[str, str], list[Thesis]] = defaultdict(list)
    for thesis in catalog:
        if eligible(thesis) and thesis.department:
            groups[(thesis.faculty, thesis.department)].append(thesis)
    candidates = sorted(key for key, members in groups.items() if len(members) >= per_department)
    rng = random.Random(SEED)
    rng.shuffle(candidates)
    cap = -(-departments // faculties)
    per_faculty: Counter[str] = Counter()
    chosen: list[Thesis] = []
    for faculty, department in candidates:
        if len(chosen) >= departments * per_department:
            break
        if per_faculty[faculty] >= cap:
            continue
        per_faculty[faculty] += 1
        members = sorted(groups[(faculty, department)], key=lambda thesis: thesis.handle)
        for thesis in rng.sample(members, per_department):
            thesis.source = "department-sample"
            chosen.append(thesis)
    return chosen


def experiment_01_handles() -> list[str]:
    manifest = EXPERIMENT_01_DIR / "manifest.jsonl"
    if not manifest.exists():
        return []
    with manifest.open(encoding="utf-8") as file:
        return [json.loads(line)["handle"] for line in file if line.strip()]


def add_fixed_theses(chosen: list[Thesis], catalog: list[Thesis]) -> list[Thesis]:
    """Add the experiment 01 and showcase theses, from the catalog or fetched one by one."""
    by_handle = {thesis.handle: thesis for thesis in catalog}
    present = {thesis.handle for thesis in chosen}
    session = new_session()
    fixed = [(handle, "experiment-01") for handle in experiment_01_handles()]
    fixed += [(handle, "showcase") for handle in SHOWCASE_HANDLES]
    for handle, source in fixed:
        if handle in present:
            continue
        thesis = by_handle.get(handle) or parse_item(fetch_item(session, handle))
        thesis.source = source
        chosen.append(thesis)
        present.add(handle)
    return chosen


def fetch_texts(corpus: list[Thesis]) -> list[Thesis]:
    """Make sure every corpus thesis has its text locally; drop the ones without any."""
    TEXTS_DIR.mkdir(parents=True, exist_ok=True)
    session = new_session()
    kept: list[Thesis] = []
    for position, thesis in enumerate(corpus, start=1):
        destination = TEXTS_DIR / f"{thesis.stem}.txt"
        local = EXPERIMENT_01_DIR / "dspace-text" / f"{thesis.stem}.txt"
        if not destination.exists():
            if local.exists():
                shutil.copyfile(local, destination)
            elif thesis.text_link:
                download(session, thesis.text_link, destination)
            else:
                print(f"{thesis.handle}: no text layer, dropped")
                continue
        kept.append(thesis)
        if position % 50 == 0:
            print(f"texts: {position}/{len(corpus)}")
    return kept


def print_summary(corpus: list[Thesis]) -> None:
    print(f"\ncorpus: {len(corpus)} theses")
    for label, counter in (
        ("faculty", Counter(thesis.faculty for thesis in corpus)),
        ("source", Counter(thesis.source for thesis in corpus)),
        ("language", Counter(thesis.language or "?" for thesis in corpus)),
        ("department", Counter(thesis.department or "?" for thesis in corpus)),
    ):
        print(f"by {label}:")
        for value, count in counter.most_common():
            print(f"  {count:4d}  {value}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--items-per-faculty", type=int, default=1000)
    parser.add_argument("--departments", type=int, default=25)
    parser.add_argument("--per-department", type=int, default=20)
    args = parser.parse_args()
    utf8_stdout()

    catalog = walk_faculties(DEFAULT_FACULTIES, args.items_per_faculty)
    print(f"catalog: {len(catalog)} items, {sum(map(eligible, catalog))} eligible")
    chosen = sample_departments(
        catalog, args.departments, args.per_department, len(DEFAULT_FACULTIES)
    )
    corpus = fetch_texts(add_fixed_theses(chosen, catalog))
    corpus.sort(key=lambda thesis: thesis.handle)

    write_theses(CORPUS_META_PATH, corpus)
    EVAL_DIR.mkdir(parents=True, exist_ok=True)
    (EVAL_DIR / "corpus.txt").write_text(
        "".join(f"{thesis.handle}\n" for thesis in corpus), encoding="utf-8"
    )
    print_summary(corpus)


if __name__ == "__main__":
    main()
