"""Topics of layer 2: add them to the evaluation set, judge the pooled results, check the judge.

Four steps, run in this order (EVAL_VERSION=v1 in front of each for version v1):

    python experiments/02-eval-set/topics.py add
        Writes the topics of the version (topics.json for v0, topics-v1.json for v1) into
        eval/<version>/queries.jsonl, each in Czech and English, type "topic", so that
        every search setup answers them in its next run.

    python experiments/02-eval-set/topics.py judge [--depth N]
        Pools the top results of every run of the version (data/runs/03-search-setups/ for
        v0, data/runs/05-search-v1/ for v1) for each topic, both languages together, lets
        the LLM grade every pooled thesis 0, 1 or 2 and writes the grades into
        eval/<version>/qrels.txt for both language versions. A cached grade is reused only
        when it was given to the same prompt.

    python experiments/02-eval-set/topics.py sample
        Draws a blind sample of judged pairs, evenly across the LLM grades, into
        data/eval-<version>/validation.json and writes validation.html next to it: a page
        to grade the pairs with the keys 0, 1 and 2, which saves validation-grades.json.
        An existing sample is never replaced.

    python experiments/02-eval-set/topics.py page
        Writes validation.html again for the existing sample, after a change of the page.
        Grades already given in the browser stay.

    python experiments/02-eval-set/topics.py agreement [--grades validation-grades.json]
        Compares the human grades with the LLM grades the sample recorded: exact agreement,
        weighted kappa and the confusion matrix. Without --grades it reads the filled
        validation.md of v0.

In PowerShell, $env:EVAL_VERSION = "v1" holds for the rest of the session. Remove it with
Remove-Item Env:EVAL_VERSION before running anything for v0.
"""

from __future__ import annotations

import argparse
import html
import json
import random
import re
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from common import (
    CORPUS_META_PATH,
    DATA_DIR,
    EVAL_DIR,
    REPO_ROOT,
    VERSION,
    Thesis,
    read_theses,
    utf8_stdout,
)
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

HERE = Path(__file__).resolve().parent
SETTINGS = {
    "v0": {"topics": "topics.json", "runs": "03-search-setups", "depth": 20, "sample": 30},
    "v1": {"topics": "topics-v1.json", "runs": "05-search-v1", "depth": 10, "sample": 150},
}[VERSION]
TOPICS_PATH = HERE / str(SETTINGS["topics"])
RUNS_DIR = REPO_ROOT / "data" / "runs" / str(SETTINGS["runs"])
JUDGE_DIR = LLM_DIR / "judge"
VALIDATION_PATH = DATA_DIR / "validation.md"
SAMPLE_PATH = DATA_DIR / "validation.json"
PAGE_PATH = DATA_DIR / "validation.html"
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


def read_topics() -> list[dict[str, Any]]:
    return json.loads(TOPICS_PATH.read_text(encoding="utf-8"))


def add() -> None:
    topics = read_topics()
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
    """The LLM grade of one pooled thesis, cached with the prompt and the answering model.

    A cached grade counts only for the same prompt, so an edited topic is judged again.
    """
    path = JUDGE_DIR / topic["id"] / f"{thesis.stem}.json"
    prompt = judge_prompt(topic, thesis)
    if path.exists():
        cached = json.loads(path.read_text(encoding="utf-8"))
        if cached.get("prompt") == prompt:
            return cached["grade"]
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

    topics = {topic["id"]: topic for topic in read_topics()}
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


def judged_pairs() -> list[tuple[dict[str, Any], Thesis, int]]:
    """Every pair the qrels hold for a topic, with its LLM grade."""
    topics = {topic["id"]: topic for topic in read_topics()}
    theses = {thesis.handle: thesis for thesis in read_theses(CORPUS_META_PATH)}
    pairs: dict[tuple[str, str], int] = {}
    for line in (EVAL_DIR / "qrels.txt").read_text(encoding="utf-8").splitlines():
        query_id, _, handle, value = line.split()
        group = query_id.rsplit("-", 1)[0]
        if group in topics:
            pairs[(group, handle)] = int(value)
    return [(topics[group], theses[handle], value) for (group, handle), value in pairs.items()]


def draw_sample(
    judged: list[tuple[dict[str, Any], Thesis, int]], size: int
) -> list[tuple[dict[str, Any], Thesis, int]]:
    """An even share of each LLM grade. A grade with too few pairs leaves room for the
    others, so the sample still reaches `size`."""
    rng = random.Random(SEED)
    by_grade = {value: [pair for pair in judged if pair[2] == value] for value in (0, 1, 2)}
    for members in by_grade.values():
        rng.shuffle(members)
    sample: list[tuple[dict[str, Any], Thesis, int]] = []
    share = size // 3
    for value in (2, 1, 0):
        sample += by_grade[value][:share]
    leftovers = [pair for value in (1, 0, 2) for pair in by_grade[value][share:]]
    sample += leftovers[: size - len(sample)]
    rng.shuffle(sample)
    return sample


def sample(size: int) -> None:
    if SAMPLE_PATH.exists():
        raise SystemExit(f"{SAMPLE_PATH.relative_to(REPO_ROOT)} exists, it may hold grades")
    judged = judged_pairs()
    drawn = draw_sample(judged, size)
    items = [
        {
            "number": number,
            "topic": topic["id"],
            "handle": thesis.handle,
            "topic_cs": topic["cs"],
            "topic_en": topic["en"],
            "narrative": topic["narrative"],
            "title": thesis.title,
            "title_translated": thesis.title_translated or "",
            "keywords": ", ".join(thesis.keywords_cs + thesis.keywords_en),
            "abstract_cs": " ".join((thesis.abstract_cs or "").split())[:ABSTRACT_CHARS],
            "abstract_en": " ".join((thesis.abstract_en or "").split())[:ABSTRACT_CHARS],
        }
        for number, (topic, thesis, _) in enumerate(drawn, start=1)
    ]
    llm = {
        f"{item['topic']} {item['handle']}": value
        for item, (_, _, value) in zip(items, drawn, strict=True)
    }
    created = datetime.now(UTC).isoformat(timespec="seconds")
    record = {
        "version": VERSION,
        "created": created,
        "seed": SEED,
        "pool_pairs": len(judged),
        "items": items,
        "llm_grades": llm,
    }
    SAMPLE_PATH.write_text(json.dumps(record, ensure_ascii=False, indent=1), encoding="utf-8")
    write_page(items, created)
    counts = Counter(value for _, _, value in drawn)
    print(f"sample of {len(items)} pairs, LLM grades {dict(sorted(counts.items()))}")
    print(f"open {PAGE_PATH.relative_to(REPO_ROOT)} in a browser")


def page() -> None:
    record = json.loads(SAMPLE_PATH.read_text(encoding="utf-8"))
    write_page(record["items"], record["created"])
    print(f"{PAGE_PATH.relative_to(REPO_ROOT)} written again for the sample of {record['created']}")


def write_page(items: list[dict[str, Any]], created: str) -> None:
    """The grading page: the pairs without the LLM grade, embedded as JSON."""
    template = (HERE / "validation.html").read_text(encoding="utf-8")
    data = json.dumps(items, ensure_ascii=False).replace("</", "<\\/")
    page = (
        template.replace("__VERSION__", html.escape(VERSION))
        .replace("__SAMPLE__", html.escape(created))
        .replace("__ITEMS__", data)
    )
    PAGE_PATH.write_text(page, encoding="utf-8")


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


def human_grades_from_markdown() -> list[tuple[str, str, int]]:
    """Grades written into the validation.md of v0."""
    found: list[tuple[str, str, int]] = []
    for block in VALIDATION_PATH.read_text(encoding="utf-8").split("\n## ")[1:]:
        marker = re.search(r"<!-- (\S+) (\S+) -->", block)
        answer = re.search(re.escape(GRADE_LINE) + r"\s*([012])", block)
        if marker and answer:
            found.append((marker.group(1), marker.group(2), int(answer.group(1))))
    return found


def human_grades_from_page(path: Path) -> list[tuple[str, str, int]]:
    """Grades saved by validation.html, for the version EVAL_VERSION selects. A pair marked
    "?" (the title and abstract do not tell) is counted and left out."""
    saved = json.loads(path.read_text(encoding="utf-8"))
    if saved.get("version") != VERSION:
        raise SystemExit(f"{path.name} holds grades of {saved.get('version')}, not of {VERSION}")
    unsure = sum(item.get("grade") == "?" for item in saved["grades"])
    ungraded = sum(item.get("grade") is None for item in saved["grades"])
    print(f"{unsure} pairs marked as not decidable and {ungraded} not graded, left out")
    return [
        (item["topic"], item["handle"], int(item["grade"]))
        for item in saved["grades"]
        if item.get("grade") in (0, 1, 2)
    ]


def agreement(grades_path: Path | None) -> None:
    if grades_path is None and VERSION != "v0":
        raise SystemExit("pass the grades saved by validation.html with --grades")
    if grades_path and not grades_path.exists() and (DATA_DIR / grades_path).exists():
        grades_path = DATA_DIR / grades_path
    found = human_grades_from_page(grades_path) if grades_path else human_grades_from_markdown()
    if not found:
        raise SystemExit("no human grades found")
    human = [value for _, _, value in found]
    # The grades the LLM had when the sample was drawn: a topic edited later is judged
    # again, while the human graded the pair as it was shown.
    sample = json.loads(SAMPLE_PATH.read_text(encoding="utf-8")) if grades_path else {}
    if grades_path and json.loads(grades_path.read_text(encoding="utf-8")).get(
        "sample"
    ) != sample.get("created"):
        raise SystemExit(f"{grades_path.name} belongs to another sample than {SAMPLE_PATH.name}")
    recorded = sample.get("llm_grades", {})
    if grades_path and sample.get("pool_pairs") != len(judged_pairs()):
        print(
            f"the pool has {len(judged_pairs())} judged pairs, the sample was drawn from "
            f"{sample.get('pool_pairs', 'an unknown number of')}: draw a new sample"
        )
    model = [
        int(recorded[f"{topic} {handle}"])
        if f"{topic} {handle}" in recorded
        else json.loads(
            (JUDGE_DIR / topic / f"{handle.replace('/', '_')}.json").read_text(encoding="utf-8")
        )["grade"]
        for topic, handle, _ in found
    ]
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
    parser.add_argument("step", choices=("add", "judge", "sample", "page", "agreement"))
    parser.add_argument("--depth", type=int, default=int(SETTINGS["depth"]), help="pool depth")
    parser.add_argument("--size", type=int, default=int(SETTINGS["sample"]), help="sample size")
    parser.add_argument("--grades", type=Path, help="grades saved by validation.html")
    args = parser.parse_args()
    utf8_stdout()
    if args.step == "add":
        add()
    elif args.step == "judge":
        judge(args.depth)
    elif args.step == "sample":
        sample(args.size)
    elif args.step == "page":
        page()
    else:
        agreement(args.grades)


if __name__ == "__main__":
    main()
