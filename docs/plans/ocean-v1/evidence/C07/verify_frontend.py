"""Verify the refreshed legacy frontend using the unchanged dependency lock."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys


output = Path(__file__).resolve().parent
root = output.parents[4]
node_directory = '/Users/jaronchai/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin'
environment = dict(os.environ, PATH=node_directory + os.pathsep + os.environ.get('PATH', ''),
                   NEXT_TELEMETRY_DISABLED='1', DEPLOYMENT_ENV='test', AUTH_MODE='required',
                   ENABLE_MOCK_LOGIN='false', AUTH_SECRET='ci-only-auth-secret-that-is-long-enough',
                   INTERNAL_AUTH_SECRET='ci-only-internal-secret-that-is-long-enough')
lock = json.loads((root / 'frontend/package-lock.json').read_text())
installed = json.loads((root / 'frontend/node_modules/next/package.json').read_text())
assert installed['version'] == lock['packages']['node_modules/next']['version']
receipt = {'locked_next': installed['version'], 'node': subprocess.check_output(
    [node_directory + '/node', '--version'], text=True).strip(), 'checks': []}
for name, command in [('tests', ['npm', 'test']), ('typecheck', ['npm', 'run', 'typecheck']),
                      ('build', ['npm', 'run', 'build'])]:
    with (output / f'frontend-refreshed-{name}.txt').open('w') as log:
        process = subprocess.run(command, cwd=root / 'frontend', env=environment,
                                 stdout=log, stderr=subprocess.STDOUT)
    receipt['checks'].append({'name': name, 'command': command, 'exit_code': process.returncode})
    if process.returncode:
        break
(output / 'frontend-refreshed-result.json').write_text(json.dumps(receipt, indent=2) + '\n')
print(json.dumps(receipt))
sys.exit(receipt['checks'][-1]['exit_code'])
