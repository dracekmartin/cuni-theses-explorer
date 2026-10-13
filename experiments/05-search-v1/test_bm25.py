"""SparseBM25 must score exactly as rank_bm25, or 01-e5-bm25 stops being experiment 01."""

from __future__ import annotations

import random

import numpy as np
from bm25 import SparseBM25
from rank_bm25 import BM25Okapi

CORPUS = [
    "a b c a",
    "a d e",
    "a b",
    "f g h a",
    "a a a b",
    "c d e f g",
    "h",
    "a b c d e f g h",
]
QUERIES = [["a"], ["b", "c"], ["a", "a", "h"], ["x"], ["g", "x", "e"], []]


def built(documents: list[list[str]]) -> SparseBM25:
    index = SparseBM25()
    for tokens in documents:
        index.add(tokens)
    index.finish()
    return index


def test_scores_equal_rank_bm25_bit_for_bit() -> None:
    documents = [text.split() for text in CORPUS]
    sparse_index, reference = built(documents), BM25Okapi(documents)
    for query in QUERIES:
        assert np.array_equal(sparse_index.get_scores(query), reference.get_scores(query))


def test_random_corpus_with_common_terms() -> None:
    rng = random.Random(1)
    vocabulary = [f"w{number}" for number in range(40)]
    weights = [1 / (rank + 1) for rank in range(len(vocabulary))]
    documents = [rng.choices(vocabulary, weights, k=rng.randint(1, 30)) for _ in range(300)]
    sparse_index, reference = built(documents), BM25Okapi(documents)
    for _ in range(50):
        query = rng.choices(vocabulary, k=rng.randint(1, 6))
        assert np.array_equal(sparse_index.get_scores(query), reference.get_scores(query))
