"""BM25Okapi of rank_bm25, computed over a sparse matrix.

rank_bm25 keeps one dictionary of term counts per chunk, which for the 0.9 million chunks
of eval/v1 does not fit into the memory of a laptop. SparseBM25 stores the same counts as
a compressed sparse column matrix and adds documents one at a time, so the token lists
never have to be held at once. The formulas and the order of every floating point
operation follow rank_bm25 0.2.2, so the scores are the same to the last bit; test_bm25.py
checks it. The module imports nothing from common, so tests of other experiments do not
collide with it.
"""

from __future__ import annotations

import math
from collections import Counter
from typing import Any

import numpy as np
from scipy import sparse


class SparseBM25:
    def __init__(self, k1: float = 1.5, b: float = 0.75, epsilon: float = 0.25) -> None:
        self.k1, self.b, self.epsilon = k1, b, epsilon
        self.vocabulary: dict[str, int] = {}
        self._term_ids: list[Any] = []
        self._counts: list[Any] = []
        self._lengths: list[int] = []
        self.corpus_size = 0

    def add(self, tokens: list[str]) -> None:
        """Add one document; terms are numbered in the order rank_bm25 first meets them."""
        counts = Counter(tokens)
        self._term_ids.append(
            np.fromiter(
                (self.vocabulary.setdefault(term, len(self.vocabulary)) for term in counts),
                dtype=np.int32,
                count=len(counts),
            )
        )
        self._counts.append(np.fromiter(counts.values(), dtype=np.int32, count=len(counts)))
        self._lengths.append(len(tokens))
        self.corpus_size += 1

    def finish(self) -> None:
        """Build the matrix and the idf once all documents are added."""
        rows = np.repeat(
            np.arange(self.corpus_size, dtype=np.int32), [len(ids) for ids in self._term_ids]
        )
        columns = np.concatenate(self._term_ids) if self._term_ids else np.zeros(0, np.int32)
        counts = np.concatenate(self._counts) if self._counts else np.zeros(0, np.int32)
        self._term_ids, self._counts = [], []
        matrix = sparse.csc_matrix(
            (counts, (rows, columns)), shape=(self.corpus_size, len(self.vocabulary))
        )
        del rows, columns, counts
        matrix.sort_indices()
        self.indptr, self.indices, self.data = matrix.indptr, matrix.indices, matrix.data
        doc_len = np.array(self._lengths)
        self.avgdl = sum(self._lengths) / self.corpus_size
        self.norm = self.k1 * (1 - self.b + self.b * doc_len / self.avgdl)
        self.idf = self._idf(np.diff(self.indptr))

    def _idf(self, document_frequency: Any) -> list[float]:
        """Idf per term, a negative one replaced by epsilon times the average idf."""
        idf: list[float] = []
        idf_sum = 0.0
        negative: list[int] = []
        for term, frequency in enumerate(document_frequency.tolist()):
            value = math.log(self.corpus_size - frequency + 0.5) - math.log(frequency + 0.5)
            idf.append(value)
            idf_sum += value
            if value < 0:
                negative.append(term)
        eps = self.epsilon * (idf_sum / len(idf)) if idf else 0.0
        for term in negative:
            idf[term] = eps
        return idf

    def get_scores(self, query: list[str]) -> Any:
        """Score of every document, a repeated query term counting every time it repeats."""
        score = np.zeros(self.corpus_size)
        for term in query:
            column = self.vocabulary.get(term)
            if column is None or not self.idf[column]:
                continue
            start, end = self.indptr[column], self.indptr[column + 1]
            documents = self.indices[start:end]
            frequency = self.data[start:end]
            score[documents] += self.idf[column] * (
                frequency * (self.k1 + 1) / (frequency + self.norm[documents])
            )
        return score
