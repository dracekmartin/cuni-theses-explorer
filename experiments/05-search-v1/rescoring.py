"""Rescore the first-stage candidates of every query with a second embedding model.

Embedding the whole corpus with Qwen3-Embedding-0.6B would take about 13 hours on the
laptop, so only chunks that are among the top candidates of some query get embedded.
Their vectors go to a cache on disk with one row per chunk of the corpus, so a stopped run
continues where it ended. The result shows how the model ranks what the first stage
found. An index for production would embed the whole corpus instead.
"""

from __future__ import annotations

import json
import time
from typing import Any

import numpy as np
from common import WORK_DIR
from embeddings import load_model, model_slug

BLOCK = 4096
Chunks = list[tuple[int, float]]


def cached_vectors(model: str, rows: int, dim: int) -> tuple[Any, Any, Any]:
    """Vectors (float16, one row per chunk), the mask of rows done, and the mask's path."""
    directory = WORK_DIR / "rescoring" / model_slug(model, "")
    directory.mkdir(parents=True, exist_ok=True)
    shape_path, vectors_path, done_path = (
        directory / "shape.json",
        directory / "vectors.npy",
        directory / "done.npy",
    )
    if shape_path.exists() and json.loads(shape_path.read_text()) != [rows, dim]:
        raise SystemExit(f"{directory} holds vectors of another chunk list, delete it")
    if not vectors_path.exists():
        np.lib.format.open_memmap(vectors_path, mode="w+", dtype=np.float16, shape=(rows, dim))
        np.save(done_path, np.zeros(rows, dtype=bool))
        shape_path.write_text(json.dumps([rows, dim]))
    vectors = np.lib.format.open_memmap(vectors_path, mode="r+")
    return vectors, np.load(done_path), done_path


def rescore_all(
    rankings: list[Chunks], queries: list[dict[str, Any]], texts: list[str], config: dict[str, Any]
) -> tuple[list[Chunks], float]:
    """Rankings whose top `candidates` chunks are reordered by the second model, the rest
    keeping their order, and the encoding time per query in milliseconds."""
    candidates = config["candidates"]
    wanted = sorted({index for ranking in rankings for index, _ in ranking[:candidates]})
    encoder = load_model(
        config["model"], config.get("dtype", "float32"), config.get("max_seq_length", 512)
    )
    dim = encoder.get_sentence_embedding_dimension()
    vectors, done, done_path = cached_vectors(config["model"], len(texts), dim)
    todo = [index for index in wanted if not done[index]]
    print(f"rescoring: {len(wanted)} candidate chunks, {len(todo)} still to embed")
    started = time.monotonic()
    for start in range(0, len(todo), BLOCK):
        block = todo[start : start + BLOCK]
        encoded = encoder.encode(
            [texts[index] for index in block],
            batch_size=32,
            normalize_embeddings=True,
            convert_to_numpy=True,
        )
        vectors[block] = np.asarray(encoded, dtype=np.float16)
        vectors.flush()
        done[block] = True
        # Through a .part file: a cut-off mask would lose an hour of embedding.
        partial = done_path.with_name(done_path.name + ".part")
        with partial.open("wb") as file:
            np.save(file, done)
        partial.replace(done_path)
        finished = start + len(block)
        rate = finished / (time.monotonic() - started)
        print(
            f"rescoring: embedded {finished}/{len(todo)}, {rate:.0f} per s, "
            f"{(len(todo) - finished) / rate / 60:.0f} min left"
        )
    started = time.monotonic()
    prefix = config.get("query_prefix", "")
    query_vectors = np.asarray(
        encoder.encode(
            [f"{prefix}{query['text']}" for query in queries],
            batch_size=64,
            normalize_embeddings=True,
            convert_to_numpy=True,
        ),
        dtype=np.float32,
    )
    encode_ms = (time.monotonic() - started) * 1000 / max(1, len(queries))
    rescored: list[Chunks] = []
    for ranking, query_vector in zip(rankings, query_vectors, strict=True):
        head = [index for index, _ in ranking[:candidates]]
        scores = np.asarray(vectors[head], dtype=np.float32) @ query_vector if head else []
        order = sorted(zip(head, map(float, scores), strict=True), key=lambda p: p[1], reverse=True)
        rescored.append(order + ranking[candidates:])
    return rescored, encode_ms
