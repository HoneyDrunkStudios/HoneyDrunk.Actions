"""Exercise shipped revision, health and traffic boundaries with Azure/HTTP stubbed."""

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
APP_FQDN = APP + '.example.azurecontainerapps.io'
NEW_FQDN = NEW + '.example.azurecontainerapps.io'
REVISION_ACTION = yaml.safe_load((ROOT / '.github/actions/azure/deploy-container-app/action.yml').read_text())
REVISION_SCRIPT = REVISION_ACTION['runs']['steps'][0]['run']


def target(revision=PREVIOUS, weight=100, **extra):
    return dict(revisionName=revision, weight=weight, **extra)


def revision(state='Running', fqdn=NEW_FQDN, name=NEW):
    return dict(name=name, properties=dict(runningState=state, fqdn=fqdn))


class RevisionShellTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.work = Path(self.temp.name)
        self.calls = self.work / 'calls'
        self.output = self.work / 'output'
        self.sleeps = self.work / 'sleeps'
        self.urls = self.work / 'urls'
        self.responses = self.work / 'responses.json'
        self.responses.write_text(json.dumps([revision()]))
        (self.work / '.actions').symlink_to(ROOT, target_is_directory=True)
        self.env = dict(os.environ, APP_NAME=APP, RESOURCE_GROUP='rg-test',
                        IMAGE='registry.example/collector@sha256:' + 'a' * 64,
                        REVISION_SUFFIX='candidate', STARTUP_WAIT='0', READY_TIMEOUT='10',
                        PATH=str(self.work) + os.pathsep + os.environ['PATH'],
                        GITHUB_OUTPUT=str(self.output), AZ_CALLS=str(self.calls),
                        RESPONSES=str(self.responses), POLL_COUNT=str(self.work / 'count'),
                        SLEEPS=str(self.sleeps), PROBE_URLS=str(self.urls),
                        APP_FQDN=APP_FQDN,
                        HEALTH_CHECK_URL='/health', HEALTH_CHECK_TIMEOUT='10', HTTP_CODE='200',
                        NEW_REVISION=NEW, CURRENT_REVISION=PREVIOUS,
                        EXPECTED_REVISION=PREVIOUS, TRAFFIC_SHIFT_MODE='full')
        self.write_command('az', '''#!/usr/bin/env python3
import json, os, sys
from pathlib import Path
args = sys.argv[1:]
with Path(os.environ['AZ_CALLS']).open('a') as stream:
    stream.write(json.dumps(args) + '\\n')
if args[:3] == ['containerapp', 'revision', 'copy']:
    sys.exit(int(os.environ.get('AZ_COPY_EXIT', '0')))
if args[:3] == ['containerapp', 'revision', 'show']:
    count = Path(os.environ['POLL_COUNT'])
    index = int(count.read_text()) if count.exists() else 0
    count.write_text(str(index + 1))
    responses = json.loads(Path(os.environ['RESPONSES']).read_text())
    response = responses[min(index, len(responses) - 1)]
    print(response if isinstance(response, str) else json.dumps(response))
    sys.exit(int(os.environ.get('AZ_READ_EXIT', '0')))
if args[:2] == ['containerapp', 'show']:
    # Deliberately healthy old app ingress: this must never be a fallback.
    print(os.environ['APP_NAME'] + '.example.azurecontainerapps.io')
    sys.exit(0)
if args[:4] == ['containerapp', 'ingress', 'traffic', 'show']:
    print(json.dumps([dict(revisionName=os.environ['CURRENT_REVISION'], weight=100)]))
    sys.exit(0)
if args[:4] == ['containerapp', 'ingress', 'traffic', 'set']:
    sys.exit(0)
raise SystemExit('Unexpected Azure operation')
''')
        self.write_command('sleep', '#!/usr/bin/env bash\nprintf "%s\\n" "$1" >> "$SLEEPS"\n')
        self.write_command('curl', '''#!/usr/bin/env bash
printf '%s\\n' "${@: -1}" >> "$PROBE_URLS"
if [[ "${@: -1}" == "https://$APP_FQDN/"* ]]; then
    printf '200'
else
    printf '%s' "$HTTP_CODE"
fi
exit "${CURL_EXIT:-0}"
''')

    def write_command(self, name, content):
        path = self.work / name
        path.write_text(content)
        path.chmod(0o755)

    def run_script(self, script, **overrides):
        return subprocess.run(['bash', '-e', '-o', 'pipefail', '-c', script],
                              cwd=self.work, env=dict(self.env, **overrides),
                              capture_output=True, text=True, timeout=10)

    def run_deploy(self, responses=None, **overrides):
        if responses is not None:
            self.responses.write_text(json.dumps(responses))
        return self.run_script(REVISION_SCRIPT, **overrides)

    def text(self, path):
        return path.read_text() if path.exists() else ''

    def azure_calls(self):
        return [json.loads(line) for line in self.text(self.calls).splitlines()]

    def assert_not_deployed(self, result):
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertEqual(self.text(self.output), '')
        self.assertFalse(self.urls.exists())
        self.assertTrue(all(call[:2] != ['containerapp', 'show'] for call in self.azure_calls()))
        self.assertTrue(all(call[:3] != ['containerapp', 'ingress', 'traffic'] for call in self.azure_calls()))

    def test_running_candidate_publishes_only_exact_revision_outputs(self):
        result = self.run_deploy(STARTUP_WAIT='15')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.text(self.output), f'revision-name={NEW}\nrevision-fqdn={NEW_FQDN}\n')
        copy, show = self.azure_calls()
        self.assertEqual(copy, ['containerapp', 'revision', 'copy', '--name', APP,
                               '--resource-group', 'rg-test', '--image', self.env['IMAGE'],
                               '--revision-suffix', 'candidate', '--output', 'none'])
        self.assertEqual(show, ['containerapp', 'revision', 'show', '--name', APP,
                               '--resource-group', 'rg-test', '--revision', NEW, '--output', 'json'])
        self.assertEqual(self.text(self.sleeps), '15\n')

    def test_waits_for_fqdn_after_running(self):
        result = self.run_deploy([revision(fqdn=None), revision(fqdn=''), revision()])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(len(self.azure_calls()), 4)
        self.assertEqual(self.text(self.sleeps), '5\n5\n')
        self.assertIn(f'revision-fqdn={NEW_FQDN}', self.text(self.output))

    def test_waits_for_running_even_with_exact_fqdn(self):
        result = self.run_deploy([revision(state='Processing'), revision()])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.text(self.sleeps), '5\n')

    def test_duration_leading_zeros_are_decimal(self):
        result = self.run_deploy([revision(fqdn=None)], READY_TIMEOUT='008', STARTUP_WAIT='000')
        self.assert_not_deployed(result)
        self.assertIn('within 8s', result.stdout)
        self.assertEqual(self.text(self.sleeps), '5\n3\n')

    def test_startup_wait_leading_zeros_and_largest_timeout_are_supported(self):
        result = self.run_deploy(READY_TIMEOUT='09223372036854775807', STARTUP_WAIT='008')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.text(self.sleeps), '8\n')

    def test_invalid_durations_fail_before_any_azure_write(self):
        sentinel = self.work / 'unexpected-command'
        values = ['', '-1', '1.5', ' 8', '8 ', '1+1', '1e2',
                  '9223372036854775808', '0009223372036854775808', '9' * 100,
                  f'$(touch {sentinel})', f'value[$(touch {sentinel})]']
        for name in ['READY_TIMEOUT', 'STARTUP_WAIT']:
            for value in values:
                with self.subTest(name=name, value=value):
                    self.assert_not_deployed(self.run_deploy(**{name: value}))
                    self.assertEqual(self.azure_calls(), [])
                    self.assertFalse(sentinel.exists())
        self.assertEqual(self.text(self.sleeps), '')

    def test_preserves_top_level_revision_fqdn_response(self):
        response = revision(fqdn=None)
        response['fqdn'] = NEW_FQDN
        result = self.run_deploy([response])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(f'revision-fqdn={NEW_FQDN}', self.text(self.output))

    def test_missing_fqdn_times_out_without_healthy_app_fallback(self):
        result = self.run_deploy([revision(fqdn=None)], READY_TIMEOUT='7')
        self.assert_not_deployed(result)
        self.assertIn('did not expose a revision-specific FQDN within 7s', result.stdout)
        self.assertEqual(self.text(self.sleeps), '5\n2\n')
        self.assertEqual(len(self.azure_calls()), 4)

    def test_old_revision_and_app_ingress_hostnames_are_rejected(self):
        for fqdn in [APP_FQDN, PREVIOUS + '.example.azurecontainerapps.io',
                     NEW + '-old.example.azurecontainerapps.io']:
            with self.subTest(fqdn=fqdn):
                self.assert_not_deployed(self.run_deploy([revision(fqdn=fqdn)]))
        self.assertEqual(self.text(self.sleeps), '')

    def test_invalid_endpoint_cannot_publish_a_url_or_forged_output(self):
        for fqdn in ['https://' + NEW_FQDN, NEW_FQDN + '/health', NEW_FQDN + ':443',
                     NEW_FQDN + '\nhealthy=true', NEW + '..example.io', {'host': NEW_FQDN}]:
            with self.subTest(fqdn=fqdn):
                self.assert_not_deployed(self.run_deploy([revision(fqdn=fqdn)]))

    def test_mismatched_or_missing_revision_identity_is_rejected(self):
        for name in [PREVIOUS, APP, None, '']:
            with self.subTest(name=name):
                self.assert_not_deployed(self.run_deploy([revision(name=name)]))

    def test_readiness_timeout_and_failed_state_publish_no_outputs(self):
        for state in ['Processing', 'Failed', 'Degraded', None]:
            with self.subTest(state=state):
                result = self.run_deploy([revision(state=state)], READY_TIMEOUT='0')
                self.assert_not_deployed(result)
                self.assertIn('did not reach Running state', result.stdout)
        self.assertEqual(self.text(self.sleeps), '')

    def test_copy_and_read_failures_cannot_succeed(self):
        for setting in ['AZ_COPY_EXIT', 'AZ_READ_EXIT']:
            with self.subTest(setting=setting):
                self.assert_not_deployed(self.run_deploy(**{setting: '1'}))

    def test_invalid_json_fails_closed(self):
        self.assert_not_deployed(self.run_deploy(['not json']))

    def test_relative_probe_targets_candidate_before_promotion(self):
        result = self.run_deploy()
        self.assertEqual(result.returncode, 0, result.stderr)
        outputs = dict(line.split('=', 1) for line in self.text(self.output).splitlines())
        probe = self.run_script(BY_ID['health-check']['run'], REVISION_FQDN=outputs['revision-fqdn'])
        self.assertEqual(probe.returncode, 0, probe.stderr)
        self.assertEqual(self.text(self.urls), f'https://{NEW_FQDN}/health\n')
        promoted = self.run_script(BY_ID['shift-traffic']['run'])
        self.assertEqual(promoted.returncode, 0, promoted.stderr)
        self.assertIn(NEW + '=100', self.azure_calls()[-1])

    def test_unhealthy_candidate_fails_even_when_old_ingress_is_healthy(self):
        result = self.run_deploy()
        self.assertEqual(result.returncode, 0, result.stderr)
        probe = self.run_script(BY_ID['health-check']['run'], REVISION_FQDN=NEW_FQDN, HTTP_CODE='503')
        self.assertNotEqual(probe.returncode, 0)
        self.assertIn('healthy=false', self.text(self.output))
        self.assertEqual(self.text(self.urls).splitlines(), [f'https://{NEW_FQDN}/health'] * 2)
        self.assertEqual(len(self.azure_calls()), 2)

    def test_probe_connection_failure_cannot_become_success(self):
        probe = self.run_script(BY_ID['health-check']['run'], REVISION_FQDN=NEW_FQDN,
                                HTTP_CODE='000', CURL_EXIT='7')
        self.assertNotEqual(probe.returncode, 0)
        self.assertEqual(self.text(self.output), 'healthy=false\n')
        self.assertEqual(self.azure_calls(), [])

    def test_input_defaults_and_workflow_failure_gates_are_preserved(self):
        self.assertEqual(REVISION_ACTION['inputs']['startup-wait']['default'], '15')
        self.assertEqual(REVISION_ACTION['inputs']['health-check-timeout']['default'], '120')
        self.assertEqual(WORKFLOW['permissions'], {'contents': 'read', 'id-token': 'write'})
        self.assertFalse(BY_ID['deploy-container-app'].get('continue-on-error', False))
        self.assertFalse(BY_ID['health-check'].get('continue-on-error', False))
        self.assertEqual(BY_ID['health-check']['if'], "${{ inputs.health-check-url != '' }}")
        self.assertEqual(BY_ID['health-check']['env']['REVISION_FQDN'],
                         '${{ steps.deploy-container-app.outputs.revision-fqdn }}')
        self.assertIn("steps.deploy-container-app.outcome == 'success'", BY_ID['shift-traffic']['if'])
        self.assertIn("steps.health-check.outcome == 'success'", BY_ID['shift-traffic']['if'])


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
