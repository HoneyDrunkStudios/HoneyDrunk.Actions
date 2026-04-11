#!/usr/bin/env bash
set -euo pipefail

PROJECT_OWNER="HoneyDrunkStudios"
PROJECT_NUMBER="4"
ISSUE_URL=""
TOKEN="${HIVE_FIELD_MIRROR_TOKEN:-${GH_TOKEN:-}}"
MAPPING_FILE=".github/config/repo-to-node.yml"

usage() {
  cat <<'USAGE'
Usage: hive-project-mirror.sh --url <issue-url> [--project-owner <owner>] [--project-number <number>] [--mapping-file <path>] [--token <token>]
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --url) ISSUE_URL="$2"; shift 2 ;;
    --project-owner) PROJECT_OWNER="$2"; shift 2 ;;
    --project-number) PROJECT_NUMBER="$2"; shift 2 ;;
    --mapping-file) MAPPING_FILE="$2"; shift 2 ;;
    --token) TOKEN="$2"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; usage; exit 1 ;;
  esac
done

if [[ -z "$ISSUE_URL" ]]; then
  echo "--url is required" >&2
  exit 1
fi

if [[ -z "$TOKEN" ]]; then
  echo "HIVE_FIELD_MIRROR_TOKEN (or GH_TOKEN) must be set" >&2
  exit 1
fi

export GH_TOKEN="$TOKEN"

if [[ ! "$ISSUE_URL" =~ ^https://github.com/([^/]+)/([^/]+)/issues/([0-9]+)$ ]]; then
  echo "Invalid issue URL: $ISSUE_URL" >&2
  exit 1
fi

ISSUE_OWNER="${BASH_REMATCH[1]}"
ISSUE_REPO="${BASH_REMATCH[2]}"
ISSUE_NUMBER="${BASH_REMATCH[3]}"

if [[ ! -f "$MAPPING_FILE" ]]; then
  echo "Mapping file not found: $MAPPING_FILE" >&2
  exit 1
fi

if ! command -v jq >/dev/null 2>&1; then
  echo "jq is required" >&2
  exit 1
fi

if ! command -v gh >/dev/null 2>&1; then
  echo "gh is required" >&2
  exit 1
fi

ISSUE_JSON="$(gh api "repos/${ISSUE_OWNER}/${ISSUE_REPO}/issues/${ISSUE_NUMBER}")"
ISSUE_NODE_ID="$(jq -r '.node_id' <<<"$ISSUE_JSON")"
if [[ -z "$ISSUE_NODE_ID" || "$ISSUE_NODE_ID" == "null" ]]; then
  echo "Could not resolve issue node ID" >&2
  exit 1
fi

mapfile -t LABELS < <(jq -r '.labels[].name' <<<"$ISSUE_JSON" | tr '[:upper:]' '[:lower:]')

WAVE_LABEL=""
TIER_LABEL=""
INITIATIVE_SLUG=""
ADR_LABELS=()

for label in "${LABELS[@]:-}"; do
  case "$label" in
    wave-1|wave-2|wave-3) WAVE_LABEL="$label" ;;
    tier-1|tier-2|tier-3) TIER_LABEL="$label" ;;
    adr-[0-9][0-9][0-9][0-9]) ADR_LABELS+=("${label^^}") ;;
    initiative-*) INITIATIVE_SLUG="${label#initiative-}" ;;
  esac
done

ADR_TEXT=""
if [[ ${#ADR_LABELS[@]} -gt 0 ]]; then
  IFS=$'\n' read -r -d '' -a ADR_SORTED < <(printf '%s\n' "${ADR_LABELS[@]}" | sort -u && printf '\0')
  ADR_TEXT="$(IFS=', '; echo "${ADR_SORTED[*]}")"
fi

NODE_OPTION="$(python3 - <<'PY' "$MAPPING_FILE" "$ISSUE_REPO"
import sys
mapping_path, repo_name = sys.argv[1], sys.argv[2]
value = ""
with open(mapping_path, encoding="utf-8") as f:
    for line in f:
        s = line.strip()
        if not s or s.startswith('#'):
            continue
        if ':' not in s:
            continue
        key, val = s.split(':', 1)
        if key.strip() == repo_name:
            value = val.strip()
            break
print(value)
PY
)"

PROJECT_JSON="$(gh project view "$PROJECT_NUMBER" --owner "$PROJECT_OWNER" --format json)"
PROJECT_ID="$(jq -r '.id' <<<"$PROJECT_JSON")"
if [[ -z "$PROJECT_ID" || "$PROJECT_ID" == "null" ]]; then
  echo "Failed to resolve project id for ${PROJECT_OWNER}/${PROJECT_NUMBER}" >&2
  exit 1
fi

add_item_query='mutation($project:ID!, $content:ID!) { addProjectV2ItemById(input:{projectId:$project, contentId:$content}) { item { id } } }'
ITEM_ID="$(gh api graphql -f query="$add_item_query" -f project="$PROJECT_ID" -f content="$ISSUE_NODE_ID" --jq '.data.addProjectV2ItemById.item.id')"

FIELDS_JSON="$(gh project field-list "$PROJECT_NUMBER" --owner "$PROJECT_OWNER" --format json)"

get_field_id() {
  local name="$1"
  jq -r --arg name "$name" '.fields[] | select(.name == $name) | .id' <<<"$FIELDS_JSON" | head -n1
}

get_single_option_id() {
  local field_name="$1"
  local option_name="$2"
  jq -r --arg field "$field_name" --arg option "$option_name" '
    .fields[]
    | select(.name == $field)
    | .options[]?
    | select(.name == $option)
    | .id
  ' <<<"$FIELDS_JSON" | head -n1
}

update_single_select() {
  local field_id="$1"
  local option_id="$2"
  local label="$3"
  if [[ -z "$field_id" || -z "$option_id" ]]; then
    echo "::warning::Skipping ${label}; missing field/option id"
    return 0
  fi
  local query='mutation($project:ID!, $item:ID!, $field:ID!, $option:String!) { updateProjectV2ItemFieldValue(input:{projectId:$project,itemId:$item,fieldId:$field,value:{singleSelectOptionId:$option}}) { projectV2Item { id } } }'
  gh api graphql -f query="$query" -f project="$PROJECT_ID" -f item="$ITEM_ID" -f field="$field_id" -f option="$option_id" >/dev/null
}

update_text() {
  local field_id="$1"
  local text="$2"
  local label="$3"
  if [[ -z "$field_id" ]]; then
    echo "::warning::Skipping ${label}; missing field id"
    return 0
  fi
  local query='mutation($project:ID!, $item:ID!, $field:ID!, $text:String!) { updateProjectV2ItemFieldValue(input:{projectId:$project,itemId:$item,fieldId:$field,value:{text:$text}}) { projectV2Item { id } } }'
  gh api graphql -f query="$query" -f project="$PROJECT_ID" -f item="$ITEM_ID" -f field="$field_id" -f text="$text" >/dev/null
}

WAVE_FIELD_ID="$(get_field_id 'Wave')"
TIER_FIELD_ID="$(get_field_id 'Tier')"
NODE_FIELD_ID="$(get_field_id 'Node')"
ADR_FIELD_ID="$(get_field_id 'ADR')"
INITIATIVE_FIELD_ID="$(get_field_id 'Initiative')"

WAVE_TARGET='N/A'
case "$WAVE_LABEL" in
  wave-1) WAVE_TARGET='Wave 1' ;;
  wave-2) WAVE_TARGET='Wave 2' ;;
  wave-3) WAVE_TARGET='Wave 3' ;;
esac
WAVE_OPTION_ID="$(get_single_option_id 'Wave' "$WAVE_TARGET")"
update_single_select "$WAVE_FIELD_ID" "$WAVE_OPTION_ID" 'Wave'

if [[ -n "$TIER_LABEL" ]]; then
  TIER_TARGET="Tier ${TIER_LABEL#tier-}"
  TIER_OPTION_ID="$(get_single_option_id 'Tier' "$TIER_TARGET")"
  if [[ -z "$TIER_OPTION_ID" ]]; then
    TIER_OPTION_ID="$(get_single_option_id 'Tier' "${TIER_LABEL#tier-}")"
  fi
  update_single_select "$TIER_FIELD_ID" "$TIER_OPTION_ID" 'Tier'
fi

if [[ -n "$NODE_OPTION" ]]; then
  NODE_OPTION_ID="$(get_single_option_id 'Node' "$NODE_OPTION")"
  update_single_select "$NODE_FIELD_ID" "$NODE_OPTION_ID" 'Node'
else
  echo "::warning::No node mapping found for repository ${ISSUE_REPO}"
fi

if [[ -n "$INITIATIVE_SLUG" ]]; then
  INITIATIVE_OPTION_ID="$(get_single_option_id 'Initiative' "$INITIATIVE_SLUG")"
  if [[ -z "$INITIATIVE_OPTION_ID" ]]; then
    INITIATIVE_OPTION_ID="$(get_single_option_id 'Initiative' "Initiative ${INITIATIVE_SLUG}")"
  fi
  if [[ -n "$INITIATIVE_OPTION_ID" ]]; then
    update_single_select "$INITIATIVE_FIELD_ID" "$INITIATIVE_OPTION_ID" 'Initiative'
  else
    echo "::warning::No Initiative option matched label initiative-${INITIATIVE_SLUG}"
  fi
fi

if [[ -n "$ADR_TEXT" ]]; then
  update_text "$ADR_FIELD_ID" "$ADR_TEXT" 'ADR'
fi

echo "Mirrored fields for ${ISSUE_OWNER}/${ISSUE_REPO}#${ISSUE_NUMBER}"
