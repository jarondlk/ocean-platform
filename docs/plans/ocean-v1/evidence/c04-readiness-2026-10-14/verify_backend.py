"""Run repository checks with explicit test settings and no application database."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys


output = Path(__file__).resolve().parent
environment = dict(
    os.environ, AUTH_MODE='disabled', DEPLOYMENT_ENV='test', ENABLE_MOCK_LOGIN='false',
    PERSIST_LOCAL_CHAT='false', RUN_POSTGRES_INTEGRATION='0',
    DATABASE_URL='postgresql://unused:unused@127.0.0.1:1/ocean_c04_readiness_unused',
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
                         ['AUTH_MODE', 'DEPLOYMENT_ENV', 'ENABLE_MOCK_LOGIN',
                          'PERSIST_LOCAL_CHAT', 'RUN_POSTGRES_INTEGRATION', 'DATABASE_URL']},
    'exit_code': result.returncode,
}, indent=2) + '\n')
print('\n'.join((output / 'backend-tests.txt').read_text().splitlines()[-5:]))
sys.exit(result.returncode)
