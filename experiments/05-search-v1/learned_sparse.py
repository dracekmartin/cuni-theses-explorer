"""Lexical weights of BGE-M3, a learned sparse representation that can replace BM25.

BGE-M3 turns the last hidden state of every token into a weight with one linear layer
(sparse_linear.pt in the model repository) and ReLU. A text becomes the set of its token
ids, each with the largest weight it got in the text, and a query and a chunk score by the
sum of the products of the weights of the tokens they share. This follows the reference
implementation in FlagEmbedding without depending on it. Unlike BM25 with simplemma, it
needs no lemmatizer and learns which tokens matter, in any language of the model.

The weights of every thesis are cached in one file per thesis, so a stopped run continues.
"""

from __future__ import annotations

import json
import time
from typing import Any

import numpy as np
from common import WORK_DIR, Chunk
from scipy import sparse

MODEL = "BAAI/bge-m3"
CACHE_DIR = WORK_DIR / "learned-sparse" / "BAAI__bge-m3"
Weights = dict[int, float]


class LexicalEncoder:
    def __init__(self, max_length: int = 512) -> None:
        import torch
        from huggingface_hub import hf_hub_download
        from transformers import AutoModel, AutoTokenizer

        self.torch = torch
        self.max_length = max_length
        self.tokenizer = AutoTokenizer.from_pretrained(MODEL)
        self.model = AutoModel.from_pretrained(MODEL, dtype=torch.float16).cuda().eval()
        self.linear = torch.nn.Linear(self.model.config.hidden_size, 1)
        state = torch.load(hf_hub_download(MODEL, "sparse_linear.pt"), map_location="cpu")
        self.linear.load_state_dict(state)
        self.linear = self.linear.half().cuda().eval()
        tokenizer = self.tokenizer
        self.unused = {
            tokenizer.cls_token_id,
            tokenizer.eos_token_id,
            tokenizer.pad_token_id,
            tokenizer.unk_token_id,
        }

    def encode(self, texts: list[str], batch_size: int = 32) -> list[Weights]:
        """Token weights of every text, in the order of `texts`."""
        torch = self.torch
        order = sorted(range(len(texts)), key=lambda index: len(texts[index]), reverse=True)
        result: list[Weights] = [{} for _ in texts]
        for start in range(0, len(order), batch_size):
            batch = order[start : start + batch_size]
            encoded = self.tokenizer(
                [texts[index] for index in batch],
                padding=True,
                truncation=True,
                max_length=self.max_length,
                return_tensors="pt",
            ).to("cuda")
            with torch.inference_mode():
                hidden = self.model(**encoded).last_hidden_state
                weights = torch.relu(self.linear(hidden)).squeeze(-1).float().cpu().numpy()
            ids = encoded["input_ids"].cpu().numpy()
            mask = encoded["attention_mask"].cpu().numpy()
            unused = np.array(sorted(self.unused))
            for row, index in enumerate(batch):
                result[index] = token_weights(ids[row], weights[row], mask[row], unused)
        return result


def token_weights(ids: Any, weights: Any, mask: Any, unused: Any) -> Weights:
    """The largest positive weight of every token of one text, special tokens left out."""
    keep = (mask > 0) & (weights > 0) & ~np.isin(ids, unused)
    tokens, values = ids[keep], weights[keep]
    if not tokens.size:
        return {}
    # Sorted by token and then weight, the last entry of a token holds its maximum.
    order = np.lexsort((values, tokens))
    tokens, values = tokens[order], values[order]
    last = np.append(tokens[1:] != tokens[:-1], True)
    return dict(zip(tokens[last].tolist(), values[last].tolist(), strict=True))


def _path(handle: str, suffix: str) -> Any:
    stem = handle.replace("/", "_")
    return CACHE_DIR / (f"{stem}.{suffix}.npz" if suffix else f"{stem}.npz")


def encode_theses(groups: dict[str, list[Chunk]], suffix: str) -> None:
    """Cache the token weights of every chunk of every thesis that has no file yet."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    todo = [handle for handle in groups if not _path(handle, suffix).exists()]
    if not todo:
        return
    encoder = LexicalEncoder()
    started = time.monotonic()
    for position, handle in enumerate(todo, start=1):
        weights = encoder.encode([chunk.text for chunk in groups[handle]])
        lengths = [len(chunk_weights) for chunk_weights in weights]
        path = _path(handle, suffix)
        partial = path.with_name(path.name + ".part")
        # Written to .part first: a cut-off file would pass exists() and break load_index.
        with partial.open("wb") as file:
            np.savez(
                file,
                indptr=np.concatenate([[0], np.cumsum(lengths)]).astype(np.int64),
                tokens=np.array([t for w in weights for t in w], dtype=np.int32),
                weights=np.array([v for w in weights for v in w.values()], dtype=np.float32),
            )
        partial.replace(path)
        if position % 25 == 0 or position == len(todo):
            elapsed = time.monotonic() - started
            left = elapsed / position * (len(todo) - position)
            print(
                f"sparse: {position}/{len(todo)} theses ({suffix or 'body'}), "
                f"{elapsed:.0f} s, {left / 60:.0f} min left"
            )
    record_seconds(time.monotonic() - started)


def record_seconds(seconds: float) -> None:
    path = CACHE_DIR / "timing.json"
    entries = json.loads(path.read_text(encoding="utf-8")) if path.exists() else []
    entries.append({"seconds": round(seconds, 1)})
    path.write_text(json.dumps(entries, indent=2), encoding="utf-8")


def recorded_seconds() -> float:
    """Total time spent encoding the corpus, across runs."""
    path = CACHE_DIR / "timing.json"
    if not path.exists():
        return 0.0
    return float(sum(entry["seconds"] for entry in json.loads(path.read_text(encoding="utf-8"))))


def load_index(sources: list[tuple[dict[str, list[Chunk]], str]], vocabulary: int) -> Any:
    """One sparse matrix, a row per chunk in the order of the groups, a column per token."""
    indptr_parts, tokens, weights, offset = [np.zeros(1, dtype=np.int64)], [], [], 0
    for groups, suffix in sources:
        for handle in groups:
            stored = np.load(_path(handle, suffix))
            indptr_parts.append(stored["indptr"][1:] + offset)
            offset += int(stored["indptr"][-1])
            tokens.append(stored["tokens"])
            weights.append(stored["weights"])
    indptr = np.concatenate(indptr_parts)
    matrix = sparse.csr_matrix(
        (np.concatenate(weights), np.concatenate(tokens), indptr),
        shape=(len(indptr) - 1, vocabulary),
    )
    return matrix.tocsc()


def scores(index: Any, query: Weights) -> Any:
    """Lexical matching score of every chunk for one query."""
    result = np.zeros(index.shape[0], dtype=np.float32)
    for token, weight in query.items():
        start, end = index.indptr[token], index.indptr[token + 1]
        result[index.indices[start:end]] += weight * index.data[start:end]
    return result
