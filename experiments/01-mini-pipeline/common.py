"""Shared paths and manifest helpers for the mini pipeline experiment."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = REPO_ROOT / "data" / "01-mini-pipeline"
PDF_DIR = DATA_DIR / "pdf"
DSPACE_TEXT_DIR = DATA_DIR / "dspace-text"
EXTRACTED_DIR = DATA_DIR / "extracted"
INDEX_DIR = DATA_DIR / "index"
MANIFEST_PATH = DATA_DIR / "manifest.jsonl"


@dataclass
class ThesisRecord:
    """One harvested thesis and the files stored for it."""

    handle: str
    uuid: str
    faculty: str
    title: str
    thesis_type: str | None
    year: str | None
    language: str | None
    authors: list[str]
    abstract: str | None
    pdf_file: str
    dspace_text_file: str | None

    @property
    def stem(self) -> str:
        """Filesystem-safe identifier derived from the handle."""
        return self.handle.replace("/", "_")


def ensure_dirs() -> None:
    for directory in (PDF_DIR, DSPACE_TEXT_DIR, EXTRACTED_DIR, INDEX_DIR):
        directory.mkdir(parents=True, exist_ok=True)


def load_manifest() -> list[ThesisRecord]:
    """Read the manifest, skipping a torn trailing line left by an interrupted write."""
    if not MANIFEST_PATH.exists():
        return []
    records: list[ThesisRecord] = []
    with MANIFEST_PATH.open(encoding="utf-8") as file:
        for line_number, line in enumerate(file, start=1):
            if not line.strip():
                continue
            try:
                records.append(ThesisRecord(**json.loads(line)))
            except (json.JSONDecodeError, TypeError):
                print(f"manifest: skipping malformed line {line_number}")
    return records


def append_record(record: ThesisRecord) -> None:
    with MANIFEST_PATH.open("a", encoding="utf-8") as file:
        file.write(json.dumps(asdict(record), ensure_ascii=False) + "\n")
