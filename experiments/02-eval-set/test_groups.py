"""Groups of records of the same thesis and their representatives in v2."""

from __future__ import annotations

from typing import Any

from groups import candidate_groups, member, normalize, outcome, representative, same_work


def entry(
    handle: str,
    title: str = "Právní úprava prostituce",
    author: str = "Nováková, Jana",
    kind: str = "diplomová práce",
    grade: str | None = "Výborně",
    accepted: str = "2019-06-01",
    status: str | None = None,
) -> dict[str, Any]:
    fields: dict[str, Any] = {"dc.creator": [[author, None]]}
    if grade:
        fields["thesis.grade.cs"] = [[grade, "cs_CZ"]]
    fields["dcterms.dateAccepted"] = [[accepted, None]]
    return {
        "handle": handle,
        "title": title,
        "thesis_type": kind,
        "defence_status": status,
        "year": accepted[:4],
        "fields": fields,
    }


def test_title_and_author_compared_without_case_diacritics_and_punctuation() -> None:
    assert normalize("Právní úprava: PROSTITUCE!") == "pravni uprava prostituce"
    records = [
        member(entry("h/1")),
        member(entry("h/2", title="Pravni uprava prostituce.", author="Nováková, Jana,")),
        member(entry("h/3", author="Novák, Jan")),
    ]
    assert [[item.handle for item in items] for items in candidate_groups(records).values()] == [
        ["h/1", "h/2"]
    ]


def test_outcome_from_the_status_or_the_grade() -> None:
    assert outcome(entry("h/1", status="N", grade="Výborně")) == "N"
    assert outcome(entry("h/1", grade="Neprospěl/a")) == "N"
    assert outcome(entry("h/1", grade="Nedostatečně")) == "N"
    assert outcome(entry("h/1", grade="Uznáno")) == "U"
    assert outcome(entry("h/1", grade="Velmi dobře")) == "O"
    assert outcome(entry("h/1", grade=None)) is None


def test_rigorous_thesis_joins_its_thesis_but_bachelor_and_master_stay_apart() -> None:
    master = member(entry("h/1"))
    rigorous = member(entry("h/2", kind="rigorózní práce", grade="Uznáno"))
    bachelor = member(entry("h/3", kind="bakalářská práce"))
    assert same_work([master, rigorous])
    assert same_work([master, member(entry("h/5", kind="Rigorózní práce"))])
    assert same_work([master, member(entry("h/4", grade="Neprospěl/a"))])
    assert not same_work([bachelor, master])


def test_representative() -> None:
    failed = member(entry("h/1", grade="Neprospěl/a", accepted="2019-09-01"))
    defended = member(entry("h/2", accepted="2019-06-01"))
    later = member(entry("h/3", kind="rigorózní práce", accepted="2020-02-01"))
    usable = {"h/1", "h/2", "h/3"}
    assert representative([failed, defended], set(), usable) == defended
    assert representative([defended, later], set(), usable) == later
    assert representative([defended, later], {"h/2"}, usable) == defended
    assert representative([defended, later], set(), {"h/2"}) == defended
    assert representative([defended, later], set(), set()) is None
