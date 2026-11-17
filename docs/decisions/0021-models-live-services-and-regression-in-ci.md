# 0021: Models, live services and regression under the control of CI

Date: 2026-11-16. Status: accepted. Since decision 0024 `live.yml` also runs `uv audit`.

## Context

Decision 0018 left the tests with a real model outside CI, decision 0020 left the live
tests to a person, and a setup rewritten from experiment 05 has to give the results of the
experiment, which only a run over the real corpus shows. A check that depends on someone
remembering it gets skipped sooner or later.

The repository is public, so GitHub runs its jobs for free on runners with 4 cores and
16 GB of memory, without a GPU. A trial with BGE-M3 on the notebook gave these numbers:

- On the CPU the model loads and encodes three sentences in 10 seconds.
- The same sentences on the GPU in float16 and on the CPU in float32 differ by at most
  0.0002 in one component. Normalized in float16, the vectors are not exactly of length
  1, so their dot products lie between 0.9998 and 1.0002.
- Two runs on the same device give the same vectors to the bit.

## Decision

Tests with a model in CI:

- The job `models` runs on every push to `main` and on every pull request. It starts
  `test-db`, installs everything like the main job and runs `pytest -m model` on the CPU.
- Tests load only models that have reference outputs (below). The job keeps the models in
  the cache of GitHub Actions under the hash of the reference outputs, which name every
  model and revision. Before the tests, `python -m explorer_models_local.download`
  downloads what the cache lacks, so a download does not count against the time limit of
  a test.
- The tests check the contract suite of the model adapters (decision 0019), the reference
  outputs, and that the model server returns the same outputs as the adapter in the
  process.
- The job measures the coverage of `explorer_models_local`, which only these tests run.
  The main job reports the other packages.
- No test needs a GPU. The marker `gpu` is gone, so strict pytest stops a test that asks
  for it.

Tests that must not skip:

- A test marked `db` or `model`, or marked `network` in a run with `--network`, never
  skips. `conftest.py` in the root turns such a skip into a failure, because a skipped
  check looks like a passed one. A live test of e-INFRA without its key fails.

Reference outputs:

- For each model that a setup uses, `explorer_models_local/reference_outputs/` holds
  a few texts written by hand in Czech, Slovak and English, the model with its revision,
  and its outputs: the vectors of an encoder, the token weights of a sparse encoder, the
  scores of a cross-encoder for pairs of a query and a text. One text is longer than the
  input limit that the setup gives the model, so a change of truncation shows too.
- Vectors and token weights pass when their cosine similarity, computed in float32 after
  normalization, is at least 0.999. Scores pass within a tolerance measured the same way
  on the CPU and the GPU. The threshold lies just below the difference measured between
  the devices. If a GPU of the cluster differs more, a measurement there sets it again.
- An index holds vectors computed by one version of a model and its libraries. When
  another version computes them differently, queries stop matching the index, and search
  gets worse without any error. The reference outputs catch that.
- Every program that uses a model checks the reference outputs when it starts, in the
  adapter, whether the adapter loads the model or calls a model server such as TEI
  (decision 0004). When they differ, the program exits with 78 (decision 0016), because
  another run does not help. This is how the GPU gets checked, on every machine that uses
  one and on every start.
- The manifest of an index build keeps the reference outputs of its encoder from the time
  of the build. The setup loader, which already refuses a query encoder that does not
  match the manifest, compares them too. An index built before the reference outputs in
  the repository were refreshed is then still caught.

Golden runs:

- A flow test in CI runs the whole path on a synthetic corpus: the fake DSpace, the
  synchronization, chunking, an index in PostgreSQL, a search, and a TREC run for
  synthetic queries. The fake models of `explorer.testing` stand in for the real ones.
  The order of the ids per query must equal the stored run exactly, the scores within
  a tolerance (decision 0018).
- Every setup that has a regression result (below) has a golden run. A test checks that
  every step in the registry appears in at least one golden run.
- Every ranking breaks a tie of scores by the id of the thesis or the chunk, otherwise the
  order of ties would depend on chance. The small corpus is searched exactly, without
  an HNSW index, which does not promise the same results.
- A command refreshes the stored runs. It refuses when the ranking of a setup changed and
  no step of that setup got a new versioned name in the registry, such as `fuse.rrf.v2`.
  The architecture asks for the new version anyway, because the caches use it in their
  keys (architecture, section 7.2). A stored run edited by hand shows in the diff that
  the author reviews before every commit.

Regression against experiment 05:

- A setup of experiment 05 rewritten into `libs/` is run by the evaluation tool on
  evaluation set v1, on the notebook or the cluster, and compared with the run of the
  experiment in `data/runs/05-search-v1/`. It passes when the means of MRR@10 and nDCG@10
  differ by at most 0.01 from `experiments/05-search-v1/results/`, the paired
  randomization test of `eval/compare.py` finds no significant difference, and the mean
  RBO of the rankings per query is at least 0.9.
- The tool writes the result next to the setup file, with the verdict and a fingerprint
  of the setup: the setup file, its index specs with the model revisions, and the
  versioned names of its steps. Index builds and snapshots stay out, because CI does not
  have them.
- A test in CI fails when the stored verdict is not a pass or when the fingerprint
  computed again differs. Its message names the command that runs the regression.
  A change of a setup, a model or the version of a step thus cannot stay in a green CI
  without a passed regression, and neither can a change of code that changes a ranking,
  because the golden runs demand a new version for it.

Live tests:

- The workflow `live.yml` runs the tests marked `network` once a week and on demand, with
  `test-db` and everything installed. The tests of DSpace UK need no key. The tests of
  e-INFRA read the key of the maintainer from the secret `EXPLORER_EINFRA_API_KEY` of the
  repository, the same name that the adapter reads as an environment variable. Workflows
  started by pull requests from forks get no secrets.
- Decision 0020 rejected scheduled live tests also because of the load on DSpace UK.
  A few requests a week are small next to the daily synchronization.
- The job `live-runs` of the main workflow fails when `live.yml` has not passed within
  the last 8 days. A failing weekly run, or a schedule that GitHub turned off after 60
  days without activity in a public repository, then shows on the next push.

Empty runs:

- A job that may select no tests yet accepts an empty run only until the code that needs
  the tests exists. The job of the core without torch, which now also starts `test-db`,
  accepts it until `libs/explorer` has its first test file. The job `models` until the
  first model has reference outputs. `live.yml` until a package in `libs/` or `apps/`
  imports httpx or httpx2. After that an empty run fails like in the main job.

## Consequences

- The cache of CI holds a few GB of models. GitHub allows 10 GB per repository.
- Every program that uses a model starts a few seconds later.
- The regression against experiment 05 is the only check that runs outside CI, and CI
  fails until it has passed.
- The maintainer stores the key of e-INFRA as a secret of the repository. Without it the
  weekly run fails, and so does the main workflow a week later.
- `explorer_models_local` needs a command `download` and the manifests of index builds
  need the reference outputs, both before the first model test.
- Decision 0018 no longer holds where it keeps the tests with a model out of CI and where
  it has the marker `gpu`. Decision 0020 no longer holds where it leaves the live tests to
  a person. Decision 0004 still says that the tests of the adapters are marked as needing
  a model or a GPU, and the manifest in the architecture does not list the reference
  outputs yet.

## Alternatives considered

- **A runner of our own on the notebook.** GitHub advises against it for a public
  repository, because a pull request could run code on the notebook, and the notebook is
  not always on.
- **GPU runners of GitHub.** They are paid.
- **Manual runs with a checklist.** They are skipped sooner or later.
- **Live checks only in the programs.** A changed format would show only when a user or
  a synchronization hits it.
- **Ending the exception for empty runs by searching the tests for a marker.** A marker
  built in code does not appear in the text, and the exception would never end.
