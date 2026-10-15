"""C09 offline readiness checks; no service startup or application changes."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys

output = Path(__file__).resolve().parent
root = output.parents[4]
environment = dict(
    os.environ, AUTH_MODE='disabled', DEPLOYMENT_ENV='test',
    ENABLE_MOCK_LOGIN='false', PERSIST_LOCAL_CHAT='false', RUN_POSTGRES_INTEGRATION='0',
    DATABASE_URL='postgresql://unused:unused@127.0.0.1:1/ocean_c09_readiness_unused',
    MODEL_PROVIDER='ollama', OLLAMA_BASE_URL='http://127.0.0.1:1',
)
checks = [
    ('baseline', [sys.executable, '-m', 'pytest', 'tests/test_artifact_store.py',
                  'tests/test_provenance_snapshot.py', 'tests/test_immutable_bundle_security.py',
                  'tests/test_catalogue_cache.py', '-q', '--tb=short']),
    ('prerequisites', [sys.executable, '-m', 'pytest', 'tests/test_retention.py',
                       'tests/test_retention_cleanup_script.py', 'tests/test_retention_postgres_guard.py',
                       'tests/test_context_catalogue_contract.py', 'tests/test_context_catalogue_fixtures.py',
                       '-q', '--tb=short']),
    ('schema', [sys.executable, 'scripts/export_context_catalogue.py', '--check']),
    ('browser-types', [sys.executable, 'scripts/export_catalogue_types.py', '--check']),
    ('examples', [sys.executable, 'scripts/export_catalogue_examples.py', '--check']),
    ('scope', [sys.executable, 'scripts/export_chat_scope.py', '--check']),
]
results = []
for name, command in checks:
    with (output / f'{name}.txt').open('w') as log:
        process = subprocess.run(command, cwd=root, env=environment, stdout=log, stderr=subprocess.STDOUT)
    lines = (output / f'{name}.txt').read_text().splitlines()
    results.append({'name': name, 'command': command, 'exit_code': process.returncode,
                    'summary': lines[-1] if lines else 'No output; command succeeded' if not process.returncode else 'No output'})
    if process.returncode:
        break
receipt = {'checks': results, 'safe_environment': {key: environment[key] for key in (
    'AUTH_MODE', 'DEPLOYMENT_ENV', 'ENABLE_MOCK_LOGIN', 'PERSIST_LOCAL_CHAT',
    'RUN_POSTGRES_INTEGRATION', 'DATABASE_URL', 'MODEL_PROVIDER', 'OLLAMA_BASE_URL')},
           'service_startups': 0, 'C09_implementation_started': False}
(output / 'results.json').write_text(json.dumps(receipt, indent=2) + '\n')
print(json.dumps(receipt))
sys.exit(results[-1]['exit_code'])
