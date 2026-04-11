#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_OWNER="HoneyDrunkStudios"
PROJECT_NUMBER="4"
ISSUE_URL=""

usage() {
  cat <<'USAGE'
Usage: hive-backfill-issue.sh --url <issue-url> [--project-owner <owner>] [--project-number <number>]

Environment:
  HIVE_FIELD_MIRROR_TOKEN  GitHub token with repository issues read + org project write.
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --url) ISSUE_URL="$2"; shift 2 ;;
    --project-owner) PROJECT_OWNER="$2"; shift 2 ;;
    --project-number) PROJECT_NUMBER="$2"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; usage; exit 1 ;;
  esac
done

if [[ -z "$ISSUE_URL" ]]; then
  echo "--url is required" >&2
  usage
  exit 1
fi

"${SCRIPT_DIR}/hive-project-mirror.sh" \
  --url "$ISSUE_URL" \
  --project-owner "$PROJECT_OWNER" \
  --project-number "$PROJECT_NUMBER"
