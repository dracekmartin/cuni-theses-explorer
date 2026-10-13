# Experiment 02: evaluation set

Which fixed corpus, queries and relevance judgments let us compare search setups with each
other and with the current DSpace search? The experiment builds the versions of the set in
[eval/](../../eval/README.md): the pilot `v0` and `v1`.

v0 done 2026-09-24, v1 done 2026-10-13, the human check of layer 2 postponed. Corpus: 592
theses (v0), 5,029 (v1). Builds on: experiments 01 and 04. LLM: `gpt-oss-120b` on
e-INFRA CZ.

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

Version v1 keeps all theses of v0, so their queries stay valid, and adds 4,437 theses of
120 departments drawn from all 17 faculties of the full harvest (experiment 04): a
department with probability proportional to its size, at most 40 theses from one, only
theses marked as defended or without a recorded outcome, with an open body text of at
least 20 KB. The 80 targets of v0 keep their 586 queries, and 120 targets from the new
part add 892, so v1 has 1,478 known-item queries. Of the 25 topics, 6 come from v0 and 19
were written for the drawn departments, so that every faculty has one. Their description
of relevance was first in English and used terms a non-expert grader could not judge by,
so it is written in plain Czech, and the LLM judged against the same Czech text.

The top 10 of the 14 setups of experiment 05 and of the two DSpace runs pooled 1,172 pairs
of topic and thesis (1,033 distinct theses) for the 25 topics. The LLM graded 703 as not
relevant, 314 as partially relevant and 155 as relevant, and none as relevant for neural
machine translation or for pressure ulcers. 883 theses of the corpus (18 %) have no
abstract in DSpace, so a grader sees only their title and, for 414 of them, keywords. A
blind sample of 150 pairs of all 1,172, 50 for each LLM grade, waits on a local page for a
person to grade (`topics.py sample` writes it, the key N marks a pair that cannot be
decided).

The human check is postponed until these weaknesses of v1 are settled:

- Relevance is judged from the title, keywords and abstract alone. A thesis that treats the
  topic in one chapter gets too low a grade, which favours setups that match abstracts over
  setups that find passages in the full text. Two remedies: show the two or three passages
  of the thesis that match the topic best, and take a missing abstract from the body text,
  where it usually stands on one of the first pages.
- 883 theses (18 %) have no abstract in DSpace and are judged by their title and, for 414
  of them, keywords. Some abstracts are damaged: HTML entities in those of 131 theses, a
  lost letter (ř as Z) in 2, page numbers and headers copied from the PDF.
- Claude wrote the topics from the list of departments, not users, and two topics have no
  relevant thesis.
- The pool holds only what some setup put into its top 10, so recall is unknown, and a new
  setup brings unjudged theses that must be judged before its topic score counts.
- The sample takes 50 pairs per LLM grade, while 60 % of the pool has grade 0, so its
  agreement has to be reweighted to stand for the pool.
- One grader without expertise in most of the fields checks the judge, and the model of the
  judge is not pinned on e-INFRA.
- Experiment 05 chose the number of summed chunks on the same topics, which need a set of
  their own for such choices.

Reproduce v0: `build_pilot_corpus.py`, `generate_queries.py` and `topics.py add`, then the
setups of experiment 03, then `topics.py judge` (needs `EINFRA_API_KEY` in `.env`). The
blind sample of v0, `data/eval-v0/validation.md`, came from the judge step of that time
and stays as it is. For v1
the same scripts run with `EVAL_VERSION=v1`, `build_v1_corpus.py` in place of the first,
and the setups of experiment 05, then `topics.py sample` and, with the saved grades,
`topics.py agreement --grades validation-grades.json`.
