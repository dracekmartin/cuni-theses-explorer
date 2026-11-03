# 0006: Search core with replaceable searchers

Date: 2026-11-03. Status: accepted.

## Context

The assignment asks for an architecture in which components, above all embedding models
and search strategies, can be replaced and compared, and for a comparison with the search
of DSpace. UC11 accepts a model swap only when it needs no code change and two
configurations can be queried side by side. Adding a model that does the whole search,
such as another engine or a model with its own index, has to be a simple change.

Experiment 05 copied `run.py` from experiment 03. Its function `answer()` picks the
branches through a chain of conditions in a fixed order
(`experiments/05-search-v1/run.py:145-262`). The setup files have one table per phase and
cannot hold a tree. Some of their keys are never read (`[chunking].max_chars`,
`[lexical]`, `[sparse]`), yet `run.py:96-110` copies them into the results, so a result
can claim a setting that was not used. DSpace needed a script of its own with a copy of
the code that writes results (`dspace_run.py:192-217`). The contract of the evaluation,
a TREC run per setup scored by `eval/score.py`, let DSpace be scored like the setups.

## Decision

Parts are replaced on two levels: a whole search behind one interface, the searcher, and
the steps inside the default searcher, PipelineSearcher.

- **Searcher.** It gets an analyzed query, filters and a limit, and has to return only
  ranked theses with id, version and score. Chunks and a trace are optional. It reports
  its capabilities: filters, chunks, languages and the index it needs. The API, the
  evaluation tool and the overview call nothing else. A searcher with its own index has to
  remove a withdrawn thesis from it too.
- **Platform wrapper.** Every searcher runs inside it. It runs the query safety check,
  which no setup can switch off, and the query analyzer once, then the searcher. It asks a
  searcher without filters for more results and drops those that do not match, runs
  passage selection when a user asks why a thesis was found, records the trace and keeps
  results in a cache for a few minutes. The visibility guard checks every result against
  the current catalog, a cached one too.
- **PipelineSearcher.** It composes a search from a tree of steps of a few kinds:
  candidate source, fusion, aggregation, passage selection, reranking, filter, router.
  Every step gets the analyzed query, takes ranked lists of candidates and returns one. A
  candidate is a chunk or a thesis, so a step fits wherever its unit fits. Another
  searcher can be a leaf, so our reranker can rescore the results of DSpace, with passage
  selection before it.
- **Setups.** Each setup is one TOML file in the repository. The tree is a flat list of
  named steps, and each step names the steps it reads. An unknown key is an error, so that
  a result never claims a setting the code did not use. `setups check` also rejects an
  unknown step type, a reference to a missing step, a cycle, a step that gets chunks where
  it needs theses or the other way round, an index without a finished build and a query
  encoder that does not match the index manifest. A setup with a reported result is never
  edited, a change makes a new file. The UI has no editor for setups: a setup goes through
  review in git like code, and results refer to its file. The default setup is one line of
  the deployment configuration, and a fallback setup without the reranker serves a node
  without a GPU.
- **Fingerprint.** A hash of the normalized setup and the ids of its index builds with
  their snapshots. The results files of TREC runs and the caches of results and overviews
  record it, so a file changed under the same name never passes for the old one.
- **Registry.** It maps names with a version, such as `fuse.rrf.v1`, to searchers, steps
  and model adapters. A plugin announces its classes through an entry point and imports
  from `explorer` only `explorer.plugin`. Setups refer to names, never to import paths.
- **Evaluation.** The evaluation tool runs the same library as the API and calls the
  platform wrapper directly. From the trace it measures each step: how many of the theses
  sought are in the top 50 before the reranker, and how long each step takes. Setups
  compared together run their shared steps only once.

## Consequences

- A whole search is one searcher class in a plugin, optionally with an index builder, and
  the API, the web UI and the evaluation tool stay unchanged. `explorer_dspace` delegates
  the search to DSpace, `explorer_sparse` adds a candidate source with its own index, and
  Qwen3-Embedding-4B needs only configuration and a new index build.
- A searcher without filters has to return more results than asked for. How many more is
  not decided.
- Each change of a setup with a result adds a file. A new default setup, one line of the
  deployment configuration, needs a restart of the API.
- The API serves only setups whose index builds and models are deployed, and each model
  takes memory (decision 0004: BGE-M3 and the reranker about 2.3 GB each in full
  precision). Only maintainers choose another setup or ask for a trace, behind a login.
- Everything a plugin needs has to be in `explorer.plugin`, and a change there reaches
  every plugin. Decision 0011 checks the imports.
- Experiment 06 is postponed and will run as setups in the new core. The default fusion,
  the size of chunks and the place of the reranker stay open until then.

## Alternatives considered

- **Searchers that must also filter, return chunks or index the changes of the catalog.**
  DSpace returns no chunks and builds no index from our catalog, so it would not qualify.
- **Fixed phases** (find candidates, fuse, rerank, aggregate). They cover all that the
  experiments tried and are easier to explain than a tree, but cannot rerank the results
  of DSpace, fuse two whole setups or route a query by its type. Elasticsearch, Qdrant and
  PyTerrier compose a search as a tree.
- **Setups as Python functions.** More flexible, but a function cannot be stored next to
  a result and compared, and UC11 asks for a model swap without a code change.
- **YAML.** A nested tree is easier to write in YAML than as the flat list of TOML. TOML
  needs no extra library in Python, and the experiments already use it.
- **An external engine for the whole search,** such as OpenSearch beside PostgreSQL. It
  has a Czech analyzer (a light stemmer) but no Slovak one, and it is a second system with
  a JVM and data to keep in sync. It can still join later as one searcher in a plugin.
