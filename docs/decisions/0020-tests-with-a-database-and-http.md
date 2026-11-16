# 0020: Tests with a database and HTTP

Date: 2026-11-16. Status: accepted.

## Context

Boundary and flow tests (decision 0018) need PostgreSQL with pgvector: the catalog, the
chunks and the indexes live there, and a stand-in would not check the SQL, the
transactions or the vector indexes. Until now CI had no database, so scenario S6, the
interruption tests and the test with a real SIGTERM (decision 0019) did not run in CI.

The core talks over HTTP with three services: e-INFRA (an OpenAI-compatible API for LLMs
and embeddings), DSpace over OAI-PMH and file downloads, and the search of DSpace. Tests in
CI cannot call them: they would need a secret, they would depend on a service outside the
project, and the answers of DSpace carry the names of people.

Docker Compose is how the system runs (decision 0002), and the notebook has Docker
Desktop.

## Decision

Database:

- `compose.yaml` in the root of the repository has the service `test-db` in the profile
  `test`. It runs the pgvector image with the version of pgvector and the major version
  of PostgreSQL in its tag, and keeps its data in memory (tmpfs). It listens on port 5433
  of 127.0.0.1 only, so a test never touches the database of development. The database
  service of the system will use the same image.
- `docker compose up --wait test-db` starts it, on the notebook and in CI alike, so the
  versions of PostgreSQL and pgvector are written in one place. Its health check asks over
  TCP, because during the first start the image runs a temporary server that listens only
  on a socket.
- At the start of a run the tests create a template database once, with the schema made by
  the same code that makes it for the programs. Each test marked `db` gets a database of
  its own, copied from the template (`CREATE DATABASE … TEMPLATE`) and dropped after the
  test. Tests then do not affect each other, although the code under test commits its own
  transactions (decision 0016). If copying turns out slow, the tests empty the tables
  after each test instead.
- The names of the template and the copies are unique to each run, so two runs at the same
  time do not collide. PostgreSQL copies a template only while nobody is connected to it,
  so the code that creates the schema closes its connections first. Databases left behind
  by a killed run stay in memory until `test-db` restarts.
- When `test-db` does not run, a test marked `db` fails with a message that says how to
  start it. It never skips, because a skipped test looks like a success.
- The main job of CI starts `test-db` before it installs the workspace and runs every test
  except those marked `model` or `gpu`. The tests marked `db` are then measured for
  coverage and timed like the rest (decision 0019).

HTTP:

- The core makes HTTP calls with httpx (decisions 0014 and 0015). The client of OpenAI 3
  builds on httpx2, which has the same interface. Which of the two the core declares as
  its dependency is decided with the first HTTP adapter, and `explorer.testing` uses the
  same one.
- A boundary module that calls HTTP creates its client itself, with its timeouts, and takes
  only a transport from its caller. A program passes none. A test passes `MockTransport`,
  which hands each request to a function of the test instead of the network.
- The boundary tests of each HTTP adapter cover a 429 with `Retry-After`, the codes 502,
  503 and 504, a timeout, a broken body, and the number of requests that the retries of
  decision 0014 send. An adapter with a limit of concurrent calls tests the limit, and an
  adapter of embeddings gets a vector with a wrong dimension.
- The client of OpenAI repeats a failed request twice by default (`max_retries=2`). The
  adapter turns this off, so only the retries of decision 0014 apply. A trial with
  a transport that answered 429 and then a vector showed two requests with the default and
  one with `max_retries=0`.
- The fake DSpace of decision 0018 is such a transport. For a synthetic corpus it answers
  OAI-PMH in the xoai format, with pages joined by resumption tokens, deleted records and
  the known quirks of DSpace UK, and it serves the files. Flow tests of the
  synchronization then run the real code of the harvester.
- Test responses are written by hand after the format, never copied from a real response,
  which would carry names of people and texts of theses.

Live tests:

- A test that calls a real external service, such as DSpace UK or e-INFRA, is marked
  `network`. It checks only the shape of the answer: keys, types, the dimension of
  a vector. It compares no content, so a failed assertion prints none either, and it
  stores nothing. It reads secrets from environment variables, as a program does
  (decision 0016).
- Tests marked `network` run only with the option `--network` (in `conftest.py` in the
  root), otherwise they skip. The option does not depend on the marker expression,
  because `-m` on the command line replaces the one in the configuration instead of
  adding to it.
- Nobody runs them in CI. A person runs `uv run pytest -m network --network` before a large
  synchronization or when an adapter starts to fail.

## Consequences

- Tests marked `db` need Docker Desktop running on the notebook.
- The flow tests with scenario S6, the interruption tests and the tests with a real
  SIGTERM run in the main job of CI, which runs on Linux.
- The image tag fixes pgvector and the major version of PostgreSQL. A minor release of
  PostgreSQL can arrive under the same tag.
- How the schema of the database is created and changed is not decided yet. The tests
  depend on it only through the code that creates the schema.
- A change of the format in DSpace or e-INFRA shows up only when a person runs the live
  tests.

## Alternatives considered

- **testcontainers.** The library starts a container from the tests, but it is one more
  dependency, and the image would be named a second time, in the code of the tests.
- **A service container in the workflow of CI.** The image would be named in CI and in
  Compose.
- **A job of its own for the tests marked `db`.** Their coverage would need merging
  across jobs, and the job would have to accept an empty run until the first such test.
- **One database for all tests, with a rollback after each test.** The code under test
  commits its own transactions, so nothing would be left to roll back.
- **A client of HTTP passed in by the caller.** The timeouts would then live outside the
  boundary module, against decision 0015.
- **Recorded real responses (cassettes).** They carry the names of people and the texts of
  theses.
- **respx or pytest-httpserver.** One more library for what `MockTransport` does. A real
  local server would test the sockets, and those belong to the HTTP library.
- **Live tests in CI on a schedule.** A secret in GitHub and load on DSpace UK, for a check
  that a person runs before a large synchronization anyway.
