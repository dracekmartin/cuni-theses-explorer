"""Query the mini index three ways and show the rankings side by side.

For a query the script prints the top theses according to (1) lexical BM25 over
lemmatized tokens, (2) semantic search over chunk embeddings, and (3) their reciprocal
rank fusion. Chunks are ranked first and aggregate to theses by their best chunk.

Usage:
    python search.py "podmíněné větvení v C#" [--top 5]
"""

from __future__ import annotations

import argparse
import json
from typing import Any

import numpy as np
from common import INDEX_DIR, ThesisRecord, lemma_tokens, load_manifest, utf8_stdout
from rank_bm25 import BM25Okapi

RRF_K = 60
CHUNK_POOL = 200  # how many top chunks per branch enter fusion and aggregation
SNIPPET_CHARS = 160


def load_index() -> tuple[list[dict[str, Any]], list[list[str]], np.ndarray, dict[str, Any]]:
    chunks_path = INDEX_DIR / "chunks.jsonl"
    if not chunks_path.exists():
        raise SystemExit("index not found, run build_index.py first")
    with chunks_path.open(encoding="utf-8") as file:
        chunks = [json.loads(line) for line in file if line.strip()]
    with (INDEX_DIR / "tokens.jsonl").open(encoding="utf-8") as file:
        tokens = [json.loads(line) for line in file if line.strip()]
    embeddings = np.load(INDEX_DIR / "embeddings.npy")
    meta = json.loads((INDEX_DIR / "meta.json").read_text(encoding="utf-8"))
    return chunks, tokens, embeddings, meta


def ranked_chunks_bm25(query: str, tokens: list[list[str]]) -> list[int]:
    bm25 = BM25Okapi(tokens)
    scores = bm25.get_scores(lemma_tokens(query))
    order = np.argsort(scores)[::-1][:CHUNK_POOL]
    return [int(index) for index in order if scores[index] > 0]


def ranked_chunks_semantic(query: str, embeddings: np.ndarray, model_name: str) -> list[int]:
    from sentence_transformers import SentenceTransformer  # lazy, loads torch

    model = SentenceTransformer(model_name)
    query_vector = model.encode(f"query: {query}", normalize_embeddings=True)
    scores = embeddings @ np.asarray(query_vector, dtype=np.float32)
    return [int(index) for index in np.argsort(scores)[::-1][:CHUNK_POOL]]


def fuse_rrf(rankings: list[list[int]]) -> list[int]:
    """Reciprocal rank fusion of chunk rankings."""
    scores: dict[int, float] = {}
    for ranking in rankings:
        for rank, chunk_index in enumerate(ranking):
            scores[chunk_index] = scores.get(chunk_index, 0.0) + 1.0 / (RRF_K + rank + 1)
    return [index for index, _ in sorted(scores.items(), key=lambda pair: pair[1], reverse=True)]


def theses_from_chunks(
    chunk_ranking: list[int],
    chunks: list[dict[str, Any]],
    theses: dict[str, ThesisRecord],
    top: int,
) -> list[tuple[ThesisRecord, str]]:
    """Aggregate a chunk ranking to theses: a thesis ranks by its best chunk."""
    results: list[tuple[ThesisRecord, str]] = []
    seen: set[str] = set()
    for chunk_index in chunk_ranking:
        handle = str(chunks[chunk_index]["handle"])
        if handle in seen or handle not in theses:
            continue
        seen.add(handle)
        snippet = " ".join(str(chunks[chunk_index]["text"]).split())[:SNIPPET_CHARS]
        results.append((theses[handle], snippet))
        if len(results) >= top:
            break
    return results


def print_ranking(heading: str, results: list[tuple[ThesisRecord, str]]) -> None:
    print(f"\n=== {heading} ===")
    if not results:
        print("  (no matches)")
    for position, (record, snippet) in enumerate(results, start=1):
        faculty_short = "MFF" if "Matematicko" in record.faculty else "FF"
        print(f"{position}. [{faculty_short} {record.year or '?'}] {record.title}")
        print(f"   {snippet}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("query")
    parser.add_argument("--top", type=int, default=5)
    args = parser.parse_args()

    utf8_stdout()
    chunks, tokens, embeddings, meta = load_index()
    theses = {record.handle: record for record in load_manifest()}

    bm25_ranking = ranked_chunks_bm25(args.query, tokens)
    semantic_ranking = ranked_chunks_semantic(args.query, embeddings, meta["model"])
    hybrid_ranking = fuse_rrf([bm25_ranking, semantic_ranking])

    print(f"query: {args.query}  (model: {meta['model']}, chunks: {meta['chunks']})")
    print_ranking("lexical (BM25)", theses_from_chunks(bm25_ranking, chunks, theses, args.top))
    print_ranking("semantic", theses_from_chunks(semantic_ranking, chunks, theses, args.top))
    print_ranking("hybrid (RRF)", theses_from_chunks(hybrid_ranking, chunks, theses, args.top))


if __name__ == "__main__":
    main()
