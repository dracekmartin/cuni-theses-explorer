import importlib.util
from pathlib import Path
from types import ModuleType

import pytest

TOOLS = Path(__file__).resolve().parent.parent


def _load(name: str) -> ModuleType:
    # By path, so the scripts need no package and cannot clash with modules of experiments.
    spec = importlib.util.spec_from_file_location(f"tools_{name}", TOOLS / f"{name}.py")
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


commit_message = _load("commit_message")
check = _load("check")


@pytest.mark.parametrize(
    "subject",
    [
        "feat: search by language",
        "docs(eval): versions of the evaluation set",
        "feat(eval, experiments): judgments of the v2 dev part",
        "chore!: drop pre-commit",
        "fix(explorer-api)!: status of an unknown setup",
    ],
)
def test_conventional_subjects_pass(subject: str) -> None:
    assert commit_message.is_valid(subject)


@pytest.mark.parametrize(
    "subject",
    [
        "Feat: upper case type",
        "feature: unknown type",
        "feat(Api): upper case scope",
        "feat(eval,experiments): scopes without a space",
        "feat(): empty scope",
        "feat:no space",
        "feat: ",
        "Merge branch 'main'",
    ],
)
def test_other_subjects_fail(subject: str) -> None:
    assert not commit_message.is_valid(subject)


def test_subject_skips_comments_and_the_diff_of_a_verbose_commit() -> None:
    message = (
        "# Please enter the commit message\n"
        "\n"
        "fix: real subject\n"
        "# ------------------------ >8 ------------------------\n"
        "diff --git a/x b/x\n"
    )
    assert commit_message.subject(message) == "fix: real subject"


def test_a_message_file_with_a_wrong_subject_fails(tmp_path: Path) -> None:
    message = tmp_path / "COMMIT_EDITMSG"
    message.write_text("updated stuff\n", encoding="utf-8")
    assert commit_message.main([str(message)]) == 1


def _package(tmp_path: Path, modules: dict[str, str]) -> Path:
    package = tmp_path / "explorer-fake"
    for name, text in modules.items():
        path = package / "src" / "explorer_fake" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return package


def test_a_skeleton_package_may_leave_its_dependencies_unused(tmp_path: Path) -> None:
    package = _package(tmp_path, {"__init__.py": '"""Fake package."""\n', "inner/__init__.py": ""})
    assert check.deptry_args(package) == ["deptry", "src", "--ignore", "DEP002"]


def test_the_first_module_ends_the_exception_for_unused_dependencies(tmp_path: Path) -> None:
    package = _package(tmp_path, {"__init__.py": "", "core.py": "VALUE = 1\n"})
    assert check.deptry_args(package) == ["deptry", "src"]


def test_code_in_an_init_file_ends_the_exception_too(tmp_path: Path) -> None:
    package = _package(tmp_path, {"__init__.py": '"""Fake package."""\n\nVALUE = 1\n'})
    assert check.deptry_args(package) == ["deptry", "src"]


def test_ruff_gets_only_python_files_of_a_commit() -> None:
    names = ["tools/check.py", "typings/lib.pyi", "notes.ipynb", "CLAUDE.md", "compose.yaml"]
    assert check.python_files(names) == ["tools/check.py", "typings/lib.pyi", "notes.ipynb"]


def test_fix_touches_only_the_named_python_files() -> None:
    steps = check.fix_steps(["tools/check.py", "CLAUDE.md"])
    assert [step.args[-1] for step in steps] == ["tools/check.py", "tools/check.py"]
    assert check.fix_steps(["CLAUDE.md"]) == []
