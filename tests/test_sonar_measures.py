"""Exercise the actual findings job against credential-free API responses."""

from contextlib import redirect_stdout
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
import urllib.error
from unittest.mock import patch

import yaml


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = yaml.safe_load((ROOT / '.github/workflows/job-sonarcloud-quality-gate.yml').read_text(encoding='utf-8'))
STEP = WORKFLOW['jobs']['sonar-quality-gate']['steps'][0]
SCRIPT = STEP['run'].split("python3 <<'PY'\n", 1)[1].rsplit('\nPY', 1)[0]


METRICS = ('new_violations', 'new_bugs', 'new_vulnerabilities',
           'new_code_smells', 'new_security_hotspots')


def zero_measures():
    return [{'metric': name, 'periods': [{'index': 1, 'value': '0'}]} for name in METRICS]


class SonarMeasuresTests(unittest.TestCase):
    def run_gate(self, measures=None, mode='enforce', responses=None):
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
            responses = responses or [payload] * 6
            responses = [response if isinstance(response, Exception) else io.BytesIO(response)
                         for response in responses]
            with patch.dict(os.environ, environment, clear=True), \
                    patch('urllib.request.urlopen', side_effect=responses) as request, \
                    patch('time.sleep'), redirect_stdout(io.StringIO()), \
                    self.assertRaises(SystemExit) as stopped:
                exec(compile(SCRIPT, 'job-sonarcloud-quality-gate.yml', 'exec'), {})
            self.request_count = request.call_count
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
                self.assertEqual(code, 1)
                self.assertIn('verdict=failed (evidence unavailable)\n', output)
                self.assertNotIn('verdict=passed\n', output)

    def test_every_configured_metric_is_required(self):
        for missing in METRICS:
            with self.subTest(missing=missing):
                code, output, summary = self.run_gate([
                    measure for measure in zero_measures() if measure['metric'] != missing])
                self.assertEqual(code, 1)
                self.assertEqual(self.request_count, 6)
                self.assertIn('gate_failed=true\n', output)
                self.assertIn(missing, summary)
                self.assertNotIn('verdict=passed\n', output)

    def test_invalid_values_are_not_zero(self):
        for value in (None, '', 'oops', 'NaN', 'Infinity', '-Infinity', '-1', '0.5', True, {}, []):
            with self.subTest(value=value):
                measures = zero_measures()
                measures[0]['periods'][0]['value'] = value
                code, output, _ = self.run_gate(measures)
                self.assertEqual(code, 1)
                self.assertIn('gate_failed=true\n', output)
                self.assertNotIn('verdict=passed\n', output)

    def test_missing_invalid_and_unrecognized_reports_fail_enforce(self):
        for payload in (b'not json', b'null', b'{}', b'[]',
                        b'{"component":{"measures":{}}}',
                        b'{"component":{"measures":[]}}',
                        b'{"component":{"measures":[{"metric":"unrecognized","value":"0"}]}}'):
            with self.subTest(payload=payload):
                code, output, _ = self.run_gate(responses=[payload] * 6)
                self.assertEqual(code, 1)
                self.assertEqual(self.request_count, 6)
                self.assertIn('gate_failed=true\n', output)
                self.assertIn('breached_count=0\n', output)

    def test_warn_reports_incomplete_evidence_without_passing_it(self):
        for measures in ([], zero_measures()[:1],
                         [{'metric': 'new_bugs', 'period': {'value': 'NaN'}}]):
            with self.subTest(measures=measures):
                code, output, _ = self.run_gate(measures, mode='warn')
                self.assertEqual(code, 0)
                self.assertIn('verdict=skipped (metrics unavailable)\n', output)
                self.assertIn('gate_failed=false\n', output)

    def test_transient_error_and_partial_report_can_recover(self):
        complete = json.dumps({'component': {'measures': zero_measures()}}).encode()
        for first in (urllib.error.URLError('timeout'), b'{"component":{"measures":[]}}'):
            with self.subTest(first=first):
                code, output, _ = self.run_gate(responses=[first, complete])
                self.assertEqual(code, 0)
                self.assertEqual(self.request_count, 2)
                self.assertIn('verdict=passed\n', output)

    def test_exhausted_transport_error_fails_enforce(self):
        code, output, _ = self.run_gate(responses=[urllib.error.URLError('timeout')] * 6)
        self.assertEqual(code, 1)
        self.assertEqual(self.request_count, 6)
        self.assertIn('gate_failed=true\n', output)

    def test_partial_reports_cannot_accumulate_into_a_pass(self):
        partials = [json.dumps({'component': {'measures': [measure]}}).encode()
                    for measure in zero_measures()]
        code, output, _ = self.run_gate(responses=partials + [b'{}'])
        self.assertEqual(code, 1)
        self.assertIn('gate_failed=true\n', output)
        self.assertNotIn('verdict=passed\n', output)

    def test_invalid_or_ambiguous_periods_cannot_hide_a_breach(self):
        for evidence in (
                {'periods': [{'index': 1, 'value': '0'}, {'index': 1, 'value': '3'}]},
                {'period': {'index': 2, 'value': '0'}},
                {'periods': [{'index': True, 'value': '0'}]},
                {'periods': [{'index': '1', 'value': '0'}]},
                {'period': {'index': True, 'value': '0'}},
                {'period': {'value': '0'}, 'periods': [{'index': 1, 'value': '3'}]},
                {'periods': None}, {'periods': {}}, {'periods': [None]}):
            with self.subTest(evidence=evidence):
                measures = zero_measures()
                measures[0] = {'metric': METRICS[0], **evidence}
                code, output, _ = self.run_gate(measures)
                self.assertEqual(code, 1)
                self.assertIn('gate_failed=true\n', output)
                self.assertNotIn('verdict=passed\n', output)

    def test_duplicate_metric_is_ambiguous(self):
        code, output, _ = self.run_gate(zero_measures() + zero_measures()[:1])
        self.assertEqual(code, 1)
        self.assertIn('new_violations', output)

    def test_complete_singular_period_zeros_pass(self):
        code, output, _ = self.run_gate([
            {'metric': metric, 'period': {'value': '0.0'}} for metric in METRICS])
        self.assertEqual(code, 0)
        self.assertEqual(self.request_count, 1)
        self.assertIn('verdict=passed\n', output)

    def test_complete_report_breach_keeps_mode_contract(self):
        for mode in ('warn', 'enforce'):
            with self.subTest(mode=mode):
                measures = zero_measures()
                measures[1]['periods'][0]['value'] = '3'
                code, output, summary = self.run_gate(measures, mode=mode)
                self.assertEqual(code, 1 if mode == 'enforce' else 0)
                self.assertEqual(self.request_count, 1)
                self.assertIn('gate_failed=true\n', output)
                self.assertIn('breached_count=1\n', output)
                self.assertIn('new_bugs=3 (threshold 0)', summary)

    def test_pr_core_preserves_opt_in_mode_and_failure_outputs(self):
        core = yaml.safe_load((ROOT / '.github/workflows/pr-core.yml').read_text())
        inputs = core[True]['workflow_call']['inputs']
        self.assertFalse(inputs['enable-sonar-quality-gate']['default'])
        self.assertEqual(inputs['sonar-quality-gate-mode']['default'], 'warn')
        gate = core['jobs']['sonar-quality-gate']
        self.assertEqual(gate['with']['mode'], '${{ inputs.sonar-quality-gate-mode }}')
        for name in ('verdict', 'gate_failed', 'breached_count', 'breach_summary', 'summary_line'):
            self.assertEqual(WORKFLOW['jobs']['sonar-quality-gate']['outputs'][name],
                             '${{ steps.gate.outputs.' + name + ' }}')

    def test_authorization_failures_remain_fatal_in_both_modes(self):
        for mode in ('warn', 'enforce'):
            for status in (400, 401, 403, 404):
                with self.subTest(mode=mode, status=status):
                    error = urllib.error.HTTPError('https://invalid.example', status,
                                                   'fixture', {}, io.BytesIO(b'fixture'))
                    code, output, _ = self.run_gate(mode=mode, responses=[error])
                    self.assertEqual(code, 1)
                    self.assertEqual(self.request_count, 1)
                    self.assertIn('verdict=configuration failed\n', output)


if __name__ == '__main__':
    unittest.main()
