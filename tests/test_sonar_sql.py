"""Run the real scanner-begin script against a credential-free argument recorder."""

import os
from pathlib import Path
import re
import subprocess
import tempfile
import unittest

import yaml


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = yaml.safe_load((ROOT / '.github/workflows/job-sonarcloud.yml').read_text(encoding='utf-8'))
STEP = next(step for step in WORKFLOW['jobs']['sonarcloud']['steps']
            if step['name'] == 'Begin SonarQube Cloud analysis')
BASH = os.environ.get('BASH_EXE', 'bash')


class SonarSqlTests(unittest.TestCase):
    def arguments(self, tsql):
        with tempfile.TemporaryDirectory(prefix='sonar sql ') as directory:
            root = Path(directory)
            scanner = root / '.sonar/scanner/dotnet-sonarscanner'
            scanner.parent.mkdir(parents=True)
            scanner.write_text('#!/usr/bin/env bash\nprintf "%s\\n" "$@" > "$ARGUMENT_FILE"\n', encoding='utf-8')
            scanner.chmod(0o755)
            arguments = root / 'arguments.txt'
            values = {'sonar-project-key': 'fixture', 'sonar-organization': 'fixture',
                      'sonar-host-url': 'https://invalid.example', 'sonar-exclusions': '.github/workflows/**'}
            script = re.sub(r'\$\{\{ inputs\.([\w-]+) \}\}', lambda match: values[match[1]], STEP['run'])
            environment = {**os.environ, 'GITHUB_WORKSPACE': root.as_posix(),
                           'ARGUMENT_FILE': arguments.as_posix(), 'SONAR_TOKEN': 'fixture-not-a-token',
                           'SONAR_TSQL': tsql, 'MSYS_NO_PATHCONV': '1'}
            result = subprocess.run([BASH, '-eu', '-c', script], env=environment,
                                    text=True, capture_output=True, check=False)
            self.assertEqual(result.returncode, 0, result.stderr)
            return arguments.read_text(encoding='utf-8').splitlines()

    def test_default_preserves_server_dialect_and_gate(self):
        self.assertFalse(WORKFLOW[True]['workflow_call']['inputs']['sonar-tsql']['default'])
        arguments = self.arguments('false')
        self.assertFalse(any('.file.suffixes=' in item for item in arguments))
        self.assertIn('/d:sonar.qualitygate.wait=true', arguments)
        self.assertIn('/d:sonar.cs.opencover.reportsPaths=**/coverage.opencover.xml', arguments)
        self.assertNotIn('', arguments)

    def test_sql_server_opt_in_is_exclusive_and_preserves_scope(self):
        arguments = self.arguments('true')
        self.assertIn('/d:sonar.tsql.file.suffixes=.sql,.tsql', arguments)
        self.assertIn('/d:sonar.plsql.file.suffixes=.plsql,.pks,.pkb', arguments)
        self.assertEqual([item for item in arguments if item.startswith('/d:sonar.exclusions=')],
                         ['/d:sonar.exclusions=.github/workflows/**'])
        self.assertIn('/d:sonar.qualitygate.wait=true', arguments)
        self.assertEqual(arguments.count('/k:fixture'), 1)


if __name__ == '__main__':
    unittest.main()
