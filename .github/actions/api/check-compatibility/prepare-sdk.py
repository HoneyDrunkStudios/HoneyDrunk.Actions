#!/usr/bin/env python3
"""Read the baseline's SDK pin without checking out or executing baseline code."""
import json
import os
from pathlib import Path
import tempfile
from check import run

cwd = Path.cwd().resolve()
root = Path(run(['git', 'rev-parse', '--show-toplevel'], cwd).stdout.strip()).resolve()
ref = os.environ['API_BASELINE_REF']
sha = run(['git', 'rev-parse', '--verify', '--end-of-options', ref + '^{commit}'], root).stdout.strip()
relative = cwd.relative_to(root)
for directory in (relative, *relative.parents):
    path = (directory / 'global.json').as_posix()
    result = run(['git', 'show', f'{sha}:{path}'], root, check=False)
    if result.returncode:
        continue
    data = json.loads(result.stdout)
    if not isinstance(data.get('sdk', {}).get('version'), str):
        raise RuntimeError(f'Baseline {path} has no sdk.version')
    # setup-dotnet installs the baseline SDK independently of the current pin.
    target = Path(tempfile.mkdtemp(prefix='api-sdk-', dir=os.environ['RUNNER_TEMP'])) / 'global.json'
    target.write_text(json.dumps(data))
    with open(os.environ['GITHUB_OUTPUT'], 'a') as output:
        output.write(f'global-json={target}\n')
    break
