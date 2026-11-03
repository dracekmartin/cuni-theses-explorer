# 0012: Code style

Date: 2026-11-03. Status: accepted.

## Context

Ruff formats the Python code and checks it against sets of rules. Until now nine sets
applied to every file: pycodestyle, pyflakes, import order, naming, modern syntax,
bugbear, simplifications and pathlib. They were chosen for the experiments. The
application adds a database, HTTP calls to models and to DSpace, timestamps from the
harvest and a public interface for plugins, and each of these has mistakes of its own.

The code in `eval/` already has a style: a docstring is one sentence that says what the
function returns (`"""Share of the top k results that have a judgment of any grade."""`),
test names describe the behavior, and there are no TODO comments.

## Decision

- `ruff format` formats all Python code, with lines of at most 100 characters.
- The nine sets stay for every file.
- All code outside `experiments/` and `eval/` is checked by more sets: today `libs/`,
  `apps/` and `tools/`, and any new folder too. Each set is listed with its reason in the
  root `pyproject.toml`:
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
  - `D`: docstrings, see below.
  - `FIX`: `TODO`, `FIXME`, `XXX` and `HACK` comments. Unfinished work goes into the plan
    or an issue, not into the code.
- Docstrings follow the Google convention. Every module, package, public class, function
  and method outside `experiments/`, `eval/`, `tools/` and the tests has one, today in
  `libs/` and `apps/`. `__init__` (covered by the class docstring), magic methods and
  names with a leading underscore need none.
- The first line of a docstring is one sentence that says what the function returns or
  does, as in `eval/`, and fits on that line. A longer docstring continues after a blank
  line. `Args`, `Returns` and `Raises` appear only where the name and the type do not
  say enough, and an `Args` section lists every argument. Types stay in the annotations.
- A comment is one line and says why, not what.
- Names follow PEP 8 (ruff `N`). A leading underscore marks what is internal to its
  package: other modules of the package may import it, other packages do not. Test names
  describe the behavior.
  Domain terms follow the Naming section of `CLAUDE.md`.
- Tests may use `assert`. Test folders and `tools/` need no `__init__.py` and no
  docstrings, because test names describe the behavior.
- `experiments/` and `eval/` stay on the nine sets, as the lighter regime of decision
  0003. That decision says test code follows the same rules as the rest. The exceptions
  above for `assert`, `__init__.py` and docstrings are the only differences.
- Rules for exceptions and logging come with the decision on those topics. Decision 0013
  adds the single rule `ANN401`.

## Consequences

- A new set of rules is a change in `pyproject.toml`. ruff is pinned in `uv.lock` and in
  `.pre-commit-config.yaml`, and both pins have to move together. An upgrade is
  a deliberate change and can bring new rules inside the selected sets.
- Code that moves from an experiment into `libs/` has to pass the stricter sets, which
  matches the rule that such code is rewritten, not copied (decision 0003).
- `FAST` and `ASYNC` have nothing to check until the first code of the API, `NPY` until
  the first numpy code in `libs/`.
- Ruff checks that a docstring exists and has the right form, not what it says. The
  underscore rule rests on review: the ruff rule for it (`PLC2701`) is still a preview.

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
- **The NumPy or PEP 257 convention.** Both require the first line in the imperative
  mood, which several dozen docstrings in today's experiments do not use.
- **Docstrings only in `explorer.plugin` and `explorer.testing`.** Less writing, but
  `CLAUDE.md` promises documented public interfaces for all of `libs/` and `apps/`.
- **TODO with a link to an issue (ruff `TD`).** The plan or the issue already holds the
  work, and the link in the code would only repeat it.
