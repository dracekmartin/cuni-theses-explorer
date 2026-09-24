# Experiment 03: search setups

Which embedding model and which extra steps (a metadata chunk, reranking) improve on the
setup of experiment 01?

Running, 2026-09-24. Corpus and queries: eval/v0 (592 theses, 586 known-item queries).
Builds on: experiments 01 and 02. Hardware: laptop, RTX 4050 6 GB.

| Setup | Change against 01-baseline | MRR@10 | S@10 | S@10 cross-lingual | S@10 detail, cross-lingual |
| --- | --- | --- | --- | --- | --- |
| `01-baseline` | experiment 01: e5-small and BM25 over chunks, fused by RRF | 0.870 | 0.961 | 0.932 | 0.852 |
| `01-baseline-lexical` | BM25 alone | 0.835* | 0.901* | 0.839* | 0.739 |
| `01-baseline-semantic` | e5-small alone | 0.872 | 0.933* | 0.884* | 0.670 |

\* differs from `01-baseline` with p < 0.05 (paired randomization test over queries).

`01-baseline` reproduces experiment 01: `check_baseline.py` gives the same chunks, lemmas
and top 5 for the showcase queries in all three branches. The only difference is the text
source, the TEXT bundle instead of pypdf. The hybrid beats each branch alone.

Semantic search wins on paraphrases, BM25 on details. On `detail` queries in the other
language e5-small falls below BM25, because such queries carry rare terms spelled the same
in both languages (Artemisia, Databricks, Pale Fire), which BM25 matches exactly and
a small embedding model blurs. Most remaining errors of the hybrid are `detail` queries.

Embedding the 108,406 chunks with e5-small took 600 s; a query takes 7 ms in the semantic
branch and 189 ms in BM25, which rank_bm25 computes in Python.

Reproduce: `python experiments/03-search-setups/run.py setups/<setup>.toml`, then
`eval/score.py` and `eval/compare.py` as described in eval/README.md.
