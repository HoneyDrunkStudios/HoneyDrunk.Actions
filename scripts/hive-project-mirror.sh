#!/usr/bin/env bash
set -euo pipefail

PROJECT_OWNER="HoneyDrunkStudios"
PROJECT_NUMBER="4"
ISSUE_URL=""
TOKEN="${HIVE_FIELD_MIRROR_TOKEN:-${GH_TOKEN:-}}"
MAPPING_FILE=".github/config/repo-to-node.yml"
ACTOR=""

usage() {
  cat <<'USAGE'
Usage: hive-project-mirror.sh --url <issue-url> [--actor <Agent|Human>] [--project-owner <owner>] [--project-number <number>] [--mapping-file <path>] [--token <token>]
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --url) ISSUE_URL="$2"; shift 2 ;;
    --project-owner) PROJECT_OWNER="$2"; shift 2 ;;
    --project-number) PROJECT_NUMBER="$2"; shift 2 ;;
    --mapping-file) MAPPING_FILE="$2"; shift 2 ;;
    --actor) ACTOR="$2"; shift 2 ;;
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

if ! command -v python3 >/dev/null 2>&1; then
  echo "python3 is required for repo-to-node mapping lookup" >&2
  exit 1
fi

# Retry a `gh` invocation up to 3 times when stderr indicates a rate-limit.
# Backoff is exponential, capped at 60s. Non-rate-limit failures return the
# original exit code so the caller can react. Keep stderr behavior identical
# to a plain `gh` call on success and on terminal failure.
gh_retry() {
  local attempt=1
  local max_attempts=3
  local stderr_file output exit_code stderr_content
  stderr_file="$(mktemp)"
  while :; do
    if output="$(gh "$@" 2>"$stderr_file")"; then
      cat "$stderr_file" >&2
      rm -f "$stderr_file"
      printf '%s' "$output"
      return 0
    fi
    exit_code=$?
    stderr_content="$(<"$stderr_file")"
    if [[ "$stderr_content" == *"rate limit"* ]] \
      || [[ "$stderr_content" == *"secondary rate limit"* ]] \
      || [[ "$stderr_content" == *"abuse detection"* ]]; then
      if (( attempt >= max_attempts )); then
        echo "$stderr_content" >&2
        echo "::error::gh exhausted ${max_attempts} retries after rate-limit responses" >&2
        rm -f "$stderr_file"
        return "$exit_code"
      fi
      local backoff=$(( 2 ** attempt ))
      (( backoff > 60 )) && backoff=60
      echo "::warning::gh rate-limited; retrying in ${backoff}s (attempt ${attempt}/${max_attempts})" >&2
      sleep "$backoff"
      attempt=$(( attempt + 1 ))
      : > "$stderr_file"
      continue
    fi
    cat "$stderr_file" >&2
    rm -f "$stderr_file"
    return "$exit_code"
  done
}

ISSUE_JSON="$(gh_retry api "repos/${ISSUE_OWNER}/${ISSUE_REPO}/issues/${ISSUE_NUMBER}")"
ISSUE_NODE_ID="$(jq -r '.node_id' <<<"$ISSUE_JSON")"
if [[ -z "$ISSUE_NODE_ID" || "$ISSUE_NODE_ID" == "null" ]]; then
  echo "Could not resolve issue node ID" >&2
  exit 1
fi

mapfile -t LABELS < <(jq -r '.labels[].name' <<<"$ISSUE_JSON" | tr -d '\r' | tr '[:upper:]' '[:lower:]')

WAVE_LABEL=""
TIER_LABEL=""
INITIATIVE_SLUG=""
ADR_LABELS=()

for label in "${LABELS[@]}"; do
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

if [[ -n "${HIVE_PROJECT_METADATA_JSON:-}" ]]; then
  PROJECT_JSON="$(jq -c '.project' <<<"$HIVE_PROJECT_METADATA_JSON")"
else
  PROJECT_JSON="$(gh_retry project view "$PROJECT_NUMBER" --owner "$PROJECT_OWNER" --format json)"
fi
PROJECT_ID="$(jq -r '.id' <<<"$PROJECT_JSON")"
if [[ -z "$PROJECT_ID" || "$PROJECT_ID" == "null" ]]; then
  echo "Failed to resolve project id for ${PROJECT_OWNER}/${PROJECT_NUMBER}" >&2
  exit 1
fi

add_item_query='mutation($project:ID!, $content:ID!) { addProjectV2ItemById(input:{projectId:$project, contentId:$content}) { item { id } } }'

ITEM_ID=""
set +e
ADD_ITEM_OUTPUT="$(gh api graphql -f query="$add_item_query" -f project="$PROJECT_ID" -f content="$ISSUE_NODE_ID" 2>&1)"
ADD_ITEM_EXIT_CODE=$?
set -e

if [[ $ADD_ITEM_EXIT_CODE -eq 0 ]]; then
  ITEM_ID="$(jq -r '.data.addProjectV2ItemById.item.id // empty' <<<"$ADD_ITEM_OUTPUT")"
else
  echo "::warning::addProjectV2ItemById failed; attempting existing item lookup."
fi

if [[ -z "$ITEM_ID" ]]; then
  lookup_query='query($issue: ID!) { node(id: $issue) { ... on Issue { projectItems(first: 100) { nodes { id project { id } } } } } }'
  LOOKUP_JSON="$(gh api graphql -f query="$lookup_query" -f issue="$ISSUE_NODE_ID")"
  ITEM_ID="$(jq -r --arg project_id "$PROJECT_ID" '.data.node.projectItems.nodes[] | select(.project.id == $project_id) | .id' <<<"$LOOKUP_JSON" | head -n1)"
fi

if [[ -z "$ITEM_ID" ]]; then
  echo "Failed to resolve project item ID for issue node ${ISSUE_NODE_ID}" >&2
  if [[ $ADD_ITEM_EXIT_CODE -ne 0 ]]; then
    echo "addProjectV2ItemById error output: $ADD_ITEM_OUTPUT" >&2
  fi
  exit 1
fi

if [[ -n "${HIVE_PROJECT_METADATA_JSON:-}" ]]; then
  FIELDS_JSON="$(jq -c '.fields' <<<"$HIVE_PROJECT_METADATA_JSON")"
else
  FIELDS_JSON="$(gh_retry project field-list "$PROJECT_NUMBER" --owner "$PROJECT_OWNER" --format json)"
fi

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

# Ensure a single-select field has the given option. Echoes the option's id
# on success (existing or newly created), empty on failure. Idempotent: if the
# option already exists on the field per a fresh live query, returns its id
# without mutating. This matters when batch metadata is cached upstream — a
# stale FIELDS_JSON in the parent script can route a packet here even though
# a previous packet in the same batch already added the option.
# Existing options are preserved with their original color and description
# (gh field-list omits these, so we query them via GraphQL).
ensure_single_select_option() {
  local field_name="$1"
  local option_name="$2"
  local existing
  if ! existing="$(gh api graphql \
    -f query='query($p:ID!,$f:String!){node(id:$p){... on ProjectV2{field(name:$f){... on ProjectV2SingleSelectField{id options{id name color description}}}}}}' \
    -f p="$PROJECT_ID" -f f="$field_name" 2>&1)"; then
    echo "ensure_single_select_option: query failed for field '$field_name': $existing" >&2
    return 1
  fi
  local field_id
  field_id="$(jq -r '.data.node.field.id // empty' <<<"$existing")"
  if [[ -z "$field_id" ]]; then
    return 1
  fi
  # Idempotency: if the option is already present on the live field, return
  # its id and skip the mutate. Avoids GitHub-side duplicate-rejection when
  # cached metadata is stale.
  local existing_id
  existing_id="$(jq -r --arg name "$option_name" '
    .data.node.field.options[]?
    | select(.name == $name)
    | .id
  ' <<<"$existing" | head -n1)"
  if [[ -n "$existing_id" ]]; then
    printf '%s' "$existing_id"
    return 0
  fi
  local options_literal
  options_literal="$(jq -r --arg name "$option_name" '
    (.data.node.field.options + [{name:$name, color:"GRAY", description:""}])
    | map("{name:" + (.name | tojson) + ",color:" + .color + ",description:" + ((.description // "") | tojson) + "}")
    | "[" + join(",") + "]"
  ' <<<"$existing")"
  local mutate
  mutate="mutation{updateProjectV2Field(input:{fieldId:\"${field_id}\",singleSelectOptions:${options_literal}}){projectV2Field{... on ProjectV2SingleSelectField{options{id name}}}}}"
  local result
  if ! result="$(gh api graphql -f query="$mutate" 2>&1)"; then
    echo "ensure_single_select_option: mutation failed for field '$field_name' option '$option_name': $result" >&2
    return 1
  fi
  jq -r --arg name "$option_name" '.data.updateProjectV2Field.projectV2Field.options[]? | select(.name == $name) | .id' <<<"$result"
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
  gh_retry api graphql -f query="$query" -f project="$PROJECT_ID" -f item="$ITEM_ID" -f field="$field_id" -f option="$option_id" >/dev/null
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
  gh_retry api graphql -f query="$query" -f project="$PROJECT_ID" -f item="$ITEM_ID" -f field="$field_id" -f text="$text" >/dev/null
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
  if [[ -z "$INITIATIVE_OPTION_ID" ]]; then
    echo "Auto-creating Initiative option: ${INITIATIVE_SLUG}"
    INITIATIVE_OPTION_ID="$(ensure_single_select_option 'Initiative' "$INITIATIVE_SLUG")"
  fi
  if [[ -n "$INITIATIVE_OPTION_ID" ]]; then
    update_single_select "$INITIATIVE_FIELD_ID" "$INITIATIVE_OPTION_ID" 'Initiative'
  else
    echo "::warning::Failed to resolve or create Initiative option: ${INITIATIVE_SLUG}"
  fi
fi

if [[ -n "$ADR_TEXT" ]]; then
  update_text "$ADR_FIELD_ID" "$ADR_TEXT" 'ADR'
fi

if [[ -n "$ACTOR" ]]; then
  case "${ACTOR,,}" in
    agent) ACTOR='Agent' ;;
    human) ACTOR='Human' ;;
    *)
      echo "::warning::Invalid --actor value '${ACTOR}'. Allowed: Agent, Human"
      ACTOR=''
      ;;
  esac
  if [[ -n "$ACTOR" ]]; then
    ACTOR_FIELD_ID="$(get_field_id 'Actor')"
    ACTOR_OPTION_ID="$(get_single_option_id 'Actor' "$ACTOR")"
    update_single_select "$ACTOR_FIELD_ID" "$ACTOR_OPTION_ID" 'Actor'
  fi
fi

echo "Mirrored fields for ${ISSUE_OWNER}/${ISSUE_REPO}#${ISSUE_NUMBER}"
