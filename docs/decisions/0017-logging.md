# 0017: Logging

Date: 2026-11-16. Status: accepted.

## Context

The API, the model server, the batch tools and the evaluation write logs. Docker keeps
them on the serving node, and SLURM keeps them in the output files of jobs on the
cluster. The architecture decides that the log of queries keeps only the text of a query,
the time and the setup, without the IP address and for a limited time, and that the
access log of the reverse proxy never keeps the text of a query next to an IP address
(section 7.6). It also promises that the system neither finds nor shows what DSpace does
not publish, and it deletes the chunks of versions that are gone (section 7.4). A log is
a copy outside the database that this deletion does not reach.

Content reaches a log not only through the messages we write. Exceptions of libraries
carry it too: a pydantic validation error repeats the input value, an HTTP error repeats
the URL with its query string, and a database error can repeat the whole row it refused.

## Decision

Who logs and where:

- The programs log with the module `logging` of the standard library. Code in `libs/`
  takes a logger named after its module (`logging.getLogger(__name__)`) and writes to it.
  Only a program in `apps/` configures logging, once, when it starts, from the deployment
  configuration.
- Every program that runs uvicorn (the API and the model server) starts it with
  `log_config=None` and `access_log=False`. uvicorn then adds no handlers of its own, and
  its records go through our configuration.
- Logs go to standard error. Docker collects it, and the job scripts on the cluster give
  standard error its own file (`sbatch --error`), so standard output stays for the results
  of commands.
- The format is readable text in development and one JSON object per line in
  deployment, as the deployment configuration chooses. A short formatter of our own
  writes the JSON.
- The records our code writes carry the id of the request in the API or of the run in
  a batch command. The API makes the id itself and never takes one from the proxy. The id
  travels in a context variable, and the thread pools of decision 0015 run each task in
  a fresh copy of the context, so the id reaches their threads too.

Levels:

- INFO: the start of a program with a summary of its configuration, and the start and
  end of each run with its counts.
- WARNING: reduced service, such as the fallback setup or a retry.
- ERROR: a unit of work or a request that failed on our side, with the traceback. A
  request answered with 4xx is not an error of the system and appears only in the line of
  the request.
- DEBUG: only in development.

What a log never contains:

- No text of a thesis: neither its full text and chunks nor its title, abstract, keywords
  or other metadata. No names of people, no IP addresses and no secrets. A log names
  a thesis by its id and version, which is enough to find the rest in the catalog.
- The text of a query goes only to the log of queries. The API writes it to one logger
  with a fixed name, `explorer.queries`, which does not pass records on to the general
  log (`propagate=False`) and carries no id of the request, so the two logs cannot be
  joined. The deployment sends the log of queries elsewhere and deletes it after
  a limited time.
- The API writes one line for each request: the method, the route as it is defined (such
  as `/v1/theses/{id}`, or a fixed word when no route matched), the status and the time
  it took. It never writes the path as the client sent it.
- A secret is a `SecretStr` field of its own, never part of another value. The password of
  the database is not inside the address of the database.
- A validation error is logged with the place and the kind of each error, without the
  input value (`errors(include_input=False)` in pydantic).
- When the message of an exception of a library can contain content, such as the refused
  row of a database constraint or the body of an error of a provider, the boundary module
  raises our exception `from None` and names the type of the original exception in its
  message. This narrows the rule of decision 0014 to keep the cause. Requests to services
  carry queries and texts in their body, never in the URL.
- `InvalidRequest` names the rule that refused a request, never the query.
- Starlette passes an exception it answered with 500 on to uvicorn, which logs it.
  The handler of decision 0014 therefore answers without logging it again.

Checks:

- Ruff checks part of this with the sets `LOG` and `G` and with the rule `TID251`, which
  forbids `logging.basicConfig` and `logging.config.dictConfig` and `fileConfig` outside
  `apps/`, `experiments/` and `eval/`.
- A test puts a marker string into the text, the title and the author of a synthetic
  thesis, runs indexing and search, forces a failing validation, a failing database
  insert and a failing HTTP call with it, and checks that the marker never appears in the
  captured general log.

## Consequences

- When DSpace withdraws a thesis and the chunker deletes its chunks, the general log holds
  nothing of it but its id. The log of queries can hold a query that repeats its title
  until the log is deleted, and whether backups follow the deletion waits for the
  supervisor (architecture, section 7.4).
- Finding everything about one thesis in the logs means searching for its id.
- Records written by threads that our pools do not own, such as those of the pool of
  database connections, carry no id of a request.
- A failing database constraint shows its type and the ids in the log, not the row, so
  finding its cause can take a look into the database.

## Alternatives considered

- **structlog or loguru.** They give structured logs out of the box, but they add
  a dependency for what a short formatter does.
- **Programs writing log files themselves.** Docker and SLURM already keep standard error,
  and files of our own would need rotation and cleanup.
- **Masking texts in a log filter.** A filter cannot tell which string is the text of
  a thesis. The rules above keep content out of our messages and out of the messages of
  libraries that we pass on, and the test checks both.
