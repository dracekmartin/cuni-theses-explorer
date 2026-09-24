"""Unit tests of the metrics on small cases computed by hand."""

from __future__ import annotations

import math

import pytest
from metrics import (
    judged,
    ndcg,
    precision,
    randomization_test,
    rbo,
    recall,
    reciprocal_rank,
    success,
)


def test_reciprocal_rank_and_success() -> None:
    ranking = ["a", "b", "c"]
    judgments = {"c": 2}
    assert reciprocal_rank(ranking, judgments, 10) == pytest.approx(1 / 3)
    assert reciprocal_rank(ranking, judgments, 2) == 0.0
    assert success(ranking, judgments, 3) == 1.0
    assert success(ranking, judgments, 2) == 0.0
    assert reciprocal_rank([], judgments, 10) == 0.0


def test_grade_zero_is_not_relevant() -> None:
    assert reciprocal_rank(["a"], {"a": 0}, 10) == 0.0
    assert precision(["a", "b"], {"a": 0, "b": 1}, 2) == 0.5


def test_ndcg_by_hand() -> None:
    ranking = ["a", "b", "c"]
    judgments = {"a": 1, "c": 2, "d": 2}
    dcg = 1 / math.log2(2) + 2 / math.log2(4)
    idcg = 2 / math.log2(2) + 2 / math.log2(3) + 1 / math.log2(4)
    assert ndcg(ranking, judgments, 10) == pytest.approx(dcg / idcg)
    assert ndcg(["c", "d", "a"], judgments, 10) == pytest.approx(1.0)
    assert ndcg(ranking, {}, 10) == 0.0


def test_recall_and_judged() -> None:
    judgments = {"a": 2, "b": 0, "c": 1}
    assert recall(["a", "x"], judgments, 100) == pytest.approx(0.5)
    assert recall(["a"], {"b": 0}, 100) is None
    assert judged(["a", "x", "b", "y"], judgments, 10) == pytest.approx(0.5)


def test_rbo_bounds_and_symmetry() -> None:
    first = ["a", "b", "c", "d"]
    assert rbo(first, first) == pytest.approx(1.0)
    assert rbo(first, ["w", "x", "y", "z"]) == pytest.approx(0.0)
    second = ["b", "a", "d", "e"]
    assert rbo(first, second) == pytest.approx(rbo(second, first))
    value = rbo(first, second)
    assert value is not None and 0.0 < value < 1.0
    assert rbo([], first) is None


def test_rbo_by_hand() -> None:
    # Overlaps at depths 1 and 2 are 0 and 2: RBO = (2/2) p^2 + (1-p)/p (0 + 2/2 p^2).
    p = 0.9
    expected = p**2 + (1 - p) / p * p**2
    assert rbo(["a", "b"], ["b", "a"], p=p) == pytest.approx(expected)


def test_randomization_test() -> None:
    same = [0.5] * 30
    assert randomization_test(same, same) == 1.0
    better = [1.0] * 30
    worse = [0.0] * 30
    assert randomization_test(better, worse) < 0.01
