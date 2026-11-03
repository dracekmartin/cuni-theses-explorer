"""Abstracts of the theses for evaluation version v2, completed from the thesis text and cleaned.

DSpace hands out half of the abstracts cut after about 1,300 characters and three dots, and
883 theses of v1 have no abstract in the metadata. The abstract of a thesis usually stands
on one of its first pages under a heading such as Abstrakt or Abstract. Some faculties put
it at the end, or a Souhrn or Summary in its place.

For each thesis of the v1 corpus and each slot of the metadata (cs, en), the script keeps
a whole abstract, completes a cut one with the rest of its paragraph in the text, and takes
a missing one from under its heading in the text. It cleans all of them: HTML entities,
soft hyphens, ligatures, words split at the end of a line, the title page DSpace copied in
front of the abstract, keywords after it, and ř written as Z. Text taken from the thesis
leaves out page numbers and the running headers next to them. A Slovak abstract goes into
the cs slot, as DSpace has it. A thesis left without any abstract does not enter v2.

Outputs: data/eval-v2/abstracts.jsonl (one line per thesis) and
data/eval-v2/abstracts-sample.md (taken and completed abstracts to be read by a person, and
the theses left without an abstract).

Usage:
    EVAL_VERSION=v2 python experiments/02-eval-set/abstracts.py [--sample 30]
"""

from __future__ import annotations

import argparse
import html
import json
import random
import re
import unicodedata
from collections import Counter
from dataclasses import dataclass
from typing import Any

import simplemma
from common import DATA_DIR, REPO_ROOT, Thesis, read_theses, require_version, utf8_stdout

V1_META_PATH = REPO_ROOT / "data" / "eval-v1" / "corpus.jsonl"
V1_TEXTS_DIR = REPO_ROOT / "data" / "eval-v1" / "texts"
OUTPUT_PATH = DATA_DIR / "abstracts.jsonl"
SAMPLE_PATH = DATA_DIR / "abstracts-sample.md"
# The front matter: the first 30,000 characters, or the first fifth of a long text.
HEAD_CHARS = 30_000
HEAD_SHARE = 0.2
# In the middle of the text, a heading starts the abstract of an attached paper or the
# summary of a chapter, not the abstract of the thesis.
END_SHARE = 0.75
MIN_CHARS = 100
MIN_WORDS = 15
# Text that runs longer without a sign of its end is not an abstract any more.
MAX_CHARS = 6_000
# A paragraph read to tell its language.
PARAGRAPH_CHARS = 300
# The title page that DSpace copied in front of the heading is shorter than this.
LEAD_CHARS = 300
TITLE_PAGE_CHARS = 600
# Fewer letters and digits of the start or the end of a cut abstract match by chance.
TAIL_KEY = 60
# The end of a cut abstract lies at most this many abstract lengths after its start.
SPAN = 1.5
SEED = 20261103
SLOTS = ("cs", "en")
SLOT_LANGUAGES = {"cs": ("cs", "sk"), "en": ("en",)}

LIGATURES = str.maketrans({"ﬀ": "ff", "ﬁ": "fi", "ﬂ": "fl", "ﬃ": "ffi", "ﬄ": "ffl", "\xad": ""})
STRONG = r"abstra[ck]t|anotace|anotácia|annotation"
WEAK = r"souhrn|súhrn|summary|resum[eé]|résumé"
HEADING = re.compile(rf"^(?P<word>{STRONG}|{WEAK})\b(?P<rest>.*)$", re.IGNORECASE)
TOC_LINE = re.compile(r"\.{4,}|…{2,}|\s\d{1,3}$")
DOT_LEADERS = re.compile(r"\.{4,}|…{2,}")
KEYWORDS = re.compile(
    r"^(?:klíčová\s+slova|klíčové\s+pojmy|kľúčové\s+slov[áa]|key\s*-?\s*words)\b", re.IGNORECASE
)
# A heading line of the front or back matter, numbered or not ("1 Úvod", "Seznam zkratek").
SECTION = re.compile(
    r"^(?:\d{1,2}(?:\.\d{1,2})*\.?\s+)?(?:obsah|contents?|table of contents|úvod|introduction"
    r"|prohlášení|čestné prohlášení|prohlašuji|declaration|poděkování|acknowledg\w*|seznam"
    r"|list|bibliografi\w*|bibliograph\w*|references|literatura|použitá literatura|zdroje"
    r"|sources|závěr|conclusions?|diskuse|discussion|přílohy?|appendix|appendices)\b"
    r"[\w\s,]{0,40}$",
    re.IGNORECASE,
)
# A chapter heading such as "2.1 Metodika" that starts after the abstract.
NUMBERED_HEADING = re.compile(r"^\d{1,2}(?:\.\d{1,2})*\.?\s+[A-ZÁČĎÉĚÍŇÓŘŠŤÚŮÝŽ]")
CAPTION = re.compile(r"^(?:obr|obrázek|fig|figure|tab|tabulka|table|graf)\.?\s*\d", re.IGNORECASE)
LABEL = re.compile(
    r"^(?:název|title|autor|author|jméno|name|katedra|department|departement|ústav|institute"
    r"|fakulta|faculty|obor|studijní|study|subject|vedoucí|supervisor|head of|konzultant"
    r"|consultant|e-mail|počet|number of|rok|year|the year|druh|typ|type|datum|date"
    r"|zpracoval\w*|vypracoval\w*|řešitel\w*|student\w*|školitel\w*|oponent\w*|program)\b"
    r"[^:]{0,40}:",
    re.IGNORECASE,
)
PAGE_NUMBER = re.compile(r"^(?:[-–]\s*)?(?:\d{1,3}|[ivxlc]{1,7})(?:\s*[-–])?$", re.IGNORECASE)
LEAD = re.compile(
    r"\b(?:Abstra[ck]t|ABSTRA[CK]T|Anotace|ANOTACE|Anotácia|ANOTÁCIA|Annotation|ANNOTATION)\b"
    r"(?:(?:\s+\w+){1,3}\s*:|\s*[:.\-–]?)\s+(?=[\"„“'(\[A-ZÁČĎÉĚÍŇÓŘŠŤÚŮÝŽ0-9])"
)
LEAD_LABELS = re.compile(
    r"název|title|autor|author|jméno|vedoucí|supervisor|řešitel|diplomov|bakalářsk"
    r"|disertační|rigorózní|thesis",
    re.IGNORECASE,
)
SENTENCE_END = re.compile(r"[a-záčďéěíňóřšťúůýž]{3}[.!?] [A-ZÁČĎÉĚÍŇÓŘŠŤÚŮÝŽ]")
TITLE_LABEL = re.compile(r"\b(?:Názov|Název|Title)[^:.]{0,40}:\s*", re.IGNORECASE)
# DSpace kept words split at the end of a PDF line ("opti- malizace"), but not "dvou- a tří".
SPLIT_WORD = re.compile(
    r"\b(\w*[a-záčďéěíňóřšťúůýžäľĺôŕ])- "
    r"(?!(?:a|i|nebo|či|až|ani|alebo|aj|and|or|to|versus|vs)\b)"
    r"([a-záčďéěíňóřšťúůýžäľĺôŕ]\w*)"
)
# The Czech particle stays with a hyphen: "je-li", not "jeli".
SPLIT_LI = re.compile(r"(?<=\w)- li\b")
INLINE_KEYWORDS = re.compile(
    r"\s(?:Klíčová slova|Klíčové pojmy|Kľúčové slová|Keywords|Key words|KLÍČOVÁ SLOVA"
    r"|KEYWORDS|KEY WORDS)\b"
)
# DSpace lost ř in a few abstracts and wrote Z instead (pZezkumu).
R_AS_Z = re.compile(r"(?<=[a-záčďéěíňóřšťúůýž])Z(?=[a-záčďéěíňóřšťúůýž])")
WORD_WITH_Z = re.compile(r"\w*[a-záčďéěíňóřšťúůýž]Z[a-záčďéěíňóřšťúůýž]\w*")
WORD = re.compile(r"\w+", re.UNICODE)


@dataclass
class Block:
    """Text under an abstract heading of the thesis text."""

    strong: bool
    text: str
    lang: str | None


def prepare(text: str) -> str:
    """Composed characters without ligatures and soft hyphens, as in the metadata."""
    return unicodedata.normalize("NFC", text).translate(LIGATURES)


def squeeze(text: str) -> str:
    return " ".join(text.split())


def unescape(text: str) -> str:
    """HTML entities, also when DSpace escaped them twice (&amp;quot;)."""
    while (plain := html.unescape(text)) != text:
        text = plain
    return text


def keyed(text: str) -> tuple[str, list[int]]:
    """Letters and digits of a text in lower case, with the position of each in the text."""
    chars: list[str] = []
    positions: list[int] = []
    for position, char in enumerate(text):
        for folded in char.casefold():
            if folded.isalnum():
                chars.append(folded)
                positions.append(position)
    return "".join(chars), positions


def loose(key: str) -> re.Pattern[str]:
    """A pattern for the letters and digits of a key with anything else between them."""
    return re.compile(r"[\W_]*".join(map(re.escape, key)), re.IGNORECASE)


def front_length(text: str) -> int:
    return max(HEAD_CHARS, int(len(text) * HEAD_SHARE))


def running_headers(text: str) -> set[str]:
    """Lines that stand next to a page number on three or more pages: running headers and
    footers of the PDF. A line repeated elsewhere, such as a species name, does not count."""
    lines = [line.strip() for line in text.splitlines()]
    numbered = {index for index, line in enumerate(lines) if PAGE_NUMBER.match(line)}
    beside: Counter[str] = Counter()
    for index, line in enumerate(lines):
        near = any(index + offset in numbered for offset in (-2, -1, 1, 2))
        if near and 8 <= len(line) <= 150 and not line.isdigit():
            beside[line] += 1
    return {line for line, count in beside.items() if count >= 3}


def heading(line: str) -> tuple[bool, str] | None:
    """Whether a line is an abstract heading: its strength and the text after it."""
    stripped = line.strip()
    match = HEADING.match(stripped)
    if not match or TOC_LINE.search(stripped):
        return None
    qualifier, colon, inline = match.group("rest").partition(":")
    if len(qualifier) > 40 or (not colon and len(qualifier.split()) > 5):
        return None
    strong = re.fullmatch(STRONG, match.group("word"), re.IGNORECASE) is not None
    return strong, inline.strip()


def ends_sentence(text: str) -> bool:
    return text.rstrip()[-1:] in (".", "!", "?", '"', "”", "“", ")")


def join_lines(parts: list[str]) -> str:
    """Lines of a paragraph as one string, with words split at the end of a line joined."""
    text = ""
    for part in parts:
        if len(text) > 1 and text.endswith("-") and text[-2].isalpha() and part[:1].islower():
            text = text[:-1] + part
        else:
            text = f"{text} {part}" if text else part
    return text


def is_stop(line: str) -> bool:
    """A line that ends an abstract: keywords, another heading, a section of the front or
    back matter, a line of the table of contents, or a caption."""
    return bool(
        KEYWORDS.match(line)
        or heading(line)
        or (len(line) <= 60 and SECTION.match(line))
        or DOT_LEADERS.search(line)
        or CAPTION.match(line)
    )


def language_group(text: str) -> str | None:
    """The language of a text, with Czech and Slovak as one: they share the cs slot."""
    lang = language(text)
    return "cs" if lang == "sk" else lang


def next_paragraph(lines: list[str], index: int) -> str:
    """The start of the paragraph at `index`, enough to tell its language."""
    taken: list[str] = []
    for line in lines[index:]:
        stripped = line.strip()
        if not stripped or sum(map(len, taken)) > PARAGRAPH_CHARS:
            break
        taken.append(stripped)
    return " ".join(taken)


def starts_other_part(collected: str, lines: list[str], index: int) -> bool:
    """Whether a new paragraph after a finished sentence is no longer the abstract: a
    numbered or capitalised chapter heading, or text in the other language."""
    line = lines[index].strip()
    letters = [char for char in line if char.isalpha()]
    heading_like = len(line) <= 80 and ":" not in line and not ends_sentence(line)
    capitalised = len(letters) >= 3 and line.upper() == line
    if heading_like and (NUMBERED_HEADING.match(line) or capitalised):
        return True
    mine, other = language_group(collected), language_group(next_paragraph(lines, index))
    return mine is not None and other is not None and mine != other


def beside_page_number(lines: list[str], index: int) -> bool:
    """Whether the nearest non-empty line before or after a line is a page number."""
    for step in (-1, 1):
        other = index + step
        while 0 <= other < len(lines) and not lines[other].strip():
            other += step
        if 0 <= other < len(lines) and PAGE_NUMBER.match(lines[other].strip()):
            return True
    return False


def collect(lines: list[str], first: str, headers: set[str]) -> tuple[str, bool]:
    """The text from `first` on through `lines` up to the end of the abstract, and whether
    the end was found before MAX_CHARS.

    The abstract ends at a stop line, at three blank lines, at a page number after
    a finished sentence, and at a blank line after a finished sentence when the next
    paragraph starts another part. Labels of a title page before the text are skipped, and
    so is a running header next to a page number.
    """
    parts = [first] if first else []
    blank = 0
    new_paragraph = False
    for index, line in enumerate(lines):
        stripped = line.strip()
        if not stripped:
            blank += 1
            if blank >= 3 and parts:
                return join_lines(parts), True
            new_paragraph = bool(parts) and ends_sentence(parts[-1])
            continue
        blank = 0
        if stripped in headers and beside_page_number(lines, index):
            continue
        if PAGE_NUMBER.match(stripped):
            if parts and ends_sentence(parts[-1]):
                return join_lines(parts), True
            continue
        if is_stop(stripped):
            return join_lines(parts), True
        if LABEL.match(stripped):
            if parts:
                return join_lines(parts), True
            continue
        if new_paragraph and starts_other_part(join_lines(parts), lines, index):
            return join_lines(parts), True
        new_paragraph = False
        parts.append(stripped)
        if sum(map(len, parts)) > MAX_CHARS:
            return join_lines(parts), False
    return join_lines(parts), True


def usable(text: str) -> bool:
    """Long enough, mostly letters, not a table of contents."""
    compact = text.replace(" ", "")
    letters = sum(char.isalpha() for char in compact)
    return (
        len(text) >= MIN_CHARS
        and len(WORD.findall(text)) >= MIN_WORDS
        and letters >= 0.6 * max(len(compact), 1)
        and not DOT_LEADERS.search(text)
    )


def language(text: str) -> str | None:
    best, score = simplemma.langdetect(text[:2000], lang=("cs", "sk", "en"))[0]
    return best if best != "unk" and score >= 0.3 else None


def find_blocks(text: str, headers: set[str]) -> list[Block]:
    """Usable texts under abstract headings in the front matter or at the end of the text."""
    lines = text.splitlines()
    front, end = front_length(text), END_SHARE * len(text)
    found: list[Block] = []
    offset = 0
    for number, line in enumerate(lines):
        position, offset = offset, offset + len(line) + 1
        marker = heading(line)
        if marker is None or front <= position < end:
            continue
        strong, inline = marker
        block, ended = collect(lines[number + 1 :], inline, headers)
        if ended and usable(block):
            found.append(Block(strong, block, language(block)))
    return found


def pick(blocks: list[Block], slot: str) -> Block | None:
    """The first block in the language of a slot, under a strong heading if there is one."""
    fitting = [block for block in blocks if block.lang in SLOT_LANGUAGES[slot]]
    strong = [block for block in fitting if block.strong]
    return (strong or fitting or [None])[0]


def strip_lead(text: str, titles: list[str]) -> str:
    """The abstract without the title page DSpace copied in front of its heading."""
    match = LEAD.search(text[: LEAD_CHARS + 30])
    if match is None or match.start() > LEAD_CHARS:
        return text
    lead = text[: match.start()]
    if not lead.strip():
        return text[match.end() :]
    # A title page has no sentences. A lead with one is the abstract itself.
    if SENTENCE_END.search(text[: match.start() + 1]):
        return text
    lead_words = set(WORD.findall(lead.lower()))
    title_words = [set(WORD.findall(title.lower())) for title in titles if title]
    from_title = any(words and len(words & lead_words) >= 0.6 * len(words) for words in title_words)
    if from_title or LEAD_LABELS.search(lead):
        return text[match.end() :]
    return text


def strip_title_page(text: str, titles: list[str]) -> str:
    """The abstract without a title page that ends with a labelled title and has no heading,
    as at the Faculty of Pharmacy ("Názov diplomovej práce: <title> <abstract>")."""
    label = TITLE_LABEL.search(text[:TITLE_PAGE_CHARS])
    if label is None:
        return text
    for title in titles:
        key = keyed(title)[0]
        found = loose(key).match(text, label.end()) if key else None
        if found:
            return text[found.end() :].lstrip(" .:")
    return text


def cut_keywords(text: str) -> tuple[str, bool]:
    """The abstract without the keywords DSpace kept after it."""
    for match in INLINE_KEYWORDS.finditer(text):
        if match.start() >= max(100, 0.3 * len(text)):
            return text[: match.start()].rstrip(), True
    return text, False


def from_metadata(abstract: str, titles: list[str]) -> tuple[str, bool, list[str]]:
    """A cleaned abstract of the metadata, whether DSpace cut it, and the rules applied."""
    applied: list[str] = []
    text = squeeze(prepare(abstract))
    plain = unescape(text)
    if plain != text:
        applied.append("entities")
    # A heading may stand right after the title page ("... Název práce: X Abstrakt: ...").
    lead_free = strip_lead(strip_title_page(strip_lead(plain, titles), titles), titles)
    if lead_free != plain:
        applied.append("title page")
    body, had_keywords = cut_keywords(lead_free)
    if had_keywords:
        applied.append("keywords")
    return body, body.endswith("...") and not had_keywords, applied


def complete(cut: str, text: str, headers: set[str]) -> str | None:
    """A cut abstract with the rest of its paragraph from the thesis text, if the text has it.

    The start and the end of the cut abstract are looked up by their letters and digits
    only, so line breaks, hyphens and punctuation of the PDF do not matter. The end must
    follow the start closely, so a sentence the conclusion repeats from the abstract does
    not count. When DSpace cut inside a word, the lookup without the last word still finds
    the place.
    """
    body = cut.removesuffix("...").rstrip()
    start_key = keyed(body)[0][:TAIL_KEY]
    if len(start_key) < TAIL_KEY:
        return None
    starts = list(loose(start_key).finditer(text))
    for candidate in (body, body.rsplit(" ", 1)[0]):
        tail = loose(keyed(candidate)[0][-TAIL_KEY:])
        for start in starts:
            match = tail.search(text, start.start(), start.start() + int(SPAN * len(body)) + 200)
            if match is None:
                continue
            line_end = text.find("\n", match.end())
            line_end = len(text) if line_end < 0 else line_end
            first = text[match.end() : line_end]
            rest, ended = collect(text[line_end + 1 :].splitlines(), first.strip(), headers)
            if not rest or not ended:
                return None
            # The text goes on right after the last letter or digit the lookup matched, so
            # a hyphen or a bracket after it in the cut abstract would come twice.
            head = re.sub(r"[\W_]+$", "", candidate)
            spaced = not first or first[0].isspace()
            return head + (" " if spaced else "") + rest
    return None


def join_split_words(text: str, slot: str) -> str:
    """Words split at the end of a line joined again. Two known words stay a compound with
    a hyphen (post-termination), unless the joined word is known too (follow-up)."""
    languages = SLOT_LANGUAGES[slot]

    def join(match: re.Match[str]) -> str:
        first, second = match.group(1), match.group(2)
        joined = first + second
        if simplemma.is_known(joined.lower(), languages):
            return joined
        if simplemma.is_known(first.lower(), languages) and simplemma.is_known(
            second.lower(), languages
        ):
            return f"{first}-{second}"
        return joined

    return SPLIT_WORD.sub(join, SPLIT_LI.sub("-li", text))


def restore_r(text: str) -> str:
    """ř in the words where DSpace wrote Z. A name such as ProZone3 has another capital
    letter or a digit and stays."""

    def fix(match: re.Match[str]) -> str:
        word = match.group(0)
        name = sum(char.isupper() for char in word) > 1 or any(char.isdigit() for char in word)
        return word if name else R_AS_Z.sub("ř", word)

    return WORD_WITH_Z.sub(fix, text)


def finish(text: str, slot: str) -> tuple[str, list[str]]:
    """The final text of a slot and the rules applied."""
    text = squeeze(text)
    applied: list[str] = []
    joined = join_split_words(text, slot)
    if joined != text:
        text = joined
        applied.append("split words")
    restored = restore_r(text) if slot == "cs" else text
    if restored != text:
        text = restored
        applied.append("ř")
    return text, applied


def abstracts_of(thesis: Thesis, text: str, events: Counter[str]) -> dict[str, Any]:
    """Both abstract slots of one thesis, with where each came from."""
    text = prepare(text)
    headers = running_headers(text)
    titles = [thesis.title, thesis.title_translated or ""]
    slots: dict[str, dict[str, Any] | None] = {}
    flags: list[str] = []
    blocks: list[Block] | None = None
    for slot in SLOTS:
        raw = getattr(thesis, f"abstract_{slot}")
        applied: list[str] = []
        if raw:
            body, cut, applied = from_metadata(raw, titles)
            source = "metadata"
            if cut:
                completed = complete(body, text, headers)
                if completed:
                    body, source = completed, "metadata+text"
                else:
                    flags.append(f"truncated-{slot}")
        else:
            if blocks is None:
                blocks = find_blocks(text, headers)
            block = pick(blocks, slot)
            if block is None:
                slots[slot] = None
                continue
            body, source = block.text, "text"
        cleaned, finishing = finish(body, slot)
        events.update(f"{slot}: {rule}" for rule in applied + finishing)
        slots[slot] = {"text": cleaned, "source": source, "lang": language(cleaned)}
    if not slots["cs"] and not slots["en"]:
        flags.append("no-abstract")
    return {"handle": thesis.handle, "cs": slots["cs"], "en": slots["en"], "flags": flags}


def write_sample(records: list[dict[str, Any]], theses: dict[str, Thesis], size: int) -> None:
    """Taken and completed abstracts drawn at random, and the theses left without one."""
    rng = random.Random(SEED)
    changed = [
        (record, slot)
        for record in records
        for slot in SLOTS
        if record[slot] and record[slot]["source"] != "metadata"
    ]
    lines = [f"# Abstracts of v2: {size} taken or completed from the text\n"]
    for record, slot in rng.sample(changed, min(size, len(changed))):
        item = record[slot]
        lines += [
            f"## {record['handle']} ({slot}, {item['source']}, {item['lang']})\n",
            f"{theses[record['handle']].title}\n",
            f"{item['text']}\n",
        ]
    missing = [record for record in records if "no-abstract" in record["flags"]]
    lines.append(f"\n# Theses without an abstract ({len(missing)})\n")
    lines += [
        f"- {record['handle']} ({theses[record['handle']].language}): "
        f"{theses[record['handle']].title}"
        for record in missing
    ]
    SAMPLE_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def print_summary(records: list[dict[str, Any]], events: Counter[str]) -> None:
    print(f"{len(records)} theses")
    for slot in SLOTS:
        sources = Counter(record[slot]["source"] if record[slot] else "none" for record in records)
        languages = Counter(record[slot]["lang"] for record in records if record[slot])
        print(f"  {slot}: {dict(sources.most_common())}, languages {dict(languages)}")
    flags = Counter(flag for record in records for flag in record["flags"])
    print(f"  flags: {dict(flags.most_common())}")
    print(f"  cleaning: {dict(sorted(events.items()))}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sample", type=int, default=30, help="abstracts written for reading")
    args = parser.parse_args()
    utf8_stdout()
    require_version("v2")
    theses = read_theses(V1_META_PATH)
    events: Counter[str] = Counter()
    records: list[dict[str, Any]] = []
    for thesis in theses:
        path = V1_TEXTS_DIR / f"{thesis.stem}.txt"
        text = path.read_text(encoding="utf-8", errors="replace") if path.exists() else ""
        records.append(abstracts_of(thesis, text, events))
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    partial = OUTPUT_PATH.with_name(OUTPUT_PATH.name + ".part")
    with partial.open("w", encoding="utf-8") as file:
        for record in records:
            file.write(json.dumps(record, ensure_ascii=False) + "\n")
    partial.replace(OUTPUT_PATH)
    write_sample(records, {thesis.handle: thesis for thesis in theses}, args.sample)
    print_summary(records, events)
    print(f"read {SAMPLE_PATH.relative_to(REPO_ROOT)}")


if __name__ == "__main__":
    main()
