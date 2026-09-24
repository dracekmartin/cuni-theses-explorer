"""Chunk embeddings cached per model and thesis.

One file per thesis, so an interrupted indexing run continues where it stopped and a
growing corpus only embeds the new theses.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import numpy as np
from common import WORK_DIR, Chunk


def model_slug(model: str, passage_prefix: str) -> str:
    base = model.replace("/", "__")
    return f"{base}__{passage_prefix.strip(': ').replace(' ', '-')}" if passage_prefix else base


def cache_dir(model: str, passage_prefix: str) -> Path:
    return WORK_DIR / "embeddings" / model_slug(model, passage_prefix)


def load_model(model: str, dtype: str, max_seq_length: int) -> Any:
    # Imported lazily: loading torch takes a while and is not needed for lexical setups.
    import torch
    from sentence_transformers import SentenceTransformer

    kwargs = {"torch_dtype": torch.float16} if dtype == "float16" else {}
    encoder = SentenceTransformer(model, device="cuda", model_kwargs=kwargs)
    encoder.max_seq_length = max_seq_length
    return encoder


def embed_theses(
    groups: dict[str, list[Chunk]],
    embedding: dict[str, Any],
    suffix: str,
) -> float:
    """Embed the chunks of every thesis that has no cached file yet. Returns seconds spent."""
    directory = cache_dir(embedding["model"], embedding.get("passage_prefix", ""))
    directory.mkdir(parents=True, exist_ok=True)
    todo = [handle for handle in groups if not _path(directory, handle, suffix).exists()]
    if not todo:
        return 0.0
    encoder = load_model(
        embedding["model"], embedding.get("dtype", "float32"), embedding.get("max_seq_length", 512)
    )
    prefix = embedding.get("passage_prefix", "")
    # Half-precision models are stored as float16, the rest as float32, so the
    # 01-baseline scores match experiment 01 bit for bit.
    stored = np.float16 if embedding.get("dtype") == "float16" else np.float32
    started = time.monotonic()
    for position, handle in enumerate(todo, start=1):
        texts = [f"{prefix}{chunk.text}" for chunk in groups[handle]]
        # A scanned thesis without OCR has an empty text and therefore no chunks.
        vectors = (
            encoder.encode(texts, batch_size=32, normalize_embeddings=True, convert_to_numpy=True)
            if texts
            else np.zeros((0,))
        )
        np.save(_path(directory, handle, suffix), np.asarray(vectors, dtype=stored))
        if position % 25 == 0 or position == len(todo):
            elapsed = time.monotonic() - started
            print(f"embedded {position}/{len(todo)} theses ({suffix or 'body'}), {elapsed:.0f} s")
    seconds = time.monotonic() - started
    _record_seconds(directory, suffix, seconds, sum(len(groups[handle]) for handle in todo))
    return seconds


def load_matrix(groups: dict[str, list[Chunk]], embedding: dict[str, Any], suffix: str) -> Any:
    """Stack the cached vectors of all theses in the order of `groups`.

    Theses without chunks contribute no rows, just as they contribute no chunks, so rows
    stay aligned with the chunk list.
    """
    directory = cache_dir(embedding["model"], embedding.get("passage_prefix", ""))
    parts = [np.load(_path(directory, handle, suffix)) for handle in groups]
    parts = [part for part in parts if part.size]
    return np.concatenate(parts).astype(np.float32) if parts else np.zeros((0, 1), np.float32)


def recorded_seconds(embedding: dict[str, Any]) -> float:
    """Total embedding time recorded for this model, across runs and chunk kinds."""
    path = cache_dir(embedding["model"], embedding.get("passage_prefix", "")) / "timing.json"
    if not path.exists():
        return 0.0
    return float(sum(entry["seconds"] for entry in json.loads(path.read_text(encoding="utf-8"))))


def _path(directory: Path, handle: str, suffix: str) -> Path:
    stem = handle.replace("/", "_")
    return directory / (f"{stem}.{suffix}.npy" if suffix else f"{stem}.npy")


def _record_seconds(directory: Path, suffix: str, seconds: float, chunks: int) -> None:
    path = directory / "timing.json"
    entries = json.loads(path.read_text(encoding="utf-8")) if path.exists() else []
    entries.append({"kind": suffix or "body", "seconds": round(seconds, 1), "chunks": chunks})
    path.write_text(json.dumps(entries, indent=2), encoding="utf-8")
