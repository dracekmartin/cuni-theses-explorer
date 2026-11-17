# 0026: Where the rules of the repository are written

Date: 2026-11-17. Status: accepted.

## Context

CLAUDE.md had 151 lines, and 64 of them held only for the code in `libs/`, `apps/` and
`web/`. A chat that works on the experiments or the evaluation loaded them anyway. Its
Maintenance rule asked for a subordinate CLAUDE.md once `apps/` exists, but Claude Code
loads a subordinate CLAUDE.md only for its own folder, while the rules hold for `libs/`
and `apps/` together.

Claude Code recommends less than 200 lines for a CLAUDE.md and moving rules for a part of
the code into rules with paths in `.claude/rules/`. Such a rule loads when Claude reads,
writes or edits a file that matches its paths.

## Decision

- CLAUDE.md holds the rules for the whole repository. The rules for the code in `libs/`,
  `apps/` and `web/` live in `.claude/rules/application.md`, with these folders as its
  paths.
- A rule that a tool checks and explains in its own message stays out of both files, such
  as the imports of a package (deptry), the place of a subpackage in the layers
  (import-linter) and the form of a commit message (the git hook). The records of
  decisions keep the reasons, the two files a short rule with the number of its record.
- The repository has no hooks of Claude Code. The git hooks and CI check the same for
  people and for AI.

## Consequences

- CLAUDE.md has about 90 lines, and the rules of the application load only with its code.
- Other coding agents do not read `.claude/rules/`. A person finds the file through
  a line in CLAUDE.md.
- The Repository map of CLAUDE.md still calls `apps/` and `libs/` future code.

## Alternatives considered

- **A CLAUDE.md in `libs/` and in `apps/`.** Each would load only for its folder, so the
  shared rules would need a copy or an import in both.
- **Everything in CLAUDE.md.** Every chat would load the rules of the application.
- **Hooks of Claude Code that run the checks.** They would hold only for Claude, while the
  git hooks hold for every commit.
