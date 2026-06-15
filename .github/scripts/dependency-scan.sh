#!/usr/bin/env bash
set -euo pipefail

TARGET="${DEPENDENCY_SCAN_PROJECT_PATH:-}"
WORKING_DIRECTORY="${DEPENDENCY_SCAN_WORKING_DIRECTORY:-.}"

if [ -z "$TARGET" ]; then
  TARGET=$(find . -maxdepth 4 \( -name '*.slnx' -o -name '*.sln' \) | sort | head -n 1 || true)
fi
if [ -z "$TARGET" ]; then
  TARGET=$(find . -maxdepth 4 \( -name '*.csproj' -o -name '*.fsproj' -o -name '*.vbproj' \) | sort | head -n 1 || true)
fi

if [ -z "$TARGET" ]; then
  echo "::error::No solution or package project file found for dependency scanning in working directory '$WORKING_DIRECTORY'. Consider setting 'project-path' input."
  exit 1
fi

echo "Preparing dependency scan target $TARGET..."

mkdir -p ./security-reports
JSON_REPORT=./security-reports/vulnerable-packages.json
ERROR_REPORT=./security-reports/vulnerable-packages.err
EXPECTED_PROJECTS=./security-reports/dependency-scan-expected-projects.txt
PROJECT_REPORT_DIR=./security-reports/dependency-scan-projects
rm -rf "$PROJECT_REPORT_DIR"
mkdir -p "$PROJECT_REPORT_DIR"
: > "$ERROR_REPORT"

# JSON output is required by downstream evaluation. If the scan fails or does
# not produce JSON, fail the job so we do not report a false clean result.
# Solutions are expanded and scanned one project at a time so mixed solution
# behavior cannot mask an individual scan failure. Requires .NET SDK 9+
# (default 10.0.x).
SCAN_ARGS=(package --vulnerable --include-transitive --format json)

if ! command -v python3 >/dev/null 2>&1; then
  echo "::error::python3 is required to validate dependency scan JSON output."
  exit 1
fi

case "$TARGET" in
  *.sln|*.slnx)
    solution_dir=$(dirname "$TARGET")
    solution_projects="$PROJECT_REPORT_DIR/solution-projects.txt"
    if ! dotnet sln "$TARGET" list > "$solution_projects"; then
      echo "::error::Could not enumerate projects from solution target '$TARGET'."
      exit 1
    fi
    while IFS= read -r solution_project; do
      [ -n "$solution_project" ] || continue
      solution_project="${solution_project//$'\r'/}"
      solution_project="${solution_project//\\//}"
      case "${solution_project,,}" in
        *.csproj|*.fsproj|*.vbproj)
          case "$solution_project" in
            /*|[A-Za-z]:/*)
              printf '%s\n' "$solution_project"
              ;;
            *)
              if [ "$solution_dir" = "." ]; then
                printf '%s\n' "$solution_project"
              else
                printf '%s/%s\n' "$solution_dir" "$solution_project"
              fi
              ;;
          esac
          ;;
      esac
    done < "$solution_projects" > "$EXPECTED_PROJECTS"
    ;;
  *.csproj|*.fsproj|*.vbproj)
    printf '%s\n' "$TARGET" > "$EXPECTED_PROJECTS"
    ;;
  *.sqlproj)
    : > "$EXPECTED_PROJECTS"
    ;;
  *)
    find . -maxdepth 4 \( -name '*.csproj' -o -name '*.fsproj' -o -name '*.vbproj' \) \
      | sort > "$EXPECTED_PROJECTS"
    ;;
esac

if [ ! -s "$EXPECTED_PROJECTS" ]; then
  echo "::error::No package project files were found for dependency scanning from target '$TARGET'. SQL/database projects are ignored because 'dotnet list package --vulnerable --format json' does not produce the package report contract for them."
  exit 1
fi

project_count=0
while IFS= read -r PROJECT; do
  [ -n "$PROJECT" ] || continue
  project_count=$((project_count + 1))
  project_report="$PROJECT_REPORT_DIR/project-$project_count.json"
  project_error="$PROJECT_REPORT_DIR/project-$project_count.err"

  echo "Scanning $PROJECT for vulnerable packages..."
  if ! dotnet list "$PROJECT" "${SCAN_ARGS[@]}" > "$project_report" 2> "$project_error"; then
    echo "::error::dotnet list package scan failed for '$PROJECT'."
    cat "$project_error" || true
    exit 1
  fi

  cat "$project_error" >> "$ERROR_REPORT" || true

  if [ ! -s "$project_report" ]; then
    echo "::error::dotnet list completed without producing JSON output for '$PROJECT'."
    cat "$project_error" || true
    exit 1
  fi

  if ! python3 - "$project_report" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as f:
    json.load(f)
PY
  then
    echo "::error::dotnet list completed without producing valid JSON output for '$PROJECT'."
    cat "$project_error" || true
    exit 1
  fi
done < "$EXPECTED_PROJECTS"

if [ "$project_count" -eq 0 ]; then
  echo "::error::No package project files were found for dependency scanning from target '$TARGET'."
  exit 1
fi

if ! python3 - "$JSON_REPORT" "$PROJECT_REPORT_DIR" <<'PY'
import json
import os
import sys

output_path, report_dir = sys.argv[1:3]
combined = {
    "version": 1,
    "parameters": "--vulnerable --include-transitive",
    "sources": [],
    "projects": [],
}
seen_sources = set()

for name in sorted(os.listdir(report_dir)):
    if not name.endswith(".json"):
        continue
    path = os.path.join(report_dir, name)
    with open(path, encoding="utf-8") as f:
        data = json.load(f)

    for source in data.get("sources", []) or []:
        if source not in seen_sources:
            combined["sources"].append(source)
            seen_sources.add(source)

    combined["projects"].extend(data.get("projects", []) or [])

with open(output_path, "w", encoding="utf-8") as f:
    json.dump(combined, f, indent=2)
    f.write("\n")
PY
then
  echo "::error::Could not merge per-project dependency scan reports."
  cat "$ERROR_REPORT" || true
  exit 1
fi

if ! python3 - "$JSON_REPORT" "$EXPECTED_PROJECTS" <<'PY'
import json
import os
import sys

report_path, expected_path = sys.argv[1:3]
workspace = os.getcwd()

def normalize(path: str) -> str:
    path = path.strip().replace("\\", "/")
    if not path:
        return path
    if not os.path.isabs(path):
        path = os.path.join(workspace, path)
    return os.path.normcase(os.path.realpath(os.path.normpath(path)))

with open(expected_path, encoding="utf-8") as f:
    expected = [normalize(line) for line in f if line.strip()]

with open(report_path, encoding="utf-8") as f:
    data = json.load(f)

reported = [
    normalize(project.get("path", ""))
    for project in data.get("projects", [])
    if project.get("path")
]

missing = [expected_project for expected_project in expected if expected_project not in reported]

if missing:
    print("Dependency scan report is missing expected project(s):", file=sys.stderr)
    for project in missing:
        print(f"  - {project}", file=sys.stderr)
    sys.exit(1)
PY
then
  echo "::error::dotnet list produced valid JSON, but the report did not cover every expected project."
  cat "$ERROR_REPORT" || true
  exit 1
fi
