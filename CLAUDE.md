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
- **Commits:** Conventional Commits, `feat|fix|docs|chore|refactor|test|ci(scope): description`,
  several scopes as `feat(eval, experiments)`. A git hook in `tools/hooks/` and CI check it.
- **Naming:** domain terms are shared between code, diagrams and the thesis text (Thesis,
  Chunk, Searcher, Setup, Step, EmbeddingProvider, TopicMap, Overview). Introduce new
  domain terms consciously and document them in `docs/architecture.md`.
- **Evaluation:** experiments do not compute retrieval metrics themselves. Each search
  setup writes a TREC run and `eval/score.py` scores it against a version in `eval/`;
  every result names that version. A version is frozen once a result has been reported
  against it, and changes make a new version. The table of search setups in
  `experiments/README.md` holds every setup with its newest result and status, and an
  experiment that adds or reruns a setup updates it.
- **Packages:** `libs/` and `apps/` form a uv workspace (decision 0010). Create a new
  package only for heavy dependencies or a program of its own. Anything else goes into
  a subpackage. A package imports only what its `pyproject.toml` declares, and a new
  subpackage of `explorer` needs a place in the layers in the root `pyproject.toml`
  (decision 0011).
- **Dependencies:** never install with pip, `uv sync` removes everything that is not in
  `uv.lock`. Run `uv sync` from the repository root: in a package folder it keeps only
  that package and removes the rest from `.venv`. Add a library to a package with
  `uv add --package <package>`. Tools and libraries of the experiments go into
  `--group dev` or `--group experiments` with an exact version (`name==1.2.3`).
- **Untyped libraries in `libs/` and `apps/`:** import them only in `explorer-models-local`
  or `explorer_batch.map_builder`. In this order: install their official stubs, or write
  a stub in `typings/` when several modules use the library, or as the last resort keep
  the calls in one module that turns off the unknown-type reports at its top with
  a reason. Its public functions take and return typed values (decision 0013).
- **Docstrings and comments:** a docstring starts with one sentence, on a single line, on
  what the function returns or does. `Args`, `Returns` and `Raises` only where the name
  and the type do not say enough. A comment is one line and says why. A leading
  underscore marks what is internal to its package, and other packages do not import it
  (decision 0012).
- **Synchronous code:** no `async def` in `libs/` and `apps/`, except the lifespan and
  middleware of the API. Parallel work runs only in thread pools that one object owns,
  such as the searcher. Only boundary modules (database, HTTP, files) do input and output,
  and every timeout lives there (decision 0015).
- **Errors:** for a failure that a caller reacts to, raise a subclass of `ExplorerError`
  from `explorer.domain`. Programming errors stay `TypeError` or `ValueError`. A boundary
  module converts the exceptions of its library with `raise ... from err`, and only
  boundary modules retry (decision 0014).
- **Configuration:** every TOML file has a pydantic model, all from one base class with
  `extra="forbid"` and `frozen=True`. Secrets come only from `EXPLORER_*` environment
  variables as `SecretStr`, and an unknown `EXPLORER_*` variable is an error (decision
  0016).
- **Commands:** one typer command per program. Exit codes 0, 1, 2, 75 (run again later)
  and 78 (configuration). A batch command saves and records each unit of work whole, and
  after SIGTERM or Ctrl+C it finishes the units in progress and exits with 75 (decision
  0016).
- **Logging:** code in `libs/` writes to `logging.getLogger(__name__)`, and only
  a program in `apps/` configures logging. A log names a thesis by its id and version,
  never by its text, title, abstract or the names of its people. No IP addresses or
  secrets, and the text of a query only through the logger `explorer.queries` in the
  API. Validation errors without input values, and a library exception whose message can
  carry content is raised again `from None` (decision 0017).
- **Test data:** only synthetic: ids `fake-…`, made-up names, sentences written by hand,
  never a real thesis. The fake encoder and the builders of test data live in
  `explorer.testing`, as plain code without pytest. A test that needs PostgreSQL is marked
  `db`, one that loads a real model `model`, and no test needs a GPU. The name of a test
  describes the behavior it checks (decision 0018).
- **Kinds of tests:** a pure function with a rule that holds for every input (fusion,
  fingerprint, chunking, metrics) also gets a property test with Hypothesis. The contract
  suite of each interface checks what every searcher, step, index builder or model adapter
  promises. It finds the classes in the registry, so a new class changes no existing
  test. Every batch command has a test that stops it, runs it again and compares the
  result with a run that was not stopped (decision 0019).
- **External services in tests:** an HTTP adapter creates its client itself, with its
  timeouts, and takes only a transport from its caller. Its tests pass `MockTransport`
  with responses written by hand, never copied from DSpace or e-INFRA. A test that calls
  a real service is marked `network` (decision 0020).
- **Models and rankings:** a program that uses a model checks the reference outputs of
  `explorer_models_local` when it starts and exits with 78 when they differ. A change of
  a ranking needs a new version of the step that causes it. A setup rewritten from
  experiment 05 carries a passed regression with its fingerprint (decision 0021).
- **API and web UI:** `apps/explorer-api/openapi.json` is generated from the code, never
  edited by hand. A breaking change of a released API needs a new path version (`/v2`).
  The web UI lives in `web/`, outside the workspace (decision 0022).

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
must update CLAUDE.md (and the relevant decision record) in the same commit. When `apps/` is created,
it gets its own subordinate CLAUDE.md.

Keep this file short and dense. Every rule in it must be (a) not derivable from the
repository itself and (b) something that would get done wrong if it were missing.
Anything else belongs in docs/ or nowhere.
