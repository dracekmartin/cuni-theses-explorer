# 0002: Containerization

Date: 2026-09-09. Status: accepted.

## Context

The system must be easy to run: by the author on Windows, by the supervisor or
a reviewer who wants to try it, and later in production on whatever infrastructure
the university provides. The deployment target is not known yet, so the setup cannot
assume one particular environment.

## Decision

**Docker Compose is how the system runs.** The goal state: `git clone`,
`docker compose up`, working system.

- Services: PostgreSQL from the official pgvector image, the API from a python-slim
  image, the web UI built with Node and served by nginx.
- Batch pipeline steps run as one-off compose commands (or profiles) against the same
  database service.
- Model files and other large caches live in named volumes, not inside images.
- `experiments/` are exempt and run in a plain virtualenv. Packaging them would slow
  down iteration and they are not deployed anywhere. The application is what gets
  containerized.

## Consequences

- The system runs the same way on the development machine and on any server with
  Docker, so the unresolved deployment question does not block development.
- Dockerfiles and the compose file are code and get reviewed like the rest.
- A local virtualenv stays around for tooling (lint, typecheck, tests); everyday
  commands do not have to go through containers.

## Alternatives considered

- **No containers, setup documented in the README.** The steps differ between
  operating systems (paths, Postgres extensions, system packages) and break easily,
  and everyone who wants to run the project repeats the setup work.
- **Kubernetes with Helm charts.** Built for fleets of machines and rolling
  deployments. A single-node thesis system uses none of that, and the configuration
  would grow several times over.
- **Nix or devcontainers.** Reproducible, but the tooling is unfamiliar to most
  people who might want to run the project.
