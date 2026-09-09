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

Other scripts (extract, index, search) arrive in the next commits.

## Findings

To be filled after the first run.
