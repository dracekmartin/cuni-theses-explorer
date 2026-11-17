"""Run the checks of the main CI job the same way CI runs them (decision 0023).

`uv run tools/check.py` runs them all. `--fix FILE...` first lets ruff fix and format the
named files, the files of one change, and never the work of another chat. `--staged` checks
only the Python files of the commit in progress, read from disk, which is what the git hook
before a commit runs.
"""

import argparse
import ast
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HOOKS = "tools/hooks"
PYTHON_SUFFIXES = (".py", ".pyi", ".ipynb")


@dataclass(frozen=True)
class Step:
    """One command of the run, with the folder it runs in."""

    name: str
    args: list[str]
    cwd: Path = ROOT


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


def full_run(fix: list[str]) -> list[Step]:
    """Return the steps of the main CI job, after the fixes of the named files."""
    return [
        Step("database for tests", ["docker", "compose", "up", "--wait", "test-db"]),
        *fix_steps(fix),
        Step("format (ruff)", ["ruff", "format", "--check", "."]),
        Step("lint (ruff)", ["ruff", "check", "."]),
        Step("types (basedpyright)", ["basedpyright"]),
        Step("layers inside explorer (import-linter)", ["lint-imports"]),
        *(Step(f"dependencies of {p.name} (deptry)", deptry_args(p), p) for p in packages()),
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


def staged_run() -> list[Step]:
    """Return the steps that check the Python files of the commit in progress."""
    listed = _git("diff", "--cached", "--name-only", "-z", "--diff-filter=ACMR")
    files = python_files([name for name in listed.split("\0") if name])
    if not files:
        return []
    return [
        Step("format (ruff)", ["ruff", "format", "--check", "--force-exclude", "--", *files]),
        Step("lint (ruff)", ["ruff", "check", "--force-exclude", "--", *files]),
    ]


def non_executable_hooks() -> list[str]:
    """Return the hooks that git on Linux would skip, because git keeps them without +x."""
    lines = _git("ls-files", "--stage", "--", HOOKS).splitlines()
    return [line.split("\t", 1)[1] for line in lines if not line.startswith("100755 ")]


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


def run(steps: list[Step], *, verbose: bool) -> list[str]:
    """Run every step, also after a failure, and return the names of the failed ones."""
    failed: list[str] = []
    for step in steps:
        if verbose:
            print(f"\n==> {step.name}", flush=True)
        try:
            code = subprocess.run(step.args, check=False, cwd=step.cwd).returncode
        except FileNotFoundError:
            print(f"{step.args[0]} not found. Run uv sync, or install it.", file=sys.stderr)
            code = 1
        if code != 0:
            failed.append(step.name)
    return failed


def main() -> int:
    """Parse the options and run the checks."""
    parser = argparse.ArgumentParser(description="Run the checks of the main CI job.")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--fix", nargs="+", default=[], metavar="FILE", help="fix these first")
    group.add_argument("--staged", action="store_true", help="check the files of the commit")
    options = parser.parse_args()
    if options.staged:
        failed = run(staged_run(), verbose=False)
    else:
        turn_on_hooks()
        failed = run(full_run(options.fix), verbose=True)
        hooks = non_executable_hooks()
        if hooks:
            print(
                f"\nNot executable in git: {' '.join(hooks)}. Run "
                f"git update-index --chmod=+x {' '.join(hooks)} and commit the change.",
                file=sys.stderr,
            )
            failed.append("git hooks are executable")
    if failed:
        print("\nFailed: " + ", ".join(failed), file=sys.stderr)
        return 1
    if not options.staged:
        print("\nAll checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
