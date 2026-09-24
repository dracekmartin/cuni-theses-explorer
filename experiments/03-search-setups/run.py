"""Run one search setup over every query of an evaluation version.

Reads a setup description (setups/<name>.toml), embeds whatever is missing from the
cache, answers all queries in eval/<version>/queries.jsonl, and writes the run
(data/runs/03-search-setups/<name>.run) and the results file (results/<name>.json) with
the pipeline and cost. Metrics are added afterwards by eval/score.py.

Usage:
    python experiments/03-search-setups/run.py setups/01-baseline.toml [--version v0]
"""

from __future__ import annotations

import argparse
import json
import statistics
import time
import tomllib
from pathlib import Path
from typing import Any

import numpy as np
from common import (
    EXPERIMENT,
    EXPERIMENT_DIR,
    RESULTS_DIR,
    RUNS_DIR,
    WORK_DIR,
    Chunk,
    chunk_text,
    lemma_tokens,
    load_corpus,
    load_queries,
    metadata_chunks,
    thesis_text,
    utf8_stdout,
)
from embeddings import embed_theses, load_matrix, load_model, recorded_seconds
from rank_bm25 import BM25Okapi
from ranking import fuse_rrf, lexical_ranking, rerank, semantic_ranking, to_theses

RESULTS_PER_QUERY = 100


def build_chunks(
    version: str, corpus: list[dict[str, Any]], with_metadata: bool
) -> tuple[dict[str, list[Chunk]], dict[str, list[Chunk]]]:
    """Body chunks and, when asked for, metadata chunks, grouped by thesis."""
    body = {
        record["handle"]: [
            Chunk(record["handle"], order, text)
            for order, text in enumerate(chunk_text(thesis_text(version, record["handle"])))
        ]
        for record in corpus
    }
    meta = {record["handle"]: metadata_chunks(record) for record in corpus} if with_metadata else {}
    return body, meta


def cached_tokens(version: str, handle: str, chunks: list[Chunk]) -> list[list[str]]:
    """Lemmatized tokens of the body chunks of one thesis, cached because lemmatizing is slow."""
    path = WORK_DIR / "tokens" / version / f"{handle.replace('/', '_')}.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    tokens = [lemma_tokens(chunk.text) for chunk in chunks]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(tokens, ensure_ascii=False), encoding="utf-8")
    return tokens


def describe(setup: dict[str, Any], version: str) -> dict[str, Any]:
    """The pipeline block of the results file, one key per stage of the experiment card."""
    sources = setup["strategy"]["sources"]
    return {
        "harvest": {"source": "DSpace REST", "corpus": f"eval/{version}"},
        "text_extraction": {"method": "DSpace TEXT bundle"},
        "chunking": setup["chunking"],
        "embedding": setup.get("embedding") if "semantic" in sources else None,
        "lexical": setup.get("lexical") if "lexical" in sources else None,
        "strategy": setup["strategy"],
        "reranking": setup.get("reranking"),
        "aggregation": {"method": "best chunk"},
    }


def run(setup_path: Path, version: str) -> None:
    setup = tomllib.loads(setup_path.read_text(encoding="utf-8"))
    name = setup["name"]
    strategy = setup["strategy"]
    sources: list[str] = strategy["sources"]
    corpus = load_corpus(version)
    queries = load_queries(version)
    print(f"{name}: {len(corpus)} theses, {len(queries)} queries, sources {sources}")

    body, meta = build_chunks(version, corpus, setup["chunking"].get("metadata_chunk", False))
    chunks = [chunk for handle in body for chunk in body[handle]]
    chunks += [chunk for handle in meta for chunk in meta[handle]]
    chunk_handles = [chunk.handle for chunk in chunks]
    chunk_texts = [chunk.text for chunk in chunks]
    print(f"{len(chunks)} chunks ({sum(len(group) for group in meta.values())} metadata)")

    bm25 = None
    if "lexical" in sources:
        tokens = [
            token for handle in body for token in cached_tokens(version, handle, body[handle])
        ]
        tokens += [lemma_tokens(chunk.text) for handle in meta for chunk in meta[handle]]
        bm25 = BM25Okapi(tokens)

    query_scores = None
    semantic_matrix: Any = None
    encode_ms = 0.0
    embedding = setup.get("embedding")
    if "semantic" in sources and embedding:
        embed_theses(body, embedding, "")
        if meta:
            embed_theses(meta, embedding, "meta")
        matrix = load_matrix(body, embedding, "")
        if meta:
            matrix = np.concatenate([matrix, load_matrix(meta, embedding, "meta")])
        encoder = load_model(
            embedding["model"],
            embedding.get("dtype", "float32"),
            embedding.get("max_seq_length", 512),
        )
        started = time.monotonic()
        prefix = embedding.get("query_prefix", "")
        query_vectors = encoder.encode(
            [f"{prefix}{query['text']}" for query in queries],
            batch_size=64,
            normalize_embeddings=True,
            convert_to_numpy=True,
        )
        encode_ms = (time.monotonic() - started) * 1000 / max(1, len(queries))
        query_scores = np.asarray(query_vectors, dtype=np.float32)
        del encoder
        semantic_matrix = matrix
    reranker = None
    reranking = setup.get("reranking")
    if reranking:
        import torch
        from sentence_transformers import CrossEncoder

        reranker = CrossEncoder(
            reranking["model"],
            max_length=reranking.get("max_length", 512),
            device="cuda",
            model_kwargs={"torch_dtype": torch.float16},
        )

    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    run_path = RUNS_DIR / f"{name}.run"
    latencies: list[float] = []
    with run_path.open("w", encoding="utf-8") as run_file:
        for position, query in enumerate(queries):
            started = time.monotonic()
            rankings = []
            if bm25 is not None:
                rankings.append(lexical_ranking(bm25, query["text"], strategy["chunk_pool"]))
            if query_scores is not None:
                scores = semantic_matrix @ query_scores[position]
                rankings.append(semantic_ranking(scores, strategy["chunk_pool"]))
            ranking = rankings[0] if len(rankings) == 1 else fuse_rrf(rankings, strategy["k"])
            if reranker is not None and reranking:
                ranking = rerank(
                    reranker, query["text"], ranking, chunk_texts, reranking["candidates"]
                )
            theses = to_theses(ranking, chunk_handles, RESULTS_PER_QUERY)
            latencies.append((time.monotonic() - started) * 1000 + encode_ms)
            for rank, (handle, score) in enumerate(theses, start=1):
                run_file.write(f"{query['id']} Q0 {handle} {rank} {score:.6f} {name}\n")
            if (position + 1) % 100 == 0:
                print(f"queries: {position + 1}/{len(queries)}")

    write_results(setup, version, run_path, chunks, latencies)
    print(f"run written to {run_path.relative_to(EXPERIMENT_DIR.parents[1])}")


def write_results(
    setup: dict[str, Any],
    version: str,
    run_path: Path,
    chunks: list[Chunk],
    latencies: list[float],
) -> None:
    """Results file with pipeline and cost; keeps metrics a previous scoring wrote."""
    import torch

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    path = RESULTS_DIR / f"{setup['name']}.json"
    previous = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    embedding = setup.get("embedding")
    index_seconds = 0.0
    if embedding and "semantic" in setup["strategy"]["sources"]:
        index_seconds = round(recorded_seconds(embedding), 1)
    results = {
        "experiment": EXPERIMENT,
        "setup": setup["name"],
        "description": setup.get("description", ""),
        "run": run_path.relative_to(EXPERIMENT_DIR.parents[1]).as_posix(),
        "pipeline": describe(setup, version),
        "cost": {
            "hardware": torch.cuda.get_device_name(0) if torch.cuda.is_available() else "CPU",
            "index_seconds": index_seconds,
            "chunks": len(chunks),
            "query_ms_median": round(statistics.median(latencies), 1) if latencies else None,
        },
        "eval_version": previous.get("eval_version"),
        "metrics": previous.get("metrics", {}),
    }
    path.write_text(json.dumps(results, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("setup", type=Path, help="setup file, relative to the experiment")
    parser.add_argument("--version", default="v0")
    args = parser.parse_args()
    utf8_stdout()
    setup_path = args.setup if args.setup.is_absolute() else EXPERIMENT_DIR / args.setup
    run(setup_path, args.version)


if __name__ == "__main__":
    main()
