"""Topics of layer 2: add them to the evaluation set, judge the pooled results, check the judge.

Four steps, run in this order (EVAL_VERSION=v1 in front of each for version v1):

    python experiments/02-eval-set/topics.py add
        Writes the topics of the version (topics.json for v0, topics-v1.json for v1,
        topics-v2.json for v2) into eval/<version>/queries.jsonl, each in Czech and English,
        type "topic", so that every search setup answers them in its next run. A topic of
        v2 goes into the part it belongs to, eval/v2/dev or eval/v2/test.

    python experiments/02-eval-set/topics.py judge [--depth N] [--runs RUN ...]
        Pools the top results of every run of the version (data/runs/03-search-setups/ for
        v0, data/runs/05-search-v1/ for v1) for each topic, both languages together, lets
        the LLM grade every pooled thesis 0, 1 or 2 and writes the grades into
        eval/<version>/qrels.txt for both language versions. A cached grade is reused only
        when it was given to the same prompt at the same temperature.

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

For v2 every step but add takes --part dev or --part test. judge keeps the judgments the
part already has and adds the top N of the runs given with --runs. Without --runs it pools
the runs of experiment 05, which answer only the dev topics, so the test part always needs
--runs. A run of a larger corpus is read as a run of v2: a record of a group counts as its
representative, and a thesis outside the corpus is left out before the top N is taken. The
judge sees abstracts up to 4,000 characters and answers at temperature 0. The sample and
its page are named after the part (validation-dev.json), and agreement also prints the
agreement reweighted to the share of each LLM grade in the pool.

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

from build_v2_corpus import PARTS, check_parts, read_groups
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
SETTINGS: dict[str, Any] = {
    "v0": {"topics": "topics.json", "runs": "03-search-setups", "depth": 20, "sample": 30},
    "v1": {"topics": "topics-v1.json", "runs": "05-search-v1", "depth": 10, "sample": 150},
    # The dev topics of v2 are those of v1, so the runs of experiment 05 pool them.
    # 1,500 characters would cut 30 % of the abstracts of v2, 4,000 cut 1 %.
    "v2": {
        "topics": "topics-v2.json",
        "runs": "05-search-v1",
        "depth": 10,
        "sample": 150,
        "abstract": 4000,
        "temperature": 0.0,
    },
}[VERSION]
TOPICS_PATH = HERE / str(SETTINGS["topics"])
RUNS_DIR = REPO_ROOT / "data" / "runs" / str(SETTINGS["runs"])
JUDGE_DIR = LLM_DIR / "judge"
VALIDATION_PATH = DATA_DIR / "validation.md"
SAMPLE_PATH = DATA_DIR / "validation.json"
PAGE_PATH = DATA_DIR / "validation.html"
ABSTRACT_CHARS = int(SETTINGS.get("abstract", 1500))
TEMPERATURE = float(SETTINGS.get("temperature", 0.3))
SEED = 20260924
GRADE_LINE = "Známka (0, 1, 2):"


def read_queries(folder: Path = EVAL_DIR) -> list[dict[str, Any]]:
    with (folder / "queries.jsonl").open(encoding="utf-8") as file:
        return [json.loads(line) for line in file if line.strip()]


def write_queries(queries: list[dict[str, Any]], folder: Path = EVAL_DIR) -> None:
    with (folder / "queries.jsonl").open("w", encoding="utf-8", newline="\n") as file:
        for item in queries:
            file.write(json.dumps(item, ensure_ascii=False) + "\n")


def rewrite_qrels(topic_ids: set[str], lines: list[str], folder: Path = EVAL_DIR) -> None:
    """Replace the topic part of qrels.txt, keeping every other judgment."""
    path = folder / "qrels.txt"
    kept = [
        line
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and line.split()[0] not in topic_ids
    ]
    path.write_text("".join(f"{line}\n" for line in kept + lines), encoding="utf-8", newline="\n")


def read_topics() -> list[dict[str, Any]]:
    return json.loads(TOPICS_PATH.read_text(encoding="utf-8"))


def folders() -> dict[str, Path]:
    """Where the topics of a part go: the parts of v2, or the version itself before it."""
    if VERSION == "v2":
        return {part: EVAL_DIR / part for part in PARTS}
    return {"": EVAL_DIR}


def part_dir(part: str) -> Path:
    return EVAL_DIR / part if part else EVAL_DIR


def label(part: str) -> str:
    return f"{VERSION}/{part}" if part else VERSION


def named(path: Path, part: str) -> Path:
    """The file of a part: validation-dev.json next to validation.json of a version."""
    return path.with_name(f"{path.stem}-{part}{path.suffix}") if part else path


def corpus_map() -> dict[str, str]:
    """The thesis of the v2 corpus that stands for a handle: itself, or the representative
    of its group. A handle without one is missing from the map."""
    corpus = set((part_dir(PARTS[0]) / "corpus.txt").read_text(encoding="utf-8").split())
    mapping = {handle: handle for handle in corpus}
    mapping.update({m: r for m, r in read_groups().items() if r in corpus})
    return mapping


def add() -> None:
    topics = read_topics()
    if stray := [topic["id"] for topic in topics if topic.get("part", "") not in folders()]:
        raise SystemExit(f"topics without a part of {VERSION}: {stray}")
    for part, folder in folders().items():
        mine = [topic for topic in topics if topic.get("part", "") == part]
        queries = [query for query in read_queries(folder) if query["type"] != "topic"]
        for topic in mine:
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
        write_queries(queries, folder)
        ids = {f"{topic['id']}-{lang}" for topic in mine for lang in ("cs", "en")}
        rewrite_qrels(ids, [], folder)
        print(f"{part or VERSION}: {len(mine)} topics added, {len(queries)} queries in total")
    if VERSION == "v2":
        check_parts()


def top_results(
    run_path: Path, query_ids: set[str], depth: int, as_corpus: dict[str, str] | None
) -> dict[str, list[str]]:
    """The top `depth` theses of one run per query. With `as_corpus` a handle counts as the
    thesis the map gives, and a handle the map does not hold is left out before the cut."""
    ranks: dict[str, list[tuple[int, str]]] = defaultdict(list)
    for line in run_path.read_text(encoding="utf-8").splitlines():
        query_id, _, handle, rank, *_ = line.split()
        if query_id in query_ids:
            ranks[query_id].append((int(rank), handle))
    top: dict[str, list[str]] = {}
    for query_id, ranked in ranks.items():
        handles: list[str] = []
        for _, handle in sorted(ranked):
            thesis = as_corpus.get(handle) if as_corpus is not None else handle
            if thesis and thesis not in handles:
                handles.append(thesis)
        top[query_id] = handles[:depth]
    return top


def pools(
    topic_queries: list[dict[str, Any]],
    run_paths: list[Path],
    depth: int,
    as_corpus: dict[str, str] | None = None,
) -> dict[str, set[str]]:
    """Union of the top `depth` theses of every run, per topic group, both languages."""
    ids = {query["id"]: query["group"] for query in topic_queries}
    pooled: dict[str, set[str]] = defaultdict(set)
    for run_path in run_paths:
        top = top_results(run_path, set(ids), depth, as_corpus)
        for query_id, handles in top.items():
            pooled[ids[query_id]].update(handles)
        if len(top) < len(ids):
            print(f"{run_path.name}: answers {len(top)} of {len(ids)} topic queries")
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

    A cached grade counts only for the same prompt and temperature, so an edited topic is
    judged again. Grades of v0 and v1 were given at 0.3 and do not record it.
    """
    path = JUDGE_DIR / topic["id"] / f"{thesis.stem}.json"
    prompt = judge_prompt(topic, thesis)
    if path.exists():
        cached = json.loads(path.read_text(encoding="utf-8"))
        if cached.get("prompt") == prompt and cached.get("temperature", 0.3) == TEMPERATURE:
            return cached["grade"]
    system = (PROMPTS_DIR / "system.txt").read_text(encoding="utf-8").strip()
    for attempt in range(3):
        response = complete(
            client,
            [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
            TEMPERATURE,
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
                "temperature": TEMPERATURE,
                "prompt": prompt,
                "content": content,
                "grade": parsed["grade"],
                "reason": parsed.get("reason", ""),
            }
            path.write_text(json.dumps(record, ensure_ascii=False, indent=1), encoding="utf-8")
            return parsed["grade"]
    print(f"{topic['id']} {thesis.handle}: no valid grade")
    return None


def judge(depth: int, part: str = "", runs: list[Path] | None = None) -> None:
    from openai import OpenAI

    folder = part_dir(part)
    topics = {topic["id"]: topic for topic in read_topics()}
    topic_queries = [query for query in read_queries(folder) if query["type"] == "topic"]
    theses = {thesis.handle: thesis for thesis in read_theses(CORPUS_META_PATH)}
    run_paths = runs or sorted(RUNS_DIR.glob("*.run"))
    pooled = pools(topic_queries, run_paths, depth, corpus_map() if part else None)
    if part:
        # A part of v2 stays open: the judgments of runs pooled earlier stay with it.
        for topic, thesis, _ in judged_pairs(part):
            pooled[topic["id"]].add(thesis.handle)
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
    # Rewriting the qrels of an open part without a pair would drop its earlier judgment.
    if part and (missing := grades.count(None)):
        raise SystemExit(f"{missing} pairs got no grade, the qrels stay as they were: run again")

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
    rewrite_qrels({query["id"] for query in topic_queries}, lines, folder)
    print(f"grades: {dict(Counter(value for _, _, value in judged))}")
    for group in sorted(pooled):
        counts = Counter(value for topic, _, value in judged if topic["id"] == group)
        print(f"  {group}: {dict(sorted(counts.items()))}")
    if part:
        check_parts()


def judged_pairs(part: str = "") -> list[tuple[dict[str, Any], Thesis, int]]:
    """Every pair the qrels hold for a topic, with its LLM grade."""
    topics = {topic["id"]: topic for topic in read_topics()}
    theses = {thesis.handle: thesis for thesis in read_theses(CORPUS_META_PATH)}
    pairs: dict[tuple[str, str], int] = {}
    for line in (part_dir(part) / "qrels.txt").read_text(encoding="utf-8").splitlines():
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


def sample(size: int, part: str = "") -> None:
    sample_path = named(SAMPLE_PATH, part)
    if sample_path.exists():
        raise SystemExit(f"{sample_path.relative_to(REPO_ROOT)} exists, it may hold grades")
    judged = judged_pairs(part)
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
    pool_grades = Counter(value for _, _, value in judged)
    record = {
        "version": label(part),
        "created": created,
        "seed": SEED,
        "pool_pairs": len(judged),
        "pool_grades": {str(value): pool_grades[value] for value in (0, 1, 2)},
        "items": items,
        "llm_grades": llm,
    }
    sample_path.write_text(json.dumps(record, ensure_ascii=False, indent=1), encoding="utf-8")
    write_page(items, created, part)
    counts = Counter(value for _, _, value in drawn)
    print(f"sample of {len(items)} pairs, LLM grades {dict(sorted(counts.items()))}")
    print(f"open {named(PAGE_PATH, part).relative_to(REPO_ROOT)} in a browser")


def page(part: str = "") -> None:
    record = json.loads(named(SAMPLE_PATH, part).read_text(encoding="utf-8"))
    write_page(record["items"], record["created"], part)
    page_path = named(PAGE_PATH, part).relative_to(REPO_ROOT)
    print(f"{page_path} written again for the sample of {record['created']}")


def write_page(items: list[dict[str, Any]], created: str, part: str = "") -> None:
    """The grading page: the pairs without the LLM grade, embedded as JSON."""
    template = (HERE / "validation.html").read_text(encoding="utf-8")
    data = json.dumps(items, ensure_ascii=False).replace("</", "<\\/")
    page = (
        template.replace("__VERSION__", html.escape(label(part)))
        .replace("__FOLDER__", html.escape(f"data/eval-{VERSION}/"))
        .replace("__GRADES__", html.escape(named(Path("validation-grades.json"), part).name))
        .replace("__SAMPLE__", html.escape(created))
        .replace("__ITEMS__", data)
    )
    named(PAGE_PATH, part).write_text(page, encoding="utf-8")


def weighted_kappa(
    human: list[int], model: list[int], categories: int = 3, weights: list[float] | None = None
) -> float:
    """Cohen's kappa with quadratic weights, for ordinal grades 0 .. categories - 1. A pair
    counts `weights[i]` times, 1 without weights."""
    weights = weights or [1.0] * len(human)
    n = sum(weights)
    observed = [[0.0] * categories for _ in range(categories)]
    for a, b, w in zip(human, model, weights, strict=True):
        observed[a][b] += w
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


def human_grades_from_page(path: Path, part: str = "") -> list[tuple[str, str, int]]:
    """Grades saved by validation.html, for the version EVAL_VERSION selects. A pair marked
    "?" (the title and abstract do not tell) is counted and left out."""
    saved = json.loads(path.read_text(encoding="utf-8"))
    if saved.get("version") != label(part):
        raise SystemExit(
            f"{path.name} holds grades of {saved.get('version')}, not of {label(part)}"
        )
    unsure = sum(item.get("grade") == "?" for item in saved["grades"])
    ungraded = sum(item.get("grade") is None for item in saved["grades"])
    print(f"{unsure} pairs marked as not decidable and {ungraded} not graded, left out")
    return [
        (item["topic"], item["handle"], int(item["grade"]))
        for item in saved["grades"]
        if item.get("grade") in (0, 1, 2)
    ]


def pool_weights(model: list[int], pool_grades: dict[str, int]) -> list[float]:
    """Weights that make a sample drawn evenly across the LLM grades stand for the pool: a
    pair of LLM grade g weighs the pool pairs of grade g divided by the sampled ones."""
    drawn = Counter(model)
    return [pool_grades[str(value)] / drawn[value] for value in model]


def agreement(grades_path: Path | None, part: str = "") -> None:
    if grades_path is None and VERSION != "v0":
        raise SystemExit("pass the grades saved by validation.html with --grades")
    if grades_path and not grades_path.exists() and (DATA_DIR / grades_path).exists():
        grades_path = DATA_DIR / grades_path
    found = (
        human_grades_from_page(grades_path, part) if grades_path else human_grades_from_markdown()
    )
    if not found:
        raise SystemExit("no human grades found")
    human = [value for _, _, value in found]
    # The grades the LLM had when the sample was drawn: a topic edited later is judged
    # again, while the human graded the pair as it was shown.
    sample_path = named(SAMPLE_PATH, part)
    sample = json.loads(sample_path.read_text(encoding="utf-8")) if grades_path else {}
    if grades_path and json.loads(grades_path.read_text(encoding="utf-8")).get(
        "sample"
    ) != sample.get("created"):
        raise SystemExit(f"{grades_path.name} belongs to another sample than {sample_path.name}")
    recorded = sample.get("llm_grades", {})
    if grades_path and sample.get("pool_pairs") != len(judged_pairs(part)):
        print(
            f"the pool has {len(judged_pairs(part))} judged pairs, the sample was drawn from "
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
    if pool_grades := sample.get("pool_grades"):
        weights = pool_weights(model, pool_grades)
        exact = sum(w for a, b, w in zip(human, model, weights, strict=True) if a == b)
        kappa = weighted_kappa(human, model, weights=weights)
        print(
            f"reweighted to the {sum(pool_grades.values())} pairs of the pool: "
            f"exact agreement {exact / sum(weights):.2f}, weighted kappa {kappa:.2f}"
        )


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("step", choices=("add", "judge", "sample", "page", "agreement"))
    parser.add_argument("--part", choices=PARTS, help="the part of v2")
    parser.add_argument("--depth", type=int, default=int(SETTINGS["depth"]), help="pool depth")
    parser.add_argument("--runs", type=Path, nargs="+", help="runs to pool, v2 only")
    parser.add_argument("--size", type=int, default=int(SETTINGS["sample"]), help="sample size")
    parser.add_argument("--grades", type=Path, help="grades saved by validation.html")
    args = parser.parse_args()
    utf8_stdout()
    part = args.part or ""
    if VERSION == "v2" and args.step != "add" and not part:
        raise SystemExit(f"the step {args.step} of v2 needs --part dev or --part test")
    if VERSION != "v2" and (part or args.runs):
        raise SystemExit("--part and --runs belong to v2")
    if args.runs and args.step != "judge":
        raise SystemExit("--runs belongs to the step judge")
    if args.step == "add" and part:
        raise SystemExit("add writes the topics of both parts, without --part")
    if args.step == "judge" and part == "test" and not args.runs:
        raise SystemExit("the test part is pooled from the runs experiment 06 picks: --runs")
    if args.step == "add":
        add()
    elif args.step == "judge":
        judge(args.depth, part, args.runs)
    elif args.step == "sample":
        sample(args.size, part)
    elif args.step == "page":
        page(part)
    else:
        agreement(args.grades, part)


if __name__ == "__main__":
    main()
