# Experiment 05: search setups on v1

Do the findings of experiment 03 hold on 5,000 theses of the whole university, how does
the search of DSpace compare, and which further steps help?

Done, 2026-10-13. Corpus and queries: eval/v1 (5,029 theses, 1,478 known-item queries,
25 topics). Builds on: experiments 03 and 04. Hardware: laptop, RTX 4050 6 GB.

| Setup | Pipeline | MRR@10 | S@1 | S@10 cross-lingual | nDCG@10 topics | RBO | ms per query |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `dspace` | baseline: the search of DSpace, queries as typed | 0.442 | 0.418 | 0.361 | 0.494 | 0.451 | |
| `dspace-escaped` | the same with the Solr syntax escaped | 0.562* | 0.534 | 0.427* | 0.494 | 0.426 | |
| `01-e5-bm25` | experiment 01: e5-small and BM25 over chunks, fused by RRF | 0.782* | 0.727 | 0.827* | 0.560* | 0.306 | 110 |
| `01-bm25` | BM25 alone | 0.760* | 0.714 | 0.751* | 0.515 | 0.283 | 53 |
| `bge-m3-sparse` | the learned lexical weights of BGE-M3 alone | 0.786* | 0.736 | 0.807* | 0.524 | 0.321 | 41 |
| `bge-m3-semantic` | BGE-M3 alone | 0.894* | 0.844 | 0.964* | 0.630* | 0.599 | 107 |
| `bge-m3-dense-sparse` | BGE-M3 plus 0.3 times its lexical weights | 0.897* | 0.849 | 0.966* | 0.624* | 0.558 | 355 |
| `bge-m3-meta-hybrid` | BGE-M3, BM25 and metadata chunks, fused by RRF | 0.881* | 0.835 | 0.960* | 0.602* | 0.419 | 153 |
| `bge-m3-meta-weighted` | the same with BM25 at half weight | 0.894* | 0.847 | 0.964* | 0.636* | 0.522 | 154 |
| `bge-m3-qwen3` | BGE-M3, its top 100 chunks rescored by Qwen3-Embedding-0.6B | 0.890* | 0.839 | 0.969* | 0.650* | 0.579 | 116 |
| `bge-m3-rerank` | BGE-M3 with a cross-encoder over the top 50 chunks | 0.933* | 0.900 | 0.986* | 0.639* | 0.608 | 842 |
| `bge-m3-meta-rerank` | meta-hybrid with the cross-encoder | 0.948* | 0.923 | 0.983* | 0.640* | 0.488 | 884 |
| `bge-m3-top2` | BGE-M3, a thesis by the sum of its 2 best chunks | 0.901* | 0.853 | 0.970* | 0.661* | 0.634 | 100 |
| `bge-m3-top3` | the same with 3 chunks | 0.894* | 0.848 | 0.965* | 0.680* | 0.642 | 355 |
| `bge-m3-top5` | the same with 5 chunks | 0.878* | 0.832 | 0.946* | 0.687* | 0.650 | 211 |
| `bge-m3-top10` | the same with 10 chunks | 0.860* | 0.812 | 0.946* | 0.699* | 0.652 | 212 |

\* differs from `dspace` with p < 0.05 (paired randomization test over queries). Topic
scores rest on LLM judgments of 1,172 pooled pairs. The human check is postponed, see
the weaknesses of v1 in experiment 02.

The code is a copy of experiment 03 with changes that keep the results of a setup as they
were: BM25 runs over a sparse matrix (`bm25.py`, the scores of rank_bm25 to the last bit,
which `test_bm25.py` checks, and its lexical ranking of v0 is byte for byte the run of
experiment 03), the embedding matrix is filled in place, and the setups run on v1 only,
since the caches know a thesis by its handle and not by its text.

v1 is harder than v0, so it separates the setups better: MRR@10 of experiment 01 falls
from 0.870 to 0.782, of BGE-M3 from 0.967 to 0.894. The findings of experiment 03 hold:
BGE-M3 is the largest step, BM25 at full weight makes it worse, and the reranker gives the
best known-item ranking. BGE-M3 with the reranker but without BM25 is second on known
items (0.933 against 0.948, a significant difference) and ties for the best across
languages (0.986 against 0.983). BM25 at half weight, fixed before any result, lifts the
hybrid on topics from 0.602 to 0.636.

DSpace finds the target in the top 10 for 48 % of the known-item queries as a user types
them, the setups for 85 to 99 %. The Solr syntax decides much of it: a question mark is a
wildcard, so sentence queries succeed in 7 %, and a colon names a field, so a title with
a colon finds nothing. Escaped, titles succeed in 99.8 % and sentences in 36 %. Detail
queries stay at 35 % either way: DSpace requires every word of the query ("videohra" has
343 results, "videohra xyzqqq" none), and a long query rarely matches. Four queries with
colons such as "1:1:1" end in a server error, and a query with a percent sign always
does, so the runs drop the sign. On topics DSpace reaches 0.494, as much as BM25 alone.

Three further steps were tried. Qwen3-Embedding-0.6B embeds 19 to 21 chunks per second on
the laptop against about 70 for BGE-M3, so the whole corpus would take 13 to 14 hours.
Rescoring only the 73,949 chunks that are among the top 100 of some query took an hour,
and it changes nothing significant. The learned lexical weights of BGE-M3
(`learned_sparse.py`, 4 hours for the corpus) beat BM25 on known items (0.786 against
0.760, p < 0.05) and do not differ from it on topics, without any lemmatizer, but add
nothing to the dense vectors. Ranking a thesis by the sum of its best chunks helps topics
the more chunks it sums (0.630 with one, 0.699 with ten). Known items hold up to three
chunks and suffer with five and ten (MRR@10 0.878 and 0.860), most of all detail queries.
Two chunks improve both. One thesis has five chunks of blanks only, which the chunking of
experiment 01 keeps and a sum counts five times, but it moves no metric by 0.001. The
numbers of chunks were tried on the test topics themselves, so the choice needs topics of
their own before it counts.

| Setup | title | about-short | about-sentence | detail |
| --- | --- | --- | --- | --- |
| `dspace` | 0.827 | 0.740 | 0.071 | 0.343 |
| `dspace-escaped` | 0.998 | 0.740 | 0.364 | 0.347 |
| `01-e5-bm25` | 0.962 | 0.927 | 0.932 | 0.782 |
| `bge-m3-semantic` | 0.992 | 0.986 | 1.000 | 0.927 |
| `bge-m3-rerank` | 0.998 | 0.990 | 0.998 | 0.968 |
| `bge-m3-top10` | 0.985 | 0.993 | 0.998 | 0.865 |

Success@10 by query type. Embedding the chunks of 4,452 theses (the 4,437 new ones and 15
of v0 whose text changed) took 1.4 hours with e5-small and 3.3 hours with BGE-M3. The 577
theses of v0 with an unchanged text came from the cache of experiment 03. A query takes
about 0.1 s, and 0.9 s with the reranker. The rescoring time of Qwen3 leaves out embedding
the candidates, which an index of the whole corpus would do in advance.

Reproduce: `python experiments/05-search-v1/run.py setups/<setup>.toml` and
`python experiments/05-search-v1/dspace_run.py [--escaped]`, then `eval/score.py` and
`eval/compare.py` with `--version v1` as described in eval/README.md.
