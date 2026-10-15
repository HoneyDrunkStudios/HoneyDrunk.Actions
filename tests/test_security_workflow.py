"""Check the caller boundary and failure-safe orchestration of nightly security."""
import pathlib
import os
import subprocess
import tempfile
import unittest

import yaml

ROOT = pathlib.Path(__file__).resolve().parents[1]


class SecurityWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.workflow = yaml.safe_load((ROOT / '.github/workflows/nightly-security.yml').read_text())
        self.jobs = self.workflow['jobs']

    def step(self, job, name):
        return next(step for step in self.jobs[job]['steps'] if step['name'] == name)

    def test_independent_scanners_do_not_wait_for_other_scanners(self):
        for job in ('dependency-scan', 'sast-analysis', 'secret-scan', 'iac-security-scan'):
            with self.subTest(job=job):
                self.assertNotIn('needs', self.jobs[job])

    def test_dependency_scan_runs_after_failed_restore_and_blocks_all_severities(self):
        restore = self.step('dependency-scan', 'Restore dependencies')
        scan = self.step('dependency-scan', 'Run comprehensive vulnerability scan')
        self.assertTrue(restore['continue-on-error'])
        self.assertIn('always()', scan['if'])
        self.assertIn("steps.setup.outcome == 'success'", scan['if'])
        self.assertTrue(scan['continue-on-error'])
        self.assertEqual(scan['with']['fail-on-severity'], 'low')
        evidence = self.step('dependency-scan', 'Record dependency execution status')
        self.assertEqual(evidence['if'], 'always()')
        self.assertEqual(evidence['env']['RESTORE_OUTCOME'], '${{ steps.restore.outcome }}')
        self.assertEqual(evidence['env']['SCAN_OUTCOME'], '${{ steps.vulnerability-scan.outcome }}')

    def test_artifacts_are_uploaded_even_on_scan_failure(self):
        for job, name in (
            ('dependency-scan', 'Upload vulnerability report'),
            ('sast-analysis', 'Upload SAST report'),
            ('secret-scan', 'Upload secret scan report'),
            ('iac-security-scan', 'Upload IaC scan report'),
        ):
            with self.subTest(job=job):
                step = self.step(job, name)
                self.assertIn('always()', step['if'])
                self.assertEqual(step['with']['if-no-files-found'], 'error')
                self.assertTrue(step['with']['path'].endswith('/**/*'))

    def test_build_retains_audit_diagnostics_and_failure_log(self):
        step = self.step('sast-analysis', 'Build for CodeQL analysis')
        self.assertNotIn('continue-on-error', step)
        self.assertIn('WarningsNotAsErrors=NU1901%3BNU1902%3BNU1903%3BNU1904', step['run'])
        self.assertIn('tee security-reports/codeql-build.log', step['run'])
        for weakening in ('NuGetAudit=false', 'NoWarn=', 'TreatWarningsAsErrors=false', '|| true'):
            self.assertNotIn(weakening, step['run'])

    def test_gate_runs_last_even_after_report_or_issue_failure(self):
        job = self.jobs['consolidate-and-report']
        self.assertEqual(job['if'], 'always()')
        self.assertEqual(set(job['needs']), {'dependency-scan', 'sast-analysis', 'secret-scan', 'iac-security-scan'})
        final = job['steps'][-1]
        self.assertEqual(final['name'], 'Enforce final security result')
        self.assertEqual(final['if'], 'always()')
        self.assertNotIn('continue-on-error', final)
        self.assertTrue(final['run'].endswith('security-report.py gate'))
        consolidate = self.step('consolidate-and-report', 'Consolidate security findings')
        self.assertEqual(consolidate['if'], 'always()')
        for name in ('DEPENDENCY_RESULT', 'SAST_RESULT', 'SECRET_RESULT', 'IAC_RESULT',
                     'ENABLE_SAST', 'ENABLE_SECRET_SCAN', 'ENABLE_IAC_SCAN', 'IAC_HAS_TARGETS',
                     'FAIL_ON_HIGH_SEVERITY', 'DOWNLOAD_OUTCOME'):
            self.assertIn(name, consolidate['env'])

    def test_iac_detection_executes_with_spaces_and_multiple_matches(self):
        script = self.step('iac-security-scan', 'Detect IaC files')['run']
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            output = root / 'output'
            env = {**os.environ, 'GITHUB_OUTPUT': str(output)}
            result = subprocess.run(['bash', '-e', '-o', 'pipefail', '-c', script],
                                    cwd=root, env=env, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(output.read_text(), 'has_iac=false\n')
            output.write_text('')
            (root / 'infra with spaces').mkdir()
            (root / 'infra with spaces' / 'main.bicep').write_text('param name string')
            for i in range(100):
                (root / f'config {i}.yaml').write_text('apiVersion: v1')
            result = subprocess.run(['bash', '-e', '-o', 'pipefail', '-c', script],
                                    cwd=root, env=env, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(output.read_text(), 'has_iac=true\n')

    def test_missing_scan_report_is_never_manufactured_as_clean(self):
        text = (ROOT / '.github/workflows/nightly-security.yml').read_text()
        self.assertNotIn('All scans passed cleanly', text)
        self.assertNotIn('count_open_alerts', text)
        self.assertNotIn('echo "0"', text)
        self.assertNotIn("cat > ./security-reports/secrets-scan.sarif", text)
        self.assertNotIn('permissions', self.workflow)


if __name__ == '__main__':
    unittest.main()
