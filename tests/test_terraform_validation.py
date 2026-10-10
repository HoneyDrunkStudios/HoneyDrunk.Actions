"""Exercise the same runner invoked by the reusable workflow."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace

spec = importlib.util.spec_from_file_location('terraform_validate', Path(__file__).parents[1] / '.github/scripts/terraform_validate.py')
validator = importlib.util.module_from_spec(spec)
spec.loader.exec_module(validator)


class TerraformValidationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.repo = Path(self.tmp.name)
        self.root = self.repo / 'platform'
        (self.root / 'tests').mkdir(parents=True)
        (self.root / 'main.tf').write_text('')
        (self.repo / 'terraform-roots.json').write_text('["platform"]')
        (self.repo / '.terraform.lock.hcl').write_text('# test lock')
        self.test = self.root / 'tests/safety.tftest.hcl'
        self.test.write_text('mock_provider "azurerm" {}\nrun "check" { command = plan }\n')

    def test_runner_never_initializes_backend_or_executes_plan_apply_import(self):
        calls = []
        def capture(args, **kwargs):
            calls.append((args, kwargs))
            return SimpleNamespace(stdout=json.dumps({'type':'test_summary','test_summary':{'status':'pass','passed':1,'failed':0,'errored':0,'skipped':0}}))
        validator.validate(self.repo, run=capture)
        self.assertEqual([c[0][2] for c in calls], ['fmt', 'init', 'validate', 'test'])
        self.assertIn('-backend=false', calls[1][0])
        self.assertIn('-lockfile=readonly', calls[1][0])
        self.assertEqual(calls[3][0][2:], ['test', '-json'])
        self.assertTrue(all(c[1]['check'] for c in calls))
        self.assertEqual(calls[3][1]['env']['ARM_USE_CLI'], 'false')

    def test_rejects_outside_root(self):
        (self.repo / 'terraform-roots.json').write_text('["../outside"]')
        with self.assertRaises(ValueError):
            validator.targets(self.repo)

    def test_rejects_duplicate_roots(self):
        (self.repo / 'terraform-roots.json').write_text('["platform", "platform"]')
        with self.assertRaises(ValueError):
            validator.targets(self.repo)

    def test_rejects_unmocked_apply_or_alternate_module_before_execution(self):
        for source in ['run "check" { command = plan }',
                       'mock_provider "azurerm" {}\nrun "check" { command = apply }',
                       'mock_provider "azurerm" {}\nprovider "azurerm" {}\nrun "check" { command = plan }',
                       'mock_provider "azurerm" {}\nrun "check" {\n command = plan\n module { source = "./other" }\n}']:
            with self.subTest(source=source):
                self.test.write_text(source)
                with self.assertRaises(ValueError):
                    validator.validate(self.repo, run=lambda *args, **kwargs: self.fail('Unsafe test reached Terraform'))

    def test_command_failure_is_not_swallowed(self):
        def fail(*args, **kwargs):
            raise RuntimeError('formatter failed')
        with self.assertRaisesRegex(RuntimeError, 'formatter failed'):
            validator.validate(self.repo, run=fail)

    def test_rejects_missing_zero_skipped_or_failed_test_results(self):
        for summary in [None, {'status':'pass','passed':0,'failed':0,'errored':0,'skipped':0},
                        {'status':'pass','passed':1,'failed':0,'errored':0,'skipped':1},
                        {'status':'fail','passed':0,'failed':1,'errored':0,'skipped':0}]:
            with self.subTest(summary=summary):
                output = '' if summary is None else json.dumps({'type':'test_summary','test_summary':summary})
                with self.assertRaises(ValueError):
                    validator.verify_test_result(output, 1)

    def test_rejects_extra_test_files(self):
        (self.root / 'tests/other.tftest.hcl').write_text('run "unsafe" { command = apply }')
        with self.assertRaises(ValueError):
            validator.require_mocked_plans(self.root)

    def test_rejects_unmocked_external_data_source(self):
        (self.root / 'main.tf').write_text('data "external" "unsafe" { program = ["script"] }')
        with self.assertRaises(ValueError):
            validator.require_azurerm_only(self.root, {self.root})

    def test_rejects_aliased_mock_that_leaves_default_provider_real(self):
        self.test.write_text('mock_provider "azurerm" { alias = "fake" }\nrun "check" { command = plan }')
        with self.assertRaises(ValueError):
            validator.require_mocked_plans(self.root)

    def test_rejects_remote_or_unvalidated_module(self):
        for source in ['registry.example/module', '../unvalidated']:
            (self.root / 'main.tf').write_text(f'module "unsafe" {{ source = "{source}" }}')
            with self.assertRaises(ValueError):
                validator.require_azurerm_only(self.root, {self.root})


if __name__ == '__main__':
    unittest.main()
