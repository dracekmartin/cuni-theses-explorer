# 0001: Languages and stack

Date: 2026-09-09. Status: accepted.

## Context

The system has two halves: a data and ML pipeline (embeddings, topic modeling,
retrieval) and a web application (API, interactive UI). The libraries the pipeline
needs (sentence-transformers, BERTopic, UMAP, evaluation tooling) exist only in
Python. There is one developer. The thesis is graded also on engineering quality,
and the system has to be easy to run (decision 0002).

## Decision

- Backend and pipeline: **Python 3.13**, API in **FastAPI**. One language for
  everything on the server, batch pipeline included.
- Frontend: **TypeScript** and **React**. The API publishes an OpenAPI specification
  and the frontend uses a TypeScript client generated from it, so the types on the
  boundary come from one source.
- Storage: **PostgreSQL** with the **pgvector** extension. Metadata, chunks, vectors,
  fulltext and caches sit in one transactional database; the schema layout is in the
  architecture document.

## Consequences

- ML libraries are called directly from application code. There is no separate ML
  service and no internal API to maintain.
- Python does not check types on its own, so type annotations are mandatory and
  checked with pyright (decision 0003).
- The project uses two languages. The seam between them is maintained by the client
  generator rather than by hand.
- There is one database to run, back up and understand. If vector search in Postgres
  stops being sufficient, a dedicated vector database can replace one schema behind
  the existing interfaces, and that change would get its own decision record.

## Alternatives considered

- **C#/.NET backend with a separate Python service for ML.** Strong language and
  tooling, but the server would consist of two runtimes with an internal API between
  them, each deployed and monitored separately. Too much overhead for one person.
- **TypeScript full stack with a Python ML service.** The same split, and JavaScript
  has no usable ecosystem for the pipeline itself.
- **A dedicated vector database (for example Qdrant) from the start.** Good hybrid
  search support, but it adds a second stateful service and separates vectors from
  metadata and transactions. The corpus we measured (about 120 thousand theses, at
  most tens of millions of chunks) is far below the sizes where pgvector runs into
  limits. Worth revisiting only with measurements in hand.
