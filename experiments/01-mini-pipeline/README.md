# Experiment 01: mini pipeline

A first end-to-end taste of the system on about 100 theses: harvest a sample from
DSpace, extract text, build a small search index, and try queries against it. The goal
is not the code but the findings: how the data behaves, whether the DSpace TEXT bundle
is usable, and how semantic and lexical search differ on real Czech and English queries.
Findings feed the open questions in [docs/architecture.md](../../docs/architecture.md).

## Setup

Reuse the repository virtualenv and install the experiment dependencies:

```sh
.venv/Scripts/pip install -r experiments/01-mini-pipeline/requirements.txt
```

## Scripts

Run from the repository root. All data lands in `data/01-mini-pipeline/` (git-ignored).

### harvest.py

```sh
python experiments/01-mini-pipeline/harvest.py --per-faculty 50
```

Walks the "Kvalifikační práce" collection of each faculty (default: MFF and FF) through
the DSpace REST API and stores, per thesis: the PDF (`pdf/`), the text DSpace itself
extracted from the PDF (`dspace-text/`), and a metadata line in `manifest.jsonl`.
One request at a time with a fixed delay; safe to interrupt and re-run, already
harvested theses are skipped.

### extract.py

```sh
python experiments/01-mini-pipeline/extract.py [--force]
```

Extracts plain text from the harvested PDFs with pypdf into `extracted/` and writes
per-thesis stats (pages, empty pages, characters, ratio against the DSpace TEXT bundle)
into `extracted/extraction-stats.jsonl`. Already extracted theses are skipped.

### build_index.py

```sh
python experiments/01-mini-pipeline/build_index.py [--model intfloat/multilingual-e5-small]
```

Splits extracted texts into chunks of about 1000 characters on sentence boundaries,
embeds them (multilingual model, `passage:` prefix, normalized vectors, GPU when
available) and lemmatizes them for BM25 (simplemma, Czech first, English fallback).
Writes `index/`: `chunks.jsonl`, `embeddings.npy`, `tokens.jsonl`, `meta.json`.

### search.py

```sh
python experiments/01-mini-pipeline/search.py "strategická videohra" [--top 5]
```

Prints three rankings for the query: lexical (BM25 over lemmatized tokens), semantic
(cosine over chunk embeddings, `query:` prefix), and their reciprocal rank fusion.
Chunks are ranked first and aggregate to theses by their best chunk; each result shows
faculty, year, title and a snippet of the best matching chunk.

## Findings

To be filled after the first run.
