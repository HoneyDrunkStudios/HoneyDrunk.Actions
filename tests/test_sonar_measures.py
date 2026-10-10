"""Exercise the actual findings job against credential-free API responses."""

from contextlib import redirect_stdout
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import yaml


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = yaml.safe_load((ROOT / '.github/workflows/job-sonarcloud-quality-gate.yml').read_text(encoding='utf-8'))
STEP = WORKFLOW['jobs']['sonar-quality-gate']['steps'][0]
SCRIPT = STEP['run'].split("python3 <<'PY'\n", 1)[1].rsplit('\nPY', 1)[0]


class SonarMeasuresTests(unittest.TestCase):
    def run_gate(self, measures, mode='enforce'):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'output'
            summary = Path(directory) / 'summary'
            environment = {
                'GITHUB_OUTPUT': str(output), 'GITHUB_STEP_SUMMARY': str(summary),
                'SONAR_TOKEN': 'fixture-not-a-token', 'SONAR_HOST_URL': 'https://invalid.example',
                'SONAR_ORGANIZATION': 'fixture', 'SONAR_PROJECT_KEY': 'fixture',
                'PR_NUMBER': '5', 'MODE': mode,
            }
            environment.update({name: '0' for name in STEP['env'] if name.startswith('MAX_NEW_')})
            payload = json.dumps({'component': {'measures': measures}}).encode()
            with patch.dict(os.environ, environment, clear=True), \
                    patch('urllib.request.urlopen', return_value=io.BytesIO(payload)), \
                    patch('time.sleep'), redirect_stdout(io.StringIO()), \
                    self.assertRaises(SystemExit) as stopped:
                exec(compile(SCRIPT, 'job-sonarcloud-quality-gate.yml', 'exec'), {})
            return stopped.exception.code, output.read_text(encoding='utf-8'), summary.read_text(encoding='utf-8')

    def test_cloud_periods_zero_is_observed(self):
        measures = [{'metric': name, 'periods': [{'index': 1, 'value': '0', 'bestValue': True}]}
                    for name in ('new_violations', 'new_bugs', 'new_vulnerabilities',
                                 'new_code_smells', 'new_security_hotspots')]
        code, output, summary = self.run_gate(measures)
        self.assertEqual(code, 0)
        self.assertIn('verdict=passed\n', output)
        for measure in measures:
            self.assertIn(measure['metric'] + '=0', summary)

    def test_cloud_periods_breach_fails_enforce(self):
        code, output, summary = self.run_gate([
            {'metric': 'new_bugs', 'periods': [{'index': 1, 'value': '3'}]}])
        self.assertEqual(code, 1)
        self.assertIn('gate_failed=true\n', output)
        self.assertIn('breached_count=1\n', output)
        self.assertIn('new_bugs=3 (threshold 0)', summary)

    def test_cloud_periods_breach_preserves_warn_mode(self):
        code, output, _ = self.run_gate([
            {'metric': 'new_vulnerabilities', 'periods': [{'index': 1, 'value': '1'}]}], mode='warn')
        self.assertEqual(code, 0)
        self.assertIn('verdict=warn - ', output)
        self.assertIn('gate_failed=true\n', output)

    def test_singular_period_remains_supported(self):
        code, output, _ = self.run_gate([{'metric': 'new_code_smells', 'period': {'value': '2'}}])
        self.assertEqual(code, 1)
        self.assertIn('new_code_smells=2 (threshold 0)', output)

    def test_selects_new_code_period_by_index_not_position(self):
        code, _, summary = self.run_gate([
            {'metric': 'new_bugs', 'periods': [{'index': 2, 'value': '0'}, {'index': 1, 'value': '4'}]}])
        self.assertEqual(code, 1)
        self.assertIn('new_bugs=4 (threshold 0)', summary)

    def test_missing_new_code_value_is_not_zero(self):
        for measure in (
                {'metric': 'new_bugs', 'periods': []},
                {'metric': 'new_bugs', 'periods': [{'index': 2, 'value': '0'}]},
                {'metric': 'new_bugs', 'periods': [{'index': 1}]},
                {'metric': 'new_bugs', 'value': '0'}):
            with self.subTest(measure=measure):
                code, output, _ = self.run_gate([measure])
                self.assertEqual(code, 0)
                self.assertIn('verdict=skipped (metrics unavailable)\n', output)
                self.assertNotIn('verdict=passed\n', output)


if __name__ == '__main__':
    unittest.main()
