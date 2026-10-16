#!/usr/bin/env python3
"""Validate current-run scanner evidence, report it, then gate in a separate step."""
import argparse
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import sys


SEVERITIES = ('low', 'moderate', 'high', 'critical', 'unknown')
SCANNERS = ('dependency', 'sast', 'secret', 'iac')


def require(condition, message):
    if not condition:
        raise ValueError(message)


def read_json(path):
    with path.open(encoding='utf-8') as stream:
        return json.load(stream)


def counts_for(severities):
    return {severity: severities.count(severity) for severity in SEVERITIES}


def dependency_counts(root):
    data = read_json(root / 'vulnerability-report/dependencies/summary.json')
    require(isinstance(data, dict), 'Dependency summary must be an object')
    require(data.get('status') in ('clean', 'findings', 'error'), 'Invalid dependency status')
    require(isinstance(data.get('errors'), list) and all(isinstance(error, str) for error in data['errors']),
            'Missing or invalid dependency errors')
    require((data['status'] == 'error') == bool(data['errors']), 'Dependency error status disagrees with errors')
    projects = data.get('projects')
    require(isinstance(projects, list) and projects, 'No dependency projects scanned')
    for project in projects:
        require(isinstance(project, dict) and project.get('status') in ('clean', 'findings', 'error'),
                'Invalid dependency project scan')
        if project['status'] == 'error':
            require(data['status'] == 'error', 'Dependency project error missing from summary')
        else:
            require(type(project.get('exitCode')) is int and project['exitCode'] == 0,
                    'Dependency project command failed')
    findings = data.get('findings')
    require(isinstance(findings, list), 'Missing dependency findings')
    severities = []
    for finding in findings:
        require(isinstance(finding, dict) and finding.get('severity') in SEVERITIES[:-1],
                'Invalid dependency finding severity')
        severities.append(finding['severity'])
    counts = counts_for(severities)
    require(data.get('counts') == {key: counts[key] for key in SEVERITIES[:-1]},
            'Dependency counts disagree with findings')
    if data['status'] != 'error':
        require(data['status'] == ('findings' if findings else 'clean'), 'Dependency status disagrees with findings')
    errors = ['Dependency scanner reported incomplete or failed project scans'] if data['errors'] else []
    return counts, errors


def severity_for(result, rule, scanner):
    if scanner == 'secret':
        return 'critical'
    for source in (result, rule):
        properties = source.get('properties', {})
        require(isinstance(properties, dict), 'Invalid SARIF properties')
        if 'security-severity' in properties:
            try:
                score = float(properties['security-severity'])
            except (ValueError, TypeError):
                raise ValueError('Invalid SARIF security severity') from None
            require(math.isfinite(score) and 0 <= score <= 10, 'Invalid SARIF security severity')
            return 'critical' if score >= 9 else 'high' if score >= 7 else 'moderate' if score >= 4 else 'low'
        severity = properties.get('severity')
        if isinstance(severity, str) and severity.lower() in (*SEVERITIES, 'medium'):
            return 'moderate' if severity.lower() == 'medium' else severity.lower()
    configuration = rule.get('defaultConfiguration', {})
    require(isinstance(configuration, dict), 'Invalid SARIF default configuration')
    level = result.get('level', configuration.get('level'))
    return {'error': 'high', 'warning': 'moderate', 'note': 'low', 'none': 'low'}.get(level, 'unknown')


def referenced_component(tool, reference):
    """Resolve SARIF 2.1.0 section 3.54 without crossing component namespaces."""
    require(isinstance(reference, dict), 'Invalid SARIF tool component reference')
    extensions = tool.get('extensions', [])
    require(isinstance(extensions, list) and all(isinstance(item, dict) for item in extensions),
            'Invalid SARIF tool extensions')
    if 'index' in reference:
        index = reference['index']
        require(type(index) is int and 0 <= index < len(extensions), 'Invalid SARIF tool component index')
        component = extensions[index]
    elif 'guid' in reference:
        matches = [item for item in [tool['driver'], *extensions] if item.get('guid') == reference['guid']]
        require(len(matches) == 1, 'Unresolved or ambiguous SARIF tool component')
        component = matches[0]
    else:
        component = tool['driver']
    for key in ('name', 'guid'):
        if key in reference:
            require(isinstance(reference[key], str) and bool(reference[key]) and
                    reference[key] == component.get(key), 'SARIF tool component identity mismatch')
    return component


def referenced_rule(tool, result):
    """Resolve nested and legacy rule references, rejecting conflicting metadata."""
    reference = result.get('rule', {})
    require(isinstance(reference, dict), 'Invalid SARIF rule reference')
    reference = reference.copy()
    for source, key in ((reference, 'index'), (result, 'ruleIndex')):
        if key in source:
            require(type(source[key]) is int and source[key] >= 0, 'Invalid SARIF rule index')
    for nested, legacy in (('id', 'ruleId'), ('index', 'ruleIndex')):
        if legacy in result:
            require(nested not in reference or reference[nested] == result[legacy],
                    'SARIF rule reference mismatch')
            reference[nested] = result[legacy]
    for key in ('id', 'guid'):
        if key in reference:
            require(isinstance(reference[key], str) and (key == 'id' or bool(reference[key])),
                    'Invalid SARIF rule identity')
    component = referenced_component(tool, reference.get('toolComponent', {}))
    rules = component.get('rules', [])
    require(isinstance(rules, list) and all(isinstance(rule, dict) for rule in rules), 'Invalid SARIF rules')
    if 'index' in reference:
        index = reference['index']
        require(type(index) is int and 0 <= index < len(rules), 'Invalid SARIF rule index')
        rule = rules[index]
    else:
        identities = ['guid'] if 'guid' in reference else ['id'] if 'id' in reference else []
        matches = [rule for rule in rules if identities and
                   all(rule.get(key) == reference[key] for key in identities)]
        require(len(matches) <= 1, 'Ambiguous SARIF rule identity')
        # A result can carry its own severity without an embedded descriptor.
        # An explicit rule reference, however, promises that descriptor exists.
        require(matches or 'rule' not in result, 'Unresolved SARIF rule reference')
        rule = matches[0] if matches else None
    if rule is None:
        return {}
    require(isinstance(rule.get('id'), str), 'Missing or invalid SARIF descriptor identity')
    if 'id' in reference:
        descriptor_id = rule.get('id')
        # SARIF permits one extra result-specific hierarchical ID component.
        parent_id, separator, _ = reference['id'].rpartition('/')
        require(reference['id'] == descriptor_id or
                bool(separator and parent_id == descriptor_id), 'SARIF rule identity mismatch')
    if 'guid' in reference:
        require(reference['guid'] == rule.get('guid'), 'SARIF rule identity mismatch')
    return rule


def sarif_counts(root, scanner):
    directory = {'sast': 'sast-report', 'secret': 'secret-scan-report', 'iac': 'iac-security-report'}[scanner]
    paths = sorted((root / directory).rglob('*.sarif'))
    require(bool(paths), 'Missing SARIF evidence')
    severities = []
    for path in paths:
        data = read_json(path)
        require(isinstance(data, dict) and data.get('version') == '2.1.0', 'Invalid SARIF version')
        runs = data.get('runs')
        require(isinstance(runs, list) and runs, 'SARIF has no runs')
        for run in runs:
            require(isinstance(run, dict), 'Invalid SARIF run')
            tool = run.get('tool')
            require(isinstance(tool, dict) and isinstance(tool.get('driver'), dict), 'Missing SARIF tool')
            driver = tool['driver']
            require(isinstance(driver.get('name'), str) and driver['name'].strip(), 'Missing SARIF tool name')
            invocations = run.get('invocations', [])
            require(isinstance(invocations, list), 'Invalid SARIF invocations')
            for invocation in invocations:
                require(isinstance(invocation, dict) and invocation.get('executionSuccessful') is True,
                        'SARIF invocation failed or lacks success status')
            rules = driver.get('rules', [])
            require(isinstance(rules, list) and all(isinstance(rule, dict) for rule in rules), 'Invalid SARIF rules')
            results = run.get('results')
            require(isinstance(results, list), 'Missing SARIF results')
            for result in results:
                require(isinstance(result, dict), 'Invalid SARIF result')
                message = result.get('message')
                require(isinstance(message, dict) and any(isinstance(message.get(key), str) and message[key]
                        for key in ('text', 'markdown', 'id')), 'Missing SARIF result message')
                rule = referenced_rule(tool, result)
                severities.append(severity_for(result, rule, scanner))
    return counts_for(severities)


def env_bool(env, key):
    value = env.get(key, '')
    require(value in ('true', 'false'), f'Missing or invalid {key}')
    return value == 'true'


def consolidate(root, env):
    scans = {}
    errors = []
    if env.get('DOWNLOAD_OUTCOME') != 'success':
        errors.append('Security artifact download did not succeed')
    try:
        high_gate = env_bool(env, 'FAIL_ON_HIGH_SEVERITY')
    except ValueError as error:
        high_gate = True
        errors.append(str(error))
    for name in SCANNERS:
        result = env.get(f'{name.upper()}_RESULT', '')
        scan = {'job_result': result, 'status': 'error', 'count': None, 'counts': None, 'errors': [], 'blocked': True}
        scans[name] = scan
        try:
            enabled = True if name == 'dependency' else env_bool(env, {
                'sast': 'ENABLE_SAST', 'secret': 'ENABLE_SECRET_SCAN', 'iac': 'ENABLE_IAC_SCAN'}[name])
            scan['enabled'] = enabled
            if not enabled:
                require(result == 'skipped', 'Disabled scanner job was not skipped')
                scan.update(status='disabled', count=0, counts=counts_for([]), blocked=False)
                continue
            if result != 'success':
                scan['errors'].append(f'Enabled scanner job result is {result or "missing"}')
            if name == 'iac' and env.get('IAC_HAS_TARGETS') == 'false':
                require(result == 'success', 'IaC target detection did not complete successfully')
                scan.update(status='no-targets', count=0, counts=counts_for([]), blocked=False)
                continue
            if name == 'iac':
                require(env.get('IAC_HAS_TARGETS') == 'true', 'Missing or invalid IaC target detection')
            if name == 'dependency':
                counts, dependency_errors = dependency_counts(root)
                scan['errors'].extend(dependency_errors)
            else:
                counts = sarif_counts(root, name)
            count = sum(counts.values())
            scan.update(count=count, counts=counts)
            if name == 'dependency':
                execution = read_json(root / 'vulnerability-report/execution.json')
                require(isinstance(execution, dict), 'Missing dependency execution status')
                if execution.get('restore') != 'success':
                    scan['errors'].append('Dependency restore did not succeed')
                if execution.get('scan') != ('failure' if count else 'success'):
                    scan['errors'].append('Dependency scan outcome disagrees with validated report')
            blocked = bool(scan['errors']) or (count > 0 if name == 'dependency' else
                      counts['critical'] + counts['unknown'] > 0 or high_gate and counts['high'] > 0)
            scan.update(status='error' if scan['errors'] else 'findings' if count else 'clean',
                        count=count, counts=counts, blocked=blocked)
        except (OSError, ValueError, TypeError, KeyError) as error:
            # Do not echo raw scanner content, which may contain secrets.
            reason = str(error) if isinstance(error, ValueError) and not isinstance(error, json.JSONDecodeError) else 'Missing or invalid scanner evidence'
            scan['errors'].append(reason)
    total = sum(scan['count'] for scan in scans.values() if scan['count'] is not None)
    complete = all(scan['count'] is not None and not scan['errors'] for scan in scans.values()) and not errors
    blocked = bool(errors) or any(scan['blocked'] for scan in scans.values())
    return {'schema_version': 1, 'scan_date': datetime.now(timezone.utc).isoformat(),
            'repository': env.get('GITHUB_REPOSITORY', ''), 'source': 'current-run-local-artifacts',
            'fail_on_high_severity': high_gate, 'scans': scans, 'errors': errors,
            'summary': {'total_issues': total if complete else None, 'known_issues': total, 'complete': complete},
            'blocked': blocked, 'gate_passed': not blocked}


def summary_markdown(report):
    lines = ['# Nightly Security Scan Results', '',
             '| Scanner | Status | Job result | Findings |', '|---|---|---|---|']
    for name, scan in report['scans'].items():
        count = 'unknown' if scan['count'] is None else str(scan['count'])
        lines.append(f"| {name} | {scan['status']} | {scan['job_result'] or 'missing'} | {count} |")
    lines.extend(['', f"Known findings: {report['summary']['known_issues']}",
                  f"Evidence complete: {str(report['summary']['complete']).lower()}",
                  f"Final gate: {'FAILED' if report['blocked'] else 'PASSED'}", '',
                  'Counts come from this run’s validated artifacts; GitHub alert dismissals are not applied.'])
    for name, scan in report['scans'].items():
        lines.extend(f'- {name}: {error}' for error in scan['errors'])
    lines.extend(f'- {error}' for error in report['errors'])
    return '\n'.join(lines) + '\n'


def check_gate(report):
    require(isinstance(report, dict) and report.get('schema_version') == 1, 'Invalid consolidated report')
    require(report.get('blocked') is False and report.get('gate_passed') is True, 'Security gate blocked')
    require(report.get('errors') == [], 'Aggregate errors or missing error status')
    require(isinstance(report.get('fail_on_high_severity'), bool), 'Missing threshold policy')
    scans = report.get('scans')
    require(isinstance(scans, dict) and set(scans) == set(SCANNERS), 'Missing scanner results')
    for name, scan in scans.items():
        require(isinstance(scan, dict) and scan.get('blocked') is False and scan.get('errors') == [], 'Scanner blocked')
        status = scan.get('status')
        require(status in ('clean', 'findings', 'disabled', 'no-targets'), 'Invalid scanner status')
        require(scan.get('job_result') == ('skipped' if status == 'disabled' else 'success'), 'Scanner job did not succeed')
        require(scan.get('enabled') is (status != 'disabled'), 'Invalid scanner enabled status')
        require(status != 'disabled' or name != 'dependency', 'Dependencies cannot be disabled')
        require(status != 'no-targets' or name == 'iac', 'Invalid no-targets scanner')
        counts = scan.get('counts')
        require(isinstance(counts, dict) and set(counts) == set(SEVERITIES), 'Missing severity counts')
        require(all(type(value) is int and value >= 0 for value in counts.values()), 'Invalid severity counts')
        require(type(scan.get('count')) is int and scan['count'] == sum(counts.values()), 'Invalid finding count')
        require((status == 'findings') == (scan['count'] > 0), 'Status disagrees with findings')
        require(not (name == 'dependency' and scan['count']), 'Dependency vulnerabilities block the gate')
        require(not (counts['critical'] + counts['unknown'] or report['fail_on_high_severity'] and counts['high']),
                'High, critical, or unknown severity findings block the gate')
    summary = report.get('summary', {})
    total = sum(scan['count'] for scan in scans.values())
    require(summary == {'total_issues': total, 'known_issues': total, 'complete': True}, 'Invalid aggregate summary')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('consolidate', 'gate'))
    parser.add_argument('--reports-root', type=Path, default=Path('all-security-reports'))
    parser.add_argument('--report', type=Path, default=Path('consolidated-security-report.json'))
    parser.add_argument('--summary', type=Path, default=Path('security-summary.md'))
    args = parser.parse_args()
    if args.command == 'gate':
        try:
            check_gate(read_json(args.report))
        except (OSError, ValueError, TypeError, KeyError) as error:
            print(f'Security gate failed: {error}', file=sys.stderr)
            return 1
        print('Security gate passed')
        return 0
    report = consolidate(args.reports_root, os.environ)
    args.report.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    markdown = summary_markdown(report)
    args.summary.write_text(markdown, encoding='utf-8')
    if os.environ.get('GITHUB_STEP_SUMMARY'):
        with open(os.environ['GITHUB_STEP_SUMMARY'], 'a', encoding='utf-8') as stream:
            stream.write(markdown)
    if os.environ.get('GITHUB_OUTPUT'):
        outputs = {'total_issues': report['summary']['total_issues'], 'known_issues': report['summary']['known_issues'],
                   'gate_passed': str(report['gate_passed']).lower()}
        for name, output in zip(SCANNERS, ('vuln_count', 'sast_count', 'secret_count', 'iac_count')):
            outputs[output] = report['scans'][name]['count']
        with open(os.environ['GITHUB_OUTPUT'], 'a', encoding='utf-8') as stream:
            for key, value in outputs.items():
                stream.write(f'{key}={"unknown" if value is None else value}\n')
    return 0  # Publishing evidence precedes the separate fail-closed gate.


if __name__ == '__main__':
    sys.exit(main())

