# 0014: Errors and retries

Date: 2026-11-16. Status: accepted.

## Context

The application talks to a database, a model server, DSpace and an LLM provider, and any
of them can fail or answer late. Its callers react in different ways: the API answers
a client, a batch command leaves a unit of work unfinished, and a program with a broken
configuration must not start. If every module raised the exceptions of its own library,
every caller would have to know httpx, psycopg and the SDK of each provider.

## Decision

- The core defines one base exception, `ExplorerError`, with subclasses named by what the
  caller does with them:
  - `ConfigurationError`: a setup, an index spec or the deployment configuration is
    invalid. A program stops when it starts, and the API does not start with an invalid
    setup.
  - `InvalidRequest`: the input of a user is wrong. The API answers 400.
  - `NotFound`: an unknown thesis or setup. The API answers 404.
  - `Unavailable`: the model server, DSpace, the LLM or the database did not answer, also
    after the retries. The API answers 503, and a batch command leaves the unit of work
    unfinished.
- The classes live in `explorer.domain`, the lowest layer of the core (decision 0011), so
  every part of the core and every program can raise and catch them.
- These exceptions are for failures that a caller reacts to. A programming error, such as
  a wrong type or an impossible state, stays a `TypeError`, `ValueError` or
  `AssertionError` and ends as a 500.
- A boundary module (decision 0015) converts an exception of its library (httpx, psycopg,
  the SDK of a provider) into one of these and keeps the cause (`raise ... from err`).
  Code outside the boundary modules never catches the exceptions of those libraries.
- Only boundary modules retry, and only after a passing failure: a refused or broken
  connection, a timeout, HTTP 429, 502, 503 or 504. The number of attempts is limited,
  the wait between them grows, and a `Retry-After` header sets the wait up to a cap.
  A longer `Retry-After` raises `Unavailable` at once. Within a request of the API, the
  retries together fit into the timeout of the request. The core and the steps never
  retry.
- The API turns the exceptions of the core into HTTP responses in one handler.
  A `ConfigurationError` raised while the API runs, for example by a setup that a reloaded
  manifest made invalid, answers 503 and is logged as an error. Any other exception
  becomes a 500 with a general message, and the log gets the whole traceback.
- A valid result is not an error: a query without a language, an empty result, the
  fallback setup without the reranker (architecture, section 4.1).
- Ruff checks part of this with the set `TRY`, without `TRY003`. Among others it reports
  raising `Exception` itself and `logging.error` instead of `logging.exception` inside
  `except`. The rule `B904`, already selected, reports a `raise` inside `except` without
  `from`.

## Consequences

- The API and the batch tools handle four exceptions instead of the exceptions of every
  library.
- The classes come with the first code of the core. The body of an error response belongs
  to the design of the API.

## Alternatives considered

- **Exceptions named by their source** (`DatabaseError`, `ModelServerError`). The caller
  would still decide for each source what to do.
- **Retries in the core**, for example around every step. A step does not know whether its
  boundary module already retried, so the attempts would multiply.
- **`TRY003` and `EM`.** They move every message into the exception class or into
  a variable before the `raise`, which makes the code longer for a slightly shorter
  traceback.
