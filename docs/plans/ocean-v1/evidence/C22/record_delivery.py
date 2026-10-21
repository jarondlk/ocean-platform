"""Create C22 delivery metadata only after exact-source hosted/local acceptance.

No test, service, migration, commit, fetch or push is performed. A read-only
ls-remote verifies the already-authorized source push. All inputs and final
source/CI identifiers are explicit, including a possible test-only amendment.
Existing reports are never replaced; this helper imports only pure validators
from its sibling and invokes them after parsing CLI arguments.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import re
import subprocess

from freeze_local import (
    GateError, HERE, ROOT, aggregate, ancestry, audit_backend,
    audit_frontend_reuse, audit_native, audit_reviews_and_export, audit_static,
    commit, coverage, digest, git, load, path, preservation, pytest_counts,
    relative, require, save_new, source_context, verify,
)

REQUIRED_JOBS = {
    'Backend tests and security boundary': (
        'Lint active Python code', 'Check generated chat scope contract',
        'Check C21 evidence and answer wire contract', 'Check frozen catalogue contracts and examples',
        'Run tests with coverage'),
    'Frontend typecheck and build': ('Audit production frontend dependencies', 'Test frontend',
                                     'Typecheck frontend', 'Build frontend'),
    'OCEAN v1 prototype tests and build': ('Audit production prototype dependencies', 'Test prototype',
                                          'Typecheck prototype', 'Build prototype'),
    'PostgreSQL migration and metadata integration': (
        'Apply application migrations', 'Verify invite acceptance and metadata persistence',
        'Verify transactional corpus upsert is idempotent',
        'Verify C03 retention transaction ordering in isolated schemas',
        'Verify C05 vector identity and metagenome replacement history',
        'Verify C09 snapshot capture and publication boundaries',
        'Verify C17 investigation migrations and retained context history',
        'Verify C20 durable execution races and immutable replay',
        'Verify C21 retained evidence and durable synthesis fences',
        'Verify C22 immutable proposals and transactional reservations',
        'Verify database backup and isolated restore'),
}
POSTGRES_SUITES = [82, 12, 12, 21, 60, 44, 23, 21]


def hosted_gates(hosted_path, context, expected_run_id, local_backend, expected_skipped, local_only_passed):
    report = load(hosted_path)
    run = report['run']
    require(report['source_commit'] == context['source_commit'] and run['head_sha'] == context['source_commit'],
            'Hosted acceptance must bind the explicit final source commit')
    require(run['id'] == expected_run_id and run['head_branch'] == 'overhaul' and run['event'] == 'push'
            and run['status'] == 'completed' and run['conclusion'] == 'success',
            'The selected exact-source overhaul push run has not succeeded')
    jobs = {job['name']: job for job in report['jobs']}
    require(len(jobs) == len(report['jobs']) and REQUIRED_JOBS.keys() <= jobs.keys(), 'Required hosted jobs are missing or duplicated')
    for name, required_steps in REQUIRED_JOBS.items():
        job = jobs[name]
        require(job['status'] == 'completed' and job['conclusion'] == 'success', f'Hosted job is incomplete: {name}')
        steps = {step['name']: step for step in job['steps']}
        for step in required_steps:
            require(step in steps and steps[step]['status'] == 'completed' and steps[step]['conclusion'] == 'success',
                    f'Required hosted step is incomplete: {name}/{step}')
    checks = report['checks']
    require(checks['backend']['passed'] == local_backend['passed'] - local_only_passed
            and checks['backend']['skipped'] == expected_skipped
            and checks['backend'].get('failed', 0) == checks['backend'].get('errors', 0) == 0
            and checks['backend']['coverage_percent'] >= 70, 'Hosted backend counts/coverage do not reconcile with local acceptance')
    require(local_only_passed == 9, 'Only the nine preserved unrelated local benchmark cases may differ')
    require(checks['postgres_suites'] == POSTGRES_SUITES and sum(POSTGRES_SUITES) == 275, 'All eight actual hosted PostgreSQL suites must pass275 cases')
    require(checks['frontend_v1_passed'] == 930 and checks['frontend_legacy_passed'] == 132,
            'Both hosted frontends must retain the930/132 test counts')
    for name in ('generated_contracts', 'lint', 'frontend_typechecks_builds_audits', 'migration_upsert_backup_restore'):
        require(checks[name] == 'passed', f'Hosted acceptance gate is incomplete: {name}')
    logs = report['logs']
    required_logs = {'backend', 'postgres', 'frontend-v1', 'frontend-legacy'}
    require(required_logs <= logs.keys(), 'All four original hosted job logs are required')
    for item in logs.values():
        require(digest(item['path']) == item['sha256'], 'Hosted original log hash differs')
    backend_text = path(logs['backend']['path']).read_text()
    backend_counts, _ = pytest_counts(backend_text)
    require(backend_counts == {'passed': local_backend['passed'] - 9, 'skipped': expected_skipped},
            'Actual hosted backend log disagrees with recorder totals')
    require(coverage(backend_text) == checks['backend']['coverage_percent'], 'Hosted coverage log disagrees with recorder')
    postgres_text = path(logs['postgres']['path']).read_text()
    summaries = [pytest_counts(line)[0] for line in postgres_text.splitlines() if re.search(r'\b\d+ passed\b', line)]
    require(summaries == [{'passed': count} for count in POSTGRES_SUITES], 'Actual hosted PostgreSQL summaries do not prove all275 cases')
    for key, expected in (('frontend-v1', 930), ('frontend-legacy', 132)):
        text = path(logs[key]['path']).read_text()
        passes = re.findall(r'# pass\s+(\d+)\b', text)
        failures = re.findall(r'# fail\s+(\d+)\b', text)
        require(passes and int(passes[-1]) == expected and failures and int(failures[-1]) == 0,
                f'Actual hosted frontend test log disagrees: {key}')
    return report


def pushed_source(context):
    require(git('branch', '--show-current') == 'overhaul', 'Delivery must remain on overhaul')
    ancestry(context['source_commit'], 'HEAD')
    remote = subprocess.check_output(['git', 'ls-remote', '--exit-code', 'origin', 'refs/heads/overhaul'],
                                     cwd=ROOT, timeout=60).decode().strip().splitlines()
    require(len(remote) == 1, 'Remote overhaul reference is unavailable or ambiguous')
    fields = remote[0].split()
    require(len(fields) == 2 and fields[1] == 'refs/heads/overhaul' and re.fullmatch(r'[a-f0-9]{40}', fields[0]),
            'Remote overhaul response is invalid')
    remote_commit = commit(fields[0])
    ancestry(context['source_commit'], remote_commit)
    return remote_commit


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-commit', required=True)
    parser.add_argument('--source-map', required=True)
    parser.add_argument('--amendment-map')
    parser.add_argument('--baseline-source-commit')
    parser.add_argument('--local-receipt', required=True)
    parser.add_argument('--hosted-receipt', required=True)
    parser.add_argument('--run-id', type=int, required=True)
    parser.add_argument('--hosted-backend-skipped', type=int, required=True)
    parser.add_argument('--local-only-passed', type=int, default=9)
    parser.add_argument('--backend-qualification')
    parser.add_argument('--output', default=str(HERE / 'delivery.json'))
    args = parser.parse_args()
    require(not path(args.output).exists(), 'Original delivery receipts are immutable')
    context = source_context(args.source_commit, args.source_map, args.amendment_map, args.baseline_source_commit)
    start, supersessions = preservation(context)
    local = load(args.local_receipt)
    require(local['component'] == 'C22' and local['preserved_prior_evidence_count'] == 1204,
            'A complete C22 local receipt is required')
    require(local['source_sha256'] == aggregate(local['files']), 'Local source aggregate is invalid')
    local_is_final = local['files'] == context['files'] and local['source_commit'] == context['source_commit']
    local_is_baseline = bool(context['amended']) and local['files'] == context['base_files'] and local['source_commit'] == context['baseline_source_commit']
    require(local_is_final or local_is_baseline, 'Local source is neither the final map nor the explicitly amended baseline')
    verify(local['files'], allowed=context['amended'])
    verify(local['tested_transitive_source_files'], allowed=context['amended'])
    verify(local['evidence_files'])
    require(local['protected_counts'] == {key: len(files) for key, files in start['preservation'].items()},
            'Local protected groups differ from the immutable start snapshot')
    backend_qualification = args.backend_qualification or local['inputs'].get('backend_qualification')
    original_backend = local['checks']['backend']
    backend, _ = audit_backend(context, local['inputs']['backend_result'], original_backend['passed'],
                               original_backend['skipped'], backend_qualification)
    # Reconcile original local gates again. Reading the148-case qualification is
    # not represented as a rerun, and superseding hosted275 is independently required.
    native, static = audit_native(context), audit_static(context)
    reviews, frontend = audit_reviews_and_export(), audit_frontend_reuse()
    hosted = hosted_gates(args.hosted_receipt, context, args.run_id, backend,
                          args.hosted_backend_skipped, args.local_only_passed)
    remote_head = pushed_source(context)
    verify(context['files'])
    record = {'component': 'C22', 'recorded_at': datetime.now(timezone.utc).isoformat(),
        'state': 'Complete for authorized separate-v1 synthetic/local C22 implementation and exact-source hosted acceptance',
        'branch': 'overhaul', 'source_commit': context['source_commit'], 'source_files': context['files'],
        'source_sha256': context['source_sha256'], 'remote_overhaul_head': remote_head,
        'local_receipt': {'path': relative(args.local_receipt), 'sha256': digest(args.local_receipt)},
        'hosted_receipt': {'path': relative(args.hosted_receipt), 'sha256': digest(args.hosted_receipt)},
        'hosted_run': hosted['run'], 'checks': hosted['checks'],
        'local_checks': {'backend': backend, 'actual_postgres': native, 'static': static,
                         'frontend_reuse': frontend, 'independent_reviews': reviews},
        'intentional_source_supersessions': supersessions,
        'test_only_amendment': {'map': context['amendment_map_path'], 'baseline_source_commit': context['baseline_source_commit'],
                               'changed_paths': sorted(context['amended']), 'backend_qualification': backend['qualification'],
                               'qualification': 'Original local broad run and source-drift record remain immutable; the approved deterministic coordination test is separately exercised. Prior hosted timeout cause is not inferred.'}
                              if context['amended'] else None,
        'preserved_prior_evidence_count': 1204, 'protected_counts': local['protected_counts'],
        'external_gates': local['external_gates'],
        'next_component': 'C23 readiness must audit this delivered C22 source; real Linux/gVisor containment, configuration and deployment are separate gates'}
    save_new(args.output, record)
    print(json.dumps({'component': 'C22', 'source_commit': context['source_commit'], 'state': record['state'],
                      'output': relative(args.output), 'sha256': digest(args.output)}))


if __name__ == '__main__':
    try:
        main()
    except (GateError, OSError, ValueError, KeyError, subprocess.SubprocessError) as error:
        raise SystemExit('C22 delivery receipt refused: ' + str(error)) from None
