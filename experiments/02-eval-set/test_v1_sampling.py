"""The draws of v1: departments for the corpus, and judged pairs for the human check."""

from __future__ import annotations

import json
import random
from collections import Counter
from pathlib import Path
from typing import Any

import build_v1_corpus
import pytest
from build_v1_corpus import draw_departments
from common import VERSION, Thesis
from topics import draw_sample, human_grades_from_page


def thesis(handle: str) -> Thesis:
    return Thesis(
        handle=handle,
        uuid="",
        faculty="",
        department=None,
        thesis_type=None,
        year=None,
        language=None,
        title="",
        title_lang=None,
        title_translated=None,
        title_translated_lang=None,
        abstract_cs=None,
        abstract_en=None,
    )


def judged(counts: dict[int, int]) -> list[tuple[dict[str, Any], Thesis, int]]:
    topic = {"id": "topic-01"}
    return [
        (topic, thesis(f"h/{grade}-{number}"), grade)
        for grade, count in counts.items()
        for number in range(count)
    ]


def test_sample_takes_an_even_share_of_each_grade() -> None:
    sample = draw_sample(judged({0: 200, 1: 80, 2: 60}), 150)
    assert Counter(grade for *_, grade in sample) == {0: 50, 1: 50, 2: 50}


def test_sample_fills_up_when_a_grade_is_short() -> None:
    sample = draw_sample(judged({0: 200, 1: 80, 2: 20}), 150)
    counts = Counter(grade for *_, grade in sample)
    assert counts[2] == 20
    assert sum(counts.values()) == 150
    assert len({pair[1].handle for pair in sample}) == 150


def test_departments_cover_every_faculty_and_stop_when_full(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(build_v1_corpus, "NEW_THESES", 200)
    pool = {
        (faculty, f"department {number}"): [
            thesis(f"h/{faculty}{number}-{index}") for index in range(30)
        ]
        for faculty in ("A", "B", "C")
        for number in range(6)
    }
    drawn = draw_departments(pool, random.Random(1))
    assert all(sum(key[0] == faculty for key in drawn) >= 2 for faculty in ("A", "B", "C"))
    assert len(drawn) == len(set(drawn))
    assert 30 * len(drawn) >= 200 > 30 * (len(drawn) - 1)


def test_page_grades_leave_out_unsure_and_ungraded_pairs(tmp_path: Path) -> None:
    saved = tmp_path / "validation-grades.json"
    grades = [
        {"topic": "topic-01", "handle": "h/1", "grade": 2},
        {"topic": "topic-01", "handle": "h/2", "grade": "?"},
        {"topic": "topic-01", "handle": "h/3", "grade": None},
        {"topic": "topic-02", "handle": "h/4", "grade": 0},
    ]
    saved.write_text(json.dumps({"version": VERSION, "grades": grades}), encoding="utf-8")
    assert human_grades_from_page(saved) == [("topic-01", "h/1", 2), ("topic-02", "h/4", 0)]


def test_page_grades_of_another_version_are_refused(tmp_path: Path) -> None:
    saved = tmp_path / "validation-grades.json"
    saved.write_text(json.dumps({"version": "v9", "grades": []}), encoding="utf-8")
    with pytest.raises(SystemExit):
        human_grades_from_page(saved)
