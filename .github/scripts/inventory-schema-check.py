#!/usr/bin/env python3
"""Schema-check for sensitive-inventory.md (ADR-0083 D5 / packet 05).

Asserts the file contains exactly one Markdown table whose header is the D2
column set in the expected order. Exits non-zero with a clear message on drift —
the downstream parser depends on stable headers.
"""
import sys

EXPECTED_COLUMNS = [
    "Name", "Kind", "Provider", "Where Stored", "Bound To", "Rotates",
    "Expiration Cadence", "Current Expiration", "Rotation Procedure",
    "Use Cases", "Blast Radius if Missed", "Owner", "Notes",
]


def split_row(line):
    # "| a | b |" -> ["a", "b"]
    cells = [c.strip() for c in line.strip().strip("|").split("|")]
    return cells


def find_header(lines):
    for i, line in enumerate(lines):
        if line.lstrip().startswith("|") and "Name" in line and "Rotates" in line:
            cells = split_row(line)
            if cells and cells[0] == "Name":
                return i, cells
    return None, None


def main(path):
    with open(path, encoding="utf-8") as fh:
        lines = fh.readlines()

    idx, header = find_header(lines)
    if header is None:
        sys.exit(f"SCHEMA ERROR: no inventory table header found in {path}")

    if header != EXPECTED_COLUMNS:
        sys.exit(
            "SCHEMA ERROR: inventory table columns drifted.\n"
            f"  expected: {EXPECTED_COLUMNS}\n"
            f"  found:    {header}\n"
            "  The external-credentials-check workflow parses by column order; "
            "fix the table or update the parser deliberately."
        )

    # Separator row must follow the header.
    if idx + 1 >= len(lines) or "---" not in lines[idx + 1]:
        sys.exit("SCHEMA ERROR: missing Markdown table separator row after header.")

    # Count data rows for a sanity signal.
    data_rows = 0
    for line in lines[idx + 2:]:
        if not line.lstrip().startswith("|"):
            break
        data_rows += 1
    if data_rows == 0:
        sys.exit("SCHEMA ERROR: inventory table has no data rows.")

    print(f"Schema OK: {len(EXPECTED_COLUMNS)} columns, {data_rows} data rows.")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("usage: inventory-schema-check.py <path-to-sensitive-inventory.md>")
    main(sys.argv[1])
