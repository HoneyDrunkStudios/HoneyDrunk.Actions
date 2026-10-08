"""Exercise the shipped traffic guard and workflow shell with Azure stubbed."""

import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = yaml.safe_load((ROOT / '.github/workflows/job-deploy-container-app.yml').read_text())
STEPS = WORKFLOW['jobs']['deploy']['steps']
BY_ID = {step['id']: step for step in STEPS if 'id' in step}
SPEC = importlib.util.spec_from_file_location('traffic', ROOT / '.github/scripts/container_app_traffic.py')
TRAFFIC = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(TRAFFIC)
APP = 'ca-hd-example-dev'
PREVIOUS = APP + '--healthy'
NEW = APP + '--candidate'


def target(revision=PREVIOUS, weight=100, **extra):
    return dict(revisionName=revision, weight=weight, **extra)


class TrafficContractTests(unittest.TestCase):
    def test_explicit_target(self):
        self.assertEqual(TRAFFIC.current_revision([target()], APP), PREVIOUS)

    def test_zero_weight_candidates_and_latest_are_safe(self):
        self.assertEqual(TRAFFIC.current_revision([
            target(), target(NEW, 0), dict(latestRevision=True, weight=0)
        ], APP), PREVIOUS)

    def test_legacy_weight_field(self):
        self.assertEqual(TRAFFIC.current_revision([
            dict(revisionName=PREVIOUS, trafficWeight=100)
        ], APP), PREVIOUS)

    def test_rejects_unknown_ambiguous_and_unsafe_traffic(self):
        cases = [
            None, {}, [], ['invalid'], [target(weight=None)],
            [target(weight=True)], [target(weight='100')], [target(weight=100.0)],
            [target(weight=-1)], [target(weight=101)], [target(weight=0)],
            [target(weight=99)], [target(weight=50), target(NEW, 50)],
            [target(weight=50), target(weight=50)], [target(), target(NEW)],
            [dict(latestRevision=True, weight=100)], [target(latestRevision=True)],
            [target(latestRevision='false')], [target(latestRevision=None)],
            [dict(weight=100)], [target('')], [target('another-app--healthy')],
            [target(PREVIOUS + '\nforged-output=1')], [target(revision=123)],
            [target(trafficWeight=50)],
        ]
        for value in cases:
            with self.subTest(value=value), self.assertRaises(ValueError):
                TRAFFIC.current_revision(value, APP)

    def test_does_not_overwrite_concurrent_rollout_or_rollback(self):
        self.assertEqual(TRAFFIC.current_revision([target()], APP, PREVIOUS), PREVIOUS)
        for expected in ['', NEW]:
            with self.subTest(expected=expected), self.assertRaises(ValueError):
                TRAFFIC.current_revision([target()], APP, expected)


class WorkflowShellTests(unittest.TestCase):
    def run_step(self, step_id, traffic=None, **overrides):
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            (work / '.actions').symlink_to(ROOT, target_is_directory=True)
            az = work / 'az'
            az.write_text('''#!/usr/bin/env python3
import json, os, sys
from pathlib import Path
with Path(os.environ['AZ_CALLS']).open('a') as stream:
    stream.write(json.dumps(sys.argv[1:]) + '\\n')
if sys.argv[1:5] == ['containerapp', 'ingress', 'traffic', 'show']:
    print(os.environ['TRAFFIC_JSON'])
    sys.exit(int(os.environ.get('AZ_READ_EXIT', '0')))
if sys.argv[1:5] == ['containerapp', 'ingress', 'traffic', 'set']:
    sys.exit(int(os.environ.get('AZ_SET_EXIT', '0')))
raise SystemExit('Unexpected Azure operation')
''')
            az.chmod(0o755)
            output = work / 'output'
            calls = work / 'calls'
            env = dict(os.environ, APP_NAME=APP, RESOURCE_GROUP='rg-test',
                       PATH=directory + os.pathsep + os.environ['PATH'],
                       GITHUB_OUTPUT=str(output), AZ_CALLS=str(calls),
                       TRAFFIC_JSON=json.dumps([target()] if traffic is None else traffic),
                       JOB_STATUS='success', DEPLOY_OUTCOME='success',
                       HEALTH_OUTCOME='success', SHIFT_OUTCOME='success',
                       HEALTH_CHECK_URL='/healthz', NEW_REVISION=NEW,
                       CURRENT_REVISION=PREVIOUS, TRAFFIC_SHIFT_MODE='full')
            env.update(overrides)
            result = subprocess.run(['bash', '-e', '-o', 'pipefail', '-c', BY_ID[step_id]['run']],
                                    cwd=work, env=env, capture_output=True, text=True)
            return result, output.read_text() if output.exists() else '', [
                json.loads(line) for line in calls.read_text().splitlines()
            ] if calls.exists() else []

    def test_preflight_publishes_only_verified_target(self):
        result, output, calls = self.run_step('current-traffic')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(output, 'current-revision=' + PREVIOUS + '\n')
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][:4], ['containerapp', 'ingress', 'traffic', 'show'])

    def test_traffic_api_failure_cannot_become_empty_success(self):
        result, output, calls = self.run_step('current-traffic', AZ_READ_EXIT='1')
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(output, '')
        self.assertEqual(len(calls), 1)
        self.assertIn('Cannot establish safe', result.stderr)

    def test_invalid_json_fails_closed(self):
        result, output, _ = self.run_step('current-traffic', TRAFFIC_JSON='not json')
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(output, '')

    def test_latest_traffic_never_publishes_a_guessed_target(self):
        result, output, calls = self.run_step('current-traffic', [dict(latestRevision=True, weight=100)])
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(output, '')
        self.assertEqual(len(calls), 1)

    def test_recheck_blocks_changed_target_before_deploy(self):
        result, _, calls = self.run_step('pre-deploy-traffic', [target(NEW)], EXPECTED_REVISION=PREVIOUS)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(len(calls), 1)

    def test_secret_configuration_checks_traffic_before_any_mutation(self):
        result, _, calls = self.run_step('configure-keyvault-refs', [target(NEW)],
                                         EXPECTED_REVISION=PREVIOUS, VAULT_NAME='kv-test', SECRETS_INPUT='secret')
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][:4], ['containerapp', 'ingress', 'traffic', 'show'])

    def test_shift_modes_keep_explicit_weights(self):
        for mode, percent, expected in [
            ('full', 100, [NEW + '=100']),
            ('canary:10', 10, [NEW + '=10', PREVIOUS + '=90']),
            ('hold', 0, None),
        ]:
            with self.subTest(mode=mode):
                result, output, calls = self.run_step('shift-traffic', TRAFFIC_SHIFT_MODE=mode,
                                                      EXPECTED_REVISION=PREVIOUS)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn(f'traffic-percent={percent}', output)
                self.assertEqual(len(calls), 2 if expected else 1)
                if expected:
                    self.assertEqual(calls[1][calls[1].index('--revision-weight') + 1:-2], expected)

    def test_shift_never_overwrites_changed_traffic(self):
        for mode in ['full', 'canary:10', 'hold']:
            with self.subTest(mode=mode):
                result, output, calls = self.run_step('shift-traffic', [target(NEW)],
                                                      TRAFFIC_SHIFT_MODE=mode, EXPECTED_REVISION=PREVIOUS)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(output, '')
                self.assertEqual(len(calls), 1)

    def test_shift_failure_has_no_confirmed_percent(self):
        result, output, _ = self.run_step('shift-traffic', EXPECTED_REVISION=PREVIOUS, AZ_SET_EXIT='1')
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn('traffic-percent', output)

    def test_success_requires_completed_deploy_and_shift(self):
        result, output, _ = self.run_step('deployment-status')
        self.assertEqual(result.returncode, 0)
        self.assertEqual(output, 'status=success\n')
        for name in ['DEPLOY_OUTCOME', 'SHIFT_OUTCOME']:
            for value in ['skipped', 'cancelled', 'failure', '']:
                with self.subTest(name=name, value=value):
                    _, output, _ = self.run_step('deployment-status', **{name: value})
                    self.assertEqual(output, 'status=deploy-failed\n')

    def test_any_job_failure_or_cancellation_is_failure(self):
        # job.status covers preflight, checkout, Buildx and every future step,
        # including steps with no id. No outcome allowlist can omit a new stage.
        self.assertEqual(BY_ID['deployment-status']['env']['JOB_STATUS'], '${{ job.status }}')
        for value in ['failure', 'cancelled', 'skipped', '']:
            with self.subTest(value=value):
                _, output, _ = self.run_step('deployment-status', JOB_STATUS=value)
                self.assertEqual(output, 'status=deploy-failed\n')

    def test_preflight_failure_with_skipped_deployment_is_not_success(self):
        _, output, _ = self.run_step('deployment-status', JOB_STATUS='failure',
                                      DEPLOY_OUTCOME='skipped', SHIFT_OUTCOME='skipped', HEALTH_OUTCOME='skipped')
        self.assertEqual(output, 'status=deploy-failed\n')

    def test_health_failure_retains_public_status_contract(self):
        _, output, _ = self.run_step('deployment-status', JOB_STATUS='failure', HEALTH_OUTCOME='failure', SHIFT_OUTCOME='skipped')
        self.assertEqual(output, 'status=health-check-failed\n')

    def test_optional_probe_skips_only_when_not_requested(self):
        _, output, _ = self.run_step('deployment-status', HEALTH_OUTCOME='skipped', HEALTH_CHECK_URL='')
        self.assertEqual(output, 'status=success\n')
        for value in ['skipped', 'cancelled', '']:
            with self.subTest(value=value):
                _, output, _ = self.run_step('deployment-status', HEALTH_OUTCOME=value)
                self.assertEqual(output, 'status=deploy-failed\n')

    def test_workflow_wiring_preserves_health_gate_and_order(self):
        ids = [step.get('id') for step in STEPS]
        self.assertLess(ids.index('current-traffic'), ids.index('image'))
        self.assertLess(ids.index('pre-deploy-traffic'), ids.index('deploy-container-app'))
        self.assertGreater(ids.index('pre-deploy-traffic'), ids.index('configure-keyvault-refs'))
        self.assertEqual(BY_ID['configure-keyvault-refs']['env']['EXPECTED_REVISION'],
                         '${{ steps.current-traffic.outputs.current-revision }}')
        self.assertEqual(BY_ID['pre-deploy-traffic']['env']['EXPECTED_REVISION'],
                         '${{ steps.current-traffic.outputs.current-revision }}')
        self.assertEqual(BY_ID['shift-traffic']['env']['EXPECTED_REVISION'],
                         '${{ steps.current-traffic.outputs.current-revision }}')
        self.assertIn("steps.health-check.outcome == 'success'", BY_ID['shift-traffic']['if'])
        self.assertEqual(BY_ID['deployment-status']['if'], 'always()')
        summary = next(step['run'] for step in STEPS if step['name'] == 'Deployment summary')
        self.assertIn('steps.current-traffic.outcome', summary)
        rollback = next(step['run'] for step in STEPS if step['name'] == 'Rollback guidance')
        self.assertIn('Read current traffic before taking action', rollback)
        self.assertNotIn('Traffic was not shifted', rollback)
        self.assertIn("traffic-percent || 'not confirmed'", summary)
        ci = (ROOT / '.github/workflows/actions-ci.yml').read_text()
        self.assertIn('test_container_app_deployment.py', ci)


if __name__ == '__main__':
    unittest.main()
