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
prose = _load("prose")
RULES = prose.load_rules()
EM_DASH = chr(0x2014)


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


def test_an_em_dash_in_markdown_prose_is_reported() -> None:
    lines = prose.markdown_prose(f"Plain text {EM_DASH} more text.\n")
    assert [m.split(": ")[1] for m in prose.findings(RULES, lines, ".md")] == ["em dash"]


def test_code_in_markdown_is_not_prose() -> None:
    text = "Run `a; b` now.\n```sh\nx; y\n```\nDone.\n"
    assert prose.findings(RULES, prose.markdown_prose(text), ".md") == []


def test_a_semicolon_counts_in_markdown_but_not_in_python_comments() -> None:
    assert prose.findings(RULES, prose.markdown_prose("One; two.\n"), ".md")
    assert prose.findings(RULES, prose.python_prose("x = 1  # one; two\n"), ".py") == []


def test_listed_words_count_in_comments_and_docstrings_but_not_in_strings() -> None:
    source = '"""A robust module."""\n\nVALUE = "robust"  # leverage it\n'
    found = prose.findings(RULES, prose.python_prose(source), ".py")
    assert found == ["1: word \"robust\": 'robust'", "3: word \"leverage\": 'leverage'"]


def test_a_line_marked_as_allowed_is_skipped() -> None:
    lines = prose.markdown_prose("A robust estimator of the median. <!-- prose: allow -->\n")
    assert prose.findings(RULES, lines, ".md") == []


def test_added_lines_come_from_the_hunks_of_a_diff() -> None:
    diff = (
        "diff --git a/docs/x.md b/docs/x.md\n"
        "--- a/docs/x.md\n"
        "+++ b/docs/x.md\n"
        "@@ -3,0 +4,2 @@\n"
        "+new\n"
        "+lines\n"
        "@@ -10 +12 @@\n"
        "-old\n"
        "+changed\n"
        "diff --git a/gone.md b/gone.md\n"
        "--- a/gone.md\n"
        "+++ /dev/null\n"
        "@@ -1 +0,0 @@\n"
        "-x\n"
    )
    assert prose.added_lines(diff) == {"docs/x.md": {4, 5, 12}}


def test_commit_subjects_are_checked_as_plain_text() -> None:
    found = prose.check_subjects([f"feat: search {EM_DASH} faster", "fix: plain subject"])
    assert len(found) == 1
    assert "em dash" in found[0]


def test_the_copy_holds_only_the_typography_and_the_english_words() -> None:
    text = "# comment\n[typografie]\n!;\n[en]\n# more\nrobust\n[cs]\nrobustn*\n"
    assert prose.rule_lines(text, ("typografie", "en")) == ["[typografie]", "!;", "[en]", "robust"]


def test_an_action_without_a_full_commit_sha_is_reported(tmp_path: Path) -> None:
    sha = "0" * 40
    (tmp_path / "workflows").mkdir()
    (tmp_path / "workflows" / "ci.yml").write_text(
        "steps:\n"
        "  - uses: actions/checkout@v4\n"
        f"  - uses: actions/cache/restore@{sha} # v4.3.0\n"
        "  - uses: ./local-action\n"
        "    uses: docker://alpine:3\n",
        encoding="utf-8",
    )
    assert check.unpinned_actions(tmp_path) == [
        "workflows/ci.yml:2: actions/checkout@v4 needs a full commit SHA"
    ]


def test_audit_lets_a_listed_vulnerability_pass_only_until_a_fix_exists(tmp_path: Path) -> None:
    ignore = tmp_path / "audit-ignore.txt"
    ignore.write_text("# header\nGHSA-aaaa-bbbb-cccc no fix yet, parser not used\n", "utf-8")
    args = check.audit_args(ignore)
    assert args[-2:] == ["--ignore-until-fixed", "GHSA-aaaa-bbbb-cccc"]
    assert args[5:7] == ["--no-group", "experiments"]


def test_the_web_ui_needs_an_entry_in_dependabot(tmp_path: Path) -> None:
    (tmp_path / ".github").mkdir()
    config = tmp_path / ".github" / "dependabot.yml"
    config.write_text("updates:\n  - package-ecosystem: github-actions\n", encoding="utf-8")
    assert check.dependabot_covers_web(tmp_path) == []
    (tmp_path / "web").mkdir()
    (tmp_path / "web" / "package.json").write_text("{}", encoding="utf-8")
    assert len(check.dependabot_covers_web(tmp_path)) == 1
    config.write_text("updates:\n  - package-ecosystem: npm\n", encoding="utf-8")
    assert check.dependabot_covers_web(tmp_path) == []


def test_a_longer_fence_holds_a_shorter_one_and_indentation_is_allowed() -> None:
    text = "````md\n```sh\nx; y\n```\n````\nAfter.\n  ~~~\n  a; b\n  ~~~\n"
    assert prose.findings(RULES, prose.markdown_prose(text), ".md") == []


def test_an_html_entity_is_no_semicolon_but_mdash_is_an_em_dash() -> None:
    assert prose.findings(RULES, prose.markdown_prose("A&nbsp;B and C\n"), ".md") == []
    found = prose.findings(RULES, prose.markdown_prose("Text &mdash; more.\n"), ".md")
    assert [m.split(": ")[1] for m in found] == ["em dash"]


def test_the_allow_marker_works_inside_inline_code() -> None:
    lines = prose.markdown_prose("A robust estimator. `prose: allow`\n")
    assert prose.findings(RULES, lines, ".md") == []


def test_inline_code_in_a_docstring_is_not_prose() -> None:
    source = '"""Return the `robust_scale` of a sample."""\n'
    assert prose.findings(RULES, prose.python_prose(source), ".py") == []


def test_a_separator_at_the_end_of_a_line_is_reported() -> None:
    lines = prose.markdown_prose("Split the text " + chr(0x2013) + "\nnext line.\n")
    found = prose.findings(RULES, lines, ".md")
    assert [m.split(": ")[0] for m in found] == ["1"]


def test_a_path_with_a_space_and_a_quoted_path_are_read_from_the_header() -> None:
    diff = (
        "diff --git a/my notes.md b/my notes.md\n"
        "--- a/my notes.md\t\n"
        "+++ b/my notes.md\t\n"
        "@@ -1 +1 @@\n"
        "-old\n"
        "+new\n"
        'diff --git "a/say \\"hi\\".md" "b/say \\"hi\\".md"\n'
        '+++ "b/say \\"hi\\".md"\n'
        "@@ -0,0 +1 @@\n"
        "+++ an added line that starts with two plus signs\n"
    )
    assert prose.added_lines(diff) == {"my notes.md": {1}, 'say "hi".md': {1}}


def test_a_missing_list_of_exceptions_means_no_exceptions(tmp_path: Path) -> None:
    assert check.audit_args(tmp_path / "missing.txt")[-2:] == ["--no-group", "experiments"]


def test_a_commented_npm_entry_does_not_count(tmp_path: Path) -> None:
    (tmp_path / ".github").mkdir()
    (tmp_path / "web").mkdir()
    (tmp_path / "web" / "package.json").write_text("{}", encoding="utf-8")
    (tmp_path / ".github" / "dependabot.yml").write_text(
        "updates:\n  # - package-ecosystem: npm\n", encoding="utf-8"
    )
    assert len(check.dependabot_covers_web(tmp_path)) == 1
