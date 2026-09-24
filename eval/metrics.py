"""Retrieval metrics used for every run, as pure functions over rankings and judgments.

A ranking is the list of thesis handles a setup returned for one query, best first.
Judgments map a handle to its grade (0, 1 or 2) for that query; a handle missing from
them is unjudged.
"""

from __future__ import annotations

import math
import random
from collections.abc import Sequence

Ranking = Sequence[str]
Judgments = dict[str, int]


def reciprocal_rank(ranking: Ranking, judgments: Judgments, k: int) -> float:
    """1 / rank of the first relevant thesis within the top k, 0 when there is none."""
    for rank, handle in enumerate(ranking[:k], start=1):
        if judgments.get(handle, 0) >= 1:
            return 1.0 / rank
    return 0.0


def success(ranking: Ranking, judgments: Judgments, k: int) -> float:
    """1 when a relevant thesis is in the top k, otherwise 0."""
    return 1.0 if any(judgments.get(handle, 0) >= 1 for handle in ranking[:k]) else 0.0


def ndcg(ranking: Ranking, judgments: Judgments, k: int) -> float:
    """nDCG@k with the grade as gain and 1 / log2(rank + 1) as discount."""
    gains = [judgments.get(handle, 0) for handle in ranking[:k]]
    dcg = sum(gain / math.log2(rank + 1) for rank, gain in enumerate(gains, start=1))
    ideal = sorted(judgments.values(), reverse=True)[:k]
    idcg = sum(gain / math.log2(rank + 1) for rank, gain in enumerate(ideal, start=1))
    return dcg / idcg if idcg > 0 else 0.0


def precision(ranking: Ranking, judgments: Judgments, k: int) -> float:
    """Share of relevant theses (grade 1 or 2) among the top k positions."""
    return sum(1 for handle in ranking[:k] if judgments.get(handle, 0) >= 1) / k


def recall(ranking: Ranking, judgments: Judgments, k: int) -> float | None:
    """Share of the judged relevant theses found in the top k; None when none is relevant."""
    relevant = {handle for handle, grade in judgments.items() if grade >= 1}
    if not relevant:
        return None
    return len(relevant & set(ranking[:k])) / len(relevant)


def judged(ranking: Ranking, judgments: Judgments, k: int) -> float:
    """Share of the top k results that have a judgment of any grade."""
    top = ranking[:k]
    return sum(1 for handle in top if handle in judgments) / len(top) if top else 0.0


def rbo(first: Ranking, second: Ranking, p: float = 0.9, depth: int = 10) -> float | None:
    """Extrapolated rank-biased overlap (Webber, Moffat, Zobel 2010) of two rankings.

    Both rankings are cut to the same depth k = min(depth, len(first), len(second)), where
    the extrapolated form for equal lengths applies. None when either ranking is empty.
    """
    k = min(depth, len(first), len(second))
    if k == 0:
        return None
    seen_first: set[str] = set()
    seen_second: set[str] = set()
    overlap = 0
    total = 0.0
    for d in range(1, k + 1):
        a, b = first[d - 1], second[d - 1]
        if a == b:
            overlap += 1
        else:
            overlap += (a in seen_second) + (b in seen_first)
        seen_first.add(a)
        seen_second.add(b)
        total += overlap / d * p**d
    return (overlap / k) * p**k + (1 - p) / p * total


def randomization_test(
    first: Sequence[float], second: Sequence[float], permutations: int = 10_000, seed: int = 0
) -> float:
    """Two-sided paired randomization test on per-query values; returns the p-value.

    Flips the sign of each per-query difference at random and counts how often the mean
    difference is at least as extreme as the observed one.
    """
    differences = [a - b for a, b in zip(first, second, strict=True)]
    if not differences:
        return 1.0
    observed = abs(sum(differences)) / len(differences)
    rng = random.Random(seed)
    extreme = 0
    for _ in range(permutations):
        flipped = sum(value if rng.random() < 0.5 else -value for value in differences)
        if abs(flipped) / len(differences) >= observed - 1e-12:
            extreme += 1
    return (extreme + 1) / (permutations + 1)
