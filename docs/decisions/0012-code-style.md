# 0012: Code style

Date: 2026-11-03. Status: accepted.

## Context

Ruff formats the Python code and checks it against sets of rules. Until now nine sets
applied to every file: pycodestyle, pyflakes, import order, naming, modern syntax,
bugbear, simplifications and pathlib. They were chosen for the experiments. The
application adds a database, HTTP calls to models and to DSpace, timestamps from the
harvest and a public interface for plugins, and each of these has mistakes of its own.

## Decision

- `ruff format` formats all Python code, with lines of at most 100 characters.
- The nine sets stay for every file.
- All code outside `experiments/` and `eval/` is checked by twenty more sets: today
  `libs/`, `apps/` and `tools/`, and any new folder too. Each set is listed with its
  reason in the root `pyproject.toml`:
  - `S` (security): SQL built from strings, HTTP calls without a timeout, `pickle`.
  - `DTZ`: dates and times without a time zone, which shift the comparison of harvest
    timestamps.
  - `T20`: `print` instead of logging.
  - `BLE`: catching every exception.
  - `FBT`: boolean positional arguments, so a call reads `find(query, rerank=True)`.
  - `A`: names that hide builtins such as `id`, `type` or `list`.
  - `ERA`: commented-out code. `ARG`: unused arguments.
  - `PLE`, `PLW`: errors and warnings from pylint, for example an overwritten loop
    variable.
  - `INP`: a folder of modules without `__init__.py`. import-linter does not see such
    a folder, so the layers of decision 0011 would not cover it.
  - `PGH`: an ignore comment (`# type: ignore`, `# noqa`) without the code of the rule.
  - `RUF`, `C4`, `PIE`, `PERF`, `PT`: ruff's own checks, comprehensions, needless
    statements, slow loops and pytest style. Czech text may contain en dashes and
    no-break spaces, which `RUF001` would otherwise report as look-alike characters.
  - `NPY`, `FAST`, `ASYNC`: deprecated numpy calls and misuse of FastAPI and asyncio.
- Tests may use `assert`. Test folders and `tools/` need no `__init__.py`.
- `experiments/` and `eval/` stay on the nine sets, as the lighter regime of decision
  0003. That decision says test code follows the same rules as the rest. The exceptions
  above for `assert` and `__init__.py` are the only differences.
- Rules for docstrings, type annotations, exceptions and logging come with the decisions
  on those topics. Decision 0013 adds the single rule `ANN401`.

## Consequences

- A new set of rules is a change in `pyproject.toml`. ruff is pinned in `uv.lock` and in
  `.pre-commit-config.yaml`, and both pins have to move together. An upgrade is
  a deliberate change and can bring new rules inside the selected sets.
- Code that moves from an experiment into `libs/` has to pass the stricter sets, which
  matches the rule that such code is rewritten, not copied (decision 0003).
- `FAST` and `ASYNC` have nothing to check until the first code of the API, `NPY` until
  the first numpy code in `libs/`.

## Alternatives considered

- **`ALL` with a list of ignored rules.** The ruff documentation warns that `ALL` turns on
  new rules with every upgrade, and the reason for each set would be lost in a long list
  of exceptions.
- **The new sets for the experiments too.** They would report about 300 places in
  `experiments/` and `eval/`, and about 50 without `print`, `assert` and the missing
  `__init__.py`. The experiments are probes, and rewriting them brings nothing.
- **`PLR` (magic numbers, too many branches or statements).** About 40 hits in today's
  code, nearly all of them noise.
- **`TC` (imports needed only for type hints).** Moving such imports brings nothing on
  Python 3.13.
