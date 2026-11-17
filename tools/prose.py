"""Report prose that the writing rules forbid, in changed lines only (decision 0024).

The rules come from `prose-words.txt`, a copy of the typography and the English part of
the author's global list. Markdown counts outside code, Python only in comments and
docstrings. A line that holds `prose: allow` is skipped, so a word that is the right term
in its place can stay, and the exception shows in the diff.

    prose.py --staged            the commit in progress against HEAD (git hook)
    prose.py --diff BASE HEAD    the changes between two commits (CI)
    prose.py --message FILE      the subject of a commit message (git hook)
    prose.py --subjects -        subjects on standard input, one per line (CI)
    prose.py --words-match       the copy equals the global list, when this machine has it
    prose.py --update-words      copy the global list again

Format of a rule line: `word` whole word in any case, `word*` start of a word, several
words a phrase, `!x` a character anywhere, `~name regex` a regular expression. Extensions
after a `!` or `~` rule limit it to those files. CI runs this with the Python of the
runner, so it uses only the standard library.
"""

import argparse
import ast
import io
import re
import subprocess
import sys
import tokenize
from dataclasses import dataclass
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
WORDS = TOOLS / "prose-words.txt"
GLOBAL_WORDS = Path.home() / ".claude" / "skills" / "mh" / "references" / "ai-vyrazy.txt"
COPIED_SECTIONS = ("typografie", "en")
ALLOW = "prose: allow"
EM_DASH = chr(0x2014)
FENCE = re.compile(r"^\s*(`{3,}|~{3,})")
INLINE_CODE = re.compile(r"`[^`\n]*`")
ENTITY = re.compile(r"&(#\d+|#x[0-9a-fA-F]+|[a-zA-Z]+);")
LABELS = {
    EM_DASH: "em dash",
    "---": "em dash of LaTeX",
    ";": "semicolon in prose",
    "pomlcka s mezerami": "dash with spaces as a separator",
    "dve pomlcky s mezerami": "double hyphen with spaces as a separator",
}
HEADER = """\
# Copy of the typography and the English part of the author's global list of words that
# sound generated. On the notebook, tools/check.py fails when the two differ, and
# `python tools/prose.py --update-words` copies them again (decision 0024). The format is
# in tools/prose.py.
"""


@dataclass(frozen=True)
class Rule:
    """One rule of the list."""

    label: str
    pattern: re.Pattern[str]
    extensions: tuple[str, ...]

    def applies_to(self, extension: str) -> bool:
        """Return whether the rule holds in files with this extension."""
        return not self.extensions or extension in self.extensions


def rule_lines(text: str, sections: tuple[str, ...] | None = None) -> list[str]:
    """Return the lines of rules with their section headers, from the named sections."""
    lines: list[str] = []
    section = None
    for raw in text.splitlines():
        line = raw.rstrip()
        if line.startswith("[") and line.endswith("]"):
            section = line[1:-1]
            if sections is None or section in sections:
                lines.append(line)
        elif line and not line.startswith("#") and (sections is None or section in sections):
            lines.append(line)
    return lines


def parse_rule(line: str) -> Rule | None:
    """Return the rule of one line of the list, or None for a section header."""
    if line.startswith("["):
        return None
    if line.startswith("!"):
        char, *extensions = line[1:].split()
        return Rule(LABELS.get(char, char), re.compile(re.escape(char)), tuple(extensions))
    if line.startswith("~"):
        name, regex, *extensions = line[1:].split()
        label = name.replace("_", " ")
        return Rule(LABELS.get(label, label), re.compile(regex), tuple(extensions))
    if line.endswith("*"):
        word = re.escape(line[:-1])
        return Rule(f'word "{line}"', re.compile(rf"(?<![\w-]){word}[\w-]*", re.IGNORECASE), ())
    phrase = r"\s+".join(re.escape(part) for part in line.split())
    return Rule(f'word "{line}"', re.compile(rf"(?<![\w-]){phrase}(?![\w-])", re.IGNORECASE), ())


def load_rules(path: Path = WORDS) -> list[Rule]:
    """Return the rules of a list file."""
    rules = (parse_rule(line) for line in rule_lines(path.read_text(encoding="utf-8")))
    return [rule for rule in rules if rule is not None]


def _blank_code(line: str) -> str:
    # A character that is neither a space nor a letter, so a dash after code still counts as
    # a separator.
    return INLINE_CODE.sub("\x00", line)


def _blank_entities(line: str) -> str:
    # The entity of an em dash is one, any other entity a blank.
    return ENTITY.sub(lambda m: EM_DASH if m.group(1) == "mdash" else "\x00", line)


def markdown_prose(text: str) -> dict[int, str]:
    """Return the lines of a Markdown text outside fenced code, with inline code blanked."""
    lines: dict[int, str] = {}
    fence = None
    for number, line in enumerate(text.splitlines(), start=1):
        match = FENCE.match(line)
        if match and fence is None:
            fence = match.group(1)
            continue
        if match and fence is not None:
            marker = match.group(1)
            # Only a fence of the same character, at least as long and with no text, closes.
            closes = marker[0] == fence[0] and len(marker) >= len(fence)
            if closes and not line.strip()[len(marker) :]:
                fence = None
            continue
        if fence is None and ALLOW not in line:
            lines[number] = _blank_entities(_blank_code(line))
    return lines


def python_prose(text: str) -> dict[int, str]:
    """Return the comments and the lines of docstrings of a Python text by line."""
    lines: dict[int, str] = {}
    source = text.splitlines()
    try:
        tree = ast.parse(text)
        tokens = list(tokenize.generate_tokens(io.StringIO(text).readline))
    except (SyntaxError, tokenize.TokenError):
        return lines
    for token in tokens:
        if token.type == tokenize.COMMENT:
            lines[token.start[0]] = token.string
    documented = (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
    for node in ast.walk(tree):
        if not isinstance(node, documented) or not node.body:
            continue
        first = node.body[0]
        if (
            isinstance(first, ast.Expr)
            and isinstance(first.value, ast.Constant)
            and isinstance(first.value.value, str)
        ):
            end = first.end_lineno or first.lineno
            for number in range(first.lineno, end + 1):
                lines[number] = source[number - 1]
    return {n: _blank_code(line) for n, line in lines.items() if ALLOW not in line}


def prose_of(path: str, text: str) -> dict[int, str]:
    """Return the prose lines of a file by its kind, or none for other files."""
    if path.endswith(".md"):
        return markdown_prose(text)
    if path.endswith(".py"):
        return python_prose(text)
    return {}


def findings(
    rules: list[Rule],
    lines: dict[int, str],
    extension: str,
    context: dict[int, str] | None = None,
) -> list[str]:
    """Return a message for every rule broken in the given lines.

    `context` holds all prose lines of the file, so a separator at the end of a line shows
    together with the start of the next one.
    """
    following = lines if context is None else context
    found: list[str] = []
    for number in sorted(lines):
        line = lines[number]
        if ALLOW in line:
            continue
        text = line + "\n" + following.get(number + 1, "")
        for rule in rules:
            if not rule.applies_to(extension):
                continue
            match = rule.pattern.search(text)
            if match and match.start() < len(line):
                found.append(f"{number}: {rule.label}: {match.group(0).strip()!r}")
    return found


def _new_path(name: str) -> str | None:
    # git ends a name with a space by a tab and quotes a name with special characters.
    name = name.rstrip("\t")
    if name.startswith('"') and name.endswith('"'):
        escapes = {'"': '"', "\\": "\\", "t": "\t", "n": "\n"}
        name = re.sub(r'\\(["\\tn])', lambda m: escapes[m.group(1)], name[1:-1])
    return name[2:] if name.startswith("b/") else None


def added_lines(diff: str) -> dict[str, set[int]]:
    """Return the numbers of added lines by file, from a diff with no context lines."""
    added: dict[str, set[int]] = {}
    path = None
    # Names come only from the header of a file, before its first hunk, so an added line
    # that starts with "++ " is not taken for one.
    header = False
    for line in diff.splitlines():
        if line.startswith("diff --git "):
            header, path = True, None
        elif header and line.startswith("+++ "):
            path = _new_path(line[4:])
        elif line.startswith("@@"):
            header = False
            match = re.match(r"@@ -\S+ \+(\d+)(?:,(\d+))? @@", line)
            if match and path is not None:
                start, count = int(match.group(1)), int(match.group(2) or "1")
                added.setdefault(path, set()).update(range(start, start + count))
    return added


def _git(*args: str) -> str:
    # A file in another encoding must not stop the check, its bytes become replacement marks.
    return subprocess.run(
        ["git", "-c", "core.quotePath=false", *args],
        capture_output=True,
        check=True,
        encoding="utf-8",
        errors="replace",
    ).stdout


def check_changes(diff_args: list[str], revision: str) -> list[str]:
    """Return the findings in the lines that a diff adds to Markdown and Python files."""
    rules = load_rules()
    diff = _git("diff", "-U0", "--no-color", "--no-ext-diff", *diff_args, "--", "*.md", "*.py")
    found: list[str] = []
    for path, numbers in sorted(added_lines(diff).items()):
        prose = prose_of(path, _git("show", f"{revision}:{path}"))
        changed = {n: line for n, line in prose.items() if n in numbers}
        extension = Path(path).suffix
        found += [f"{path}:{m}" for m in findings(rules, changed, extension, prose)]
    return found


def check_subjects(subjects: list[str]) -> list[str]:
    """Return the findings in commit subjects, which count as plain text."""
    rules = load_rules()
    return [
        f"subject {subject!r}: {message.split(': ', 1)[1]}"
        for subject in subjects
        for message in findings(rules, {1: subject}, ".txt")
    ]


def message_subject(message: str) -> str:
    """Return the first line of a commit message that git keeps."""
    for line in message.split("# ------------------------ >8", 1)[0].splitlines():
        if line.strip() and not line.startswith("#"):
            return line
    return ""


def words_match() -> list[str]:
    """Return a finding when the copy differs from the global list on this machine."""
    if not GLOBAL_WORDS.exists():
        return []
    expected = rule_lines(GLOBAL_WORDS.read_text(encoding="utf-8"), COPIED_SECTIONS)
    if rule_lines(WORDS.read_text(encoding="utf-8")) == expected:
        return []
    return [f"{WORDS.name} differs from {GLOBAL_WORDS}, run prose.py --update-words"]


def update_words() -> None:
    """Copy the sections of the global list into the repository."""
    lines = rule_lines(GLOBAL_WORDS.read_text(encoding="utf-8"), COPIED_SECTIONS)
    WORDS.write_text(HEADER + "\n".join(lines) + "\n", encoding="utf-8", newline="\n")


def main(argv: list[str]) -> int:
    """Run the mode that the options name."""
    parser = argparse.ArgumentParser(description="Report forbidden prose in changed lines.")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--staged", action="store_true")
    mode.add_argument("--diff", nargs=2, metavar=("BASE", "HEAD"))
    mode.add_argument("--message", metavar="FILE")
    mode.add_argument("--subjects", metavar="-")
    mode.add_argument("--words-match", action="store_true")
    mode.add_argument("--update-words", action="store_true")
    options = parser.parse_args(argv)
    if options.update_words:
        update_words()
        return 0
    if options.staged:
        found = check_changes(["--cached"], "")
    elif options.diff:
        found = check_changes(options.diff, options.diff[1])
    elif options.message:
        text = Path(options.message).read_text(encoding="utf-8")
        found = check_subjects([message_subject(text)])
    elif options.subjects:
        found = check_subjects([line for line in sys.stdin.read().splitlines() if line])
    else:
        found = words_match()
    for message in found:
        print(message, file=sys.stderr)
    if found:
        print(
            "See Writing style in CLAUDE.md. A term that is right in its place gets "
            f"'{ALLOW}' on its line.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
