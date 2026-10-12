"""Paths and small helpers shared by the harvest steps."""

from __future__ import annotations

import io
import shutil
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = REPO_ROOT / "data" / "04-full-harvest"
SETS_PATH = DATA_DIR / "sets.json"
OAI_DIR = DATA_DIR / "oai"
CATALOG_PATH = DATA_DIR / "catalog.jsonl.gz"
CATALOG_META_PATH = DATA_DIR / "catalog.json"
TEXTS_DIR = DATA_DIR / "texts"
FAILED_PATH = DATA_DIR / "texts-failed.jsonl"
LOG_PATH = DATA_DIR / "harvest.log"
LOCK_PATH = DATA_DIR / "harvest.lock"
MIN_FREE_BYTES = 5 * 1024**3


def stem(handle: str) -> str:
    """Filesystem-safe identifier derived from the handle, as in experiments 02 and 03."""
    return handle.replace("/", "_")


def text_path(handle: str) -> Path:
    """Where the body text of a thesis lands. Shards of a thousand keep directories small."""
    number = handle.rsplit("/", 1)[-1]
    shard = str(int(number) // 1000) if number.isdigit() else "other"
    return TEXTS_DIR / shard / f"{stem(handle)}.txt.gz"


def write_atomic(path: Path, data: bytes) -> None:
    """Write to a .part file first, so an interrupted run never leaves a file that looks
    complete."""
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_name(path.name + ".part")
    partial.write_bytes(data)
    partial.replace(path)


def check_disk() -> None:
    free = shutil.disk_usage(DATA_DIR).free
    if free < MIN_FREE_BYTES:
        raise SystemExit(f"only {free / 1024**3:.1f} GB free on the data disk, stopping")


def short_lang(value: str | None) -> str | None:
    """Two-letter language code, since DSpace mixes forms such as cs_CZ and en_US."""
    if not value:
        return None
    code = value.replace("-", "_").split("_")[0].strip().lower()
    return code or None


def utf8_stdout() -> None:
    """Force UTF-8 stdout, so Czech titles survive the default Windows console."""
    if isinstance(sys.stdout, io.TextIOWrapper):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
