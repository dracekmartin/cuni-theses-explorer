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
- Each package has a `py.typed` file, so pyright in strict mode uses its types when
  another package imports it.
- The development tools and the dependencies of `experiments/` and `eval/` are two
  dependency groups (PEP 735) in the root `pyproject.toml`, `dev` and `experiments`.
  `uv sync` installs both by default. The groups pin exact versions, so an upgrade is
  a deliberate change. The `experiments` group holds the versions that produced the
  reported results.
- The package with the in-process model adapters will offer torch in two extras, `cpu`
  and `cu126`, which exclude each other, and the lock will hold both. The notebook's
  driver (560.94) supports at most CUDA 12.6. Until that package has code, torch comes
  only through the `experiments` group: the CUDA 12.6 build on Windows, the CPU build on
  Linux. The source of torch in the root `pyproject.toml` depends only on the platform,
  so the extras will need sources of their own and a declared conflict with the
  `experiments` group.
- The lock covers Windows and Linux only.
- The uv version is pinned by `required-version` in the root `pyproject.toml`. CI installs
  the same version.

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
- The lock holds one version of each library for the whole repository (torch has one
  build per platform). The pinned versions of the experiments therefore also bind the
  packages of the application, until someone upgrades them.
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
