# 0019: Property, contract and interruption tests, coverage and time

Date: 2026-11-16. Status: accepted. Since decision 0020 the main job of CI runs the tests
that need PostgreSQL, the tests with a real SIGTERM included, and measures their coverage.

## Context

Decision 0018 sets the levels of tests, their markers and their data. Some promises of the
architecture need more than small cases computed by hand:

- Fusion, the aggregation of chunks, fingerprints, chunking and the metrics in `eval/` are
  pure functions with rules that hold for every input. A few hand-made cases miss the
  inputs nobody thought of.
- In scenarios S3 and S4 a new searcher or step is a new class, and only its registration
  changes existing code. That has to hold for the tests too.
- Decision 0016 promises that a batch command stopped by a signal continues where it
  stopped, without a unit saved twice.
- CI has no limit for a single test, and GitHub stops a job only after six hours.

## Decision

Property tests:

- A pure function with a rule that holds for every input gets a property test with
  Hypothesis, next to its cases computed by hand. Examples of rules: a fusion input
  without candidates changes nothing, a fingerprint does not depend on the order of keys
  in a setup, the chunks of a text cover the whole text and none exceeds the size limit,
  nDCG, precision and reciprocal rank of a ranking without repeated ids stay between 0
  and 1.
- A generator builds related inputs together, such as a ranking and its judgments from the
  same ids. Inputs generated apart rarely share an id, so the test seldom sees a ranking
  that contains a judged thesis. A trial on a copy of `eval/metrics.py` with a planted
  off-by-one error in nDCG showed this: generators that built a ranking and its judgments
  apart missed the error, a combined generator found it and reduced it to two relevant
  theses and `k=1`.
- Generators live with the tests that use them. `explorer.testing` does not import
  Hypothesis, because it uses only the dependencies of the core (decision 0018).
- Hypothesis needs no configuration. On GitHub Actions it loads its profile `ci` by itself:
  a fixed seed, no time limit per example and no database of failed examples. Locally it
  draws new inputs on every run and keeps failed examples in `.hypothesis/`, a folder it
  excludes from git by itself.

Contract tests:

- Each replaceable interface (searcher, step, index builder, model adapter) has one suite
  of contract tests in the tests of `explorer`. The suite is parametrized over every name
  of that kind in the registry, so a new registered class is tested without a change of
  existing tests. The own logic of a class, such as the formula of a fusion, gets its tests
  in a new test file.
- The suite checks what every implementation of the interface promises. For example,
  a searcher and a step return results sorted by score, without repeats and no more than
  they were asked for, and the same input gives the same ranking. A model adapter returns
  one vector per text with the dimension it declares, and the same text gives the same
  vector within a tolerance (decision 0018).
- The suite needs a small configuration for each class. The class provides it next to its
  model of parameters (decision 0016), so a new class brings it along, and a class without
  one fails the suite.
- A case whose class needs PostgreSQL or a real model carries the marker `db` or `model`
  (decision 0018). A class of the core states what it needs in its definition. The suite
  reads that when it collects the cases, and importing a class of the core never imports
  torch. A name that comes
  from the entry point of `explorer_models_local` always gets `model`, and the suite loads
  its class only inside the test, so deselecting the case never imports torch.

Interruption tests:

- Each batch command has a test that stops it after a few units, runs it again and
  compares the result with a run that was not stopped. The result is the same, no unit is
  saved twice and no temporary file is left behind.
- The test stops the command by the same stop flag that the handler of SIGTERM and SIGINT
  sets, so it also runs on Windows. When Hypothesis chooses after which unit the command
  stops, the test limits the number of examples, so it stays within the time limit below.
- For each program one test sends a real SIGTERM to the command in a process of its own
  and checks the exit code 75. That test runs only on Linux (decision 0016).
- Batch commands write to the catalog, so most of these tests are flow tests marked `db`.

Coverage:

- coverage.py measures branch coverage of `libs/` and `apps/` while CI runs the tests, and
  CI prints the report. The report lists every module of the application, also one that no
  test imports. It runs as `coverage run -m pytest`, without the plugin pytest-cov, which
  would only wrap the same tool.
- When the first test of SIGTERM comes, the configuration of coverage gets
  `patch = ["subprocess"]`, so coverage also measures the process that the test starts.
- No lower limit yet. There is no application code to measure, and a number chosen in
  advance leads to tests written for the number. The limit is set from the first
  measurement of a core with logic, as `fail_under` in the configuration of coverage, and
  that change updates this record.

Time:

- The unit tests of `libs/` and `apps/` finish within a minute on the notebook, and a job
  of CI within ten minutes. CI prints the ten slowest tests (`--durations=10`).
- A test that runs longer than 120 seconds is stopped (pytest-timeout). On Linux the test
  fails and the run goes on. On Windows pytest-timeout cannot interrupt a single test, so
  it prints the stacks of all threads and ends the whole run. A test that needs more time,
  such as a model test, raises its own limit with the marker `timeout` and says why in
  a comment.
- A job of CI stops after 20 minutes, twice its budget, so a step that hangs outside
  a test does not wait for the six hours of GitHub.

## Consequences

- The group `dev` gets three tools: `hypothesis`, `pytest-timeout` and `coverage`.
- Until CI has a database, the interruption tests of the batch commands and the contract
  tests of the classes that need PostgreSQL run only on the notebook. The tests with
  a real SIGTERM need both Linux and a database, so until then they run nowhere
  automatically.
- The metrics in `eval/` get property tests in addition to the cases in
  `eval/test_metrics.py`.
- Measuring coverage makes the tests in CI slower. The report does not stop CI until the
  lower limit exists, only a missing measurement does.

## Alternatives considered

- **A list of classes in each contract suite.** A new class would change the tests, and
  scenarios S3 and S4 would not hold.
- **Interruption only by real signals.** Windows cannot deliver SIGTERM to Python, and the
  moment of the stop would depend on timing.
- **pytest-cov.** One more plugin around coverage, which `coverage run -m pytest` uses
  directly.
- **A lower limit of coverage now.** Without code to measure, any number would be a guess.
