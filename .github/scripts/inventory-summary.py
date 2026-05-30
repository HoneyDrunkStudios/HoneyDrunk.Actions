#!/usr/bin/env python3
"""Write an operator-friendly summary of the credential drift check to
$GITHUB_STEP_SUMMARY (ADR-0083 D5 / packet 05).

Also emits a one-line success heartbeat — the load-bearing mitigation for the
"watcher who watches the watcher" hole: if this workflow stops running (e.g.
GH_ISSUE_TOKEN silently expires), the absence of the heartbeat is the signal.
"""
import datetime
import json
import sys

# The summary uses emoji; force UTF-8 so it never dies on a non-UTF-8 locale.
try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    pass

TIER_ICON = {
    "ok": "✅", "urgent_T30": "⚠️", "imminent_T7": "🚨", "expired_T0": "⛔",
}


def main(path):
    today = datetime.datetime.now(datetime.timezone.utc).date().isoformat()
    print(f"## External Credentials Drift Check — {today} (UTC)\n")

    # The summary runs with `if: always()`, so a failed evaluate step can leave
    # escalations.json missing or malformed. Distinguish that from a clean
    # zero-row result — collapsing both into "no rows" would mask an upstream
    # failure (and suppress the heartbeat's real signal).
    try:
        with open(path, encoding="utf-8") as fh:
            escalations = json.load(fh)
    except (OSError, json.JSONDecodeError) as exc:
        print(f"⚠️ Could not read `{path}` ({exc.__class__.__name__}). An earlier "
              f"step likely failed — **no heartbeat this run**; investigate the run log.")
        return

    print(f"💚 Heartbeat: workflow ran. Evaluated {len(escalations)} `Rotates: yes` row(s).\n")

    if not escalations:
        print("_No `Rotates: yes` rows found in the inventory._")
        return

    print("| Credential | Expiration | Days to expiry | Tier |")
    print("|---|---|---|---|")
    for esc in sorted(escalations, key=lambda e: e["days_to_expiry"]):
        icon = TIER_ICON.get(esc["escalation_tier"], "")
        print(f"| `{esc['name']}` | {esc['expiration']} | {esc['days_to_expiry']} | "
              f"{icon} {esc['escalation_tier']} |")

    fired = [e for e in escalations if e["escalation_tier"] != "ok"]
    if fired:
        print(f"\n**{len(fired)} escalation(s) fired this run.**")
    else:
        print("\n_All credentials within bounds._")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("usage: inventory-summary.py <escalations.json>")
    main(sys.argv[1])
