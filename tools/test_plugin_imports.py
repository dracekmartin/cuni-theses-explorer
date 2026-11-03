"""Plugins import from explorer only explorer.plugin, its public interface for plugins."""

from __future__ import annotations

import tomllib
from pathlib import Path

import grimp

ROOT = Path(__file__).resolve().parent.parent
# A package becomes a plugin by registering in this entry point group, which the registry reads.
PLUGIN_GROUP = "explorer.plugins"
PUBLIC_MODULE = "explorer.plugin"


def plugin_packages(root: Path) -> list[str]:
    """Import names of the packages in libs/ and apps/ that register in the plugin group."""
    names: list[str] = []
    pyprojects = [*root.glob("libs/*/pyproject.toml"), *root.glob("apps/*/pyproject.toml")]
    for pyproject in sorted(pyprojects):
        project = tomllib.loads(pyproject.read_text(encoding="utf-8")).get("project", {})
        if PLUGIN_GROUP in project.get("entry-points", {}):
            names.append(project["name"].replace("-", "_"))
    return names


def forbidden_imports(graph: grimp.ImportGraph, plugin: str) -> list[str]:
    """Imports of non-public explorer modules, as 'importer -> imported (line N)'."""
    found: list[str] = []
    for module in sorted({plugin, *graph.find_descendants(plugin)}):
        for imported in sorted(graph.find_modules_directly_imported_by(module)):
            if imported.split(".")[0] != "explorer":
                continue
            if imported == PUBLIC_MODULE or imported.startswith(PUBLIC_MODULE + "."):
                continue
            details = graph.get_import_details(importer=module, imported=imported)
            lines = ", ".join(str(detail["line_number"]) for detail in details) or "?"
            found.append(f"{module} -> {imported} (line {lines})")
    return found


def test_plugins_import_explorer_only_through_explorer_plugin() -> None:
    plugins = plugin_packages(ROOT)
    if not plugins:
        return
    graph = grimp.build_graph("explorer", *plugins, cache_dir=None)
    assert [found for plugin in plugins for found in forbidden_imports(graph, plugin)] == []


def test_a_package_is_a_plugin_only_when_it_registers_in_the_group(tmp_path: Path) -> None:
    packages = {
        "libs/explorer-foo": '[project.entry-points."explorer.plugins"]\nfoo = "x:Foo"\n',
        "libs/explorer-bar": "",
        "apps/explorer-cli": '[project.entry-points.console_scripts]\ncli = "x:main"\n',
    }
    for folder, entry_points in packages.items():
        (tmp_path / folder).mkdir(parents=True)
        name = folder.split("/")[1]
        (tmp_path / folder / "pyproject.toml").write_text(
            f'[project]\nname = "{name}"\n\n{entry_points}', encoding="utf-8"
        )
    assert plugin_packages(tmp_path) == ["explorer_foo"]


def test_reports_imports_of_explorer_internals_and_nothing_else() -> None:
    graph = grimp.ImportGraph()
    modules = [
        "foo",
        "foo.search",
        "explorer",
        "explorer.plugin",
        "explorer.plugin.types",
        "explorer.plugins_internal",
        "explorer.search",
        "numpy",
    ]
    for module in modules:
        graph.add_module(module)
    imports = [
        ("foo", "explorer.plugin", 1),
        ("foo", "explorer", 2),
        ("foo.search", "explorer.search", 3),
        ("foo.search", "numpy", 4),
        ("foo.search", "explorer.plugin.types", 5),
        ("foo.search", "explorer.plugins_internal", 6),
    ]
    for importer, imported, line in imports:
        graph.add_import(
            importer=importer,
            imported=imported,
            line_number=line,
            line_contents=f"import {imported}",
        )
    assert forbidden_imports(graph, "foo") == [
        "foo -> explorer (line 2)",
        "foo.search -> explorer.plugins_internal (line 6)",
        "foo.search -> explorer.search (line 3)",
    ]
