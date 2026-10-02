"""Exercise the actual inline metadata validator without network access."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import textwrap
import unittest

ROOT = Path(__file__).resolve().parents[1]


def validator_source():
    source = (ROOT / '.github/workflows/pr-core.yml').read_text()
    section = source.split('  pr-metadata-check:', 1)[1].split('  # Job 9:', 1)[0]
    return textwrap.dedent(section.split("python3 <<'PY'\n", 1)[1].rsplit('          PY', 1)[0])


class MetadataTests(unittest.TestCase):
    def run_validator(self, body, authorship='agent-codex'):
        with tempfile.TemporaryDirectory() as directory:
            stub = Path(directory) / 'gh'
            stub.write_text('#!/bin/sh\nexit 0\n')
            stub.chmod(0o755)
            env = dict(os.environ, PR_BODY=body, AUTHORSHIP=authorship,
                       REPOSITORY='example/test', PR_NUMBER='1',
                       PATH=directory + os.pathsep + os.environ['PATH'])
            return subprocess.run([sys.executable, '-c', validator_source()],
                                  env=env, text=True, capture_output=True)

    def test_direct_request_needs_no_packet(self):
        result = self.run_validator('Request: Rename the planning repository and update its current references.')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('Direct request context present', result.stdout)

    def test_approved_scope_section(self):
        self.assertEqual(self.run_validator('## Approved scope\n- Archive the retired filing workflow.\n').returncode, 0)

    def test_placeholder_does_not_pass(self):
        for placeholder in ['', 'N/A', 'TODO', 'N/A (describe the direct request or approved scope; no work item required)']:
            with self.subTest(placeholder=placeholder):
                self.assertEqual(self.run_validator('Request: ' + placeholder).returncode, 1)

    def test_legacy_metadata_compatible(self):
        for body in ['Work Item: https://example.test/historical-packet', 'Out-of-band reason: Directly requested maintenance.']:
            self.assertEqual(self.run_validator(body).returncode, 0)

    def test_conflicting_legacy_fields_still_fail(self):
        self.assertEqual(self.run_validator('Work Item: https://example.test/packet\nOut-of-band reason: Other scope.').returncode, 1)
        self.assertEqual(self.run_validator('Request: Review selected scope.\nWork Item: https://example.test/packet\nOut-of-band reason: Other scope.').returncode, 1)

    def test_human_behavior_unchanged(self):
        self.assertEqual(self.run_validator('', 'human').returncode, 0)

    def test_agent_prompt_keeps_request_and_retires_packet_enforcement(self):
        source = (ROOT / '.github/workflows/agent-run.yml').read_text()
        section = source.split('      - name: Resolve prompt', 1)[1].split('      - name: Run agent', 1)[0]
        script = textwrap.dedent(section.split('        run: |\n', 1)[1])
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'output'
            env = dict(os.environ, AGENT='review', PROMPT='Review the selected change only.',
                       LEGACY_WORK_ITEM_PATH='generated/work-items/old.md', GITHUB_OUTPUT=str(output))
            result = subprocess.run(['bash', '-c', script], env=env, text=True, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn('work-item-path is retired', result.stdout)
            self.assertIn('Review the selected change only.', output.read_text())
            self.assertNotIn('Work Item:', output.read_text())
            self.assertNotIn('gh pr edit', source)


if __name__ == '__main__':
    unittest.main()
