"""C16 backend regression run with explicit isolated-test settings."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys


output = Path(__file__).resolve().parent
environment = dict(
    os.environ, AUTH_MODE='disabled', DEPLOYMENT_ENV='test', ENABLE_V1_SHELL='false', ENABLE_V1_CATALOGUE='false', ENABLE_MOCK_LOGIN='false',
    PERSIST_LOCAL_CHAT='false', RUN_POSTGRES_INTEGRATION='0',
    MODEL_PROVIDER='ollama', OLLAMA_BASE_URL='http://127.0.0.1:1',
    DATABASE_URL='postgresql://unused:unused@127.0.0.1:1/ocean_c16_regressions_unused',
)
command = [sys.executable, '-m', 'pytest', 'tests/', '-q', '--tb=short',
           '--cov=api', '--cov=config', '--cov=db', '--cov=preprocessing',
           '--cov=ingestion', '--cov=orchestration', '--cov=schema', '--cov=evaluation',
           '--cov-report=term-missing', '--cov-fail-under=70']
with (output / 'backend-tests.txt').open('w') as log:
    result = subprocess.run(command, env=environment, stdout=log, stderr=subprocess.STDOUT)
(output / 'backend-result.json').write_text(json.dumps({
    'command': command,
    'safe_environment': {key: environment[key] for key in
                         ['AUTH_MODE', 'DEPLOYMENT_ENV', 'ENABLE_V1_SHELL', 'ENABLE_V1_CATALOGUE', 'ENABLE_MOCK_LOGIN',
                          'PERSIST_LOCAL_CHAT', 'RUN_POSTGRES_INTEGRATION', 'DATABASE_URL',
                          'MODEL_PROVIDER', 'OLLAMA_BASE_URL']},
    'exit_code': result.returncode,
}, indent=2) + '\n')
print('\n'.join((output / 'backend-tests.txt').read_text().splitlines()[-5:]))
sys.exit(result.returncode)
