#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PACKETS_DIR=""
MANIFEST=""
PROJECT_OWNER="HoneyDrunkStudios"
PROJECT_NUMBER="4"
MAPPING_FILE="${SCRIPT_DIR}/../.github/config/repo-to-node.yml"
LINK_DEPS=1
ARCHITECTURE_REPO="HoneyDrunkStudios/HoneyDrunk.Architecture"

usage() {
  cat <<'USAGE'
Usage: file-packets.sh --packets-dir <dir> --manifest <file> [options]

Files issue packets from HoneyDrunk.Architecture as GitHub Issues, adds them
to The Hive, mirrors custom fields, and links declared dependencies.

Required:
  --packets-dir <dir>         Directory containing active packet .md files.
  --manifest <file>           Path to filed-packets.json manifest (created if absent).

Options:
  --project-owner <owner>     The Hive project owner (default: HoneyDrunkStudios).
  --project-number <number>   The Hive project number (default: 4).
  --mapping-file <path>       Path to repo-to-node.yml (default: alongside this script).
  --architecture-repo <slug>  owner/name of Architecture repo (default: HoneyDrunkStudios/HoneyDrunk.Architecture).
  --link-deps                 Run the dependency-linking pass (default).
  --skip-link-deps            Skip the dependency-linking pass.
  -h, --help                  Show this help.

Environment:
  GH_TOKEN                    Required. Used by gh for issue creation and commenting.
  HIVE_FIELD_MIRROR_TOKEN     Token used by hive-project-mirror.sh. Defaults to GH_TOKEN.
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --packets-dir) PACKETS_DIR="$2"; shift 2 ;;
    --manifest) MANIFEST="$2"; shift 2 ;;
    --project-owner) PROJECT_OWNER="$2"; shift 2 ;;
    --project-number) PROJECT_NUMBER="$2"; shift 2 ;;
    --mapping-file) MAPPING_FILE="$2"; shift 2 ;;
    --architecture-repo) ARCHITECTURE_REPO="$2"; shift 2 ;;
    --link-deps) LINK_DEPS=1; shift ;;
    --skip-link-deps) LINK_DEPS=0; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; usage; exit 1 ;;
  esac
done

if [[ -z "$PACKETS_DIR" ]]; then
  echo "--packets-dir is required" >&2
  exit 1
fi
if [[ -z "$MANIFEST" ]]; then
  echo "--manifest is required" >&2
  exit 1
fi
if [[ ! -d "$PACKETS_DIR" ]]; then
  echo "Packets directory not found: $PACKETS_DIR" >&2
  exit 1
fi
if [[ ! -f "$MAPPING_FILE" ]]; then
  echo "Mapping file not found: $MAPPING_FILE" >&2
  exit 1
fi

: "${GH_TOKEN:?GH_TOKEN must be set}"
export GH_TOKEN
export HIVE_FIELD_MIRROR_TOKEN="${HIVE_FIELD_MIRROR_TOKEN:-$GH_TOKEN}"

for bin in gh jq python3 git; do
  if ! command -v "$bin" >/dev/null 2>&1; then
    echo "$bin is required" >&2
    exit 1
  fi
done

PACKETS_DIR_ABS="$(cd "$PACKETS_DIR" && pwd)"
REPO_ROOT="$(git -C "$PACKETS_DIR_ABS" rev-parse --show-toplevel)"

mkdir -p "$(dirname "$MANIFEST")"
if [[ ! -f "$MANIFEST" ]]; then
  echo "{}" > "$MANIFEST"
fi

MIRROR_SCRIPT="${SCRIPT_DIR}/hive-project-mirror.sh"
if [[ ! -x "$MIRROR_SCRIPT" ]]; then
  echo "hive-project-mirror.sh not found or not executable at $MIRROR_SCRIPT" >&2
  exit 1
fi

# Extract frontmatter + body + title as a tab-separated JSON blob.
# Emits one line: <json>\n where json has: title, body, target_repo, labels[], initiative, actor, dependencies[], adrs[]
parse_packet() {
  local packet_file="$1"
  python3 - "$packet_file" <<'PY'
import json, re, sys
try:
    import yaml
except ImportError:
    print("PyYAML is required", file=sys.stderr)
    sys.exit(1)

path = sys.argv[1]
with open(path, encoding="utf-8") as f:
    raw = f.read()

fm = {}
body = raw
m = re.match(r"^---\r?\n(.*?)\r?\n---\r?\n(.*)$", raw, re.DOTALL)
if m:
    fm = yaml.safe_load(m.group(1)) or {}
    body = m.group(2).lstrip("\n")

title = ""
for line in body.splitlines():
    s = line.strip()
    if s.startswith("# "):
        title = s[2:].strip()
        break

def as_list(v):
    if v is None:
        return []
    if isinstance(v, list):
        return [str(x) for x in v]
    return [str(v)]

out = {
    "title": title,
    "body": body,
    "target_repo": str(fm.get("target_repo", "")).strip(),
    "labels": as_list(fm.get("labels")),
    "initiative": str(fm.get("initiative", "")).strip(),
    "actor": str(fm.get("actor", "")).strip(),
    "dependencies": as_list(fm.get("dependencies")),
    "adrs": as_list(fm.get("adrs")),
}
print(json.dumps(out))
PY
}

manifest_has() {
  local rel="$1"
  jq -e --arg k "$rel" 'has($k)' "$MANIFEST" >/dev/null 2>&1
}

manifest_get() {
  local rel="$1"
  jq -r --arg k "$rel" '.[$k] // empty' "$MANIFEST"
}

manifest_set() {
  local rel="$1" url="$2"
  local tmp
  tmp="$(mktemp)"
  jq --arg k "$rel" --arg v "$url" '.[$k] = $v' "$MANIFEST" > "$tmp"
  mv "$tmp" "$MANIFEST"
}

# Look up a dependency issue URL by basename of the dependency path.
dep_lookup_url() {
  local dep="$1"
  local base
  base="$(basename "$dep")"
  jq -r --arg b "$base" '
    to_entries
    | map(select((.key | split("/") | last) == $b))
    | .[0].value // empty
  ' "$MANIFEST"
}

# Collected summary rows: "packet\turl\tblockers"
SUMMARY_ROWS=()
# Packets filed during THIS run; used to scope the dependency-linking pass so
# re-runs do not repost "Blocked by" comments on already-linked issues.
declare -A NEW_PACKETS=()

shopt -s globstar nullglob

echo "Scanning packets under: $PACKETS_DIR_ABS"
for packet in "$PACKETS_DIR_ABS"/**/*.md; do
  [[ -f "$packet" ]] || continue
  rel="${packet#"$REPO_ROOT/"}"

  if manifest_has "$rel"; then
    existing="$(manifest_get "$rel")"
    echo "skip  $rel -> already filed at $existing"
    continue
  fi

  packet_json="$(parse_packet "$packet")"
  title="$(jq -r '.title' <<<"$packet_json")"
  body_content="$(jq -r '.body' <<<"$packet_json")"
  target_repo="$(jq -r '.target_repo' <<<"$packet_json")"
  initiative="$(jq -r '.initiative' <<<"$packet_json")"
  actor="$(jq -r '.actor' <<<"$packet_json")"
  mapfile -t labels < <(jq -r '.labels[]?' <<<"$packet_json")
  mapfile -t adrs < <(jq -r '.adrs[]?' <<<"$packet_json")

  if [[ -z "$target_repo" ]]; then
    echo "::error::Packet $rel is missing target_repo"
    exit 1
  fi
  if [[ -z "$title" ]]; then
    echo "::error::Packet $rel has no h1 title"
    exit 1
  fi

  # Synthesize labels: frontmatter labels + initiative-<slug>
  all_labels=("${labels[@]}")
  if [[ -n "$initiative" ]]; then
    initiative_label="initiative-${initiative}"
    present=0
    for l in "${all_labels[@]}"; do
      if [[ "$l" == "$initiative_label" ]]; then present=1; break; fi
    done
    if [[ $present -eq 0 ]]; then
      all_labels+=("$initiative_label")
    fi
  fi

  adr_text="$(IFS=', '; echo "${adrs[*]:-}")"
  note_line="Packet: \`${rel}\`"
  if [[ -n "$adr_text" ]]; then
    note_line+=" · ADRs: ${adr_text}"
  fi
  if [[ -n "$initiative" ]]; then
    note_line+=" · Initiative: ${initiative}"
  fi

  body_file="$(mktemp)"
  {
    printf '> [!NOTE]\n'
    printf '> Filed from issue packet in [HoneyDrunk.Architecture](https://github.com/%s).\n' "$ARCHITECTURE_REPO"
    printf '> %s\n\n' "$note_line"
    printf '%s\n' "$body_content"
  } > "$body_file"

  label_args=()
  for l in "${all_labels[@]}"; do
    [[ -z "$l" ]] && continue
    # Ensure label exists on the target repo; auto-create with neutral defaults
    # if missing. `gh label create` exits non-zero when the label already exists
    # — that's the no-op path. Stderr is suppressed to keep logs clean on re-runs.
    gh label create "$l" --repo "$target_repo" --color "ededed" --description "Auto-created by file-packets" 2>/dev/null || true
    label_args+=("--label" "$l")
  done

  echo "file  $rel -> ${target_repo}"
  issue_url="$(gh issue create \
    --repo "$target_repo" \
    --title "$title" \
    --body-file "$body_file" \
    "${label_args[@]}")"
  rm -f "$body_file"

  if [[ -z "$issue_url" || ! "$issue_url" =~ ^https://github.com/ ]]; then
    echo "::error::Failed to create issue for $rel" >&2
    exit 1
  fi

  mirror_args=(--url "$issue_url" \
               --project-owner "$PROJECT_OWNER" \
               --project-number "$PROJECT_NUMBER" \
               --mapping-file "$MAPPING_FILE")
  if [[ -n "$actor" ]]; then
    mirror_args+=(--actor "$actor")
  fi
  "$MIRROR_SCRIPT" "${mirror_args[@]}"

  manifest_set "$rel" "$issue_url"
  NEW_PACKETS["$rel"]=1
  SUMMARY_ROWS+=("${rel}"$'\t'"${issue_url}"$'\t')
done

# Dependency-linking pass — only for packets filed during THIS run, so re-runs
# do not post duplicate "Blocked by" comments on issues we already linked.
if [[ $LINK_DEPS -eq 1 ]]; then
  echo "Running dependency-linking pass"
  for packet in "$PACKETS_DIR_ABS"/**/*.md; do
    [[ -f "$packet" ]] || continue
    rel="${packet#"$REPO_ROOT/"}"
    [[ -n "${NEW_PACKETS[$rel]:-}" ]] || continue
    packet_json="$(parse_packet "$packet")"
    mapfile -t deps < <(jq -r '.dependencies[]?' <<<"$packet_json")
    [[ ${#deps[@]} -eq 0 ]] && continue

    dependent_url="$(manifest_get "$rel")"
    if [[ -z "$dependent_url" ]]; then
      echo "::warning::Skipping dep-link for $rel: no manifest entry (not filed)"
      continue
    fi

    blockers=()
    for dep in "${deps[@]}"; do
      [[ -z "$dep" ]] && continue
      dep_url="$(dep_lookup_url "$dep")"
      if [[ -z "$dep_url" ]]; then
        echo "::warning::Dependency not found in manifest for $rel: $dep"
        continue
      fi
      blockers+=("$dep_url")
    done

    [[ ${#blockers[@]} -eq 0 ]] && continue

    body_file="$(mktemp)"
    {
      for b in "${blockers[@]}"; do
        printf 'Blocked by %s\n' "$b"
      done
    } > "$body_file"

    echo "link  $rel -> ${#blockers[@]} blocker(s)"
    gh issue comment "$dependent_url" --body-file "$body_file" >/dev/null
    rm -f "$body_file"

    # Update summary row if this packet was newly filed this run.
    for i in "${!SUMMARY_ROWS[@]}"; do
      row="${SUMMARY_ROWS[$i]}"
      row_rel="${row%%$'\t'*}"
      if [[ "$row_rel" == "$rel" ]]; then
        blockers_joined="$(IFS=', '; echo "${blockers[*]}")"
        rest="${row#*$'\t'}"
        row_url="${rest%%$'\t'*}"
        SUMMARY_ROWS[$i]="${rel}"$'\t'"${row_url}"$'\t'"${blockers_joined}"
        break
      fi
    done
  done
fi

# Summary
summary_out() {
  echo ""
  echo "## Packet filing summary"
  echo ""
  if [[ ${#SUMMARY_ROWS[@]} -eq 0 ]]; then
    echo "_No new packets filed._"
    return
  fi
  echo "| Packet | Issue | Blockers |"
  echo "|--------|-------|----------|"
  for row in "${SUMMARY_ROWS[@]}"; do
    IFS=$'\t' read -r p u b <<<"$row"
    echo "| ${p} | ${u} | ${b:-—} |"
  done
}

summary_out
if [[ -n "${GITHUB_STEP_SUMMARY:-}" ]]; then
  summary_out >> "$GITHUB_STEP_SUMMARY"
fi
