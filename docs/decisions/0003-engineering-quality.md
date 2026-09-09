# 0003: Engineering quality and its enforcement

Date: 2026-09-09. Status: accepted.

## Context

The thesis field is software and data engineering, so the quality of the software is
graded together with the research. One developer works without a reviewer, the project
will run for about a year, and parts of it will be written under time pressure. The
conventions have to be checked by tools, because nobody else will check them.

## Decision

The same checks run at two gates:

- At commit time, through pre-commit hooks: ruff lint and format on the changed files,
  and validation of the commit message against Conventional Commits.
- In CI on every push and pull request: ruff format check, ruff lint, pyright, pytest,
  and validation of all pushed commit messages, because local hooks can be skipped
  with `--no-verify`.

Rules of the codebase:

- All Python code carries type annotations. Pyright runs in standard mode and
  application code has no untyped exceptions.
- Tests use pytest: unit tests for pure logic, integration tests for pipeline steps
  and API endpoints. Test code follows the same style rules as the rest.
- There are two quality regimes, defined in CLAUDE.md. `experiments/` are typed,
  cleanly structured scripts without a full test suite. `apps/` and `libs/` carry
  tests and documented interfaces. Code that proves useful in an experiment is
  rewritten for `apps/` or `libs/`, not copied over.
- Every commit is reviewed and approved by the author before it is made.

## Consequences

- The first days of the project go into tooling instead of features. After that the
  codebase stays consistent without anyone having to remember the rules.
- The git history is machine-readable and can serve in the thesis text as
  documentation of the engineering practice.
- A contributor, human or AI, who drifts from the conventions is stopped at commit
  time or in CI, and the mistake never enters the history.

## Alternatives considered

- **mypy instead of pyright.** Both work. Pyright is faster, matches the VS Code
  language server and needs less configuration.
- **black, flake8 and isort.** Ruff covers all three in one tool with one block of
  configuration.
- **commitlint with husky.** Common in JavaScript projects, but it would add a Node
  toolchain only for commit messages; pre-commit already does the same natively.
- **No enforcement, relying on discipline.** A year is long, deadlines come, and
  a solo project has no second pair of eyes to catch the lapses.
