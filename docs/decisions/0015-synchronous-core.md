# 0015: Synchronous core

Date: 2026-11-16. Status: accepted.

## Context

The search runs several candidate sources in parallel (architecture, section 5.1), the
overview calls an LLM whose provider allows at most 4 parallel requests, and the batch
tools and the evaluation call the same code without a server. Python offers threads or
asyncio for such work. An `async` function can be called only from another `async`
function, so the choice spreads through every chain of calls.

## Decision

- The code in `libs/` and `apps/` is synchronous. `Searcher.search`, `Step.run`, the model
  adapters and the endpoints of the API are plain functions. FastAPI runs such endpoints
  in its own pool of threads.
- The only `async` code is the glue of the web framework in `explorer-api`: its lifespan
  and its middleware, which Starlette expects as `async`. They do no work of the core.
- A boundary module is a module that talks to something outside the process: the
  database, an HTTP service or the file system. The model adapters, the storage of the
  catalog, of index builds and of caches, the readers of configuration and manifests and
  the writers of runs and results are boundary modules. Only they do input and output.
  The rest of the core works on data it has been given.
- Parallel work runs in thread pools, and each pool belongs to one object that also sets
  its size: the searcher for its candidate sources, a batch command for its independent
  units of work. Nothing else starts threads.
- The database is reached through a pool of connections (`psycopg_pool`). A thread holds
  one connection at a time, because the queries of one connection run one after another
  and share its transaction.
- A thread of a request cannot be stopped from outside. Every timeout therefore lives in
  a boundary module: the timeout of an HTTP client, `statement_timeout` in PostgreSQL.
- The LLM adapter keeps its parallel calls within a limit with a bounded wait. A call that
  waits longer than its timeout raises `Unavailable` (decision 0014). The limit holds
  within one process, so the deployment configuration sets it for each program so that
  the programs using one key stay within the limit of the provider together.
- The model server of decision 0004 collects parallel requests in a queue, from which one
  worker thread forms the batches for the model.

## Consequences

- A replaceable part of the core, such as a searcher or a step, is a plain class with
  plain methods.
- If the API ever has to hold many slow connections at once, the interface gets an
  `asearch` next to `search`, which by default runs `search` in a thread. Existing
  searchers keep working. The endpoint of the overview, which holds a connection longest
  while the LLM writes, can become asynchronous on its own and run the synchronous core in
  threads.
- Because parallel work and input and output each sit in a known kind of place, a later
  move to asyncio changes those places, not the logic of the core.
- Every request of the API that waits, for example for the LLM, holds a thread of the
  pool of FastAPI. The limits of the API for expensive endpoints (architecture, section
  7.6) have to stay below the size of that pool.

## Alternatives considered

- **An asynchronous core.** Every searcher and step would have to be asynchronous, the
  batch tools would start an event loop, and the blocking calls of torch would move into
  threads anyway. It pays off with thousands of slow connections, which an API with
  limits does not have.
- **Processes instead of threads.** The parallel sources of one query share the pool of
  database connections and the models in memory, which separate processes cannot.
