"""Reconcile C21 local gates without rewriting original reports or old receipts."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]
SOURCE = '0ab726a243a4c74d584a4894dca1a71158cb9cc2'


def read(name):
    return json.loads((HERE / name).read_text())


def sha(name):
    return hashlib.sha256((ROOT / name).read_bytes()).hexdigest()


def verify(files):
    changed = [name for name, digest in files.items() if sha(name) != digest]
    assert not changed, changed


def save(name, value):
    with (HERE / name).open('x') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write('\n')


start, checkpoint = read('start-snapshot.json'), read('source-checkpoint.json')
verify(start['prior_evidence_files'])
for protected in start['preservation'].values():
    verify(protected)
verify(checkpoint['files'])
for name, digest in checkpoint['files'].items():
    committed = subprocess.check_output(['git', 'show', SOURCE + ':' + name], cwd=ROOT)
    assert hashlib.sha256(committed).hexdigest() == digest, name
changed_prior = {name: {'prior': digest, 'current': sha(name)} for name, digest in start['prior_source_files'].items()
                 if sha(name) != digest}
assert set(changed_prior) == set(checkpoint['intentional_source_supersessions']), set(changed_prior)

backend = read('backend-acceptance-01/result.json')
assert len(backend['commands']) == 1 and backend['commands'][0]['exit_code'] == 1
retry = read('backend-loopback-retry-01/result.json')
assert retry['exit_code'] == 0 and retry['case_count'] == 43 and retry['source_changed_during_run'] == []
assert re.search(r'\b43 passed\b', retry['test_summary'])
verify(retry['source_after_sha256'])
before, after = read('backend-acceptance-01/source-before.json'), read('backend-acceptance-01/source-after.json')
allowed = {'migrations/versions/20261019_0019_research_evidence.py',
           'tests/integration/test_research_evidence_postgres.py', 'tests/integration/test_research_runs_postgres.py'}
assert set(backend['source_changed_during_run']) <= allowed, backend['source_changed_during_run']
verify(after)
backend_text = (HERE / 'backend-acceptance-01/backend.txt').read_text()
summaries = [line for line in backend_text.splitlines() if re.search(r'\d+ passed', line)]
assert summaries
initial_counts = {kind: int(amount) for amount, kind in re.findall(r'(\d+) (passed|failed|skipped|errors|error)', summaries[-1])}
assert initial_counts == {'failed': 29, 'passed': 4997, 'skipped': 251, 'errors': 14}, initial_counts
exceptions = [line for line in backend_text.splitlines() if line.startswith('E   ')]
assert len(exceptions) == 43 and all(line == 'E   PermissionError: [Errno 1] Operation not permitted' for line in exceptions)
assert hashlib.sha256((HERE / 'backend-acceptance-01/backend.txt').read_bytes()).hexdigest() == retry['original_report_sha256']
counts = {'passed': 5040, 'failed': 0, 'errors': 0, 'skipped': 251}
coverage = re.findall(r'^TOTAL\s+.*?([0-9]+(?:\.[0-9]+)?)%\s*$', backend_text, flags=re.M)

frontend = read('frontend-full-verification.json')
assert frontend['test_counts']['pass'] == 930 and frontend['test_counts']['fail'] == 0
assert frontend['production_dependency_vulnerabilities']['total'] == 0
assert all(command['exit_code'] == 0 for command in frontend['commands'])
verify(frontend['reviewed_source_sha256'])
store, amendment, synthesis = read('store-verification.json'), read('closure-amendment/verification.json'), read('synthesis-verification.json')
assert store['focused_tests']['passed'] == 16 and store['ruff_exit_code'] == 0
verify(synthesis['files'])
verify(amendment['source_sha256'])
for path, digest in store['source_sha256'].items():
    assert sha(path) == digest or path in amendment['source_sha256'], path
pg, closure, regressions = read('store-pg-final-01/postgres-result.json'), read('closure-amendment/verified-01/postgres-result.json'), read('pg-regressions-02/postgres-result.json')
for report, expected in ((pg, 20), (closure, 3), (regressions, 104)):
    assert report['driver_exit_code'] == report['test_exit_code'] == 0
    assert report['server_stopped'] and report['test_schemas_remaining'] == 0
    assert report['source_changed_during_run'] == []
    assert report['test_counts']['passed'] == expected
verify(regressions['source_after_sha256'])
assert read('static-acceptance-01/result.json')['success']
for name, field in (('frontend-independent-backend-review.json', 'reviewed_source_sha256'),
                    ('frontend-independent-review.json', 'source_sha256'),
                    ('store-independent-review.json', 'source_sha256')):
    report = read(name)
    verify(report[field])
    assert not report.get('remaining_findings', report.get('open_blockers', []))

tested = {**start['prior_source_files'], **after, **checkpoint['files']}
tested = {name: sha(name) for name in tested if name not in start['preservation']['unrelated_files']}
evidence = {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(HERE.rglob('*')) if path.is_file() and '__pycache__' not in path.parts}
qualification = {
    'reason': 'Only reviewed PostgreSQL migration/test changes occurred during the local non-PostgreSQL suite; application/runtime files and executed tests stayed fixed.',
    'changed_during_backend': {name: {'before': before.get(name), 'after': after.get(name)}
                               for name in backend['source_changed_during_run']},
    'final_database_verification': '20 original actual C21 cases plus 3 targeted closure amendment cases and 104 final C17/C20 regressions',
    'requirement': 'Component delivery additionally requires exact-source hosted CI on ' + SOURCE,
    'original_full_suite': initial_counts,
    'loopback_retry': 'Exactly43 previously blocked synthetic local HTTP-server cases pass with loopback permission; original sandbox failure report remains immutable.',
    'no_broad_repeat': True,
}
save('backend-source-qualification.json', qualification)
save('verification.json', {'component': 'C21', 'created_at': datetime.now(timezone.utc).isoformat(),
    'state': 'Local acceptance reconciled; exact-source hosted CI and delivered handoff remain required',
    'source_commit': SOURCE, 'files': checkpoint['files'], 'source_sha256': checkpoint['source_sha256'],
    'tested_transitive_source_files': tested, 'intentional_source_supersessions': changed_prior,
    'evidence_files': evidence, 'checks': {'backend': counts, 'original_backend_summary': summaries[-1],
        'loopback_retry_summary': retry['test_summary'],
        'coverage_percent': float(coverage[-1]) if coverage else None, 'frontend': frontend['test_counts'],
        'actual_postgres': 127, 'generated_contracts': 'pass', 'reviews': 'no remaining scoped blockers'},
    'backend_source_qualification': qualification,
    'preserved_prior_evidence_count': len(start['prior_evidence_files']),
    'protected_counts': {key: len(values) for key, values in start['preservation'].items()},
    'external_gates': ['No real provider/data acquisition/transfer or GCP provisioning/deployment acceptance',
                       'No independent scientific approval claimed', 'C26 assembled browser/system acceptance remains']})
print(json.dumps({'state': 'local acceptance reconciled', 'backend': counts, 'actual_postgres': 127,
                  'source_sha256': checkpoint['source_sha256']}))
