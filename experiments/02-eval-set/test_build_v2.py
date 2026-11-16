"""The rules the two parts of v2 must keep, on small parts written by hand."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from build_v2_corpus import check_parts


def known(query_id: str, target: str) -> dict[str, Any]:
    return {
        "id": query_id,
        "group": query_id[:-3],
        "type": "title",
        "target": target,
        "text": "query",
    }


def topic(query_id: str, text: str) -> dict[str, Any]:
    return {"id": query_id, "group": query_id[:-3], "type": "topic", "target": None, "text": text}


def write_parts(
    root: Path, dev: list[dict[str, Any]], test: list[dict[str, Any]], qrels: str
) -> None:
    for part, queries in (("dev", dev), ("test", test)):
        folder = root / part
        folder.mkdir()
        (folder / "corpus.txt").write_text("h/1\nh/2\n", encoding="utf-8")
        lines = "".join(json.dumps(query) + "\n" for query in queries)
        (folder / "queries.jsonl").write_text(lines, encoding="utf-8")
    (root / "dev" / "qrels.txt").write_text(qrels, encoding="utf-8")


def test_parts_that_keep_the_rules(tmp_path: Path) -> None:
    write_parts(
        tmp_path,
        [known("ki-0001-title-cs", "h/1")],
        [topic("topic-26-cs", "pohyb dětí")],
        "ki-0001-title-cs 0 h/1 2\n \n",
    )
    check_parts(tmp_path)


def test_target_outside_the_corpus(tmp_path: Path) -> None:
    write_parts(tmp_path, [], [known("ki-0201-title-cs", "h/9")], "")
    with pytest.raises(SystemExit, match="not in the corpus"):
        check_parts(tmp_path)


def test_one_topic_in_both_parts_under_two_ids(tmp_path: Path) -> None:
    write_parts(
        tmp_path,
        [topic("topic-01-cs", "Zubní kaz u dětí")],
        [topic("topic-26-cs", "zubní  kaz u dětí")],
        "",
    )
    with pytest.raises(SystemExit, match="both parts"):
        check_parts(tmp_path)


def test_topics_go_into_their_part(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import topics

    write_parts(
        tmp_path, [known("ki-0001-title-cs", "h/1")], [known("ki-0201-title-cs", "h/2")], ""
    )
    (tmp_path / "test" / "qrels.txt").write_text("ki-0201-title-cs 0 h/2 2\n", encoding="utf-8")
    listed = tmp_path / "topics.json"
    entries = [
        {"id": "topic-01", "part": "dev", "cs": "zubní kaz", "en": "caries", "narrative": "n"},
        {"id": "topic-26", "part": "test", "cs": "šikana", "en": "bullying", "narrative": "n"},
    ]
    listed.write_text(json.dumps(entries), encoding="utf-8")
    monkeypatch.setattr(topics, "VERSION", "v2")
    monkeypatch.setattr(topics, "EVAL_DIR", tmp_path)
    monkeypatch.setattr(topics, "TOPICS_PATH", listed)
    monkeypatch.setattr(topics, "check_parts", lambda: None)
    topics.add()
    for part, kept, topic in (("dev", "ki-0001", "topic-01"), ("test", "ki-0201", "topic-26")):
        lines = (tmp_path / part / "queries.jsonl").read_text(encoding="utf-8").splitlines()
        ids = [json.loads(line)["id"] for line in lines]
        assert ids == [f"{kept}-title-cs", f"{topic}-cs", f"{topic}-en"]
    assert (tmp_path / "test" / "qrels.txt").read_text(
        encoding="utf-8"
    ) == "ki-0201-title-cs 0 h/2 2\n"


def test_topic_without_a_part_stops_the_step(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import topics

    write_parts(tmp_path, [], [], "")
    listed = tmp_path / "topics.json"
    entries = [
        {"id": "topic-26", "part": "Test", "cs": "šikana", "en": "bullying", "narrative": "n"}
    ]
    listed.write_text(json.dumps(entries), encoding="utf-8")
    monkeypatch.setattr(topics, "VERSION", "v2")
    monkeypatch.setattr(topics, "EVAL_DIR", tmp_path)
    monkeypatch.setattr(topics, "TOPICS_PATH", listed)
    with pytest.raises(SystemExit, match="topic-26"):
        topics.add()
