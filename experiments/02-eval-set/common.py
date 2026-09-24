"""Shared paths and records for building the evaluation set."""

from __future__ import annotations

import io
import json
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
VERSION = "v0"
EVAL_DIR = REPO_ROOT / "eval" / VERSION
DATA_DIR = REPO_ROOT / "data" / f"eval-{VERSION}"
CATALOG_DIR = DATA_DIR / "catalog"
CORPUS_META_PATH = DATA_DIR / "corpus.jsonl"
TEXTS_DIR = DATA_DIR / "texts"
EXPERIMENT_01_DIR = REPO_ROOT / "data" / "01-mini-pipeline"


@dataclass
class Thesis:
    """Metadata of one thesis as harvested from DSpace, plus where its text comes from."""

    handle: str
    uuid: str
    faculty: str
    department: str | None
    thesis_type: str | None
    year: str | None
    language: str | None
    title: str
    title_lang: str | None
    title_translated: str | None
    title_translated_lang: str | None
    abstract_cs: str | None
    abstract_en: str | None
    keywords_cs: list[str] = field(default_factory=list)
    keywords_en: list[str] = field(default_factory=list)
    defence_status: str | None = None
    text_link: str | None = None
    source: str = "catalog"

    @property
    def stem(self) -> str:
        """Filesystem-safe identifier derived from the handle."""
        return self.handle.replace("/", "_")


def short_lang(value: str | None) -> str | None:
    """Two-letter language code; DSpace mixes forms such as cs_CZ and en_US."""
    if not value:
        return None
    code = value.replace("-", "_").split("_")[0].strip().lower()
    return code or None


def read_theses(path: Path) -> list[Thesis]:
    """Read a JSONL file of theses, skipping a torn trailing line left by an interrupted write."""
    if not path.exists():
        return []
    theses: list[Thesis] = []
    with path.open(encoding="utf-8") as file:
        for line_number, line in enumerate(file, start=1):
            if not line.strip():
                continue
            try:
                theses.append(Thesis(**json.loads(line)))
            except (json.JSONDecodeError, TypeError):
                print(f"{path.name}: skipping malformed line {line_number}")
    return theses


def write_theses(path: Path, theses: list[Thesis]) -> None:
    """Write theses to a JSONL file atomically, so a crash never leaves half a file."""
    partial = path.with_suffix(path.suffix + ".part")
    with partial.open("w", encoding="utf-8") as file:
        for thesis in theses:
            file.write(json.dumps(asdict(thesis), ensure_ascii=False) + "\n")
    partial.replace(path)


def utf8_stdout() -> None:
    """Force UTF-8 stdout, so Czech titles survive the default Windows console."""
    if isinstance(sys.stdout, io.TextIOWrapper):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
