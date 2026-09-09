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

September 9, 2026. Two runs: the first (103 theses) revealed a bug in picking the
thesis PDF, so after the fix everything was harvested again from scratch (100 theses,
50 MFF + 50 FF). Numbers below come from the clean second run unless said otherwise.
Model: `intfloat/multilingual-e5-small`.

**A DSpace item is not one file.** A thesis item carries several PDFs: the body,
abstracts, reviews, attachments. Picking "the largest PDF" chose a scanned one-page
attachment over the thesis body for two theses in the first run. The working rule is
to pick the PDF whose paired TEXT bitstream (`<pdf>.txt`) is largest, the body being
the file with the most text.

**Scans exist across all years.** The first run caught 5 image-only or partly scanned
theses out of 103, with defense years 2008, 2012, 2013, 2017 and 2025. The guarantee
of a text layer has exceptions, and they are not limited to old theses. The clean
second run had none in its 100-thesis sample, so the rate is a few percent, sample
dependent.

**Data.** 100 theses take 675 MB in PDF and 17 MB in the DSpace TEXT bundle, a 40x
difference. Median thesis: about 80 pages, 150 thousand characters. 0.7 % of pages
have no extractable text (title pages, figures).

**Extraction (open question 3).** With the paired pick, our pypdf extraction and the
DSpace TEXT bundle are practically identical for all 100 theses (median character
ratio 1.01, none below 0.7). Implication: the TEXT bundle looks trustworthy enough to
harvest directly, cutting the download volume by an order of magnitude; scanned theses
even favor it, because DSpace ran OCR we do not have. Verify on a bigger sample before
committing to it.

**Hardware (open question 4).** Embedding 17 441 chunks took 140 seconds on a laptop
GPU (RTX 4050); the CPU attempt was on course for about two hours, a factor of roughly
50. Scaled to the full corpus of 120+ thousand theses, CPU embedding is out of the
question; a GPU or the e-INFRA API is required for indexing.

**The repository has bad days.** Between the two runs DSpace degraded for a while
(status endpoint took 8 to 14 s, listing endpoints returned 504) and recovered on its
own. The pipeline must treat harvesting as an unreliable, long-running conversation:
retry with backoff, resume from a manifest, and wait out outages rather than hammer
a struggling server. All three earned their place on day one.

**Queries.** Behavior matched the motivation of the thesis (identical in both runs):

- "strategy videogame" (EN): the semantic branch put *Artificial Intelligence for
  a Castle Conquest Simulation Game* first.
- "strategická videohra" (CZ): the same English thesis appeared only sixth in the
  semantic ranking. Cross-lingual retrieval works but weakly with this small model;
  this is the concrete reason to compare larger multilingual models (open question in
  docs/architecture.md, embedding model comparison).
- "psychologie dlouhodobých partnerských vztahů" (FF): the semantic branch put
  *Psychologické aspekty vztahů na dálku* first, a pure paraphrase match with almost
  no word overlap; BM25 found only loose lexical matches.
- "podmíněné větvení v C#": the target thesis is not in the sample, and the system did
  the right thing, returning the nearest available works (C++ introspection, compiler
  internals) instead of nothing.

**Smaller lessons.** The Windows console needs UTF-8 forced before printing Czech
titles. API read timeouts belong at 120 s, not 60; a struggling DSpace still answers,
just slowly.
