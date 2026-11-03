# 0011: Direction of dependencies

Date: 2026-11-03. Status: accepted.

## Context

The thesis has to show that components can be replaced, so the code has to keep to the
dependencies that the architecture allows. Python does not stop any import, and
in a uv workspace every package sees every other one (decision 0010). The rules come from
the architecture ([Code packages](../architecture.md#code-packages)): the core depends on
no other package and never imports torch, programs reach plugins and in-process adapters
only through the registry, plugins import only `explorer.plugin`, and the subpackages of
the core form layers.

## Decision

Every rule is checked against data that exists anyway, so a new package, plugin or
subpackage cannot slip past the checks.

- deptry checks the dependencies between packages. It runs as `deptry src` in every
  folder of `libs/` and `apps/` and reports each import that the package does not declare
  in its `pyproject.toml`. Run from the package folder itself, deptry would not recognize
  the package's own modules and would report them too. The dependencies of a package are
  therefore the complete list of what it may import, other packages of the workspace and
  torch included. The core declares neither.
- When a program has an extra only so that the registry finds a plugin, the extra is
  listed in `[tool.deptry] optional_dependencies_dev_groups`, and deptry reports a direct
  import of the plugin as an error (DEP004). `explorer-api`, `explorer-batch` and
  `explorer-eval` list `local-models` there. `explorer-batch` imports `explorer-map`
  directly, because the map is not a plugin.
- A package is a plugin when its `pyproject.toml` registers in the entry point group of
  the registry (working name `explorer.plugins`). The test
  `tools/test_plugin_imports.py` finds these packages and checks with grimp that they
  import from `explorer` only `explorer.plugin`.
- import-linter checks the layers inside the core. A layers contract in the root
  `pyproject.toml` orders the subpackages of `explorer`. With `exhaustive = true`, a new
  subpackage fails the check until it is placed in a layer. One more contract forbids the
  search core to import the harvest, which sits below it.
- An exception in a contract (`ignore_imports`) needs a comment with the reason.
- CI installs `explorer` alone, without torch, and runs its tests.
- The checks run at both gates of decision 0003, at commit time and in CI.

## Consequences

- No list of packages has to be kept up to date. A package is checked as soon as its
  folder exists, a plugin as soon as it registers.
- The rules are only as strict as the declared dependencies: torch added to the core's
  `pyproject.toml` passes deptry. The CI job without torch and the review of every change
  to a `pyproject.toml` catch that.
- Layers express only an order. The adapters sit at the top because nothing in the core
  imports them, so they could import the search core and the check would not notice.
- deptry finds the import name of a package of the workspace by the naming rule of
  decision 0010.
- The tests of a plugin live outside `src/` and are not checked.
- For now only import-linter runs in CI. Pre-commit, deptry in CI and the CI job without
  torch come with the switch to uv, which installs the packages. deptry also reports the
  empty packages of the skeleton as not using `explorer` (DEP002) until they contain code.
- The plugin test needs the packages installed to build its graph. Until a package
  registers as a plugin, it has nothing to check.

## Alternatives considered

- **import-linter for everything,** with forbidden and independence contracts that name
  every package. It repeats `pyproject.toml`, and a forgotten name goes unchecked. In
  a trial with this setup, two subpackages of the core were in no layer and nothing
  reported it.
- **tach.** It checks module boundaries and public interfaces in one tool, but version
  0.35 is still a beta.
- **Review only.** One developer without a reviewer would miss violations (decision 0003).
