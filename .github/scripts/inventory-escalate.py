#!/usr/bin/env python3
"""Apply per-tier escalations for the credential drift check (ADR-0083 D5 / packet 05).

Tiers:
  urgent_T30  -> on the standing rotation issue: add `urgent` label + a comment
                 (idempotent: only if `urgent` not already present). Open the
                 issue if it does not exist.
  imminent_T7 -> add `imminent` label + a comment (idempotent). Open if missing.
  expired_T0  -> create generated/incidents/{date}-{credential}-expired.md in the
                 HoneyDrunk.Architecture checkout via a PR (never direct to main,
                 ADR-0054), and comment the incident path on the standing issue.
                 Idempotent: skips if today's incident file already exists.

Reads escalations.json from inventory-evaluate.py. Uses the `gh` CLI directly
(invariant 38). Never logs or stores a secret value (invariant 8).
"""
import argparse
import datetime
import json
import os
import re
import subprocess
import sys

REPO = "HoneyDrunkStudios/HoneyDrunk.Architecture"
LABEL = "external-credential-rotation"
WORKFLOW_URL = "https://github.com/HoneyDrunkStudios/HoneyDrunk.Actions/blob/main/.github/workflows/external-credentials-check.yml"


def gh(args, **kw):
    return subprocess.run(["gh", *args], check=True, text=True,
                          capture_output=True, **kw).stdout


def gh_quiet(args, **kw):
    return subprocess.run(["gh", *args], text=True, capture_output=True, **kw)


def find_issue(name):
    """Return (number, labels) of the open standing issue for `name`, or (None, [])."""
    out = gh(["issue", "list", "--repo", REPO, "--label", LABEL, "--state", "open",
              "--json", "number,title,labels", "--limit", "200"])
    for issue in json.loads(out):
        # Title shape: "[Rotate] {name} — expires {date}"
        if issue["title"].startswith(f"[Rotate] {name} "):
            labels = [lb["name"] for lb in issue["labels"]]
            return issue["number"], labels
    return None, []


def open_issue(name, expiration):
    body = (
        f"Standing rotation issue per ADR-0083 D3 (auto-opened by external-credentials-check.yml).\n\n"
        f"**Credential:** `{name}`\n"
        f"**Current expiration:** {expiration}\n"
        f"**Inventory row:** `infrastructure/reference/sensitive-inventory.md`\n\n"
        f"When rotating: follow the credential's walkthrough under `infrastructure/walkthroughs/`. "
        f"When done, close this issue and immediately open the next one with the new expiration date.\n\n"
        f"---\nPer ADR-0083 D7 invariant 103 — every `Rotates: yes` inventory row carries an open standing issue."
    )
    out = gh(["issue", "create", "--repo", REPO, "--title",
              f"[Rotate] {name} — expires {expiration}", "--label", LABEL, "--body", body])
    url = out.strip()
    print(f"  opened standing issue for {name}: {url}")
    # Parse the number straight from the create URL (.../issues/N) rather than
    # re-listing — `gh issue list` is eventually consistent and may not yet
    # return the just-created issue, which would drop the escalation.
    m = re.search(r"/issues/(\d+)\s*$", url)
    return int(m.group(1)) if m else None


def escalate_label_tier(esc, tier_label, message):
    name = esc["name"]
    number, labels = find_issue(name)
    if number is None:
        number = open_issue(name, esc["expiration"])
        labels = []
    if number is None:
        print(f"  WARN: could not resolve a standing issue for {name}; skipping.")
        return
    if tier_label in labels:
        print(f"  {name}: already at `{tier_label}` — no duplicate comment.")
        return
    gh(["issue", "edit", str(number), "--repo", REPO, "--add-label", tier_label])
    gh(["issue", "comment", str(number), "--repo", REPO, "--body", message])
    print(f"  {name}: added `{tier_label}` + comment on #{number}.")


def escalate_expired(esc, architecture_checkout):
    name = esc["name"]
    today = datetime.datetime.now(datetime.timezone.utc).date().isoformat()
    safe = name.replace("/", "-").replace(" ", "-")
    rel_path = f"generated/incidents/{today}-{safe}-expired.md"
    branch = f"incident/{today}-{safe}-expired"

    # Idempotency: skip if an incident PR for this branch already exists in ANY
    # state (open, merged, or closed) — a same-day PR merged earlier must not be
    # re-created — or if the remote branch already exists.
    existing = gh_quiet(["pr", "list", "--repo", REPO, "--head", branch,
                         "--state", "all", "--json", "number"])
    if existing.returncode == 0 and json.loads(existing.stdout or "[]"):
        print(f"  {name}: incident PR for {branch} already exists (any state) — skipping.")
        return
    # `git ls-remote` handles slashes in the branch name natively (the incident
    # branch is `incident/<date>-...`); the branches REST API would need the name
    # URL-encoded. Run it from the Architecture checkout, which has the remote.
    ls = subprocess.run(["git", "-C", architecture_checkout, "ls-remote",
                         "--heads", "origin", branch], text=True, capture_output=True)
    if ls.returncode == 0 and ls.stdout.strip():
        print(f"  {name}: incident branch {branch} already exists on remote — skipping.")
        return

    incident = (
        f"---\n"
        f"severity: SEV-2\n"
        f"date: {today}\n"
        f"credential: {name}\n"
        f"status: open\n"
        f"source: external-credentials-check.yml\n"
        f"adr: ADR-0083\n"
        f"---\n\n"
        f"# SEV-2: `{name}` expired ({today})\n\n"
        f"The sensitive-inventory `Current Expiration` for `{name}` is in the past "
        f"(was {esc['expiration']}; {abs(esc['days_to_expiry'])} day(s) overdue).\n\n"
        f"## Impact\n\n"
        f"See the `Blast Radius if Missed` cell for `{name}` in "
        f"`infrastructure/reference/sensitive-inventory.md`.\n\n"
        f"## Action\n\n"
        f"1. Rotate `{name}` per its walkthrough under `infrastructure/walkthroughs/`.\n"
        f"2. Update the inventory row's `Current Expiration`.\n"
        f"3. Close the standing rotation issue and open the next one.\n"
        f"4. Set this incident's `status: resolved` and merge.\n"
    )

    cwd = architecture_checkout
    inc_dir = os.path.join(cwd, "generated", "incidents")
    os.makedirs(inc_dir, exist_ok=True)
    with open(os.path.join(cwd, rel_path), "w", encoding="utf-8") as fh:
        fh.write(incident)

    def git(args):
        subprocess.run(["git", "-C", cwd, *args], check=True, text=True, capture_output=True)

    git(["config", "user.name", "honeydrunk-credentials-check[bot]"])
    git(["config", "user.email", "noreply@honeydrunkstudios.com"])
    git(["checkout", "-b", branch])
    git(["add", rel_path])
    git(["commit", "-m", f"SEV-2: {name} expired ({today}) — external-credentials-check"])
    git(["push", "origin", branch])

    pr_body = (
        f"Automated SEV-2 incident record: `{name}` is past its inventory "
        f"`Current Expiration` ({esc['expiration']}). Rotate it per its walkthrough and "
        f"update the inventory row.\n\n"
        f"Authorship: agent-claude-code\n"
        f"Out-of-band reason: external-credentials-check.yml drift detection; "
        f"T+0 expiration of {name}; see incident record at {rel_path}\n"
    )
    gh(["pr", "create", "--repo", REPO, "--base", "main", "--head", branch,
        "--title", f"SEV-2: {name} expired ({today})", "--body", pr_body])
    print(f"  {name}: opened SEV-2 incident PR ({rel_path}).")

    number, _ = find_issue(name)
    if number is not None:
        gh(["issue", "comment", str(number), "--repo", REPO, "--body",
            f"⛔ **T+0 — `{name}` has expired.** SEV-2 incident filed at `{rel_path}` "
            f"(see the incident PR). Rotate now per the walkthrough."])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tier", required=True,
                    choices=["urgent_T30", "imminent_T7", "expired_T0"])
    ap.add_argument("--escalations", required=True)
    ap.add_argument("--architecture-checkout", default="architecture")
    args = ap.parse_args()

    with open(args.escalations, encoding="utf-8") as fh:
        escalations = json.load(fh)

    matching = [e for e in escalations if e["escalation_tier"] == args.tier]
    if not matching:
        print(f"No rows at tier {args.tier}.")
        return

    for esc in matching:
        if args.tier == "urgent_T30":
            escalate_label_tier(
                esc, "urgent",
                f"⚠️ **T-30** — `{esc['name']}` expires {esc['expiration']} "
                f"({esc['days_to_expiry']} days). Rotate per the walkthrough. "
                f"(auto: {WORKFLOW_URL})")
        elif args.tier == "imminent_T7":
            escalate_label_tier(
                esc, "imminent",
                f"🚨 **T-7** — `{esc['name']}` expires {esc['expiration']} "
                f"({esc['days_to_expiry']} days). Rotate now. (auto: {WORKFLOW_URL})")
        elif args.tier == "expired_T0":
            escalate_expired(esc, args.architecture_checkout)


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as exc:
        sys.stderr.write(f"gh/git command failed: {exc}\n{exc.stderr}\n")
        sys.exit(1)
