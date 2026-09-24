# Evaluation data

Versioned data for measuring search quality: a fixed corpus, queries, and relevance
judgments, plus the scripts that score runs against them. Every experiment is scored
against the same files by the same code, so results of different experiments can be
compared. How a version was built is described in `experiments/02-eval-set/`.

The data here are handles, queries and labels only. Thesis texts and harvested metadata
stay in `data/`, which is not versioned.

## Versions

- Each version has its own directory: `v1/`, `v2/`, and so on.
- A version is frozen once a result has been reported against it. A changed corpus, new
  queries or new judgments make a new version. Runs are kept, so older search setups can
  be scored against a newer version again.
- Every result names the version it was scored against.

| Version | State | Contents |
| --- | --- | --- |
| v1 | in preparation | about 1,000 theses sampled by department; known-item queries (layer 1); a pilot of judged topics (layer 2) |

## Files of a version

### corpus.txt

One handle per line, sorted, for example `20.500.11956/184050`. The corpus is the whole
search space: runs rank these theses and nothing else.

### queries.jsonl

One JSON object per line.

| Field | Meaning |
| --- | --- |
| `id` | unique query id, `<group>-<lang>` |
| `group` | the same query in Czech and in English; for `title` it pairs the original and the translated title |
| `lang` | language of the query: `cs` or `en` for generated queries; a `title` query carries the language of the title (`sk`, `de`, ...) |
| `type` | layer 1 (known-item): `title`, `about-short`, `about-sentence`, `detail`; layer 2: `topic` |
| `text` | the query as a user would type it |
| `target` | layer 1: handle of the thesis the query was made from, otherwise `null` |
| `target_lang` | layer 1: language of that thesis (`cs`, `en`, `sk`, ...), otherwise `null` |
| `narrative` | layer 2: what counts as relevant, written for the judges, otherwise `null` |

Group ids are `ki-NNNN-<type>` for known-item queries (NNNN numbers the target thesis) and
`topic-NN` for topics.

### qrels.txt

TREC qrels, one judgment per line, fields separated by spaces:

```text
query_id 0 handle grade
```

| Grade | Meaning |
| --- | --- |
| 2 | relevant: the thesis is about the topic; for a known-item query, its target |
| 1 | partially relevant: the thesis touches the topic or covers a part of it |
| 0 | judged and not relevant |

A known-item query has exactly one line, its target with grade 2. A topic has one line per
judged thesis, grade 0 included, so that an unjudged result can be told apart from
a judged non-relevant one.

## Runs

A run is the output of one search setup for every query of a version, in TREC run format,
one line per returned thesis:

```text
query_id Q0 handle rank score setup_name
```

- Lines rank theses, not chunks. Aggregation to theses happens before writing.
- At most 100 theses per query, ranks start at 1. A query without results has no lines.
- The scorer orders results by `rank`. The `score` column is kept for inspection only.
- Runs live in `data/runs/<experiment>/<setup>.run`. They are not versioned, because the
  experiment can reproduce them.

## Metrics

`score.py` computes them the same way for every run.

| Layer | Metrics |
| --- | --- |
| known-item (`title`, `about-*`, `detail`) | MRR@10, Success@1, Success@10, Success@100; split by type and by query language against thesis language |
| topic | nDCG@10 with grades as gains; P@10 and Recall@100 counting grade 1 and 2 as relevant; judged@10, the share of the top 10 that has a judgment |
| consistency | rank-biased overlap (p = 0.9) between the two language versions of each group, averaged per type |

Differences between two runs are tested with a paired randomization test over queries,
and results mark those with p < 0.05.

## Results files

An experiment keeps one `results/<setup>.json` per search setup. The experiment writes
the run path, the pipeline and the cost; `score.py` adds `eval_version` and `metrics`.

```json
{
  "experiment": "03-search-setups",
  "setup": "bge-m3-hybrid",
  "run": "data/runs/03-search-setups/bge-m3-hybrid.run",
  "pipeline": {
    "harvest": {"source": "DSpace REST", "corpus": "eval/v1"},
    "text_extraction": {"method": "DSpace TEXT bundle"},
    "chunking": {"max_chars": 1000, "split": "sentence", "overlap": 0},
    "embedding": {"model": "BAAI/bge-m3", "query_prompt": null, "passage_prompt": null},
    "lexical": {"method": "BM25Okapi", "lemmatizer": "simplemma cs, en"},
    "strategy": {"fusion": "rrf", "k": 60, "chunk_pool": 200},
    "reranking": null,
    "aggregation": {"method": "best chunk"}
  },
  "cost": {
    "hardware": "laptop, RTX 4050 6 GB",
    "index_seconds": 0,
    "chunks": 0,
    "index_bytes": 0,
    "query_ms_median": 0
  },
  "eval_version": "v1",
  "metrics": {}
}
```

The pipeline keys are the stages of the experiment card in `experiments/TEMPLATE.md`.
A stage the setup does not use is `null`.

## Usage

Planned interface of the scripts, which are in preparation:

```sh
python eval/score.py --version v1 --results experiments/03-search-setups/results/bge-m3-hybrid.json
python eval/compare.py --version v1 --baseline 01-baseline experiments/03-search-setups/results/*.json
```

`score.py` reads the run named in the results file and writes the metrics into it.
`compare.py` prints one row per results file, with significance against the baseline.
