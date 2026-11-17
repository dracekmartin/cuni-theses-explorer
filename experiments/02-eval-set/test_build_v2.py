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


def test_a_run_of_a_larger_corpus_pools_like_a_run_of_v2(tmp_path: Path) -> None:
    from topics import top_results

    run = tmp_path / "setup.run"
    ranked = ["h/twin", "h/outside", "h/rep", "h/2", "h/3"]
    lines = [f"topic-01-cs Q0 {handle} {rank} 1.0 setup" for rank, handle in enumerate(ranked, 1)]
    run.write_text("\n".join([*lines, "ki-0001-title-cs Q0 h/2 1 1.0 setup"]), encoding="utf-8")
    as_corpus = {"h/rep": "h/rep", "h/twin": "h/rep", "h/2": "h/2", "h/3": "h/3"}
    top = top_results(run, {"topic-01-cs"}, 2, as_corpus)
    assert top == {"topic-01-cs": ["h/rep", "h/2"]}


def test_judge_keeps_the_qrels_of_a_part_when_a_pair_gets_no_grade(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import topics
    from common import Thesis

    qrels = "topic-01-cs 0 h/1 2\ntopic-01-en 0 h/1 2\n"
    write_parts(
        tmp_path, [topic("topic-01-cs", "zubní kaz"), topic("topic-01-en", "caries")], [], qrels
    )
    listed = tmp_path / "topics.json"
    entries = [
        {"id": "topic-01", "part": "dev", "cs": "zubní kaz", "en": "caries", "narrative": "n"}
    ]
    listed.write_text(json.dumps(entries), encoding="utf-8")
    corpus = tmp_path / "corpus.jsonl"
    theses = [
        Thesis(h, "u", "f", None, None, None, "cs", "t", "cs", None, None, None, None)
        for h in ("h/1", "h/2")
    ]
    corpus.write_text(
        "".join(json.dumps(thesis.__dict__) + "\n" for thesis in theses), encoding="utf-8"
    )
    run = tmp_path / "setup.run"
    run.write_text("topic-01-cs Q0 h/2 1 1.0 setup\n", encoding="utf-8")
    monkeypatch.setattr(topics, "EVAL_DIR", tmp_path)
    monkeypatch.setattr(topics, "TOPICS_PATH", listed)
    monkeypatch.setattr(topics, "CORPUS_META_PATH", corpus)
    monkeypatch.setattr(topics, "corpus_map", lambda: {"h/1": "h/1", "h/2": "h/2"})
    monkeypatch.setattr(topics, "load_api_key", lambda: "fake-key")
    monkeypatch.setattr(topics, "check_parts", lambda: None)
    # The pair judged earlier fails and the new pair gets a grade.
    monkeypatch.setattr(
        topics, "grade", lambda _client, _topic, thesis: 2 if thesis.handle == "h/2" else None
    )
    with pytest.raises(SystemExit, match="1 pairs got no grade"):
        topics.judge(10, "dev", [run])
    assert (tmp_path / "dev" / "qrels.txt").read_text(encoding="utf-8") == qrels


def test_agreement_reweighted_to_the_pool() -> None:
    from topics import pool_weights, weighted_kappa

    model = [2, 2, 0, 0]
    weights = pool_weights(model, {"0": 80, "1": 0, "2": 20})
    assert weights == [10.0, 10.0, 40.0, 40.0]
    human = [2, 1, 0, 1]
    repeated = weighted_kappa([2, 1, 0, 0, 1], [2, 2, 0, 0, 0])
    assert weighted_kappa(human, model, weights=[1, 1, 2, 1]) == pytest.approx(repeated)


def test_grade_shift_splits_the_disagreements_by_direction() -> None:
    from topics import grade_shift

    # The LLM grades higher once and lower three times, the last pair agrees.
    assert grade_shift([0, 2, 2, 1, 1], [1, 1, 0, 0, 1]) == (1, 3)


def test_sign_test_against_counts_done_by_hand() -> None:
    from topics import sign_test

    assert sign_test(3, 3) == 1.0
    assert sign_test(0, 0) == 1.0
    assert sign_test(5, 0) == pytest.approx(2 / 32)
    # 12 of 15 one way: (C(15,12) + C(15,13) + C(15,14) + C(15,15)) / 2**15, twice.
    assert sign_test(3, 12) == pytest.approx(2 * 576 / 32768)
