"""Groups of records of the same thesis, for evaluation version v2.

DSpace keeps a rigorous thesis recognized from an earlier master's or doctoral thesis as a
record of its own, with the same title and author, and every attempt to defend a thesis as
another record. Search shows all of them, as DSpace does. The evaluation counts one record
per group: a known-item query that finds the twin of its target found the thesis, and two
twins in the top 10 are one thesis.

A group is two or more records of the catalog with the same title and first author,
compared without case, diacritics and punctuation. A rigorous thesis grew from the master's
or doctoral thesis of the same title and belongs to its group. A bachelor's and a master's
thesis with one title are two works and form no group.

The representative of a group in v2 is a target of v1 when the group has one, else a thesis
of the v1 corpus that has an abstract, and of several the last defended. A failed attempt
stands for its group when it is the only such thesis, because the defended record is not in
the corpus. The other members leave the corpus of v2. Over the whole university (v3) the
representative will be the last defended record.

Outputs: eval/v2/groups.txt (a member and its representative per line, handles only, for
every group with a representative in v2) and data/eval-v2/groups.json (the groups with
titles, authors, types and outcomes, for inspection).

Usage:
    EVAL_VERSION=v2 python experiments/02-eval-set/groups.py
"""

from __future__ import annotations

import json
import random
import unicodedata
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from typing import Any

from build_v1_corpus import iter_catalog
from common import DATA_DIR, EVAL_DIR, REPO_ROOT, require_version, utf8_stdout

V1_CORPUS = REPO_ROOT / "eval" / "v1" / "corpus.txt"
V1_QUERIES = REPO_ROOT / "eval" / "v1" / "queries.jsonl"
ABSTRACTS_PATH = DATA_DIR / "abstracts.jsonl"
GROUPS_PATH = EVAL_DIR / "groups.txt"
DETAILS_PATH = DATA_DIR / "groups.json"
RIGOROUS = "rigorózní práce"
SEED = 20261103


@dataclass
class Member:
    """One record of a group, with what decides which record represents the group."""

    handle: str
    thesis_type: str | None
    outcome: str | None
    accepted: str
    title: str
    author: str


def normalize(text: str) -> str:
    """Lower case letters and digits without diacritics, words separated by one space."""
    decomposed = unicodedata.normalize("NFKD", text.casefold())
    plain = "".join(char for char in decomposed if not unicodedata.combining(char))
    return " ".join("".join(char if char.isalnum() else " " for char in plain).split())


def field(entry: dict[str, Any], name: str) -> str | None:
    values = (entry.get("fields") or {}).get(name) or []
    return values[0][0] if values else None


def first_author(entry: dict[str, Any]) -> str:
    """The first author as DSpace wrote it, which may end with a comma before 2006."""
    author = field(entry, "dc.creator") or field(entry, "dc.contributor.author") or ""
    return author.strip().rstrip(",").strip()


def outcome(entry: dict[str, Any]) -> str | None:
    """O defended, N not defended, U recognized. Records changed before 2021 have no
    outcome in DSpace, so the grade decides: Neprospěl and the older Nedostatečně are N,
    Uznáno U, any other grade O."""
    if entry.get("defence_status"):
        return entry["defence_status"]
    grade = field(entry, "thesis.grade.cs")
    if not grade:
        return None
    if grade.startswith(("Neprospěl", "Nedostatečně")):
        return "N"
    return "U" if grade == "Uznáno" else "O"


def member(entry: dict[str, Any]) -> Member:
    return Member(
        handle=entry["handle"],
        # DSpace writes some types with a capital letter ("Rigorózní práce").
        thesis_type=(entry.get("thesis_type") or "").casefold() or None,
        outcome=outcome(entry),
        accepted=field(entry, "dcterms.dateAccepted") or entry.get("year") or "",
        title=entry.get("title") or "",
        author=first_author(entry),
    )


def key(item: Member) -> tuple[str, str]:
    return normalize(item.title), normalize(item.author)


def same_work(members: list[Member]) -> bool:
    """Whether records with one title and author are one thesis: one type, or a rigorous
    thesis with the thesis it grew from."""
    return len({item.thesis_type for item in members} - {RIGOROUS}) <= 1


def candidate_groups(members: list[Member]) -> dict[tuple[str, str], list[Member]]:
    """Records with the same title and author, where there are two or more."""
    grouped: dict[tuple[str, str], list[Member]] = defaultdict(list)
    for item in members:
        if all(key(item)):
            grouped[key(item)].append(item)
    return {found: items for found, items in grouped.items() if len(items) > 1}


def shape(members: list[Member]) -> str:
    """Why the records belong together, as far as the metadata tell."""
    if any(item.outcome == "U" for item in members):
        return "recognized"
    if len({item.thesis_type for item in members}) == 1:
        return "repeated defence"
    return "rigorous thesis"


def handle_number(handle: str) -> int:
    number = handle.rsplit("/", 1)[-1]
    return int(number) if number.isdigit() else 0


def representative(members: list[Member], targets: set[str], usable: set[str]) -> Member | None:
    """The record that stands for the group in v2: a target first, then the last defended
    thesis of the v1 corpus that has an abstract. None when no record can stand for it."""
    candidates = [item for item in members if item.handle in usable]
    if not candidates:
        return None
    return max(
        candidates,
        key=lambda item: (
            item.handle in targets,
            item.outcome in ("O", "U"),
            item.outcome != "N",
            item.accepted,
            handle_number(item.handle),
        ),
    )


def read_targets() -> set[str]:
    with V1_QUERIES.open(encoding="utf-8") as file:
        return {query["target"] for line in file if (query := json.loads(line))["target"]}


def read_usable() -> set[str]:
    """Theses of the v1 corpus that have an abstract, so that they can enter v2."""
    corpus = set(V1_CORPUS.read_text(encoding="utf-8").split())
    with ABSTRACTS_PATH.open(encoding="utf-8") as file:
        records = [json.loads(line) for line in file]
    return {
        record["handle"]
        for record in records
        if record["handle"] in corpus and "no-abstract" not in record["flags"]
    }


def print_summary(
    groups: dict[tuple[str, str], list[Member]],
    chosen: dict[tuple[str, str], Member],
    usable: set[str],
    targets: set[str],
) -> None:
    print(f"{len(groups)} groups in the catalog: {dict(Counter(map(shape, groups.values())))}")
    print(f"{len(chosen)} groups with a representative in v2: ", end="")
    print(dict(Counter(shape(groups[found]) for found in chosen)))
    leaving = [
        item.handle
        for found, best in chosen.items()
        for item in groups[found]
        if item.handle in usable and item.handle != best.handle
    ]
    print(f"{len(leaving)} theses of the v1 corpus leave v2 as twins: {sorted(leaving)}")
    shared = [found for found in chosen if sum(i.handle in targets for i in groups[found]) > 1]
    print(f"groups with two targets: {len(shared)}")


def print_two_works(candidates: dict[tuple[str, str], list[Member]]) -> None:
    """Records with one title and author that are two works, with a sample to check by."""
    two_works = [items for items in candidates.values() if not same_work(items)]
    kinds = Counter(
        tuple(sorted({item.thesis_type or "?" for item in items})) for items in two_works
    )
    print(f"{len(two_works)} groups of one title and author are two works: {dict(kinds)}")
    rng = random.Random(SEED)
    for items in rng.sample(two_works, min(5, len(two_works))):
        print("  ", [(item.thesis_type, item.outcome, item.accepted) for item in items])


def main() -> None:
    utf8_stdout()
    require_version("v2")
    targets = read_targets()
    usable = read_usable()
    candidates = candidate_groups([member(entry) for entry in iter_catalog()])
    groups = {found: items for found, items in candidates.items() if same_work(items)}
    print_two_works(candidates)
    chosen = {
        found: best
        for found, items in groups.items()
        if (best := representative(items, targets, usable)) is not None
    }
    lines = sorted(
        (item.handle, best.handle) for found, best in chosen.items() for item in groups[found]
    )
    EVAL_DIR.mkdir(parents=True, exist_ok=True)
    GROUPS_PATH.write_text(
        "".join(f"{handle} {best}\n" for handle, best in lines), encoding="utf-8", newline="\n"
    )
    details = [
        {
            "key": " | ".join(found),
            "shape": shape(groups[found]),
            "representative": best.handle,
            "members": [asdict(item) for item in groups[found]],
        }
        for found, best in sorted(chosen.items(), key=lambda pair: pair[1].handle)
    ]
    DETAILS_PATH.write_text(json.dumps(details, ensure_ascii=False, indent=1), encoding="utf-8")
    print_summary(groups, chosen, usable, targets)


if __name__ == "__main__":
    main()
