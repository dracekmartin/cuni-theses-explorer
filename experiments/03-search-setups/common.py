"""Shared paths, corpus loading, chunking and lemmatization for experiment 03.

Chunking and lemmatization are copied unchanged from experiment 01, so that the
01-baseline setup reproduces it exactly.
"""

from __future__ import annotations

import io
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from simplemma import lemmatize

REPO_ROOT = Path(__file__).resolve().parents[2]
EXPERIMENT = "03-search-setups"
EXPERIMENT_DIR = REPO_ROOT / "experiments" / EXPERIMENT
SETUPS_DIR = EXPERIMENT_DIR / "setups"
RESULTS_DIR = EXPERIMENT_DIR / "results"
WORK_DIR = REPO_ROOT / "data" / EXPERIMENT
RUNS_DIR = REPO_ROOT / "data" / "runs" / EXPERIMENT

CHUNK_CHARS = 1000
SENTENCE_END = re.compile(r"(?<=[.!?])\s+")
WORD_PATTERN = re.compile(r"\w+", re.UNICODE)


def eval_dir(version: str) -> Path:
    return REPO_ROOT / "eval" / version


def eval_data_dir(version: str) -> Path:
    return REPO_ROOT / "data" / f"eval-{version}"


@dataclass
class Chunk:
    """A passage of a thesis. Order -1 and -2 mark the Czech and English metadata chunks."""

    handle: str
    order: int
    text: str


def chunk_text(text: str) -> list[str]:
    """Chunks of at most CHUNK_CHARS, split on sentence ends where possible."""
    chunks: list[str] = []
    current = ""
    for sentence in SENTENCE_END.split(text):
        sentence = sentence.strip()
        if not sentence:
            continue
        if len(current) + len(sentence) + 1 > CHUNK_CHARS and current:
            chunks.append(current)
            current = ""
        while len(sentence) > CHUNK_CHARS:
            chunks.append(sentence[:CHUNK_CHARS])
            sentence = sentence[CHUNK_CHARS:]
        current = f"{current} {sentence}".strip()
    if current:
        chunks.append(current)
    return chunks


def lemma_tokens(text: str) -> list[str]:
    """Lowercased, lemmatized word tokens for BM25, Czech first and English as the fallback."""
    return [lemmatize(token, lang=("cs", "en")) for token in WORD_PATTERN.findall(text.lower())]


def load_corpus(version: str) -> list[dict[str, Any]]:
    """Metadata of the corpus theses, in the order of eval/<version>/corpus.txt."""
    handles = (eval_dir(version) / "corpus.txt").read_text(encoding="utf-8").split()
    meta_path = eval_data_dir(version) / "corpus.jsonl"
    with meta_path.open(encoding="utf-8") as file:
        by_handle = {record["handle"]: record for record in map(json.loads, file) if record}
    missing = [handle for handle in handles if handle not in by_handle]
    if missing:
        raise SystemExit(f"{len(missing)} corpus handles have no metadata, first {missing[0]}")
    return [by_handle[handle] for handle in handles]


def thesis_text(version: str, handle: str) -> str:
    path = eval_data_dir(version) / "texts" / f"{handle.replace('/', '_')}.txt"
    return path.read_text(encoding="utf-8", errors="replace")


def metadata_chunks(record: dict[str, Any]) -> list[Chunk]:
    """One Czech and one English chunk built from the catalog metadata.

    The DSpace record holds the title, keywords and abstract in both languages even when
    the thesis text does not, which is what the cross-lingual queries need.
    """
    parts: dict[str, list[str]] = {"cs": [], "en": []}
    for title, lang in (
        (record.get("title"), record.get("title_lang")),
        (record.get("title_translated"), record.get("title_translated_lang")),
    ):
        if title:
            parts["en" if lang == "en" else "cs"].append(title)
    for lang in ("cs", "en"):
        keywords = record.get(f"keywords_{lang}") or []
        if keywords:
            parts[lang].append(", ".join(keywords))
        abstract = record.get(f"abstract_{lang}")
        if abstract:
            parts[lang].append(" ".join(abstract.split()))
    return [
        Chunk(record["handle"], order, "\n".join(parts[lang]))
        for order, lang in ((-1, "cs"), (-2, "en"))
        if parts[lang]
    ]


def load_queries(version: str) -> list[dict[str, Any]]:
    with (eval_dir(version) / "queries.jsonl").open(encoding="utf-8") as file:
        return [json.loads(line) for line in file if line.strip()]


def utf8_stdout() -> None:
    """Force UTF-8 stdout, so Czech titles survive the default Windows console."""
    if isinstance(sys.stdout, io.TextIOWrapper):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
