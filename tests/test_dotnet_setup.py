"""Exercise the shipped SDK selector without installing SDKs or using credentials."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

import yaml


ROOT = Path(__file__).resolve().parents[1]
ACTION = yaml.safe_load((ROOT / '.github/actions/dotnet/setup/action.yml').read_text())
SELECTOR = next(step for step in ACTION['runs']['steps'] if step.get('id') == 'resolve-sdk')


class DotnetSdkSelectionTests(unittest.TestCase):
    def select(self, version='', pinned=None):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / 'output'
            pin = root / 'nested workspace' / 'global.json'
            if pinned is not None:
                pin.parent.mkdir()
                pin.write_text(json.dumps({'sdk': {'version': pinned}}))
            result = subprocess.run(
                ['bash', '-e', '-o', 'pipefail', '-c', SELECTOR['run']],
                cwd=root, capture_output=True, text=True, check=True,
                env={**os.environ, 'DOTNET_VERSION': version,
                     'GLOBAL_JSON_FILE': str(pin), 'GITHUB_OUTPUT': str(output)},
                timeout=10)
            self.assertEqual(result.stderr, '')
            values = dict(line.split('=', 1) for line in output.read_text().splitlines())
            if values['global-json-file']:
                values['global-json-file'] = Path(values['global-json-file']).relative_to(root).as_posix()
            return values

    def test_explicit_net11_sdk_takes_precedence(self):
        self.assertEqual(self.select('11.0.100', '10.0.402'), {
            'dotnet-version': '11.0.100', 'global-json-file': ''})

    def test_global_json_with_spaces_is_used_for_net11(self):
        self.assertEqual(self.select(pinned='11.0.100'), {
            'dotnet-version': '', 'global-json-file': 'nested workspace/global.json'})

    def test_unmigrated_consumers_keep_the_existing_default(self):
        self.assertEqual(self.select(), {
            'dotnet-version': '10.0.x', 'global-json-file': ''})


if __name__ == '__main__':
    unittest.main()
