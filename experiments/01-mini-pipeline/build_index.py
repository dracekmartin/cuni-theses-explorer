"""Build the search index: chunks, their embeddings and lemmatized tokens.

Reads the extracted text of every thesis in the manifest, splits it into chunks of
about 1000 characters aligned to sentence boundaries, embeds the chunks with
a multilingual model (with the "passage: " prefix the e5 family requires) and
lemmatizes them for BM25. Outputs land in data/01-mini-pipeline/index/:

- chunks.jsonl: one line per chunk (thesis handle, order, text)
- embeddings.npy: chunk vectors, rows in chunks.jsonl order, L2-normalized
- tokens.jsonl: lemmatized tokens per chunk, same order
- meta.json: model name and counts

Usage:
    python build_index.py [--model intfloat/multilingual-e5-small]
"""

from __future__ import annotations

import argparse
import json
import re
import time

import numpy as np
from common import EXTRACTED_DIR, INDEX_DIR, ensure_dirs, lemma_tokens, load_manifest, utf8_stdout

CHUNK_CHARS = 1000
DEFAULT_MODEL = "intfloat/multilingual-e5-small"
SENTENCE_END = re.compile(r"(?<=[.!?])\s+")


def chunk_text(text: str) -> list[str]:
    """Chunks of at most CHUNK_CHARS, split on sentence ends where possible."""
    chunks: list[str] = []
    current = ""
    for sentence in SENTENCE_END.split(text):
        sentence = sentence.strip()
        if not sentence:
            continue
        if len(current) + len(sentence) + 1 > CHUNK_CHARS and current:
            chunks.append(current)
            current = ""
        while len(sentence) > CHUNK_CHARS:
            chunks.append(sentence[:CHUNK_CHARS])
            sentence = sentence[CHUNK_CHARS:]
        current = f"{current} {sentence}".strip()
    if current:
        chunks.append(current)
    return chunks


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    args = parser.parse_args()

    utf8_stdout()
    ensure_dirs()
    records = load_manifest()
    if not records:
        raise SystemExit("manifest is empty, run harvest.py and extract.py first")

    chunks: list[dict[str, str | int]] = []
    for record in records:
        text_path = EXTRACTED_DIR / f"{record.stem}.txt"
        if not text_path.exists():
            print(f"skipping {record.handle}: no extracted text")
            continue
        text = text_path.read_text(encoding="utf-8")
        for order, chunk in enumerate(chunk_text(text)):
            chunks.append({"handle": record.handle, "order": order, "text": chunk})
    print(f"{len(records)} theses, {len(chunks)} chunks")

    print("lemmatizing for BM25")
    started = time.monotonic()
    tokens = [lemma_tokens(str(chunk["text"])) for chunk in chunks]
    print(f"lemmatization took {time.monotonic() - started:.0f} s")

    # Imported lazily: the import alone loads torch, which takes a while.
    from sentence_transformers import SentenceTransformer

    print(f"embedding with {args.model} (CPU)")
    started = time.monotonic()
    model = SentenceTransformer(args.model)
    embeddings = model.encode(
        [f"passage: {chunk['text']}" for chunk in chunks],
        batch_size=32,
        normalize_embeddings=True,
        show_progress_bar=True,
    )
    print(f"embedding took {time.monotonic() - started:.0f} s")

    with (INDEX_DIR / "chunks.jsonl").open("w", encoding="utf-8") as file:
        for chunk in chunks:
            file.write(json.dumps(chunk, ensure_ascii=False) + "\n")
    with (INDEX_DIR / "tokens.jsonl").open("w", encoding="utf-8") as file:
        for chunk_tokens in tokens:
            file.write(json.dumps(chunk_tokens, ensure_ascii=False) + "\n")
    np.save(INDEX_DIR / "embeddings.npy", np.asarray(embeddings, dtype=np.float32))
    meta = {"model": args.model, "theses": len(records), "chunks": len(chunks)}
    (INDEX_DIR / "meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    print(f"index written to {INDEX_DIR}")


if __name__ == "__main__":
    main()
