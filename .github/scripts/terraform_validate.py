"""Credential-free Terraform checks; no live plan/apply/import/backend operation.

Run in a disposable checkout: the shared lock is staged into each root.
"""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import hcl2


def targets(repository):
    repository = Path(repository).resolve()
    roots = json.loads((repository / 'terraform-roots.json').read_text())
    if not isinstance(roots, list) or not roots or not all(isinstance(root, str) for root in roots) or len(roots) != len(set(roots)):
        raise ValueError('Expected a nonempty unique root list')
    result = []
    for root in roots:
        path = (repository / root).resolve()
        if not path.is_relative_to(repository) or path == repository:
            raise ValueError('Terraform roots must remain within the checkout')
        if not (path / 'main.tf').is_file():
            raise ValueError(f'Missing root: {root}')
        result.append(path)
    result += sorted(p.parent.resolve() for p in (repository / 'modules').glob('*/*/main.tf'))
    if len(result) != len(set(result)) or any(not path.is_relative_to(repository) for path in result):
        raise ValueError('Module targets must be unique and remain within the checkout')
    return result


def require_mocked_plans(path):
    test = path / 'tests' / 'safety.tftest.hcl'
    if list((path / 'tests').glob('*.tftest.*')) != [test] or list(path.glob('*.tftest.*')):
        raise ValueError(f'{path}: exactly one safety.tftest.hcl test file is required')
    with test.open(encoding='utf-8') as stream:
        document = hcl2.load(stream)
    mocks = {name for item in document.get('mock_provider', []) for name in item}
    if mocks != {'azurerm'} or document.get('provider'):
        raise ValueError(f'{test}: only the mocked AzureRM provider is allowed')
    if any('alias' in body for item in document['mock_provider'] for body in item.values()):
        raise ValueError(f'{test}: the default AzureRM provider must be mocked')
    runs = document.get('run', [])
    if not runs:
        raise ValueError(f'{test}: at least one test is required')
    for run in runs:
        for config in run.values():
            if config.get('command') != '${plan}' or 'providers' in config or 'module' in config:
                raise ValueError(f'{test}: only mocked plans of this module are allowed')
    return sum(len(run) for run in runs)


def require_azurerm_only(path, allowed_paths):
    if list(path.glob('*.tf.json')):
        raise ValueError('JSON configurations need an explicit validator contract extension')
    for file in path.glob('*.tf'):
        with file.open(encoding='utf-8') as stream:
            document = hcl2.load(stream)
        for block in document.get('terraform', []):
            for providers in block.get('required_providers', []):
                if set(providers) != {'azurerm'} or providers['azurerm']['source'] != 'hashicorp/azurerm':
                    raise ValueError(f'{file}: only the mocked HashiCorp AzureRM provider is supported')
        for block in document.get('provider', []):
            if set(block) != {'azurerm'} or 'alias' in block['azurerm']:
                raise ValueError(f'{file}: provider aliases need explicit mock coverage')
        for block in document.get('module', []):
            for module in block.values():
                source = module.get('source', '')
                if not source.startswith(('./', '../')) or (path / source).resolve() not in allowed_paths or 'providers' in module:
                    raise ValueError(f'{file}: module must be a validated local target with the default mocked provider')
        for kind in ('resource', 'data'):
            for block in document.get(kind, []):
                if any(not name.startswith('azurerm_') for name in block):
                    raise ValueError(f'{file}: resource/data source needs mock coverage')
                if any('provider' in body for resources in block.values() for body in resources.values()):
                    raise ValueError(f'{file}: resource provider overrides need explicit mock coverage')


def verify_test_result(output, expected):
    events = [json.loads(line) for line in output.splitlines() if line.strip()]
    summaries = [event['test_summary'] for event in events if event.get('type') == 'test_summary']
    if len(summaries) != 1 or summaries[0] != {
        'status': 'pass', 'passed': expected, 'failed': 0, 'errored': 0, 'skipped': 0,
    }:
        raise ValueError('Terraform must execute and pass every declared test; missing/zero/skipped results fail')
    if any(event.get('type') == 'diagnostic' for event in events):
        raise ValueError('Terraform test diagnostics require review; warnings are not silently ignored')
    print(f'{expected} mocked plan tests passed', flush=True)


def validate(repository, terraform='terraform', run=subprocess.run):
    repository = Path(repository).resolve()
    paths = targets(repository)
    for path in paths:
        require_azurerm_only(path, set(paths))
    counts = {path: require_mocked_plans(path) for path in paths}
    env = os.environ.copy()
    env.update(TF_IN_AUTOMATION='1', TF_INPUT='0', ARM_USE_CLI='false', ARM_USE_MSI='false', ARM_USE_OIDC='false')
    run([terraform, f'-chdir={repository}', 'fmt', '-check', '-recursive'], check=True, env=env)
    lock = repository / '.terraform.lock.hcl'
    if not lock.is_file():
        raise ValueError('Commit the reviewed shared provider lock file')
    for path in paths:
        print(f'Validating {path.relative_to(repository)}', flush=True)
        shutil.copyfile(lock, path / '.terraform.lock.hcl')
        for command in (
            ['init', '-backend=false', '-input=false', '-lockfile=readonly', '-no-color'],
            ['validate', '-no-color'],
        ):
            run([terraform, f'-chdir={path}', *command], check=True, env=env)
        try:
            result = run([terraform, f'-chdir={path}', 'test', '-json'], check=True, env=env, capture_output=True, text=True)
        except subprocess.CalledProcessError as error:
            # Only synthetic mocked tests reach this branch; expose their failures.
            print(error.stdout or '', file=sys.stderr)
            print(error.stderr or '', file=sys.stderr)
            raise
        verify_test_result(result.stdout, counts[path])
    print(f'Validated {len(paths)} Terraform roots/modules with mocked plans; no backend or Azure authentication.')


if __name__ == '__main__':
    validate(sys.argv[1] if len(sys.argv) > 1 else '.', os.environ.get('TERRAFORM_BIN', 'terraform'))
