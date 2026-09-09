# Use cases

What the system should do for whom. This is the working list the design is built around;
formal requirements will grow out of it later. Each use case has a short scenario and
acceptance criteria that tell us when it works.

## Actors

Roles that directly use the system. They are a subset of the stakeholders; other
stakeholders (university leadership, the library as data owner, thesis authors whose
texts are exposed) shape requirements but do not operate the system themselves.

- **Student**: picks a thesis topic, writes a related-work chapter, or looks for
  a supervisor. Knows their subject, does not know the repository.
- **Visitor**: applicant, journalist, or curious member of the public. Wants to see
  what the university works on, in plain terms.
- **Teacher**: supervises theses, sits on committees. Wants an overview of what has
  already been written in an area and who supervises what.
- **Operator**: library or faculty staff running the service. Cares about keeping the
  index fresh and the service healthy.
- **Maintainer**: developer or researcher evolving the system. Cares about comparing
  models and configurations without rebuilding everything.

## UC1: Search by meaning

**Student** types a query in natural language, for example "conditional branching in C#".
The system returns a ranked list of theses whose content matches the meaning of the
query even when the wording differs. Each result links back to the thesis record in DSpace.

Accepted when:

- A thesis titled almost identically to the query ranks at or near the top.
- Queries phrased differently than the thesis text still find it (synonyms, paraphrase).
- Results are returned in a few seconds at most.

## UC2: Search across languages

**Student** searches in Czech, relevant theses written in English still show up, and the
other way around. "strategická videohra" and "strategy videogame" lead to the same works.

Accepted when:

- The same query in Czech and in English returns substantially the same top results.
- A Czech query finds relevant English-written theses and vice versa.

## UC3: Narrow results with filters

**Student** limits search results by faculty, year range, language, or thesis type
(bachelor, master, dissertation). Filters combine with the text query.

Accepted when:

- Filters apply without re-typing the query and update results immediately.
- Filter values come from repository metadata, not from free text.

## UC4: Explore the neighborhood of a thesis

**Student** opens a thesis (from search results or from the map) and sees the works most
similar to it, as a small graph or list they can keep expanding. Similarity is based on
content, not citations.

Accepted when:

- Every thesis detail offers its nearest neighbors with a similarity indication.
- The user can walk from neighbor to neighbor without going back to search.

## UC5: Understand why two theses are similar

**Student** or **teacher** looks at a pair of similar theses and can read a short
generated text explaining what the two works share: topic, method, data, domain.

Accepted when:

- The explanation names concrete shared aspects and is verifiable against both texts.
- The explanation never invents content that is not in the theses.

## UC6: Browse the topic map

**Visitor** opens an interactive map of the whole corpus where theses cluster by topic,
clusters have readable labels, and zooming reveals finer structure. Clicking a point
opens the thesis.

Accepted when:

- The map renders tens of thousands of points smoothly in a regular browser.
- Cluster labels are understandable to a non-expert.
- The map supports the same filters as search (faculty, year, type).

## UC7: See how topics evolve over time

**Teacher** or **visitor** views the volume of theses per topic across years, for
example the rise of machine learning topics. The view is linked with the map: picking
a topic highlights it there.

Accepted when:

- The chart shows per-topic volume by defense year and reacts to filters.
- A topic can be followed from the chart to the map and to the list of its theses.

## UC8: Get an AI overview of a question

**Visitor** asks a question, for example "what has been written here about medieval
manuscripts?", and gets a short generated summary answering it, with references to the
specific theses it draws from. The answer is a single response; the system does not
carry on a conversation.

Accepted when:

- Every claim in the summary is backed by a reference to a concrete thesis.
- Referenced theses actually exist and are relevant to the question.
- When the corpus has nothing to say, the system says so instead of making something up.

## UC9: Find a potential supervisor

**Student** searches a topic and can see who supervised the relevant theses, and browse
by supervisor: what topics they cover, how many works, in which years.

Accepted when:

- Search results and the map can be grouped or colored by supervisor or department.
- A supervisor view lists their supervised theses and dominant topics.

## UC10: The index stays fresh on its own

The system periodically syncs with DSpace by itself: newly defended theses get indexed,
errata and takedowns propagate, and affected works are re-indexed or removed. Nobody adds
theses by hand. The **operator** only watches that the sync runs and steps in when it
reports a problem.

Accepted when:

- New theses appear in search within a scheduled interval (for example weekly) with no
  manual action.
- Removing or correcting a thesis in the source removes stale content from results
  automatically.
- Sync runs without downtime and reports its outcome somewhere the operator can see.

## UC11: Swap a model and compare configurations

**Maintainer** switches the embedding model, search strategy, or overview LLM through
configuration, indexes the corpus with the new setup, and compares result quality with
the previous one on a fixed query set.

Accepted when:

- Changing a model requires configuration change only, no code change.
- Two configurations can exist side by side and be queried for comparison.

## Out of scope for now

- Iterative chat over the corpus. The AI overview (UC8) deliberately gives one answer
  and ends there.
- Exposing the search to external AI tools (for example as an MCP server). Noted as
  a future idea.
- Abuse resistance beyond the basics. The repository publishes errata for theses (for
  example GDPR redactions), and search must not become a tool for digging up redacted
  or problematic passages. The full answer needs a dedicated design later; for now the
  system serves only current versions of theses (see UC10).
