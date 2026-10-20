"""Retry only C21 full-suite cases blocked by local loopback sandbox permissions."""
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]
spec = importlib.util.spec_from_file_location('c21_local_verifier', HERE / 'verify_local.py')
helper = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helper)
text = (HERE / 'backend-acceptance-01/backend.txt').read_text()
errors = [line for line in text.splitlines() if line.startswith('E   ')]
assert len(errors) == 43 and all(line == 'E   PermissionError: [Errno 1] Operation not permitted' for line in errors)
nodes = re.findall(r'^(?:FAILED|ERROR) (tests/\S+)', text, flags=re.M)
assert len(nodes) == len(set(nodes)) == 43
output = HERE / 'backend-loopback-retry-01'
output.mkdir(exist_ok=False)
before = helper.source_pins()
environment = dict(os.environ, AUTH_MODE='disabled', DEPLOYMENT_ENV='test', ENABLE_MOCK_LOGIN='false',
    PERSIST_LOCAL_CHAT='false', ENABLE_V1_SHELL='false', ENABLE_V1_CATALOGUE='false',
    ENABLE_V1_CATALOGUE_BROWSER='false', ENABLE_V1_INVESTIGATIONS='false', ENABLE_V1_RESEARCH_CONTROLLER='false',
    ENABLE_V1_RESEARCH_RUNS='false', ENABLE_V1_RESEARCH_DISPATCH='false', ENABLE_V1_EVIDENCE='false',
    ENABLE_V1_SYNTHESIS='false', RUN_POSTGRES_INTEGRATION='0',
    DATABASE_URL='postgresql://unused:unused@127.0.0.1:1/ocean_c21_unused',
    MODEL_PROVIDER='ollama', OLLAMA_BASE_URL='http://127.0.0.1:1')
command = [sys.executable, '-m', 'pytest', *nodes, '-q', '--tb=short', '--no-cov']
started = time.monotonic()
with (output / 'tests.txt').open('x') as log:
    completed = subprocess.run(command, cwd=ROOT, env=environment, stdout=log, stderr=subprocess.STDOUT, timeout=180)
after = helper.source_pins()
changed = sorted(name for name in set(before) | set(after) if before.get(name) != after.get(name))
summary = [line for line in (output / 'tests.txt').read_text().splitlines() if re.search(r'\d+ passed', line)]
record = {'component': 'C21', 'created_at': datetime.now(timezone.utc).isoformat(), 'command': command,
    'exit_code': completed.returncode, 'seconds': round(time.monotonic()-started, 2),
    'test_summary': summary[-1] if summary else None, 'case_count': len(nodes),
    'original_report_sha256': hashlib.sha256((HERE / 'backend-acceptance-01/backend.txt').read_bytes()).hexdigest(),
    'source_before_sha256': before, 'source_after_sha256': after, 'source_changed_during_run': changed,
    'preservation': helper.preservation(), 'scope': 'Only43 exact previously blocked local synthetic HTTP-server cases; no broad suite repeated'}
helper.save(output, 'result.json', record)
print(json.dumps({key:record[key] for key in ('exit_code','seconds','test_summary','case_count','source_changed_during_run')}))
raise SystemExit(completed.returncode or bool(changed))
