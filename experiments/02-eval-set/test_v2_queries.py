"""Test targets, exact terms and their queries in v2, on records written by hand."""

from __future__ import annotations

from collections import Counter
from typing import Any

import generate_queries
import generate_v2_queries
import pytest
from common import Thesis
from generate_v2_queries import (
    choose_exact,
    choose_test_targets,
    cited,
    exact_queries,
    number_belongs,
    owned,
    private_names,
    squeezed,
    term_counts,
    term_language,
    valid_exact,
)


def thesis(handle: str, language: str = "cs", title: str = "Mutace genů") -> Thesis:
    return Thesis(
        handle=handle,
        uuid="",
        faculty=f"faculty {handle[-1]}",
        department=None,
        thesis_type=None,
        year=None,
        language=language,
        title=title,
        title_lang=language,
        title_translated="Gene mutations",
        title_translated_lang="en",
        abstract_cs="Abstrakt.",
        abstract_en="Abstract.",
    )


def candidate(term: str, none: bool = True) -> dict[str, Any]:
    wording: Any = (
        term if none else {"cs": f"{term} gen", "en": f"{term} gene", "sk": f"{term} gén"}
    )
    return {"term": term, "kind": "code", "none": none, "query": wording}


def test_term_counts_across_case_and_line_breaks() -> None:
    texts = [("h/1", "Mutace genu TP53 a\nBRCA1 u pacientů."), ("h/2", "gen TP 53")]
    counts = term_counts({"tp53", "tp53 a brca1", "egfr"}, texts)
    assert counts == {"tp53": {"h/1"}, "tp53 a brca1": {"h/1"}, "egfr": set()}


def test_chosen_term_is_only_in_this_thesis_and_no_name() -> None:
    target = thesis("h/1", title="Mutace genu BRCA1")
    candidates = [
        candidate("BRCA1"),
        candidate("TP53"),
        candidate("Novák"),
        candidate("EGFR"),
        candidate("KRAS"),
    ]
    counts = {
        "brca1": {"h/1"},
        "tp53": {"h/1", "h/2"},
        "novák": {"h/1"},
        "egfr": {"h/1"},
        "kras": {"h/1"},
    }
    chosen, log = choose_exact(target, candidates, counts, private_names(author("Novák, Jan")))
    assert chosen is not None and chosen["term"] == "EGFR"
    reasons = {item["term"]: item["reason"] for item in log}
    assert reasons == {
        "BRCA1": "in the title",
        "TP53": "in 1 other theses",
        "Novák": "a name of the author or a teacher",
        "EGFR": "chosen",
        "KRAS": "another term chosen",
    }


def test_dashes_compared_as_a_student_types_them() -> None:
    texts = [("h/1", "gen blaNDM‑5"), ("h/2", "gen blaNDM-5")]
    assert term_counts({squeezed("blaNDM‑5")}, texts) == {"blandm-5": {"h/1", "h/2"}}


def test_references_and_footnote_numbers_are_no_terms() -> None:
    def kind(term: str, value: str) -> dict[str, Any]:
        return {**candidate(term), "kind": value}

    assert cited(kind("Jan Cernik", "person"), "According to Jan Cernik (2005), the client")
    assert cited(kind("ROSE 1981", "work"), "as shown before (ROSE 1981).")
    assert not cited(
        kind("Garcetti v. Ceballos", "law"), "In Garcetti v. Ceballos (2006) the court"
    )
    assert not number_belongs("MIQE guidelines 80", "The MIQE guidelines \n80 were adhered to")
    assert number_belongs("canon 1055", "Under canon 1055 the marriage")


def test_language_of_a_term_alone() -> None:
    assert term_language("Jan Cernik", "person", "en") is None
    assert term_language("Union mondiale pour la nature", "organization", "cs") is None
    assert term_language("tetrachorického koeficientu korelace", "work", "cs") == "cs"
    assert term_language("γ-valerolaktónu", "code", "sk") == "sk"
    assert term_language("kánon 1222", "law", "cs") == "cs"
    assert term_language("lineárnym písmom B", "code", "en") is None
    assert term_language("École Colarossi", "organization", "cs") is None


def test_wording_that_lost_the_term_is_left_out() -> None:
    lost = {
        **candidate("TP53", none=False),
        "query": {"cs": "TP53 mutace", "en": "gene mutation", "sk": "TP53 mutace"},
    }
    assert [(item["id"], item["text"]) for item in exact_queries(3, thesis("h/1"), lost)] == [
        ("ki-0003-exact-cs", "TP53 mutace")
    ]
    mixed = {**candidate("TP53", none=False), "query": {"cs": "TP53", "en": "TP53 gene", "sk": ""}}
    assert [(item["id"], item["lang"]) for item in exact_queries(4, thesis("h/1"), mixed)] == [
        ("ki-0004-exact-none", None),
        ("ki-0004-exact-en", "en"),
    ]


def author(name: str) -> dict[str, Any]:
    return {"fields": {"dc.creator": [[name, None]]}}


def test_exact_queries_with_and_without_a_language() -> None:
    target = thesis("h/1")
    bare = exact_queries(201, target, candidate("TP53"))
    assert [(item["id"], item["group"], item["lang"]) for item in bare] == [
        ("ki-0201-exact-none", "ki-0201-exact", None)
    ]
    worded = exact_queries(201, target, candidate("TP53", none=False))
    assert [item["id"] for item in worded] == ["ki-0201-exact-cs", "ki-0201-exact-en"]

    def same(term: str) -> dict[str, Any]:
        return {**candidate(term, none=False), "query": dict.fromkeys(("cs", "en", "sk"), term)}

    assert [
        (item["id"], item["lang"]) for item in exact_queries(2, target, same("Zabitý bleskem"))
    ] == [("ki-0002-exact-cs", "cs")]
    assert [item["lang"] for item in exact_queries(2, target, same("Kristen Hastrup"))] == [None]


def test_pdf_artefacts_and_reviewed_names_are_no_terms() -> None:
    terms = ["diacetyl- morfin", "warehouse-10-20-10-2-1.map", "Rudolf Mauretter"]
    counts = {generate_v2_queries.squeezed(term): {"h/1"} for term in terms}
    _, log = choose_exact(thesis("h/1"), [candidate(term) for term in terms], counts, set())
    assert [item["reason"] for item in log] == [
        "a word split at the end of a line",
        "a file name",
        "a patient of a sanatorium, a private person",
    ]


def test_term_in_many_theses_of_the_university() -> None:
    counts = {"tp53": {"h/1"}, "egfr": {"h/1"}}
    university = Counter({"tp53": 4, "egfr": 3})
    chosen, log = choose_exact(
        thesis("h/1"), [candidate("TP53"), candidate("EGFR")], counts, set(), university
    )
    assert chosen is not None and chosen["term"] == "EGFR"
    assert log[0]["reason"] == "in 4 theses of the university"


def test_a_new_run_replaces_only_its_own_queries() -> None:
    v1 = {"type": "about-short", "lang": "cs", "target": "h/1"}
    exact = {"type": "exact", "lang": None, "target": "h/1"}
    slovak_title = {"type": "title", "lang": "sk", "target": "h/1"}
    topic = {"type": "topic", "lang": "cs", "target": None}
    assert [owned("dev", item) for item in (v1, exact, slovak_title, topic)] == [
        False,
        True,
        False,
        False,
    ]
    assert [owned("test", item) for item in (v1, slovak_title, topic)] == [True, True, False]


def test_citation_is_no_term() -> None:
    chosen, log = choose_exact(
        thesis("h/1"),
        [candidate("Stein and Quirk (1991)")],
        {"stein and quirk (1991)": {"h/1"}},
        set(),
    )
    assert chosen is None and log[0]["reason"] == "a citation"


def test_answer_of_the_llm_is_checked() -> None:
    assert valid_exact({"skip": True})
    assert valid_exact({"terms": [candidate("TP53"), candidate("EGFR", none=False)]})
    assert not valid_exact({"terms": [{**candidate("TP53"), "kind": "gene"}]})
    assert not valid_exact({"terms": [{**candidate("EGFR", none=False), "query": {"cs": "x"}}]})
    assert not valid_exact({"terms": []})


def test_test_targets_leave_out_dev_targets_and_keep_quotas(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(generate_queries, "text_of", lambda _: "x" * 30_000)
    monkeypatch.setattr(generate_v2_queries, "TEST_TARGETS", 4)
    monkeypatch.setattr(generate_v2_queries, "TEST_QUOTAS", {"cs": 2, "sk": 2})
    corpus = [thesis(f"h/{n}", "sk" if n < 4 else "cs") for n in range(10)]
    chosen = choose_test_targets(corpus, {"h/0", "h/1"})
    assert [number for number, _ in chosen] == [201, 202, 203, 204]
    assert {item.handle for _, item in chosen}.isdisjoint({"h/0", "h/1"})
    assert sorted(item.language or "" for _, item in chosen) == ["cs", "cs", "sk", "sk"]
