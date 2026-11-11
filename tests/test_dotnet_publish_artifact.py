"""Execute publish/ZIP transport boundaries without cloud credentials or services."""
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import tempfile
import unittest
import zipfile

import yaml

ROOT = Path(__file__).parents[1]
PUBLISH = yaml.safe_load((ROOT / '.github/workflows/job-dotnet-publish-artifact.yml').read_text())
DEPLOY = yaml.safe_load((ROOT / '.github/workflows/job-deploy-function.yml').read_text())
STEPS = PUBLISH['jobs']['publish']['steps']
DEPLOY_STEPS = DEPLOY['jobs']['deploy']['steps']


def step(name, steps=STEPS):
    return next(s for s in steps if s.get('name') == name)


def inputs(workflow):
    return workflow.get('on', workflow.get(True))['workflow_call']['inputs']


class DotnetPublishArtifactTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.publish = self.root / 'nested dir/publish'
        self.publish.mkdir(parents=True)
        (self.publish / 'host.json').write_text('{}')
        (self.publish / '.azurefunctions').mkdir()
        (self.publish / '.azurefunctions/extensions.json').write_text('{}')
        (self.publish / 'worker.config.json').write_text('{}')
        self.apphost = self.publish / 'Example.Functions'
        self.apphost.write_text('#!/bin/sh\nexit 0\n')
        self.apphost.chmod(0o755)
        self.output = self.root / 'output'
        self.bin = self.root / 'bin'
        self.bin.mkdir()
        tool = self.bin / 'dotnet'
        tool.write_text('#!/usr/bin/env python3\nimport json, os, sys\n'
                        'open(os.environ["CALLS"], "w").write(json.dumps(sys.argv[1:]))\n'
                        'sys.exit(int(os.environ.get("PUBLISH_EXIT", "0")))\n')
        tool.chmod(0o755)
        self.env = {**os.environ, 'GITHUB_WORKSPACE': str(self.root),
                    'GITHUB_OUTPUT': str(self.output), 'RUNNER_OS_NAME': 'Linux',
                    'RUNTIME_IDENTIFIER': '', 'SELF_CONTAINED': 'false', 'PACKAGE_FILE': '',
                    'NO_BUILD': 'true', 'WORKING_DIR': 'nested dir', 'PUBLISH_OUTPUT': './publish',
                    'PUBLISH_PROJECT': 'src/Example Functions.csproj', 'CONFIGURATION': 'Release',
                    'PACKAGE_PATH': str(self.publish), 'PATH': str(self.bin) + os.pathsep + os.environ['PATH'],
                    'CALLS': str(self.root / 'calls')}

    def run_step(self, name, overrides=None, steps=STEPS):
        return subprocess.run(['bash', '-c', step(name, steps)['run']], cwd=self.root,
                              env={**self.env, **(overrides or {})}, text=True, capture_output=True)

    def scd(self):
        return {'RUNTIME_IDENTIFIER': 'linux-x64', 'SELF_CONTAINED': 'true',
                'PACKAGE_FILE': 'functions.zip', 'NO_BUILD': 'false'}

    def test_existing_callers_keep_default_contract(self):
        values = inputs(PUBLISH)
        self.assertEqual(values['runtime-identifier']['default'], '')
        self.assertFalse(values['self-contained']['default'])
        self.assertEqual(values['package-file']['default'], '')
        self.assertTrue(values['no-build']['default'])
        self.assertEqual(inputs(DEPLOY)['package-file']['default'], '')
        self.assertEqual(self.run_step('Validate publish options').returncode, 0)
        result = self.run_step('Publish artifact')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads((self.root / 'calls').read_text()),
                         ['publish', 'src/Example Functions.csproj', '--configuration', 'Release',
                          '--output', './publish', '--no-build'])
        result = self.run_step('Resolve artifact path')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.output.read_text(), 'path=nested dir/publish\n')
        self.output.unlink()
        result = self.run_step('Resolve deployment package', steps=DEPLOY_STEPS)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.output.read_text(), f'path={self.publish}\n')

    def test_self_contained_publish_arguments_are_exact_and_quoted(self):
        result = self.run_step('Validate publish options', self.scd())
        self.assertEqual(result.returncode, 0, result.stderr)
        result = self.run_step('Publish artifact', self.scd())
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads((self.root / 'calls').read_text()),
                         ['publish', 'src/Example Functions.csproj', '--configuration', 'Release',
                          '--output', './publish', '--runtime', 'linux-x64', '--self-contained', 'true'])

    def test_framework_dependent_rid_does_not_force_self_contained(self):
        options = {'RUNTIME_IDENTIFIER': 'linux-x64', 'NO_BUILD': 'false'}
        self.assertEqual(self.run_step('Validate publish options', options).returncode, 0)
        self.assertEqual(self.run_step('Publish artifact', options).returncode, 0)
        args = json.loads((self.root / 'calls').read_text())
        self.assertNotIn('--self-contained', args)
        self.assertIn('linux-x64', args)

    def test_invalid_options_fail_before_sdk_restore_or_publish(self):
        for options in [{'SELF_CONTAINED': 'true'},
                        {**self.scd(), 'NO_BUILD': 'true'},
                        {**self.scd(), 'PACKAGE_FILE': ''},
                        {**self.scd(), 'RUNTIME_IDENTIFIER': 'win-x64'},
                        {**self.scd(), 'RUNNER_OS_NAME': 'Windows'},
                        {'RUNTIME_IDENTIFIER': 'linux-x64'},
                        {'RUNTIME_IDENTIFIER': '--option', 'NO_BUILD': 'false'}]:
            with self.subTest(options=options):
                self.assertNotEqual(self.run_step('Validate publish options', options).returncode, 0)
        names = [s.get('name') for s in STEPS]
        self.assertLess(names.index('Validate publish options'), names.index('Setup .NET SDK'))

    def test_archive_basename_rejects_escape_injection_and_newlines(self):
        for name in ['../outside.zip', '/tmp/out.zip', 'sub/out.zip', '-out.zip', 'out.tar',
                     'out.zip\npath=other', 'out$(touch marker).zip', r'sub\out.zip', 'out*.zip']:
            with self.subTest(name=name):
                self.assertNotEqual(self.run_step('Validate publish options', {'PACKAGE_FILE': name}).returncode, 0)
                self.assertNotEqual(self.run_step('Resolve deployment package', {'PACKAGE_FILE': name}, DEPLOY_STEPS).returncode, 0)
                self.assertFalse(self.output.exists())

    def test_zip_round_trip_preserves_root_hidden_files_executable_and_bytes(self):
        result = self.run_step('Resolve artifact path', self.scd())
        self.assertEqual(result.returncode, 0, result.stderr)
        archive = self.root / self.output.read_text().strip().removeprefix('path=')
        self.assertFalse(archive.is_relative_to(self.publish))
        before = hashlib.sha256(archive.read_bytes()).hexdigest()
        # upload/download-artifact normalizes the outer file to 0644, not bytes inside it.
        downloaded = self.publish / 'functions.zip'
        downloaded.write_bytes(archive.read_bytes())
        downloaded.chmod(0o644)
        self.output.unlink()
        result = self.run_step('Resolve deployment package', self.scd(), DEPLOY_STEPS)
        self.assertEqual(result.returncode, 0, result.stderr)
        selected = Path(self.output.read_text().strip().removeprefix('path='))
        self.assertEqual(before, hashlib.sha256(selected.read_bytes()).hexdigest())
        with zipfile.ZipFile(selected) as package:
            self.assertIn('host.json', package.namelist())
            self.assertIn('.azurefunctions/extensions.json', package.namelist())
            self.assertIn('worker.config.json', package.namelist())
            self.assertEqual(stat.S_IMODE(package.getinfo('Example.Functions').external_attr >> 16), 0o755)
            self.assertFalse(any(n.endswith('.zip') for n in package.namelist()))
        extracted = self.root / 'extracted'
        subprocess.run(['unzip', '-q', str(selected), '-d', str(extracted)], check=True)
        self.assertEqual(stat.S_IMODE((extracted / 'Example.Functions').stat().st_mode), 0o755)
        self.assertEqual(subprocess.run([str(extracted / 'Example.Functions')]).returncode, 0)

    def test_missing_corrupt_or_symlink_zip_stops_before_azure_login(self):
        for kind in ['missing', 'corrupt', 'symlink']:
            with self.subTest(kind=kind):
                package = self.publish / 'functions.zip'
                if kind == 'corrupt':
                    package.write_text('not a zip')
                elif kind == 'symlink':
                    package.unlink()
                    package.symlink_to(self.apphost)
                result = self.run_step('Resolve deployment package', self.scd(), DEPLOY_STEPS)
                self.assertNotEqual(result.returncode, 0)
                self.assertFalse(self.output.exists())
        names = [s.get('name') for s in DEPLOY_STEPS]
        self.assertLess(names.index('Resolve deployment package'), names.index('Azure Login'))

    def test_publish_and_archive_failures_propagate(self):
        self.assertEqual(self.run_step('Publish artifact', {'PUBLISH_EXIT': '42'}).returncode, 42)
        result = self.run_step('Resolve artifact path', {**self.scd(), 'PUBLISH_OUTPUT': 'absent'})
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(self.output.exists())

    def test_config_zip_receives_exact_archive_without_repacking(self):
        result = self.run_step('Resolve artifact path', self.scd())
        self.assertEqual(result.returncode, 0, result.stderr)
        archive = self.root / self.output.read_text().strip().removeprefix('path=')
        before = hashlib.sha256(archive.read_bytes()).hexdigest()
        az = self.bin / 'az'
        az.write_text('#!/usr/bin/env python3\nimport json, os, sys\n'
                      'open(os.environ["CALLS"], "w").write(json.dumps(sys.argv[1:]))\n')
        az.chmod(0o755)
        composite = yaml.safe_load((ROOT / '.github/actions/azure/deploy-function/action.yml').read_text())
        deploy = composite['runs']['steps'][0]['run']
        result = subprocess.run(['bash', '-c', deploy], cwd=self.root,
                                env={**self.env, 'APP_NAME': 'fixture-app', 'RESOURCE_GROUP': 'fixture-group',
                                     'SLOT': 'production', 'PACKAGE_PATH': str(archive)},
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        args = json.loads((self.root / 'calls').read_text())
        self.assertEqual(args, ['functionapp', 'deployment', 'source', 'config-zip',
                                '--resource-group', 'fixture-group', '--name', 'fixture-app',
                                '--src', str(archive), '--output', 'none'])
        self.assertEqual(before, hashlib.sha256(archive.read_bytes()).hexdigest())

    def test_config_zip_receives_directory_callers_as_before(self):
        az = self.bin / 'az'
        az.write_text('#!/usr/bin/env python3\nimport json, os, sys\n'
                      'open(os.environ["CALLS"], "w").write(json.dumps(sys.argv[1:]))\n')
        az.chmod(0o755)
        composite = yaml.safe_load((ROOT / '.github/actions/azure/deploy-function/action.yml').read_text())
        result = subprocess.run(['bash', '-c', composite['runs']['steps'][0]['run']], cwd=self.root,
                                env={**self.env, 'APP_NAME': 'fixture-app', 'RESOURCE_GROUP': 'fixture-group',
                                     'SLOT': 'staging', 'RUNNER_TEMP': str(self.root)},
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        args = json.loads((self.root / 'calls').read_text())
        self.assertEqual(args[args.index('--slot') + 1], 'staging')
        self.assertEqual(args[args.index('--src') + 1], str(self.root / 'functionapp-deploy.zip'))
        with zipfile.ZipFile(self.root / 'functionapp-deploy.zip') as archive:
            self.assertIn('host.json', archive.namelist())

    def test_deploy_passes_selected_zip_to_existing_composite_unchanged(self):
        self.assertEqual(step('Download artifact', DEPLOY_STEPS)['with']['path'], '${{ inputs.package-path }}')
        self.assertEqual(step('Deploy to Function App', DEPLOY_STEPS)['with']['package-path'],
                         '${{ steps.package.outputs.path }}')
        composite = (ROOT / '.github/actions/azure/deploy-function/action.yml').read_text()
        self.assertIn('PKG="$PACKAGE_PATH"', composite)
        self.assertEqual(PUBLISH['permissions'], {'contents': 'read'})
        self.assertEqual(DEPLOY['permissions'], {'contents': 'read', 'id-token': 'write'})
        upload = step('Upload published artifact')['with']
        self.assertEqual(upload['path'], '${{ steps.artifact-path.outputs.path }}')
        self.assertTrue(upload['include-hidden-files'])
        self.assertEqual(upload['if-no-files-found'], 'error')


if __name__ == '__main__':
    unittest.main()
