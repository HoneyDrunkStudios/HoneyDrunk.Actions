#!/usr/bin/env python3
"""Redaction + embed formatting for job-discord-notify.yml (ADR-0084 D8 / D9).

This is the single source of truth for:
  - the secret-shape pattern set (PATTERNS),
  - the fail-closed redaction scan (scan / redact),
  - Discord embed assembly with severity decoration, truncation, and the
    6000-char total-embed budget enforced across fields (format_embed).

It lives as a real script (mirroring the .github/scripts/inventory-*.py helpers)
so the logic is unit-tested (test_discord_notify.py) and reused without the
drift that an inline-YAML heredoc invites. The reusable workflow checks out
HoneyDrunk.Actions (checkout-actions-repo) and calls the subcommands below.

Subcommands (all read inputs from the environment / stdin, never argv, so no
secret value is ever placed on a command line — Invariant 8):
  precheck  Scan TITLE+BODY+LINK+METADATA for secret shapes. Exit 1 on any hit
            with a ::error:: annotation. Used BEFORE formatting on raw inputs.
  format    Validate METADATA is a JSON object, build the embed JSON, scan the
            FINAL assembled payload (closes JSON-escape decode bypass), and
            print the payload to stdout. Exit 1 on a redaction hit or bad input.
  redact    Read stdin, print it with every secret shape replaced by [REDACTED]
            (truncated to 1000 chars). Used to sanitize a non-2xx response body.

The regex set is defense-in-depth against ACCIDENTAL plaintext leaks (the same
discipline as VaultTelemetry), not an adversarial guarantee — a caller-side
base64/gzip-encoded secret is out of scope.
"""
import json
import os
import re
import sys

# name -> regex. The ONLY place secret patterns are defined.
PATTERNS = {
    "GitHub classic token (ghp_/gho_/ghu_/ghs_/ghr_)": r"gh[pousr]_[A-Za-z0-9]{36,}",
    "GitHub fine-grained PAT (github_pat_)": r"github_pat_[A-Za-z0-9_]{40,}",
    "JWT": r"eyJ[A-Za-z0-9_-]+\.eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+",
    "Discord webhook URL": r"https://discord(?:app)?\.com/api/webhooks/[0-9]+/[A-Za-z0-9_-]+",
    "AWS access key id": r"AKIA[0-9A-Z]{16}",
    "Azure connection-string key fragment": r"(?:AccountKey|SharedAccessKey)=",
    "PEM private key header": r"-----BEGIN [A-Z ]+PRIVATE KEY-----",
    # High-entropy run (32+) adjacent to a credential keyword.
    "keyword-adjacent secret": r"(?i)(?:token|secret|password|api[_-]?key)[\"'\s:=]+[A-Za-z0-9+/_\-]{32,}",
    "credit-card-shaped number": r"\b(?:\d[ -]*?){13,16}\b",
    "US SSN-shaped number": r"\b\d{3}-\d{2}-\d{4}\b",
}

# Discord embed limits.
TITLE_MAX = 200          # headroom under the 256 hard cap
BODY_MAX = 4000          # headroom under the 4096 hard cap
TOTAL_MAX = 5900         # headroom under the 6000 total-embed hard cap

COLORS = {"info": 0x3FB950, "medium": 0xD29922, "high": 0xFB8500, "critical": 0xDA3633}
PREFIXES = {"info": "", "medium": "⚠️ ", "high": "\U0001f525 ", "critical": "\U0001f6a8 "}
FOOTER = "HoneyDrunk Grid · operator-alerts (ADR-0084)"


def scan(text):
    """Return the names of every pattern that matches `text`."""
    return [name for name, pat in PATTERNS.items() if re.search(pat, text)]


def redact(text):
    """Replace every matched secret shape with [REDACTED]."""
    for pat in PATTERNS.values():
        text = re.sub(pat, "[REDACTED]", text)
    return text


def _embed_chars(embed):
    """Total character count Discord counts against the 6000 budget."""
    n = (len(embed.get("title", ""))
         + len(embed.get("description", ""))
         + len(embed.get("footer", {}).get("text", "")))
    for f in embed.get("fields", []):
        n += len(f["name"]) + len(f["value"])
    return n


def format_embed(severity, title, body="", link="", metadata=""):
    """Build the Discord webhook payload dict. Raises ValueError on bad input."""
    if severity not in COLORS:
        raise ValueError(f"unknown severity '{severity}'")

    # Severity decoration: prepend the emoji unless the caller already did.
    prefix = PREFIXES[severity]
    if prefix and not title.startswith(prefix.strip()):
        title = prefix + title

    if len(title) > TITLE_MAX:
        title = title[:TITLE_MAX - 1] + "…"
    if len(body) > BODY_MAX:
        body = body[:BODY_MAX] + " ... (truncated)"

    embed = {"title": title, "color": COLORS[severity]}
    if body:
        embed["description"] = body
    if link:
        embed["url"] = link

    field_count = 0
    if metadata:
        md = json.loads(metadata)  # caller validates; raises on malformed
        if not isinstance(md, dict):
            raise ValueError("metadata must be a JSON object")
        if md:
            embed["fields"] = [
                {"name": str(k)[:256], "value": str(v)[:1024], "inline": True}
                for k, v in list(md.items())[:25]
            ]
            field_count = len(md)

    embed["footer"] = {"text": FOOTER}

    # Enforce the total budget. Trim the description first (most expendable),
    # then drop trailing metadata fields, recording how many were omitted so a
    # delivered-minus-fields alert beats a 400 that drops the whole thing.
    over = _embed_chars(embed) - TOTAL_MAX
    if over > 0 and embed.get("description"):
        marker = " ... (truncated)"
        keep = max(0, len(embed["description"]) - over - len(marker))
        embed["description"] = embed["description"][:keep] + marker
    if embed.get("fields"):
        while embed["fields"] and _embed_chars(embed) > TOTAL_MAX:
            embed["fields"].pop()
        dropped = field_count - len(embed["fields"])
        if dropped > 0:
            note = {"name": "…",
                    "value": f"({dropped} field(s) omitted to fit Discord's size limit)",
                    "inline": False}
            while embed["fields"] and _embed_chars(embed) + len(note["name"]) + len(note["value"]) > TOTAL_MAX:
                embed["fields"].pop()
            embed["fields"].append(note)

    return {"embeds": [embed]}


def _err(msg):
    print(f"::error::{msg}", file=sys.stderr)


def cmd_precheck():
    payload = "\n".join(os.environ.get(k, "") for k in ("TITLE", "BODY", "LINK", "METADATA"))
    hits = scan(payload)
    if hits:
        for name in hits:
            _err(f"Redaction pre-check matched '{name}'. Discord payloads must "
                 f"carry no secret values, PII, or credentials (ADR-0084 D8 / "
                 f"Invariant 8). Post aborted; fix the emitter so it sends "
                 f"metadata, not secrets.")
        return 1
    print("Redaction pre-check passed.")
    return 0


def cmd_format():
    metadata = os.environ.get("METADATA", "")
    if metadata:
        try:
            if not isinstance(json.loads(metadata), dict):
                _err("metadata input must be a JSON object (e.g. {\"key\":\"value\"}). "
                     "Arrays, strings, numbers, and malformed JSON are rejected.")
                return 1
        except json.JSONDecodeError:
            _err("metadata input must be a JSON object (e.g. {\"key\":\"value\"}). "
                 "Arrays, strings, numbers, and malformed JSON are rejected.")
            return 1
    try:
        payload = format_embed(
            os.environ["SEVERITY"], os.environ.get("TITLE", ""),
            os.environ.get("BODY", ""), os.environ.get("LINK", ""), metadata)
    except ValueError as exc:
        _err(f"could not format Discord payload: {exc}")
        return 1
    serialized = json.dumps(payload)
    # Final-payload scan: METADATA is JSON, so a "\\u0067hp_..." value passes the
    # raw precheck and only becomes a literal token after json.loads here. Scan
    # the assembled ASCII payload to close that decode bypass.
    hits = scan(serialized)
    if hits:
        for name in hits:
            _err(f"Final-payload redaction matched '{name}' after formatting "
                 f"(likely a JSON-escaped secret in metadata). Post aborted "
                 f"(ADR-0084 D8 / Invariant 8).")
        return 1
    print(serialized)
    return 0


def cmd_redact():
    print(redact(sys.stdin.read())[:1000])
    return 0


def main(argv):
    cmds = {"precheck": cmd_precheck, "format": cmd_format, "redact": cmd_redact}
    if len(argv) != 2 or argv[1] not in cmds:
        sys.exit(f"usage: discord_notify.py {{{'|'.join(cmds)}}}")
    return cmds[argv[1]]()


if __name__ == "__main__":
    sys.exit(main(sys.argv))
