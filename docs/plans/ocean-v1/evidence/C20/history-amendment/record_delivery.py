"""Create final C20 delivery for the explicitly supplied, hosted amended source."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[5]
BASE = HERE.parent


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    return json.loads(path.read_text())


def verify(files):
    assert all(sha(ROOT / path) == digest for path, digest in files.items())


parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--source-commit', required=True)
args = parser.parse_args()
source = args.source_commit
assert re.fullmatch(r'[0-9a-f]{40}', source)
assert not (BASE / 'delivery.json').exists(), 'Final C20 delivery is create-only'
assert subprocess.check_output(['git', 'branch', '--show-current'], cwd=ROOT, text=True).strip() == 'overhaul'
subprocess.run(['git', 'merge-base', '--is-ancestor', source, 'origin/overhaul'], cwd=ROOT, check=True)
ci = read(HERE / 'hosted-ci.json')
assert ci['source_commit'] == ci['run']['head_sha'] == source
assert ci['run']['status'] == 'completed' and ci['run']['conclusion'] == 'success'
required = {'backend': 'Backend tests and security boundary', 'postgres': 'PostgreSQL migration and metadata integration',
            'frontend-v1': 'OCEAN v1 prototype tests and build', 'frontend-legacy': 'Frontend typecheck and build'}
jobs = {job['name']: job for job in ci['jobs']}
assert all(jobs[name]['conclusion'] == 'success' for name in required.values())
assert all(job['conclusion'] == 'success' for name, job in jobs.items() if name != 'Dependency review')
accepted = read(HERE / 'verification.json')
start = read(HERE / 'start-snapshot.json')
for files in (accepted['files'], accepted['tested_transitive_source_files'], accepted['evidence_files'],
              start['prior_evidence_files'], start['original_local_evidence_files'], *start['preservation'].values()):
    verify(files)
for path, digest in accepted['tested_transitive_source_files'].items():
    body = subprocess.check_output(['git', 'show', source + ':' + path], cwd=ROOT)
    assert hashlib.sha256(body).hexdigest() == digest, path
assert not subprocess.check_output(['git', 'diff', '--name-only', source, '--', str(BASE.relative_to(ROOT))], cwd=ROOT, text=True).strip()
logs = {}
for short, name in required.items():
    log = HERE / ('hosted-' + short + '.txt')
    logs[short] = log.read_text()
    metadata = read(HERE / ('hosted-' + short + '-log-metadata.json'))
    assert metadata['source_commit'] == source and metadata['job_id'] == jobs[name]['id']
    assert metadata['saved_sha256'] == sha(log)
passed, skipped, seconds = re.findall(r'(\d+) passed, (\d+) skipped[^\n]*?in ([\d.]+)s', logs['backend'])[-1]
coverage = float(re.findall(r'Total coverage: ([\d.]+)%', logs['backend'])[-1])
assert int(passed) == 4838 and int(skipped) == 231 and coverage >= 70
postgres = [int(v) for v in re.findall(r'(\d+) passed[^\n]*? in [\d.]+s', logs['postgres'])]
assert postgres == [82, 12, 12, 21, 60, 44], postgres
frontend = accepted['checks']['frontend']['passed']
assert re.search(r'# pass ' + str(frontend) + r'\b', logs['frontend-v1'])
assert re.search(r'# pass 132\b', logs['frontend-legacy'])
assert all('found 0 vulnerabilities' in logs[key] for key in ('frontend-v1', 'frontend-legacy'))
extras = {str(path.relative_to(ROOT)): sha(path) for path in sorted(BASE.rglob('*'))
          if path.is_file() and '__pycache__' not in path.parts and path.name != 'delivery.json'}
record = {'component': 'C20', 'created_at': datetime.now(timezone.utc).isoformat(),
          'state': 'Complete; amended source committed/pushed and exact-source hosted validation passed',
          'branch': 'overhaul', 'source_commit': source, 'original_source_commit': start['original_source_commit'],
          'original_local_verification_sha256': start['original_verification_sha256'],
          'amendment_receipt': str((HERE / 'verification.json').relative_to(ROOT)),
          'amendment_receipt_sha256': sha(HERE / 'verification.json'),
          'source_sha256': accepted['source_sha256'], 'files': accepted['files'],
          'tested_transitive_source_files': accepted['tested_transitive_source_files'],
          'intentional_source_supersessions': accepted['intentional_source_supersessions'],
          'all_tested_sources_match_hosted_source_commit': True, 'hosted_ci': ci,
          'hosted_counts': {'backend': int(passed), 'postgres_gated_skips': int(skipped), 'coverage_percent': coverage,
                            'backend_pytest_seconds': float(seconds), 'postgres_actual': sum(postgres), 'postgres_steps': postgres,
                            'v1_frontend': frontend, 'legacy_frontend': 132, 'both_builds_typechecks_audits': 'pass',
                            'generated_contracts_migrations_upsert_backup_isolated_restore': 'pass'},
          'delivery_evidence_files': extras, 'prior_tracked_evidence_unchanged': len(start['prior_evidence_files']),
          'protected_counts': {key: len(files) for key, files in start['preservation'].items()},
          'qualification': 'Local backend includes nine pre-existing unrelated benchmark tests excluded from source and hosted CI',
          'external_gates': ['C21 retained answers/evidence and C26 assembled browser acceptance remain separate',
                             'No actual cloud/provider/OIDC/real data/scientific approval/deployment acceptance']}
with (BASE / 'delivery.json').open('x') as stream:
    json.dump(record, stream, indent=2)
    stream.write('\n')
print(json.dumps({'state': 'delivered', 'source_commit': source, 'backend': int(passed), 'postgres': sum(postgres),
                  'v1_frontend': frontend, 'delivery_sha256': sha(BASE / 'delivery.json')}))
