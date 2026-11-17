"""Check the form of commit messages, in the git hook and in CI (decision 0023).

The hook passes the file of the message. CI passes `-` and the subjects of the pushed
commits on standard input, one per line. CI runs it with the Python of the runner, so it
uses only the standard library.
"""

import re
import sys
from pathlib import Path

TYPES = ("feat", "fix", "docs", "chore", "refactor", "test", "ci")
# Several scopes are separated by a comma and a space: feat(eval, experiments): ...
PATTERN = re.compile(rf"^({'|'.join(TYPES)})(\([a-z0-9-]+(, [a-z0-9-]+)*\))?!?: \S")
# git writes the diff of a verbose commit below this line, outside the message.
SCISSORS = "# ------------------------ >8 ------------------------"
FORM = "type(scope): subject, type one of " + ", ".join(TYPES)


def subject(message: str) -> str:
    """Return the first line of a message that git keeps, skipping comments."""
    for line in message.split(SCISSORS, 1)[0].splitlines():
        if line.strip() and not line.startswith("#"):
            return line
    return ""


def is_valid(subject_line: str) -> bool:
    """Return whether a subject has the form of a conventional commit."""
    return PATTERN.match(subject_line) is not None


def main(argv: list[str]) -> int:
    """Check the message file in `argv`, or the subjects on standard input after `-`."""
    if argv == ["-"]:
        subjects = [line for line in sys.stdin.read().splitlines() if line]
    elif len(argv) == 1:
        subjects = [subject(Path(argv[0]).read_text(encoding="utf-8"))]
    else:
        print("usage: commit_message.py MESSAGE_FILE | -", file=sys.stderr)
        return 2
    invalid = [line for line in subjects if not is_valid(line)]
    for line in invalid:
        print(f"Not a conventional commit: {line}", file=sys.stderr)
    if invalid:
        print(f"Expected {FORM}.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
