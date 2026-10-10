"""Exercise the shipped pre-authentication guard and build shell without cloud access."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
import yaml

WORKFLOW = yaml.safe_load((Path(__file__).parents[1] / '.github/workflows/job-deploy-app-service.yml').read_text())
STEPS = WORKFLOW['jobs']['deploy']['steps']
GUARD = next(s['run'] for s in STEPS if s.get('name') == 'Require reviewed setup and protected environment')
BUILD = next(s['run'] for s in STEPS if s.get('id') == 'build')


class AppServiceWorkflowTests(unittest.TestCase):
    def execute(self, script, overrides=None):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'scripts').mkdir()
            (root / 'scripts/deploy_app_service.py').touch()
            for name, body in {
                'gh': 'printf "%s\\n" "$REVIEWERS"',
                'az': 'if [ "$1 $2" = "acr repository" ]; then printf "sha256:%064d\\n" 0; fi',
                'docker': 'printf "%s\\n" "$*" >> "$CALLS"; if [ "$1" = run ] && [ "${SCAN_FAIL:-0}" = 1 ]; then exit 1; fi',
            }.items():
                tool = root / name
                tool.write_text('#!/bin/bash\nset -eu\n' + body + '\n')
                tool.chmod(0o755)
            env = {**os.environ, 'PATH': str(root) + os.pathsep + os.environ['PATH'],
                   'ENABLED': 'true', 'APP': 'app-hd-identity-dev', 'CLIENT': 'client',
                   'TENANT': 'tenant', 'SUBSCRIPTION': 'subscription', 'REGISTRY': 'acrhdshareddev',
                   'IMAGE_NAME': 'honeydrunk-identity-api', 'OPERATION': 'deploy',
                   'ROLLBACK_IMAGE': '', 'ROLLBACK_RELEASE': '', 'REVIEWERS': '1',
                   'GITHUB_REPOSITORY': 'example/consumer', 'GITHUB_SHA': 'a' * 40,
                   'GITHUB_RUN_ID': '123', 'GITHUB_RUN_ATTEMPT': '1',
                   'GITHUB_OUTPUT': str(root / 'output'), 'CALLS': str(root / 'calls'), **(overrides or {})}
            result = subprocess.run(['bash', '-c', script], cwd=root, env=env, capture_output=True, text=True)
            output = (root / 'output').read_text() if (root / 'output').exists() else ''
            calls = (root / 'calls').read_text() if (root / 'calls').exists() else ''
            return result, output, calls

    def test_guard_requires_approval_reviewers_and_consistent_operation(self):
        self.assertEqual(self.execute(GUARD)[0].returncode, 0)
        for invalid in [{'ENABLED': 'false'}, {'REVIEWERS': ''}, {'REVIEWERS': '0'},
                        {'CLIENT': ''}, {'OPERATION': 'prod'}, {'OPERATION': 'rollback'},
                        {'ROLLBACK_IMAGE': 'unexpected'}, {'REGISTRY': 'bad; command'},
                        {'IMAGE_NAME': '../outside'}]:
            with self.subTest(invalid=invalid):
                self.assertNotEqual(self.execute(GUARD, invalid)[0].returncode, 0)
        self.assertEqual(self.execute(GUARD, {'OPERATION': 'rollback', 'ROLLBACK_IMAGE': 'retained',
                                            'ROLLBACK_RELEASE': 'known'})[0].returncode, 0)

    def test_build_bakes_unique_release_and_outputs_immutable_digest(self):
        result, output, calls = self.execute(BUILD)
        self.assertEqual(result.returncode, 0, result.stderr)
        release = 'dev-' + 'a' * 40 + '-123-1'
        self.assertIn('RELEASE_ID=' + release, calls)
        self.assertLess(calls.index('aquasec/trivy:0.69.3'), calls.index('push '))
        self.assertIn('--severity HIGH,CRITICAL --exit-code 1', calls)
        self.assertIn('push acrhdshareddev.azurecr.io/honeydrunk-identity-api:' + release, calls)
        self.assertEqual(output, 'image=acrhdshareddev.azurecr.io/honeydrunk-identity-api@sha256:' + '0' * 64 + '\nrelease=' + release + '\n')

    def test_scanner_failure_prevents_registry_push(self):
        result, output, calls = self.execute(BUILD, {'SCAN_FAIL': '1'})
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn('push ', calls)
        self.assertEqual(output, '')

    def test_scope_and_verifier_are_fail_closed(self):
        job = WORKFLOW['jobs']['deploy']
        self.assertEqual(job['environment'], 'dev')
        self.assertEqual(job['if'], "github.ref == 'refs/heads/main'")
        names = [s.get('name', s.get('uses', '')) for s in STEPS]
        self.assertLess(names.index('Require reviewed setup and protected environment'), names.index('azure/login@v2'))
        verify = next(s for s in STEPS if s.get('name', '').startswith('Update serving image'))
        self.assertNotIn('continue-on-error', verify)
        self.assertIn('scripts/deploy_app_service.py', verify['run'])
        self.assertNotIn('slot', verify['run'])
        self.assertNotIn('sql', verify['run'])


if __name__ == '__main__':
    unittest.main()
