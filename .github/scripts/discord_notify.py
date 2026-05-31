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

# Patterns are split into two classes because they have different false-positive
# profiles against URLs:
#
#   CREDENTIAL_PATTERNS — token/key/webhook shapes. Safe to scan EVERYWHERE,
#     including `link` (a credential in a URL is exactly what we must block).
#   PII_PATTERNS — generic credit-card / SSN digit-run heuristics. These match
#     any 13-16 digit run, which a legitimate URL path can contain (e.g. a
#     GitHub Actions run id in `.../actions/runs/<id>`). Scanning a URL with
#     these would fail-closed on clean alert links, so PII heuristics apply ONLY
#     to human-text surfaces (title / body / metadata), never to `link`.
CREDENTIAL_PATTERNS = {
    "GitHub classic token (ghp_/gho_/ghu_/ghs_/ghr_)": r"gh[pousr]_[A-Za-z0-9]{36,}",
    "GitHub fine-grained PAT (github_pat_)": r"github_pat_[A-Za-z0-9_]{40,}",
    "JWT": r"eyJ[A-Za-z0-9_-]+\.eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+",
    "Discord webhook URL": r"https://discord(?:app)?\.com/api/webhooks/[0-9]+/[A-Za-z0-9_-]+",
    "AWS access key id": r"AKIA[0-9A-Z]{16}",
    "Azure connection-string key fragment": r"(?:AccountKey|SharedAccessKey)=",
    "PEM private key header": r"-----BEGIN (?:[A-Z0-9 ]+ )?PRIVATE KEY-----",
    # High-entropy run (32+) adjacent to a credential keyword.
    "keyword-adjacent secret": r"(?i)(?:token|secret|password|api[_-]?key)[\"'\s:=]+[A-Za-z0-9+/_\-]{32,}",
}
PII_PATTERNS = {
    "credit-card-shaped number": r"\b(?:\d[ -]*?){13,16}\b",
    "US SSN-shaped number": r"\b\d{3}-\d{2}-\d{4}\b",
}
# Full set — used by redact() on response bodies (not URLs) and kept as the
# canonical "everything" view.
PATTERNS = {**CREDENTIAL_PATTERNS, **PII_PATTERNS}

# Discord embed limits.
TITLE_MAX = 200          # headroom under the 256 hard cap
BODY_MAX = 4000          # headroom under the 4096 hard cap
TOTAL_MAX = 5900         # headroom under the 6000 total-embed hard cap
FIELD_MAX = 25           # Discord's hard cap on fields per embed

COLORS = {"info": 0x3FB950, "medium": 0xD29922, "high": 0xFB8500, "critical": 0xDA3633}
PREFIXES = {"info": "", "medium": "⚠️ ", "high": "\U0001f525 ", "critical": "\U0001f6a8 "}
FOOTER = "HoneyDrunk Grid · operator-alerts (ADR-0084)"


def scan(text, include_pii=True):
    """Return the names of every pattern that matches `text`.

    include_pii=False scans only CREDENTIAL_PATTERNS — use it for URL-shaped
    inputs (`link`) where the generic card/SSN digit-run heuristics would
    false-positive on legitimate numeric path segments (e.g. CI run ids).
    """
    pats = CREDENTIAL_PATTERNS if not include_pii else PATTERNS
    return [name for name, pat in pats.items() if re.search(pat, text)]


def redact(text):
    """Replace every matched secret shape with [REDACTED] (full pattern set)."""
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
            field_count = len(md)
            # Build ALL fields first; the budgeting loop below drops the excess
            # (by Discord's 25-field cap and the char budget) and reserves a slot
            # for the omitted-fields note. Capping at [:25] here would hide the
            # true count and let an appended note push the payload to 26 fields.
            # Discord rejects fields with an empty name or value, so normalize
            # empties to a single "-" placeholder rather than 400 the whole post.
            embed["fields"] = [
                {"name": (str(k)[:256] or "-"), "value": (str(v)[:1024] or "-"), "inline": True}
                for k, v in md.items()
            ]

    embed["footer"] = {"text": FOOTER}

    # Trim the description first (it is the most expendable long text) to fit the
    # total character budget.
    over = _embed_chars(embed) - TOTAL_MAX
    if over > 0 and embed.get("description"):
        marker = " ... (truncated)"
        keep = max(0, len(embed["description"]) - over - len(marker))
        embed["description"] = embed["description"][:keep] + marker

    # Drop trailing metadata fields until BOTH limits hold: Discord's 25-field
    # cap AND the 6000-char budget — counting the omitted-fields note (one slot +
    # its chars) whenever any field has been dropped. This guarantees the final
    # field list (real fields + note) never exceeds 25 and never busts the budget,
    # so a delivered-minus-fields alert beats a 400 that drops the whole thing.
    if embed.get("fields"):
        def _note_chars():
            return len("…") + len(f"({field_count} field(s) omitted to fit Discord's limits)")

        def _over_limit():
            need_note = len(embed["fields"]) < field_count
            slots = len(embed["fields"]) + (1 if need_note else 0)
            chars = _embed_chars(embed) + (_note_chars() if need_note else 0)
            return slots > FIELD_MAX or chars > TOTAL_MAX

        while embed["fields"] and _over_limit():
            embed["fields"].pop()

        dropped = field_count - len(embed["fields"])
        if dropped > 0:
            embed["fields"].append({
                "name": "…",
                "value": f"({dropped} field(s) omitted to fit Discord's limits)",
                "inline": False,
            })

    return {"embeds": [embed]}


def _err(msg):
    print(f"::error::{msg}", file=sys.stderr)


def cmd_precheck():
    # Human-text surfaces get the full set (credentials + PII heuristics).
    text = "\n".join(os.environ.get(k, "") for k in ("TITLE", "BODY", "METADATA"))
    # The link is URL-shaped: scan it for credential/webhook/token shapes only,
    # so a legitimate URL path containing a long digit run (e.g. a CI run id)
    # does not fail-closed as a card/SSN false positive.
    link = os.environ.get("LINK", "")
    hits = scan(text, include_pii=True) + scan(link, include_pii=False)
    if hits:
        for name in dict.fromkeys(hits):  # de-dupe, preserve order
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
    # Final-payload scan closes the decode bypass: METADATA is JSON, so a
    # "\\u0067hp_..." value passes the raw precheck and only becomes a literal
    # token after json.loads during formatting. Scan the DECODED human-text
    # surfaces (title / description / field names+values) with the full set
    # (credentials + PII). The embed `url` (the link) is deliberately excluded —
    # it is not JSON-decoded (no bypass risk) and was already credential-scanned
    # in precheck, and scanning it with PII heuristics would false-positive on a
    # legitimate URL digit run (e.g. a CI run id).
    embed = payload["embeds"][0]
    decoded_surfaces = "\n".join(filter(None, [
        embed.get("title", ""),
        embed.get("description", ""),
        *[f["name"] for f in embed.get("fields", [])],
        *[f["value"] for f in embed.get("fields", [])],
    ]))
    hits = scan(decoded_surfaces, include_pii=True)
    if hits:
        for name in dict.fromkeys(hits):
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
