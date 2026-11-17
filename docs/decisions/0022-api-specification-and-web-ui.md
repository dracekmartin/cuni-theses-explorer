# 0022: The API specification and the web UI under the control of CI

Date: 2026-11-17. Status: accepted.

## Context

The API is public, with its version in the path (`/v1`) and an OpenAPI specification, so
that a change does not break clients (architecture, section 7.6). Besides the web UI,
scripts and later AI assistants call it, so it gets inputs that nobody planned for. The
web UI is a separate TypeScript and React application with an API client generated from
the specification (architecture, section 3), and its texts can be replaced, Czech and
English first (section 7.7).

Neither the API nor the web UI has code yet. Like the other checks (decision 0021), the
checks below run in CI and start by themselves when the code arrives.

## Decision

The specification in the repository:

- FastAPI builds the OpenAPI specification from the code. The file
  `apps/explorer-api/openapi.json` keeps it, indented, in the repository, and a command of
  `explorer-api` writes it again. Nobody edits it by hand.
- A test compares the file with the specification that the code gives and fails when they
  differ. Its message names the command. A change of the API thus shows in the diff that
  the author reviews before every commit.
- Once `explorer-api` imports FastAPI, the job `api-compat` of CI fails while the file is
  missing.

Breaking changes:

- A release is a version that the public API runs. It gets a git tag `vX.Y.Z`, and a tag
  with a suffix, such as `v1.0.0-rc.1`, is not a release.
- The job `api-compat` compares `openapi.json` with the file of the newest release tag in
  the history of the commit, using oasdiff. It fails on the changes that oasdiff counts as
  breaking or as possibly breaking, such as a removed field, a new required parameter or
  a new value of an enum in a response.
- Changes between two releases do not count, because no client saw the state in between.
  Until a release contains `openapi.json`, the job passes with a message, so the check
  starts with the first release of the API.
- A breaking change goes into a new version of the path, `/v2`, next to `/v1`. An old
  operation is removed only after a release marked it `deprecated`, and only after its
  date in `x-sunset` when it has one. oasdiff checks both.
- A possibly breaking change that the author accepts, such as a new language in an enum,
  gets a line in `apps/explorer-api/openapi-warn-ignore.txt`: the method, the path and the
  text of the warning, followed by the reason. The exception then shows in the diff.

Generated tests of the API:

- Schemathesis generates requests for every operation from the specification, with
  Hypothesis, and calls the application in the process, without a server.
  `call_and_validate` runs the checks of Schemathesis. Among them, no response has
  a status 5xx, and status codes, content types, bodies and headers match the
  specification.
- The test runs over a synthetic corpus in `test-db` with the fake models, so it is marked
  `db` and runs in the main job of CI. The endpoints for maintainers get a login made for
  the test.
- The API refuses a setup with a fake model when it starts (decision 0018). This test and
  the tests in the browser build the application through code in the tests of
  `explorer-api`, which allows the fake models. The installed program keeps refusing them.

The code of the web UI:

- The web UI lives in `web/`. In `apps/`, uv would take it for a member of the workspace.
- npm installs it from `package-lock.json` with exact versions, and `web/.node-version`
  pins Node, as `uv.lock` and `requires-python` do for Python (decision 0010).
- TypeScript runs with `strict`. ESLint checks the code with the type-aware rules of
  typescript-eslint and the official rules of React hooks, Prettier checks the format, and
  Vitest runs the unit tests.
- ESLint forbids text written into JSX by `react/jsx-no-literals` with `noStrings`, and
  with `restrictedAttributes` for the attributes that a user reads or hears: `alt`,
  `title`, `placeholder`, `label`, `aria-label`, `aria-description`,
  `aria-roledescription` and `aria-valuetext`. Texts thus go to the catalogs of
  translations. A test checks that the Czech and the English catalog have the same keys.
- openapi-typescript generates the types of the API client from
  `apps/explorer-api/openapi.json` before the type check and before the build. The
  generated file stays out of git. A change of the API that breaks the web UI fails the
  type check in CI.

Tests in the browser:

- Playwright walks a few paths of a user in Chromium: a search, the detail of a thesis, the
  topic map and the switch of language. It runs against the real API with a synthetic
  corpus in `test-db` and the fake models.
- On every page of these paths, axe checks accessibility with its rules for WCAG 2.0 and
  2.1 at the levels A and AA (tags `wcag2a`, `wcag2aa`, `wcag21a`, `wcag21aa`). Directive
  (EU) 2016/2102 asks this level of the websites of public bodies, through EN 301 549.
  A missing label or a low contrast fails the test.

The job `web`:

- It runs on every push to `main` and every pull request. It starts `test-db`, installs
  `explorer-api`, runs `npm ci` and then the scripts `lint`, `typecheck`, `test` and `e2e`
  of `web/package.json`. The script `e2e` starts the API and the web UI itself, so a run
  on the notebook does the same as CI.
- The job installs `explorer-api` without the groups `dev` and `experiments`. The script
  `e2e` therefore starts the API with `uv run --no-sync`, and the code that starts it uses
  nothing from those groups.
- Until `web/package.json` exists, the job does not run (decision 0021, empty runs).

## Consequences

- Every change of an endpoint shows in `openapi.json`, so a review of the API happens in
  the diff.
- After the first release, a breaking change of `/v1` needs `/v2`, or a deprecation in
  a release before the operation goes.
- `explorer-api` gets Schemathesis in the group `dev` with its first endpoint. The web UI
  brings Node and npm into CI.
- ESLint and Prettier run only in CI so far. Which checks run before a commit too is open.
- The Repository map in CLAUDE.md does not list `web/` yet, and the deployment
  (architecture, section 6) does not say yet that the public API runs only releases.

## Alternatives considered

- **Biome instead of ESLint and Prettier.** One fast tool, like ruff for Python. Its rule
  for React hooks is a port with known differences, and only typescript-eslint has rules
  that need types, such as a forgotten `await`.
- **The specification only generated in CI.** A change of the API would not show in the
  diff before a commit.
- **Comparing with `main` instead of the last release.** Every breaking change during
  development would need a new version, although no client saw it.
- **A minimum period of deprecation checked by oasdiff** (`deprecation-days-stable`).
  oasdiff counts the days from the day of the run, and the base is the last release. CI
  would fail from the day after a deprecation until the next release.
- **Failing only on breaking changes, not on possibly breaking ones.** A warning that
  only shows in the log gets overlooked.
- **Generated types committed in `web/`.** A second copy of the specification that can
  drift from the first.
- **Firefox and WebKit in the browser tests too.** They triple the time of the browser
  tests.
