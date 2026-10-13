# Experiments

Self-contained probes, numbered in order. Each one answers a question the design needs
answered before code goes into `apps/` or `libs/`. Every README follows
[TEMPLATE.md](TEMPLATE.md).

| Experiment | Question | Status |
| --- | --- | --- |
| [01-mini-pipeline](01-mini-pipeline/README.md) | Does a first end-to-end pipeline work on real DSpace data, and how do lexical and semantic search behave on it? | done, 2026-09-09 |
| [02-eval-set](02-eval-set/README.md) | Which fixed corpus, queries and relevance judgments let us compare search setups with each other and with the current DSpace search? | v0 and v1 built, human check of layer 2 postponed |
| [03-search-setups](03-search-setups/README.md) | Which embedding model and which extra steps (a metadata chunk, reranking) improve on the setup of experiment 01? | done, 2026-09-24 |
| [04-full-harvest](04-full-harvest/README.md) | Can the metadata and body texts of all theses be harvested in one unattended run, and how many theses have a usable text? | done, 2026-10-12 |
| [05-search-v1](05-search-v1/README.md) | Do the findings of experiment 03 hold on 5,000 theses of the whole university, how does the search of DSpace compare, and which further steps help? | done, 2026-10-13 |

## Comparing experiments

An experiment that builds a search setup does not compute metrics itself. Each setup
writes a run, the ranked theses for every query, and `eval/score.py` scores it against
a versioned evaluation set described in [eval/README.md](../eval/README.md). Two results
are comparable when they were scored against the same version. An older setup is compared
by running its configuration again on the current version: experiment 03 does this for
experiment 01 as `01-baseline`, experiment 05 as `01-e5-bm25`. The baseline of the
evaluation is the search the university runs today, the run `dspace` of experiment 05.

## Search setups

Every search setup tried so far, with its result on the newest version it ran on. Results
of different versions do not compare. An experiment that adds or reruns a setup updates
this table.

| Setup | Experiments | Pipeline | MRR@10 | nDCG@10 topics | Version | Status |
| --- | --- | --- | --- | --- | --- | --- |
| `dspace` | 05 | the search of DSpace, queries as typed | 0.442 | 0.494 | v1 | baseline: what the university runs today |
| `dspace-escaped` | 05 | the same with the Solr syntax escaped | 0.562 | 0.494 | v1 | reference |
| `01-e5-bm25` | 01, 03, 05 | e5-small and BM25 (simplemma) over chunks, RRF (`01-baseline` in 03) | 0.782 | 0.560 | v1 | reference: experiment 01 |
| `01-bm25` | 03, 05 | BM25 alone (`01-baseline-lexical` in 03) | 0.760 | 0.515 | v1 | reference |
| `01-baseline-semantic` | 03 | e5-small alone | 0.872 | 0.626 | v0 | superseded by `bge-m3-semantic` |
| `bge-m3-semantic` | 03, 05 | BGE-M3 alone | 0.894 | 0.630 | v1 | reference for every BGE-M3 setup |
| `bge-m3-hybrid` | 03 | BGE-M3 and BM25, RRF | 0.908 | 0.663 | v0 | superseded: BM25 at full weight hurts |
| `bge-m3-meta-hybrid` | 03, 05 | the same plus metadata chunks | 0.881 | 0.602 | v1 | superseded by `bge-m3-meta-weighted` |
| `bge-m3-meta-weighted` | 05 | the same with BM25 at half weight | 0.894 | 0.636 | v1 | superseded by `bge-m3-top2` |
| `bge-m3-meta-rerank` | 03, 05 | meta-hybrid with a cross-encoder over the top 50 chunks | 0.948 | 0.640 | v1 | best on known items |
| `bge-m3-rerank` | 05 | BGE-M3 with the cross-encoder | 0.933 | 0.639 | v1 | second on known items, ties for the best across languages, simpler than `bge-m3-meta-rerank` |
| `bge-m3-sparse` | 05 | the learned lexical weights of BGE-M3 alone | 0.786 | 0.524 | v1 | candidate lexical branch: beats BM25 without a lemmatizer |
| `bge-m3-dense-sparse` | 05 | BGE-M3 plus 0.3 times its lexical weights | 0.897 | 0.624 | v1 | dead end: adds nothing to BGE-M3 |
| `bge-m3-qwen3` | 05 | BGE-M3, top 100 chunks rescored by Qwen3-Embedding-0.6B | 0.890 | 0.650 | v1 | dead end on the laptop: no significant gain, the 4B model is untested |
| `bge-m3-top2` | 05 | BGE-M3, a thesis by the sum of its 2 best chunks | 0.901 | 0.661 | v1 | best balance, tuned on the test topics |
| `bge-m3-top3`, `-top5`, `-top10` | 05 | the same with 3, 5 and 10 chunks | 0.894 to 0.860 | 0.680 to 0.699 | v1 | best on topics, worse on known items from 5 chunks, tuned on the test topics |

Not tried yet: the cross-encoder together with summing two chunks, Qwen3-Embedding-4B over
the whole corpus.

## Showcase queries

Four queries from experiment 01, kept as a quick qualitative check in every experiment
that builds a search setup. The last column is the thesis the query was about in
experiment 01, not a relevance judgment.

| Query | Thesis in question |
| --- | --- |
| strategy videogame | *Artificial Intelligence for a Castle Conquest Simulation Game* (20.500.11956/148361) |
| strategická videohra | the same thesis, through a Czech query |
| psychologie dlouhodobých partnerských vztahů | *Psychologické aspekty vztahů na dálku* (20.500.11956/29514) |
| podmíněné větvení v C# | *Conditional Branching Assistant for C#* (20.500.11956/192893), not in the experiment 01 sample |
