# 0025: Branches, merging and the form of commit messages

Date: 2026-11-17. Status: accepted.

## Context

The repository has one branch, `main`, and no tag. All 89 commits have a subject only, and
their scopes are names of folders: `experiments` 34 times, `eval` 11, `decisions` 3,
`docs` 1. 47 commits have no scope. CLAUDE.md did not say what a scope means.

Chats of Claude Code work either in the main working tree, where a switch of the branch
would change the files of the other chat, or in a worktree of their own with a local
branch. The skills of the author bring such a branch back to `main` by rebase or cherry-pick
and a fast-forward (`/wtm`, `/streams`), never by a merge commit. A worktree has no Python
environment of its own until someone runs `uv sync` in it, and Docker Compose names its
project after the folder, so two worktrees would start two `test-db` on one port.

Dependabot opens pull requests (decision 0024). Its commits carry a body with release
notes. A merge commit fails the check of commit messages (decision 0023), and the system
configuration of git on the notebook has `pull.rebase=false`, so a pull over a diverged
`main` would create one. A pull with rebase refuses to start while a tracked file has
changes, which is the normal state when another chat works in the same tree.

## Decision

Branches:

- The history of `main` stays linear. A commit reaches it directly, or by a fast-forward
  from a local branch of a worktree, never by a merge commit.
- Only `main` goes to GitHub, and the author pushes it. Pull requests come only from
  Dependabot.
- No rule of GitHub requires a green CI before a merge. Such a rule fits pull requests, and
  the direct pushes of the author would need an exception from it.

Worktrees:

- The git hooks use the Python environment of their worktree, and the one of the main
  worktree when theirs lacks the tools. A worktree can commit without `uv sync`.
- `compose.yaml` names its project, so every worktree uses the same `test-db`. Tests do not
  collide in it, because each creates databases with names of its own (decision 0020).
- `.gitignore` leaves out `.claude/worktrees/`, where the worktrees of Claude Code live, so
  the checks of the main tree do not read the unfinished work of a worktree.

Merging pull requests:

- A pull request is merged only by "Squash and merge", with the title of the pull request
  as the subject. The settings of the repository on GitHub turn off merge commits and
  rebase merging, and set the message of a squash to the title. The author sets them once
  by hand. A merge commit on `main` that slips through fails CI.
- On a pull request, CI checks its title as the subject, because only the title reaches
  `main`, and runs again when the title changes. The commits inside the pull request may
  have bodies. CI passes the title to the script through an environment variable, so
  a title cannot run as part of the script.

Pulling:

- `tools/check.py` sets `pull.ff=only` and `pull.rebase=false` in the repository, as it
  sets the hooks. A pull then only fast-forwards, also next to the unfinished work of
  another chat, and refuses when `main` diverged.
- `main` diverges only when a pull request of Dependabot is merged on GitHub while local
  commits wait for a push. The author therefore pushes `main` before such a merge.

Commit messages:

- A message is one line, the subject. CI rejects every further line of a stored message,
  trailers included. The hook skips comment lines, because git drops them from a message
  written in the editor, so a line that starts with `#` passed with `-m` shows only in CI.
- The scope names the folders that the commit changes, such as `eval`, `experiments`,
  `docs` or a package of the workspace like `explorer-api`, several separated by a comma
  and a space. Only lower case letters, digits and hyphens fit, so a folder like
  `explorer_api` cannot be a scope. A change of the setup of the whole repository, such as
  CI, the tools or the records of decisions, may have none.
- The hook and CI accept a scope only when it is the name of a folder in the index, in
  HEAD or in the revision before the checked commits, or `deps` and `deps-dev` for
  Dependabot. The names come from the tree, so no list has to be kept up to date, and
  a typo such as `expriments` fails.

Releases:

- A release gets a tag `vX.Y.Z` when the author deploys it (decision 0022).

## Consequences

- The author sets the merge buttons of the repository on GitHub once. Until then, a merge
  by another button shows as a failing CI on `main`.
- When GitHub fills the body of a squash, for example with `Co-authored-by` after the
  author pushed to the branch of Dependabot, the author deletes it before the merge, or CI
  fails on `main`.
- A scope for a new folder works from the commit that adds the folder.
- `git revert` writes a subject `Revert "..."` and a body, so a revert needs its message
  rewritten, for example `fix(eval): revert the change of the scorer`.
- The worktrees of one repository share one `test-db`, so stopping it stops the tests of
  the others too. When their `compose.yaml` differ, for example after a new digest on
  `main`, starting it from one worktree recreates it and drops the databases of the others.
- A worktree that changes the version of ruff in `uv.lock` checks its commits with the ruff
  of the main worktree until it runs `uv sync` itself.
- A diverged `main` needs a rebase by hand when no other chat has unfinished work, because
  a pull refuses it.

## Alternatives considered

- **Branches on GitHub with pull requests.** Every change would go through a pull request,
  while the author reviews each commit before it is made anyway.
- **Rebase merging of pull requests.** It would bring the commits of Dependabot with their
  bodies onto `main`.
- **A fixed list of scopes.** It would need an update with every new folder.
- **No check of scopes.** A typo would stay in the history.
- **`uv sync` in every worktree.** It installs the whole environment, torch included,
  before the first commit.
