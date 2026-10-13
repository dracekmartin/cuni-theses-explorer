"""Paging and query handling of the DSpace run, against pages built here instead of DSpace."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import dspace_run
import pytest
from dspace_run import QueryFailedError, query_text, search

ATOM = "http://www.w3.org/2005/Atom"
OPENSEARCH = "http://a9.com/-/spec/opensearch/1.1/"


class FakeDSpace:
    """Serves `results` as DSpace does: `start` counts from 1, so pages overlap by one."""

    def __init__(self, results: list[str], fail_from: int | None = None) -> None:
        self.results, self.fail_from = results, fail_from
        self.starts: list[int] = []

    def page(self, text: str, start: int) -> bytes:
        self.starts.append(start)
        if self.fail_from is not None and start >= self.fail_from:
            raise QueryFailedError("HTTP 500 after 5 attempts")
        first = max(start, 1) - 1
        entries = "".join(
            f"<entry><id>http://hdl.handle.net/{handle}</id></entry>"
            for handle in self.results[first : first + 100]
        )
        return (
            f'<feed xmlns="{ATOM}" xmlns:opensearch="{OPENSEARCH}">'
            f"<opensearch:totalResults>{len(self.results)}</opensearch:totalResults>"
            f"{entries}</feed>"
        ).encode()


def handles(count: int) -> list[str]:
    return [f"h/{number}" for number in range(1, count + 1)]


def ask(dspace: Any, corpus: set[str]) -> dict[str, Any]:
    return search(dspace, "query", corpus)


@pytest.fixture(autouse=True)
def cache(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(dspace_run, "CACHE_DIR", tmp_path)


def test_query_text_drops_the_percent_sign_and_escapes_on_demand() -> None:
    assert query_text("návratnost  50 % : a?", escaped=False) == "návratnost 50 : a?"
    assert query_text("čas: pojetí?", escaped=True) == "čas\\: pojetí\\?"


def test_keeps_corpus_theses_in_dspace_order_once() -> None:
    answer = ask(FakeDSpace(handles(250)), {"h/5", "h/100", "h/150", "h/250"})
    assert answer["theses"] == ["h/5", "h/100", "h/150", "h/250"]


def test_reads_the_last_result_when_the_total_is_a_full_hundred() -> None:
    assert ask(FakeDSpace(handles(200)), {"h/200"})["theses"] == ["h/200"]


def test_stops_once_enough_corpus_theses_are_found(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(dspace_run, "RESULTS_PER_QUERY", 3)
    dspace = FakeDSpace(handles(1000))
    assert ask(dspace, set(handles(1000)))["theses"] == ["h/1", "h/2", "h/3"]
    assert dspace.starts == [0]


def test_a_failing_later_page_keeps_the_earlier_theses() -> None:
    answer = ask(FakeDSpace(handles(250), fail_from=100), {"h/5", "h/150"})
    assert answer["theses"] == ["h/5"]
    assert answer["partial"]


def test_a_failing_first_page_fails_the_query() -> None:
    with pytest.raises(QueryFailedError):
        ask(FakeDSpace(handles(10), fail_from=0), {"h/1"})


def test_a_second_search_reads_the_cache() -> None:
    ask(FakeDSpace(handles(150)), {"h/120"})
    assert ask(FakeDSpace([], fail_from=0), {"h/120"})["theses"] == ["h/120"]
