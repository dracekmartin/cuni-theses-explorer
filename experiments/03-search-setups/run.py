"""Run search setups over the queries of an evaluation version, or answer single queries.

Reads each setup description (setups/<name>.toml), embeds whatever is missing from the
cache, answers all queries in eval/<version>/queries.jsonl, and writes the run
(data/runs/03-search-setups/<name>.run) and the results file (results/<name>.json) with
the pipeline and cost. Metrics are added afterwards by eval/score.py. With --query the
setups answer the given queries instead and print their top theses, side by side when
several setups are given.

Usage:
    python experiments/03-search-setups/run.py setups/01-baseline.toml [--version v0]
    python experiments/03-search-setups/run.py setups/01-baseline.toml
        setups/bge-m3-semantic.toml --query "strategická videohra" --top 3
"""

from __future__ import annotations

import argparse
import gc
import html
import json
import shutil
import statistics
import textwrap
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
MAX_TITLE_LINES = 4
Ranking = list[tuple[str, float]]


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


def load_setup(path: Path) -> dict[str, Any]:
    return tomllib.loads(path.read_text(encoding="utf-8"))


def answer(
    setup: dict[str, Any],
    version: str,
    corpus: list[dict[str, Any]],
    queries: list[dict[str, Any]],
) -> tuple[list[Ranking], list[float], int]:
    """Rank the theses for every query. Returns the rankings, the latency of each query in
    milliseconds and the number of chunks in the index."""
    strategy = setup["strategy"]
    sources: list[str] = strategy["sources"]
    print(f"{setup['name']}: {len(corpus)} theses, {len(queries)} queries, sources {sources}")

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

    answers: list[Ranking] = []
    latencies: list[float] = []
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
            ranking = rerank(reranker, query["text"], ranking, chunk_texts, reranking["candidates"])
        answers.append(to_theses(ranking, chunk_handles, RESULTS_PER_QUERY))
        latencies.append((time.monotonic() - started) * 1000 + encode_ms)
        if (position + 1) % 100 == 0:
            print(f"queries: {position + 1}/{len(queries)}")
    return answers, latencies, len(chunks)


def run_setup(setup_path: Path, version: str) -> None:
    """Answer the query set of the version and write the run and the results file."""
    setup = load_setup(setup_path)
    corpus = load_corpus(version)
    queries = load_queries(version)
    answers, latencies, chunk_count = answer(setup, version, corpus, queries)
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    run_path = RUNS_DIR / f"{setup['name']}.run"
    with run_path.open("w", encoding="utf-8") as run_file:
        for query, theses in zip(queries, answers, strict=True):
            for rank, (handle, score) in enumerate(theses, start=1):
                run_file.write(f"{query['id']} Q0 {handle} {rank} {score:.6f} {setup['name']}\n")
    write_results(setup, version, run_path, chunk_count, latencies)
    print(f"run written to {run_path.relative_to(EXPERIMENT_DIR.parents[1])}")


def ask(setup_paths: list[Path], version: str, texts: list[str], top: int) -> None:
    """Answer single queries with each setup and print the top theses of every setup."""
    corpus = load_corpus(version)
    queries = [{"id": f"q{number}", "text": text} for number, text in enumerate(texts, 1)]
    columns: list[tuple[str, list[Ranking]]] = []
    for path in setup_paths:
        setup = load_setup(path)
        answers, _, _ = answer(setup, version, corpus, queries)
        columns.append((setup["name"], answers))
        free_memory()
    records = {record["handle"]: record for record in corpus}
    for number, text in enumerate(texts):
        print(f"\n=== {text}")
        if len(columns) == 1:
            for rank, (handle, _) in enumerate(columns[0][1][number][:top], start=1):
                record = records[handle]
                year = (record.get("year") or "?")[:4]
                title = html.unescape(record["title"])
                print(f"{rank:3d}. [{record.get('language')}, {year}] {title} ({handle})")
            continue
        width = column_width(len(columns))
        print("      " + "".join(f"{name:<{width + 2}}" for name, _ in columns).rstrip())
        for rank in range(top):
            cells: list[list[str]] = []
            for _, answers in columns:
                theses = answers[number]
                lines: list[str] = []
                if rank < len(theses):
                    record = records[theses[rank][0]]
                    title = f"[{record.get('language')}] {html.unescape(record['title'])}"
                    lines = textwrap.wrap(
                        title, width, max_lines=MAX_TITLE_LINES, placeholder=" ..."
                    )
                cells.append(lines)
            for line in range(max(1, *(len(lines) for lines in cells))):
                prefix = f"{rank + 1:3d}.  " if line == 0 else "      "
                parts = [lines[line] if line < len(lines) else "" for lines in cells]
                print(prefix + "".join(f"{part:<{width + 2}}" for part in parts).rstrip())


def column_width(columns: int) -> int:
    """Width of one setup column, fitted to the width of the terminal."""
    total = shutil.get_terminal_size(fallback=(120, 40)).columns
    return max(30, (total - 6) // columns - 2)


def free_memory() -> None:
    """Release what one setup held before the next one loads; the laptop runs short of
    commit memory with two indexes and models at once."""
    gc.collect()
    import torch

    if torch.cuda.is_available():
        torch.cuda.empty_cache()


def write_results(
    setup: dict[str, Any],
    version: str,
    run_path: Path,
    chunk_count: int,
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
            "chunks": chunk_count,
            "query_ms_median": round(statistics.median(latencies), 1) if latencies else None,
        },
        "eval_version": previous.get("eval_version"),
        "metrics": previous.get("metrics", {}),
    }
    path.write_text(json.dumps(results, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("setups", nargs="+", type=Path, help="setup files, relative to here")
    parser.add_argument("--version", default="v0")
    parser.add_argument(
        "--query", action="append", help="answer this query instead of the set, repeatable"
    )
    parser.add_argument("--top", type=int, default=10, help="theses shown per --query")
    args = parser.parse_args()
    utf8_stdout()
    paths = [path if path.is_absolute() else EXPERIMENT_DIR / path for path in args.setups]
    if args.query:
        ask(paths, args.version, args.query, args.top)
    else:
        for path in paths:
            run_setup(path, args.version)


if __name__ == "__main__":
    main()
