# 0023: Git hooks and one command for the checks

Date: 2026-11-17. Status: accepted.

## Context

Two chats of Claude Code work in one working tree, and every commit names its files
(`git commit --only -- <files>`). Before its hooks, pre-commit saves the changes outside
the commit to a patch, resets those files with `git checkout -- .` and applies the patch
again afterwards, once for the code and once for the message. For a few seconds the other
chat sees its files as they were in the last commit. A write in that moment conflicts with
the patch, and pre-commit drops it without an error. The transcripts of the chats name 74
such patches, and the message of a conflict, `Stashed changes conflicted`, never appears.

The checks took these times on the notebook: ruff check 0.2 s, ruff format 0.1 s,
import-linter 0.5 s, deptry 0.4 s per package, basedpyright 35 s, pytest 13 s.

The commands of the checks were listed twice, in CLAUDE.md and in the main job of CI.
deptry ran nowhere: decision 0011 had left it for the time when the packages get code.

## Decision

Git hooks:

- `tools/hooks/` holds two git hooks, and `core.hooksPath` points git at them. They
  replace pre-commit.
- The hook before a commit runs `ruff format --check` and `ruff check` over the Python
  files of the commit, read from disk. With `git commit --only`, the disk holds exactly
  what the commit takes. The hook stashes nothing and changes no file.
- The hook of the commit message runs `tools/commit_message.py`, which CI runs over every
  pushed commit too. A subject is `type(scope): description` with the types of CLAUDE.md,
  an optional scope of lower case words with hyphens, several scopes separated by a comma
  and a space (`feat(eval, experiments): ...`), and an optional `!` before the colon.
- The hooks only check. A fix made by a hook would change a file after its review.
- Checks over the whole project stay out of the hooks. In a shared tree they would see the
  unfinished work of the other chat and stop a commit for code that it does not contain.
  basedpyright and the tests would also make every commit slower by tens of seconds.

One command:

- `uv run tools/check.py` runs what the main job of CI runs: it starts `test-db`, then
  runs ruff, basedpyright, import-linter, deptry in every package, and the tests without
  the marker `model` with coverage. The main job of CI calls the same script. It runs every
  check also after a failure and lists the failed ones at the end.
- `--fix` followed by the files of a change lets ruff fix and format those files first. It
  runs before the review of the change. A fix of the whole tree would rewrite the
  unfinished work of the other chat.
- A step whose program is missing, such as Docker on the cluster, fails with a message, and
  the other steps run.
- Outside CI, the script sets `core.hooksPath` when it is missing, so the hooks do not
  stay off after a clone. It fails when git keeps a hook without the executable bit.
- The other jobs of CI keep their own steps, because each needs another environment.

deptry:

- deptry runs in every package of `libs/` and `apps/`. A package whose modules hold
  nothing but docstrings cannot use its dependencies yet, so there the script ignores
  DEP002, a declared dependency that nothing imports. The exception ends with the first
  code of the package.

What runs where:

| Where | What | Time |
| --- | --- | --- |
| hook before a commit | ruff over the Python files of the commit | about 1 s |
| hook of the commit message | the form of the subject | under 1 s |
| `tools/check.py`, the CI job `quality` | ruff, basedpyright, import-linter, deptry, the tests without `model` with coverage | 10 min in CI (decision 0019) |
| the CI job `core-without-torch` | `explorer` alone: imports of all modules, its tests | 20 min at most |
| the CI job `models` | the tests marked `model` on the CPU (decision 0021) | 20 min at most |
| the CI job `api-compat` | the API specification against the last release (decision 0022) | 20 min at most |
| the CI job `web` | the web UI (decision 0022) | 20 min at most |
| the CI job `commit-messages` | the subjects of the pushed commits | 20 min at most |
| the CI job `live-runs` | a pass of `live.yml` within the last 8 days | 20 min at most |
| `live.yml`, once a week | the tests marked `network` (decision 0021) | 20 min at most |
| the notebook or the cluster, the result checked in CI | the regression against experiment 05 (decision 0021) | |

## Consequences

- A commit no longer touches files outside the commit.
- After a clone, the hooks run only once `tools/check.py` has run. CI checks the same
  anyway.
- A commit made without `--only`, from a file staged in part, is checked by its content on
  disk, not by the staged content.
- Git on Linux skips a hook without the executable bit. On Windows, `git commit --only`
  records a new file without it, so the bit comes in a commit of its own, made with
  `git update-index --chmod=+x` and a plain `git commit`.
- A subject with several scopes now passes CI, which accepted only one scope before. The
  local hook of pre-commit accepted them, and the history has such commits.
- The hook of pre-commit let merge commits, `fixup!` subjects and types in upper case
  through. They now stop already at the hook, as they did in CI. A `git pull` on a branch
  that diverged needs `--rebase`.
- ruff is pinned only in `uv.lock`, no longer also in `.pre-commit-config.yaml`.
- pre-commit leaves the group `dev`. Decision 0003 no longer holds where it runs the same
  checks at both gates, decision 0011 where deptry waits for code, and decision 0012 where
  ruff is pinned twice.

## Alternatives considered

- **pre-commit with a list of files** (`pre-commit run --files ...`), which stashes
  nothing. The hook of the commit message gets no list of files, so pre-commit would stash
  there anyway.
- **Another hook manager, such as lefthook.** One more tool to install and learn for two
  short hooks.
- **A Makefile or `just`** for the one command. Neither comes with Windows, and the script
  needs only Python.
- **Hooks that fix the code.** The author reviews every commit before it is made
  (CLAUDE.md, Working agreement), and a fix by a hook would change the content after that
  review.
