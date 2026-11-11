#!/usr/bin/env python3
"""Fail-closed compiled contract comparison; no network fetch of baseline refs."""
import datetime
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile

HERE = Path(__file__).resolve().parent


def run(args, cwd, check=True):
    result = subprocess.run([str(a) for a in args], cwd=cwd, text=True,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    if check and result.returncode:
        raise RuntimeError(f"Command failed ({result.returncode}): {args[0:3]}\n{result.stdout}")
    return result


def target_at(cwd, value):
    if value:
        target = (cwd / value).resolve()
    else:
        candidates = sorted([*cwd.glob('*.sln'), *cwd.glob('*.slnx')])
        if not candidates:
            candidates = sorted(cwd.glob('*.csproj'))
        if len(candidates) != 1:
            raise RuntimeError('Specify project-path: expected exactly one solution or project in working-directory')
        target = candidates[0]
    if not target.is_file() or target.suffix not in ('.csproj', '.sln', '.slnx'):
        raise RuntimeError(f'Missing or unsupported build target: {target}')
    return target


def build(root, cwd, target, inventory):
    run(['dotnet', 'build', target, '-c', 'Release', '--disable-build-servers',
         '-m:1', '-nr:false', '-p:UseSharedCompilation=false',
         f'-p:CustomAfterMicrosoftCommonTargets={HERE / "collect.targets"}',
         f'-p:ApiInventory={inventory}'], cwd)
    if not inventory.is_file():
        raise RuntimeError('Build produced no public library inventory (test/executable-only targets are unsupported)')
    assemblies = {}
    for line in inventory.read_text().splitlines():
        project, framework, binary, refs = line.split('|', 3)
        project = Path(project).resolve()
        if not project.is_relative_to(root):
            raise RuntimeError(f'Project outside repository: {project}')
        key = (str(project.relative_to(root)), framework)
        binary = Path(binary)
        references = refs.split(',') if refs else []
        if not binary.is_file() or any(not Path(ref).is_file() for ref in references):
            raise RuntimeError(f'Missing assembly or reference for {key}')
        value = (binary, references)
        if key in assemblies and assemblies[key] != value:
            raise RuntimeError(f'Ambiguous build outputs for {key}')
        assemblies[key] = value
    if not assemblies:
        raise RuntimeError('Empty assembly inventory')
    return assemblies


def compare(tool, baseline, current, cwd):
    changes, comparisons = [], []
    for key, (left, lrefs) in sorted(baseline.items()):
        right_key = key
        if key not in current:
            match = re.fullmatch(r'net(\d+)\.(\d+)', key[1])
            candidates = []
            if match:
                version = tuple(map(int, match.groups()))
                for candidate in current:
                    other = re.fullmatch(r'net(\d+)\.(\d+)', candidate[1])
                    if candidate[0] == key[0] and other:
                        candidate_version = tuple(map(int, other.groups()))
                        if candidate_version > version:
                            candidates.append((candidate_version, candidate))
            if not candidates:
                changes.append(f'Removed project/framework contract: {key[0]} ({key[1]})')
                continue
            right_key = min(candidates)[1]
        right, rrefs = current[right_key]
        if not left.is_file() or not right.is_file() or any(not Path(ref).is_file() for ref in lrefs + rrefs):
            raise RuntimeError(f'Missing comparison assembly or reference for {key}')
        result = run([tool, '-l', left, '-r', right, '--lref', ','.join(lrefs),
                      '--rref', ','.join(rrefs)], cwd, check=False)
        diagnostics = re.findall(r'^CP0\d{3}:.*$', result.stdout, re.MULTILINE)
        # CP diagnostics indicate incompatibility; any other failure or assembly
        # resolution diagnostic is an infrastructure error even in warning mode.
        if (result.returncode and not diagnostics) or re.search(r'\b(?:CP[1-9]\d{3}|CS\d+|error (?!CP\d+:))', result.stdout):
            raise RuntimeError(f'ApiCompat could not compare {key}:\n{result.stdout}')
        if result.returncode == 0 and diagnostics:
            raise RuntimeError(f'Unexpected ApiCompat result for {key}:\n{result.stdout}')
        changes.extend(line for line in result.stdout.splitlines() if re.match(r'CP0\d{3}:', line))
        comparisons.append({'project': key[0], 'framework': key[1], 'current_framework': right_key[1], 'output': result.stdout})
    return changes, comparisons


def main():
    cwd = Path.cwd().resolve()
    output = (cwd / os.environ.get('API_OUTPUT', './api-compat-reports')).resolve()
    output.mkdir(parents=True, exist_ok=True)
    report_path = output / 'api-compat-report.json'
    report = {'scan_date': datetime.datetime.now(datetime.timezone.utc).isoformat(),
              'status': 'error', 'breaking_changes': None}
    exit_code = 1
    try:
        if os.environ.get('API_BASELINE_PATH'):
            raise RuntimeError('baseline-path text snapshots are unsupported: they cannot prove binary compatibility. Clear baseline-path and use baseline-ref with compiled assemblies.')
        root = Path(run(['git', 'rev-parse', '--show-toplevel'], cwd).stdout.strip()).resolve()
        relative_cwd = cwd.relative_to(root)
        current_target = target_at(cwd, os.environ.get('API_PROJECT', ''))
        relative_target = current_target.relative_to(root)
        ref = os.environ.get('API_BASELINE_REF', 'origin/main')
        sha = run(['git', 'rev-parse', '--verify', '--end-of-options', ref + '^{commit}'], root).stdout.strip()
        report['baseline_commit'] = sha
        with tempfile.TemporaryDirectory(prefix='api-compat-') as temp:
            temp = Path(temp)
            baseline_root = temp / 'baseline'
            run(['git', 'worktree', 'add', '--detach', baseline_root, sha], root)
            try:
                baseline_cwd = baseline_root / relative_cwd
                baseline_target = target_at(baseline_cwd, str(baseline_root / relative_target))
                # Honor each checkout's global.json. A missing baseline SDK must
                # fail, never build the baseline under silently substituted SDKs.
                baseline = build(baseline_root, baseline_cwd, baseline_target, temp / 'baseline.txt')
                current = build(root, cwd, current_target, temp / 'current.txt')
                tool_dir = temp / 'tool'
                run(['dotnet', 'tool', 'install', 'Microsoft.DotNet.ApiCompat.Tool',
                     '--version', '11.0.100', '--tool-path', tool_dir], temp)
                changes, comparisons = compare(tool_dir / 'apicompat', baseline, current, temp)
                migrations = [c for c in comparisons if c['framework'] != c['current_framework']]
                if migrations:
                    print('::warning::Target framework support was retired; a newer-framework API comparison does not preserve old runtime compatibility.')
                report.update(status='breaking-changes-detected' if changes else ('api-compatible-framework-support-changed' if migrations else 'compatible'),
                              framework_migrations=[{'project': c['project'], 'baseline': c['framework'], 'current': c['current_framework']} for c in migrations],
                              breaking_changes=len(changes), changes=changes, comparisons=comparisons)
                exit_code = int(bool(changes) and os.environ.get('API_FAIL_ON_BREAKING', 'true').lower() != 'false')
            finally:
                run(['git', 'worktree', 'remove', '--force', baseline_root], root)
    except (RuntimeError, OSError, ValueError) as error:
        exit_code = 1
        report.update(status='error', breaking_changes=None, error=str(error))
        print(f'::error::{error}')
    finally:
        report_path.write_text(json.dumps(report, indent=2) + '\n')
        if os.environ.get('GITHUB_OUTPUT'):
            with open(os.environ['GITHUB_OUTPUT'], 'a') as stream:
                stream.write(f'report-path={report_path}\n')
                if report['breaking_changes'] is not None:
                    stream.write(f'breaking-changes={report["breaking_changes"]}\n')
        print(json.dumps(report, indent=2))
    return exit_code


if __name__ == '__main__':
    raise SystemExit(main())
