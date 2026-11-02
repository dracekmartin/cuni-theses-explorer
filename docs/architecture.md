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
- The serving node is not known yet. The system's batch jobs (bulk embeddings, index
  builds, evaluation runs) run on the MFF HPC cluster, which schedules jobs with SLURM and
  offers GPU nodes. MetaCentrum, scheduled with PBS, is the alternative.
- Languages and stack: Python and TypeScript ([0001](decisions/0001-languages-and-stack.md)),
  Docker Compose ([0002](decisions/0002-containerization.md)). The cluster has no Docker,
  so batch jobs there will run the same images under Podman or Apptainer. That changes
  0002 and waits for its own record (chapter 10).

## 2. Context

![System context](diagrams/context.svg)

| Who or what | Relation to the system |
| --- | --- |
| User (student, visitor, teacher) | searches theses, browses the topic map, reads AI overviews in a web browser |
| Operator | watches the outcome of synchronization runs with DSpace and steps in when one reports a problem |
| Maintainer | defines and compares search setups, runs evaluations |
| API client | scripts and other tools using the public API. An MCP adapter for AI assistants is a later idea, outside the current use cases |
| DSpace UK | source of thesis metadata, access status and texts: OAI-PMH in the xoai format and files over HTTPS. DSpace 6.4, read only |
| e-INFRA CZ | academic OpenAI-compatible LLM API for overviews, explanations and relevance judgments in evaluation. For batch work such as relevance judgments, a self-hosted LLM on the faculty cluster can replace it |
| Batch compute | MFF HPC cluster (SLURM, GPU nodes) or MetaCentrum (PBS). The system's own batch jobs run there: bulk embeddings, index builds, evaluation runs. Results come back as files |

## 3. Containers

*Pending:* web UI, reverse proxy, API with the search core as a library inside it, model
server (needs a change of 0001, chapter 10), database with one writer per schema, batch
scheduler, batch jobs (they run on the cluster, chapter 6), evaluation tool.

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

Planned records (numbers 0004 to 0009 are reserved for architecture decisions):

- models at query time behind adapters, in process or as a separate model server. It
  changes the point of 0001 that there is no separate ML service.
- batch jobs on the faculty cluster run the same images under Podman or Apptainer. It
  changes 0002, which runs batch steps as compose commands.
- the search core with replaceable searchers and steps, language handling, storage at full
  scale.

## 11. Glossary

These are working names, the final naming is still open.

| Term | Meaning |
| --- | --- |
| Thesis | one thesis record in DSpace: metadata, files, extracted text, document version |
| Catalog | the system's record of all theses: versions, metadata, files and access status |
| Chunk | a searchable piece of a thesis: a passage of the body, or a metadata chunk with the title, keywords and abstract in one language, as in the experiments. Text unit is the working name for this general notion |
| Searcher | the interface of a whole search: query, filters and k in, ranked theses out |
| Setup | a named configuration of a searcher. For the default searcher it is a tree of steps |
| Step | one node of that tree: candidate source, fusion, aggregation, passage selection, reranking, filter or router |
| Search strategy | the term of the assignment and of earlier documents for how ranking sources combine. Here it is the step tree of a setup |
| Query analyzer | turns the query text into a query with language, lemmas and embeddings |
| Index spec, index build | what an index is built from (chunking, encoder or analyzer) and one built instance, recorded with an index manifest (model, revision, snapshot, counts) |
| Snapshot | the state of the catalog after one synchronization run |
| SyncRun | one scheduled synchronization pass with its recorded outcome |
| NeighborGraph | precomputed top-k similarity edges between theses |
| TopicMap | precomputed, versioned 2D layout of the corpus with labeled clusters |
| Explanation | generated text describing what two neighboring theses share, always cached |
| Overview | verified generated answer to a question, grounded in cited theses |
| Gate | a small replaceable check that lets an overview through or stops it with a reason |
| EmbeddingProvider, Reranker, LLMProvider, Verifier | small interfaces hiding which model runs where |
