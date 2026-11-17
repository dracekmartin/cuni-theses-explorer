"""Run the checks of the main CI job the same way CI runs them (decisions 0023 and 0024).

`uv run tools/check.py` runs them all. `--fix FILE...` first lets ruff fix and format the
named files, the files of one change, and never the work of another chat. `--staged` checks
only the commit in progress, which is what the git hook before a commit runs: ruff reads
the files from disk and the check of prose reads the index, which hold the same content
under `git commit --only`. `--audit` looks only for known vulnerabilities, which the weekly
workflow runs.
"""

import argparse
import ast
import os
import re
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HOOKS = "tools/hooks"
PYTHON_SUFFIXES = (".py", ".pyi", ".ipynb")
PROSE = str(ROOT / "tools" / "prose.py")
AUDIT_IGNORE = ROOT / "tools" / "audit-ignore.txt"
# A local action or a container needs no pin. Every other action names a full commit SHA.
PINNED = re.compile(r"(\./|docker://)\S*|[^@\s]+@[0-9a-f]{40}")


@dataclass(frozen=True)
class Step:
    """One command of the run, with the folder it runs in."""

    name: str
    args: list[str]
    cwd: Path = ROOT


@dataclass(frozen=True)
class Check:
    """One check done in Python, which returns its findings."""

    name: str
    run: Callable[[], list[str]]


def packages() -> list[Path]:
    """Return the folders of the packages of the workspace."""
    found = [*ROOT.glob("libs/*/pyproject.toml"), *ROOT.glob("apps/*/pyproject.toml")]
    return sorted(path.parent for path in found)


def _is_docstring(statement: ast.stmt) -> bool:
    return (
        isinstance(statement, ast.Expr)
        and isinstance(statement.value, ast.Constant)
        and isinstance(statement.value.value, str)
    )


def has_code(package: Path) -> bool:
    """Return whether a module of a package holds more than a docstring."""
    for path in (package / "src").rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        if any(not _is_docstring(statement) for statement in tree.body):
            return True
    return False


def deptry_args(package: Path) -> list[str]:
    """Return the command of deptry for one package of the workspace."""
    args = ["deptry", "src"]
    # A skeleton cannot use its dependencies yet. The exception ends with its first code.
    if not has_code(package):
        args += ["--ignore", "DEP002"]
    return args


def audit_args(ignore_file: Path = AUDIT_IGNORE) -> list[str]:
    """Return the command of uv audit with the exceptions of the repository."""
    args = ["uv", "audit", "--preview-features", "audit-command", "--frozen"]
    # The experiments keep the versions that produced their results, nothing deploys them.
    args += ["--no-group", "experiments"]
    if not ignore_file.exists():
        return args
    for line in ignore_file.read_text(encoding="utf-8").splitlines():
        if line.strip() and not line.startswith("#"):
            # Only while no fix exists, so the exception ends with the fix.
            args += ["--ignore-until-fixed", line.split()[0]]
    return args


def unpinned_actions(github: Path = ROOT / ".github") -> list[str]:
    """Return every action in workflows and local actions without a full commit SHA."""
    found: list[str] = []
    files = [*github.glob("workflows/*.y*ml"), *github.glob("actions/**/action.y*ml")]
    for path in sorted(files):
        name = path.relative_to(github).as_posix()
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            match = re.match(r"\s*(?:-\s*)?uses:\s*[\"']?([^\s\"'#]+)", line)
            if match and not PINNED.fullmatch(match.group(1)):
                found.append(f"{name}:{number}: {match.group(1)} needs a full commit SHA")
    return found


def dependabot_covers_web(root: Path = ROOT) -> list[str]:
    """Return a finding when the web UI exists and Dependabot does not update it."""
    if not (root / "web" / "package.json").exists():
        return []
    config = (root / ".github" / "dependabot.yml").read_text(encoding="utf-8")
    # At the start of a line, so a commented entry does not count.
    if re.search(r"^[ \t-]*package-ecosystem:\s*[\"']?npm", config, re.MULTILINE):
        return []
    return ["web/package.json exists, but .github/dependabot.yml has no entry for npm"]


def python_files(names: list[str]) -> list[str]:
    """Return the names that ruff checks."""
    return [name for name in names if name.endswith(PYTHON_SUFFIXES)]


def fix_steps(names: list[str]) -> list[Step]:
    """Return the steps that let ruff fix and format the named files."""
    files = python_files(names)
    if not files:
        return []
    return [
        Step("fixes (ruff)", ["ruff", "check", "--fix", "--force-exclude", "--", *files]),
        Step("formatting (ruff)", ["ruff", "format", "--force-exclude", "--", *files]),
    ]


def full_run(fix: list[str]) -> list[Step | Check]:
    """Return the steps of the main CI job, after the fixes of the named files."""
    return [
        Step("database for tests", ["docker", "compose", "up", "--wait", "test-db"]),
        *fix_steps(fix),
        Step("format (ruff)", ["ruff", "format", "--check", "."]),
        Step("lint (ruff)", ["ruff", "check", "."]),
        Step("types (basedpyright)", ["basedpyright"]),
        Step("layers inside explorer (import-linter)", ["lint-imports"]),
        *(Step(f"dependencies of {p.name} (deptry)", deptry_args(p), p) for p in packages()),
        Step("known vulnerabilities (uv audit)", audit_args()),
        Check("actions pinned by commit SHA", unpinned_actions),
        Check("Dependabot updates the web UI", dependabot_covers_web),
        Step("word list equals the global list", [sys.executable, PROSE, "--words-match"]),
        # The CI job models runs the tests marked model and measures explorer_models_local.
        Step(
            "tests (pytest)",
            ["coverage", "run", "-m", "pytest", "-m", "not model", "--durations=10"],
        ),
        Step("coverage", ["coverage", "report", "--omit=libs/explorer-models-local/*"]),
    ]


def _git(*args: str) -> str:
    return subprocess.run(
        ["git", *args], capture_output=True, check=True, cwd=ROOT, encoding="utf-8"
    ).stdout


def staged_run() -> list[Step | Check]:
    """Return the steps that check the commit in progress."""
    listed = _git("diff", "--cached", "--name-only", "-z", "--diff-filter=ACMR")
    files = python_files([name for name in listed.split("\0") if name])
    steps: list[Step | Check] = [Step("prose", [sys.executable, PROSE, "--staged"])]
    if files:
        steps += [
            Step("format (ruff)", ["ruff", "format", "--check", "--force-exclude", "--", *files]),
            Step("lint (ruff)", ["ruff", "check", "--force-exclude", "--", *files]),
        ]
    return steps


def non_executable_hooks() -> list[str]:
    """Return the hooks that git on Linux would skip, because git keeps them without +x."""
    lines = _git("ls-files", "--stage", "--", HOOKS).splitlines()
    hooks = [line.split("\t", 1)[1] for line in lines if not line.startswith("100755 ")]
    if not hooks:
        return []
    names = " ".join(hooks)
    return [f"not executable in git: {names}. Run git update-index --chmod=+x {names}, commit"]


def turn_on_hooks() -> None:
    """Point git at the hooks of the repository, unless CI runs the script."""
    if os.environ.get("GITHUB_ACTIONS"):
        return
    current = subprocess.run(
        ["git", "config", "--get", "core.hooksPath"],
        capture_output=True,
        check=False,
        cwd=ROOT,
        encoding="utf-8",
    ).stdout.strip()
    if current != HOOKS:
        subprocess.run(["git", "config", "core.hooksPath", HOOKS], check=True, cwd=ROOT)
        print(f"git now runs the hooks in {HOOKS}.")


def _passes(step: Step | Check) -> bool:
    if isinstance(step, Check):
        try:
            found = step.run()
        except OSError as error:
            found = [f"{error.filename}: {error.strerror}"]
        for message in found:
            print(message, file=sys.stderr)
        return not found
    try:
        return subprocess.run(step.args, check=False, cwd=step.cwd).returncode == 0
    except FileNotFoundError:
        print(f"{step.args[0]} not found. Run uv sync, or install it.", file=sys.stderr)
        return False


def run(steps: list[Step | Check], *, verbose: bool) -> list[str]:
    """Run every step, also after a failure, and return the names of the failed ones."""
    failed: list[str] = []
    for step in steps:
        if verbose:
            print(f"\n==> {step.name}", flush=True)
        if not _passes(step):
            failed.append(step.name)
    return failed


def main() -> int:
    """Parse the options and run the checks."""
    parser = argparse.ArgumentParser(description="Run the checks of the main CI job.")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--fix", nargs="+", default=[], metavar="FILE", help="fix these first")
    group.add_argument("--staged", action="store_true", help="check the commit in progress")
    group.add_argument("--audit", action="store_true", help="look for known vulnerabilities")
    options = parser.parse_args()
    if options.staged:
        failed = run(staged_run(), verbose=False)
    elif options.audit:
        failed = run([Step("known vulnerabilities (uv audit)", audit_args())], verbose=True)
    else:
        turn_on_hooks()
        steps = [*full_run(options.fix), Check("git hooks are executable", non_executable_hooks)]
        failed = run(steps, verbose=True)
    if failed:
        print("\nFailed: " + ", ".join(failed), file=sys.stderr)
        return 1
    if not options.staged:
        print("\nAll checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
