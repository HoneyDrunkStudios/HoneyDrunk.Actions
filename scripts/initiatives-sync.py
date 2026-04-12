#!/usr/bin/env python3
"""Gather initiative state from GitHub issues and catalogs.

Data-gathering layer for the initiatives-sync agent. Reads
filed-packets.json, queries GitHub for issue states, detects release
drift, and writes a JSON report. Does NOT modify any initiative
markdown files — that's the agent's job.
"""

import argparse
import json
import os
import re
import subprocess
import sys
from collections import defaultdict
from datetime import datetime, timezone


def parse_args():
    parser = argparse.ArgumentParser(
        description="Gather initiative state into a sync report for the initiatives-sync agent"
    )
    parser.add_argument(
        "--arch-root",
        required=True,
        help="Path to Architecture repo root",
    )
    parser.add_argument(
        "--report",
        default="",
        help="Path to write JSON report (default: generated/initiatives-sync-report.json)",
    )
    return parser.parse_args()


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def load_filed_packets(arch_root):
    """Group filed-packets.json entries by initiative slug (directory name)."""
    path = os.path.join(arch_root, "generated", "issue-packets", "filed-packets.json")
    with open(path, encoding="utf-8") as f:
        packets = json.load(f)

    initiatives = defaultdict(list)
    for packet_path, issue_url in packets.items():
        parts = packet_path.replace("\\", "/").split("/")
        try:
            active_idx = parts.index("active")
            slug = parts[active_idx + 1]
        except (ValueError, IndexError):
            continue
        initiatives[slug].append(
            {"packet": packet_path, "issue_url": issue_url, "filename": parts[-1]}
        )

    return dict(initiatives)


def load_grid_health(arch_root):
    path = os.path.join(arch_root, "catalogs", "grid-health.json")
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return data.get("nodes", [])


# ---------------------------------------------------------------------------
# GitHub queries
# ---------------------------------------------------------------------------

def query_issue_state(issue_url):
    """Query a single issue via gh CLI. Returns state dict."""
    try:
        result = subprocess.run(
            ["gh", "issue", "view", issue_url, "--json", "state,title,closedAt,stateReason"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode == 0:
            data = json.loads(result.stdout)
            return {
                "state": data.get("state", "UNKNOWN"),
                "title": data.get("title", ""),
                "closed_at": data.get("closedAt"),
                "state_reason": data.get("stateReason", ""),
            }
        return {"state": "ERROR", "title": "", "error": result.stderr.strip()}
    except Exception as exc:
        return {"state": "ERROR", "title": "", "error": str(exc)}


def query_all_issue_states(initiative_packets):
    """Query states for every issue across all initiatives."""
    states = {}
    seen = set()
    total = sum(len(pkts) for pkts in initiative_packets.values())
    done = 0

    for slug, packets in initiative_packets.items():
        for entry in packets:
            url = entry["issue_url"]
            if url in seen:
                continue
            seen.add(url)
            done += 1
            print(f"  [{done}/{total}] Querying {url} ...", file=sys.stderr)
            states[url] = query_issue_state(url)

    return states


# ---------------------------------------------------------------------------
# Progress computation
# ---------------------------------------------------------------------------

def compute_progress(slug, packets, issue_states):
    total = len(packets)
    closed_issues = []
    open_issues = []
    error_issues = []

    for entry in packets:
        url = entry["issue_url"]
        info = issue_states.get(url, {"state": "UNKNOWN"})

        if info["state"] == "CLOSED":
            closed_issues.append({"url": url, "title": info.get("title", "")})
        elif info["state"] == "OPEN":
            open_issues.append({"url": url, "title": info.get("title", "")})
        else:
            error_issues.append({"url": url, "error": info.get("error", "unknown")})

    pct = round(len(closed_issues) / total * 100) if total > 0 else 0

    return {
        "slug": slug,
        "total": total,
        "closed": len(closed_issues),
        "open": len(open_issues),
        "errors": len(error_issues),
        "percent": pct,
        "complete": len(closed_issues) == total and total > 0,
        "open_issues": open_issues,
        "closed_issues": closed_issues,
        "error_details": error_issues,
        "packets": [
            {
                "filename": entry["filename"],
                "issue_url": entry["issue_url"],
                "state": issue_states.get(entry["issue_url"], {}).get("state", "UNKNOWN"),
                "title": issue_states.get(entry["issue_url"], {}).get("title", ""),
                "closed_at": issue_states.get(entry["issue_url"], {}).get("closed_at"),
            }
            for entry in packets
        ],
    }


# ---------------------------------------------------------------------------
# Release drift detection
# ---------------------------------------------------------------------------

def detect_release_drift(arch_root, grid_nodes):
    """Compare grid-health.json versions against releases.md entries."""
    releases_path = os.path.join(arch_root, "initiatives", "releases.md")
    with open(releases_path, encoding="utf-8") as f:
        releases_content = f.read()

    drift = []
    for node in grid_nodes:
        name = node.get("name", "")
        version = node.get("version", "0.0.0")
        signal = node.get("signal", "")

        if version in ("0.0.0", "N/A") or signal == "Seed":
            continue

        short_name = name.removeprefix("HoneyDrunk.")
        full_pattern = f"### {name} {version}"
        short_pattern = f"### {short_name} {version}"
        if full_pattern not in releases_content and short_pattern not in releases_content:
            drift.append({
                "node": name,
                "version": version,
                "signal": signal,
                "last_release": node.get("last_release"),
                "message": f"{name} {version} not found in releases.md",
            })

    return drift


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------

def generate_report(progress_results, release_drift):
    now = datetime.now(timezone.utc).isoformat()

    total_initiatives = len(progress_results)
    completed = sum(1 for p in progress_results.values() if p["complete"])
    total_issues = sum(p["total"] for p in progress_results.values())
    total_closed = sum(p["closed"] for p in progress_results.values())

    return {
        "generated_at": now,
        "summary": {
            "initiatives_tracked": total_initiatives,
            "initiatives_complete": completed,
            "total_issues": total_issues,
            "total_closed": total_closed,
            "overall_percent": round(total_closed / total_issues * 100) if total_issues else 0,
        },
        "initiatives": {
            slug: {
                "total": p["total"],
                "closed": p["closed"],
                "open": p["open"],
                "percent": p["percent"],
                "complete": p["complete"],
                "open_issues": p["open_issues"],
                "closed_issues": p["closed_issues"],
                "packets": p["packets"],
                "error_details": p["error_details"],
            }
            for slug, p in progress_results.items()
        },
        "release_drift": release_drift,
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    args = parse_args()
    arch_root = os.path.abspath(args.arch_root)
    report_path = args.report or os.path.join(
        arch_root, "generated", "initiatives-sync-report.json"
    )

    print("Loading filed packets...", file=sys.stderr)
    initiative_packets = load_filed_packets(arch_root)
    initiative_packets.pop("standalone", None)
    print(f"  Found {len(initiative_packets)} initiative(s)", file=sys.stderr)

    print("Querying GitHub issue states...", file=sys.stderr)
    issue_states = query_all_issue_states(initiative_packets)

    print("Computing progress...", file=sys.stderr)
    progress_results = {}
    for slug, packets in initiative_packets.items():
        progress_results[slug] = compute_progress(slug, packets, issue_states)
        p = progress_results[slug]
        print(
            f"  {slug}: {p['closed']}/{p['total']} ({p['percent']}%)",
            file=sys.stderr,
        )

    print("Checking release drift...", file=sys.stderr)
    grid_nodes = load_grid_health(arch_root)
    release_drift = detect_release_drift(arch_root, grid_nodes)
    for d in release_drift:
        print(f"  DRIFT: {d['message']}", file=sys.stderr)

    report = generate_report(progress_results, release_drift)

    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
    print(f"Report written to {report_path}", file=sys.stderr)

    json.dump(report["summary"], sys.stdout, indent=2)
    print()

    return 0


if __name__ == "__main__":
    sys.exit(main())
