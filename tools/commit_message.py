"""Check the form of commit messages, in the git hook and in CI (decisions 0023 and 0025).

The hook passes the file of the message. Comment lines in it are skipped, because git drops
them from a message written in the editor. CI passes `-` and the stored messages on
standard input, separated by NUL characters (`git log --format=%B%x00`), and there every
line counts. The scopes of a subject must be names of folders of the repository, in the
index, in HEAD or in a revision given by `--base`, so a commit may name a folder that it
deletes. CI runs this with the Python of the runner, so it uses only the standard library.
"""

import argparse
import re
import subprocess
import sys
from pathlib import Path

TYPES = ("feat", "fix", "docs", "chore", "refactor", "test", "ci")
# Several scopes are separated by a comma and a space: feat(eval, experiments): ...
PATTERN = re.compile(rf"^({'|'.join(TYPES)})(?:\(([a-z0-9-]+(?:, [a-z0-9-]+)*)\))?!?: \S")
# Dependabot names its pull requests chore(deps): ... and chore(deps-dev): ...
OTHER_SCOPES = frozenset({"deps", "deps-dev"})
# git writes the diff of a verbose commit below this line, outside the message.
SCISSORS = "------------------------ >8 ------------------------"
FORM = "one line type(scope): subject, type one of " + ", ".join(TYPES)


def kept_lines(message: str, comment: str | None = "#") -> list[str]:
    """Return the lines of a message that git keeps, without empty and comment lines."""
    if comment is not None:
        message = message.split(f"{comment} {SCISSORS}", 1)[0]
    lines = [line for line in message.splitlines() if line.strip()]
    if comment is None:
        return lines
    return [line for line in lines if not line.startswith(comment)]


def subject(message: str, comment: str | None = "#") -> str:
    """Return the first line of a message that git keeps."""
    lines = kept_lines(message, comment)
    return lines[0] if lines else ""


def is_valid(subject_line: str) -> bool:
    """Return whether a subject has the form of a conventional commit."""
    return PATTERN.match(subject_line) is not None


def scopes(subject_line: str) -> list[str]:
    """Return the scopes that a valid subject names."""
    match = PATTERN.match(subject_line)
    return match.group(2).split(", ") if match and match.group(2) else []


def _git(*args: str, cwd: str | None = None) -> str:
    # A revision that does not exist, such as HEAD before the first commit, adds nothing.
    return subprocess.run(
        ["git", *args], capture_output=True, check=False, cwd=cwd, encoding="utf-8"
    ).stdout


def comment_char() -> str:
    """Return the character that starts a comment in the editor of a commit message."""
    configured = _git("config", "core.commentChar").strip()
    # "auto" picks a character per message, so only a fixed one is known here.
    return configured if len(configured) == 1 else "#"


def folders(revisions: list[str]) -> set[str]:
    """Return the names of all folders in the index and in the given revisions."""
    # From the top of the tree, because git lists only the folder it runs in.
    top = _git("rev-parse", "--show-toplevel").strip() or None
    listings = [_git("ls-files", cwd=top)]
    listings += [_git("ls-tree", "-r", "--name-only", rev, cwd=top) for rev in revisions]
    names: set[str] = set()
    for listing in listings:
        for path in listing.splitlines():
            names.update(path.split("/")[:-1])
    return names


def problems(message: str, known: set[str], comment: str | None = "#") -> list[str]:
    """Return what is wrong with one commit message."""
    line = subject(message, comment)
    if not is_valid(line):
        return [f"Not a conventional commit: {line}"]
    found: list[str] = []
    unknown = [scope for scope in scopes(line) if scope not in known | OTHER_SCOPES]
    if unknown:
        found.append(f"No folder of the repository is called {', '.join(unknown)}: {line}")
    if len(kept_lines(message, comment)) > 1:
        found.append(f"The message has more than its subject: {line}")
    return found


def main(argv: list[str]) -> int:
    """Check the message file, or the stored messages on standard input after `-`."""
    parser = argparse.ArgumentParser(description="Check the form of commit messages.")
    parser.add_argument("source", help="the file of a message, or - for standard input")
    parser.add_argument("--base", action="append", default=[], help="a revision with folders")
    options = parser.parse_args(argv)
    if options.source == "-":
        messages = [m for m in sys.stdin.read().split("\0") if m.strip()]
        comment = None
    else:
        messages = [Path(options.source).read_text(encoding="utf-8")]
        comment = comment_char()
    known = folders(["HEAD", *options.base])
    found = [problem for message in messages for problem in problems(message, known, comment)]
    for problem in found:
        print(problem, file=sys.stderr)
    if found:
        print(f"Expected {FORM}, the scope named after folders.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
