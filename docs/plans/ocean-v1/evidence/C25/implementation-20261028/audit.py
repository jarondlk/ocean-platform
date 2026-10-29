"""C25 local acceptance/source receipt. Never provisions or executes analyses."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import gzip
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[6]
BASE = ROOT / 'docs/plans/ocean-v1'
OUT = Path(__file__).resolve().parent


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT, text=True).strip()


def git_sha(commit, name):
    return hashlib.sha256(subprocess.check_output(['git', 'show', commit + ':' + name], cwd=ROOT)).hexdigest()


def read(path):
    return json.loads(path.read_text())


def source_paths():
    paths = set(git('diff', '--name-only', read(OUT / 'start.json')['base_commit'], '--', '.github/workflows/tests.yml', 'api', 'config.py', 'orchestration', 'frontend-v1/src', 'frontend-v1/tests').splitlines())
    for folder, pattern in [
        ('api', 'experiment_workspace_routes.py'), ('orchestration', 'experiment_workspace.py'),
        ('schema', 'experiment_workspace.py'), ('scripts', 'export_experiment_contract.py'),
        ('tests', '*experiment_workspace*'), ('tests', 'experiment_workspace_support.py'),
        ('tests', 'test_experiment_browser_contract.py'), ('tests/integration', 'test_experiment_workspace_postgres.py'),
        ('frontend-v1/src', 'experiment-*.ts'), ('frontend-v1/src', 'research-experiments*'),
        ('frontend-v1/src/generated', 'experiment-*.ts'), ('frontend-v1/tests', 'experiment-*.test.ts'),
        ('frontend-v1/tests/fixtures', 'experiment-execution-wire.json'),
    ]:
        paths.update(str(p.relative_to(ROOT)) for p in (ROOT / folder).glob(pattern) if p.is_file())
    paths.update(str(p.relative_to(ROOT)) for p in (ROOT / 'frontend-v1/development/c25').rglob('*')
        if p.is_file() and not any(part.startswith('.') for part in p.relative_to(ROOT / 'frontend-v1/development/c25').parts)
        and not p.name.endswith('.tsbuildinfo'))
    paths.update([str(Path(__file__).relative_to(ROOT)), 'docs/plans/ocean-v1/evidence/C25/serve_experiments_qa.py'])
    return paths


def verify_prerequisites(start):
    prerequisites, current = {}, {}
    records = [
        ('P00', 'mockups/p00/source-revision.json', 'files', 'c7ea5f4c4243d1c1a0657a0a01c075f5f738219d'),
        ('C18', 'evidence/C18/delivery.json', 'files', None),
        ('C22', 'evidence/C22/delivery.json', 'source_files', None),
        ('C23', 'evidence/C23/operator-hosted-f6f823b/receipt.json', 'source_files', None),
        ('C24', 'evidence/C24/delivery.json', 'source_files', None),
    ]
    for component, relative, key, historical in records:
        path = BASE / relative
        assert sha(path) == git_sha(start['base_commit'], str(path.relative_to(ROOT))), relative
        receipt = read(path)
        commit = historical or receipt['source_commit']
        superseded = {}
        for name, original in receipt[key].items():
            assert git_sha(commit, name) == original, (component, name)
            actual = sha(ROOT / name)
            baseline = git_sha(start['base_commit'], name)
            current[name] = actual
            if actual != baseline:
                superseded[name] = {'prior_current_sha256': baseline, 'c25_sha256': actual,
                    'original_receipt_sha256': original,
                    'qualification': 'Intentional C25 software/source supersession; original receipt remains immutable. New CI verifies software only, not fresh Linux containment or scientific approval.'}
        prerequisites[component] = {'receipt': str(path.relative_to(ROOT)), 'receipt_sha256': sha(path),
            'original_accepted_source': commit, 'source_entries': len(receipt[key]), 'c25_source_supersessions': superseded}
        if component == 'P00':
            for name, expected in receipt['screenshots'].items():
                assert sha(BASE / 'mockups/p00' / name) == expected
    return prerequisites, current


def verify():
    assert git('branch', '--show-current') == 'overhaul'
    start = read(OUT / 'start.json')
    assert sha(BASE / 'evidence/C25/readiness-20261028/verification.json') == start['readiness_receipt_sha256']
    for name, expected in start['protected_sha256'].items():
        assert sha(ROOT / name) == expected, name
    # All earlier tracked evidence stays byte-identical, including readiness.
    changed = git('diff', '--name-status', start['base_commit'], '--', 'docs/plans/ocean-v1/evidence')
    for line in changed.splitlines():
        assert line.startswith('A\tdocs/plans/ocean-v1/evidence/C25/'), line
    prerequisites, current = verify_prerequisites(start)
    for path in source_paths():
        current[path] = sha(ROOT / path)
    from schema.research_experiments import EXPERIMENT_REQUEST_MODELS, ExperimentSnapshot
    from schema.experiment_workspace import EXECUTION_REQUEST_MODELS
    assert set(EXPERIMENT_REQUEST_MODELS) == {'create', 'revise', 'get', 'status', 'list', 'approve', 'dispatch', 'events', 'retry'}
    assert ExperimentSnapshot.model_fields['execution_performed'].annotation.__args__ == (False,)
    assert set(EXECUTION_REQUEST_MODELS) == {'capability', 'status', 'events', 'cancel', 'artifact'}
    ledger = json.loads(gzip.decompress((OUT / 'actual-browser-http.json.gz').read_bytes()))
    assert ledger['server_stopped'] and ledger['metadata']['execution_performed'] is False
    requests = ledger['actual_requests']
    approvals = [x for x in requests if x['path'].endswith('/experiments/approve')]
    cancels = [x for x in requests if x['path'].endswith('/experiment-executions/cancel')]
    assert approvals[0]['request'] == approvals[1]['request'] and [x['status'] for x in approvals[:2]] == [503, 200]
    assert any(x['status'] == 409 for x in approvals)
    assert len(cancels) == 2 and cancels[0]['request'] == cancels[1]['request'] and [x['status'] for x in cancels] == [503, 200]
    assert not any('/dispatch' in x['path'] or '/classification' in x['path'] for x in requests)
    assert '1049' in (OUT / 'source-frontend-tests.log').read_text() and '# fail 0' in (OUT / 'source-frontend-tests.log').read_text()
    assert '24 passed' in (OUT / 'ocean-c25-backend-final02-20261029.log').read_text()
    assert '1 passed' in (OUT / 'ocean-c25-native-pg-test-20261029.log').read_text()
    receipt = {'version': 'c25-local-acceptance-v1', 'recorded_utc': datetime.now(timezone.utc).isoformat(),
        'state': 'Local implementation verified; source checkpoint and hosted CI required', 'base_commit': start['base_commit'],
        'source_files': dict(sorted(current.items())), 'prerequisites': prerequisites,
        'protected_unrelated_paths': len(start['protected_sha256']), 'original_evidence_immutable': True,
        'local_tests': {'frontend': 1049, 'workspace_backend': 24, 'browser_contract': 1, 'native_postgres_compatibility': 1},
        'browser_actual_requests': len(requests), 'browser_evidence': 'browser-observations.json',
        'qualifications': ['Explicit synthetic durable port and TEST accounts; no Python execution, live provider, real-data, GCP, DNS or deployment.',
            'C22 v1 remains nine actions and execution_performed:false. Five-action execution projection is a separate version; start_enabled:false.',
            'C22 released-reservation public projection intentionally supersedes prior source. Original C23 physical receipts remain bound to their original source, not all new pins.',
            'Production auth/hosting, Cloud Tasks/outbox, retained worker port/supervisor and live isolation/recovery/backup/release remain external integration/acceptance gates. Scheduler PAUSED.'],
        'evidence_files': {str(p.relative_to(OUT)): sha(p) for p in sorted(OUT.iterdir()) if p.is_file() and p.name != 'local-receipt.json'}}
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--verify-only', action='store_true')
    args = parser.parse_args()
    actual = verify()
    target = OUT / 'local-receipt.json'
    if args.verify_only:
        original = read(target)
        assert actual['source_files'] == original['source_files'], 'C25 source changed'
        assert actual['prerequisites'] == original['prerequisites'], 'Prerequisite receipt/source changed'
        for name, expected in original['evidence_files'].items():
            assert sha(OUT / name) == expected, name
    else:
        with target.open('x') as stream:
            stream.write(json.dumps(actual, indent=2, sort_keys=True) + '\n')
    print(f"C25 verified: {len(actual['source_files'])} source pins, protected unrelated paths and immutable prerequisites; local checks only")


if __name__ == '__main__':
    main()
