# Experiment 02: evaluation set

Which fixed corpus, queries and relevance judgments let us compare search setups with each
other and with the current DSpace search? The experiment builds the pilot version `v0` of
the set in [eval/](../../eval/README.md).

Done except the human check of layer 2, 2026-09-24. Corpus: 592 theses. Builds on:
experiment 01. LLM: `gpt-oss-120b` on e-INFRA CZ.

| Query type | Queries | Written from | Tests |
| --- | --- | --- | --- |
| `title` | 154 | the original and the translated title | the obvious case, easy for BM25 |
| `about-short` | 114 | title, keywords and abstract, by the LLM | a short query as typed into a search box |
| `about-sentence` | 158 | the same, by the LLM | a natural question, search by meaning |
| `detail` | 160 | a passage from the body, by the LLM | the value of the full text |
| `topic` | 6 × 2 | the list of sampled departments, by hand | graded relevance of many theses |

The corpus draws 25 whole departments of six faculties (MFF, FF, PřF, 1. LF, PF, FSV) with
20 theses each and adds the theses of experiment 01. Theses of one department overlap in
topic, so a search can confuse them, which a thin sample of the whole university would not
offer. Known-item queries exist for 80 target theses, each in Czech and English; in 311 of
the 586 the query language differs from the language of the thesis. The LLM comes from
a different model family than the embedding models compared, and every raw answer is
stored with its prompt.

Metadata stands in the thesis text word for word: BM25 finds a thesis by its title at
rank 1 in 93 of 100 cases, and by the first words of its abstract in the other language in
22 of 30. Queries copied from metadata therefore test neither search by meaning nor search
across languages. A first limit of 50 % title words removed natural questions on which BM25
is strong and would have inflated the advantage of semantic search; the final limit drops
only near copies of the title (above 80 %). Even so the pilot set is easy: BM25 alone finds
90 % of the targets in the top 10, and version v1 needs a larger or denser corpus.

For the 6 topics, the top 20 of the seven setups of experiment 03 pooled 276 theses (38 to
63 per topic), which covers the whole top 10 of every setup. The LLM graded 16 of them as
relevant, 49 as partially relevant and 211 as not relevant; the topic on neural machine
translation got no relevant thesis at all, although the corpus holds 24 theses of the
institute of formal and applied linguistics. A blind sample of 30 pairs for a human check
is prepared in `data/eval-v0/validation.md`; until it is graded, topic scores rest on the
LLM alone.

Reproduce: `build_pilot_corpus.py`, `generate_queries.py` and `topics.py add`, then the
setups of experiment 03, then `topics.py judge` (needs `EINFRA_API_KEY` in `.env`).
