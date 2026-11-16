"""Known-item queries of evaluation version v2: the test targets and the exact terms.

The dev part keeps the targets of v1 with their queries. The test part gets 200 new targets
from the corpus of v2, 40 of them Slovak, with the query types of v1: title, about-short,
about-sentence and detail. The targets of both parts get a query of the type exact: a name,
code, abbreviation or number of a law from the thesis, alone or with up to three words.
A query of the term alone has the language of its words, or none (lang null) for a name or
a code. The term must stand in the text of the target and in no other thesis of the corpus,
so that the target is the one right answer, and in at most three theses of the whole
university, so that it stays a good query over all of them (v3).

v2 has no queries the LLM wrote in Slovak, because nobody checks them. A Slovak thesis keeps
its Slovak title as a title query, and an exact term copied from its text.

The LLM (gpt-oss-120b on e-INFRA CZ) writes the queries, and every answer is kept with its
prompt in data/eval-v2/llm/. A check run with --limit N prints the queries of the first N
targets of each part and writes nothing into eval/.

Outputs: eval/v2/dev/queries.jsonl and qrels.txt with the new queries added,
eval/v2/test/queries.jsonl and qrels.txt, data/eval-v2/targets.json and
data/eval-v2/exact.json (every candidate term and why it was kept or left out).

Usage:
    EVAL_VERSION=v2 python experiments/02-eval-set/generate_v2_queries.py --limit 5
    EVAL_VERSION=v2 python experiments/02-eval-set/generate_v2_queries.py
"""

from __future__ import annotations

import argparse
import gzip
import json
import random
import re
import unicodedata
from collections import Counter
from collections.abc import Callable, Iterable
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import simplemma
from build_v1_corpus import iter_catalog
from build_v2_corpus import check_parts, read_jsonl, write_text
from common import (
    CORPUS_META_PATH,
    DATA_DIR,
    EVAL_DIR,
    HARVEST_DIR,
    TEXTS_DIR,
    Thesis,
    read_theses,
    require_version,
    utf8_stdout,
)
from generate_queries import (
    API_BASE,
    ATTEMPTS,
    LLM_DIR,
    MODEL,
    PROMPTS_DIR,
    TYPED_FORMS,
    WORKERS,
    complete,
    fill,
    generated_queries,
    load_api_key,
    parse_json,
    pick_passage,
    query,
    select_targets,
    text_of,
    title_queries,
)

TEST_TARGETS = 200
TEST_QUOTAS = {"cs": 100, "en": 60, "sk": 40}
TEST_FACULTY_CAP = 20
FIRST_TEST_NUMBER = 201
EXACT_KINDS = {"person", "place", "organization", "work", "law", "code", "abbreviation"}
ABSTRACT_CHARS = 3000
# A term in more theses of the whole university would have several right answers in v3.
UNIVERSITY_LIMIT = 3
SEED = 20261103
TARGETS_PATH = DATA_DIR / "targets.json"
EXACT_PATH = DATA_DIR / "exact.json"
TOKEN = re.compile(r"\w+")
# A reference to literature, "Novák (2010)" or "Smith et al.", is not what a student types.
CITATION = re.compile(r"\(\d{4}[a-z]?\)|\bet al\b", re.IGNORECASE)
YEAR_AT_END = re.compile(r"\b(?:1[5-9]|20)\d\d$")
# The PDF split the word at the end of a line ("diacetyl- morfin"), a student types it whole.
SPLIT_TERM = re.compile(r"\w- \w")
FILE_NAME = re.compile(r"\.(?:map|txt|csv|xml|json|py|java|xlsx?|docx?|pdf|png|jpg)\b", re.I)
# Languages simplemma may find in a term besides those of the set: a French or Polish name
# has none of the set.
DETECTED_LANGUAGES = ("cs", "sk", "en", "de", "fr", "pl")
# Terms a person read in the text and left out, with the reason.
REVIEWED = {
    "rudolf mauretter": "a patient of a sanatorium, a private person",
    "leo dušak": "a patient of a sanatorium, a private person",
    "6akcbl": "Cyrillic letters the PDF turned into Latin ones",
    "natan ai'tman square": "a letter the PDF misread",
    "dorsetshiere": "a misspelling in the thesis",
    "lindarse": "a cited author in a declined form",
}
PEOPLE_FIELDS = (
    "dc.creator",
    "dc.contributor.author",
    "dc.contributor.advisor",
    "dc.contributor.referee",
    "dc.contributor.consultant",
)
Target = tuple[int, Thesis]


def squeezed(text: str) -> str:
    """A text compared as a student types it: dashes as "-", no case, single spaces."""
    plain = unicodedata.normalize("NFC", text).translate(TYPED_FORMS).casefold()
    return " ".join(plain.split())


def ask_checked(client: Any, prompt: str, path: Path, check: Callable[[Any], bool]) -> Any:
    """One LLM answer that passes `check`, kept on disk with its prompt. A kept answer
    counts only for the same prompt."""
    if path.exists():
        cached = json.loads(path.read_text(encoding="utf-8"))
        if cached.get("prompt") == prompt and check(cached.get("parsed")):
            return cached["parsed"]
    system = (PROMPTS_DIR / "system.txt").read_text(encoding="utf-8").strip()
    for attempt in range(ATTEMPTS):
        response = complete(
            client, [{"role": "system", "content": system}, {"role": "user", "content": prompt}]
        )
        content = response.choices[0].message.content or ""
        parsed = parse_json(content)
        if check(parsed):
            record = {
                "requested_model": MODEL,
                "model": response.model,
                "created": datetime.now(UTC).isoformat(timespec="seconds"),
                "attempt": attempt + 1,
                "prompt": prompt,
                "content": content,
                "parsed": parsed,
            }
            path.write_text(json.dumps(record, ensure_ascii=False, indent=1), encoding="utf-8")
            return parsed
    print(f"{path.name}: no valid answer after {ATTEMPTS} attempts")
    return None


def exact_prompt(thesis: Thesis) -> str:
    text = text_of(thesis)
    passages = [
        pick_passage(text, random.Random(f"{SEED}-exact-{index}-{thesis.handle}")) or ""
        for index in (1, 2)
    ]
    return fill(
        "exact.txt",
        title=thesis.title,
        title_translated=thesis.title_translated or "",
        keywords=", ".join(thesis.keywords_cs + thesis.keywords_en),
        abstract_cs=(thesis.abstract_cs or "")[:ABSTRACT_CHARS],
        abstract_en=(thesis.abstract_en or "")[:ABSTRACT_CHARS],
        passage_1=passages[0],
        passage_2=passages[1],
    )


def valid_exact(parsed: Any) -> bool:
    if not isinstance(parsed, dict):
        return False
    if parsed.get("skip") is True:
        return True
    terms = parsed.get("terms")
    if not isinstance(terms, list) or not terms:
        return False
    for term in terms:
        if not isinstance(term, dict) or not str(term.get("term") or "").strip():
            return False
        if term.get("kind") not in EXACT_KINDS or not isinstance(term.get("none"), bool):
            return False
        wording = term.get("query")
        if term["none"] and not (isinstance(wording, str) and wording.strip()):
            return False
        if not term["none"] and not (
            isinstance(wording, dict)
            and all(str(wording.get(lang) or "").strip() for lang in ("cs", "en", "sk"))
        ):
            return False
    return True


def private_names(entry: dict[str, Any] | None) -> set[str]:
    """Surnames and first names of the author, supervisor, referees and consultants."""
    names: set[str] = set()
    for name in PEOPLE_FIELDS:
        for value, _ in ((entry or {}).get("fields") or {}).get(name) or []:
            names.update(word for word in TOKEN.findall(value.casefold()) if len(word) > 2)
    return names


def terms_in(text: str, wanted: dict[str, set[str]]) -> list[str]:
    """The terms a text holds, compared without case and line breaks. The words of a term
    are looked up first, so the text is searched only for terms that can be in it."""
    plain = squeezed(text)
    tokens = set(TOKEN.findall(plain))
    return [term for term, words in wanted.items() if words <= tokens and term in plain]


def term_counts(terms: set[str], texts: Iterable[tuple[str, str]]) -> dict[str, set[str]]:
    """The theses whose text holds each term."""
    found: dict[str, set[str]] = {term: set() for term in terms}
    wanted = {term: set(TOKEN.findall(term)) for term in terms}
    for handle, text in texts:
        for term in terms_in(text, wanted):
            found[term].add(handle)
    return found


_wanted: dict[str, set[str]] = {}


def _start_worker(terms: set[str]) -> None:
    _wanted.update({term: set(TOKEN.findall(term)) for term in terms})


def _terms_in_file(path: Path) -> list[str]:
    return terms_in(gzip.decompress(path.read_bytes()).decode("utf-8", errors="replace"), _wanted)


def university_counts(terms: set[str]) -> Counter[str]:
    """In how many theses of the whole harvest of experiment 04 each term stands."""
    paths = sorted(HARVEST_DIR.glob("texts/*/*.txt.gz"))
    counts: Counter[str] = Counter()
    with ProcessPoolExecutor(initializer=_start_worker, initargs=(terms,)) as pool:
        for found in pool.map(_terms_in_file, paths, chunksize=200):
            counts.update(found)
    print(f"{len(terms)} terms looked up in {len(paths)} texts of the university")
    return counts


def corpus_texts(corpus: list[Thesis]) -> Iterable[tuple[str, str]]:
    for thesis in corpus:
        yield (
            thesis.handle,
            (TEXTS_DIR / f"{thesis.stem}.txt").read_text(encoding="utf-8", errors="replace"),
        )


def cited(candidate: dict[str, Any], text: str) -> bool:
    """Whether the text uses a term as a reference to literature: "Smith et al.", an author
    before a year in brackets ("Jan Cernik (2005)"), or an author and year in brackets
    ("(ROSE 1981)"). A court case before its year stays a term."""
    term, plain = squeezed(candidate["term"]), squeezed(text)
    if CITATION.search(candidate["term"]):
        return True
    if candidate["kind"] == "person" and re.search(re.escape(term) + r",? \(?\d{4}", plain):
        return True
    return bool(YEAR_AT_END.search(term)) and f"({term})" in plain


def number_belongs(term: str, text: str) -> bool:
    """Whether a number at the end of a term stands on its line in the text. A footnote
    number on the next line ("MIQE guidelines\\n80") is not a part of the term."""
    words = term.split()
    if len(words) < 2 or not words[-1].isdigit():
        return True
    pattern = r"\s+".join(map(re.escape, words[:-1])) + r"[ \t\xa0]+" + re.escape(words[-1])
    return re.search(pattern, unicodedata.normalize("NFC", text), re.IGNORECASE) is not None


def choose_exact(
    thesis: Thesis,
    candidates: list[dict[str, Any]],
    counts: dict[str, set[str]],
    names: set[str],
    university: Counter[str] | None = None,
    text: str = "",
) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    """The first candidate term that only this thesis of the corpus holds, and at most
    UNIVERSITY_LIMIT theses of the whole university, with the reason for every candidate.
    Without counts of the university only the corpus decides. A term of the title is left
    out, the title queries have it already."""
    title = squeezed(f"{thesis.title} {thesis.title_translated or ''}")
    log: list[dict[str, Any]] = []
    chosen = None
    for candidate in candidates:
        term = squeezed(candidate["term"])
        holders = counts.get(term, set())
        if thesis.handle not in holders:
            reason = "not in the text"
        elif holders - {thesis.handle}:
            reason = f"in {len(holders) - 1} other theses"
        elif university is not None and university[term] > UNIVERSITY_LIMIT:
            reason = f"in {university[term]} theses of the university"
        elif term in title:
            reason = "in the title"
        elif set(TOKEN.findall(term)) & names:
            reason = "a name of the author or a teacher"
        elif cited(candidate, text):
            reason = "a citation"
        elif not number_belongs(term, text):
            reason = "a footnote number"
        elif SPLIT_TERM.search(candidate["term"]):
            reason = "a word split at the end of a line"
        elif FILE_NAME.search(candidate["term"]):
            reason = "a file name"
        elif term in REVIEWED:
            reason = REVIEWED[term]
        elif chosen is not None:
            reason = "another term chosen"
        else:
            reason = "chosen"
            chosen = candidate
        log.append({**candidate, "reason": reason})
    return chosen, log


def term_language(text: str, kind: str, thesis_lang: str | None) -> str | None:
    """The language of a term alone: the name of a work in Czech is Czech. A name of
    a person, a code, or a name in another language has none. Czech and Slovak share most
    words, so between them the language of the thesis decides, and only a Slovak thesis
    gives a Slovak term."""
    if kind == "person":
        return None
    ranked = simplemma.langdetect(text, lang=DETECTED_LANGUAGES)
    best, score = ranked[0]
    # Half of the words known: a phrase. Fewer: a name, one of whose words a dictionary knows.
    if best == "unk" or score < 0.5:
        return None
    tied = {lang for lang, other in ranked if other == score}
    if tied - {"cs", "sk"}:
        return best if tied == {best} and best == "en" else None
    if thesis_lang in ("cs", "sk"):
        return thesis_lang
    return "cs" if tied == {"cs"} else None


def exact_queries(number: int, thesis: Thesis, chosen: dict[str, Any]) -> list[dict[str, Any]]:
    """The Czech and English wordings that keep the term, or the term alone.

    A wording with more words has the language the LLM wrote it in. The term alone has the
    language of its own words, or none. A wording that lost the term in translation is no
    exact query, and two queries with one language are one.
    """
    term = chosen["term"]
    if chosen["none"]:
        wordings = [chosen["query"]]
    else:
        # The prompt asks for a Slovak wording too, v2 leaves it out.
        wordings = [chosen["query"][version] for version in ("cs", "en")]
    found: dict[str | None, str] = {}
    for version, text in zip(("cs", "en"), wordings, strict=False):
        if squeezed(term) not in squeezed(text):
            continue
        alone = chosen["none"] or squeezed(text) == squeezed(term)
        lang = (
            (None if chosen["none"] else term_language(term, chosen["kind"], thesis.language))
            if alone
            else version
        )
        found.setdefault(lang, text)
    if not found:
        found[term_language(term, chosen["kind"], thesis.language)] = term
    items = []
    for lang, text in found.items():
        item = query(number, "exact", lang or "none", text, thesis)
        item["lang"] = lang
        items.append(item)
    return items


def owned(part: str, item: dict[str, Any]) -> bool:
    """Whether this script writes a query, so that a new run replaces it: every known-item
    query of the test part and the exact queries of the dev part. The queries of v1 and the
    topics stay."""
    return item["type"] == "exact" or (part == "test" and item["target"] is not None)


def dev_targets(queries: list[dict[str, Any]], corpus: dict[str, Thesis]) -> list[Target]:
    """The targets of v1 with the numbers their queries carry (ki-0042-title-cs is 42)."""
    numbers = {int(item["id"][3:7]): item["target"] for item in queries if item["target"]}
    return [(number, corpus[handle]) for number, handle in sorted(numbers.items())]


def choose_test_targets(corpus: list[Thesis], taken: set[str]) -> list[Target]:
    free = [thesis for thesis in corpus if thesis.handle not in taken]
    chosen = select_targets(free, TEST_TARGETS, TEST_QUOTAS, TEST_FACULTY_CAP)
    return list(enumerate(chosen, start=FIRST_TEST_NUMBER))


def work(client: Any, part: str, number: int, thesis: Thesis) -> dict[str, Any]:
    """Everything the LLM writes for one target: base queries of a test target and candidate
    exact terms."""
    base: list[dict[str, Any]] = []
    if part == "test":
        generated, _ = generated_queries(client, number, thesis)
        base = title_queries(number, thesis) + generated
    exact = ask_checked(
        client, exact_prompt(thesis), LLM_DIR / f"{thesis.stem}.exact.json", valid_exact
    )
    candidates = [] if not exact or exact.get("skip") else exact["terms"]
    return {"base": base, "candidates": candidates}


def print_check(
    part: str,
    number: int,
    thesis: Thesis,
    result: dict[str, Any],
    log: list[dict[str, Any]],
    exact: list[dict[str, Any]],
) -> None:
    print(f"\n=== {part} ki-{number:04d} {thesis.handle} ({thesis.language}) {thesis.title}")
    for item in result["base"] + exact:
        print(f"  {item['type']:<15} {str(item['lang']):<5} {item['text']}")
    for candidate in log:
        print(f"  term [{candidate['kind']}] {candidate['term']!r}: {candidate['reason']}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, help="only the first N targets of each part, printed")
    args = parser.parse_args()
    check_run = args.limit is not None
    utf8_stdout()
    require_version("v2")
    corpus = read_theses(CORPUS_META_PATH)
    by_handle = {thesis.handle: thesis for thesis in corpus}
    dev_queries = read_jsonl(EVAL_DIR / "dev" / "queries.jsonl")
    plan = {"dev": dev_targets(dev_queries, by_handle)}
    plan["test"] = choose_test_targets(corpus, {thesis.handle for _, thesis in plan["dev"]})
    if check_run:
        plan = {part: targets[: args.limit] for part, targets in plan.items()}

    from openai import OpenAI

    client = OpenAI(base_url=API_BASE, api_key=load_api_key(), timeout=180)
    LLM_DIR.mkdir(parents=True, exist_ok=True)
    jobs = [(part, number, thesis) for part, targets in plan.items() for number, thesis in targets]

    def run(job: tuple[str, int, Thesis]) -> dict[str, Any]:
        return work(client, *job)

    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        results = list(pool.map(run, jobs))

    terms = {squeezed(c["term"]) for result in results for c in result["candidates"]}
    counts = term_counts(terms, corpus_texts(corpus))
    # A check run stops at the corpus, the university takes tens of minutes.
    unique = {term for term, holders in counts.items() if len(holders) == 1}
    university = None if check_run else university_counts(unique)
    handles = {thesis.handle for _, _, thesis in jobs}
    names = {
        entry["handle"]: private_names(entry)
        for entry in iter_catalog()
        if entry["handle"] in handles
    }
    new: dict[str, list[dict[str, Any]]] = {"dev": [], "test": []}
    logs: list[dict[str, Any]] = []
    for (part, number, thesis), result in zip(jobs, results, strict=True):
        chosen, log = choose_exact(
            thesis,
            result["candidates"],
            counts,
            names.get(thesis.handle, set()),
            university,
            text_of(thesis),
        )
        exact = exact_queries(number, thesis, chosen) if chosen else []
        new[part] += result["base"] + exact
        logs.append({"part": part, "number": number, "handle": thesis.handle, "terms": log})
        if check_run:
            print_check(part, number, thesis, result, log, exact)
    if check_run:
        return

    TARGETS_PATH.write_text(
        json.dumps(
            {part: [t.handle for _, t in targets] for part, targets in plan.items()}, indent=1
        ),
        encoding="utf-8",
    )
    EXACT_PATH.write_text(json.dumps(logs, ensure_ascii=False, indent=1), encoding="utf-8")
    for part in ("dev", "test"):
        kept = [q for q in read_jsonl(EVAL_DIR / part / "queries.jsonl") if not owned(part, q)]
        queries = kept + new[part]
        kept_ids = {item["id"] for item in kept}
        qrels_path = EVAL_DIR / part / "qrels.txt"
        lines = qrels_path.read_text(encoding="utf-8").splitlines() if qrels_path.exists() else []
        qrels = [line for line in lines if line.strip() and line.split()[0] in kept_ids]
        qrels += [f"{item['id']} 0 {item['target']} 2" for item in new[part]]
        write_text(
            EVAL_DIR / part / "queries.jsonl", [json.dumps(q, ensure_ascii=False) for q in queries]
        )
        write_text(qrels_path, qrels)
        print(f"{part}: {len(new[part])} new queries, {len(queries)} in all")
    check_parts()


if __name__ == "__main__":
    main()
