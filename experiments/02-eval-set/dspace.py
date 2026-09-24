"""Polite access to the DSpace REST API of the university repository.

Follows the harvester of experiment 01: one request at a time with a fixed delay, and
retries with backoff for transient failures, because the repository has bad days.
"""

from __future__ import annotations

import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import requests
from common import Thesis, short_lang

DSPACE_BASE = "https://dspace.cuni.cz"
API_BASE = f"{DSPACE_BASE}/rest"
THESES_COLLECTION = "Kvalifikační práce"
REQUEST_DELAY_S = 0.8
PAGE_SIZE = 50
MAX_ATTEMPTS = 5
RETRYABLE_STATUS = (429, 500, 502, 503, 504)
USER_AGENT = "cuni-theses-explorer/experiment-02 (student project)"


def new_session() -> requests.Session:
    session = requests.Session()
    session.headers["User-Agent"] = USER_AGENT
    return session


def get_with_retries(
    session: requests.Session,
    url: str,
    *,
    stream: bool = False,
    params: dict[str, int | str] | None = None,
) -> requests.Response:
    """One GET with the politeness delay, retrying transient failures with backoff."""
    last_error: Exception | None = None
    for attempt in range(MAX_ATTEMPTS):
        time.sleep(REQUEST_DELAY_S)
        try:
            response = session.get(
                url, params=params, timeout=300 if stream else 120, stream=stream
            )
        except requests.RequestException as error:
            last_error = error
        else:
            if response.status_code not in RETRYABLE_STATUS:
                response.raise_for_status()
                return response
            last_error = requests.HTTPError(f"HTTP {response.status_code} for {url}")
            retry_after = response.headers.get("Retry-After")
            if retry_after and retry_after.isdigit():
                time.sleep(int(retry_after))
                continue
        time.sleep(2**attempt)
    raise SystemExit(f"giving up on {url} after {MAX_ATTEMPTS} attempts: {last_error}")


def api_get(session: requests.Session, path: str, **params: int | str) -> Any:
    return get_with_retries(session, f"{API_BASE}{path}", params=params).json()


def find_theses_collection(session: requests.Session, faculty: str) -> str | None:
    """UUID of the thesis collection of a faculty community, or None when it has none."""
    for community in api_get(session, "/communities", limit=200):
        if community["name"] != faculty:
            continue
        collections = api_get(session, f"/communities/{community['uuid']}/collections", limit=50)
        for collection in collections:
            if collection["name"] == THESES_COLLECTION:
                return collection["uuid"]
        return None
    return None


def iter_collection_items(
    session: requests.Session, collection_uuid: str, limit: int
) -> Iterator[Any]:
    """The first `limit` items of a collection, with metadata and bitstreams."""
    offset = 0
    while offset < limit:
        page = api_get(
            session,
            f"/collections/{collection_uuid}/items",
            limit=min(PAGE_SIZE, limit - offset),
            offset=offset,
            expand="metadata,bitstreams",
        )
        if not page:
            return
        yield from page
        offset += len(page)


def fetch_item(session: requests.Session, handle: str) -> Any:
    return api_get(session, f"/handle/{handle}", expand="metadata,bitstreams")


def body_text_link(item: Any) -> str | None:
    """Retrieve link of the TEXT bitstream paired with the thesis body.

    An item carries several PDFs (body, abstracts, reviews, attachments). As found in
    experiment 01, the body is the PDF whose paired TEXT bitstream ("<pdf>.txt") is largest.
    """
    bitstreams = item.get("bitstreams") or []
    pdfs = [
        bitstream
        for bitstream in bitstreams
        if bitstream.get("bundleName") == "ORIGINAL"
        and bitstream.get("mimeType") == "application/pdf"
    ]
    texts = {
        bitstream.get("name"): bitstream
        for bitstream in bitstreams
        if bitstream.get("bundleName") == "TEXT"
    }
    best_link: str | None = None
    best_size = 0
    for pdf in pdfs:
        text = texts.get(f"{pdf.get('name')}.txt")
        size = int(text.get("sizeBytes") or 0) if text is not None else 0
        if text is not None and size > best_size:
            best_link, best_size = text.get("retrieveLink"), size
    return best_link


def _values(item: Any, key: str) -> list[tuple[str, str | None]]:
    return [
        (entry["value"], entry.get("language"))
        for entry in item.get("metadata") or []
        if entry["key"] == key and entry.get("value")
    ]


def _first(item: Any, key: str) -> str | None:
    values = _values(item, key)
    return values[0][0] if values else None


def _in_language(item: Any, key: str, lang: str) -> str | None:
    for value, language in _values(item, key):
        if short_lang(language) == lang:
            return value
    return None


def _keywords(item: Any, lang: str) -> list[str]:
    """Keywords of one language; DSpace stores them as one value separated by '|'."""
    keywords: list[str] = []
    for value, language in _values(item, "dc.subject"):
        if short_lang(language) == lang:
            keywords.extend(part.strip() for part in value.split("|") if part.strip())
    return keywords


def parse_item(item: Any, faculty: str | None = None) -> Thesis:
    titles = _values(item, "dc.title")
    title, title_lang = titles[0] if titles else (item.get("name") or "", None)
    translated = _values(item, "dc.title.translated")
    return Thesis(
        handle=item["handle"],
        uuid=item["uuid"],
        faculty=faculty
        or _in_language(item, "dc.description.faculty", "cs")
        or _first(item, "uk.faculty-name.cs")
        or "",
        department=_in_language(item, "dc.description.department", "cs")
        or _first(item, "dc.description.department"),
        thesis_type=_first(item, "dc.type"),
        year=_first(item, "dc.date.issued"),
        language=short_lang(_first(item, "dc.language.iso")),
        title=title,
        title_lang=short_lang(title_lang),
        title_translated=translated[0][0] if translated else None,
        title_translated_lang=short_lang(translated[0][1]) if translated else None,
        abstract_cs=_first(item, "uk.abstract.cs")
        or _in_language(item, "dc.description.abstract", "cs"),
        abstract_en=_first(item, "uk.abstract.en")
        or _in_language(item, "dc.description.abstract", "en"),
        keywords_cs=_keywords(item, "cs"),
        keywords_en=_keywords(item, "en"),
        defence_status=_first(item, "uk.thesis.defenceStatus"),
        text_link=body_text_link(item),
    )


def download(session: requests.Session, link: str, destination: Path) -> None:
    """Download to a .part file first, so an interrupted run never leaves a file that
    looks complete."""
    partial = destination.with_suffix(destination.suffix + ".part")
    with (
        get_with_retries(session, f"{DSPACE_BASE}{link}", stream=True) as response,
        partial.open("wb") as file,
    ):
        for chunk in response.iter_content(chunk_size=1 << 16):
            file.write(chunk)
    partial.replace(destination)
