#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SCRIPT="$REPO_ROOT/.github/scripts/dependency-scan.sh"
TMP_ROOT="$(mktemp -d)"
trap 'rm -rf "$TMP_ROOT"' EXIT

if ! command -v dotnet >/dev/null 2>&1; then
  echo "dotnet SDK is required for the real dependency scan smoke test." >&2
  exit 1
fi

(
  cd "$TMP_ROOT"

  dotnet new sln -n RealScan >/dev/null
  dotnet new classlib -n App -f net8.0 >/dev/null
  dotnet new classlib -n Lib -f net8.0 >/dev/null
  dotnet sln RealScan.slnx add ./App/App.csproj ./Lib/Lib.csproj >/dev/null

  export DEPENDENCY_SCAN_PROJECT_PATH="RealScan.slnx"
  export DEPENDENCY_SCAN_WORKING_DIRECTORY="."
  bash "$SCRIPT"

  python3 - "$TMP_ROOT/security-reports/vulnerable-packages.json" <<'PY'
import json
import os
import sys

with open(sys.argv[1], encoding="utf-8") as f:
    report = json.load(f)

workspace = os.getcwd()
reported = {
    os.path.normcase(os.path.realpath(os.path.normpath(project.get("path", ""))))
    for project in report.get("projects", [])
}
expected = {
    os.path.normcase(os.path.realpath(os.path.join(workspace, "App", "App.csproj"))),
    os.path.normcase(os.path.realpath(os.path.join(workspace, "Lib", "Lib.csproj"))),
}
missing = expected - reported
if missing:
    raise SystemExit(f"real dotnet scan omitted expected clean project(s): {sorted(missing)}")
PY
)

echo "dependency scan real SDK smoke test passed"
