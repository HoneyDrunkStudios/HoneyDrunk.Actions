#!/usr/bin/env python3
"""Evaluate sensitive-inventory.md Rotates:yes rows (ADR-0083 D5 / packet 05).

Parses the inventory table, filters `Rotates: yes`, parses `Current Expiration`
as strict ISO 8601 (YYYY-MM-DD), computes days-to-expiry against today's UTC
date (ADR-0063 N2), and emits a JSON array of escalations to stdout:

    [{"name", "expiration", "days_to_expiry", "escalation_tier"}]

escalation_tier in {ok, urgent_T30, imminent_T7, expired_T0}.

Strict ISO only — a non-date Current Expiration cell (e.g. "TBD ...") fails fast.
"""
import datetime
import json
import re
import sys

ISO = re.compile(r"^\d{4}-\d{2}-\d{2}$")
COLUMNS = [
    "Name", "Kind", "Provider", "Where Stored", "Bound To", "Rotates",
    "Expiration Cadence", "Current Expiration", "Rotation Procedure",
    "Use Cases", "Blast Radius if Missed", "Owner", "Notes",
]


def split_row(line):
    return [c.strip() for c in line.strip().strip("|").split("|")]


def parse_rows(path):
    with open(path, encoding="utf-8") as fh:
        lines = fh.readlines()
    header_idx = None
    for i, line in enumerate(lines):
        if line.lstrip().startswith("|"):
            cells = split_row(line)
            if cells and cells[0] == "Name":
                header_idx = i
                break
    if header_idx is None:
        sys.exit(f"PARSE ERROR: no inventory table header in {path}")
    rows = []
    for line in lines[header_idx + 2:]:
        if not line.lstrip().startswith("|"):
            break
        cells = split_row(line)
        if len(cells) != len(COLUMNS):
            # Never silently drop a row — a malformed `Rotates: yes` credential
            # would otherwise vanish from escalation. Warn loudly to stderr; the
            # schema-check step is the hard gate, this is the belt-and-suspenders.
            sys.stderr.write(
                f"WARNING: skipping malformed inventory row "
                f"({len(cells)} cells, expected {len(COLUMNS)}): {line.strip()[:120]}\n")
            continue
        rows.append(dict(zip(COLUMNS, cells)))
    return rows


def clean(cell):
    # Strip Markdown emphasis/backticks/links so "`SONAR_TOKEN`" -> "SONAR_TOKEN".
    cell = cell.strip().strip("`").strip("*").strip()
    return cell


def main(path):
    today = datetime.datetime.now(datetime.timezone.utc).date()
    escalations = []
    for row in parse_rows(path):
        if clean(row["Rotates"]).lower() != "yes":
            continue
        name = clean(row["Name"])
        raw_exp = clean(row["Current Expiration"])
        if not ISO.match(raw_exp):
            sys.exit(
                f"PARSE ERROR: row '{name}' has Rotates: yes but a non-ISO-8601 "
                f"Current Expiration ('{row['Current Expiration']}'). "
                "Every Rotates:yes row must carry a strict YYYY-MM-DD date "
                "(provisional dates are allowed, placeholder strings are not)."
            )
        try:
            exp = datetime.date.fromisoformat(raw_exp)
        except ValueError:
            sys.exit(f"PARSE ERROR: row '{name}' Current Expiration '{raw_exp}' is not a real date.")
        days = (exp - today).days
        if days <= 0:
            # T+0 is the expiration day itself (and anything past it) — treat the
            # day-of as expired so the SEV-2 fires on the day, not the day after.
            tier = "expired_T0"
        elif days <= 7:
            tier = "imminent_T7"
        elif days <= 30:
            tier = "urgent_T30"
        else:
            tier = "ok"
        escalations.append({
            "name": name,
            "expiration": raw_exp,
            "days_to_expiry": days,
            "escalation_tier": tier,
        })
    print(json.dumps(escalations, indent=2))


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("usage: inventory-evaluate.py <path-to-sensitive-inventory.md>")
    main(sys.argv[1])
