# 0010: Packages, layout and the lock file

Date: 2026-11-03. Status: accepted.

## Context

The application has a core library, three programs (API, batch tools, evaluation) and
plugins that show replaceability. Some parts need torch and CUDA. Others must install
without them, for example the API on a serving node without a GPU, or the tests of the
core in CI. The code runs on a Windows notebook and on Linux (CI, the faculty cluster).
The architecture decides which components get a package of their own
([architecture, Code packages](../architecture.md#code-packages)).

## Decision

- The Python code of the application is a uv workspace. Every folder in `libs/`
  (libraries and plugins) and `apps/` (programs) is a package with its own
  `pyproject.toml` and its own dependencies. One `uv.lock` in the root pins the versions
  for Windows and Linux together. `experiments/` and `eval/` stay outside the workspace.
- A component gets a package only when it has heavy dependencies, runs as a program of
  its own, or is a plugin. Everything else is a subpackage, a folder of modules inside
  a package.
- A package names another package of the workspace in its dependencies and marks it with
  `{ workspace = true }` in `[tool.uv.sources]`. uv then installs it from the repository
  in editable mode, so changes take effect without reinstalling.
- Each package uses the src layout: code in `src/<import name>/`, tests in `tests/` next
  to `src/`. The tests then import the installed package.
- The import name is the package name with `_` instead of `-`: `explorer-map` is imported
  as `explorer_map`.
- Python is pinned to 3.13 (`requires-python = "==3.13.*"`).
- torch comes in two extras of the package with the in-process model adapters, `cpu` and
  `cu126`, which exclude each other. Both are in the lock. The notebook's driver (560.94)
  supports at most CUDA 12.6.
- Development tools move into dependency groups (PEP 735) in the root `pyproject.toml`,
  and `requirements-dev.txt` goes away.

## Consequences

- One `uv sync` gives one environment with every package. `uv sync --package explorer-api`
  installs one program with only its own dependencies, for a deployment image or the CI
  job without torch.
- All packages share one environment, so a package can import a package it does not
  declare and still work locally. Decision 0011 closes this gap.
- Pyright checks `libs/` and `apps/` strictly through its `strict` setting (decision
  0003). Pytest imports test files in importlib mode, so two packages can both have
  a `tests/test_config.py`. In this mode pytest does not put the folder of a test on
  `sys.path`, so the conftests of the experiments do it.
- uv is not yet installed on the development machine. Until it is, the skeleton has no
  `uv.lock` and the tools still come from `requirements-dev.txt`. Pyright cannot resolve
  an import of another package of the workspace before uv installs the packages, so the
  switch to uv has to come before the first code that imports another package.
- OpenAI announced in March 2026 that it is buying Astral, the company behind uv. The lock
  can be exported to the standard `pylock.toml` (PEP 751), so moving away from uv stays
  possible.

## Alternatives considered

- **One package with optional extras for the heavy parts.** Simpler to set up, but nothing
  would stop the core from importing torch, and a plugin inside the core package shows no
  replaceability.
- **A lock per package.** Versions would drift apart between the API and the batch tools,
  and one developer would keep eight locks up to date.
- **Flat layout without `src/`.** Tests would import the source folder even when the
  package is installed wrong, and the error would show only in deployment.
- **Subpackages of one name (`explorer.map` instead of `explorer_map`).** `explorer` is
  a regular package with an `__init__.py`, so another package cannot add modules under it.
