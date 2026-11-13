"""Pin the private CodeQL permission boundary without weakening its gates."""
from pathlib import Path
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[1]


class PrivateCodeqlPermissionsTests(unittest.TestCase):
    def setUp(self):
        self.sdk = yaml.safe_load((ROOT / '.github/workflows/pr-sdk.yml').read_text(encoding='utf-8'))
        self.core = yaml.safe_load((ROOT / '.github/workflows/pr-core.yml').read_text(encoding='utf-8'))
        self.codeql = yaml.safe_load((ROOT / '.github/workflows/job-codeql.yml').read_text(encoding='utf-8'))

    def test_nested_codeql_uses_the_same_immutable_revision(self):
        job = self.core['jobs']['codeql']
        self.assertEqual(job['uses'], './.github/workflows/job-codeql.yml')
        self.assertEqual(job['with']['actions-ref'], '${{ inputs.actions-ref }}')
        checkout = next(step for step in self.codeql['jobs']['codeql']['steps']
                        if step['name'] == 'Checkout HoneyDrunk.Actions')
        self.assertEqual(checkout['with']['ref'], '${{ inputs.actions-ref }}')

    def test_sdk_preserves_the_same_permission_and_revision_chain(self):
        job = self.sdk['jobs']['codeql']
        self.assertEqual(job['uses'], './.github/workflows/job-codeql.yml')
        self.assertEqual(job['with']['actions-ref'], '${{ inputs.actions-ref }}')
        self.assertEqual(job['permissions'], self.core['jobs']['codeql']['permissions'])
        self.assertNotIn('actions', self.sdk['permissions'])
        for name, other in self.sdk['jobs'].items():
            if name != 'codeql':
                self.assertNotIn('actions', other.get('permissions', {}))

    def test_actions_read_is_scoped_to_codeql(self):
        required = {'actions': 'read', 'contents': 'read', 'security-events': 'write'}
        self.assertEqual(self.core['jobs']['codeql']['permissions'], required)
        self.assertEqual(self.codeql['permissions'], required)
        self.assertNotIn('permissions', self.codeql['jobs']['codeql'])
        self.assertNotIn('actions', self.core['permissions'])
        for name, job in self.core['jobs'].items():
            if name != 'codeql':
                with self.subTest(job=name):
                    self.assertNotIn('actions', job.get('permissions', {}))

    def test_analysis_upload_and_post_upload_gate_remain_required(self):
        steps = self.codeql['jobs']['codeql']['steps']
        names = [step['name'] for step in steps]
        required = ['Perform CodeQL Analysis', 'Filter generated-code findings from SARIF',
                    'Upload filtered SARIF', 'Evaluate findings']
        indexes = [names.index(name) for name in required]
        self.assertEqual(indexes, sorted(indexes))
        for name in required:
            with self.subTest(step=name):
                self.assertNotIn('continue-on-error', steps[names.index(name)])
        upload = steps[names.index('Upload filtered SARIF')]
        self.assertTrue(upload['with']['wait-for-processing'])
        gate = steps[names.index('Evaluate findings')]
        self.assertEqual(gate['if'], 'always()')
        self.assertIn('/code-scanning/alerts?', gate['run'])
        self.assertIn('exit 1', gate['run'])
        inputs = self.codeql.get('on', self.codeql.get(True))['workflow_call']['inputs']
        self.assertEqual(inputs['fail-on-severity']['default'], 'note')
        self.assertEqual(inputs['queries']['default'], 'security-and-quality')


if __name__ == '__main__':
    unittest.main()
