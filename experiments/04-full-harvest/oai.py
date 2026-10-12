"""Access to the university repository that waits out its outages, and OAI-PMH paging.

Requests go one at a time, spaced by a rate limit. A transient failure (no connection,
a timeout, HTTP 5xx or 429, or a response the caller does not accept) is retried with a
growing pause and without a limit while the repository is down. When the repository
answers an Identify request but one URL keeps failing, that URL gives up with ItemFailed,
so one broken file or page cannot stall the whole harvest.

Each page of a set is stored as it came, gzipped, one file per page. The resumption token
for the next page is read back from the last stored page, so a restart continues where
the previous run stopped.
"""

from __future__ import annotations

import gzip
import json
import logging
import time
import xml.etree.ElementTree as ET
from collections import deque
from collections.abc import Callable
from pathlib import Path

import requests
from common import OAI_DIR, write_atomic

BASE_URL = "https://dspace.cuni.cz/oai/request"
METADATA_PREFIX = "xoai"
OAI_NS = "{http://www.openarchives.org/OAI/2.0/}"
USER_AGENT = (
    "cuni-theses-explorer/experiment-04 (+https://github.com/dracekmartin/cuni-theses-explorer)"
)
TIMEOUT_S = (30, 120)
FIRST_PAUSE_S = 5
MAX_PAUSE_S = 600
ATTEMPTS_PER_ITEM = 3

log = logging.getLogger("harvest")
Params = dict[str, str]


class ItemFailedError(Exception):
    """One URL keeps failing while the repository answers other requests."""


class Client:
    """One HTTP session, so the server keeps one Tomcat session for us instead of one per
    request."""

    def __init__(self, requests_per_second: float) -> None:
        self.session = requests.Session()
        self.session.headers["User-Agent"] = USER_AGENT
        self.spacing = 1 / requests_per_second
        self.last_start = 0.0
        self.latencies: deque[float] = deque(maxlen=200)

    def _wait_turn(self) -> None:
        pause = self.last_start + self.spacing - time.monotonic()
        if pause > 0:
            time.sleep(pause)
        self.last_start = time.monotonic()

    def get(
        self,
        url: str,
        params: Params | None = None,
        accept: Callable[[requests.Response], bool] | None = None,
    ) -> requests.Response:
        """GET that returns any response except a transient failure. 4xx is the caller's."""
        failures = 0
        pause = FIRST_PAUSE_S
        down_since: float | None = None
        while True:
            self._wait_turn()
            started = time.monotonic()
            retry_after: int | None = None
            try:
                response = self.session.get(url, params=params, timeout=TIMEOUT_S)
            except requests.RequestException as error:
                reason = type(error).__name__
            else:
                self.latencies.append(time.monotonic() - started)
                status = response.status_code
                if status == 429 or status >= 500:
                    reason = f"HTTP {status}"
                    retry_after = _retry_after(response)
                elif status == 200 and accept is not None and not accept(response):
                    reason = "unexpected content"
                else:
                    if down_since is not None:
                        log.info("answers again after %s", duration(time.time() - down_since))
                    return response
            failures += 1
            if failures >= ATTEMPTS_PER_ITEM and self.healthy():
                raise ItemFailedError(f"{reason} after {failures} attempts")
            if down_since is None:
                down_since = time.time()
            wait = min(retry_after or pause, MAX_PAUSE_S)
            log.warning(
                "%s for %s, failure %d since %s, next try in %d s",
                reason,
                url.removeprefix("https://dspace.cuni.cz"),
                failures,
                time.strftime("%H:%M", time.localtime(down_since)),
                wait,
            )
            time.sleep(wait)
            pause = min(pause * 2, MAX_PAUSE_S)

    def healthy(self) -> bool:
        """Whether the repository answers at all, to tell an outage from one bad URL."""
        self._wait_turn()
        try:
            response = self.session.get(BASE_URL, params={"verb": "Identify"}, timeout=TIMEOUT_S)
        except requests.RequestException:
            return False
        return response.status_code == 200 and b"<Identify>" in response.content

    def median_latency(self) -> float | None:
        if not self.latencies:
            return None
        return sorted(self.latencies)[len(self.latencies) // 2]


def _retry_after(response: requests.Response) -> int | None:
    value = response.headers.get("Retry-After", "")
    return int(value) if value.isdigit() else None


def duration(seconds: float) -> str:
    minutes = int(seconds // 60)
    if minutes < 60:
        return f"{minutes} min" if minutes else f"{int(seconds)} s"
    return f"{minutes // 60} h {minutes % 60} min"


def is_oai(response: requests.Response) -> bool:
    """A complete OAI-PMH document, which a maintenance page or a cut-off body is not."""
    try:
        root = ET.fromstring(response.content)
    except ET.ParseError:
        return False
    return root.tag == f"{OAI_NS}OAI-PMH" and len(root) >= 3


def error_code(root: ET.Element) -> str | None:
    error = root.find(f"{OAI_NS}error")
    return error.get("code") if error is not None else None


def resumption_token(root: ET.Element) -> str | None:
    """The token for the next page, or None on the last page."""
    token = root.find(f".//{OAI_NS}resumptionToken")
    if token is None or not (token.text or "").strip():
        return None
    return (token.text or "").strip()


def read_page(path: Path) -> ET.Element:
    return ET.fromstring(gzip.decompress(path.read_bytes()))


def set_pages(spec: str) -> list[Path]:
    """Stored pages of a set in order, named by zero-padded page numbers."""
    return sorted((OAI_DIR / spec).glob("*.xml.gz"))


def list_sets(client: Client) -> list[tuple[str, str]]:
    """All sets of the repository as (setSpec, setName)."""
    sets: list[tuple[str, str]] = []
    params: Params = {"verb": "ListSets"}
    while True:
        root = ET.fromstring(client.get(BASE_URL, params, accept=is_oai).content)
        for item in root.iter(f"{OAI_NS}set"):
            sets.append(
                (item.findtext(f"{OAI_NS}setSpec") or "", item.findtext(f"{OAI_NS}setName") or "")
            )
        token = resumption_token(root)
        if token is None:
            return sets
        params = {"verb": "ListSets", "resumptionToken": token}


def harvest_set(client: Client, spec: str) -> bool:
    """Download every page of one set. True when the set is complete."""
    directory = OAI_DIR / spec
    if (directory / "done").exists():
        return True
    directory.mkdir(parents=True, exist_ok=True)
    first: Params = {"verb": "ListRecords", "metadataPrefix": METADATA_PREFIX, "set": spec}
    pages = set_pages(spec)
    params = first
    if pages:
        token = resumption_token(read_page(pages[-1]))
        if token is None:
            finish_set(spec)
            return True
        params = {"verb": "ListRecords", "resumptionToken": token}
        log.info("%s: continuing after page %d", spec, len(pages))
    number = len(pages)
    while True:
        try:
            response = client.get(BASE_URL, params, accept=is_oai)
        except ItemFailedError as failure:
            log.error("%s: page %d failed (%s), the set stays incomplete", spec, number, failure)
            return False
        root = ET.fromstring(response.content)
        code = error_code(root)
        if code == "noRecordsMatch":
            finish_set(spec)
            return True
        if code == "badResumptionToken":
            log.warning("%s: the server refused the resumption token, starting the set again", spec)
            for page in set_pages(spec):
                page.unlink()
            params, number = first, 0
            continue
        if code:
            log.error("%s: OAI error %s, the set stays incomplete", spec, code)
            return False
        write_atomic(directory / f"{number:05d}.xml.gz", gzip.compress(response.content, 6))
        number += 1
        if number % 25 == 0:
            log.info("%s: %d pages", spec, number)
        token = resumption_token(root)
        if token is None:
            finish_set(spec)
            return True
        params = {"verb": "ListRecords", "resumptionToken": token}


def finish_set(spec: str) -> None:
    """Mark a set complete, with the record count the server announced and the time span."""
    pages = set_pages(spec)
    summary: dict[str, object] = {"pages": len(pages), "records": 0}
    if pages:
        first, last = read_page(pages[0]), read_page(pages[-1])
        token = first.find(f".//{OAI_NS}resumptionToken")
        announced = token.get("completeListSize") if token is not None else None
        summary["records"] = (
            int(announced) if announced else len(first.findall(f".//{OAI_NS}record"))
        )
        summary["first_response"] = first.findtext(f"{OAI_NS}responseDate")
        summary["last_response"] = last.findtext(f"{OAI_NS}responseDate")
    write_atomic(OAI_DIR / spec / "done", json.dumps(summary).encode("utf-8"))
    log.info("%s: complete, %d pages, %s records", spec, len(pages), summary["records"])
