# 0024: Pinned versions, the audit of dependencies and the check of prose

Date: 2026-11-17. Status: accepted. Since decision 0025, CI checks the title of a pull
request instead of its commits.

## Context

The workflows named their actions by tags such as `actions/checkout@v4`. The author of an
action can move a tag to other code, and CI would run it, `live.yml` with the key of
e-INFRA. GitHub calls a full commit SHA the only way to use an action as an immutable
release. The runners were `ubuntu-latest`, which GitHub moves to Ubuntu 26 from
19 October 2026, and the image of `test-db` was named by a tag that a new minor release of
PostgreSQL can replace (decision 0020).

`uv audit`, experimental in uv 0.13, compares `uv.lock` with the vulnerability database OSV.
On 17 November 2026 it found 62 known vulnerabilities, all in the group `experiments`:
24 in pypdf 6.18.0 and 19 in each of the two builds of torch 2.6.0. Without that group it
found none in 23 packages.

On a pull request, GitHub tests a merge commit that it builds itself, with the subject
`Merge <sha> into <sha>`. The job `commit-messages` checked it too, so every pull request
failed.

The rules of writing in CLAUDE.md were checked only by a hook of Claude Code on the
notebook of the author, and only in text that Claude writes.

## Decision

Pinned versions:

- Every action in a workflow names a full commit SHA, with its version in a comment.
  `tools/check.py` fails on an action without one.
- Every job runs on `ubuntu-24.04`. A move to a newer Ubuntu is a change in the diff.
- `compose.yaml` names the image of `test-db` by its tag and its digest.

Dependabot:

- Once a month it opens one pull request for all actions and one for the image of
  `test-db`. Its commit subjects start with `chore(deps):`, the form of decision 0023.
- Python packages get no version updates. The group `experiments` keeps the versions that
  produced the reported results, and the tools are raised deliberately (decision 0012).
  Dependabot also rewrites the lower bounds in `pyproject.toml` for uv.
- When `web/package.json` exists, `tools/check.py` fails until `.github/dependabot.yml`
  has an entry for npm.

The audit of dependencies:

- `tools/check.py` runs `uv audit` without the group `experiments`, so the main job of CI
  does it on every push. `live.yml` does it once a week too, so a vulnerability published
  between two pushes shows within a week. The job `live-runs` already fails when that run
  has not passed for 8 days.
- The experiments are left out: nothing deploys them, and their versions must not change.
- An exception is a line in `tools/audit-ignore.txt` with the ID and the reason. It holds
  only while no fixed version exists (`--ignore-until-fixed`), then the check fails again.

Commit messages on pull requests:

- The job `commit-messages` checks the commits from the merge base to the last commit of
  the pull request, without the merge commit of GitHub.

The check of prose:

- `tools/prose.py` reports what the writing rules forbid: an em dash, a dash or a double
  hyphen with spaces as a separator, a semicolon in Markdown prose, and the words of the
  list. It reads Markdown outside code, the comments and docstrings of Python, and commit
  subjects.
- It checks only added and changed lines: in the git hooks against HEAD, in the job
  `commit-messages` over the pushed range or the pull request. Older text stays until
  someone edits its line, otherwise the 29 lines with a semicolon in 9 files would block
  every change of those files.
- A finding stops the commit or CI. A listed word that is the right term in its place
  passes with `prose: allow` on its line, which the diff shows.
- The list is `tools/prose-words.txt`, a copy of the typography and the English part of
  the global list of the author, because CI cannot read files outside the repository. On
  the notebook, `tools/check.py` fails when the copy differs, and
  `python tools/prose.py --update-words` copies it again.

## Consequences

- An update of an action or of the image arrives as a pull request that the author reviews
  like any other change.
- A pull request of Dependabot is merged by squash or rebase, until the rules of merging
  are decided, because a merge commit on `main` fails the check of commit messages.
- A new vulnerability in a dependency of the application or the tools stops CI until the
  dependency moves to a fixed version or gets an exception.
- uv calls `uv audit` experimental, so any new release of uv, a patch release too, can
  change its options. A changed option fails the step until `tools/check.py` follows it.
- The main job of CI and every run of `tools/check.py` need the service OSV. When it is
  down or the notebook is offline, the audit fails like any other check.
- Dependabot has not run on this repository yet. Whether it finds `compose.yaml` under
  that name shows in its first run.
- Decision 0020 no longer holds where the tag of the image alone fixes it.

## Alternatives considered

- **Tags of actions with Dependabot.** A tag can move without a pull request.
- **The setting of GitHub that requires SHAs.** It works only on GitHub, while the check
  in `tools/check.py` also runs on the notebook.
- **Dependabot for uv.** It would raise the frozen versions of the experiments and
  rewrite lower bounds.
- **pip-audit.** It audits an installed environment or a requirements file, so it would
  need an export from `uv.lock` first.
- **Vale.** One more program outside uv, with its own format of rules, next to a list
  that already exists.
- **Checking whole files.** The old semicolons would block every change of their files.
- **Warnings instead of errors.** A warning that only shows in a log gets overlooked.
