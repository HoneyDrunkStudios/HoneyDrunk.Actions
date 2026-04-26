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

# Retry a `gh` invocation up to 3 times when stderr contains a rate-limit
# signature. Backoff is exponential, capped at 60s. Non-rate-limit failures
# return immediately with the original exit code. Successful calls return
# stdout unchanged. Keep stderr behavior identical to a plain `gh` call.
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
has_frontmatter = False
m = re.match(r"^---\r?\n(.*?)\r?\n---\r?\n(.*)$", raw, re.DOTALL)
if m:
    loaded = yaml.safe_load(m.group(1))
    if loaded is None:
        fm = {}
    elif isinstance(loaded, dict):
        fm = loaded
    else:
        print(
            f"Frontmatter in {path} is not a YAML mapping (got {type(loaded).__name__})",
            file=sys.stderr,
        )
        sys.exit(1)
    body = m.group(2).lstrip("\n")
    has_frontmatter = True

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
    "has_frontmatter": has_frontmatter,
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

# Look up a dependency issue URL by basename of the dependency path. Accepts
# either the full packet filename ("01-foo.md") or its bare slug ("foo") by
# normalizing both sides: strip a leading "NN-" prefix and trailing ".md".
dep_lookup_url() {
  local dep="$1"
  local base
  base="$(basename "$dep")"
  jq -r --arg b "$base" '
    def norm: sub("^[0-9]+-"; "") | sub("[.]md$"; "");
    to_entries
    | map(.key |= (split("/") | last))
    | map(select(.key == $b or (.key | norm) == ($b | norm)))
    | .[0].value // empty
  ' "$MANIFEST"
}

# Collected summary rows: "packet\turl\tblockers"
SUMMARY_ROWS=()
# Packets filed during THIS run. The dependency-linking pass walks every
# packet in the manifest (idempotent across runs) but only newly-filed
# packets get their blocker list reflected back into SUMMARY_ROWS.
declare -A NEW_PACKETS=()

# Repo-existence cache — avoids one `gh repo view` per packet for the same
# target repo. Values: "1" = exists, "0" = confirmed 404 / no access.
# Transient failures (rate limit, network, 5xx) are NOT cached and propagate
# so the run fails fast rather than silently skipping every subsequent packet.
declare -A REPO_EXISTS=()

repo_exists() {
  local repo="$1"
  if [[ -n "${REPO_EXISTS[$repo]:-}" ]]; then
    if [[ "${REPO_EXISTS[$repo]}" == "1" ]]; then
      return 0
    fi
    return 1
  fi
  local stderr_file
  stderr_file="$(mktemp)"
  if gh repo view "$repo" --json name >/dev/null 2>"$stderr_file"; then
    rm -f "$stderr_file"
    REPO_EXISTS[$repo]=1
    return 0
  fi
  local stderr_content
  stderr_content="$(<"$stderr_file")"
  rm -f "$stderr_file"
  # Only cache negative when gh clearly reports the repo doesn't exist or is
  # inaccessible. Everything else (rate limits, network errors, 5xx) is
  # surfaced so the caller can decide whether to abort.
  if [[ "$stderr_content" == *"Could not resolve"* ]] \
    || [[ "$stderr_content" == *"HTTP 404"* ]] \
    || [[ "$stderr_content" == *"Not Found"* ]] \
    || [[ "$stderr_content" == *"could not find any repository"* ]]; then
    REPO_EXISTS[$repo]=0
    return 1
  fi
  # Plain stderr, not ::error::, because $repo (packet frontmatter) and
  # $stderr_content (gh output) are untrusted and could contain workflow-command
  # syntax that would otherwise inject into the runner log stream.
  echo "gh repo view failed for $repo with non-404 error: $stderr_content" >&2
  exit 1
}

# Label cache — avoids one `gh label view` call per (packet, label). First
# encounter of a target repo lists its labels once; subsequent checks are
# in-memory. `LABELS_LISTED[repo]=1` marks a repo as fetched.
# `LABELS_KNOWN[repo|name]=1` marks a label as present on that repo.
declare -A LABELS_LISTED=()
declare -A LABELS_KNOWN=()

ensure_label() {
  local repo="$1" name="$2"
  if [[ -z "${LABELS_LISTED[$repo]:-}" ]]; then
    local existing
    while IFS= read -r existing; do
      [[ -z "$existing" ]] && continue
      LABELS_KNOWN["$repo|$existing"]=1
    done < <(gh label list --repo "$repo" --limit 200 --json name -q '.[].name')
    LABELS_LISTED["$repo"]=1
  fi
  if [[ -z "${LABELS_KNOWN[$repo|$name]:-}" ]]; then
    gh label create "$name" --repo "$repo" --color "ededed" --description "Auto-created by file-packets"
    LABELS_KNOWN["$repo|$name"]=1
  fi
}

shopt -s globstar nullglob

# Resolve The Hive project metadata (project ID + field list) once up front,
# then export it as a JSON blob so each mirror invocation in the loop reuses
# the cached structure instead of re-querying. The mirror script reads
# HIVE_PROJECT_METADATA_JSON if set and falls back to its own per-call
# resolution otherwise.
echo "Resolving project metadata for ${PROJECT_OWNER}/${PROJECT_NUMBER}"
PROJECT_VIEW_JSON="$(gh_retry project view "$PROJECT_NUMBER" --owner "$PROJECT_OWNER" --format json)"
PROJECT_FIELDS_JSON="$(gh_retry project field-list "$PROJECT_NUMBER" --owner "$PROJECT_OWNER" --format json)"
HIVE_PROJECT_METADATA_JSON="$(jq -n \
  --argjson project "$PROJECT_VIEW_JSON" \
  --argjson fields "$PROJECT_FIELDS_JSON" \
  '{project: $project, fields: $fields}')"
export HIVE_PROJECT_METADATA_JSON

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
  has_frontmatter="$(jq -r '.has_frontmatter' <<<"$packet_json")"

  # Files without YAML frontmatter are coordination docs (dispatch-plan.md,
  # READMEs, notes), not packets. Skip quietly so non-packet markdown can live
  # alongside packets in the same directory.
  if [[ "$has_frontmatter" != "true" ]]; then
    echo "skip  $rel -> no frontmatter (not a packet)"
    continue
  fi

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

  # Target repo must exist and be accessible. A packet that names a future /
  # not-yet-created repo is a legitimate state (standup packets land before
  # their repos do). Skip with a plain log line instead of erroring the whole
  # run. Plain echo (not ::warning::) matches the existing skip-log style and
  # avoids interpolating untrusted values into a workflow command.
  if ! repo_exists "$target_repo"; then
    echo "skip  $rel -> target repo $target_repo does not exist (or no access); will retry on future runs"
    continue
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
    ensure_label "$target_repo" "$l"
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

# Dependency-linking pass — runs over every packet in the manifest, not just
# packets filed during the current run, so a partial-failure run can recover
# its missing blocking edges on a re-run. Idempotency is enforced per-(dependent,
# blocker): before posting a `Blocked by <URL>` line for a given pair, we
# verify it's not already present in any prior comment on the dependent issue.
# Cache exists for the lifetime of one run only.
declare -A LINKED_BLOCKERS_CACHE=()

# List the dep URLs already mentioned as `Blocked by <url>` lines on a given
# dependent issue. Caches per dependent_url to avoid re-paginating comments
# when the same issue has multiple dependencies.
load_existing_blockers() {
  local dependent_url="$1"
  if [[ -n "${LINKED_BLOCKERS_CACHE[$dependent_url]:-}" ]]; then
    return 0
  fi
  if [[ ! "$dependent_url" =~ ^https://github.com/([^/]+)/([^/]+)/issues/([0-9]+)$ ]]; then
    LINKED_BLOCKERS_CACHE[$dependent_url]=$'\n'
    return 0
  fi
  local owner="${BASH_REMATCH[1]}"
  local repo="${BASH_REMATCH[2]}"
  local num="${BASH_REMATCH[3]}"
  local bodies
  bodies="$(gh_retry api "repos/${owner}/${repo}/issues/${num}/comments" --paginate --jq '.[].body')" || bodies=""
  # Stash with a leading and trailing newline so grep -F line-anchored matches
  # are robust regardless of the comment body's own newline endings.
  LINKED_BLOCKERS_CACHE[$dependent_url]=$'\n'"${bodies}"$'\n'
}

already_linked() {
  local dependent_url="$1"
  local dep_url="$2"
  load_existing_blockers "$dependent_url"
  local cached="${LINKED_BLOCKERS_CACHE[$dependent_url]}"
  [[ "$cached" == *$'\n'"Blocked by ${dep_url}"$'\n'* ]]
}

if [[ $LINK_DEPS -eq 1 ]]; then
  echo "Running dependency-linking pass (idempotent across runs)"
  for packet in "$PACKETS_DIR_ABS"/**/*.md; do
    [[ -f "$packet" ]] || continue
    rel="${packet#"$REPO_ROOT/"}"

    dependent_url="$(manifest_get "$rel")"
    if [[ -z "$dependent_url" ]]; then
      # Packet not yet filed (no manifest entry yet, or coordination doc
      # without frontmatter). Skip silently — earlier loop logged the reason.
      continue
    fi

    packet_json="$(parse_packet "$packet")"
    mapfile -t deps < <(jq -r '.dependencies[]?' <<<"$packet_json")
    [[ ${#deps[@]} -eq 0 ]] && continue

    new_blockers=()
    skipped_blockers=()
    for dep in "${deps[@]}"; do
      [[ -z "$dep" ]] && continue
      dep_url="$(dep_lookup_url "$dep")"
      if [[ -z "$dep_url" ]]; then
        echo "::warning::Dependency not found in manifest for $rel: $dep"
        continue
      fi
      if already_linked "$dependent_url" "$dep_url"; then
        skipped_blockers+=("$dep_url")
        continue
      fi
      new_blockers+=("$dep_url")
    done

    if [[ ${#new_blockers[@]} -eq 0 ]]; then
      if [[ ${#skipped_blockers[@]} -gt 0 ]]; then
        echo "skip  $rel -> all ${#skipped_blockers[@]} blocker(s) already linked"
      fi
      continue
    fi

    body_file="$(mktemp)"
    {
      for b in "${new_blockers[@]}"; do
        printf 'Blocked by %s\n' "$b"
      done
    } > "$body_file"

    echo "link  $rel -> ${#new_blockers[@]} new blocker(s) (${#skipped_blockers[@]} already linked)"
    gh_retry issue comment "$dependent_url" --body-file "$body_file" >/dev/null
    rm -f "$body_file"

    # Reflect newly-posted blockers in the in-process cache so any later
    # packet that depends on this dependent_url for its own check sees them.
    LINKED_BLOCKERS_CACHE[$dependent_url]+=""
    for b in "${new_blockers[@]}"; do
      LINKED_BLOCKERS_CACHE[$dependent_url]+="Blocked by ${b}"$'\n'
    done

    # Update summary row only if this packet was newly filed this run.
    if [[ -n "${NEW_PACKETS[$rel]:-}" ]]; then
      for i in "${!SUMMARY_ROWS[@]}"; do
        row="${SUMMARY_ROWS[$i]}"
        row_rel="${row%%$'\t'*}"
        if [[ "$row_rel" == "$rel" ]]; then
          blockers_joined="$(IFS=', '; echo "${new_blockers[*]}")"
          rest="${row#*$'\t'}"
          row_url="${rest%%$'\t'*}"
          SUMMARY_ROWS[$i]="${rel}"$'\t'"${row_url}"$'\t'"${blockers_joined}"
          break
        fi
      done
    fi
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
