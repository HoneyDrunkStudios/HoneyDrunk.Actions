"""Exercise real completion verifier and scanner-end wrapper without credentials."""

from contextlib import redirect_stdout
from datetime import datetime, timezone
import io
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = yaml.safe_load((ROOT / '.github/workflows/job-sonarcloud.yml').read_text())
STEPS = {step['name']: step for step in WORKFLOW['jobs']['sonarcloud']['steps']}
VERIFY = STEPS['Verify completed analysis after scanner failure']
SCRIPT = VERIFY['run'].split("python3 <<'PYTHON'\n", 1)[1].rsplit('\nPYTHON', 1)[0]
END = STEPS['End SonarQube Cloud analysis']


def stamp(seconds):
    return datetime.fromtimestamp(seconds, timezone.utc).isoformat()


class CompletionTests(unittest.TestCase):
    def verify(self, metadata=None, task=None, mtime=110, error=None, missing=False,
               host='https://sonarcloud.io', raw=None, payload=None):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            report = root / 'report-task.txt'
            output = root / 'output'
            data = {'projectKey': 'fixture', 'serverUrl': 'https://sonarcloud.io',
                    'ceTaskId': 'task-123', 'ceTaskUrl': 'https://sonarcloud.io/api/ce/task?id=task-123'}
            data.update(metadata or {})
            if not missing:
                report.write_text(raw if raw is not None else '\n'.join(f'{k}={v}' for k, v in data.items()))
                os.utime(report, (mtime, mtime))
            evidence = {'id': 'task-123', 'componentKey': 'fixture', 'status': 'SUCCESS',
                        'analysisId': 'analysis-123', 'submittedAt': stamp(105), 'executedAt': stamp(115)}
            evidence.update(task or {})
            response = io.BytesIO(payload if payload is not None else json.dumps({'task': evidence}).encode())
            env = {'SONAR_TOKEN': 'fixture-not-a-token', 'SONAR_HOST_URL': host,
                   'SONAR_PROJECT_KEY': 'fixture', 'SONAR_REPORT_PATH': str(report),
                   'SCANNER_STARTED_AT': '100', 'SCANNER_FINISHED_AT': '120',
                   'GITHUB_OUTPUT': str(output)}
            namespace = {}
            with patch.dict(os.environ, env, clear=True), \
                    patch('urllib.request.OpenerDirector.open', return_value=response, side_effect=error) as request, \
                    redirect_stdout(io.StringIO()):
                exec(compile(SCRIPT, 'completion-verifier', 'exec'), namespace)
            self.requests = request.call_count
            if request.called:
                self.assertEqual(request.call_args.args[0].full_url,
                                 'https://sonarcloud.io/api/ce/task?id=task-123')
                self.assertEqual(request.call_args.kwargs['timeout'], 10)
            self.assertIsNone(namespace['NoRedirect']().redirect_request(None, None, 302, '', {}, 'https://evil.test'))
            return output.read_text() == 'analysis-completed=true\n'

    def test_completed_analysis_survives_failed_awaited_gate(self):
        self.assertTrue(self.verify())
        self.assertEqual(self.requests, 1)
        self.assertIn("steps.scanner-end.outcome == 'failure'", VERIFY['if'])

    def test_missing_or_stale_metadata_never_queries_api(self):
        for arguments in ({'missing': True}, {'mtime': 99}, {'mtime': 121}):
            with self.subTest(arguments=arguments):
                self.assertFalse(self.verify(**arguments))
                self.assertEqual(self.requests, 0)

    def test_wrong_project_or_task_or_missing_analysis_rejected(self):
        for task in ({'componentKey': 'other'}, {'id': 'other'}, {'analysisId': ''},
                     {'analysisId': None}, {'analysisId': '../spoof'}):
            with self.subTest(task=task):
                self.assertFalse(self.verify(task=task))

    def test_failed_pending_cancelled_and_timeout_do_not_complete(self):
        for status in ('FAILED', 'CANCELED', 'PENDING', 'IN_PROGRESS', '', None):
            with self.subTest(status=status):
                self.assertFalse(self.verify(task={'status': status}))
        self.assertFalse(self.verify(error=TimeoutError('fixture timeout')))
        self.assertEqual(self.requests, 1)  # No second CE wait after scanner timeout.

    def test_prior_or_later_task_does_not_complete(self):
        for task in ({'submittedAt': stamp(99)}, {'executedAt': stamp(121)},
                     {'submittedAt': stamp(119), 'executedAt': stamp(118)},
                     {'submittedAt': 'bad'}, {'submittedAt': '2026-01-01T00:00:00'}):
            with self.subTest(task=task):
                self.assertFalse(self.verify(task=task))

    def test_spoofed_host_and_metadata_urls_never_receive_token(self):
        for arguments in ({'host': 'https://evil.test'},
                          {'metadata': {'serverUrl': 'https://evil.test'}},
                          {'metadata': {'ceTaskUrl': 'https://evil.test/api/ce/task?id=task-123'}},
                          {'metadata': {'ceTaskUrl': 'https://sonarcloud.io@evil.test/api/ce/task?id=task-123'}},
                          {'metadata': {'ceTaskId': '../evil'}},
                          {'metadata': {'projectKey': 'other'}}):
            with self.subTest(arguments=arguments):
                self.assertFalse(self.verify(**arguments))
                self.assertEqual(self.requests, 0)

    def test_malformed_and_duplicate_metadata_rejected(self):
        for raw in ('', 'not a property', 'ceTaskId=one\nceTaskId=two', 'x=' + 'x' * 16384):
            self.assertFalse(self.verify(raw=raw))
            self.assertEqual(self.requests, 0)

    def test_malformed_server_evidence_never_completes(self):
        for payload in (b'invalid', b'null', b'{}', b'{"task":[]}', b'{"task":null}'):
            with self.subTest(payload=payload):
                self.assertFalse(self.verify(payload=payload))

    def test_end_wrapper_keeps_failure_and_erases_build_metadata(self):
        for exit_code in (0, 1, 124):
            with self.subTest(exit_code=exit_code), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                report = root / 'report-task.txt'
                report.write_text('stale build metadata')
                scanner = root / '.sonar/scanner/dotnet-sonarscanner'
                scanner.parent.mkdir(parents=True)
                scanner.write_text('#!/bin/bash\n[[ ! -e "$SONAR_REPORT_PATH" ]] || exit 99\nexit ' + str(exit_code))
                scanner.chmod(0o755)
                output = root / 'output'
                env = {**os.environ, 'GITHUB_WORKSPACE': str(root), 'SONAR_REPORT_PATH': str(report),
                       'GITHUB_OUTPUT': str(output), 'SONAR_TOKEN': 'fixture-not-a-token'}
                result = subprocess.run(['bash', '-e', '-c', END['run']], env=env, capture_output=True)
                self.assertEqual(result.returncode, exit_code)
                self.assertFalse(report.exists())
                self.assertIn('started-at=', output.read_text())
                self.assertIn('finished-at=', output.read_text())

    def test_wiring_preserves_failed_scanner_and_limits_diagnostics(self):
        scanner = WORKFLOW['jobs']['sonarcloud']
        nested = WORKFLOW['jobs']['failure-findings']
        self.assertNotIn('continue-on-error', scanner)
        self.assertNotIn('continue-on-error', END)
        self.assertNotIn('outputs', WORKFLOW[True]['workflow_call'])
        self.assertFalse(WORKFLOW[True]['workflow_call']['inputs']['collect-failure-findings']['default'])
        self.assertEqual(nested['uses'], './.github/workflows/job-sonarcloud-quality-gate.yml')
        self.assertEqual(nested['permissions'], {'contents': 'read'})
        self.assertEqual(nested['with']['mode'], 'enforce')
        for guard in ('always()', '!cancelled()', 'inputs.collect-failure-findings',
                      "github.event_name == 'pull_request'", 'github.event.pull_request.head.repo.full_name == github.repository',
                      "needs.sonarcloud.result == 'failure'", "needs.sonarcloud.outputs.analysis-completed == 'true'"):
            self.assertIn(guard, nested['if'])
        self.assertIn("steps.analysis-metadata.outcome == 'success'", VERIFY['if'])
        begin = STEPS['Begin SonarQube Cloud analysis']['run']
        self.assertIn('/d:sonar.scanner.metadataFilePath=${SONAR_REPORT_PATH}', begin)
        self.assertIn('/d:sonar.qualitygate.wait=true', begin)
        self.assertIn('/d:sonar.qualitygate.timeout=300', begin)


if __name__ == '__main__':
    unittest.main()
