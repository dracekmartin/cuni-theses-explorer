"""Download a sample of theses from the CUNI DSpace repository.

For each selected faculty the script walks its "Kvalifikacni prace" collection, takes
theses that have a PDF, and stores three things under data/01-mini-pipeline/: the PDF,
the text DSpace itself extracted from it (the TEXT bundle), and one manifest line with
metadata. It is polite to the repository (one request at a time, fixed delay) and
resumable (theses already in the manifest are skipped).

Usage:
    python harvest.py [--per-faculty 50]
"""

from __future__ import annotations

import argparse
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import requests
from common import (
    DSPACE_TEXT_DIR,
    PDF_DIR,
    ThesisRecord,
    append_record,
    ensure_dirs,
    load_manifest,
)

DSPACE_BASE = "https://dspace.cuni.cz"
API_BASE = f"{DSPACE_BASE}/rest"
THESES_COLLECTION = "Kvalifikační práce"
DEFAULT_FACULTIES = ("Matematicko-fyzikální fakulta", "Filozofická fakulta")
REQUEST_DELAY_S = 0.8
PAGE_SIZE = 50
MAX_ATTEMPTS = 5
RETRYABLE_STATUS = (429, 500, 502, 503, 504)


def get_with_retries(
    session: requests.Session,
    url: str,
    *,
    stream: bool = False,
    params: dict[str, int | str] | None = None,
) -> requests.Response:
    """One GET with the politeness delay, retrying transient failures with backoff.

    Retries connection errors, timeouts and the status codes in RETRYABLE_STATUS.
    A 429 with a Retry-After header waits as instructed.
    """
    last_error: Exception | None = None
    for attempt in range(MAX_ATTEMPTS):
        time.sleep(REQUEST_DELAY_S)
        try:
            response = session.get(url, params=params, timeout=300 if stream else 60, stream=stream)
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


def find_faculty_community(session: requests.Session, faculty: str) -> str:
    communities = api_get(session, "/communities", limit=200)
    for community in communities:
        if community["name"] == faculty:
            return community["uuid"]
    raise SystemExit(f"faculty community not found: {faculty}")


def find_theses_collection(session: requests.Session, community_uuid: str) -> str:
    collections = api_get(session, f"/communities/{community_uuid}/collections", limit=50)
    for collection in collections:
        if collection["name"] == THESES_COLLECTION:
            return collection["uuid"]
    raise SystemExit(f"collection '{THESES_COLLECTION}' not found in community {community_uuid}")


def iter_collection_items(session: requests.Session, collection_uuid: str) -> Iterator[Any]:
    offset = 0
    while True:
        page = api_get(
            session,
            f"/collections/{collection_uuid}/items",
            limit=PAGE_SIZE,
            offset=offset,
            expand="metadata,bitstreams",
        )
        if not page:
            return
        yield from page
        offset += PAGE_SIZE


def metadata_values(item: Any, key: str) -> list[str]:
    return [entry["value"] for entry in item.get("metadata") or [] if entry["key"] == key]


def metadata_value(item: Any, key: str) -> str | None:
    values = metadata_values(item, key)
    return values[0] if values else None


def pick_bitstream(item: Any, bundle: str, mime_type: str | None = None) -> Any | None:
    """The largest bitstream of the given bundle, optionally restricted by MIME type."""
    candidates = [
        bitstream
        for bitstream in item.get("bitstreams") or []
        if bitstream.get("bundleName") == bundle
        and (mime_type is None or bitstream.get("mimeType") == mime_type)
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda bitstream: bitstream.get("sizeBytes") or 0)


def download_bitstream(session: requests.Session, bitstream: Any, destination: Path) -> None:
    """Download to a .part file first, so an interrupted run never leaves a file that
    looks complete."""
    url = f"{DSPACE_BASE}{bitstream['retrieveLink']}"
    partial = destination.with_suffix(destination.suffix + ".part")
    with get_with_retries(session, url, stream=True) as response, partial.open("wb") as file:
        for chunk in response.iter_content(chunk_size=1 << 16):
            file.write(chunk)
    partial.replace(destination)


def harvest_faculty(
    session: requests.Session, faculty: str, limit: int, already_harvested: set[str]
) -> int:
    """Harvest up to `limit` theses of one faculty. Returns how many were stored."""
    community_uuid = find_faculty_community(session, faculty)
    collection_uuid = find_theses_collection(session, community_uuid)
    stored = 0
    for item in iter_collection_items(session, collection_uuid):
        if stored >= limit:
            break
        handle = item.get("handle")
        if not handle or handle in already_harvested:
            continue
        pdf = pick_bitstream(item, "ORIGINAL", "application/pdf")
        if pdf is None:
            continue

        record = ThesisRecord(
            handle=handle,
            uuid=item["uuid"],
            faculty=faculty,
            title=item.get("name") or "",
            thesis_type=metadata_value(item, "dc.type"),
            year=metadata_value(item, "dc.date.issued"),
            language=metadata_value(item, "dc.language.iso"),
            authors=metadata_values(item, "dc.contributor.author"),
            abstract=metadata_value(item, "dc.description.abstract"),
            pdf_file=f"{handle.replace('/', '_')}.pdf",
            dspace_text_file=None,
        )

        download_bitstream(session, pdf, PDF_DIR / record.pdf_file)

        dspace_text = pick_bitstream(item, "TEXT")
        if dspace_text is not None:
            text_name = f"{record.stem}.txt"
            download_bitstream(session, dspace_text, DSPACE_TEXT_DIR / text_name)
            record.dspace_text_file = text_name

        append_record(record)
        already_harvested.add(handle)
        stored += 1
        print(f"[{faculty}] {stored}/{limit} {handle} {record.title[:60]}")
    return stored


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--per-faculty", type=int, default=50)
    parser.add_argument("--faculty", action="append", help="faculty name, repeatable")
    args = parser.parse_args()
    faculties: tuple[str, ...] = tuple(args.faculty) if args.faculty else DEFAULT_FACULTIES

    ensure_dirs()
    already_harvested = {record.handle for record in load_manifest()}
    session = requests.Session()
    session.headers["User-Agent"] = "cuni-theses-explorer/experiment-01 (student project)"

    for faculty in faculties:
        stored = harvest_faculty(session, faculty, args.per_faculty, already_harvested)
        print(f"{faculty}: stored {stored} theses")


if __name__ == "__main__":
    main()
