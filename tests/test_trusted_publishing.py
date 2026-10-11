"""Exercise release artifact rejection and the caller-owned OIDC contract."""
import importlib.util
import os
import re
import subprocess
import tempfile
from pathlib import Path
import unittest
from zipfile import ZipFile
import yaml

ROOT = Path(__file__).resolve().parents[1]
ACTION = ROOT / '.github/actions/nuget/trusted-publish'
spec = importlib.util.spec_from_file_location('validate_packages', ACTION / 'validate_packages.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class TrustedPublishingTests(unittest.TestCase):
    def test_ref_guard_rejects_unreviewed_and_nonrelease_refs(self):
        action = yaml.safe_load((ACTION / 'action.yml').read_text())
        script = action['runs']['steps'][0]['run']
        bash = 'C:/Program Files/Git/bin/bash.exe' if os.name == 'nt' else 'bash'
        with tempfile.TemporaryDirectory() as temp:
            def git(*args):
                return subprocess.run(['git', *args], cwd=temp, check=True, capture_output=True)
            git('init', '-b', 'main')
            git('-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid', 'commit', '--allow-empty', '-m', 'fixture')
            git('update-ref', 'refs/remotes/origin/main', 'HEAD')
            for event, ref, accepted in [('workflow_dispatch', 'refs/heads/main', True), ('workflow_dispatch', 'refs/heads/topic', False), ('push', 'refs/tags/v1.0.0', True), ('push', 'refs/heads/main', False), ('pull_request', 'refs/pull/1/merge', False)]:
                with self.subTest(event=event, ref=ref):
                    result = subprocess.run([bash, '-c', script], cwd=temp, env={**os.environ, 'GITHUB_EVENT_NAME': event, 'GITHUB_REF': ref}, capture_output=True)
                    self.assertEqual(result.returncode == 0, accepted)
            git('-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid', 'commit', '--allow-empty', '-m', 'unreviewed')
            result = subprocess.run([bash, '-c', script], cwd=temp, env={**os.environ, 'GITHUB_EVENT_NAME': 'push', 'GITHUB_REF': 'refs/tags/v1.0.0'}, capture_output=True)
            self.assertNotEqual(result.returncode, 0)

    def test_secret_policy_exception_is_exact(self):
        policy = (ROOT / '.github/workflows/actions-ci.yml').read_text()
        exception = re.search(r"TRUSTED_OUTPUT='([^']+)'", policy).group(1)
        line = '.github/actions/nuget/trusted-publish/action.yml:54:        EPHEMERAL_NUGET_KEY: ${{ steps.nuget-login.outputs.NUGET_API_KEY }}'
        self.assertIsNotNone(re.fullmatch(exception, line))
        for altered in [line.replace('steps.nuget-login.outputs', 'secrets'), line.replace('trusted-publish/', 'other/'), line + ' extra']:
            self.assertIsNone(re.fullmatch(exception, altered))

    def test_complete_packages_and_rejections(self):
        with tempfile.TemporaryDirectory() as temp:
            def package(filename, package_id='Example', version='1.0.0'):
                with ZipFile(Path(temp) / filename, 'w') as archive:
                    archive.writestr('Example.nuspec', f'<package xmlns="http://schemas.microsoft.com/packaging/2013/05/nuspec.xsd"><metadata><id>{package_id}</id><version>{version}</version></metadata></package>')
            package('Example.1.0.0.nupkg')
            module.validate(temp, '1.0.0', 'Example')
            for version, ids in [('2.0.0', 'Example'), ('1.0.0', 'Other'), ('1.0.0', 'Example\nMissing'), ('', 'Example'), ('1.0.0', '')]:
                with self.subTest(version=version, ids=ids), self.assertRaises(ValueError):
                    module.validate(temp, version, ids)
            package('Duplicate.nupkg')
            with self.assertRaisesRegex(ValueError, 'Duplicate'):
                module.validate(temp, '1.0.0', 'Example')

    def test_missing_artifact_fails_closed(self):
        with tempfile.TemporaryDirectory() as temp, self.assertRaises(ValueError):
            module.validate(temp, '1.0.0', 'Example')

    def test_no_credentials_escape_and_verification_cannot_push(self):
        action = yaml.safe_load((ACTION / 'action.yml').read_text())
        self.assertNotIn('outputs', action)
        steps = action['runs']['steps']
        login = next(step for step in steps if step.get('id') == 'nuget-login')
        self.assertEqual(login['uses'], 'NuGet/login@8d196754b4036150537f80ac539e15c2f1028841')
        push = next(step for step in steps if 'EPHEMERAL_NUGET_KEY' in step.get('env', {}))
        self.assertEqual(push['if'], "inputs.verify-only != 'true'")
        self.assertNotIn('skip-duplicate', push['run'])
        self.assertLess(steps.index(login), steps.index(push))
        self.assertIn('git merge-base --is-ancestor HEAD origin/main', steps[0]['run'])
        self.assertIn('refs/heads/main', steps[0]['run'])

    def test_pack_only_preserves_existing_publish_contract(self):
        workflow = yaml.safe_load((ROOT / '.github/workflows/release.yml').read_text())
        self.assertEqual(workflow['permissions'], {'contents': 'read'})
        for name, release_job in workflow['jobs'].items():
            if name not in ('build-and-scan-container', 'github-release'):
                self.assertEqual(release_job.get('permissions', workflow['permissions']), {'contents': 'read'})
        self.assertEqual(workflow['jobs']['build-and-scan-container']['permissions'], {
            'contents': 'read', 'packages': 'write', 'id-token': 'write', 'security-events': 'write'})
        inputs = workflow.get('on', workflow.get(True))['workflow_call']['inputs']
        self.assertFalse(inputs['enable-nuget-pack']['default'])
        self.assertFalse(inputs['enable-nuget-publish']['default'])
        job = workflow['jobs']['publish-nuget']
        self.assertEqual(job['needs'], ['build-and-test', 'security-compliance'])
        push = next(step for step in job['steps'] if step['name'] == 'Push to NuGet')
        self.assertEqual(push['if'], '${{ inputs.enable-nuget-publish }}')
        self.assertEqual(job['steps'][-1]['with']['if-no-files-found'], 'error')


if __name__ == '__main__':
    unittest.main()
