"""Reconcile C25 prerequisites and expose the current public API completion gates.

Read-only source/receipt checks; never runs Python analyses or contacts GCP.
The default creates a new receipt; --verify-only leaves existing receipts intact.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess

from api.research_experiment_routes import router
from schema.research_experiments import EXPERIMENT_REQUEST_MODELS, ExperimentSnapshot

ROOT = Path(__file__).resolve().parents[6]
BASE = ROOT / 'docs/plans/ocean-v1'
OUT = Path(__file__).resolve().parent
ACCEPTED = 'eeec2e159e10ae3da509c478ff712a1e20c8e91e'
P00_SOURCE = 'c7ea5f4c4243d1c1a0657a0a01c075f5f738219d'


def read(path):
    return json.loads(path.read_text())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT, text=True).strip()


def source_sha(commit, name):
    return hashlib.sha256(subprocess.check_output(['git', 'show', commit + ':' + name], cwd=ROOT)).hexdigest()


def verify():
    start = read(OUT / 'baseline.json')
    assert git('branch', '--show-current') == 'overhaul'
    assert read(OUT / 'remote-overhaul.json')['commit']['sha'] == start['base_commit']
    for name, expected in start['protected_sha256'].items():
        assert sha(ROOT / name) == expected, name
    # New readiness evidence is append-only; no original tracked evidence changes.
    for line in git('diff', '--name-status', start['base_commit'], '--', 'docs/plans/ocean-v1/evidence').splitlines():
        assert line.startswith('A\tdocs/plans/ocean-v1/evidence/C25/'), line
    records = [
        ('P00', 'mockups/p00/source-revision.json', 'files', P00_SOURCE),
        ('C18', 'evidence/C18/delivery.json', 'files', None),
        ('C22', 'evidence/C22/delivery.json', 'source_files', None),
        ('C23', 'evidence/C23/operator-hosted-f6f823b/receipt.json', 'source_files', None),
        ('C24', 'evidence/C24/delivery.json', 'source_files', None),
    ]
    prerequisites, current_sources = {}, {}
    for component, relative, key, historical in records:
        path = BASE / relative
        assert sha(path) == source_sha(start['base_commit'], str(path.relative_to(ROOT)))
        receipt = read(path)
        commit = historical or receipt['source_commit']
        entries, supersessions = receipt[key], {}
        for name, expected in entries.items():
            assert source_sha(commit, name) == expected, (component, name)
            current = sha(ROOT / name)
            assert current == source_sha(ACCEPTED, name), name
            current_sources[name] = current
            if current != expected:
                supersessions[name] = {
                    'original_sha256': expected, 'current_accepted_sha256': current,
                    'latest_source_change': git('log', '-1', '--format=%H %s', '--', name),
                    'acceptance': 'Intentional later overhaul source, covered by exact-source hosted CI40663077852',
                }
        prerequisites[component] = {
            'receipt': str(path.relative_to(ROOT)), 'receipt_sha256': sha(path),
            'original_accepted_source': commit, 'source_entries': len(entries),
            'unchanged_entries': len(entries) - len(supersessions), 'intentional_supersessions': supersessions,
        }
        if component == 'P00':
            for name, expected in receipt['screenshots'].items():
                assert sha(BASE / 'mockups/p00' / name) == expected
        elif component == 'C18':
            assert receipt['state'].startswith('Complete') and receipt['hosted_ci']['run']['conclusion'] == 'success'
            for field in ('original_local_receipt_sha256', 'accepted_source_receipt_sha256'):
                assert receipt[field]
        elif component == 'C22':
            assert receipt['state'].startswith('Complete') and receipt['hosted_run']['conclusion'] == 'success'
            for field in ('local_receipt', 'hosted_receipt'):
                ref = receipt[field]
                assert sha(ROOT / ref['path']) == ref['sha256']
        elif component == 'C23':
            assert receipt['required_hosted_CI_complete'] and set(receipt['required_job_results'].values()) == {'success'}
            complete = read(BASE / 'evidence/C23/completion-20261028.json')
            assert complete['status'] == 'Complete' and complete['required_CI_complete']
            for name, expected in complete['receipt_sha256'].items():
                assert sha(BASE / 'evidence/C23' / name) == expected
        elif component == 'C24':
            assert receipt['state'].startswith('Complete')
            assert len(receipt['required_job_results']) == 4 and set(receipt['required_job_results'].values()) == {'success'}
            assert receipt['provider_schema_validated'] is False and receipt['dispatch_enabled'] is False
    run = read(BASE / 'evidence/C24/hosted-eeec2e1/run.json')
    assert run['head_sha'] == ACCEPTED and run['status'] == 'completed' and run['conclusion'] == 'success'
    actions = sorted(EXPERIMENT_REQUEST_MODELS)
    assert actions == ['approve', 'create', 'dispatch', 'events', 'get', 'list', 'retry', 'revise', 'status']
    route_actions = sorted(route.path.rsplit('/', 1)[-1] for route in router.routes)
    assert route_actions == actions
    assert ExperimentSnapshot.model_json_schema()['properties']['execution_performed']['const'] is False
    # This pins the inspected current placeholder; it is not C25 UI acceptance.
    workspace = ROOT / 'frontend-v1/src/research-workspace.tsx'
    assert 'Experiments are unavailable until proposal and execution services are connected.' in workspace.read_text()
    checks = {}
    for name in ('frontend-baseline', 'backend-baseline', 'typecheck', 'build'):
        data = read(OUT / (name + '.json'))
        assert data['exit_code'] == 0, name
        checks[name] = {**data, 'stdout_sha256': sha(OUT / (name + '.stdout.txt')),
                       'stderr_sha256': sha(OUT / (name + '.stderr.txt'))}
    return {
        'version': 'c25-readiness-v1', 'recorded_at': datetime.now(timezone.utc).isoformat(),
        'base_commit': start['base_commit'], 'branch': 'overhaul',
        'decision': 'Ready to begin checkpoint1/local C25 implementation; later service acceptance has explicit contract prerequisites',
        'implementation_selected': False, 'component_status': 'Not started',
        'ready_to_start_proposal_review_and_approval_UI': True,
        'full_execution_results_service_contract_ready': False,
        'live_beta_ready': False, 'prerequisites': prerequisites,
        'source_entry_count': sum(p['source_entries'] for p in prerequisites.values()),
        'current_source_files': dict(sorted(current_sources.items())),
        'current_accepted_source': ACCEPTED, 'hosted_run': run['html_url'],
        'public_actions': actions, 'execution_performed_contract': False,
        'missing_public_contracts': [
            'Trusted experiment runtime capability/discovery; current v1 runtime has no experiment execution capability',
            'Owner-authorized retained execution status/progress and exact approval/context binding',
            'Idempotent cancellation request and separately proven physical termination/terminal outcome',
            'Owner-authorized validated output manifest/table/raster/download and result/evidence attachment contract',
        ],
        'required_contract_order': 'Preserve research-experiments-v1 review semantics; accept a bounded C22/C23 public execution/artifact contract amendment before C25 checkpoints2/3 claim actual service parity',
        'separate_live_integration_gate': 'Authenticated beta hosting/proxy, real Cloud Tasks/outbox adapter and production worker supervisor plus provider/live isolation before C26 live acceptance',
        'checks': checks, 'unrelated_paths_preserved': len(start['protected_sha256']),
        'prior_evidence_tree': start['prior_evidence_tree'],
        'cloud_DNS_or_production_actions': 'none', 'scheduler': 'PAUSED',
        'qualification': 'Original receipts and accepted user UX direction retained; fixtures may test unavailable or proposed execution contracts but cannot imply worker availability, execution, deployment or scientific approval.',
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--verify-only', action='store_true')
    args = parser.parse_args()
    receipt = verify()
    if not args.verify_only:
        with (OUT / 'verification.json').open('x') as stream:
            json.dump(receipt, stream, indent=2, sort_keys=True)
            stream.write('\n')
    print(json.dumps({
        'ready_to_start_C25': True, 'full_execution_contract_ready': False,
        'source_entries': receipt['source_entry_count'], 'unique_sources': len(receipt['current_source_files']),
        'implementation': 'Not started', 'beta_deployment': 'not ready',
    }))


if __name__ == '__main__':
    main()
