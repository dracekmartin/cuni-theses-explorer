# cuni-theses-explorer

Semantic search and visualization over Charles University theses. This is the practical
part of the master's thesis *Semantic Search and Visualization of Charles University
Theses* (MFF UK, software and data engineering).

The university publishes tens of thousands of defended theses in its
[DSpace repository](https://dspace.cuni.cz/), but its search only matches words in the
text. It fails on queries phrased differently than the thesis itself, and the same query
in Czech and in English returns different results. This project addresses that in three
ways:

1. **Search**: combined semantic and fulltext search, independent of the language of the
   query and of the thesis.
2. **Visualization**: an interactive map of theses grouped by topic similarity, with
   generated explanations of what similar theses have in common.
3. **AI overview**: a generated summary answering the user's query, grounded in specific
   theses.

## Repository structure

| Path | Contents |
|---|---|
| `docs/` | use cases, architecture, ADRs (architecture decision records) |
| `experiments/` | experimental probes (small-scale harvesting, indexing, search) |
| `data/` | local experiment data (not versioned) |
| `apps/` | *(later)* the application: pipeline, API, frontend |

## Status

Early stage: documentation and the first experimental pipeline. The quickstart for the
first experiment will live in `experiments/01-mini-pipeline/README.md`.

## Related

The ideation phase of the thesis (assignment, specification, research survey, meeting
notes) lives in the [diplomkaManagement](https://github.com/dracekmartin/diplomkaManagement)
repo.
