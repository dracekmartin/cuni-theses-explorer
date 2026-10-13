"""Aggregation of chunks to theses, and scoring with the learned sparse index."""

from __future__ import annotations

from pathlib import Path

import learned_sparse
import numpy as np
import pytest
from common import Chunk
from learned_sparse import load_index, scores, token_weights
from ranking import to_theses

HANDLES = ["a", "a", "a", "b", "c", "b"]


def test_best_chunk_ranks_by_the_first_chunk_of_each_thesis() -> None:
    ranking = [(3, 0.9), (0, 0.8), (1, 0.7), (2, 0.6), (4, 0.5)]
    assert [handle for handle, _ in to_theses(ranking, HANDLES, 10)] == ["b", "a", "c"]


def test_sum_of_top_chunks_lifts_a_thesis_with_several_good_chunks() -> None:
    ranking = [(3, 0.9), (0, 0.8), (1, 0.7), (2, 0.6), (4, 0.5), (5, 0.1)]
    theses = to_theses(ranking, HANDLES, 10, method="sum of top chunks", chunks=3)
    assert [handle for handle, _ in theses] == ["a", "b", "c"]
    assert theses[0][1] == pytest.approx(0.8 + 0.7 + 0.6)
    assert theses[1][1] == pytest.approx(0.9 + 0.1)


def test_learned_sparse_scores_sum_products_of_shared_tokens(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(learned_sparse, "CACHE_DIR", tmp_path)
    groups = {"h/1": [Chunk("h/1", 0, "x"), Chunk("h/1", 1, "y")], "h/2": [Chunk("h/2", 0, "z")]}
    stored = {"h/1": [{5: 0.5, 7: 0.2}, {7: 1.0}], "h/2": [{9: 0.4}]}
    for handle, weights in stored.items():
        np.savez(
            tmp_path / f"{handle.replace('/', '_')}.npz",
            indptr=np.concatenate([[0], np.cumsum([len(w) for w in weights])]),
            tokens=np.array([t for w in weights for t in w], dtype=np.int32),
            weights=np.array([v for w in weights for v in w.values()], dtype=np.float32),
        )
    index = load_index([(groups, "")], vocabulary=10)
    assert index.shape == (3, 10)
    assert scores(index, {7: 2.0, 9: 1.0}) == pytest.approx([0.4, 2.0, 0.4])


def test_token_weights_keep_the_largest_weight_of_each_token() -> None:
    ids = np.array([0, 7, 5, 7, 2, 1])
    weights = np.array([0.9, 0.2, 0.0, 0.6, 0.8, 0.5], dtype=np.float32)
    mask = np.array([1, 1, 1, 1, 1, 0])
    found = token_weights(ids, weights, mask, np.array([0, 1, 2, 3]))
    assert found == pytest.approx({7: 0.6})
