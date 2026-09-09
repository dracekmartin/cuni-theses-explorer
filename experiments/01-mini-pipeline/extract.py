"""Extract plain text from the harvested PDFs and compare it with the DSpace text.

For every thesis in the manifest the script writes extracted/<stem>.txt and one stats
line into extraction-stats.jsonl: page count, characters extracted by pypdf, characters
in the text DSpace extracted itself (the TEXT bundle), and their ratio. The stats are
the input for the open question whether the TEXT bundle can replace our own extraction.

Already extracted theses are skipped; use --force to redo them.

Usage:
    python extract.py [--force]
"""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass

from common import (
    DSPACE_TEXT_DIR,
    EXTRACTED_DIR,
    PDF_DIR,
    ThesisRecord,
    ensure_dirs,
    load_manifest,
    utf8_stdout,
)
from pypdf import PdfReader

STATS_PATH = EXTRACTED_DIR / "extraction-stats.jsonl"


@dataclass
class ExtractionStats:
    """Extraction outcome of one thesis, one line in extraction-stats.jsonl."""

    handle: str
    pages: int
    empty_pages: int
    pypdf_chars: int
    dspace_chars: int | None

    @property
    def chars_ratio(self) -> float | None:
        """pypdf characters relative to DSpace characters, when both exist."""
        if not self.dspace_chars:
            return None
        return self.pypdf_chars / self.dspace_chars


def extract_pdf_text(record: ThesisRecord) -> tuple[str, int, int]:
    """Extract text of one PDF with pypdf. Returns (text, pages, empty pages)."""
    reader = PdfReader(PDF_DIR / record.pdf_file)
    page_texts = [page.extract_text() or "" for page in reader.pages]
    empty_pages = sum(1 for text in page_texts if len(text.strip()) < 20)
    return "\n\n".join(page_texts), len(page_texts), empty_pages


def dspace_text_length(record: ThesisRecord) -> int | None:
    if record.dspace_text_file is None:
        return None
    path = DSPACE_TEXT_DIR / record.dspace_text_file
    if not path.exists():
        return None
    return len(path.read_text(encoding="utf-8", errors="replace"))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true", help="re-extract existing outputs")
    args = parser.parse_args()

    utf8_stdout()
    ensure_dirs()
    records = load_manifest()
    if not records:
        raise SystemExit("manifest is empty, run harvest.py first")

    stats_done = set()
    if STATS_PATH.exists() and not args.force:
        with STATS_PATH.open(encoding="utf-8") as file:
            stats_done = {json.loads(line)["handle"] for line in file if line.strip()}
    elif STATS_PATH.exists():
        STATS_PATH.unlink()

    for record in records:
        output = EXTRACTED_DIR / f"{record.stem}.txt"
        if record.handle in stats_done and output.exists() and not args.force:
            continue
        text, pages, empty_pages = extract_pdf_text(record)
        output.write_text(text, encoding="utf-8")
        stats = ExtractionStats(
            handle=record.handle,
            pages=pages,
            empty_pages=empty_pages,
            pypdf_chars=len(text),
            dspace_chars=dspace_text_length(record),
        )
        with STATS_PATH.open("a", encoding="utf-8") as file:
            file.write(json.dumps(asdict(stats), ensure_ascii=False) + "\n")
        ratio = stats.chars_ratio
        ratio_text = f"{ratio:.2f}" if ratio is not None else "n/a"
        print(f"{record.handle}: {pages} pages, {stats.pypdf_chars} chars, ratio {ratio_text}")

    print(f"stats written to {STATS_PATH}")


if __name__ == "__main__":
    main()
