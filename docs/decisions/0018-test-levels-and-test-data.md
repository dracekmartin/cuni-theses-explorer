# 0018: Test levels and test data

Date: 2026-11-16. Status: accepted. Since decision 0020 the main job of CI runs the tests
marked `db` too. Since decision 0021 the tests marked `model` run in CI on the CPU, and the
marker `gpu` is gone.

## Context

Decision 0003 asks for tests in `libs/` and `apps/`: unit tests for pure logic, and
integration tests for the steps of pipelines and for the endpoints of the API. Decision
0004 asks that the search core is tested without torch, with a fake deterministic
encoder, and that tests of the in-process adapters run separately, marked as needing
a model or a GPU. The quality scenarios of the architecture (chapter 9) rest on tests too:
a thesis withdrawn in DSpace is no longer found (S6), and a new searcher or step is a new
class that needs no change elsewhere (S3, S4). The theses are works of students with
names of people, so their data stays out of git, and tests cannot build on them.

## Decision

Levels, named by what a test touches:

- Unit tests check pure logic without a database, a network or files: fusion, the
  aggregation of chunks, the analysis of queries, fingerprints, models of configuration.
  Most tests are unit tests.
- Boundary tests check a boundary module (decision 0015) against the real thing: storage
  against PostgreSQL, writing files. How they reach a database is decided with the tests
  that need infrastructure.
- Flow tests run a whole path on a small synthetic corpus: synchronization, chunking, an
  index build, search and the visibility guard. A thesis that the fake DSpace withdraws is
  no longer found after the next synchronization (S6). The catalog and the indexes live in
  PostgreSQL, so flow tests need it too. Tests of the endpoints of the API belong here as
  well, and their details come with the tests that need infrastructure.
- Model tests load a real model, and some of them need a GPU. They do not run in CI.

Markers:

- `db` for a test that needs PostgreSQL, `model` for one that loads a real model, `gpu` for
  one that needs a GPU. A test that needs a GPU also loads a model, so it carries both
  `model` and `gpu`.
- The markers are registered in the configuration of pytest, which runs in strict mode
  (`strict = true`, pytest 9). A marker with a typo on a test then stops the run instead
  of letting the test run where it should not. The documentation of pytest advises strict
  mode only with a pinned pytest, which `uv.lock` provides.
- CI selects tests with a marker expression. Until CI has a database, it runs
  `-m "not db and not model and not gpu"`. Strict mode does not check the expression
  itself, so the run of all tests in CI fails when it selects no test. Only the job of
  the core without torch accepts an empty run, until the core has tests.

Place and names:

- The tests of a package lie in its folder `tests/` next to `src/` (decision 0010) and
  follow the structure of its modules, for example
  `libs/explorer/tests/search/test_fusion.py`.
- The name of a test describes the behavior it checks, such as
  `test_withdrawn_thesis_is_not_found`. One test checks one behavior, and the expected
  results are small cases computed by hand, as in `eval/test_metrics.py`.

Test data:

- No real thesis and no real name. Tests build their data themselves.
- Synthetic theses have ids of their own form (`fake-0001`), which cannot be mistaken for
  a handle of DSpace. Their authors and supervisors are made up.
- Short Czech, Slovak and English sentences for tests of lemmas and languages are written
  by hand, not taken from theses.
- The fake encoder turns a text into a vector from its words, so similar texts get
  similar vectors and a test of ranking means something. It maps a word to a dimension by
  a stable hash (`hashlib`), never by `hash()`, which changes with every process. Tests
  compare rankings, or scores with a tolerance, never exact floats. The fake encoder is
  a model adapter registered in the registry like any other, so a setup in a test names
  it the way it would name a real model. The API refuses at start a setup that names
  a fake model.
- Data is built in code by small helper functions, not loaded from large files.
- The helpers that the tests of several packages share live in the subpackage
  `explorer.testing`: the fake models, a fake DSpace for synchronization, and the builders
  of synthetic theses and corpora. They are plain functions and classes without pytest,
  and they use only the dependencies of the core, so the CI job without torch can import
  them. In the layers of decision 0011, `testing` is a layer of its own above `adapters`,
  so it may use everything in the core.

## Consequences

- Until CI gets a database, it runs no test marked `db`. The flow tests, scenario S6
  included, then run only on the notebook.
- The fake encoder ships with the core, so a demonstration can run without a model.
- `explorer.testing` is installed with the core although only tests use it. It brings no
  heavy dependency.

## Alternatives considered

- **Markers by level** (unit, integration). A level says little about what a test needs,
  while a marker by requirement selects directly the tests a machine can run.
- **A package of its own for the helpers.** It would break the rule of decision 0010 that
  a package exists only for heavy dependencies or a program of its own.
- **Helpers copied into the `conftest.py` of each package.** The same code would live in
  several places.
- **Test data from real theses with the names removed.** Removing names reliably is hard,
  and the texts stay works of students.
