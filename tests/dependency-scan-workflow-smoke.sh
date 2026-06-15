#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SCRIPT="$REPO_ROOT/.github/scripts/dependency-scan.sh"
TMP_ROOT="$(mktemp -d)"
trap 'rm -rf "$TMP_ROOT"' EXIT

assert_contains() {
  local file="$1"
  local expected="$2"
  if ! grep -Fq "$expected" "$file"; then
    echo "Expected '$file' to contain: $expected" >&2
    echo "--- $file ---" >&2
    cat "$file" >&2 || true
    exit 1
  fi
}

install_fake_dotnet() {
  local bin_dir="$1"
  mkdir -p "$bin_dir"
  cat > "$bin_dir/dotnet" <<'SH'
#!/usr/bin/env bash
set -euo pipefail

if [ "${1:-}" = "sln" ]; then
  cat "$FAKE_SOLUTION_LIST"
  exit 0
fi

if [ "${1:-}" = "list" ]; then
  project="$2"
  case "${FAKE_DOTNET_MODE:-clean}" in
    invalid-json)
      echo "not json"
      exit 0
      ;;
    missing-project)
      echo '{"version":1,"sources":[],"projects":[{"path":"Missing.csproj","frameworks":[]}]}'
      exit 0
      ;;
    clean)
      python3 - "$project" <<'PY'
import json
import os
import sys

project = sys.argv[1]
print(json.dumps({
    "version": 1,
    "sources": ["https://api.nuget.org/v3/index.json"],
    "projects": [
        {
            "path": os.path.realpath(os.path.normpath(project)),
            "frameworks": [
                {
                    "framework": "net10.0",
                    "topLevelPackages": [],
                    "transitivePackages": []
                }
            ]
        }
    ]
}))
PY
      exit 0
      ;;
  esac
fi

echo "Unexpected fake dotnet invocation: $*" >&2
exit 64
SH
  chmod +x "$bin_dir/dotnet"
}

run_case() {
  local name="$1"
  local mode="$2"
  local work_dir="$TMP_ROOT/$name"
  local bin_dir="$work_dir/bin"
  mkdir -p "$work_dir/solutions/App" "$work_dir/solutions/Lib" "$work_dir/solutions/App/Api" "$work_dir/solutions/App/Database"
  : > "$work_dir/solutions/Lib/Lib.csproj"
  : > "$work_dir/solutions/App/Api/Api.csproj"
  : > "$work_dir/solutions/App/Database/Database.sqlproj"
  cat > "$work_dir/solution-list.txt" <<'EOF'
Project(s)
----------
..\Lib\Lib.csproj
.\Api\Api.csproj
.\Database\Database.sqlproj
EOF

  install_fake_dotnet "$bin_dir"
  (
    cd "$work_dir"
    export PATH="$bin_dir:$PATH"
    export FAKE_DOTNET_MODE="$mode"
    export FAKE_SOLUTION_LIST="$work_dir/solution-list.txt"
    export DEPENDENCY_SCAN_PROJECT_PATH="solutions/App/App.slnx"
    export DEPENDENCY_SCAN_WORKING_DIRECTORY="."
    bash "$SCRIPT" > "$work_dir/stdout.txt" 2> "$work_dir/stderr.txt"
  )
}

run_case clean-multi-project clean
python3 - "$TMP_ROOT/clean-multi-project/security-reports/vulnerable-packages.json" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as f:
    report = json.load(f)

paths = [project["path"] for project in report["projects"]]
if len(paths) != 2:
    raise SystemExit(f"expected 2 scanned package projects, got {len(paths)}: {paths}")
if any(path.endswith(".sqlproj") for path in paths):
    raise SystemExit(f"sqlproj should not be scanned: {paths}")
PY

if run_case invalid-json invalid-json; then
  echo "invalid JSON scan should fail" >&2
  exit 1
else
  assert_contains "$TMP_ROOT/invalid-json/stdout.txt" "without producing valid JSON"
fi

if run_case missing-project missing-project; then
  echo "missing project coverage should fail" >&2
  exit 1
else
  assert_contains "$TMP_ROOT/missing-project/stdout.txt" "did not cover every expected project"
fi

empty_dir="$TMP_ROOT/no-target"
mkdir -p "$empty_dir/bin"
install_fake_dotnet "$empty_dir/bin"
(
  cd "$empty_dir"
  export PATH="$empty_dir/bin:$PATH"
  export DEPENDENCY_SCAN_PROJECT_PATH=""
  export DEPENDENCY_SCAN_WORKING_DIRECTORY="."
  if bash "$SCRIPT" > stdout.txt 2> stderr.txt; then
    echo "no target scan should fail" >&2
    exit 1
  fi
)
assert_contains "$empty_dir/stdout.txt" "No solution or package project file found"

echo "dependency scan workflow smoke tests passed"
