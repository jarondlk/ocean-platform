"""Record C21 delivery only after exact-source hosted checks and preserved local gates."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]
ORIGINAL_SOURCE = '0ab726a243a4c74d584a4894dca1a71158cb9cc2'
SOURCE = '567684b6649ed8a31ed4f89f1a0e223a677f2fe8'


def sha(name):
    return hashlib.sha256((ROOT / name).read_bytes()).hexdigest()


def read(name):
    return json.loads((HERE / name).read_text())


def verify(files):
    changed = [name for name, digest in files.items() if sha(name) != digest]
    assert not changed, changed


assert not (HERE / 'delivery.json').exists(), 'Original delivery receipts are immutable'
local, hosted, start = read('verification.json'), read('hosted-ci.json'), read('start-snapshot.json')
amendment = read('ci-budget-amendment/selection.json')
assert local['source_commit'] == ORIGINAL_SOURCE and hosted['source_commit'] == SOURCE
assert hosted['run']['head_sha'] == SOURCE and hosted['run']['head_branch'] == 'overhaul'
assert hosted['run']['status'] == 'completed' and hosted['run']['conclusion'] == 'success'
assert hosted['run']['event'] == 'push' and hosted['run']['id'] != 39447528914
required = {'Backend tests and security boundary', 'Frontend typecheck and build',
            'OCEAN v1 prototype tests and build', 'PostgreSQL migration and metadata integration'}
jobs = {job['name']: job for job in hosted['jobs']}
assert required <= jobs.keys()
assert all(jobs[name]['status'] == 'completed' and jobs[name]['conclusion'] == 'success' for name in required)
assert hosted['checks']['backend']['passed'] == 5031 and hosted['checks']['backend']['skipped'] == 254
assert hosted['checks']['backend']['coverage_percent'] >= 70
assert hosted['checks']['postgres_suites'] == [82, 12, 12, 21, 60, 44, 23]
assert sum(hosted['checks']['postgres_suites']) == 254
assert hosted['checks']['frontend_v1_passed'] == 930 and hosted['checks']['frontend_legacy_passed'] == 132
for record in hosted['logs'].values():
    assert sha(record['path']) == record['sha256']
workflow = '.github/workflows/tests.yml'
verify(amendment['final_source_files'])
verify({name: digest for name, digest in local['files'].items() if name != workflow})
verify({name: digest for name, digest in local['tested_transitive_source_files'].items() if name != workflow})
verify(local['evidence_files'])
verify(start['prior_evidence_files'])
for protected in start['preservation'].values():
    verify(protected)
subprocess.run(['git', 'merge-base', '--is-ancestor', SOURCE, 'HEAD'], cwd=ROOT, check=True)
for name, digest in amendment['final_source_files'].items():
    assert hashlib.sha256(subprocess.check_output(['git', 'show', SOURCE + ':' + name], cwd=ROOT)).hexdigest() == digest
source_hash = hashlib.sha256(''.join(f'{name}:{digest}\n' for name,digest in sorted(amendment['final_source_files'].items())).encode()).hexdigest()
supersessions = {**local['intentional_source_supersessions'], workflow: {
    'prior': start['prior_source_files'][workflow], 'current': amendment['final_source_files'][workflow]}}
record = {'component': 'C21', 'state': 'Complete for the authorized separate-v1 synthetic/local implementation and exact-source hosted acceptance',
    'recorded_at': datetime.now(timezone.utc).isoformat(), 'branch': 'overhaul', 'source_commit': SOURCE,
    'source_sha256': source_hash, 'source_files': amendment['final_source_files'],
    'local_receipt': {'path': str((HERE / 'verification.json').relative_to(ROOT)),
                      'sha256': sha(str((HERE / 'verification.json').relative_to(ROOT)))},
    'hosted_receipt': {'path': str((HERE / 'hosted-ci.json').relative_to(ROOT)),
                       'sha256': sha(str((HERE / 'hosted-ci.json').relative_to(ROOT)))},
    'hosted_run': hosted['run'], 'checks': hosted['checks'],
    'local_qualifications': local['backend_source_qualification'],
    'intentional_source_supersessions': supersessions,
    'ci_budget_amendment': {'original_source': ORIGINAL_SOURCE, 'original_cancelled_run':39447528914,
        'selection_receipt': str((HERE / 'ci-budget-amendment/selection.json').relative_to(ROOT)),
        'selection_sha256': sha(str((HERE / 'ci-budget-amendment/selection.json').relative_to(ROOT))),
        'only_change': 'Backend CI timeout30 to60 minutes; all tests, coverage gates and other50 application/test files unchanged'},
    'preserved_prior_evidence_count': len(start['prior_evidence_files']),
    'protected_counts': {key: len(values) for key, values in start['preservation'].items()},
    'external_gates': local['external_gates'],
    'next_component': 'C22 readiness must audit formal prerequisites C01/C07/C09/C17/C21 against this delivered source after the metadata checkpoint is pushed'}
with (HERE / 'delivery.json').open('x') as stream:
    json.dump(record, stream, ensure_ascii=False, indent=2)
    stream.write('\n')
print(json.dumps({'component': 'C21', 'source': SOURCE, 'state': 'source-bound delivery verified',
                  'delivery_sha256': sha(str((HERE / 'delivery.json').relative_to(ROOT)))}))
