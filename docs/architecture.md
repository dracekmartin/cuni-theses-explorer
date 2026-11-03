# Architecture

How the system is put together and why. Diagrams come from the C4 model in
[workspace.dsl](workspace.dsl), and [diagrams/render.sh](diagrams/render.sh) renders them
into [diagrams/](diagrams/). Choices between alternatives live in
[design decision records](decisions/). Renaming a component here means renaming it in
code and in the thesis text too.

Chapters marked *pending* are not written yet. Their draft, in Czech, is
`architektura-nastrel.md` in the
[diplomkaManagement](https://github.com/dracekmartin/diplomkaManagement) repo.

## 1. Goals and constraints

The system makes the theses of Charles University accessible in three ways, as set by the
[assignment](assignment.md): hybrid semantic and lexical search that works across
languages, an interactive map of the corpus with generated explanations of why two theses
are similar, and an AI overview that answers a question from cited theses. Who uses it
and for what is in the [use cases](use-cases.md).

Quality goals, in the order that decides a conflict:

1. Replaceable and comparable parts: embedding models, search strategies and whole
   search engines can be swapped and compared on a fixed evaluation set (assignment,
   UC11).
2. Simple for users: search and the user interface stay simple. The public interface
   knows only the default setup, and tools for maintainers are not linked from it.
3. Faithful to the source: what DSpace does not publish, the system neither finds nor
   shows. Errata, embargoes and withdrawn theses reach the index (UC10).
4. Reproducible: every result records the evaluation set, the setup, the model revision
   and the index build it came from, so it can be repeated.
5. Fast and affordable: results within a few seconds (UC1), on hardware the university
   can provide.
6. Operable by one person on a single serving node.

Constraints:

- One developer. The system is a prototype ready for deployment: it does not have to run
  in production, but it has to be shown that it could.
- The system uses only self-hosted open source components and academic services, no
  commercial APIs.
- The system indexes full text only where DSpace publishes it openly. Metadata of every
  record DSpace shows publicly is searchable too, as in DSpace.
- The serving node is not known yet. Heavy batch jobs (bulk embeddings, evaluation runs
  at full scale, builds of the topic map) run on the MFF HPC cluster, which schedules jobs
  with SLURM and offers GPU nodes. MetaCentrum, scheduled with PBS, is the alternative.
  Light batch work runs on the serving node.
- Languages and stack: Python and TypeScript ([0001](decisions/0001-languages-and-stack.md)),
  Docker Compose ([0002](decisions/0002-containerization.md)). The cluster has no Docker,
  so batch jobs there run the same images under Podman or Apptainer
  ([0005](decisions/0005-batch-jobs-on-the-faculty-cluster.md)).

## 2. Context

![System context](diagrams/context.svg)

| Who or what | Relation to the system |
| --- | --- |
| User (student, visitor, teacher) | searches theses, browses the topic map, reads AI overviews in a web browser |
| Operator | watches the outcome of synchronization runs with DSpace and steps in when one reports a problem |
| Maintainer | defines and compares search setups, runs evaluations |
| API client | scripts and other tools using the public API. An MCP adapter for AI assistants is a later idea, outside the current use cases |
| DSpace UK | source of thesis metadata, access status and texts: OAI-PMH in the xoai format and files over HTTPS. Its own search serves as one setup for comparison. DSpace 6.4, read only |
| e-INFRA CZ | academic OpenAI-compatible LLM API for overviews, explanations and relevance judgments in evaluation. For batch work such as relevance judgments, a self-hosted LLM on the faculty cluster can replace it |
| Batch compute | MFF HPC cluster (SLURM, GPU nodes) or MetaCentrum (PBS). The system's own heavy batch jobs run there: bulk embeddings, evaluation runs at full scale, builds of the topic map. Results come back as files |

## 3. Containers

![Containers overview](diagrams/containers.svg)

The containers fall into three groups. The batch tools write the database, and the API
reads it. File storage holds only what the batch tools bring in or work from. The overview
shows every container and everyone outside the system, but leaves out some relations
whose target already has another arrow. The three views below show every relation of
one part of the system.

Serving queries:

![Containers serving queries](diagrams/containers-serving.svg)

Batch work:

![Containers doing batch work](diagrams/containers-batch.svg)

Evaluation:

![Containers of the evaluation](diagrams/containers-evaluation.svg)

| Container | Responsibility | Technology |
| --- | --- | --- |
| Web UI | search, thesis detail, topic map and overview in the browser. Pages for maintainers and operators are not linked from the public part | TypeScript, React |
| Reverse proxy | HTTPS with the server certificate, static files of the web UI, limits on requests per IP address. Requests go on to the API as plain HTTP inside the server | nginx |
| API | public REST API with a version in the path (`/v1`). The search core, the overview and the explanations run inside it as a library. It sends the topic map as one response per map version. Limits for expensive endpoints and for parallel GPU and LLM work | Python, FastAPI |
| Model server | query embeddings, reranking and sparse weights for the API, the batch tools and the evaluation tool, on a GPU or on the CPU. By default it is our own service: it offers the in-process adapters over HTTP with the same endpoints as TEI. TEI or vLLM can take its place when throughput matters. On the notebook and in tests the models can run inside the program instead ([0004](decisions/0004-models-at-query-time.md)) | Python, FastAPI |
| Database | catalog, chunks, indexes, map data and caches | PostgreSQL with pgvector |
| File storage | results of cluster jobs (vectors, map builds) with their manifests, kept for a repeated import, and PDFs for own text extraction. Only the batch tools use it | file system |
| Batch tools | synchronization with DSpace, chunking, index builds and imports, map builds. Cron starts them on the serving node, heavy jobs run on the cluster (SLURM) or MetaCentrum (PBS) ([0005](decisions/0005-batch-jobs-on-the-faculty-cluster.md)) | Python |
| Evaluation tool | runs setups over an evaluation set on the notebook or as a job on the cluster, writes TREC runs and scores them | Python |

Each schema of the database has one writer:

| Schema | Writer | Contents |
| --- | --- | --- |
| `catalog` | batch tools (synchronization, text extraction) | theses, versions, metadata, extracted texts, access status, synchronization runs |
| `chunks_<chunking>` | batch tools (chunking) | the chunks of one chunking, shared by every index build that uses it |
| `index_<build>` | batch tools (index builds, imports, plugins through their index storage) | one schema per index build: its manifest, vectors and their index, lexical postings or the data of a plugin |
| `artifacts` | batch tools (map builds) | neighbor graph, versions of the topic map with clusters and labels |
| `cache` | API | search results for a few minutes, overviews, explanations |

The topic map lives only in `artifacts`. The API sends the map of one version to the
browser as one response. A map version never changes, so browsers may cache the response
for a long time.
Cached overviews and explanations record the versions of the theses they cite. The API
drops an entry when one of those theses changed or was withdrawn, both when it reads the
entry and in a periodic cleanup, so the cache keeps a single writer.

### Code packages

The Python code is a uv workspace. A component gets a package of its own only when it has
heavy dependencies such as torch, runs as a program of its own, or is a plugin that shows
replaceability. Other components are folders inside a package. Where the packages live in
the repository and how the workspace is set up is decided in the engineering records
(numbers from 0010).

| Package | Contents | May depend on |
| --- | --- | --- |
| `explorer` | the core library: domain model, catalog and harvest, texts and chunks, indexes and their PostgreSQL backends, the search core, model interfaces and HTTP adapters, overview, explanations, reading map artifacts | no other package of the workspace |
| `explorer_models_local` | in-process model adapters with torch, and the model server that offers them over HTTP | `explorer` |
| `explorer_map` | builds of thesis vectors, the neighbor graph and the topic map (umap-learn, hdbscan, faiss) | `explorer` |
| `explorer_api` | the API program | `explorer`, and `explorer_models_local` only as an optional extra |
| `explorer_batch` | the batch tools | `explorer`, and `explorer_models_local` and `explorer_map` only as optional extras |
| `explorer_eval` | the evaluation tool | `explorer`, and `explorer_models_local` only as an optional extra |
| `explorer_dspace` | plugin: the whole search delegated to the search of DSpace | `explorer` |
| `explorer_sparse` | plugin: learned sparse weights of BGE-M3 as a candidate source with its own index | `explorer` |

The core never imports torch. Programs reach the in-process adapters and the plugins only
through the registry. The registry finds them by Python entry points, a standard way for
an installed package to announce its classes, so nothing depends on a plugin. Which
plugins a program has is a matter of installation: the development environment installs
all of them, a deployment image lists the ones its setups need. Plugins may import only
the public module `explorer.plugin`, and `explorer.testing` in their tests. The web UI is a separate TypeScript application, outside the workspace, with
an API client generated from the OpenAPI specification.

## 4. Components

*Pending:* search core in detail (searcher interface, step tree, platform wrapper, setups
and registry, language handling), indexing, topic map and overview at a high level.

## 5. Runtime views

*Pending:* answering a query, indexing a new thesis version, a thesis withdrawn from
DSpace, an evaluation run, an overview, an explanation of a neighbor edge.

## 6. Deployment

*Pending:* development notebook, batch compute, serving node, and the hardware a full
index needs.

## 7. Crosscutting concepts

*Pending:* plugins and registry, index manifests and snapshots, visibility guard, query
safety check, protection against overload, language handling.

## 8. Variability

*Pending:* what can be replaced, through which interface, at which time (configuration,
deployment, code) and at what cost.

## 9. Quality scenarios

*Pending:* change scenarios in six parts (source, stimulus, artifact, environment,
response, response measure), carried out and measured in the thesis.

## 10. Decisions

| Record | Decision |
| --- | --- |
| [0001](decisions/0001-languages-and-stack.md) | Python 3.13 and FastAPI, TypeScript and React, PostgreSQL with pgvector |
| [0002](decisions/0002-containerization.md) | Docker Compose is how the system runs |
| [0003](decisions/0003-engineering-quality.md) | engineering quality and its enforcement |
| [0004](decisions/0004-models-at-query-time.md) | models behind interfaces, adapters in process or over HTTP, one model server for all programs in deployment |
| [0005](decisions/0005-batch-jobs-on-the-faculty-cluster.md) | heavy batch jobs on the faculty cluster, results come back as files |

Planned records (numbers up to 0009 are reserved for architecture decisions): the search
core with replaceable searchers and steps, language handling, storage at full scale.

## 11. Glossary

These are working names, the final naming is still open.

| Term | Meaning |
| --- | --- |
| Thesis | one thesis record in DSpace: metadata, files, extracted text, document version |
| Catalog | the system's record of all theses: versions, metadata, files, extracted texts and access status |
| Chunk | a searchable piece of a thesis: a passage of the body, or a metadata chunk with the title, keywords and abstract in one language, as in the experiments. Text unit is the working name for this general notion |
| Searcher | the interface of a whole search: query, filters and k in, ranked theses out |
| Setup | a named configuration of a searcher. For the default searcher it is a tree of steps |
| Step | one node of that tree: candidate source, fusion, aggregation, passage selection, reranking, filter or router |
| Search strategy | the term of the assignment and of earlier documents for how ranking sources combine. Here it is the step tree of a setup |
| Query analyzer | turns the query text into a query with language, lemmas and embeddings |
| Index spec, index build | what an index is built from (a chunking, an encoder or analyzer) and one built instance, recorded with an index manifest (model, revision, snapshot, counts) |
| Registry | the list of named searchers, steps, model adapters and plugins that a setup can refer to |
| Plugin | a separate package that adds a searcher, a step or an index to the registry without changes to the core |
| Index storage | the place a plugin gets for its own index: a schema in PostgreSQL or a folder of files |
| Snapshot | the state of the catalog after one synchronization run |
| SyncRun | one scheduled synchronization pass with its recorded outcome |
| NeighborGraph | precomputed top-k similarity edges between theses |
| TopicMap | precomputed, versioned 2D layout of the corpus with labeled clusters |
| Explanation | generated text describing what two neighboring theses share, always cached |
| Overview | verified generated answer to a question, grounded in cited theses |
| Gate | a small replaceable check that lets an overview through or stops it with a reason |
| EmbeddingProvider, SparseEncoder, Reranker, LLMProvider, Verifier | small interfaces hiding which model runs where |

### Abbreviations and tools

| Abbreviation | Meaning |
| --- | --- |
| BGE-M3 | the multilingual embedding model of BAAI that the experiments found best. It gives one dense vector per passage and also weights of its tokens |
| C4 | a way of drawing software architecture in four levels of zoom: context, containers, components and code |
| CLI | a program run from the command line |
| HNSW | the graph index that pgvector uses to find the nearest vectors without comparing a query with every vector |
| HPC | high-performance computing, here the MFF cluster for batch jobs |
| LLM | large language model, used for the overview, the explanations and relevance judgments |
| MCP | Model Context Protocol, a standard way for AI assistants to call tools such as a search API |
| MFF | the Faculty of Mathematics and Physics of Charles University |
| OAI-PMH | the standard protocol through which repositories hand out their metadata page by page. xoai is the metadata format DSpace offers in it |
| OpenAPI | a machine-readable description of a REST API. The web UI generates its API client from it |
| PBS | the job scheduler of MetaCentrum. A job is a script with its resource needs, submitted with `qsub` |
| pgvector | the PostgreSQL extension for vectors and nearest-neighbor search |
| SLURM | the job scheduler of the MFF cluster, the same role as PBS. Jobs are submitted with `sbatch` |
| TEI, vLLM | servers from other projects that run models behind an HTTP API: Text Embeddings Inference from Hugging Face for embeddings and rerankers, vLLM mainly for LLMs. Either can replace our own model server |
| TREC | Text REtrieval Conference, a long series of evaluation campaigns for search. Its formats are used here: a TREC run lists the ranked results of each query, qrels hold the relevance judgments |
| UC | a use case from [use-cases.md](use-cases.md), for example UC1 |
| uv | the Python tool that manages the packages and dependencies of the workspace |
