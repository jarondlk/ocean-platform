"""Read-only C26 source/receipt verification; local preparation is not release."""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(ROOT))
from evaluation.system_acceptance import content_sha256  # noqa: E402
from schema.system_acceptance import SystemAcceptanceReport  # noqa: E402

DIRECTORY = Path(__file__).resolve().parent
FUNCTIONAL_SOURCE = 'e0874e0aaf138eef762b38fdd0b225551ced1bf5'


def safe(path):
    result = (ROOT / path).resolve()
    if not result.is_relative_to(ROOT) or not result.is_file():
        raise ValueError('Missing or out-of-repository receipt/source path')
    return result


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def blob(raw):
    return hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest()


def read_json(path):
    return json.loads(path.read_text())


JOB_NAMES = {
    'backend': 'Backend tests and security boundary',
    'postgres': 'PostgreSQL migration and metadata integration',
    'v1-frontend': 'OCEAN v1 prototype tests and build',
    'legacy-frontend': 'Frontend typecheck and build',
}
REQUIRED_STEPS = {
    'backend': {
        'Lint active Python code', 'Check generated chat scope contract',
        'Check C21 evidence and answer wire contract',
        'Check frozen catalogue contracts and examples',
        'Run isolated C26 complete 100000-object traversal and lab budget',
        'Run C26 shared-service integration with fresh-process coverage',
        'Run remaining tests and enforce combined coverage',
    },
    'postgres': {
        'Apply application migrations', 'Verify invite acceptance and metadata persistence',
        'Verify transactional corpus upsert is idempotent',
        'Verify C03 retention transaction ordering in isolated schemas',
        'Verify C05 vector identity and metagenome replacement history',
        'Verify C09 snapshot capture and publication boundaries',
        'Verify C17 investigation migrations and retained context history',
        'Verify C20 durable execution races and immutable replay',
        'Verify C21 retained evidence and durable synthesis fences',
        'Verify C22 immutable proposals and transactional reservations',
        'Verify C23 execution fences, restricted proof release and C25 public read compatibility',
        'Verify database backup and isolated restore',
    },
    'v1-frontend': {
        'Audit production prototype dependencies', 'Test prototype',
        'Typecheck prototype', 'Build prototype',
    },
    'legacy-frontend': {
        'Audit production frontend dependencies', 'Test frontend',
        'Typecheck frontend', 'Build frontend',
    },
}


def shell_sections(raw):
    """Bound each command's output by the next Actions shell-step header."""
    text = re.sub(r'\x1b\[[0-?]*[ -/]*[@-~]', '', raw.decode('utf-8'))
    text = re.sub(r'^\d{4}-\d{2}-\d{2}T\S+Z ?', '', text, flags=re.MULTILINE)
    headers = list(re.finditer(r'^##\[group\]Run ([^\n]+)', text, re.MULTILINE))
    assert headers, 'No shell-step headers in retained log'
    return [(header.group(1), text[header.end():headers[index + 1].start()
        if index + 1 < len(headers) else len(text)]) for index, header in enumerate(headers)]


def one_section(sections, command):
    matches = [body for actual, body in sections if actual == command]
    assert len(matches) == 1, ('Missing or duplicate command', command)
    return matches[0]


def pytest_summary(body):
    # Match only final pytest summary lines, never collected-case or warning prose.
    summaries = re.findall(
        r'^=*\s*((?:\d+ (?:passed|failed|skipped|warnings?|errors?|xfailed|xpassed|deselected)'
        r'(?:, )?)+) in \d+(?:\.\d+)?s[^\n]*$', body, re.MULTILINE)
    assert len(summaries) == 1, 'Missing or duplicate bounded pytest summary'
    counts = {label.rstrip('s'): int(count)
        for count, label in re.findall(r'(\d+) ([a-z]+)', summaries[0])}
    assert counts.get('passed', 0) > 0
    assert not any(counts.get(label, 0) for label in
        ('failed', 'error', 'xfailed', 'xpassed', 'deselected'))
    return {'passed': counts['passed'], 'skipped': counts.get('skipped', 0)}


def verify_hosted_log(key, metadata, raw):
    sections = shell_sections(raw)
    pytest = [(command, body) for command, body in sections
        if command.startswith('python -m pytest ')]
    if key == 'backend':
        assert len(pytest) == 3
        assert pytest[0][0] == 'python -m pytest tests/test_system_acceptance_scale.py -q --tb=short'
        assert pytest[1][0] == 'python -m pytest tests/test_experimental_artifact_integration.py \\'
        assert pytest[2][0] == 'python -m pytest tests/ -x -vv --tb=short -o faulthandler_timeout=120 \\'
        scale, covered, remaining = [pytest_summary(body) for _, body in pytest]
        coverage = re.findall(r'Total coverage:\s*([0-9]+(?:\.[0-9]+)?)%', pytest[2][1])
        assert len(coverage) == 1, 'Missing or duplicate final combined coverage result'
        percent = float(coverage[0])
        assert scale == {'passed': 1, 'skipped': 0}
        assert covered == {'passed': 17, 'skipped': 0}
        assert remaining['passed'] > 6000 and percent >= 70
        assert metadata['isolated_scale_passed'] == scale['passed']
        assert metadata['covered_integration_passed'] == covered['passed']
        assert metadata['remaining_tests_passed'] == remaining['passed']
        assert metadata['explicit_skipped'] == remaining['skipped']
        assert metadata['combined_coverage_percent'] == percent
        return {'isolated_scale_passed': scale['passed'],
            'covered_integration_passed': covered['passed'],
            'remaining_tests_passed': remaining['passed'],
            'explicit_skipped': remaining['skipped'], 'combined_coverage_percent': percent}
    if key == 'postgres':
        expected_first_paths = (
            'test_app_metadata_postgres.py', 'test_retention_concurrency_postgres.py',
            'test_retrieval_identity_postgres.py', 'test_catalogue_snapshot_capture_postgres.py',
            'test_investigation_postgres.py', 'test_research_runs_postgres.py',
            'test_research_evidence_postgres.py', 'test_research_experiments_postgres.py',
            'test_experiment_execution_postgres.py',
        )
        assert len(pytest) == len(expected_first_paths)
        results = []
        for (command, body), first in zip(pytest, expected_first_paths):
            assert command.startswith('python -m pytest tests/integration/' + first + ' ')
            results.append(pytest_summary(body))
        passed, skipped = (sum(row[field] for row in results) for field in ('passed', 'skipped'))
        assert metadata['actual_passed'] == passed and metadata['explicit_skipped'] == skipped
        backup = [body for command, body in sections
            if command.startswith('python scripts/database_backup.py create ')]
        assert len(backup) == 1 and metadata['backup_restore'] == 'passed'
        return {'actual_passed': passed, 'explicit_skipped': skipped, 'backup_restore': 'passed'}
    assert not pytest
    body = one_section(sections, 'npm test')
    counts = {}
    for label in ('tests', 'pass', 'fail', 'cancelled', 'skipped', 'todo'):
        found = re.findall(r'^# ' + label + r' (\d+)\s*$', body, re.MULTILINE)
        assert len(found) == 1, ('Missing or duplicate TAP summary', label)
        counts[label] = int(found[0])
    expected = 1051 if key == 'v1-frontend' else 132
    assert counts['tests'] == counts['pass'] == metadata['tests_passed'] == expected
    assert all(counts[label] == 0 for label in ('fail', 'cancelled', 'skipped', 'todo'))
    audit = one_section(sections, 'npm audit --omit=dev --audit-level=moderate')
    assert re.search(r'^found 0 vulnerabilities\s*$', audit, re.MULTILINE)
    assert one_section(sections, 'npm run typecheck').strip()
    assert one_section(sections, 'npm run build').strip()
    assert metadata['typecheck_build_audit'] == 'passed'
    return {'tests_passed': counts['pass'], 'typecheck_build_audit': 'passed'}


def verify(local_only=False):
    local = DIRECTORY / 'implementation-20261030'
    artifacts = read_json(local / 'artifacts.json')
    for entry in artifacts['files']:
        path = safe((local / entry['path']).relative_to(ROOT))
        stored = path.read_bytes()
        assert sha(stored) == entry['retained_sha256'], path
        raw = gzip.decompress(stored) if path.suffix == '.gz' else stored
        assert sha(raw) == entry['raw_sha256'] and len(raw) == entry['raw_bytes'], path
    document = read_json(local / 'report.json')
    report = SystemAcceptanceReport.model_validate(document['acceptance_report'])
    assert report.preparation_complete and not report.release_accepted
    assert report.preparation_status == 'passed' and report.release_status == 'not_run'
    expected = {f'R{number:02d}' for number in range(1, 34)} | {f'G{number}' for number in range(10)}
    assert {row['id'] for row in document['matrix']} == expected
    assert all(row['preparation_status'] == 'passed' and row['full_operational_acceptance'] == 'not_run'
        for row in document['matrix'])
    assert all(value.status == 'passed' and not value.live_quality_established for value in report.comparisons)
    manifest = read_json(local / 'source-manifest.json')
    files = manifest['source_files']
    assert report.source_revision == manifest['source_revision'] == 'sha256:' + content_sha256(files)
    assert artifacts['source_commit'] == FUNCTIONAL_SOURCE and artifacts['source_revision'] == report.source_revision
    target = read_json(DIRECTORY / 'delivery-target.json')
    amendment = read_json(safe((DIRECTORY / target['source_supersession']).relative_to(ROOT)))
    assert amendment['original_functional_source_commit'] == FUNCTIONAL_SOURCE
    assert amendment['original_functional_source_revision'] == report.source_revision
    assert amendment['verification_source_commit'] == target['candidate_source_commit']
    assert amendment['verification_run_id'] == target['run_id']
    assert len(amendment['supersessions']) == 1
    change = amendment['supersessions'][0]
    assert change['path'] == '.github/workflows/tests.yml' and change['from_sha256'] == files[change['path']]
    plan = read_json(safe((DIRECTORY / amendment['plan']).relative_to(ROOT)))
    assert plan['from_sha256'] == change['from_sha256'] and plan['to_sha256'] == change['to_sha256']
    assert plan['coverage_core'] == 'sysmon' and plan['final_combined_coverage_gate'] == 70
    assert plan['first_cases'] == 17 and plan['no_tests_dropped'] and plan['coverage_append_second']
    before = (DIRECTORY / 'ci-isolation-20261030/workflow-before.yml').read_bytes()
    assert sha(before) == change['from_sha256']
    original_tree = {}
    for entry in subprocess.check_output(['git', 'ls-tree', '-r', '-z', FUNCTIONAL_SOURCE], cwd=ROOT).split(b'\0'):
        if entry:
            metadata, name = entry.split(b'\t', 1)
            original_tree[name.decode()] = metadata.decode().split()[2]
    assert blob(before) == original_tree[change['path']]
    effective = {**files, change['path']: change['to_sha256']}
    assert set(effective) == set(files)
    assert amendment['effective_source_revision'] == 'sha256:' + content_sha256(effective)
    source, run_id = target['candidate_source_commit'], target['run_id']
    assert re.fullmatch(r'[a-f0-9]{40}', source) and type(run_id) is int and run_id > 0
    assert target['hosted_directory'] == 'hosted-' + source[:7]
    tree = {}
    for entry in subprocess.check_output(['git', 'ls-tree', '-r', '-z', source], cwd=ROOT).split(b'\0'):
        if entry:
            metadata, name = entry.split(b'\t', 1)
            tree[name.decode()] = metadata.decode().split()[2]
    for name, expected_sha in effective.items():
        raw = safe(name).read_bytes()
        assert sha(raw) == expected_sha and tree.get(name) == blob(raw), name
        if name != change['path']:
            assert original_tree.get(name) == blob(raw), name
    browser = read_json(local / 'browser.json')
    assert browser['source_unchanged'] is True
    assert all(files.get(name) == digest for name, digest in browser['source_files'].items())
    assert {row['id'] for row in browser['checks']} == {'browser-catalogue', 'browser-research', 'browser-experiments', 'browser-accessibility'}
    assert all(row['status'] == 'passed' for row in browser['checks'])
    assert any(row['status'] == 'open' and row['severity'] == 'P2' for row in browser['findings'])
    start = read_json(DIRECTORY / 'implementation-20261029/start.json')
    for name, digest in start['protected_sha256'].items():
        assert sha(safe(name).read_bytes()) == digest, name
    originals = 0
    for entry in subprocess.check_output(['git', 'ls-tree', '-r', '-z', start['prior_evidence_tree']], cwd=ROOT).split(b'\0'):
        if entry:
            metadata, name = entry.split(b'\t', 1)
            mode, _, identity = metadata.decode().split()
            path = safe('docs/plans/ocean-v1/evidence/' + name.decode())
            raw = os.readlink(path).encode() if mode == '120000' else path.read_bytes()
            assert blob(raw) == identity, name
            originals += 1
    jobs = []
    if not local_only:
        hosted = DIRECTORY / target['hosted_directory']
        run = read_json(hosted / 'run.json')
        assert run['head_sha'] == source and run['id'] == run_id and run['status'] == 'completed' and run['conclusion'] == 'success'
        readback = read_json(hosted / 'jobs.json')['jobs']
        job_ids = set()
        for key, name in JOB_NAMES.items():
            metadata = read_json(hosted / (key + '.json'))
            assert metadata['source_commit'] == source and metadata['run_id'] == run_id and metadata['conclusion'] == 'success'
            assert metadata['job'] == key
            job_id = metadata['job_id']
            assert type(job_id) is int and job_id > 0 and job_id not in job_ids
            job_ids.add(job_id)
            matches = [job for job in readback if job['id'] == job_id]
            assert len(matches) == 1
            job = matches[0]
            assert job['name'] == name and job['run_id'] == run_id
            assert job['status'] == 'completed' and job['conclusion'] == 'success'
            steps = job['steps']
            assert len({step['name'] for step in steps}) == len(steps)
            assert REQUIRED_STEPS[key].issubset({step['name'] for step in steps})
            assert all(step['status'] == 'completed' and step['conclusion'] == 'success' for step in steps)
            compressed = (hosted / (key + '.log.gz')).read_bytes()
            raw = gzip.decompress(compressed)
            assert sha(compressed) == metadata['gzip_sha256'] and sha(raw) == metadata['raw_sha256']
            assert len(raw) == metadata['raw_bytes']
            observed = verify_hosted_log(key, metadata, raw)
            jobs.append({'name': key, 'id': job_id, 'conclusion': metadata['conclusion'], **observed})
        assert len(job_ids) == 4
    return {'version': 'c26-delivery-verification-v1', 'source_commit': source,
        'original_functional_source_commit': FUNCTIONAL_SOURCE,
        'original_functional_source_revision': report.source_revision,
        'effective_delivery_source_revision': amendment['effective_source_revision'],
        'workflow_only_supersession_verified': True, 'unchanged_application_paths': len(files) - 1,
        'source_paths': len(files),
        'protected_paths': len(start['protected_sha256']), 'original_receipts': originals,
        'requirements': len(expected), 'local_preparation_verified': True,
        'hosted_verified': not local_only, 'release_accepted': False,
        'open_P2_history_latency_preserved': True, 'jobs': jobs}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--local-only', action='store_true')
    args = parser.parse_args()
    print(json.dumps(verify(local_only=args.local_only), indent=2))
