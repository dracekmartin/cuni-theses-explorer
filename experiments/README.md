# Experiments

Self-contained probes, numbered in order. Each one answers a question the design needs
answered before code goes into `apps/` or `libs/`. Every README follows
[TEMPLATE.md](TEMPLATE.md).

| Experiment | Question | Status |
| --- | --- | --- |
| [01-mini-pipeline](01-mini-pipeline/README.md) | Does a first end-to-end pipeline work on real DSpace data, and how do lexical and semantic search behave on it? | done, 2026-09-09 |
| [02-eval-set](02-eval-set/README.md) | Which fixed corpus, queries and relevance judgments let us compare search setups with each other and with the current DSpace search? | running |
| [03-search-setups](03-search-setups/README.md) | Which embedding model and which extra steps (a metadata chunk, reranking) improve on the setup of experiment 01? | running |

## Comparing experiments

An experiment that builds a search setup does not compute metrics itself. Each setup
writes a run, the ranked theses for every query, and `eval/score.py` scores it against
a versioned evaluation set described in [eval/README.md](../eval/README.md). Two results
are comparable when they were scored against the same version. An older setup is compared
by running its configuration again on the current version: experiment 03 does this for
experiment 01 as `01-baseline`.

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
