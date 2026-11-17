---
paths:
  - "libs/**"
  - "apps/**"
  - "web/**"
---

# Rules for the application code

They hold for the code in `libs/`, `apps/` and `web/`, next to the rules of CLAUDE.md.
Claude Code loads this file when it works on a file there (decision 0026).

- **Packages:** `libs/` and `apps/` form a uv workspace (decision 0010). Create a new
  package only for heavy dependencies or a program of its own. Anything else goes into
  a subpackage (decision 0011).
- **Untyped libraries:** import them only in `explorer-models-local` or
  `explorer_batch.map_builder`. In this order: install their official stubs, or write
  a stub in `typings/` when several modules use the library, or as the last resort keep
  the calls in one module that turns off the unknown-type reports at its top with
  a reason. Its public functions take and return typed values (decision 0013).
- **Docstrings and comments:** a docstring starts with one sentence, on a single line, on
  what the function returns or does. `Args`, `Returns` and `Raises` only where the name
  and the type do not say enough. A comment is one line and says why. A leading
  underscore marks what is internal to its package, and other packages do not import it
  (decision 0012).
- **Synchronous code:** no `async def`, except the lifespan and middleware of the API.
  Parallel work runs only in thread pools that one object owns, such as the searcher.
  Only boundary modules (database, HTTP, files) do input and output, and every timeout
  lives there (decision 0015).
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
