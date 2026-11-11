"""Real SDK + official ApiCompat integration tests (no external service fixtures)."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / '.github/actions/api/check-compatibility/check.py'
spec = importlib.util.spec_from_file_location('api_check', SCRIPT)
api = importlib.util.module_from_spec(spec)
spec.loader.exec_module(api)


class RealApiCompatibility(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix='real-api-fixture-')
        cls.root = Path(cls.temp.name)
        cls.tool = cls.root / 'tool'
        api.run(['dotnet', 'tool', 'install', 'Microsoft.DotNet.ApiCompat.Tool', '--version', '11.0.100', '--tool-path', cls.tool], cls.root)
        cls.repo = cls.root / 'repo with spaces'
        cls.repo.mkdir()
        api.run(['git', 'init'], cls.repo)
        api.run(['git', 'config', 'user.email', 'fixture@example.invalid'], cls.repo)
        api.run(['git', 'config', 'user.name', 'Fixture'], cls.repo)
        cls.project = cls.repo / 'nested folder' / 'Library'
        cls.project.mkdir(parents=True)
        (cls.project / 'Library.csproj').write_text('<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup><TargetFrameworks>net10.0;net11.0</TargetFrameworks></PropertyGroup></Project>')
        (cls.project / 'Class.cs').write_text('public class Contract { public string Value(int input) => ""; }')
        (cls.repo / '.gitignore').write_text('bin/\nobj/\nreports/\n')
        api.run(['git', 'add', '.'], cls.repo)
        api.run(['git', 'commit', '-m', 'Baseline fixture'], cls.repo)
        cls.baseline = api.build(cls.repo, cls.project, cls.project / 'Library.csproj', cls.root / 'baseline.txt')
        # Keep baseline binaries/references stable while rebuilding the same project.
        import shutil
        cls.baseline_copy = cls.root / 'baseline binaries'
        shutil.copytree(cls.project / 'bin', cls.baseline_copy)
        cls.baseline = {key: (cls.baseline_copy / binary.relative_to(cls.project / 'bin'), refs)
                        for key, (binary, refs) in cls.baseline.items()}

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def build_compare(self, code):
        (self.project / 'Class.cs').write_text(code)
        inventory = self.root / 'current.txt'
        inventory.unlink(missing_ok=True)
        current = api.build(self.repo, self.project, self.project / 'Library.csproj', inventory)
        return api.compare(self.tool / 'apicompat', self.baseline, current, self.root)

    def test_addition_is_compatible_for_both_frameworks(self):
        changes, comparisons = self.build_compare('public class Contract { public string Value(int input) => ""; public void Added() {} }')
        self.assertEqual([], changes)
        self.assertEqual({'net10.0', 'net11.0'}, {c['framework'] for c in comparisons})

    def test_removed_member_breaks_both_frameworks(self):
        changes, _ = self.build_compare('public class Contract {}')
        self.assertEqual(2, len(changes))

    def test_changed_signature_breaks_both_frameworks(self):
        changes, _ = self.build_compare('public class Contract { public string Value(string input) => ""; }')
        self.assertEqual(2, len(changes))

    def test_framework_upgrade_reports_explicit_mapping(self):
        key = next(k for k in self.baseline if k[1] == 'net10.0')
        upgraded = {(key[0], 'net11.0'): self.baseline[(key[0], 'net11.0')]}
        changes, comparisons = api.compare(self.tool / 'apicompat', {key: self.baseline[key]}, upgraded, self.root)
        self.assertEqual([], changes)
        self.assertEqual('net11.0', comparisons[0]['current_framework'])

    def test_missing_reference_fails_closed(self):
        key = next(iter(self.baseline))
        left, _ = self.baseline[key]
        with self.assertRaises(RuntimeError):
            api.compare(self.tool / 'apicompat', {key: (left, ['/missing/reference.dll'])}, self.baseline, self.root)

    def test_solution_excludes_tests_and_copied_dependency_dlls(self):
        (self.project / 'Class.cs').write_text('public class Contract { public string Value(int input) => ""; }')
        test = self.repo / 'Fixture.Tests'
        test.mkdir(exist_ok=True)
        (test / 'Fixture.Tests.csproj').write_text('<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup><TargetFramework>net11.0</TargetFramework><IsTestProject>true</IsTestProject></PropertyGroup></Project>')
        solution = self.repo / 'Fixture.slnx'
        solution.write_text('<Solution><Project Path="nested folder/Library/Library.csproj" /><Project Path="Fixture.Tests/Fixture.Tests.csproj" /></Solution>')
        import shutil
        destination = self.project / 'bin/Release/net11.0/Unowned.Dependency.dll'
        shutil.copy2(next(iter(self.baseline.values()))[0], destination)
        inventory = self.root / 'solution.txt'
        assemblies = api.build(self.repo, self.repo, solution, inventory)
        self.assertEqual(2, len(assemblies))
        self.assertTrue(all(k[0].endswith('Library.csproj') for k in assemblies))

    def test_invalid_metadata_fails_closed(self):
        binary = self.root / 'invalid.dll'
        binary.write_text('Not assembly metadata')
        invalid = {('Library.csproj', 'net11.0'): (binary, [])}
        with self.assertRaises(RuntimeError):
            api.compare(self.tool / 'apicompat', invalid, invalid, self.root)

    def test_tool_failure_never_passes(self):
        with self.assertRaises(RuntimeError):
            api.compare('/bin/false', self.baseline, self.baseline, self.root)

    def invoke(self, **settings):
        env = {**os.environ, 'API_PROJECT': 'Library.csproj', 'API_BASELINE_REF': 'HEAD',
               'API_OUTPUT': str(self.root / 'reports'), 'API_FAIL_ON_BREAKING': 'false', **settings}
        result = subprocess.run(['python3', str(SCRIPT)], cwd=self.project, env=env,
                                capture_output=True, text=True)
        report = json.loads((self.root / 'reports/api-compat-report.json').read_text())
        return result, report

    def test_missing_ref_fails_even_when_breaking_allowed(self):
        result, report = self.invoke(API_BASELINE_REF='does-not-exist')
        self.assertNotEqual(0, result.returncode)
        self.assertEqual('error', report['status'])
        self.assertIsNone(report['breaking_changes'])

    def test_baseline_build_failure_is_not_compatible(self):
        (self.project / 'Class.cs').write_text('invalid baseline source')
        api.run(['git', 'add', 'nested folder/Library/Class.cs'], self.repo)
        api.run(['git', 'commit', '-m', 'Broken baseline'], self.repo)
        bad = api.run(['git', 'rev-parse', 'HEAD'], self.repo).stdout.strip()
        api.run(['git', 'reset', '--hard', 'HEAD~1'], self.repo)
        result, report = self.invoke(API_BASELINE_REF=bad)
        self.assertNotEqual(0, result.returncode)
        self.assertEqual('error', report['status'])

    def test_baseline_sdk_10_and_current_sdk_11_are_honored(self):
        project_file = self.project / 'Library.csproj'
        original = project_file.read_text()
        project_file.write_text(original.replace('net10.0;net11.0', 'net10.0'))
        (self.project / 'Class.cs').write_text('public class Contract { public string Value(int input) => ""; }')
        pin = self.repo / 'global.json'
        pin.write_text('{"sdk":{"version":"10.0.404","rollForward":"disable"}}')
        api.run(['git', 'add', '.'], self.repo)
        api.run(['git', 'commit', '-m', 'SDK10 baseline'], self.repo)
        bad = api.run(['git', 'rev-parse', 'HEAD'], self.repo).stdout.strip()
        try:
            pin.write_text('{"sdk":{"version":"11.0.100","rollForward":"disable"}}')
            project_file.write_text(original.replace('net10.0;net11.0', 'net11.0'))
            result, report = self.invoke(API_BASELINE_REF=bad)
            self.assertEqual(0, result.returncode, result.stdout + result.stderr)
            self.assertEqual('api-compatible-framework-support-changed', report['status'])
            self.assertEqual('net10.0', report['framework_migrations'][0]['baseline'])
            self.assertEqual('net11.0', report['framework_migrations'][0]['current'])
        finally:
            api.run(['git', 'reset', '--hard', 'HEAD~1'], self.repo)

    def test_commented_and_unpinned_baselines_build_without_rewriting(self):
        sources = ['{"test":{"runner":"VSTest"},"sdk":{"allowPrerelease":false}}',
                   '{ // SDK comment\n "sdk": {"version":"11.0.100", /* exact */ "rollForward":"disable"}}']
        for source in sources:
            with self.subTest(source=source):
                (self.project / 'Class.cs').write_text('public class Contract { public string Value(int input) => ""; }')
                pin = self.repo / 'global.json'
                pin.write_text(source)
                api.run(['git', 'add', 'global.json', 'nested folder/Library/Class.cs'], self.repo)
                api.run(['git', 'commit', '-m', 'Baseline global config'], self.repo)
                try:
                    result, report = self.invoke()
                    self.assertEqual(0, result.returncode, result.stdout + result.stderr)
                    self.assertEqual('compatible', report['status'])
                    self.assertEqual(source, pin.read_text())
                finally:
                    api.run(['git', 'reset', '--hard', 'HEAD~1'], self.repo)

    def test_missing_baseline_sdk_is_not_substituted(self):
        (self.repo / 'global.json').write_text('{"sdk":{"version":"99.0.100","rollForward":"disable"}}')
        api.run(['git', 'add', 'global.json'], self.repo)
        api.run(['git', 'commit', '-m', 'Unavailable baseline SDK'], self.repo)
        bad = api.run(['git', 'rev-parse', 'HEAD'], self.repo).stdout.strip()
        api.run(['git', 'reset', '--hard', 'HEAD~1'], self.repo)
        result, report = self.invoke(API_BASELINE_REF=bad)
        self.assertNotEqual(0, result.returncode)
        self.assertEqual('error', report['status'])
        self.assertIn('99.0.100', report['error'])

    def test_breaking_policy_and_outputs(self):
        (self.project / 'Class.cs').write_text('public class Contract {}')
        outputs = self.root / 'github-output'
        result, report = self.invoke(API_FAIL_ON_BREAKING='true', GITHUB_OUTPUT=str(outputs))
        self.assertEqual(1, result.returncode, result.stdout)
        self.assertEqual('breaking-changes-detected', report['status'])
        self.assertEqual(2, report['breaking_changes'])
        self.assertIn('breaking-changes=2', outputs.read_text())
        self.assertIn(str(self.root / 'reports/api-compat-report.json'), outputs.read_text())
        result, report = self.invoke(API_FAIL_ON_BREAKING='false')
        self.assertEqual(0, result.returncode, result.stdout)
        self.assertEqual(2, report['breaking_changes'])

    def test_text_baseline_is_explicitly_rejected(self):
        result, report = self.invoke(API_BASELINE_PATH='api.txt')
        self.assertNotEqual(0, result.returncode)
        self.assertIn('text snapshots are unsupported', report['error'])

    def test_build_failure_is_not_compatible(self):
        (self.project / 'Class.cs').write_text('this is invalid C#')
        result, report = self.invoke()
        self.assertNotEqual(0, result.returncode)
        self.assertEqual('error', report['status'])

    def test_full_git_comparison_nested_directory_and_spaces(self):
        (self.project / 'Class.cs').write_text('public class Contract { public string Value(int input) => ""; public void Added() {} }')
        result, report = self.invoke()
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertEqual('compatible', report['status'])
        self.assertEqual(2, len(report['comparisons']))
        self.assertEqual(1, len(api.run(['git', 'worktree', 'list', '--porcelain'], self.repo).stdout.split('worktree ')) - 1)


class DetachedPullRequestBaseline(unittest.TestCase):
    def test_preparation_uses_immutable_base_without_local_branch(self):
        with tempfile.TemporaryDirectory(prefix='detached-pr-fixture-') as temp:
            root = Path(temp)
            api.run(['git', 'init', '-b', 'main'], root)
            api.run(['git', 'config', 'user.email', 'fixture@example.invalid'], root)
            api.run(['git', 'config', 'user.name', 'Fixture'], root)
            pin = {'sdk': {'version': '10.0.404', 'rollForward': 'disable'}}
            (root / 'global.json').write_text(json.dumps(pin))
            api.run(['git', 'add', 'global.json'], root)
            api.run(['git', 'commit', '-m', 'Baseline'], root)
            baseline = api.run(['git', 'rev-parse', 'HEAD'], root).stdout.strip()
            api.run(['git', 'update-ref', 'refs/remotes/origin/main', baseline], root)
            (root / 'global.json').write_text('{"sdk":{"version":"11.0.100"}}')
            api.run(['git', 'commit', '-am', 'PR current revision'], root)
            api.run(['git', 'checkout', '--detach'], root)
            api.run(['git', 'branch', '-D', 'main'], root)
            self.assertNotEqual(0, api.run(['git', 'rev-parse', '--verify', 'main'], root, check=False).returncode)
            nested = root / 'nested folder'
            nested.mkdir()
            for ref in (baseline, 'refs/remotes/origin/main'):
                with self.subTest(ref=ref):
                    output = root / 'output'
                    output.unlink(missing_ok=True)
                    result = subprocess.run(['python3', str(SCRIPT.with_name('prepare-sdk.py'))],
                                            cwd=nested, capture_output=True, text=True,
                                            env={**os.environ, 'API_BASELINE_REF': ref,
                                                 'RUNNER_TEMP': temp, 'GITHUB_OUTPUT': str(output)})
                    self.assertEqual(0, result.returncode, result.stdout + result.stderr)
                    prepared = Path(output.read_text().strip().removeprefix('global-json='))
                    self.assertEqual(pin, json.loads(prepared.read_text()))
            workflow = SCRIPT.parents[3] / 'workflows/job-api-compatibility.yml'
            self.assertIn("baseline-ref: ${{ github.event.pull_request.base.sha || 'refs/remotes/origin/main' }}",
                          workflow.read_text())


class BaselineGlobalJsonTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location('prepare_sdk', SCRIPT.with_name('prepare-sdk.py'))
        import sys
        sys.path.insert(0, str(SCRIPT.parent))
        cls.prepare = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.prepare)

    def test_commented_pin_preserves_strings(self):
        source = r'''{
          // Historical SDK selection
          "sdk": {"version": "10.0.404", /* exact */ "rollForward": "disable"},
          "note": "https://example.invalid/a/*text*/?value=,} and \"quoted\""
        }'''
        data = self.prepare.parse_global_json(source)
        self.assertEqual('10.0.404', data['sdk']['version'])
        self.assertIn('https://example.invalid/a/*text*/', data['note'])
        self.assertIn('"quoted"', data['note'])

    def test_valid_unpinned_configs(self):
        for data in ({}, {'test': {'runner': 'VSTest'}},
                     {'msbuild-sdks': {'Example.Sdk': '1.0.0'}},
                     {'sdk': {'allowPrerelease': False}}):
            self.assertEqual(data, self.prepare.parse_global_json(json.dumps(data)))

    def test_invalid_configs_still_fail(self):
        for source in ('{"sdk":', '{/* unterminated', '{"sdk":{"version":null}}',
                       '{"sdk":{"version":42}}', '{"sdk":{"version":""}}',
                       '{"sdk":[]}', '[]', '{"a":1,,}', '{"sdk":{"version":"10.0.404",}}'):
            with self.subTest(source=source), self.assertRaises(ValueError):
                self.prepare.parse_global_json(source)

    def test_preparation_matches_real_sdk_nearest_config(self):
        with tempfile.TemporaryDirectory(prefix='sdk-json-fixture-') as temp:
            root = Path(temp)
            api.run(['git', 'init'], root)
            api.run(['git', 'config', 'user.email', 'fixture@example.invalid'], root)
            api.run(['git', 'config', 'user.name', 'Fixture'], root)
            (root / 'global.json').write_text('{"sdk":{"version":"99.0.100"}}')
            nested = root / 'nested space'
            nested.mkdir()
            pin = nested / 'global.json'
            cases = [
                ('{"test":{"runner":"VSTest"}}', None),
                ('{"msbuild-sdks":{}}', None),
                ('{"sdk":{"allowPrerelease":false}}', None),
                ('{ // pin\n "sdk": {"version":"10.0.404", /* exact */ "rollForward":"disable"}}', '10.0.404'),
            ]
            for source, version in cases:
                with self.subTest(source=source):
                    pin.write_text(source)
                    api.run(['git', 'add', '.'], root)
                    api.run(['git', 'commit', '-m', 'SDK config fixture'], root)
                    output = root / 'output'
                    output.unlink(missing_ok=True)
                    result = subprocess.run(['python3', str(SCRIPT.with_name('prepare-sdk.py'))],
                                            cwd=nested, capture_output=True, text=True,
                                            env={**os.environ, 'API_BASELINE_REF': 'HEAD',
                                                 'RUNNER_TEMP': temp, 'GITHUB_OUTPUT': str(output)})
                    self.assertEqual(0, result.returncode, result.stderr)
                    resolved = api.run(['dotnet', '--version'], nested).stdout.strip()
                    if version:
                        self.assertEqual(version, resolved)
                        prepared = Path(output.read_text().strip().removeprefix('global-json='))
                        self.assertEqual(version, json.loads(prepared.read_text())['sdk']['version'])
                    else:
                        self.assertFalse(output.exists(), 'Do not install an ancestor SDK pin')
                        self.assertRegex(resolved, r'^11\.0\.')
                    self.assertEqual(source, pin.read_text(), 'Do not rewrite baseline configuration')


if __name__ == '__main__':
    unittest.main()
