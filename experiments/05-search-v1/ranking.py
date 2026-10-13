"""Ranking steps of a search setup: branches, fusion, reranking, aggregation to theses.

Copied from experiment 03, where check_baseline.py verified that the branches, the fusion
and the aggregation behave exactly as in experiment 01. The fusion can now weight the
branches, and equal weights give the fusion of experiment 01.
"""

from __future__ import annotations

from typing import Any

import numpy as np
from common import lemma_tokens


def lexical_ranking(bm25: Any, query: str, pool: int) -> list[tuple[int, float]]:
    """Top chunks by BM25 over lemmatized tokens; chunks without any match are left out."""
    scores = bm25.get_scores(lemma_tokens(query))
    order = np.argsort(scores)[::-1][:pool]
    return [(int(index), float(scores[index])) for index in order if scores[index] > 0]


def positive_ranking(scores: Any, pool: int) -> list[tuple[int, float]]:
    """Top chunks of a lexical score, without chunks that share no token with the query."""
    order = np.argsort(scores)[::-1][:pool]
    return [(int(index), float(scores[index])) for index in order if scores[index] > 0]


def semantic_ranking(scores: Any, pool: int) -> list[tuple[int, float]]:
    """Top chunks by cosine similarity (vectors are normalized, so a dot product)."""
    order = np.argsort(scores)[::-1][:pool]
    return [(int(index), float(scores[index])) for index in order]


def fuse_rrf(
    rankings: list[list[tuple[int, float]]], k: int, weights: list[float] | None = None
) -> list[tuple[int, float]]:
    """Reciprocal rank fusion of chunk rankings, each branch with its weight."""
    scores: dict[int, float] = {}
    for ranking, weight in zip(rankings, weights or [1.0] * len(rankings), strict=True):
        for rank, (chunk_index, _) in enumerate(ranking):
            scores[chunk_index] = scores.get(chunk_index, 0.0) + weight / (k + rank + 1)
    return sorted(scores.items(), key=lambda pair: pair[1], reverse=True)


def to_theses(
    ranking: list[tuple[int, float]],
    chunk_handles: list[str],
    top: int,
    method: str = "best chunk",
    chunks: int = 1,
) -> list[tuple[str, float]]:
    """Aggregate a chunk ranking to theses. With "best chunk" a thesis ranks by its best
    chunk, with "sum of top chunks" by the sum of the scores of its best `chunks` chunks in
    the ranking, so a thesis with several matching passages moves up. The sum needs scores
    of one model, so it does not follow reranking."""
    if method == "sum of top chunks":
        return sum_of_top_chunks(ranking, chunk_handles, top, chunks)
    if method != "best chunk":
        raise ValueError(f"unknown aggregation: {method}")
    results: list[tuple[str, float]] = []
    seen: set[str] = set()
    for chunk_index, score in ranking:
        handle = chunk_handles[chunk_index]
        if handle in seen:
            continue
        seen.add(handle)
        results.append((handle, score))
        if len(results) >= top:
            break
    return results


def sum_of_top_chunks(
    ranking: list[tuple[int, float]], chunk_handles: list[str], top: int, chunks: int
) -> list[tuple[str, float]]:
    totals: dict[str, float] = {}
    counts: dict[str, int] = {}
    for chunk_index, score in ranking:
        handle = chunk_handles[chunk_index]
        if counts.get(handle, 0) < chunks:
            totals[handle] = totals.get(handle, 0.0) + score
            counts[handle] = counts.get(handle, 0) + 1
    # sorted() keeps the first-seen order of equal sums, so ties follow the best chunk.
    return sorted(totals.items(), key=lambda pair: pair[1], reverse=True)[:top]


def rerank(
    reranker: Any,
    query: str,
    ranking: list[tuple[int, float]],
    chunk_texts: list[str],
    candidates: int,
) -> list[tuple[int, float]]:
    """Rescore the top candidate chunks with a cross-encoder; the rest keep their order."""
    head = ranking[:candidates]
    if not head:
        return ranking
    scores = reranker.predict(
        [(query, chunk_texts[index]) for index, _ in head], batch_size=32, show_progress_bar=False
    )
    rescored = sorted(
        ((index, float(score)) for (index, _), score in zip(head, scores, strict=True)),
        key=lambda pair: pair[1],
        reverse=True,
    )
    return rescored + ranking[candidates:]
