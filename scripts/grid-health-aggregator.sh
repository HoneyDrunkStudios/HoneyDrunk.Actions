#!/usr/bin/env bash
set -euo pipefail

CATALOG_PATH="${1:?usage: grid-health-aggregator.sh <catalog-path>}"
: "${GH_TOKEN:?GH_TOKEN must be set}"
: "${GRID_HEALTH_TITLE:=Grid Health}"
: "${ACTIONS_REPO:=HoneyDrunkStudios/HoneyDrunk.Actions}"
ORG="HoneyDrunkStudios"
NOW_EPOCH="$(date -u +%s)"
NOW_ISO="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

schema="$(jq -r '._meta.schema_version // "0.0"' "$CATALOG_PATH")"
major="${schema%%.*}"
minor="${schema#*.}"; minor="${minor%%.*}"
if [ "${major:-0}" -lt 1 ] || { [ "${major:-0}" -eq 1 ] && [ "${minor:-0}" -lt 1 ]; }; then
  cat >&2 <<EOF
ERROR: catalogs/grid-health.json _meta.schema_version is "$schema", aggregator requires ">=1.1".
tracked_workflows was introduced at schema 1.1 (packet 03 of the ADR-0012 rollout).
Verify catalogs/grid-health.json has been updated and merged before running this aggregator.
EOF
  exit 1
fi

staleness_seconds() {
  case "$1" in
    publish.yml) echo 0 ;;
    weekly-*.yml) echo $((8*24*60*60)) ;;
    nightly-*.yml) echo $((28*60*60)) ;;
    *) echo $((28*60*60)) ;;
  esac
}

status_emoji() {
  case "$1" in
    Pass) echo "✅ Pass" ;;
    Fail) echo "🔴 Fail" ;;
    Stale) echo "🟠 Stale" ;;
    Missing) echo "❓ Missing" ;;
    *) echo "$1" ;;
  esac
}


workdir="$(mktemp -d)"
trap 'rm -rf "$workdir"' EXIT
results="$workdir/results.jsonl"
: > "$results"

mapfile -t repos < <(jq -c '.nodes[] | {id,name,tracked_workflows:(.tracked_workflows // [])}' "$CATALOG_PATH")
for row in "${repos[@]}"; do
  name="$(jq -r '.name' <<<"$row")"
  name="${name//$'\r'/}"
  count="$(jq '.tracked_workflows | length' <<<"$row")"
  if [ "$count" -eq 0 ]; then
    continue
  fi
  mapfile -t workflows < <(jq -r '.tracked_workflows[]' <<<"$row")
  for workflow in "${workflows[@]}"; do
    workflow="${workflow//$'\r'/}"
    if [ "$workflow" = "pr-core.yml" ]; then
      continue
    fi
    repo="$ORG/$name"
    api="repos/$repo/actions/workflows/$workflow/runs?per_page=10"
    body="$workdir/response.json"
    response="$workdir/response.raw"
    gh_status=0
    gh_error="$workdir/response.err"
    gh api -i "$api" > "$response" 2>"$gh_error" || gh_status=$?
    status_code="$(awk 'BEGIN{code=0} /^HTTP\//{code=$2} END{print code}' "$response" | tr -d '\r')"
    if [ "$gh_status" -ne 0 ] && [ "$status_code" = "0" ]; then
      echo "ERROR: gh api failed before returning headers for $api (exit $gh_status)." >&2
      if [ -s "$gh_error" ]; then cat "$gh_error" >&2; fi
      exit 1
    fi
    awk 'BEGIN{body=0} /^\r?$/{body=1; next} body{print}' "$response" > "$body"
    classification="Missing"; url=""; created=""; conclusion=""
    if [ "$status_code" = "200" ]; then
      total="$(jq -r '.total_count // 0' "$body")"
      if [ "$total" != "0" ]; then
        latest="$(jq -c '.workflow_runs[0]' "$body")"
        conclusion="$(jq -r '.conclusion // ""' <<<"$latest")"
        created="$(jq -r '.created_at // ""' <<<"$latest")"
        url="$(jq -r '.html_url // ""' <<<"$latest")"
        if [[ "$conclusion" =~ ^(failure|cancelled|timed_out|action_required)$ ]]; then
          classification="Fail"
        elif [ "$workflow" = "publish.yml" ]; then
          [ "$conclusion" = "success" ] && classification="Pass" || classification="Fail"
        else
          window="$(staleness_seconds "$workflow")"
          created_epoch="$(date -u -d "$created" +%s 2>/dev/null || echo 0)"
          age=$((NOW_EPOCH-created_epoch))
          if [ "$conclusion" = "success" ] && [ "$age" -le "$window" ]; then
            classification="Pass"
          elif [ -z "$conclusion" ]; then
            recent_success="$(jq -c '[.workflow_runs[] | select(.conclusion == "success")][0] // empty' "$body")"
            if [ -n "$recent_success" ]; then
              success_created="$(jq -r '.created_at' <<<"$recent_success")"
              success_epoch="$(date -u -d "$success_created" +%s 2>/dev/null || echo 0)"
              success_age=$((NOW_EPOCH-success_epoch))
              if [ "$success_age" -le "$window" ]; then classification="Pass"; else classification="Stale"; fi
            else
              classification="Stale"
            fi
          else
            classification="Stale"
          fi
        fi
      fi
    elif [ "$status_code" = "404" ]; then
      classification="Missing"
    else
      echo "ERROR: gh api returned HTTP $status_code for $api" >&2
      exit 1
    fi
    jq -nc --arg repo "$name" --arg workflow "$workflow" --arg status "$classification" --arg url "$url" --arg created "$created" --arg conclusion "$conclusion" '{repo:$repo,workflow:$workflow,status:$status,url:$url,created_at:$created,conclusion:$conclusion}' >> "$results"
  done
done

workflows_json="$(jq -R -s 'split("\n")[:-1] | unique | sort' < <(jq -r '.workflow' "$results"))"
fail_count="$(jq 'select(.status=="Fail") | 1' "$results" | wc -l | tr -d ' ')"
stale_missing_count="$(jq 'select(.status=="Stale" or .status=="Missing") | 1' "$results" | wc -l | tr -d ' ')"
if [ "$fail_count" -gt 0 ]; then header="🔴 $fail_count failures"; elif [ "$stale_missing_count" -gt 0 ]; then header="🟠 $stale_missing_count stale or missing"; else header="✅ all green"; fi

org_repos="$workdir/org-repos.txt"
gh api "orgs/$ORG/repos?per_page=100" --paginate --jq '.[].name' | sort > "$org_repos"
catalog_repos="$workdir/catalog-repos.txt"
jq -r '.nodes[].name' "$CATALOG_PATH" | sort > "$catalog_repos"
drift="$(comm -23 "$org_repos" "$catalog_repos" || true)"
if [ -n "$drift" ]; then header="$header · ⚠️ Catalog drift"; fi

report="$workdir/report.md"
{
  echo "# $header"
  echo
  echo "Last updated: $NOW_ISO"
  echo
  echo "Legend: ✅ Pass · 🔴 Fail · 🟠 Stale · ❓ Missing · blank = workflow not tracked for that repo."
  echo
  printf '| Repo |'
  jq -r '.[]' <<<"$workflows_json" | while read -r w; do printf ' `%s` |' "$w"; done
  echo
  printf '|---|'
  jq -r '.[]' <<<"$workflows_json" | while read -r _; do printf '%s' '---|'; done
  echo
  jq -r '.nodes[] | select((.tracked_workflows // []) | length > 0) | .name' "$CATALOG_PATH" | while read -r repo; do
    printf '| `%s` |' "$repo"
    jq -r '.[]' <<<"$workflows_json" | while read -r workflow; do
      cell="$(jq -r --arg repo "$repo" --arg workflow "$workflow" 'select(.repo==$repo and .workflow==$workflow) | @base64' "$results" | head -n1)"
      if [ -z "$cell" ]; then printf ' |'; else
        obj="$(printf '%s' "$cell" | base64 -d)"
        st="$(jq -r '.status' <<<"$obj")"; url="$(jq -r '.url' <<<"$obj")"
        label="$(status_emoji "$st")"
        if [ -n "$url" ] && [ "$url" != "null" ]; then printf ' [%s](%s) |' "$label" "$url"; else printf ' %s |' "$label"; fi
      fi
    done
    echo
  done
  echo
  echo "## Per-repo failure issues"
  echo
  echo "Per-repo issues are opened for Fail/Missing and closed when the pair returns to Pass. Stale results remain central-only."
  echo
  echo "## Catalog drift"
  echo
  if [ -n "$drift" ]; then
    echo "$drift" | sed 's/^/- ⚠️ Missing from `catalogs\/grid-health.json`: `/' | sed 's/$/`/'
  else
    echo "None."
  fi
} > "$report"

find_issue() {
  local repo="$1" title="$2" state="${3:-all}"
  gh issue list --repo "$repo" --state "$state" --limit 1000 --search "in:title \"$title\"" --json number,title,state \
    | jq -r --arg title "$title" '.[] | select(.title == $title) | .number' \
    | head -n1
}

main_issue="$(find_issue "$ACTIONS_REPO" "$GRID_HEALTH_TITLE")"
if [ -z "$main_issue" ]; then
  main_issue_url="$(gh issue create --repo "$ACTIONS_REPO" --title "$GRID_HEALTH_TITLE" --body-file "$report")"
  main_issue="${main_issue_url##*/}"
else
  gh issue reopen "$main_issue" --repo "$ACTIONS_REPO" >/dev/null 2>&1 || true
  gh issue edit "$main_issue" --repo "$ACTIONS_REPO" --body-file "$report"
fi

jq -c 'select(.status=="Fail" or .status=="Missing")' "$results" | while read -r row; do
  repo_name="$(jq -r '.repo' <<<"$row")"; workflow="$(jq -r '.workflow' <<<"$row")"; status="$(jq -r '.status' <<<"$row")"; url="$(jq -r '.url' <<<"$row")"; title="[grid-health] $workflow unhealthy"
  body="$workdir/failure.md"
  printf 'Grid health classified `%s` in `%s` as **%s**.\n\nLatest run: %s\n\nUpdated: %s\n' "$workflow" "$repo_name" "$status" "${url:-none}" "$NOW_ISO" > "$body"
  repo="$ORG/$repo_name"
  issue="$(find_issue "$repo" "$title")"
  if [ -z "$issue" ]; then gh issue create --repo "$repo" --title "$title" --body-file "$body" >/dev/null; else gh issue reopen "$issue" --repo "$repo" >/dev/null 2>&1 || true; gh issue edit "$issue" --repo "$repo" --body-file "$body" >/dev/null; fi
done

jq -c 'select(.status=="Pass")' "$results" | while read -r row; do
  repo_name="$(jq -r '.repo' <<<"$row")"; workflow="$(jq -r '.workflow' <<<"$row")"; url="$(jq -r '.url' <<<"$row")"; title="[grid-health] $workflow unhealthy"; repo="$ORG/$repo_name"
  issue="$(find_issue "$repo" "$title" open)"
  if [ -n "$issue" ]; then gh issue close "$issue" --repo "$repo" --comment "Resolved by run $url at $NOW_ISO." >/dev/null; fi
done

if [ -n "${GITHUB_STEP_SUMMARY:-}" ]; then
  cat "$report" >> "$GITHUB_STEP_SUMMARY"
else
  cat "$report"
fi
