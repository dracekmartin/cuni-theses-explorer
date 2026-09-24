"""Topics of layer 2: add them to the evaluation set, judge the pooled results, check the judge.

Three steps, run in this order:

    python experiments/02-eval-set/topics.py add
        Writes the topics of topics.json into eval/v0/queries.jsonl (each in Czech and
        English, type "topic"), so that every search setup answers them in its next run.

    python experiments/02-eval-set/topics.py judge [--depth 20]
        Pools the top results of every run in data/runs/03-search-setups/ for each topic
        (both languages together), lets the LLM grade every pooled thesis 0, 1 or 2 and
        writes the grades into eval/v0/qrels.txt for both language versions. Also writes
        data/eval-v0/validation.md, a blind sample for a human to grade.

    python experiments/02-eval-set/topics.py agreement
        Compares the human grades from the filled validation.md with the LLM grades.
"""

from __future__ import annotations

import argparse
import json
import random
import re
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from common import CORPUS_META_PATH, DATA_DIR, EVAL_DIR, REPO_ROOT, Thesis, read_theses, utf8_stdout
from generate_queries import (
    API_BASE,
    LLM_DIR,
    MODEL,
    PROMPTS_DIR,
    WORKERS,
    complete,
    fill,
    load_api_key,
    parse_json,
)

TOPICS_PATH = Path(__file__).resolve().parent / "topics.json"
RUNS_DIR = REPO_ROOT / "data" / "runs" / "03-search-setups"
JUDGE_DIR = LLM_DIR / "judge"
VALIDATION_PATH = DATA_DIR / "validation.md"
SAMPLE_PER_GRADE = 10
ABSTRACT_CHARS = 1500
SEED = 20260924
GRADE_LINE = "Známka (0, 1, 2):"


def read_queries() -> list[dict[str, Any]]:
    with (EVAL_DIR / "queries.jsonl").open(encoding="utf-8") as file:
        return [json.loads(line) for line in file if line.strip()]


def write_queries(queries: list[dict[str, Any]]) -> None:
    with (EVAL_DIR / "queries.jsonl").open("w", encoding="utf-8") as file:
        for item in queries:
            file.write(json.dumps(item, ensure_ascii=False) + "\n")


def rewrite_qrels(topic_ids: set[str], lines: list[str]) -> None:
    """Replace the topic part of qrels.txt, keeping every other judgment."""
    path = EVAL_DIR / "qrels.txt"
    kept = [
        line
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and line.split()[0] not in topic_ids
    ]
    path.write_text("".join(f"{line}\n" for line in kept + lines), encoding="utf-8")


def add() -> None:
    topics = json.loads(TOPICS_PATH.read_text(encoding="utf-8"))
    queries = [query for query in read_queries() if query["type"] != "topic"]
    for topic in topics:
        for lang in ("cs", "en"):
            queries.append(
                {
                    "id": f"{topic['id']}-{lang}",
                    "group": topic["id"],
                    "lang": lang,
                    "type": "topic",
                    "text": topic[lang],
                    "target": None,
                    "target_lang": None,
                    "narrative": topic["narrative"],
                }
            )
    write_queries(queries)
    rewrite_qrels({f"{topic['id']}-{lang}" for topic in topics for lang in ("cs", "en")}, [])
    print(f"{len(topics)} topics added, {len(queries)} queries in total")


def pools(topic_queries: list[dict[str, Any]], depth: int) -> dict[str, set[str]]:
    """Union of the top `depth` theses of every run, per topic group, both languages."""
    ids = {query["id"]: query["group"] for query in topic_queries}
    pooled: dict[str, set[str]] = defaultdict(set)
    for run_path in sorted(RUNS_DIR.glob("*.run")):
        seen_ids: set[str] = set()
        for line in run_path.read_text(encoding="utf-8").splitlines():
            query_id, _, handle, rank, *_ = line.split()
            if query_id in ids and int(rank) <= depth:
                pooled[ids[query_id]].add(handle)
                seen_ids.add(query_id)
        if len(seen_ids) < len(ids):
            print(f"{run_path.name}: answers {len(seen_ids)} of {len(ids)} topic queries")
    return pooled


def judge_prompt(topic: dict[str, Any], thesis: Thesis) -> str:
    return fill(
        "judge.txt",
        topic_cs=topic["cs"],
        topic_en=topic["en"],
        narrative=topic["narrative"],
        title=thesis.title,
        title_translated=thesis.title_translated or "",
        keywords=", ".join(thesis.keywords_cs + thesis.keywords_en),
        abstract_cs=" ".join((thesis.abstract_cs or "").split())[:ABSTRACT_CHARS],
        abstract_en=" ".join((thesis.abstract_en or "").split())[:ABSTRACT_CHARS],
    )


def grade(client: Any, topic: dict[str, Any], thesis: Thesis) -> int | None:
    """The LLM grade of one pooled thesis, cached with the prompt and the answering model."""
    path = JUDGE_DIR / topic["id"] / f"{thesis.stem}.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))["grade"]
    prompt = judge_prompt(topic, thesis)
    system = (PROMPTS_DIR / "system.txt").read_text(encoding="utf-8").strip()
    for attempt in range(3):
        response = complete(
            client, [{"role": "system", "content": system}, {"role": "user", "content": prompt}]
        )
        content = response.choices[0].message.content or ""
        parsed = parse_json(content)
        if parsed and parsed.get("grade") in (0, 1, 2):
            path.parent.mkdir(parents=True, exist_ok=True)
            record = {
                "requested_model": MODEL,
                "model": response.model,
                "created": datetime.now(UTC).isoformat(timespec="seconds"),
                "attempt": attempt + 1,
                "prompt": prompt,
                "content": content,
                "grade": parsed["grade"],
                "reason": parsed.get("reason", ""),
            }
            path.write_text(json.dumps(record, ensure_ascii=False, indent=1), encoding="utf-8")
            return parsed["grade"]
    print(f"{topic['id']} {thesis.handle}: no valid grade")
    return None


def judge(depth: int) -> None:
    from openai import OpenAI

    topics = {topic["id"]: topic for topic in json.loads(TOPICS_PATH.read_text(encoding="utf-8"))}
    topic_queries = [query for query in read_queries() if query["type"] == "topic"]
    theses = {thesis.handle: thesis for thesis in read_theses(CORPUS_META_PATH)}
    pooled = pools(topic_queries, depth)
    pairs = [
        (topics[group], theses[handle])
        for group in sorted(pooled)
        for handle in sorted(pooled[group])
    ]
    sizes = {group: len(handles) for group, handles in sorted(pooled.items())}
    print(f"{len(pairs)} pooled pairs: {sizes}")

    client = OpenAI(base_url=API_BASE, api_key=load_api_key(), timeout=180)
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        grades = list(pool.map(lambda pair: grade(client, *pair), pairs))

    judged = [
        (topic, thesis, value)
        for (topic, thesis), value in zip(pairs, grades, strict=True)
        if value is not None
    ]
    lines = [
        f"{topic['id']}-{lang} 0 {thesis.handle} {value}"
        for topic, thesis, value in judged
        for lang in ("cs", "en")
    ]
    rewrite_qrels({query["id"] for query in topic_queries}, lines)
    print(f"grades: {dict(Counter(value for _, _, value in judged))}")
    for group in sorted(pooled):
        counts = Counter(value for topic, _, value in judged if topic["id"] == group)
        print(f"  {group}: {dict(sorted(counts.items()))}")
    write_validation(judged)


def write_validation(judged: list[tuple[dict[str, Any], Thesis, int]]) -> None:
    """A blind sample, drawn evenly across the LLM grades, for a human to grade."""
    rng = random.Random(SEED)
    sample: list[tuple[dict[str, Any], Thesis]] = []
    for value in (0, 1, 2):
        members = [(topic, thesis) for topic, thesis, grade_ in judged if grade_ == value]
        sample += rng.sample(members, min(SAMPLE_PER_GRADE, len(members)))
    rng.shuffle(sample)
    parts = [
        "# Validation of the relevance judgments\n",
        f'Write 0, 1 or 2 after each "{GRADE_LINE}" line, using the description of relevance '
        "of the topic. 2 = the thesis is about the topic, 1 = it touches the topic or covers a "
        "part of it, 0 = not relevant.\n",
    ]
    for number, (topic, thesis) in enumerate(sample, start=1):
        abstract = " ".join((thesis.abstract_cs or thesis.abstract_en or "").split())
        parts.append(
            f"## {number}. {topic['cs']}\n\n<!-- {topic['id']} {thesis.handle} -->\n\n"
            f"**Relevantní:** {topic['narrative']}\n\n"
            f"**Práce:** {thesis.title}  \n**Přeložený název:** {thesis.title_translated or ''}  \n"
            f"**Klíčová slova:** {', '.join(thesis.keywords_cs or thesis.keywords_en)}\n\n"
            f"**Abstrakt:** {abstract[:ABSTRACT_CHARS]}\n\n{GRADE_LINE} \n"
        )
    VALIDATION_PATH.write_text("\n".join(parts), encoding="utf-8")
    location = VALIDATION_PATH.relative_to(REPO_ROOT)
    print(f"validation sample of {len(sample)} pairs written to {location}")


def weighted_kappa(human: list[int], model: list[int], categories: int = 3) -> float:
    """Cohen's kappa with quadratic weights, for ordinal grades 0 .. categories - 1."""
    n = len(human)
    observed = [[0.0] * categories for _ in range(categories)]
    for a, b in zip(human, model, strict=True):
        observed[a][b] += 1
    rows = [sum(row) for row in observed]
    columns = [sum(observed[i][j] for i in range(categories)) for j in range(categories)]
    weight = [
        [(i - j) ** 2 / (categories - 1) ** 2 for j in range(categories)] for i in range(categories)
    ]
    disagreement = sum(
        weight[i][j] * observed[i][j] for i in range(categories) for j in range(categories)
    )
    expected = sum(
        weight[i][j] * rows[i] * columns[j] / n
        for i in range(categories)
        for j in range(categories)
    )
    return 1.0 - disagreement / expected if expected else 1.0


def agreement() -> None:
    text = VALIDATION_PATH.read_text(encoding="utf-8")
    human: list[int] = []
    model: list[int] = []
    for block in text.split("\n## ")[1:]:
        marker = re.search(r"<!-- (\S+) (\S+) -->", block)
        answer = re.search(re.escape(GRADE_LINE) + r"\s*([012])", block)
        if not marker or not answer:
            continue
        topic_id, handle = marker.groups()
        record = JUDGE_DIR / topic_id / f"{handle.replace('/', '_')}.json"
        human.append(int(answer.group(1)))
        model.append(json.loads(record.read_text(encoding="utf-8"))["grade"])
    if not human:
        raise SystemExit("no filled grades found in validation.md")
    exact = sum(a == b for a, b in zip(human, model, strict=True)) / len(human)
    kappa = weighted_kappa(human, model)
    print(f"{len(human)} pairs, exact agreement {exact:.2f}, weighted kappa {kappa:.2f}")
    print("rows: human grade, columns: LLM grade")
    for value in (0, 1, 2):
        row = [
            sum(1 for a, b in zip(human, model, strict=True) if a == value and b == other)
            for other in (0, 1, 2)
        ]
        print(f"  {value}: {row}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("step", choices=("add", "judge", "agreement"))
    parser.add_argument("--depth", type=int, default=20, help="pool depth per run")
    args = parser.parse_args()
    utf8_stdout()
    if args.step == "add":
        add()
    elif args.step == "judge":
        judge(args.depth)
    else:
        agreement()


if __name__ == "__main__":
    main()
