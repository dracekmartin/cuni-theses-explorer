# Experiment 03: search setups

Which embedding model and which extra steps (a metadata chunk, reranking) improve on the
setup of experiment 01?

Done, 2026-09-24. Corpus and queries: eval/v0 (592 theses, 586 known-item queries,
6 topics). Builds on: experiments 01 and 02. Hardware: laptop, RTX 4050 6 GB.

| Setup | Change against 01-baseline | MRR@10 | S@1 | S@10 cross-lingual | nDCG@10 topics | RBO | ms per query |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `01-baseline` | experiment 01: e5-small and BM25 over chunks, fused by RRF | 0.870 | 0.831 | 0.932 | 0.630 | 0.349 | 211 |
| `01-baseline-lexical` | BM25 alone | 0.835* | 0.795 | 0.839* | 0.587 | 0.328 | 220 |
| `01-baseline-semantic` | e5-small alone | 0.872 | 0.841 | 0.884* | 0.626 | 0.343 | 8 |
| `bge-m3-semantic` | BGE-M3 alone | 0.967* | 0.945 | 0.997* | 0.758* | 0.666 | 12 |
| `bge-m3-hybrid` | BGE-M3 and BM25, fused by RRF | 0.908* | 0.865 | 0.994* | 0.663 | 0.425 | 219 |
| `bge-m3-meta-hybrid` | the same plus a Czech and an English metadata chunk | 0.949* | 0.925 | 0.997* | 0.700* | 0.453 | 227 |
| `bge-m3-meta-rerank` | the same plus a cross-encoder over the top 50 chunks | 0.985* | 0.976 | 0.997* | 0.729* | 0.489 | 1054 |

\* differs from `01-baseline` with p < 0.05 (paired randomization test over queries).
Topic scores rest on LLM judgments that no human has checked yet.

`01-baseline` reproduces experiment 01: `check_baseline.py` gives the same chunks, lemmas
and top 5 for the showcase queries in all three branches; only the text source differs
(TEXT bundle instead of pypdf). With e5-small the hybrid beats each branch alone, because
BM25 matches rare terms spelled the same in both languages (Artemisia, Databricks), which
the small model blurs.

BGE-M3 is the largest step. It lifts MRR@10 from 0.870 to 0.967, `detail` queries in the
other language from 0.670 (e5-small) to 0.989, and topics from 0.630 to 0.758, and it
returns similar results for the Czech and the English version of a query (RBO 0.666 against
0.349). All 28 known-item queries on which experiment 01 missed the top 5 and BGE-M3 ranked
the target first cross languages; in the same language there is no such query.

BM25 fused with equal weight makes BGE-M3 worse (MRR@10 0.908, topics 0.663), most of all on
`detail` queries. The metadata chunk wins back part of it, but only on `title` and `about`
queries, which were written from the same metadata. The reranker gives the best known-item
ranking (MRR@10 0.985) for one second per query, yet on topics BGE-M3 alone stays best.
BGE-M3 alone with the reranker is still to be tried.

The known-item queries are nearly saturated (Success@10 of at least 0.993 for every BGE-M3
setup), and the topic scores stand on 6 topics only. Embedding the 108,406 chunks took
600 s with e5-small and 1,468 s with BGE-M3. A hybrid run held about 2.4 GB of memory, and
two runs at once did not fit next to each other on the laptop.

Reproduce: `python experiments/03-search-setups/run.py setups/<setup>.toml`, then
`eval/score.py` and `eval/compare.py` as described in eval/README.md. With `--query "..."`
it answers single queries instead, side by side when given several setups.
