# CLAUDE.md

Semantic search and visualization over Charles University theses, built as the practical
part of a master's thesis (MFF UK, software and data engineering). The corpus comes from
the university [DSpace repository](https://dspace.cuni.cz/). Three pillars: hybrid
semantic + fulltext search (language-independent), corpus visualizations (topic map,
thesis neighborhood), and AI overview (grounded answer summaries). The thesis assignment
and ideation documents live in the sibling repo `dracekmartin/diplomkaManagement`.

## Repository map

- `docs/`: use cases, architecture (`architecture.md`, C4 model in `workspace.dsl`, SVG
  views in `diagrams/` rendered by `diagrams/render.sh`), design decisions
- `docs/decisions/`: design decision records, **the source of truth for decisions**.
  Never contradict a recorded decision silently: change the record (or add a superseding
  one) first.
- `experiments/NN-name/`: self-contained experimental probes, numbered in order; each
  README follows `experiments/TEMPLATE.md`
- `eval/`: versioned evaluation data (corpus, queries, relevance judgments) and the
  scorer, see `eval/README.md`
- `data/`: local experiment data (PDFs, extracted texts, indexes, runs), git-ignored
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
  If a sentence sounds like generated boilerplate, rewrite it. `tools/prose.py` checks the
  changed lines of Markdown, comments, docstrings and commit subjects. A listed word that
  is the right term in its place keeps `prose: allow` on its line (decision 0024).
- **Commits:** one-line Conventional Commits. The scope names the folders that the commit
  changes, several as `feat(eval, experiments)`, and a change of the setup of the whole
  repository may have none. `main` stays linear: a commit lands directly or by
  a fast-forward from a worktree branch, never by a merge commit. Pull requests come only
  from Dependabot and are squashed (decision 0025).
- **Naming:** domain terms are shared between code, diagrams and the thesis text (Thesis,
  Chunk, Searcher, Setup, Step, EmbeddingProvider, TopicMap, Overview). Introduce new
  domain terms consciously and document them in `docs/architecture.md`.
- **Evaluation:** experiments do not compute retrieval metrics themselves. Each search
  setup writes a TREC run and `eval/score.py` scores it against a version in `eval/`;
  every result names that version. A version is frozen once a result has been reported
  against it, and changes make a new version. The table of search setups in
  `experiments/README.md` holds every setup with its newest result and status, and an
  experiment that adds or reruns a setup updates it.
- **Dependencies:** never install with pip, `uv sync` removes everything that is not in
  `uv.lock`. Run `uv sync` from the repository root: in a package folder it keeps only
  that package and removes the rest from `.venv`. Add a library to a package with
  `uv add --package <package>`. Tools and libraries of the experiments go into
  `--group dev` or `--group experiments` with an exact version (`name==1.2.3`).
- **Application code:** the rules for `libs/`, `apps/` and `web/` live in
  `.claude/rules/application.md`, which Claude Code loads with a file there (decision 0026).

## Quality gates

`uv sync` installs the workspace, the tools and the experiment dependencies. Before the
review of a change, `uv run tools/check.py --fix <files of the change>` fixes those files
and runs the checks of the main CI job. Never let ruff fix the whole tree, another chat may
have work in it. The script needs Docker for the database of the tests, and it turns on
the git hooks (decision 0023).

## Quality boundary

- `experiments/` is a lightweight regime: single-purpose scripts, typed, cleanly named
  and structured into functions, but without the full test apparatus. They are probes,
  not products. They are still visible in the repo, so keep them presentable.
- `eval/` follows the experiments regime, except that its metric code has unit tests,
  because every comparison in the thesis depends on it.
- `apps/` and `libs/` are the full regime: tests required, public
  interfaces documented, modularity per the architecture doc. Anything from
  `experiments/` that proves permanent gets rewritten into `libs/` properly.

## Working agreement

**Every commit is reviewed and approved by the author before it is made.** Claude (or any
assistant) assists with changes in the working tree and stops; the commit and push happen
only after the author has reviewed the diff and explicitly approved it. Never commit or
push autonomously.

## Maintenance rule

Any commit that changes repository structure, conventions, or an architectural decision
must update CLAUDE.md (and the relevant decision record) in the same commit. A rule for the
code in `libs/`, `apps/` or `web/` goes into `.claude/rules/application.md` instead.

Keep this file short and dense. Every rule in it must be (a) not derivable from the
repository itself and (b) something that would get done wrong if it were missing.
Anything else belongs in docs/ or nowhere.
