#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORKFLOW="$REPO_ROOT/.github/workflows/job-dependency-scan.yml"
export BASH_BIN="${BASH:-bash}"

python3 - "$WORKFLOW" <<'PY'
import re
import os
import subprocess
import sys
import tempfile
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

if "id: resolve-actions-ref" not in workflow:
    raise SystemExit(
        "job-dependency-scan.yml must resolve the HoneyDrunk.Actions ref before checkout."
    )

if "toJson(job)" not in workflow or "workflow_repository" not in workflow or "workflow_sha" not in workflow:
    raise SystemExit(
        "job-dependency-scan.yml must resolve HoneyDrunk.Actions checkout from the job.workflow_repository and job.workflow_sha identity values."
    )

if "github.workflow_ref" in workflow:
    raise SystemExit(
        "job-dependency-scan.yml must not derive reusable workflow self-checkout from caller-oriented github.workflow_ref."
    )

if script_path not in workflow:
    raise SystemExit(
        "job-dependency-scan.yml must invoke dependency-scan.sh from the .github/actions-repo checkout path."
    )

lines = workflow.splitlines()
resolve_index = next(
    (
        index
        for index, line in enumerate(lines)
        if re.match(r"\s*-\s+name:\s*Resolve HoneyDrunk\.Actions ref\s*$", line)
    ),
    None,
)
if resolve_index is None:
    raise SystemExit("Could not find Resolve HoneyDrunk.Actions ref step.")

run_index = next(
    (
        index
        for index in range(resolve_index + 1, len(lines))
        if re.match(r"\s*run:\s*\|\s*$", lines[index])
    ),
    None,
)
if run_index is None:
    raise SystemExit("Resolve HoneyDrunk.Actions ref step must use a literal run block.")

script_lines = []
block_indent = None
for line in lines[run_index + 1:]:
    if line.strip():
        indent = len(line) - len(line.lstrip(" "))
        if block_indent is None:
            block_indent = indent
        elif indent < block_indent:
            break
    if block_indent is not None:
        script_lines.append(line[block_indent:])

resolve_script = "\n".join(script_lines)
if not resolve_script.strip():
    raise SystemExit("Resolve HoneyDrunk.Actions ref script block is empty.")

def run_resolver(actions_ref_input, job_context):
    with tempfile.TemporaryDirectory() as temp_dir:
        script_file = Path(temp_dir) / "resolve.sh"
        output_file = Path(temp_dir) / "github_output.txt"
        script_file.write_text(resolve_script, encoding="utf-8")
        env = os.environ.copy()
        env["ACTIONS_REF_INPUT"] = actions_ref_input
        env["JOB_CONTEXT"] = job_context
        env["GITHUB_OUTPUT"] = str(output_file)
        result = subprocess.run(
            [os.environ.get("BASH_BIN", "bash"), str(script_file)],
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )
        output = output_file.read_text(encoding="utf-8") if output_file.exists() else ""
        return result, output

default_result, default_output = run_resolver(
    "",
    '{"workflow_repository":"HoneyDrunkStudios/HoneyDrunk.Actions","workflow_sha":"abc123"}',
)
if default_result.returncode != 0 or default_output.strip() != "ref=abc123":
    raise SystemExit(
        "Resolve step must emit job.workflow_sha from the serialized job identity when actions-ref is empty."
    )

override_result, override_output = run_resolver(
    "refs/heads/reviewed-actions-ref",
    "{}",
)
if override_result.returncode != 0 or override_output.strip() != "ref=refs/heads/reviewed-actions-ref":
    raise SystemExit("Resolve step must preserve explicit actions-ref overrides.")

invalid_result, _ = run_resolver(
    "",
    '{"workflow_repository":"HoneyDrunkStudios/Caller","workflow_sha":"abc123"}',
)
if invalid_result.returncode == 0:
    raise SystemExit("Resolve step must fail closed when the reusable workflow identity is not HoneyDrunk.Actions.")
PY

echo "dependency scan workflow wiring smoke test passed"
