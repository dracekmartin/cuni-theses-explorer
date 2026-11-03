# 0004: Models at query time

Date: 2026-11-02. Status: accepted. Supersedes the points of
[0001](0001-languages-and-stack.md) that ML libraries are called directly from application
code and that there is no separate ML service.

## Context

Every query needs models: an embedding of the query, often a cross-encoder that reranks
the candidates, and for the overview an LLM and a verifier. Decision 0001 calls ML
libraries directly from the application code. That works on the notebook, but on a server
each API worker would hold its own copy of the models (BGE-M3 and the reranker take about
2.3 GB each in full precision, about half in float16) and would need its own access to the
GPU. Whether the serving node has a GPU at all is not known yet.

HTTP servers for models exist (vLLM, Hugging Face TEI, Infinity). They offer
OpenAI-compatible endpoints for embeddings and LLMs, and endpoints of their own for
reranking and sparse weights. e-INFRA CZ offers an OpenAI-compatible API for LLMs. The
search core must not depend on torch, so that it can be tested and installed without it.
Query vectors and passage vectors must come from the same model revision, and e-INFRA
replaces its models without notice.

## Decision

- The core library `explorer` defines the model interfaces: EmbeddingProvider (one vector
  per text), SparseEncoder (token weights), Reranker, LLMProvider and Verifier. It never
  imports torch.
- Each interface has adapters of two kinds. In-process adapters run the model with torch
  and live in the package `explorer_models_local`. HTTP adapters call a model server and
  live in `explorer`: OpenAI-compatible endpoints for embeddings and LLMs, the endpoints of
  TEI for reranking and sparse weights.
- Configuration selects the adapter by its registered name. The registry finds adapters
  through entry points, so the API and the evaluation tool never import
  `explorer_models_local` directly.
- In deployment the model server is a container of its own. The API, the batch tools and
  the evaluation tool call it, so one copy of each model serves them all and the image of
  the API needs no torch. The in-process adapters stay for the notebook, tests and
  evaluation on the notebook.
- By default the model server is our own service: the command `serve` of
  `explorer_models_local` offers the in-process adapters over HTTP with the same endpoints
  as TEI. It serves every model the in-process adapters can run, the sparse weights of
  BGE-M3 included, and gives the same results. TEI can take its place with the same
  adapters when throughput matters. Another server, such as vLLM, needs adapters for its
  own endpoints.
- The manifest of an index build records the model and its revision. The configuration of
  an adapter records the revision it serves, because a server may not report it. The API
  refuses to serve a setup whose query encoder does not match the manifest.
- Corpus embeddings come only from models whose weights the project holds. LLMs may come
  from e-INFRA or from a self-hosted vLLM with a pinned model.

## Consequences

- The search core is tested without torch, with a fake deterministic encoder. Tests of the
  in-process adapters run separately, marked as needing a model or a GPU.
- A serving node without a GPU runs the model server on the CPU, or the API calls a model
  server on another machine if one is available. The reranker is slower on a CPU,
  and its cost there is still to be measured.
- One GPU serves both the API and batch work, because both talk to the same model server.
- Our model server needs its own batching of parallel requests, a queue and a health
  check. TEI and vLLM have them ready and run faster on a GPU, which matters for bulk
  embeddings and heavy traffic.
- A model swap on e-INFRA cannot make query vectors incompatible with the index, because
  corpus embeddings never depend on it. An LLM, reranker or verifier taken from e-INFRA can
  still change its answers, so an evaluation records the model name and date, and runs that
  must be repeatable use a self-hosted model with a pinned version.
- A plugin that needs a SparseEncoder depends only on `explorer` as a package. At run time
  it needs an adapter that offers sparse weights: the in-process one or our model server.
  Whether TEI or vLLM offer the sparse weights of BGE-M3 is not verified.

## Alternatives considered

- **Only in-process models, as in 0001.** Simplest on the notebook, but every API worker
  loads its own models, and the API needs a GPU itself.
- **TEI or vLLM as the only model server.** Batching ready and faster on a GPU, but the
  sparse weights of BGE-M3 are not verified in either, and their results can differ
  slightly from the in-process adapters, because they run the model with other code.
- **Only an HTTP model server.** One way to run models everywhere, but tests and the
  notebook would need a running server for every change.
- **Corpus embeddings through e-INFRA.** No GPU of our own needed, but the model can change
  under the index, and comparing models through their API needs prior consultation with
  the provider.
