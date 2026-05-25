#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
workdir="$(mktemp -d)"
trap 'rm -rf "$workdir"' EXIT

cat > "$workdir/catalog.json" <<'JSON'
{
  "_meta": { "schema_version": "1.1" },
  "nodes": [
    { "id": "pass", "name": "RepoPass", "signal": "ok", "tracked_workflows": ["weekly-health.yml"] },
    { "id": "fail", "name": "RepoFail", "signal": "bad", "tracked_workflows": ["nightly-health.yml"] },
    { "id": "empty", "name": "RepoEmpty", "signal": "empty", "tracked_workflows": ["weekly-empty.yml"] },
    { "id": "missing", "name": "RepoMissing", "signal": "missing", "tracked_workflows": ["publish.yml"] }
  ]
}
JSON

mkdir -p "$workdir/bin"
cat > "$workdir/bin/gh" <<'GH'
#!/usr/bin/env bash
set -euo pipefail
log="${GRID_HEALTH_FAKE_GH_LOG:?}"
cmd="${1:-}"; shift || true
case "$cmd" in
  api)
    include_headers=false
    if [ "${1:-}" = "-i" ]; then include_headers=true; shift; fi
    endpoint="${1:-}"
    case "$endpoint" in
      orgs/HoneyDrunkStudios/repos*)
        printf '%s\n' RepoPass RepoFail RepoEmpty RepoMissing RepoDrift
        ;;
      repos/HoneyDrunkStudios/RepoPass/actions/workflows/weekly-health.yml/runs*)
        printf 'HTTP/2 200\r\ncontent-type: application/json\r\n\r\n{"total_count":1,"workflow_runs":[{"conclusion":"success","created_at":"2999-01-01T00:00:00Z","html_url":"https://example.test/pass"}]}'
        ;;
      repos/HoneyDrunkStudios/RepoFail/actions/workflows/nightly-health.yml/runs*)
        printf 'HTTP/2 200\r\ncontent-type: application/json\r\n\r\n{"total_count":1,"workflow_runs":[{"conclusion":"failure","created_at":"2999-01-01T00:00:00Z","html_url":"https://example.test/fail"}]}'
        ;;
      repos/HoneyDrunkStudios/RepoEmpty/actions/workflows/weekly-empty.yml/runs*)
        printf 'HTTP/2 200\r\ncontent-type: application/json\r\n\r\n{"total_count":0,"workflow_runs":[]}'
        ;;
      repos/HoneyDrunkStudios/RepoMissing/actions/workflows/publish.yml/runs*)
        printf 'HTTP/2 404\r\ncontent-type: application/json\r\n\r\n{"message":"Not Found"}'
        ;;
      *)
        echo "unexpected gh api endpoint: $endpoint" >&2
        exit 9
        ;;
    esac
    ;;
  issue)
    sub="${1:-}"; shift || true
    case "$sub" in
      list)
        true
        ;;
      create)
        printf 'issue create %s\n' "$*" >> "$log"
        printf 'https://github.com/HoneyDrunkStudios/HoneyDrunk.Actions/issues/9001\n'
        ;;
      edit|reopen|close)
        printf 'issue %s %s\n' "$sub" "$*" >> "$log"
        ;;
      *)
        echo "unexpected gh issue subcommand: $sub" >&2
        exit 9
        ;;
    esac
    ;;
  auth)
    exit 0
    ;;
  *)
    echo "unexpected gh command: $cmd" >&2
    exit 9
    ;;
esac
GH
chmod +x "$workdir/bin/gh"

export PATH="$workdir/bin:$PATH"
export GH_TOKEN=fake-token
export GRID_HEALTH_FAKE_GH_LOG="$workdir/gh.log"
unset GITHUB_STEP_SUMMARY || true

output="$workdir/output.md"
"$repo_root/scripts/grid-health-aggregator.sh" "$workdir/catalog.json" > "$output"

grep -q '# 🔴 1 failures' "$output"
grep -q '`RepoPass`' "$output"
grep -q '✅ Pass' "$output"
grep -q '🔴 Fail' "$output"
grep -q '❓ Missing' "$output"
grep -q 'RepoDrift' "$output"
grep -q 'issue create --repo HoneyDrunkStudios/HoneyDrunk.Actions' "$workdir/gh.log"
grep -q 'issue create --repo HoneyDrunkStudios/RepoFail' "$workdir/gh.log"
grep -q 'issue create --repo HoneyDrunkStudios/RepoEmpty' "$workdir/gh.log"
grep -q 'issue create --repo HoneyDrunkStudios/RepoMissing' "$workdir/gh.log"

echo "grid-health aggregator smoke passed"
