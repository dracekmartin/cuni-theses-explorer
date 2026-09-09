# CLAUDE.md

Semantic search and visualization over Charles University theses, built as the practical
part of a master's thesis (MFF UK, software and data engineering). The corpus comes from
the university [DSpace repository](https://dspace.cuni.cz/). Three pillars: hybrid
semantic + fulltext search (language-independent), corpus visualizations (topic map,
thesis neighborhood), and AI overview (grounded answer summaries). The thesis assignment
and ideation documents live in the sibling repo `dracekmartin/diplomkaManagement`.

## Repository map

- `docs/`: use cases, architecture (with diagrams), design decisions
- `docs/decisions/`: design decision records, **the source of truth for decisions**.
  Never contradict a recorded decision silently: change the record (or add a superseding
  one) first.
- `experiments/NN-name/`: self-contained experimental probes, numbered in order
- `data/`: local experiment data (PDFs, extracted texts, indexes), git-ignored
- `apps/`, `libs/`: (future) the real application code

## Conventions

- **Language:** everything in this repository is written in English: code, identifiers,
  comments, commits, and documents. The only exception is user-facing UI text of the
  application, which will be localized (Czech first).
- **Writing style:** applies to every piece of persistent text: documents, code
  comments, commit messages, UI strings, log messages. Write like a person, not like
  a press release. Plain sentences, concrete statements, no filler, no AI-flavored
  rhetorical tics (such as "X matters:", "not just X, it's Y", "One shot, not a chat").
  No em dashes anywhere; restructure the sentence or use a comma, colon, or parentheses.
  If a sentence sounds like generated boilerplate, rewrite it.
- **Commits:** Conventional Commits, `feat|fix|docs|chore|refactor|test|ci(scope): description`.
  Enforced by a pre-commit hook; run `pre-commit install` once after cloning.
- **Naming:** domain terms are shared between code, diagrams and the thesis text
  (Thesis, Chunk, EmbeddingProvider, SearchStrategy, TopicMap, Overview). Introduce new
  domain terms consciously and document them in `docs/architecture.md`.

## Quality gates

Run before pushing (CI runs the same):

```sh
ruff format --check .
ruff check .
pyright
pytest
```

## Quality boundary

- `experiments/` is a lightweight regime: single-purpose scripts, typed, cleanly named
  and structured into functions, but without the full test apparatus. They are probes,
  not products. They are still visible in the repo, so keep them presentable.
- `apps/` and `libs/` (once they exist) are the full regime: tests required, public
  interfaces documented, modularity per the architecture doc. Anything from
  `experiments/` that proves permanent gets rewritten into `libs/` properly.

## Working agreement

**Every commit is reviewed and approved by the author before it is made.** Claude (or any
assistant) assists with changes in the working tree and stops; the commit and push happen
only after the author has reviewed the diff and explicitly approved it. Never commit or
push autonomously.

## Maintenance rule

Any commit that changes repository structure, conventions, or an architectural decision
must update CLAUDE.md (and the relevant decision record) in the same commit. When `apps/` is created,
it gets its own subordinate CLAUDE.md.

Keep this file short and dense. Every rule in it must be (a) not derivable from the
repository itself and (b) something that would get done wrong if it were missing.
Anything else belongs in docs/ or nowhere.
