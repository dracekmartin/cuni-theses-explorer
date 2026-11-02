#!/bin/sh
# Renders every view of docs/workspace.dsl to an SVG file in docs/diagrams.
# Run from the repository root: sh docs/diagrams/render.sh
# Needs Java 17 or newer, the Structurizr CLI and PlantUML, given by two variables:
#   STRUCTURIZR_CLI  folder of the unpacked structurizr-cli release (rendered with v2025.11.09)
#   PLANTUML_JAR     path to plantuml.jar (rendered with 1.2026.9)
# PlantUML lays out with Graphviz. Its jar brings Graphviz only on Windows, so install
# graphviz elsewhere, or the layout of the SVG changes without any warning.
set -eu

: "${STRUCTURIZR_CLI:?set STRUCTURIZR_CLI to the folder of the Structurizr CLI}"
: "${PLANTUML_JAR:?set PLANTUML_JAR to the path of plantuml.jar}"

# Java on Windows needs native paths and ';' between classpath entries.
native() {
    if command -v cygpath >/dev/null 2>&1; then cygpath -m "$1"; else printf '%s' "$1"; fi
}
separator=":"
case "$(uname -s)" in MINGW* | MSYS* | CYGWIN*) separator=";" ;; esac

here=$(cd "$(dirname "$0")" && pwd)
cli=$(native "$STRUCTURIZR_CLI")
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT

java -cp "$cli$separator$cli/lib/*" com.structurizr.cli.StructurizrCliApplication export \
    -workspace "$(native "$here/../workspace.dsl")" -format plantuml/c4plantuml \
    -output "$(native "$work")"
# The legend lists every tag of the exporter and adds nothing to these views.
for puml in "$work"/*.puml; do
    sed '/^SHOW_LEGEND/d' "$puml" >"$puml.tmp" && mv "$puml.tmp" "$puml"
done
java -jar "$(native "$PLANTUML_JAR")" -tsvg -charset UTF-8 "$(native "$work")/*.puml"

# Views can be renamed or removed, so the old renders go before the new ones arrive.
rm -f "$here"/*.svg
for svg in "$work"/*.svg; do
    name=$(basename "$svg")
    mv "$svg" "$here/${name#structurizr-}"
    echo "rendered docs/diagrams/${name#structurizr-}"
done
