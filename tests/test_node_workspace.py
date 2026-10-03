"""Execute the actual reusable-workflow scripts against temporary consumer repos.

PyYAML parses the contract; actionlint separately validates GitHub's expressions.
These tests do not emulate checkout, setup-node caching, or artifact service APIs.
"""

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import yaml


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = yaml.safe_load((ROOT / '.github/workflows/job-node-workspace.yml').read_text(encoding='utf-8'))
# PyYAML's YAML 1.1 loader treats the GitHub YAML key `on` as True.
CONTRACT = WORKFLOW[True]['workflow_call']
JOB = WORKFLOW['jobs']['node-workspace']
STEPS = {step.get('id', step['name']): step for step in JOB['steps']}
DEFAULTS = {key: value['default'] for key, value in CONTRACT['inputs'].items()}
BASH = os.environ.get('BASH_EXE', 'bash')
CI_WORKFLOW = yaml.safe_load((ROOT / '.github/workflows/actions-ci.yml').read_text(encoding='utf-8'))
SMOKE_STEPS = {step['name']: step for step in CI_WORKFLOW['jobs']['verify-node-workspace-smoke']['steps']}


def read_outputs(path):
    """Read both GitHub output forms so newline/delimiter bugs fail locally."""
    values = {}
    lines = iter(path.read_text(encoding='utf-8').splitlines())
    for line in lines:
        if '<<' in line:
            name, delimiter = line.split('<<', 1)
            payload = []
            for item in lines:
                if item == delimiter:
                    break
                payload.append(item)
            else:
                raise AssertionError('Unterminated output')
            values[name] = '\n'.join(payload)
        else:
            name, value = line.split('=', 1)
            values[name] = value
    return values


class NodeWorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='node-workflow-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.repo = self.root / 'consumer'
        self.repo.mkdir()
        self.workdir = self.repo / 'app with spaces'
        self.workdir.mkdir()
        self.package = {'name': 'quality-fixture', 'version': '1.0.0', 'private': True,
                        'scripts': {'build': 'node -e "process.exit(0)"',
                                    'test': 'node --test fixture.test.cjs',
                                    'lint': 'node -e "process.exit(0)"',
                                    'typecheck': 'node -e "process.exit(0)"'}}
        (self.workdir / 'package.json').write_text(json.dumps(self.package), encoding='utf-8')
        (self.workdir / 'package-lock.json').write_text(json.dumps({
            'name': 'quality-fixture', 'version': '1.0.0', 'lockfileVersion': 3,
            'requires': True, 'packages': {'': {'name': 'quality-fixture', 'version': '1.0.0'}}}), encoding='utf-8')
        (self.workdir / 'fixture.test.cjs').write_text(
            "const {test} = require('node:test');\n"
            "test('CI environment reaches the test runner', () => {\n"
            "  require('node:assert/strict').equal(process.env.CI, 'true');\n"
            "});\n", encoding='utf-8')
        self.inputs = {**DEFAULTS, 'working-directory': 'app with spaces'}
        self.outputs = self.root / 'output.txt'
        self.summary = self.root / 'summary.md'
        self.environment = {**os.environ, 'GITHUB_WORKSPACE': self.repo.as_posix(),
                            'RUNNER_TEMP': self.root.as_posix(), 'GITHUB_OUTPUT': self.outputs.as_posix(),
                            'GITHUB_STEP_SUMMARY': self.summary.as_posix(), 'CI': 'true',
                            'GITHUB_RUN_ID': '42', 'GITHUB_RUN_ATTEMPT': '2',
                            'GITHUB_SHA': 'a' * 40, 'GITHUB_REPOSITORY': 'fixture/consumer',
                            'npm_config_cache': (self.root / 'npm-cache').as_posix()}

    def execute(self, step_id, *, inputs=None, steps=None, extra_env=None):
        self.outputs.write_text('', encoding='utf-8')
        step = STEPS[step_id]
        env = {**self.environment, 'NODE_INPUTS': json.dumps(inputs or self.inputs),
               'NODE_STEPS': json.dumps(steps or {}), **(extra_env or {})}
        if step['shell'] == 'python':
            args = [sys.executable, '-c', step['run']]
        else:
            # A script file avoids Windows/Git Bash -c quoting ambiguities.
            script = self.root / 'step.sh'
            script.write_text(step['run'], encoding='utf-8', newline='\n')
            args = [BASH, '--noprofile', '--norc', '-e', '-o', 'pipefail', script.as_posix()]
        result = subprocess.run(args, cwd=self.workdir, env=env, capture_output=True,
                                text=True, encoding='utf-8', timeout=60)
        return result, read_outputs(self.outputs)

    def collect(self, *, steps=None):
        result, outputs = self.execute('evidence', steps=steps)
        artifact = Path(outputs['directory'])
        report = json.loads((artifact / 'validation-results.json').read_text(encoding='utf-8'))
        return result, artifact, report

    def test_inherited_defaults_and_order_remain_compatible(self):
        inherited = {'runs-on': 'ubuntu-latest', 'working-directory': '.', 'node-version': '22',
                     'node-version-file': '', 'package-manager': 'npm',
                     'cache-dependency-path': 'package-lock.json', 'install-command': 'npm ci',
                     'build-command': 'npm run build', 'test-command': 'npm test',
                     'lint-command': 'npm run lint', 'run-build': True, 'run-test': True, 'run-lint': True}
        self.assertEqual({key: DEFAULTS[key] for key in inherited}, inherited)
        commands = [s['id'] for s in JOB['steps'] if 'NODE_COMMAND' in s.get('env', {})]
        self.assertEqual(commands, ['install', 'build', 'test', 'lint', 'typecheck',
                                    'browser-install', 'accessibility', 'e2e'])
        self.assertEqual(DEFAULTS['timeout-minutes'], 360)
        self.assertFalse(DEFAULTS['run-typecheck'])

    def test_read_only_pinned_contract_and_caller_owned_concurrency(self):
        self.assertEqual(WORKFLOW['permissions'], {'contents': 'read'})
        self.assertEqual(JOB['permissions'], {'contents': 'read'})
        self.assertNotIn('secrets', CONTRACT)
        self.assertNotIn('concurrency', JOB)  # Reusing caller's group can cancel the caller.
        self.assertNotIn('concurrency', WORKFLOW)
        for step in JOB['steps']:
            if 'uses' in step:
                self.assertRegex(step['uses'], r'@[0-9a-f]{40}$')
            self.assertNotIn('${{', step.get('run', ''))
            self.assertNotIn('continue-on-error', step)
        checkout = STEPS['Checkout repository']
        self.assertFalse(checkout['with']['persist-credentials'])
        self.assertEqual(JOB['steps'][0]['name'], 'Reject privileged PR context')

    def test_privileged_pr_context_fails_before_checkout(self):
        result, _ = self.execute('Reject privileged PR context', extra_env={'GITHUB_EVENT_NAME': 'pull_request_target'})
        self.assertNotEqual(result.returncode, 0)
        result, _ = self.execute('Reject privileged PR context', extra_env={'GITHUB_EVENT_NAME': 'pull_request'})
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_nested_workdir_and_multiline_cache_outputs(self):
        (self.workdir / '.nvmrc').write_text('22', encoding='utf-8')
        self.inputs.update({'node-version-file': '.nvmrc',
                            'cache-dependency-path': 'package-lock.json\npackages/*/package-lock.json'})
        result, outputs = self.execute('validate')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(outputs['working-directory'], self.workdir.resolve().as_posix())
        self.assertEqual(outputs['node-version-file'], 'app with spaces/.nvmrc')
        self.assertEqual(len(outputs['cache-dependency-path'].splitlines()), 2)
        self.assertTrue(all(p.startswith(self.workdir.resolve().as_posix()) for p in outputs['cache-dependency-path'].splitlines()))

    def test_reject_invalid_configuration(self):
        cases = [
            ('working-directory', '../escape'), ('working-directory', '/absolute'),
            ('working-directory', 'C:/absolute'), ('working-directory', 'app\\bad'),
            ('working-directory', 'app\ninjected=value'), ('package-manager', 'npm; echo bad'),
            ('package-manager-version', 'latest'), ('package-manager-version', '--foo'),
            ('artifact-retention-days', 0), ('artifact-retention-days', 91),
            ('artifact-retention-days', 1.5), ('timeout-minutes', 361),
            ('artifact-name', '../bad'), ('artifact-name', 'bad\nname'),
            ('coverage-path', '.'), ('coverage-path', '.git'), ('coverage-path', '**/*'),
            ('coverage-path', '../private'), ('test-results-path', '/private'),
            ('cache-dependency-path', '../../package-lock.json'), ('cache-dependency-path', ''),
            ('test-command', ' \n '), ('install-command', ''), ('e2e-command', ' '),
            ('node-version-file', 'missing'), ('browser-install-command', 'npm run browsers'),
        ]
        for name, value in cases:
            with self.subTest(name=name, value=value):
                result, outputs = self.execute('validate', inputs={**self.inputs, name: value})
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(outputs, {})

    def test_manager_versions_and_browser_setup_are_opt_in(self):
        for manager, version in [('npm', '10.9.2'), ('pnpm', '10.11.0'), ('yarn', '1.22.22')]:
            result, _ = self.execute('validate', inputs={**self.inputs, 'package-manager': manager,
                                                        'package-manager-version': version})
            self.assertEqual(result.returncode, 0, result.stderr)
        result, _ = self.execute('validate', inputs={**self.inputs, 'package-manager': 'yarn',
                                                    'package-manager-version': '4.0.0'})
        self.assertNotEqual(result.returncode, 0)
        order = list(STEPS)
        self.assertLess(order.index('Provision package manager locally'), order.index('Restore package manager cache'))

    def test_monorepo_paths_can_resolve_to_checkout_root(self):
        (self.repo / '.nvmrc').write_text('22', encoding='utf-8')
        (self.repo / 'package-lock.json').write_text('{}', encoding='utf-8')
        self.inputs.update({'node-version-file': '../.nvmrc',
                            'cache-dependency-path': '../package-lock.json\n../apps/*/package-lock.json'})
        result, outputs = self.execute('validate')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(outputs['node-version-file'], '.nvmrc')
        self.assertEqual(outputs['cache-dependency-path'].splitlines()[0],
                         (self.repo / 'package-lock.json').resolve().as_posix())

    def test_setup_node_can_read_validated_version_file_from_checkout(self):
        (self.repo / '.nvmrc').write_text('22', encoding='utf-8')
        result, outputs = self.execute('validate', inputs={**self.inputs, 'node-version-file': '../.nvmrc'})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(Path(outputs['node-version-file']).is_absolute())
        # Pinned setup-node uses path.join(GITHUB_WORKSPACE, versionFileInput).
        # Passing our former absolute output doubled the checkout prefix on Linux.
        result = subprocess.run([
            'node', '-e',
            "const fs = require('node:fs'); const path = require('node:path'); "
            "process.stdout.write(fs.readFileSync(path.join(process.argv[1], process.argv[2]), 'utf8'));",
            self.repo.resolve().as_posix(), outputs['node-version-file'],
        ], capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, '22')

    def test_parent_paths_cannot_escape_checkout(self):
        for key in ('node-version-file', 'cache-dependency-path'):
            with self.subTest(key=key):
                result, _ = self.execute('validate', inputs={**self.inputs, key: '../../outside'})
                self.assertNotEqual(result.returncode, 0)

    def test_monorepo_version_symlink_cannot_escape_checkout(self):
        outside = self.root / 'outside-version'
        outside.write_text('22', encoding='utf-8')
        self.make_symlink(self.repo / '.nvmrc', outside)
        result, _ = self.execute('validate', inputs={**self.inputs, 'node-version-file': '../.nvmrc'})
        self.assertNotEqual(result.returncode, 0)

    def test_default_npm_consumer_executes_install_build_test_lint(self):
        # No registry dependencies, credentials, or network needed by this fixture.
        for name in ('install', 'build', 'test', 'lint', 'typecheck'):
            with self.subTest(name=name):
                result, _ = self.execute(name, extra_env={'NODE_COMMAND': self.inputs[name + '-command'],
                                                         'npm_config_offline': 'true'})
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_command_failure_and_pipeline_failure_remain_fatal(self):
        for name in ('test', 'typecheck', 'accessibility', 'e2e'):
            for command in ('exit 17', 'false | cat', 'false\nprintf should-not-run'):
                with self.subTest(name=name, command=command):
                    result, _ = self.execute(name, extra_env={'NODE_COMMAND': command})
                    self.assertEqual(result.returncode, 17 if command == 'exit 17' else 1, result.stderr)
                    self.assertNotIn('should-not-run', result.stdout)

    def test_command_quoting_and_multiline_scripts(self):
        command = "printf '%s\\n' 'space quote \" and dollar $ literal'\nprintf '%s' second-line"
        result, _ = self.execute('test', extra_env={'NODE_COMMAND': command})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, 'space quote " and dollar $ literal\nsecond-line')

    def test_success_failure_disabled_and_blocked_statuses_are_distinct(self):
        self.inputs.update({'run-lint': False, 'e2e-command': 'npm run e2e'})
        result, _, report = self.collect(steps={'test': {'outcome': 'failure'}, 'build': {'outcome': 'success'}})
        self.assertEqual(result.returncode, 0, result.stderr)
        checks = report['checks']
        self.assertEqual(checks['build']['outcome'], 'success')
        self.assertEqual(checks['test']['outcome'], 'failure')
        self.assertEqual(checks['lint'], {'requested': False, 'outcome': 'skipped', 'reason': 'not requested'})
        self.assertEqual(checks['e2e']['outcome'], 'skipped')
        self.assertTrue(checks['e2e']['requested'])
        self.assertIn('blocked', checks['e2e']['reason'])

    def test_reports_survive_test_failure_and_exclude_hidden_files(self):
        self.inputs.update({'coverage-path': 'coverage', 'test-results-path': 'reports/junit.xml'})
        (self.workdir / 'coverage').mkdir()
        (self.workdir / 'coverage/lcov.info').write_text('TN:fixture\n', encoding='utf-8')
        (self.workdir / 'coverage/.env').write_text('never upload', encoding='utf-8')
        (self.workdir / 'reports').mkdir()
        (self.workdir / 'reports/junit.xml').write_text('<testsuites/>', encoding='utf-8')
        result, artifact, report = self.collect(steps={'validate': {'outcome': 'success'}, 'test': {'outcome': 'failure'}})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(report['checks']['test']['outcome'], 'failure')
        self.assertTrue((artifact / 'coverage/lcov.info').exists())
        self.assertTrue((artifact / 'test-results/junit.xml').exists())
        self.assertFalse((artifact / 'coverage/.env').exists())

    def test_missing_or_empty_requested_reports_fail_even_after_green_test(self):
        self.inputs['coverage-path'] = 'coverage'
        for create_directory in (False, True):
            if create_directory:
                (self.workdir / 'coverage').mkdir()
            result, _, report = self.collect(steps={'validate': {'outcome': 'success'}, 'test': {'outcome': 'success'}})
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('missing or empty', report['evidenceErrors'][0])

    def test_zero_byte_report_is_not_evidence(self):
        (self.workdir / 'lcov.info').write_text('', encoding='utf-8')
        self.inputs['coverage-path'] = 'lcov.info'
        result, _, report = self.collect(steps={'validate': {'outcome': 'success'}})
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('missing or empty', report['evidenceErrors'][0])

    def test_cancelled_command_is_not_reported_as_failure_or_pass(self):
        result, _, report = self.collect(steps={'test': {'outcome': 'cancelled'}})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(report['checks']['test']['outcome'], 'cancelled')

    def test_coverage_cannot_be_requested_when_tests_are_disabled(self):
        self.inputs.update({'coverage-path': 'coverage', 'run-test': False})
        result, _ = self.execute('validate')
        self.assertNotEqual(result.returncode, 0)

    def make_symlink(self, link, target, directory=False):
        try:
            link.symlink_to(target, target_is_directory=directory)
        except OSError as error:
            self.skipTest(f'OS does not allow test symlinks: {error}')

    def test_workdir_symlink_escape_is_rejected(self):
        outside = self.root / 'outside'
        outside.mkdir()
        (outside / 'package.json').write_text('{}', encoding='utf-8')
        self.make_symlink(self.repo / 'escaped', outside, True)
        result, _ = self.execute('validate', inputs={**self.inputs, 'working-directory': 'escaped'})
        self.assertNotEqual(result.returncode, 0)

    def test_report_symlink_escape_is_not_uploaded(self):
        (self.workdir / 'coverage').mkdir()
        secret = self.root / 'private.txt'
        secret.write_text('outside-workspace-sentinel', encoding='utf-8')
        self.make_symlink(self.workdir / 'coverage/leak.txt', secret)
        self.inputs['coverage-path'] = 'coverage'
        result, artifact, report = self.collect(steps={'validate': {'outcome': 'success'}})
        self.assertNotEqual(result.returncode, 0)
        self.assertTrue(report['evidenceErrors'])
        self.assertFalse((artifact / 'coverage/leak.txt').exists())

    def test_optional_checks_keep_success_gating_and_evidence_runs_always(self):
        for name in ('build', 'test', 'lint', 'typecheck'):
            self.assertEqual(STEPS[name]['if'], '${{ inputs.run-' + name + ' }}')
        for name in ('browser-install', 'accessibility', 'e2e'):
            self.assertEqual(STEPS[name]['if'], "${{ inputs." + name + "-command != '' }}")
        self.assertEqual(STEPS['evidence']['if'], '${{ always() }}')
        upload = STEPS['upload']
        self.assertIn('always()', upload['if'])
        self.assertEqual(upload['with']['if-no-files-found'], 'error')
        self.assertFalse(upload['with']['include-hidden-files'])
        self.assertFalse(DEFAULTS['upload-summary-artifact'])
        self.assertIn("(inputs.upload-summary-artifact || inputs.coverage-path != '' || inputs.test-results-path != '')",
                      upload['if'])

    def test_hosted_smoke_calls_this_revision_with_default_and_pinned_managers(self):
        profiles = ('node-workspace-smoke', 'node-workspace-smoke-pinned')
        for job_id, manager_version in zip(profiles, ('', '10.9.2')):
            smoke = CI_WORKFLOW['jobs'][job_id]
            self.assertEqual(smoke['uses'], './.github/workflows/job-node-workspace.yml')
            self.assertEqual(smoke['with'].get('package-manager-version', ''), manager_version)
            self.assertEqual(smoke['with']['cache-dependency-path'], '../../package-lock.json')
            for command in ('install-command', 'build-command', 'test-command', 'lint-command'):
                self.assertNotIn(command, smoke['with'])
        verify = CI_WORKFLOW['jobs']['verify-node-workspace-smoke']
        self.assertEqual(verify['needs'], list(profiles))
        download = next(step for step in verify['steps'] if step.get('uses', '').startswith('actions/download-artifact@'))
        self.assertRegex(download['uses'], r'@[0-9a-f]{40}$')
        self.assertEqual(download['with']['artifact-ids'], '${{ steps.producers.outputs.artifact-ids }}')
        self.assertNotIn('pattern', download['with'])
        producers = SMOKE_STEPS['Validate producer artifact IDs']['env']['PRODUCER_ARTIFACT_IDS']
        for job_id in profiles:
            self.assertIn('needs.' + job_id + '.outputs.evidence-artifact-id', producers)
        self.assertEqual(CONTRACT['outputs']['evidence-artifact-id']['value'],
                         '${{ jobs.node-workspace.outputs.evidence-artifact-id }}')
        self.assertEqual(JOB['outputs']['evidence-artifact-id'], '${{ steps.upload.outputs.artifact-id }}')

    def execute_smoke_verifier(self, step_name='Verify uploaded outcomes, test results, and runtime versions', **env):
        self.outputs.write_text('', encoding='utf-8')
        return subprocess.run([sys.executable, '-c', SMOKE_STEPS[step_name]['run']],
                              cwd=self.root, env={**self.environment, **env},
                              capture_output=True, text=True, timeout=30)

    def smoke_artifacts(self, attempts=(1, 1)):
        """Build reports with the real collector, then emulate downloaded directories."""
        downloaded = self.root / 'node-smoke-evidence'
        downloaded.mkdir()
        artifacts = []
        for profile, attempt in zip(('npm-defaults', 'npm-pinned'), attempts):
            previous_attempt = self.environment['GITHUB_RUN_ATTEMPT']
            self.environment['GITHUB_RUN_ATTEMPT'] = str(attempt)
            result, artifact, _ = self.collect(steps={name: {'outcome': 'success'}
                                                     for name in ('install', 'build', 'test', 'lint')})
            self.environment['GITHUB_RUN_ATTEMPT'] = previous_attempt
            self.assertEqual(result.returncode, 0, result.stderr)
            target = downloaded / f'node-smoke-{profile}-42-{attempt}-{artifact.name}'
            artifact.rename(target)
            (target / 'test-results').mkdir()
            (target / 'test-results/runtime.json').write_text(json.dumps({
                'node': '22.23.3', 'npm': '10.9.2' if profile == 'npm-pinned' else '10.9.9'}), encoding='utf-8')
            (target / 'test-results/junit.xml').write_text(
                '<testsuites><testsuite><testcase name="executed"/></testsuite></testsuites>', encoding='utf-8')
            artifacts.append(target)
        return artifacts

    def test_verifier_only_rerun_accepts_original_producer_attempts(self):
        self.smoke_artifacts((1, 1))
        result = self.execute_smoke_verifier()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.count('producer attempt 1, verifier attempt 2'), 2)

    def test_partial_rerun_accepts_mixed_producer_attempts(self):
        self.smoke_artifacts((1, 2))
        result = self.execute_smoke_verifier()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('producer attempt 1, verifier attempt 2', result.stdout)
        self.assertIn('producer attempt 2, verifier attempt 2', result.stdout)

    def test_verifier_rejects_ambiguous_profile_artifacts(self):
        artifacts = self.smoke_artifacts()
        artifacts[1].rename(artifacts[1].with_name(artifacts[1].name.replace('npm-pinned', 'npm-defaults')))
        result = self.execute_smoke_verifier()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('expected one uploaded artifact', result.stderr)

    def test_verifier_rejects_wrong_revision_or_run_provenance(self):
        artifact = self.smoke_artifacts()[0]
        path = artifact / 'validation-results.json'
        original = json.loads(path.read_text(encoding='utf-8'))
        for field, value in (('runId', '43'), ('runAttempt', '2'), ('sha', 'b' * 40), ('repository', 'wrong/repo')):
            with self.subTest(field=field):
                report = json.loads(json.dumps(original))
                report['provenance'][field] = value
                path.write_text(json.dumps(report), encoding='utf-8')
                result = self.execute_smoke_verifier()
                self.assertNotEqual(result.returncode, 0)
                self.assertIn('provenance does not match', result.stderr)

    def test_verifier_rejects_future_producer_attempt(self):
        self.smoke_artifacts((1, 3))
        result = self.execute_smoke_verifier()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('future attempt', result.stderr)

    def test_download_requires_two_distinct_valid_producer_ids(self):
        step = 'Validate producer artifact IDs'
        for value in ('', '1,', ',2', '1,1', '1,2,3', '1,garbage', '1,2\nother=value'):
            with self.subTest(value=value):
                result = self.execute_smoke_verifier(step, PRODUCER_ARTIFACT_IDS=value)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(read_outputs(self.outputs), {})
        result = self.execute_smoke_verifier(step, PRODUCER_ARTIFACT_IDS='123,456')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(read_outputs(self.outputs), {'artifact-ids': '123,456'})

    def test_repeated_default_calls_have_distinct_artifact_ids(self):
        first, first_outputs = self.execute('evidence')
        second, second_outputs = self.execute('evidence')
        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertNotEqual(first_outputs['artifact-id'], second_outputs['artifact-id'])
        self.assertIn('steps.evidence.outputs.artifact-id', STEPS['upload']['with']['name'])

    def test_existing_security_audit_surfaces_unpatched_findings(self):
        audit = yaml.safe_load((ROOT / '.github/workflows/job-node-security-audit.yml').read_text(encoding='utf-8'))
        audit_steps = audit['jobs']['node-security-audit']['steps']
        command = next(step for step in audit_steps if step['name'] == 'Run npm audit')['run']
        # Exercise the existing audit boundary with an unpatched high finding;
        # there is no registry/network request and no suppression configuration.
        fixture = self.workdir / 'audit-fixture.cjs'
        fixture.write_text('console.log(JSON.stringify({vulnerabilities:{example:{severity:"high",'
                           'fixAvailable:false}}})); process.exit(1);', encoding='utf-8')
        script = self.root / 'audit.sh'
        script.write_text(command.replace('${{ inputs.audit-command }}', 'node audit-fixture.cjs'),
                          encoding='utf-8', newline='\n')
        result = subprocess.run([BASH, '--noprofile', '--norc', '-e', '-o', 'pipefail', script.as_posix()],
                                cwd=self.workdir, env=self.environment, capture_output=True,
                                text=True, encoding='utf-8', timeout=60)
        self.assertEqual(result.returncode, 1, result.stderr)
        report = json.loads((self.workdir / 'security-reports/node-audit.json').read_text(encoding='utf-8'))
        self.assertFalse(report['vulnerabilities']['example']['fixAvailable'])
        upload = next(step for step in audit_steps if step['name'] == 'Upload security report')
        self.assertEqual(upload['if'], 'always()')


if __name__ == '__main__':
    unittest.main()
