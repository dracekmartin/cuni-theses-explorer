"""Ranking steps of a search setup: branches, fusion, reranking, aggregation to theses.

The lexical and semantic branches, the fusion and the aggregation behave exactly as in
experiment 01 (search.py there), which check_baseline.py verifies.
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


def semantic_ranking(scores: Any, pool: int) -> list[tuple[int, float]]:
    """Top chunks by cosine similarity (vectors are normalized, so a dot product)."""
    order = np.argsort(scores)[::-1][:pool]
    return [(int(index), float(scores[index])) for index in order]


def fuse_rrf(rankings: list[list[tuple[int, float]]], k: int) -> list[tuple[int, float]]:
    """Reciprocal rank fusion of chunk rankings."""
    scores: dict[int, float] = {}
    for ranking in rankings:
        for rank, (chunk_index, _) in enumerate(ranking):
            scores[chunk_index] = scores.get(chunk_index, 0.0) + 1.0 / (k + rank + 1)
    return sorted(scores.items(), key=lambda pair: pair[1], reverse=True)


def to_theses(
    ranking: list[tuple[int, float]], chunk_handles: list[str], top: int
) -> list[tuple[str, float]]:
    """Aggregate a chunk ranking to theses: a thesis ranks by its best chunk."""
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
