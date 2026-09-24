"""Check that the 01-baseline setup reproduces experiment 01.

Three checks against the files experiment 01 left in data/01-mini-pipeline/:
1. chunk_text gives the same chunks for the same extracted text,
2. lemma_tokens gives the same tokens for a sample of chunks,
3. over experiment 01's own index, the rankings of this experiment give the same top 5
   theses as experiment 01's search functions, for the showcase queries, in all three
   branches (lexical, semantic, hybrid).

Experiment 01 runs in a separate process, because both experiments have a module named
common. Exits with status 1 when anything differs.

Usage:
    python experiments/03-search-setups/check_baseline.py
"""

from __future__ import annotations

import json
import random
import subprocess
import sys
import textwrap

import numpy as np
from common import REPO_ROOT, chunk_text, lemma_tokens, utf8_stdout
from rank_bm25 import BM25Okapi
from ranking import fuse_rrf, lexical_ranking, semantic_ranking, to_theses

EXPERIMENT_01 = REPO_ROOT / "experiments" / "01-mini-pipeline"
INDEX_01 = REPO_ROOT / "data" / "01-mini-pipeline" / "index"
EXTRACTED_01 = REPO_ROOT / "data" / "01-mini-pipeline" / "extracted"
SHOWCASE_QUERIES = (
    "strategy videogame",
    "strategická videohra",
    "psychologie dlouhodobých partnerských vztahů",
    "podmíněné větvení v C#",
)
TOP = 5


def experiment_01_rankings() -> dict[str, dict[str, list[str]]]:
    script = textwrap.dedent(
        f"""
        import json, sys
        sys.path.insert(0, {str(EXPERIMENT_01)!r})
        import search
        from common import load_manifest
        chunks, tokens, embeddings, meta = search.load_index()
        theses = {{record.handle: record for record in load_manifest()}}
        out = {{}}
        for query in {list(SHOWCASE_QUERIES)!r}:
            lexical = search.ranked_chunks_bm25(query, tokens)
            semantic = search.ranked_chunks_semantic(query, embeddings, meta["model"])
            hybrid = search.fuse_rrf([lexical, semantic])
            out[query] = {{
                name: [record.handle for record, _ in
                       search.theses_from_chunks(ranking, chunks, theses, {TOP})]
                for name, ranking in
                (("lexical", lexical), ("semantic", semantic), ("hybrid", hybrid))
            }}
        print(json.dumps(out))
        """
    )
    completed = subprocess.run(
        [sys.executable, "-c", script], capture_output=True, text=True, check=True
    )
    return json.loads(completed.stdout.strip().splitlines()[-1])


def our_rankings() -> dict[str, dict[str, list[str]]]:
    from sentence_transformers import SentenceTransformer

    with (INDEX_01 / "chunks.jsonl").open(encoding="utf-8") as file:
        chunks = [json.loads(line) for line in file if line.strip()]
    with (INDEX_01 / "tokens.jsonl").open(encoding="utf-8") as file:
        tokens = [json.loads(line) for line in file if line.strip()]
    embeddings = np.load(INDEX_01 / "embeddings.npy")
    model = json.loads((INDEX_01 / "meta.json").read_text(encoding="utf-8"))["model"]
    handles = [str(chunk["handle"]) for chunk in chunks]
    bm25 = BM25Okapi(tokens)
    encoder = SentenceTransformer(model)
    out: dict[str, dict[str, list[str]]] = {}
    for query in SHOWCASE_QUERIES:
        lexical = lexical_ranking(bm25, query, 200)
        vector = encoder.encode(f"query: {query}", normalize_embeddings=True)
        semantic = semantic_ranking(embeddings @ np.asarray(vector, dtype=np.float32), 200)
        hybrid = fuse_rrf([lexical, semantic], 60)
        out[query] = {
            name: [handle for handle, _ in to_theses(ranking, handles, TOP)]
            for name, ranking in (("lexical", lexical), ("semantic", semantic), ("hybrid", hybrid))
        }
    return out


def check_chunking_and_tokens() -> list[str]:
    problems: list[str] = []
    with (INDEX_01 / "chunks.jsonl").open(encoding="utf-8") as file:
        chunks = [json.loads(line) for line in file if line.strip()]
    with (INDEX_01 / "tokens.jsonl").open(encoding="utf-8") as file:
        tokens = [json.loads(line) for line in file if line.strip()]
    by_handle: dict[str, list[str]] = {}
    for chunk in chunks:
        by_handle.setdefault(str(chunk["handle"]), []).append(str(chunk["text"]))
    for handle in sorted(by_handle)[:10]:
        text = (EXTRACTED_01 / f"{handle.replace('/', '_')}.txt").read_text(encoding="utf-8")
        if chunk_text(text) != by_handle[handle]:
            problems.append(f"chunking differs for {handle}")
    rng = random.Random(1)
    for index in rng.sample(range(len(chunks)), 200):
        if lemma_tokens(str(chunks[index]["text"])) != tokens[index]:
            problems.append(f"tokens differ for chunk {index}")
    return problems


def main() -> None:
    utf8_stdout()
    problems = check_chunking_and_tokens()
    print(f"chunking and tokens: {'ok' if not problems else f'{len(problems)} differences'}")
    theirs, ours = experiment_01_rankings(), our_rankings()
    for query in SHOWCASE_QUERIES:
        for branch in ("lexical", "semantic", "hybrid"):
            same = theirs[query][branch] == ours[query][branch]
            print(f"{'ok  ' if same else 'DIFF'} {branch:8s} {query}")
            if not same:
                problems.append(f"{branch} ranking differs for {query!r}")
    for problem in problems:
        print(f"problem: {problem}")
    sys.exit(1 if problems else 0)


if __name__ == "__main__":
    main()
