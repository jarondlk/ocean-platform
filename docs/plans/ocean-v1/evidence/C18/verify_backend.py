"""One C18 backend acceptance run; explicit unavailable external targets."""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]
previous = json.loads((ROOT / 'docs/plans/ocean-v1/evidence/C17/accepted-source.json').read_text())
paths = sorted({*previous['files'], 'api/v1_runtime_routes.py', 'tests/test_v1_runtime.py'})
def hashes():
    return {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in paths}
if any((HERE / name).exists() for name in ('backend-tests.txt', 'backend-result.json', 'backend-tested-source.json')):
    raise RuntimeError('Refusing to rewrite C18 acceptance evidence')
before = hashes()
environment = dict(os.environ, AUTH_MODE='disabled', DEPLOYMENT_ENV='test', ENABLE_MOCK_LOGIN='false', PERSIST_LOCAL_CHAT='false', ENABLE_V1_SHELL='false', ENABLE_V1_CATALOGUE='false', ENABLE_V1_CATALOGUE_BROWSER='false', ENABLE_V1_INVESTIGATIONS='false', RUN_POSTGRES_INTEGRATION='0', DATABASE_URL='postgresql://unused:unused@127.0.0.1:1/ocean_c18_unused', MODEL_PROVIDER='ollama', OLLAMA_BASE_URL='http://127.0.0.1:1')
command = [sys.executable, '-m', 'pytest', 'tests/', '-q', '--tb=short', '--cov=api', '--cov=config', '--cov=db', '--cov=preprocessing', '--cov=ingestion', '--cov=orchestration', '--cov=schema', '--cov=evaluation', '--cov-report=term-missing', '--cov-fail-under=70']
started = time.monotonic()
with (HERE / 'backend-tests.txt').open('x') as log:
    result = subprocess.run(command, cwd=ROOT, env=environment, stdout=log, stderr=subprocess.STDOUT)
after = hashes()
changed = [name for name in before if before[name] != after[name]]
(HERE / 'backend-tested-source.json').write_text(json.dumps({'before_sha256': before, 'after_sha256': after, 'changed': changed}, indent=2) + '\n')
receipt = {'command': command, 'seconds': round(time.monotonic()-started, 2), 'exit_code': result.returncode, 'source_changed_during_run': changed, 'source_paths': len(paths), 'environment': {key:environment[key] for key in ('AUTH_MODE','DEPLOYMENT_ENV','ENABLE_MOCK_LOGIN','PERSIST_LOCAL_CHAT','ENABLE_V1_SHELL','ENABLE_V1_CATALOGUE','ENABLE_V1_CATALOGUE_BROWSER','ENABLE_V1_INVESTIGATIONS','RUN_POSTGRES_INTEGRATION','DATABASE_URL','MODEL_PROVIDER','OLLAMA_BASE_URL')}}
(HERE / 'backend-result.json').write_text(json.dumps(receipt, indent=2) + '\n')
print(json.dumps(receipt))
print('\n'.join((HERE / 'backend-tests.txt').read_text().splitlines()[-4:]))
raise SystemExit(result.returncode or bool(changed))
