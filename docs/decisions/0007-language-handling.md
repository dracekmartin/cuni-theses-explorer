# 0007: Language handling

Date: 2026-11-03. Status: accepted.

## Context

In experiment 05, BM25 at the same weight as the dense source hurts queries in another
language than their thesis. BGE-M3 alone reaches MRR@10 0.869 on them, the hybrid with
BM25 and metadata chunks 0.823 (`bge-m3-semantic` against `bge-m3-meta-hybrid`), and the
same hybrid with BM25 at half weight 0.848 (`bge-m3-meta-weighted`). For Czech queries on
Slovak theses it falls from 0.821 to 0.603. A lexical source rarely finds a chunk in
another language than the query. The fusion sums what each branch gives a candidate
(`experiments/05-search-v1/ranking.py`), and a branch that did not find it gives zero. So
the plain sum favors theses in the language of the query.

The language in the metadata (`dc.language.iso`, filled for all 167,082 theses) agrees
with the text in 98.2 % of a sample of 500 theses, and 1.5 % of the theses listed as Czech
have their whole body in English or Slovak. A Czech thesis carries its English abstract in
its text: in a sample of 399 Czech theses, the body holds it in 94.9 % of cases. The
metadata have only a Czech and an English slot, and for 85 % of Slovak theses the Czech
slot holds a Slovak abstract. Slovak theses are a small share, 4,451 (2.7 %). The
experiments lemmatize only Czech and English (`experiments/05-search-v1/common.py`),
although simplemma covers Slovak too, with an accuracy of 0.92.

Many queries have no language: a name, a code, an abbreviation, a formula. In a test of
the library lingua that chose among 75 languages, the best detectors recognize one Czech
word in 65 % and two words in 84 % of cases, and they often confuse Czech with Slovak. On
the queries of the evaluation set v1, written by an LLM with a median of 8 words, simplemma tells Czech from
English in 96.9 %, and with Slovak as a third choice it is right for 85.1 % of the Czech
ones. Real queries will be shorter.

## Decision

- The chunker detects the language of each chunk from its own text, metadata chunks
  included. The thesis keeps the language of its metadata for filters and display.
- Czech, Slovak and English are full languages in the analysis of chunks and queries, each
  with its own lemmatizer, which the lexical builder and the query analyzer share. The
  default is simplemma (MIT). UDPipe, with models under CC BY-NC-SA, is only an optional
  variant, because a non-commercial licence is never the default. If UDPipe wins clearly
  in the evaluation, the supervisor or ÚFAL (the Institute of Formal and Applied
  Linguistics at MFF, which publishes UDPipe) is asked about its licence.
- The query analyzer returns Czech, Slovak or English with a confidence, or no language,
  which is a valid result, not an error. A query without a language searches lexically in
  chunks of all languages, because exact matches of names and codes help most there.
- For a query with a language, the fusion treats a lexical source as blind to chunks in
  other languages, and it knows for each candidate which branches could see it. Its
  configuration sets how it counts a branch that searched and did not find a candidate
  (zero, or a score just below the last hit of that branch) and a branch that could not
  see it (the same way, or left out of the score of that candidate).
- The core supports every way of handling the lexical branch: the fusion rule above,
  lexical search over metadata chunks only, leaving the correction to the reranker, no
  lexical branch, and translation of the query as an optional step that may wait. The
  evaluation decides the default, and whether the language of the UI helps the query
  analyzer on short queries.
- The overview answers in the language of the UI, unless the query analyzer is confident
  that the query is in another language. It can cite chunks in another language.

## Consequences

- An average over the branches that could see a candidate removes the credit that BM25
  gives theses in the language of the query. It also costs theses in the language of the
  query that only the dense source found. With RRF, k = 60, weights 1 and zero for a miss,
  such a thesis at rank 1 gets 1/61 / 2 = 0.0082, while a thesis in another language at
  rank 2 keeps 1/62 = 0.0161. Which effect wins, the evaluation shows. On the whole
  university the cost may come up more often than on the evaluation set v1, because the
  top 200 chunks of BM25 cover a smaller part of about 30 million chunks.
- Lexical search over metadata chunks alone needs no language of the query: in the
  metadata, 156,799 theses (94 %) have a title in Czech and in English, 128,167 both
  abstracts. It loses exact matches in the body. It also keeps lexical search away from
  personal data in full text.
- Leaving the correction to the reranker works already: `bge-m3-meta-rerank`, with BM25 at
  full weight, reaches MRR@10 0.931 on queries in another language. Its cost on a CPU is
  not measured yet, so a node without a GPU may need the fallback setup without the
  reranker (decision 0006).
- For names and codes the lexical source keeps its exact matches in all languages. That
  helped e5-small on rare terms spelled alike in both languages (Artemisia, Databricks) in
  experiment 03. BGE-M3 is not measured yet, and the lemmatizers must not mangle names.
- The evaluation has to measure MRR@10 for queries in the same language (680 in v1) and in
  another language, the share of theses in another language in the top 10, queries with
  names and codes, Slovak queries, and whether Slovak hurts Czech. The evaluation set v1
  has 23 Slovak queries, all on titles, and none with such exact terms. Version v2 of the
  set adds Slovak queries.
- Open: how a query with no language is lemmatized, and which language and lemmatizer
  a chunk in German, French or another language gets (882 German, 542 French and about
  460 other theses).

## Alternatives considered

- **Language of the thesis for every chunk.** No detection at indexing, but the fusion
  rule would drop the credit BM25 gives an English query for the English abstract of
  a Czech thesis. The body chunks of 1.5 % of Czech theses would get a wrong language.
- **A detector without "no language".** Simpler, but a name or a code would get a guessed
  language, and the lexical source would miss its exact matches in the other languages.
- **Translation of every query by default,** by an LLM or by the machine translation of
  LINDAT at ÚFAL, then BM25 in each language, as the search tools Onyx, Primo and Scopus
  AI do. It adds about a second per query and a dependency on an API.
- **Dropping the lexical branch from the core.** No language of the query is needed, but
  on known-item queries (a query for one particular thesis) BGE-M3 with the reranker
  reaches MRR@10 0.933 without BM25, against 0.948 with BM25 and metadata chunks, and
  exact matches of names and codes are lost.
- **UDPipe as the default lemmatizer.** More accurate (99.5 % for Czech), but its models
  are under CC BY-NC-SA, and the project rejected the embeddings of Jina for that reason.
