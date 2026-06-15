#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORKFLOW="$REPO_ROOT/.github/workflows/job-dependency-scan.yml"

python3 - "$WORKFLOW" <<'PY'
import re
import sys
from pathlib import Path

workflow = Path(sys.argv[1]).read_text(encoding="utf-8")

checkout_pattern = re.compile(
    r"- name:\s*Checkout HoneyDrunk\.Actions\b"
    r"(?:(?!\n\s*-\s+name:).)*?"
    r"uses:\s*actions/checkout@v[0-9]+"
    r"(?:(?!\n\s*-\s+name:).)*?"
    r"repository:\s*HoneyDrunkStudios/HoneyDrunk\.Actions"
    r"(?:(?!\n\s*-\s+name:).)*?"
    r"path:\s*\.github/actions-repo"
    r"(?:(?!\n\s*-\s+name:).)*?"
    r"ref:\s*\$\{\{\s*steps\.resolve-actions-ref\.outputs\.ref\s*\}\}",
    re.S,
)

script_path = '$GITHUB_WORKSPACE/.github/actions-repo/.github/scripts/dependency-scan.sh'

if not checkout_pattern.search(workflow):
    raise SystemExit(
        "job-dependency-scan.yml must check out HoneyDrunk.Actions to .github/actions-repo at the resolved workflow ref before using shared helpers."
    )

if "id: resolve-actions-ref" not in workflow or "github.workflow_ref" not in workflow:
    raise SystemExit(
        "job-dependency-scan.yml must resolve HoneyDrunk.Actions ref from github.workflow_ref before checkout."
    )

if script_path not in workflow:
    raise SystemExit(
        "job-dependency-scan.yml must invoke dependency-scan.sh from the .github/actions-repo checkout path."
    )
PY

echo "dependency scan workflow wiring smoke test passed"
