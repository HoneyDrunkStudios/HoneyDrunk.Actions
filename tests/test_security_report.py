"""Current-run security evidence and fail-closed final gate regression tests."""
import copy
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / '.github/scripts/security-report.py'
SPEC = importlib.util.spec_from_file_location('security_report', SCRIPT)
reporter = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(reporter)


class SecurityReportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.env = {f'{name.upper()}_RESULT': 'success' for name in reporter.SCANNERS}
        self.env.update(ENABLE_SAST='true', ENABLE_SECRET_SCAN='true', ENABLE_IAC_SCAN='true',
                        IAC_HAS_TARGETS='true', FAIL_ON_HIGH_SEVERITY='true', DOWNLOAD_OUTCOME='success')
        self.dependency = {'status': 'clean', 'counts': dict.fromkeys(reporter.SEVERITIES[:-1], 0),
                           'findings': [], 'errors': [], 'projects': [{'path': 'App.csproj', 'status': 'clean', 'exitCode': 0}]}
        self.write('vulnerability-report/dependencies/summary.json', self.dependency)
        self.write('vulnerability-report/execution.json', {'restore': 'success', 'scan': 'success'})
        self.sarif = {'version': '2.1.0', 'runs': [{'tool': {'driver': {'name': 'Scanner', 'rules': []}}, 'results': []}]}
        for directory in ('sast-report', 'secret-scan-report', 'iac-security-report'):
            self.write(directory + '/results.sarif', self.sarif)

    def write(self, path, data):
        target = self.root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(data), encoding='utf-8')

    def report(self):
        return reporter.consolidate(self.root, self.env)

    def finding(self, severity=None, level=None):
        result = {'message': {'text': 'A finding'}, 'ruleId': 'R1'}
        if severity is not None:
            result['properties'] = {'security-severity': severity}
        if level is not None:
            result['level'] = level
        return result

    def test_complete_clean(self):
        report = self.report()
        self.assertTrue(report['gate_passed'])
        self.assertEqual(report['summary']['total_issues'], 0)
        reporter.check_gate(report)

    def test_each_dependency_severity_blocks_even_without_high_gate(self):
        self.env['FAIL_ON_HIGH_SEVERITY'] = 'false'
        for severity in reporter.SEVERITIES[:-1]:
            with self.subTest(severity=severity):
                data = copy.deepcopy(self.dependency)
                data.update(status='findings', findings=[{'severity': severity}])
                data['counts'][severity] = 1
                data['projects'][0]['status'] = 'findings'
                self.write('vulnerability-report/dependencies/summary.json', data)
                self.write('vulnerability-report/execution.json', {'restore': 'success', 'scan': 'failure'})
                report = self.report()
                self.assertEqual(report['scans']['dependency']['count'], 1)
                self.assertTrue(report['blocked'])

    def test_sarif_thresholds_and_unknown(self):
        for severity, blocked in [('3.9', False), ('4.0', False), ('7.0', True), ('9.0', True), (None, True)]:
            with self.subTest(severity=severity):
                self.sarif['runs'][0]['results'] = [self.finding(severity)]
                self.write('sast-report/results.sarif', self.sarif)
                report = self.report()
                self.assertEqual(report['blocked'], blocked)
                self.assertEqual(report['summary']['total_issues'], 1)
        self.env['FAIL_ON_HIGH_SEVERITY'] = 'false'
        self.assertTrue(self.report()['blocked'])  # Unknown severity remains fail-closed.
        self.sarif['runs'][0]['results'] = [self.finding('8.0')]
        self.write('sast-report/results.sarif', self.sarif)
        reporter.check_gate(self.report())
        self.sarif['runs'][0]['results'] = [self.finding('9.0')]
        self.write('sast-report/results.sarif', self.sarif)
        self.assertTrue(self.report()['blocked'])

    def test_sarif_rule_metadata_and_level(self):
        self.sarif['runs'][0]['tool']['driver']['rules'] = [{'id': 'R1', 'properties': {'security-severity': '8.5'}}]
        self.sarif['runs'][0]['results'] = [self.finding(level='warning')]
        self.write('sast-report/results.sarif', self.sarif)
        self.assertEqual(self.report()['scans']['sast']['counts']['high'], 1)
        self.sarif['runs'][0]['tool']['driver']['rules'] = []
        self.write('sast-report/results.sarif', self.sarif)
        reporter.check_gate(self.report())

    def codeql_fixture(self):
        return json.loads((Path(__file__).parent / 'fixtures/security/codeql-extensions.sarif').read_text())

    def test_real_codeql_extension_metadata_preserves_counts_and_policy(self):
        data = self.codeql_fixture()
        self.assertEqual(data['runs'][0]['tool']['driver']['rules'], [])
        self.assertEqual(len(data['runs'][0]['tool']['extensions'][0]['rules']), 164)
        self.write('sast-report/results.sarif', data)
        for high_gate in ('true', 'false'):
            with self.subTest(high_gate=high_gate):
                self.env['FAIL_ON_HIGH_SEVERITY'] = high_gate
                report = self.report()
                self.assertEqual(report['scans']['sast']['counts'],
                                 {'low': 15, 'moderate': 1, 'high': 1, 'critical': 0, 'unknown': 0})
                self.assertEqual(report['blocked'], high_gate == 'true')
                if high_gate == 'false':
                    reporter.check_gate(report)

    def test_extension_rule_resolution_forms_and_component_isolation(self):
        for reference in ({'index': 0}, {'name': 'extension', 'index': 0}, {'guid': '11111111-1111-4111-8111-111111111111'}):
            for rule_reference in ({'id': 'R1'}, {'index': 0}, {'guid': '22222222-2222-4222-8222-222222222222'}):
                with self.subTest(component=reference, rule=rule_reference):
                    data = copy.deepcopy(self.sarif)
                    tool = data['runs'][0]['tool']
                    tool['driver']['rules'] = [{'id': 'R1', 'defaultConfiguration': {'level': 'note'}}]
                    tool['extensions'] = [{'name': 'extension', 'guid': '11111111-1111-4111-8111-111111111111', 'rules': [
                        {'id': 'R1', 'guid': '22222222-2222-4222-8222-222222222222', 'properties': {'security-severity': '9.1'}}]}]
                    data['runs'][0]['results'] = [{'message': {'text': 'Finding'},
                        'rule': dict(rule_reference, toolComponent=reference)}]
                    self.write('sast-report/results.sarif', data)
                    report = self.report()
                    self.assertEqual(report['scans']['sast']['counts']['critical'], 1)
                    self.assertTrue(report['blocked'])

    def test_legacy_and_nested_driver_references(self):
        tool = {'driver': {'name': 'scanner', 'rules': [{'id': 'R1', 'properties': {'security-severity': '8'}}]}}
        for result in ({'ruleId': 'R1'}, {'ruleIndex': 0}, {'rule': {'id': 'R1'}},
                       {'rule': {'index': 0}}, {'ruleId': 'R1', 'ruleIndex': 0, 'rule': {'id': 'R1', 'index': 0}}):
            with self.subTest(result=result):
                self.assertEqual(reporter.referenced_rule(tool, result), tool['driver']['rules'][0])

    def test_hierarchical_rule_ids_preserve_index_and_guid_resolution(self):
        rule = {'id': 'abc/def', 'guid': '22222222-2222-4222-8222-222222222222', 'properties': {'security-severity': '8'}}
        tool = {'driver': {'name': 'scanner', 'rules': [rule]}}
        for result in ({'ruleId': 'abc/def/ghi', 'ruleIndex': 0},
                       {'ruleId': 'abc/def/', 'ruleIndex': 0},
                       {'rule': {'id': 'abc/def/ghi', 'index': 0}},
                       {'rule': {'id': 'abc/def/ghi', 'guid': '22222222-2222-4222-8222-222222222222'}}):
            with self.subTest(result=result):
                self.assertEqual(reporter.referenced_rule(tool, result), rule)
        for rule_id in ('abc/defg', 'abc/def/ghi/jkl'):
            with self.subTest(rule_id=rule_id), self.assertRaises(ValueError):
                reporter.referenced_rule(tool, {'ruleId': rule_id, 'ruleIndex': 0})

    def test_invalid_extension_references_fail_closed_even_with_result_severity(self):
        cases = []
        for invalid in (-1, 3, True, '0', 0.0, None):
            cases.append({'rule': {'index': 47, 'toolComponent': {'index': invalid}}})
        for invalid in (-1, 164, True, '47', 47.0, None):
            cases.append({'rule': {'index': invalid, 'toolComponent': {'index': 0}}})
        cases.extend([
            {'rule': None}, {'rule': []}, {'rule': {'toolComponent': None}},
            {'rule': {'index': 47, 'id': 'wrong', 'toolComponent': {'index': 0}}},
            {'rule': {'index': 47, 'toolComponent': {'index': 0, 'name': 'wrong'}}},
            {'rule': {'index': 47, 'toolComponent': {'index': 0, 'guid': 'wrong'}}},
            {'rule': {'index': 47, 'toolComponent': {'guid': 'missing'}}},
            {'ruleIndex': 48}, {'ruleId': 'wrong'},
            {'ruleIndex': 47, 'rule': {'index': 47.0, 'toolComponent': {'index': 0}}},
            {'ruleIndex': 47.0},
            {'rule': {'id': 'missing', 'toolComponent': {'index': 0}}},
            {'rule': {}},
        ])
        self.env['FAIL_ON_HIGH_SEVERITY'] = 'false'
        for mutation in cases:
            with self.subTest(mutation=mutation):
                data = self.codeql_fixture()
                result = data['runs'][0]['results'][0]
                result.update(mutation)
                result['properties'] = {'security-severity': '1.0'}
                self.write('sast-report/results.sarif', data)
                report = self.report()
                self.assertTrue(report['blocked'])
                self.assertEqual(report['scans']['sast']['status'], 'error')
                self.assertIsNone(report['summary']['total_issues'])

    def test_ambiguous_and_malformed_metadata_is_rejected(self):
        tool = {'driver': {'name': 'scanner', 'rules': [{'id': 'R1'}, {'id': 'R1'}]}}
        with self.assertRaises(ValueError):
            reporter.referenced_rule(tool, {'ruleId': 'R1'})
        self.assertEqual(reporter.referenced_rule(tool, {'ruleId': 'R1', 'ruleIndex': 1}), {'id': 'R1'})
        for extensions in (None, {}, [None], [{'rules': {}}], [{'rules': [None]}], [{'rules': [{}]}]):
            with self.subTest(extensions=extensions), self.assertRaises(ValueError):
                reporter.referenced_rule(dict(tool, extensions=extensions),
                                         {'rule': {'index': 0, 'toolComponent': {'index': 0}}})
        tool['extensions'] = [{'guid': '33333333-3333-4333-8333-333333333333'}, {'guid': '33333333-3333-4333-8333-333333333333'}]
        with self.assertRaises(ValueError):
            reporter.referenced_rule(tool, {'rule': {'toolComponent': {'guid': '33333333-3333-4333-8333-333333333333'}}})

    def test_guid_resolution_ignores_hexadecimal_case(self):
        component_guid = 'abcdefab-cdef-4abc-8abc-abcdefabcdef'
        rule_guid = 'fedcbafe-dcba-4fed-9fed-fedcbafedcba'
        rule = {'id': 'CaseSensitive', 'guid': rule_guid, 'properties': {'security-severity': '7.5'}}
        component = {'name': 'CaseSensitive', 'guid': component_guid, 'rules': [rule]}
        for driver in (True, False):
            for indexed in (True, False):
                with self.subTest(driver=driver, indexed=indexed):
                    tool = {'driver': component} if driver else {'driver': {'name': 'scanner'}, 'extensions': [component]}
                    reference = {'id': 'CaseSensitive', 'guid': rule_guid.upper(),
                                 'toolComponent': {'name': 'CaseSensitive', 'guid': component_guid.upper()}}
                    if indexed:
                        reference['index'] = 0
                        if not driver:
                            reference['toolComponent']['index'] = 0
                    self.assertEqual(reporter.referenced_rule(tool, {'rule': reference}), rule)
                    reference['id'] = 'casesensitive'
                    with self.assertRaises(ValueError):
                        reporter.referenced_rule(tool, {'rule': reference})
        duplicate = dict(component, guid=component_guid.upper())
        with self.assertRaises(ValueError):
            reporter.referenced_component({'driver': component, 'extensions': [duplicate]}, {'guid': component_guid})
        duplicate_rule = dict(rule, guid=rule_guid.upper())
        with self.assertRaises(ValueError):
            reporter.referenced_rule({'driver': dict(component, rules=[rule, duplicate_rule])},
                                     {'rule': {'guid': rule_guid}})

    def test_malformed_guids_cannot_resolve_low_severity_metadata(self):
        self.env['FAIL_ON_HIGH_SEVERITY'] = 'false'
        invalid_guids = ('not-a-uuid', '', '22222222222242228222222222222222',
                         '22222222-2222-0222-8222-222222222222',
                         '22222222-2222-4222-0222-222222222222', None, 42, [])
        for invalid in invalid_guids:
            for target in ('rule', 'component'):
                for reference_has_guid in (True, False):
                    with self.subTest(guid=invalid, target=target, reference=reference_has_guid):
                        data = copy.deepcopy(self.sarif)
                        rule = {'id': 'R1', 'properties': {'security-severity': '1.0'}}
                        component = {'name': 'extension', 'rules': [rule]}
                        reference = {'id': 'R1', 'index': 0, 'toolComponent': {'index': 0}}
                        definition = rule if target == 'rule' else component
                        identity = reference if target == 'rule' else reference['toolComponent']
                        definition['guid'] = invalid
                        if reference_has_guid:
                            identity['guid'] = invalid
                            del identity['index']
                        data['runs'][0]['tool']['extensions'] = [component]
                        data['runs'][0]['results'] = [{'message': {'text': 'Finding'}, 'rule': reference}]
                        self.write('sast-report/results.sarif', data)
                        report = self.report()
                        self.assertTrue(report['blocked'])
                        self.assertEqual(report['scans']['sast']['status'], 'error')
                        self.assertIsNone(report['summary']['total_issues'])

    def test_extension_unknown_and_malformed_severity_remain_blocking(self):
        self.env['FAIL_ON_HIGH_SEVERITY'] = 'false'
        for metadata in ({}, {'properties': {'security-severity': 'NaN'}},
                         {'properties': {'security-severity': 'bad'}}, {'defaultConfiguration': []}):
            with self.subTest(metadata=metadata):
                data = self.codeql_fixture()
                data['runs'][0]['tool']['extensions'][0]['rules'][47] = dict(metadata, id='cs/insecure-sql-connection')
                self.write('sast-report/results.sarif', data)
                report = self.report()
                self.assertTrue(report['blocked'])
                if not metadata:
                    self.assertEqual(report['scans']['sast']['counts']['unknown'], 1)
                else:
                    self.assertEqual(report['scans']['sast']['status'], 'error')

    def test_secret_is_critical(self):
        self.sarif['runs'][0]['results'] = [self.finding(level='note')]
        self.write('secret-scan-report/results.sarif', self.sarif)
        report = self.report()
        self.assertEqual(report['scans']['secret']['counts']['critical'], 1)
        self.assertTrue(report['blocked'])

    def test_missing_invalid_and_failed_sarif_never_zero(self):
        mutations = [{}, {'version': '2.1.0', 'runs': []},
                     {'version': '2.1.0', 'runs': [{'results': []}]},
                     {'version': '2.1.0', 'runs': [{'tool': {'driver': {'name': 'Scanner'}}}]},
                     {'version': '2.1.0', 'runs': [{'tool': {'driver': {'name': 'Scanner'}}, 'results': [],
                                                   'invocations': [{'executionSuccessful': False}]}]}]
        path = self.root / 'sast-report/results.sarif'
        for data in mutations + [None, 'invalid-json']:
            with self.subTest(data=data):
                if data is None:
                    path.unlink(missing_ok=True)
                elif data == 'invalid-json':
                    path.write_text('{broken')
                else:
                    self.write('sast-report/results.sarif', data)
                report = self.report()
                self.assertIsNone(report['scans']['sast']['count'])
                self.assertIsNone(report['summary']['total_issues'])
                self.assertTrue(report['blocked'])
                self.assertIn('unknown', reporter.summary_markdown(report))

    def test_one_invalid_file_invalidates_scanner_not_other_findings(self):
        self.sarif['runs'][0]['results'] = [self.finding('8')]
        self.write('sast-report/results.sarif', self.sarif)
        self.write('sast-report/broken.sarif', {})
        self.write('secret-scan-report/results.sarif', self.sarif)
        report = self.report()
        self.assertIsNone(report['scans']['sast']['count'])
        self.assertEqual(report['summary']['known_issues'], 1)

    def test_failed_cancelled_skipped_or_missing_enabled_jobs_block_with_valid_evidence(self):
        for scanner in reporter.SCANNERS:
            for result in ('failure', 'cancelled', 'skipped', ''):
                with self.subTest(scanner=scanner, result=result):
                    env = self.env.copy()
                    env[scanner.upper() + '_RESULT'] = result
                    report = reporter.consolidate(self.root, env)
                    self.assertTrue(report['blocked'])
                    self.assertEqual(report['scans'][scanner]['status'], 'error')
                    self.assertFalse(report['summary']['complete'])

    def test_build_failure_missing_sast_preserves_other_results(self):
        self.env['SAST_RESULT'] = 'failure'
        (self.root / 'sast-report/results.sarif').unlink()
        report = self.report()
        self.assertEqual(report['scans']['dependency']['status'], 'clean')
        self.assertIsNone(report['scans']['sast']['count'])
        self.assertTrue(report['blocked'])

    def test_disabled_and_no_targets_are_distinct_from_clean(self):
        self.env.update(ENABLE_SAST='false', SAST_RESULT='skipped', IAC_HAS_TARGETS='false')
        (self.root / 'sast-report/results.sarif').unlink()
        (self.root / 'iac-security-report/results.sarif').unlink()
        report = self.report()
        self.assertEqual(report['scans']['sast']['status'], 'disabled')
        self.assertEqual(report['scans']['iac']['status'], 'no-targets')
        reporter.check_gate(report)
        self.env['IAC_RESULT'] = 'failure'
        self.assertTrue(self.report()['blocked'])

    def test_missing_or_invalid_configuration_blocks(self):
        for key in ('ENABLE_SAST', 'FAIL_ON_HIGH_SEVERITY', 'IAC_HAS_TARGETS'):
            env = self.env.copy()
            del env[key]
            self.assertTrue(reporter.consolidate(self.root, env)['blocked'])

    def test_invalid_dependency_summary_blocks(self):
        for changes in ({'status': 'error'}, {'errors': ['scanner failed']}, {'projects': []},
                        {'counts': {}}, {'findings': [{}]}, {'status': 'findings'},
                        {'projects': [{'status': 'clean', 'exitCode': 1}]}):
            with self.subTest(changes=changes):
                data = dict(self.dependency, **changes)
                self.write('vulnerability-report/dependencies/summary.json', data)
                report = self.report()
                self.assertIsNone(report['scans']['dependency']['count'])
                self.assertTrue(report['blocked'])

    def test_gate_rejects_missing_invalid_and_contradictory_report(self):
        for report in ({}, None, {'gate_passed': True}):
            with self.assertRaises(ValueError):
                reporter.check_gate(report)
        report = self.report()
        report['scans']['sast']['job_result'] = 'failure'
        with self.assertRaises(ValueError):
            reporter.check_gate(report)
        report = self.report()
        report['scans']['dependency'].update(count=1, status='findings')
        report['scans']['dependency']['counts']['low'] = 1
        with self.assertRaises(ValueError):
            reporter.check_gate(report)

    def test_partial_dependency_errors_preserve_validated_known_findings(self):
        data = copy.deepcopy(self.dependency)
        data.update(status='error', findings=[{'severity': 'high'}], errors=['Second project failed'])
        data['counts']['high'] = 1
        data['projects'].extend([{'path': 'Vulnerable.csproj', 'status': 'findings', 'exitCode': 0},
                                 {'path': 'Broken.csproj', 'status': 'error', 'exitCode': 1}])
        self.write('vulnerability-report/dependencies/summary.json', data)
        self.write('vulnerability-report/execution.json', {'restore': 'failure', 'scan': 'failure'})
        report = self.report()
        self.assertEqual(report['scans']['dependency']['count'], 1)
        self.assertEqual(report['scans']['dependency']['status'], 'error')
        self.assertEqual(report['summary']['known_issues'], 1)
        self.assertIsNone(report['summary']['total_issues'])
        self.assertFalse(report['summary']['complete'])
        self.assertTrue(report['blocked'])
        data['counts']['high'] = 2
        self.write('vulnerability-report/dependencies/summary.json', data)
        self.assertIsNone(self.report()['scans']['dependency']['count'])

    def test_download_failure_and_hidden_dependency_step_failures_block(self):
        self.env['DOWNLOAD_OUTCOME'] = 'failure'
        self.assertTrue(self.report()['blocked'])
        self.env['DOWNLOAD_OUTCOME'] = 'success'
        for execution in ({}, {'restore': 'failure', 'scan': 'success'},
                          {'restore': 'success', 'scan': 'failure'},
                          {'restore': 'success', 'scan': 'skipped'}):
            with self.subTest(execution=execution):
                self.write('vulnerability-report/execution.json', execution)
                self.assertTrue(self.report()['blocked'])
        (self.root / 'vulnerability-report/execution.json').unlink()
        self.assertTrue(self.report()['blocked'])

    def test_cli_publishes_before_gate_failure_and_outputs_unknown(self):
        (self.root / 'sast-report/results.sarif').unlink()
        output = self.root / 'output'
        summary = self.root / 'step-summary'
        env = dict(os.environ, **self.env, GITHUB_OUTPUT=str(output), GITHUB_STEP_SUMMARY=str(summary))
        command = [sys.executable, str(SCRIPT)]
        result = subprocess.run(command + ['consolidate', '--reports-root', str(self.root)], cwd=self.root,
                                env=env, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue((self.root / 'consolidated-security-report.json').exists())
        self.assertTrue((self.root / 'security-summary.md').exists())
        self.assertIn('sast_count=unknown', output.read_text())
        self.assertIn('gate_passed=false', output.read_text())
        self.assertIn('FAILED', summary.read_text())
        result = subprocess.run(command + ['gate'], cwd=self.root, capture_output=True, text=True)
        self.assertEqual(result.returncode, 1)
        (self.root / 'consolidated-security-report.json').unlink()
        self.assertEqual(subprocess.run(command + ['gate'], cwd=self.root, capture_output=True).returncode, 1)


if __name__ == '__main__':
    unittest.main()

