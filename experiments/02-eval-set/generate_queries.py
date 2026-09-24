"""Generate the known-item queries of layer 1 for the pilot evaluation set (eval/v0).

Picks target theses from the corpus, builds `title` queries from their metadata and asks
an LLM (gpt-oss-120b on e-INFRA CZ) for `about-short`, `about-sentence` and `detail`
queries in Czech and English. Every raw answer is kept in data/eval-v0/llm/, so the set
can be rebuilt without calling the model again and a rerun only asks for what is
missing. A query group is dropped when the model copied the title into it.

Outputs: eval/v0/queries.jsonl, eval/v0/qrels.txt (the target of each query, grade 2),
data/eval-v0/targets.json.

Usage:
    python experiments/02-eval-set/generate_queries.py [--limit 5] [--dry-run]
"""

from __future__ import annotations

import argparse
import json
import os
import random
import re
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from string import Template
from typing import Any

from common import (
    CORPUS_META_PATH,
    DATA_DIR,
    EVAL_DIR,
    REPO_ROOT,
    TEXTS_DIR,
    Thesis,
    read_theses,
    utf8_stdout,
)
from simplemma import lemmatize

MODEL = "gpt-oss-120b"
API_BASE = "https://llm.ai.e-infra.cz/v1/"
PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"
LLM_DIR = DATA_DIR / "llm"
TARGETS = 80
LANGUAGE_QUOTAS = {"cs": 40, "en": 30, "sk": 10}
FACULTY_CAP = 20
MIN_TEXT_CHARS = 20_000
# Largest share of a query's words that may come from the title. Only a near copy is
# dropped: a stricter limit removes natural queries that name the topic in the title's
# words, and with them exactly the queries where lexical search is strong.
MAX_COPY_SHARE = 0.8
# Hyphen, non-breaking hyphen and en dash: a model writes them, a user types "-".
TYPED_FORMS = str.maketrans({chr(0x2010): "-", chr(0x2011): "-", chr(0x2013): "-"})
# e-INFRA allows 4 parallel requests per key; half of it leaves room for retries.
WORKERS = 2
ATTEMPTS = 3
SEED = 20260924
WORD = re.compile(r"\w+", re.UNICODE)
SENTENCE_START = re.compile(r"[.!?]\s+(?=[A-ZÁČĎÉĚÍŇÓŘŠŤÚŮÝŽ])")


def load_api_key() -> str:
    key = os.environ.get("EINFRA_API_KEY")
    env_file = REPO_ROOT / ".env"
    if not key and env_file.exists():
        for line in env_file.read_text(encoding="utf-8-sig").splitlines():
            if line.strip().startswith("EINFRA_API_KEY="):
                key = line.split("=", 1)[1].strip().strip("\"'")
    if not key:
        raise SystemExit("EINFRA_API_KEY is missing: put it into .env in the repository root")
    return key


def text_of(thesis: Thesis) -> str:
    path = TEXTS_DIR / f"{thesis.stem}.txt"
    return path.read_text(encoding="utf-8", errors="replace") if path.exists() else ""


def select_targets(corpus: list[Thesis]) -> list[Thesis]:
    """Targets with metadata in both languages and a real body text, English and Slovak
    theses over-represented, at most FACULTY_CAP per faculty."""
    candidates = [
        thesis
        for thesis in corpus
        if thesis.title_translated
        and (thesis.abstract_cs or thesis.abstract_en)
        and len(text_of(thesis)) >= MIN_TEXT_CHARS
    ]
    rng = random.Random(SEED)
    rng.shuffle(candidates)
    per_language: Counter[str] = Counter()
    per_faculty: Counter[str] = Counter()
    chosen: list[Thesis] = []
    for thesis in candidates:
        language = thesis.language or "?"
        quota = LANGUAGE_QUOTAS.get(language, 0)
        if per_language[language] >= quota or per_faculty[thesis.faculty] >= FACULTY_CAP:
            continue
        per_language[language] += 1
        per_faculty[thesis.faculty] += 1
        chosen.append(thesis)
    # Languages that fell short of their quota leave room for more Czech theses.
    for thesis in candidates:
        if len(chosen) >= TARGETS:
            break
        if thesis not in chosen and thesis.language == "cs":
            chosen.append(thesis)
    return chosen[:TARGETS]


def pick_passage(text: str, rng: random.Random) -> str | None:
    """A passage of about 1000 characters from the middle of the body, cut at sentences."""
    for _ in range(20):
        start = int(len(text) * rng.uniform(0.2, 0.8))
        begin = SENTENCE_START.search(text, start)
        if begin is None:
            continue
        passage = " ".join(text[begin.end() : begin.end() + 1400].split())
        end = max(passage.rfind(". ", 0, 1100), passage.rfind("? ", 0, 1100))
        passage = passage[: end + 1] if end > 600 else ""
        letters = sum(char.isalpha() for char in passage)
        digits = sum(char.isdigit() for char in passage)
        if passage and letters > 0.6 * len(passage) and digits < 0.05 * len(passage):
            return passage
    return None


def fill(template: str, **values: str) -> str:
    return Template((PROMPTS_DIR / template).read_text(encoding="utf-8")).substitute(values)


def about_prompt(thesis: Thesis) -> str:
    return fill(
        "about.txt",
        title=thesis.title,
        title_translated=thesis.title_translated or "",
        keywords_cs=", ".join(thesis.keywords_cs),
        keywords_en=", ".join(thesis.keywords_en),
        abstract_cs=" ".join((thesis.abstract_cs or "").split()),
        abstract_en=" ".join((thesis.abstract_en or "").split()),
    )


def parse_json(content: str) -> dict[str, Any] | None:
    start, end = content.find("{"), content.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        parsed = json.loads(content[start : end + 1])
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def valid(parsed: dict[str, Any] | None, keys: tuple[str, ...]) -> bool:
    if not parsed:
        return False
    if parsed.get("skip") is True:
        return True
    return all(
        isinstance(parsed.get(key), dict)
        and all(str(parsed[key].get(lang) or "").strip() for lang in ("cs", "en"))
        for key in keys
    )


def complete(client: Any, messages: list[dict[str, str]]) -> Any:
    """One chat completion, waiting out rate limits and transient failures of the API."""
    import openai

    for wait in (10, 20, 40, 60, 90, 120):
        try:
            return client.chat.completions.create(
                model=MODEL, messages=messages, temperature=0.3, max_tokens=2000
            )
        except (openai.RateLimitError, openai.APIConnectionError, openai.InternalServerError):
            time.sleep(wait)
    raise SystemExit("the LLM API keeps failing, try again later")


def ask(client: Any, prompt: str, keys: tuple[str, ...], path: Path, **extra: Any) -> Any:
    """One LLM answer, cached on disk together with the prompt and the model that answered."""
    if path.exists():
        cached = json.loads(path.read_text(encoding="utf-8"))
        if valid(cached.get("parsed"), keys):
            return cached["parsed"]
    system = (PROMPTS_DIR / "system.txt").read_text(encoding="utf-8").strip()
    for attempt in range(ATTEMPTS):
        response = complete(
            client,
            [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
        )
        content = response.choices[0].message.content or ""
        parsed = parse_json(content)
        if valid(parsed, keys):
            record = {
                "requested_model": MODEL,
                "model": response.model,
                "created": datetime.now(UTC).isoformat(timespec="seconds"),
                "attempt": attempt + 1,
                "prompt": prompt,
                "content": content,
                "parsed": parsed,
                **extra,
            }
            path.write_text(json.dumps(record, ensure_ascii=False, indent=1), encoding="utf-8")
            return parsed
    print(f"{path.name}: no valid answer after {ATTEMPTS} attempts")
    return None


def lemmas(text: str) -> set[str]:
    return {
        lemmatize(word, lang=("cs", "en")) for word in WORD.findall(text.lower()) if len(word) > 2
    }


def copy_share(query: str, thesis: Thesis) -> float:
    """Share of the query's words that also appear in one of the titles."""
    words = lemmas(query)
    title_words = lemmas(f"{thesis.title} {thesis.title_translated or ''}")
    return len(words & title_words) / len(words) if words else 1.0


def query(number: int, kind: str, lang: str, text: str, thesis: Thesis) -> dict[str, Any]:
    group = f"ki-{number:04d}-{kind}"
    return {
        "id": f"{group}-{lang}",
        "group": group,
        "lang": lang,
        "type": kind,
        "text": " ".join(text.translate(TYPED_FORMS).split()),
        "target": thesis.handle,
        "target_lang": thesis.language,
        "narrative": None,
    }


def title_queries(number: int, thesis: Thesis) -> list[dict[str, Any]]:
    original_lang = thesis.title_lang or thesis.language or "cs"
    queries = [query(number, "title", original_lang, thesis.title, thesis)]
    translated = thesis.title_translated
    # A translation equal to the original (a name, a Latin title) would make a pair that
    # agrees with itself and inflate the consistency score.
    if (
        translated
        and thesis.title_translated_lang not in (None, original_lang)
        and " ".join(translated.lower().split()) != " ".join(thesis.title.lower().split())
    ):
        queries.append(query(number, "title", thesis.title_translated_lang, translated, thesis))
    return queries


def generated_queries(
    client: Any, number: int, thesis: Thesis
) -> tuple[list[dict[str, Any]], Counter[str]]:
    """LLM queries of one target, and what was dropped and why."""
    queries: list[dict[str, Any]] = []
    dropped: Counter[str] = Counter()
    about = ask(
        client, about_prompt(thesis), ("short", "sentence"), LLM_DIR / f"{thesis.stem}.about.json"
    )
    if about and not about.get("skip"):
        for key, kind in (("short", "about-short"), ("sentence", "about-sentence")):
            pair = about[key]
            share = max(copy_share(pair["cs"], thesis), copy_share(pair["en"], thesis))
            if share > MAX_COPY_SHARE:
                dropped[kind] += 1
                continue
            queries += [query(number, kind, lang, pair[lang], thesis) for lang in ("cs", "en")]
    rng = random.Random(f"{SEED}-{thesis.handle}")
    passage = pick_passage(text_of(thesis), rng)
    if passage:
        detail = ask(
            client,
            fill("detail.txt", passage=passage),
            ("detail",),
            LLM_DIR / f"{thesis.stem}.detail.json",
            passage=passage,
        )
        if detail and not detail.get("skip"):
            queries += [
                query(number, "detail", lang, detail["detail"][lang], thesis)
                for lang in ("cs", "en")
            ]
        else:
            dropped["detail (skipped by the model)"] += 1
    else:
        dropped["detail (no usable passage)"] += 1
    return queries, dropped


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, help="only the first N targets, for a check run")
    parser.add_argument("--dry-run", action="store_true", help="print two prompts, call nothing")
    args = parser.parse_args()
    utf8_stdout()

    corpus = read_theses(CORPUS_META_PATH)
    if not corpus:
        raise SystemExit("corpus is empty, run build_pilot_corpus.py first")
    targets = select_targets(corpus)[: args.limit]
    print(f"{len(targets)} targets: {dict(Counter(thesis.language for thesis in targets))}")

    if args.dry_run:
        thesis = targets[0]
        print(f"\n--- about prompt for {thesis.handle}:\n{about_prompt(thesis)}")
        passage = pick_passage(text_of(thesis), random.Random(f"{SEED}-{thesis.handle}"))
        print(f"\n--- detail prompt:\n{fill('detail.txt', passage=passage or '(none)')}")
        return

    from openai import OpenAI

    client = OpenAI(base_url=API_BASE, api_key=load_api_key(), timeout=180)
    LLM_DIR.mkdir(parents=True, exist_ok=True)
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        generated = list(
            pool.map(
                lambda item: generated_queries(client, item[0], item[1]),
                enumerate(targets, start=1),
            )
        )
    queries = [
        item
        for number, thesis in enumerate(targets, start=1)
        for item in title_queries(number, thesis) + generated[number - 1][0]
    ]
    dropped = sum((counts for _, counts in generated), Counter())

    EVAL_DIR.mkdir(parents=True, exist_ok=True)
    with (EVAL_DIR / "queries.jsonl").open("w", encoding="utf-8") as file:
        for item in queries:
            file.write(json.dumps(item, ensure_ascii=False) + "\n")
    with (EVAL_DIR / "qrels.txt").open("w", encoding="utf-8") as file:
        for item in queries:
            file.write(f"{item['id']} 0 {item['target']} 2\n")
    (DATA_DIR / "targets.json").write_text(
        json.dumps([thesis.handle for thesis in targets], indent=1), encoding="utf-8"
    )
    print(f"{len(queries)} queries: {dict(Counter(item['type'] for item in queries))}")
    if dropped:
        print(f"dropped: {dict(dropped)}")


if __name__ == "__main__":
    main()
