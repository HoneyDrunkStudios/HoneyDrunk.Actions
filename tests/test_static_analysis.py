"""Run the shipped formatter step with the real SDK; no dotnet stub."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = yaml.safe_load((ROOT / '.github/workflows/job-static-analysis.yml').read_text())
FORMAT = next(step for step in WORKFLOW['jobs']['static-analysis']['steps'] if step.get('id') == 'formatting')


class FormatterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.temp.cleanup)
        cls.root = Path(cls.temp.name)
        cls.solution_dir = cls.root / 'nested workspace'
        cls.solution_dir.mkdir()
        for command in [
            ['dotnet', 'new', 'sln', '-n', 'Fixture', '-o', str(cls.solution_dir)],
            ['dotnet', 'new', 'classlib', '-f', 'net10.0', '-o', str(cls.solution_dir / 'App')],
            ['dotnet', 'sln', str(cls.solution_dir / 'Fixture.slnx'), 'add',
             str(cls.solution_dir / 'App/App.csproj')],
        ]:
            subprocess.run(command, check=True, capture_output=True, text=True, timeout=120)
        cls.source = cls.solution_dir / 'App/Class1.cs'
        cls.formatted = cls.source.read_text()

    def setUp(self):
        self.source.write_text(self.formatted)

    def run_formatter(self, project='nested workspace/Fixture.slnx', strict=True, cwd=None):
        output = self.root / 'outputs'
        output.write_text('')
        result = subprocess.run(
            [shutil.which('bash') or 'bash', '-e', '-o', 'pipefail', '-c', FORMAT['run']],
            cwd=cwd or self.root, capture_output=True, text=True, timeout=120,
            env={**os.environ, 'FORMAT_PROJECT_PATH': project,
                 'FAIL_ON_FORMATTING_ISSUES': str(strict).lower(),
                 'GITHUB_OUTPUT': output.as_posix()})
        return result, output.read_text()

    def test_explicit_nested_solution_with_spaces_is_formatted(self):
        result, output = self.run_formatter()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('Formatted 0 of', result.stdout)
        self.assertEqual(output, 'has-issue=false\n')

    def test_empty_project_preserves_discovery_in_working_directory(self):
        result, output = self.run_formatter(project='', cwd=self.solution_dir)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(output, 'has-issue=false\n')

    def test_workspace_errors_fail_even_in_advisory_mode(self):
        for strict in (True, False):
            with self.subTest(strict=strict):
                result, output = self.run_formatter(project='missing.slnx', strict=strict)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn('::error::dotnet format failed', result.stdout)
                self.assertNotIn('::warning::', result.stdout)
                self.assertEqual(output, '')

    def test_actual_formatting_differences_fail_without_modifying_source(self):
        malformed = 'namespace App;\npublic class Class1{public int Value{get;set;}}\n'
        self.source.write_text(malformed)
        result, output = self.run_formatter()
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertEqual(self.source.read_text(), malformed)
        self.assertEqual(output, '')
        self.assertIn('::error::dotnet format failed', result.stdout)

    def test_existing_advisory_option_only_allows_formatting_differences(self):
        self.source.write_text('namespace App;\npublic class Class1{public int Value{get;set;}}\n')
        result, output = self.run_formatter(strict=False)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(output, 'has-issue=true\n')
        self.assertIn('::warning::Code formatting issues detected', result.stdout)


if __name__ == '__main__':
    unittest.main()
