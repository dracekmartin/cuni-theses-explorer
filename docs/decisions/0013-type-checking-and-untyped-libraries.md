# 0013: Type checking and untyped libraries

Date: 2026-11-03. Status: accepted.

## Context

Decision 0003 checks the types with pyright, strictly in `libs/` and `apps/`. Strict mode
needs a known type for every value. The application calls machine learning libraries that
are typed only in part. On 25 lines that call sentence-transformers, rank_bm25, scipy,
torch and numpy, strict mode reported 11 errors. All of them came from rank_bm25 (no
types), scipy (its types are a separate package) and sentence-transformers (partly
typed). torch and numpy are typed.

The VS Code extension Pylance carries its own pyright, so the editor and CI can report
different errors. The pyright package on PyPI also downloads Node.js on its first run,
unless it is installed with its `nodejs` extra.

## Decision

- basedpyright, a fork of pyright, checks the types. It is pinned in the `dev` group,
  installs from PyPI with Node.js inside the package, and its VS Code extension uses the
  version from the lock instead of Pylance.
- `experiments/` and `eval/` stay in standard mode, `libs/` and `apps/` in strict mode
  (decision 0003).
- Untyped libraries in `libs/` and `apps/`, in this order of preference:
  1. They are imported only in the packages with adapters (`explorer-models-local`,
     `explorer-map`).
  2. Official stubs are installed together with their library, for example `scipy-stubs`
     with scipy.
  3. A library without types that several modules use gets a small stub in `typings/`.
     The stub gives the full public signature of each class and function it declares and
     ends with a module `__getattr__` returning `Incomplete`, so the parts it leaves out
     stay usable. The stub applies to the whole repository, experiments included.
  4. Otherwise its calls stay in one adapter module. That module turns off the reports of
     unknown types at its top, with a one-line reason. Its public functions take and
     return typed values, so the code that calls it stays fully strict.
- An ignore comment names the rule (`# pyright: ignore[reportUnknownMemberType]`), and
  an ignore that suppresses nothing is an error. Both hold in the whole repository
  (`reportIgnoreCommentWithoutRule`, `reportUnnecessaryTypeIgnoreComment`).
- `Any` in a function signature is an error outside `experiments/` and `eval/` (ruff
  `ANN401`).

## Consequences

- In a trial, a stub of 8 lines for rank_bm25 and `scipy-stubs` removed the errors of
  rank_bm25 and all but one of scipy. sentence-transformers still needed the adapter
  module with the reports turned off. That module then had no error, and the code that
  called it none either.
- The rule that untyped libraries stay in the adapter packages rests on deptry and on
  review. deptry reports an import that a package does not declare, but a library added
  to the core's `pyproject.toml` passes it (decision 0011).
- The editor and CI report the same errors once the basedpyright extension is installed
  in VS Code.
- basedpyright checks the code for all platforms by default (`pythonPlatform` is `All`),
  pyright only for the platform it runs on. Code for Windows and for Linux is therefore
  checked the same way on the notebook and in CI.
- `scipy-stubs` follows the version of scipy (1.18.1.1 for scipy 1.18.1), and its helper
  `numpy-typing-compat` follows numpy, so they move together with those libraries.
- A community maintains basedpyright, not Microsoft. It reads the same settings as
  pyright, so going back means one line in the `dev` group and the name of one section in
  `pyproject.toml`.

## Alternatives considered

- **pyright.** It reported the same 11 errors in the trial and none in the experiments.
  The editor can run a different version than CI.
- **pyrefly** (Meta). Stable since May 2026, but a different checker with its own rules
  and configuration, so the experiments would have to be checked again under new rules.
- **ty** (Astral). Still a beta (version 0.0.96).
- **Stubs for every untyped library.** More work than the few calls into rank_bm25 or
  hdbscan justify.
- **No type checking in the adapter packages.** The typed boundary between the adapters
  and the rest of the code would be lost.
