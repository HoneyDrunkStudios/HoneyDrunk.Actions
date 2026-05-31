#!/usr/bin/env python3
"""Unit tests for discord_notify.py (ADR-0084 D8 redaction + D9 formatting).

Run: python3 -m unittest discover -s .github/scripts -p 'test_*.py'

NOTE: secret-shaped fixtures are assembled by concatenation (e.g. "ghp_" + "A"*36)
so the literal does not appear contiguously in this source file — otherwise the
actions-ci.yml "no inline secrets" lint grep would flag the test itself.
"""
import json
import unittest

import discord_notify as dn

# Secret fixtures built so no contiguous secret-shaped literal exists in source.
GHP = "ghp_" + "A" * 36
GHPAT = "github_pat_" + "B" * 42
AWS = "AKIA" + "C" * 16
DISCORD_URL = "https://discord.com/api/webhooks/" + "123456789/" + "abcDEF_ghi-jkl"
JWT = "eyJ" + "abc" + "." + "eyJ" + "def" + "." + "sig123"  # eyJ.eyJ.sig three-part
PEM = "-----BEGIN RSA PRIVATE KEY-----"


class TestScan(unittest.TestCase):
    def test_clean_payloads_pass(self):
        for clean in [
            "❌ HoneyDrunk.Actions / pr-core: a1b2c3d — run link",
            "\U0001f511 SONAR_TOKEN expires in 30 days",
            "\U0001f4e6 HoneyDrunk.Kernel 1.4.0 published to nuget.org",
            "✔️ HoneyDrunk.Actions#173 merged",
        ]:
            self.assertEqual(dn.scan(clean), [], f"clean payload flagged: {clean!r}")

    def test_secret_shapes_blocked(self):
        for label, fixture in [
            ("ghp", GHP), ("github_pat", GHPAT), ("aws", AWS),
            ("discord", DISCORD_URL), ("jwt", JWT), ("pem", PEM),
            ("ssn", "123-45-6789"),
            ("azure", "AccountKey=abc123=="),
        ]:
            self.assertTrue(dn.scan(fixture), f"{label} fixture not detected: {fixture!r}")

    def test_redact_uses_same_set(self):
        leaked = f"err {AWS} and {GHP}"
        out = dn.redact(leaked)
        self.assertNotIn(AWS, out)
        self.assertNotIn(GHP, out)
        self.assertIn("[REDACTED]", out)


class TestFormat(unittest.TestCase):
    def test_severity_color_and_prefix(self):
        p = dn.format_embed("critical", "disk full")
        e = p["embeds"][0]
        self.assertEqual(e["color"], dn.COLORS["critical"])
        self.assertTrue(e["title"].startswith("\U0001f6a8"))

    def test_info_has_no_prefix(self):
        e = dn.format_embed("info", "hello")["embeds"][0]
        self.assertEqual(e["title"], "hello")

    def test_unknown_severity_raises(self):
        with self.assertRaises(ValueError):
            dn.format_embed("bogus", "x")

    def test_metadata_object_becomes_fields(self):
        e = dn.format_embed("info", "t", metadata='{"k":"v"}')["embeds"][0]
        self.assertEqual(e["fields"][0]["name"], "k")

    def test_metadata_non_object_raises(self):
        with self.assertRaises(ValueError):
            dn.format_embed("info", "t", metadata='["a","b"]')

    def test_title_truncated(self):
        e = dn.format_embed("info", "x" * 500)["embeds"][0]
        self.assertLessEqual(len(e["title"]), dn.TITLE_MAX)

    def test_total_budget_trims_description(self):
        e = dn.format_embed("info", "t", body="d" * 6000)["embeds"][0]
        self.assertLessEqual(dn._embed_chars(e), 6000)

    def test_total_budget_drops_fields(self):
        md = json.dumps({f"k{i}": "v" * 250 for i in range(25)})
        e = dn.format_embed("info", "t", metadata=md)["embeds"][0]
        self.assertLessEqual(dn._embed_chars(e), 6000)
        # An omitted-fields note is present when fields were dropped.
        self.assertTrue(any("omitted" in f["value"] for f in e["fields"]))

    def test_final_payload_scan_catches_json_escaped_secret(self):
        # A GitHub token JSON-escaped in metadata passes the RAW precheck...
        escaped = "ghp_" + "\\u0041" * 36
        raw_meta = '{"x":"' + escaped + '"}'
        self.assertEqual(dn.scan(raw_meta), [], "raw escaped token should evade raw scan")
        # ...but the assembled payload (json.dumps emits literal ASCII) is caught.
        payload = json.dumps(dn.format_embed("info", "t", metadata=raw_meta))
        self.assertTrue(dn.scan(payload), "final-payload scan should catch decoded token")


if __name__ == "__main__":
    unittest.main()
