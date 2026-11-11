#!/usr/bin/env python3
"""Read the baseline's SDK pin without checking out or executing baseline code."""
import json
import os
from pathlib import Path
import re
import tempfile
from check import run


def parse_global_json(source):
    """Accept SDK JSON comments while preserving string contents."""
    # Match strings before comments so URLs, escaped quotes and comment-like
    # string values are never modified. Keep newlines for useful parse errors.
    tokens = re.compile(r'"(?:[^"\\]|\\.)*"|//[^\r\n]*|/\*[\s\S]*?\*/')
    source = tokens.sub(lambda m: m[0] if m[0].startswith('"') else
                        ''.join('\n' if c == '\n' else ' ' for c in m[0]), source)
    data = json.loads(source.lstrip('\ufeff'))
    if not isinstance(data, dict):
        raise ValueError('Baseline global.json must contain a JSON object')
    sdk = data.get('sdk', {})
    if not isinstance(sdk, dict):
        raise ValueError('Baseline global.json sdk must be an object')
    if 'version' in sdk and (not isinstance(sdk['version'], str) or not sdk['version'].strip()):
        raise ValueError('Baseline global.json sdk.version must be a nonempty string')
    return data


def main():
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
        data = parse_global_json(result.stdout)
        if 'version' not in data.get('sdk', {}):
            # A nearest global.json without a pin is valid and terminates SDK
            # config lookup. Do not inherit a more distant ancestor's version.
            # The baseline worktree retains this exact file for the actual build.
            break
        # setup-dotnet needs strict JSON. Normalize only this installer copy;
        # never rewrite the baseline's configuration or its SDK resolution policy.
        target = Path(tempfile.mkdtemp(prefix='api-sdk-', dir=os.environ['RUNNER_TEMP'])) / 'global.json'
        target.write_text(json.dumps(data))
        with open(os.environ['GITHUB_OUTPUT'], 'a') as output:
            output.write(f'global-json={target}\n')
        break


if __name__ == '__main__':
    main()
