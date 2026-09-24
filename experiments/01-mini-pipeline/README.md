# Experiment 01: mini pipeline

Does a first end-to-end pipeline work on real theses, and how do the DSpace TEXT bundle,
lexical search and semantic search behave on them?

Done, 2026-09-09. Corpus: own sample, the first 50 theses with a PDF in the thesis
collections of MFF and FF (100 theses). Queries: four ad hoc ones. Builds on: none.

| Stage | Setting |
| --- | --- |
| Harvest | DSpace REST API, PDF and TEXT bundle of each thesis |
| Text extraction | pypdf |
| Chunking | up to 1000 characters on sentence boundaries |
| Embedding | `intfloat/multilingual-e5-small` with `query:` and `passage:` prefixes |
| Lexical branch | BM25 over simplemma lemmas, Czech first, English as the fallback |
| Search strategy | top 200 chunks of each branch, reciprocal rank fusion with k = 60 |
| Aggregation to theses | a thesis ranks by its best chunk |

A DSpace item carries several PDFs (body, abstracts, reviews, attachments). The body is
the PDF whose paired TEXT bitstream is largest; picking the largest PDF chose a scanned
attachment twice. Scans occur in all years, up to 2025 (5 of 103 theses in the first
run). The TEXT bundle matches our pypdf extraction (median character ratio 1.01) at
a fortieth of the download volume, 17 MB against 675 MB for 100 theses, so later
experiments harvest it directly.

Embedding the 17,441 chunks took 140 s on the laptop GPU against about two hours on the
CPU, so indexing the whole university needs a GPU. DSpace had an outage between the two
runs (listings answered 504); harvesting has to retry with backoff, resume after an
interruption and wait out outages.

Semantic search found topics that BM25 missed: "psychologie dlouhodobých partnerských
vztahů" returned a thesis on long-distance relationships, a related topic with almost no
shared words. Cross-lingual search was weak: "strategy videogame" put *Artificial
Intelligence for a Castle Conquest Simulation Game* first, "strategická videohra" only
sixth. Four queries show behavior, not quality; experiment 03 measures this setup on
eval/v0 as `01-baseline`.

Reproduce: `python experiments/01-mini-pipeline/harvest.py`, then `extract.py`,
`build_index.py` and `search.py "strategická videohra"` in the same directory.
