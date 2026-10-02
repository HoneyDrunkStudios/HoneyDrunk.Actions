"""Run the workflow's actual Bash/Python with Git stubbed; never access a remote."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import textwrap
import unittest
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / '.github/workflows/coverage-baseline-ratchet.yml'


def step_source(name):
    section = WORKFLOW.read_text().split(f'      - name: {name}\n', 1)[1]
    return textwrap.dedent(section.split('        run: |\n', 1)[1].split('\n      - name:', 1)[0])


def report(classes):
    root = ET.Element('coverage')
    for filename, lines in classes.items():
        cls = ET.SubElement(root, 'class', filename=filename)
        for number, hits in lines.items():
            ET.SubElement(cls, 'line', number=str(number), hits=str(hits))
    return ET.tostring(root, encoding='unicode')


class CoverageBaselineRatchetTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.workdir = self.root
        self.output = self.root / 'step-output'
        self.git_log = self.root / 'git-log'
        bin_dir = self.root / 'bin'
        bin_dir.mkdir()
        git = bin_dir / 'git'
        git.write_text(textwrap.dedent('''\
            #!/usr/bin/env python3
            import json, os, sys
            from pathlib import Path
            args = sys.argv[1:]
            with open(os.environ['GIT_LOG'], 'a') as log:
                log.write(json.dumps(args) + '\\n')
            if args[0] == 'add' and not Path(args[-1]).is_file():
                sys.exit(128)
            if args[0] == 'diff':
                sys.exit(int(os.environ.get('GIT_DIFF_EXIT', '1')))
            sys.exit(0)
            '''))
        git.chmod(0o755)
        self.env = dict(os.environ, PATH=str(bin_dir) + os.pathsep + os.environ['PATH'],
                        GITHUB_OUTPUT=str(self.output), GIT_LOG=str(self.git_log),
                        GITHUB_SHA='test-commit-sha', DEFAULT_BRANCH='main')

    @property
    def baseline(self):
        return self.workdir / '.github/coverage-baseline.json'

    def add_project(self, name='HoneyDrunk.Payments.Tests.Unit.csproj'):
        path = self.workdir / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('<Project />\n')

    def add_report(self, content, name='one'):
        path = self.root / 'TestResults' / name / 'coverage.cobertura.xml'
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)

    def set_baseline(self, value):
        self.baseline.parent.mkdir(parents=True, exist_ok=True)
        self.baseline.write_text(json.dumps({'totalLineCoverage': value,
                                             'commit': 'previous', 'measuredAtUtc': 'previous'}))

    def run_workflow(self):
        self.env['WORKING_DIRECTORY'] = str(self.workdir.relative_to(self.root))
        measured = subprocess.run(['bash', '-e', '-o', 'pipefail', '-c',
                                   step_source('Measure coverage baseline')], cwd=self.root,
                                  env=self.env, capture_output=True, text=True)
        self.assertEqual(measured.returncode, 0, measured.stdout + measured.stderr)
        outputs = dict(line.split('=', 1) for line in self.output.read_text().splitlines())
        # Apply the exact GitHub step condition after exercising the real Bash/Python boundary.
        workflow = WORKFLOW.read_text()
        measure_step = workflow.split('      - name: Measure coverage baseline\n', 1)[1]
        self.assertIn('        id: coverage-baseline\n', measure_step.split('        run:', 1)[0])
        commit_step = workflow.split('      - name: Commit changed coverage baseline\n', 1)[1]
        self.assertIn("        if: steps.coverage-baseline.outputs.changed == 'true'\n",
                      commit_step.split('        run:', 1)[0])
        if outputs['changed'] == 'true':
            committed = subprocess.run(['bash', '-e', '-o', 'pipefail', '-c',
                                        step_source('Commit changed coverage baseline')],
                                       cwd=self.root, env=self.env, capture_output=True, text=True)
            self.assertEqual(committed.returncode, 0, committed.stdout + committed.stderr)
        return outputs

    def git_calls(self):
        return [json.loads(line) for line in self.git_log.read_text().splitlines()] if self.git_log.exists() else []

    def assert_skipped(self):
        self.assertEqual(self.run_workflow()['changed'], 'false')
        self.assertEqual(self.git_calls(), [])

    def test_tests_unit_projects_create_missing_baseline(self):
        self.add_project()
        self.add_report(report({'HoneyDrunk.Payments/Service.cs': {1: 3, 2: 0, 3: 1}}))
        self.assertEqual(self.run_workflow()['changed'], 'true')
        payload = json.loads(self.baseline.read_text())
        self.assertEqual(payload['totalLineCoverage'], 66.67)
        self.assertEqual(payload['commit'], 'test-commit-sha')
        self.assertRegex(payload['measuredAtUtc'], r'^\d{4}-\d{2}-\d{2}T.*Z$')
        self.assertIn(['add', '-f', './.github/coverage-baseline.json'], self.git_calls())
        self.assertIn(['commit', '-m', 'chore: ratchet coverage baseline to 66.67% [skip ci]'], self.git_calls())
        self.assertIn(['push', 'origin', 'HEAD:main'], self.git_calls())

    def test_valid_report_does_not_require_project_filename_discovery(self):
        self.add_report(report({'src/Service.cs': {1: 1}}))
        self.assertEqual(self.run_workflow()['changed'], 'true')
        self.assertEqual(json.loads(self.baseline.read_text())['totalLineCoverage'], 100)

    def test_missing_reports_skip_without_git_even_when_baseline_exists(self):
        self.add_project()
        self.set_baseline(90)
        before = self.baseline.read_bytes()
        self.assert_skipped()
        self.assertEqual(self.baseline.read_bytes(), before)

    def test_missing_reports_and_baseline_skip_without_git(self):
        self.add_project()
        self.assert_skipped()
        self.assertFalse(self.baseline.exists())

    def test_malformed_reports_skip_without_git(self):
        self.add_project()
        self.add_report('<coverage><broken')
        self.assert_skipped()
        self.assertFalse(self.baseline.exists())

    def test_zero_line_reports_skip_without_git(self):
        self.add_project()
        self.add_report(report({'src/Service.cs': {}}))
        self.assert_skipped()
        self.assertFalse(self.baseline.exists())

    def test_zero_covered_lines_write_real_zero_measurement(self):
        self.add_report(report({'src/Service.cs': {1: 0, 2: 0}}))
        self.assertEqual(self.run_workflow()['changed'], 'true')
        self.assertEqual(json.loads(self.baseline.read_text())['totalLineCoverage'], 0)

    def test_unchanged_baseline_preserves_metadata_and_skips_all_git(self):
        self.set_baseline(66.67)
        before = self.baseline.read_bytes()
        self.add_report(report({'src/Service.cs': {1: 1, 2: 0, 3: 1}}))
        self.assert_skipped()
        self.assertEqual(self.baseline.read_bytes(), before)

    def test_changed_baseline_is_committed(self):
        self.set_baseline(50)
        self.add_report(report({'src/Service.cs': {1: 1, 2: 1}}))
        self.assertEqual(self.run_workflow()['changed'], 'true')
        self.assertEqual(json.loads(self.baseline.read_text())['totalLineCoverage'], 100)
        self.assertIn(['push', 'origin', 'HEAD:main'], self.git_calls())

    def test_duplicate_reports_merge_hits_and_exclude_test_sources(self):
        source = self.root / 'src/Service.cs'
        source.parent.mkdir()
        source.write_text('// source\n')
        self.add_report(report({'src/Service.cs': {1: 1, 2: 0},
                                'HoneyDrunk.Payments.Tests.Unit/Tests.cs': {1: 0},
                                'HoneyDrunk.Payments.Canary/Probe.cs': {1: 0}}))
        self.add_report(report({str(source): {1: 0, 2: 1, 3: 0}}), name='two')
        self.add_report('<invalid', name='malformed')
        self.assertEqual(self.run_workflow()['changed'], 'true')
        self.assertEqual(json.loads(self.baseline.read_text())['totalLineCoverage'], 66.67)

    def test_test_sources_only_skip_without_git(self):
        self.add_report(report({'App.Tests.Unit/Tests.cs': {1: 1}, 'App.Canary/Probe.cs': {1: 1}}))
        self.assert_skipped()
        self.assertFalse(self.baseline.exists())

    def test_nested_working_directory_with_spaces(self):
        self.workdir = self.root / 'nested repo'
        self.add_project()
        self.add_report(report({'src/Service.cs': {1: 1}}))
        self.assertEqual(self.run_workflow()['changed'], 'true')
        self.assertTrue(self.baseline.is_file())
        self.assertIn(['add', '-f', 'nested repo/.github/coverage-baseline.json'], self.git_calls())

    def test_git_diff_no_change_does_not_commit_or_push(self):
        self.env['GIT_DIFF_EXIT'] = '0'
        self.add_report(report({'src/Service.cs': {1: 1}}))
        self.assertEqual(self.run_workflow()['changed'], 'true')
        self.assertFalse(any(call[0] in ('commit', 'fetch', 'rebase', 'push') for call in self.git_calls()))

    def test_unreadable_baseline_is_replaced_with_current_measurement(self):
        self.baseline.parent.mkdir()
        self.baseline.write_text('invalid json')
        self.add_report(report({'src/Service.cs': {1: 1}}))
        self.assertEqual(self.run_workflow()['changed'], 'true')
        self.assertEqual(json.loads(self.baseline.read_text())['totalLineCoverage'], 100)


if __name__ == '__main__':
    unittest.main()
