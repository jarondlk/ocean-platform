"""Read-only integrity check; no subprocess, tests, credentials or cloud calls."""
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]
receipt = json.loads((HERE / 'receipt.json').read_text())
for group in ['sources', 'artifacts', 'unchanged_host_sources']:
    for relative, expected in receipt[group].items():
        path = ROOT / relative
        if path.is_symlink() or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise SystemExit('Source or evidence byte mismatch: ' + relative)
output = (HERE / 'checks.stdout').read_text()
if '# tests 14\n' not in output or '# pass 14\n' not in output or '# fail 0\n' not in output:
    raise SystemExit('Focused original HTTP result does not match receipt')
if (HERE / 'checks.stderr').read_bytes():
    raise SystemExit('Unexpected focused check diagnostics')
print(json.dumps({'state': 'byte_integrity_verified', 'http_checks_repeated': False,
    'cloud_calls': False, 'sources': len(receipt['sources']),
    'artifacts': len(receipt['artifacts']), 'unchanged_host_sources': len(receipt['unchanged_host_sources'])}))
