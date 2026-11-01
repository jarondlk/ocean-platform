"""Verify C27's local release package; this never accepts or deploys a live release."""
from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[5]
DIRECTORY = Path(__file__).resolve().parent
C26 = DIRECTORY.parent / 'C26'
SOFTWARE = 'afe9cb2d1a6d2c28a834daab1a342de4563dc3a3'


def read(path):
    return json.loads(path.read_text())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def safe(name):
    path = (ROOT / name).resolve()
    assert path.is_relative_to(ROOT) and path.is_file(), name
    return path


def run_verifier(path, *args):
    result = subprocess.run([sys.executable, str(DIRECTORY / path), *args],
        cwd=ROOT, check=True, text=True, capture_output=True, timeout=60)
    return json.loads(result.stdout)


def default_flags():
    flags = {}
    for node in ast.parse((ROOT / 'config.py').read_text()).body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            target = node.targets[0]
            if isinstance(target, ast.Name) and target.id.startswith('ENABLE_V1_'):
                call = node.value
                assert isinstance(call, ast.Call) and len(call.args) == 2
                assert ast.literal_eval(call.args[0]) == target.id
                flags[target.id] = ast.literal_eval(call.args[1])
    assert len(flags) == 12 and set(flags.values()) == {'false'}
    return flags


def verify():
    artifacts = read(DIRECTORY / 'package-artifacts.json')
    assert artifacts['version'] == 'c27-package-artifacts-v1'
    for name, expected in artifacts['sha256'].items():
        assert sha(safe(name)) == expected, name
    readiness = run_verifier('readiness-20261101/audit.py', '--verify-only')
    migration = run_verifier('migrations-20261101/verify.py')
    rollback = run_verifier('rollback-20261101/verify.py')
    assert readiness['local_implementation_ready'] and not readiness['release_accepted']
    assert migration['verified'] and migration['checks'] == 20
    assert migration['owned_cluster_stopped_removed'] and not migration['release_accepted']
    assert rollback['verified'] and not rollback['release_accepted']
    manifest = read(DIRECTORY / 'release-manifest.json')
    assert manifest['version'] == 'c27-release-preparation-v1'
    assert manifest['candidate_label'] == 'v1.0.0-rc.1'
    assert manifest['candidate_label_is_git_tag'] is False
    assert manifest['local_preparation_complete'] is True
    assert manifest['ready_to_deploy'] is False and manifest['release_accepted'] is False
    assert manifest['live_actions_performed'] is False
    assert manifest['source']['accepted_software_commit'] == SOFTWARE
    c26delivery = read(C26 / 'delivery.json')
    assert manifest['source']['effective_source_revision'] == c26delivery['effective_delivery_source_revision']
    original = read(C26 / 'implementation-20261030/source-manifest.json')['source_files']
    overlay = read(C26 / c26delivery['source_supersession'])['supersessions'][0]
    expected_files = {**original, overlay['path']: overlay['to_sha256']}
    assert manifest['source']['source_files'] == expected_files
    assert all(sha(safe(name)) == expected for name, expected in expected_files.items())
    target = read(ROOT / 'deploy/gcp-v1/examples/site.operator.pending.json')
    assert manifest['v1_target_worksheet'] == target
    assert target['browser']['cookie_domain'] is None
    assert manifest['target_configuration_complete'] is False
    assert manifest['images_built'] is False and manifest['prior_v1_binary_compatibility'] == 'not_established'
    assert manifest['migration_head'] == readiness['migration_head'] == migration['head_revision']
    assert manifest['flag_profiles']['candidate_defaults'] == default_flags()
    observed = read(DIRECTORY / 'rollback-20261101/accepted/result.json')
    profiles = observed['shared_stack']['profiles']
    assert manifest['flag_profiles']['dispatch_drain'] == profiles['drain_preserve_history']
    assert manifest['flag_profiles']['emergency_unavailable'] == profiles['emergency_unavailable']
    assert manifest['flag_profiles']['synthetic_enabled_profile_is_deployable'] is False
    requirements = read(DIRECTORY / 'requirement-evidence.json')
    original_report = read(C26 / 'implementation-20261030/report.json')
    assert requirements['master_requirements'] == original_report['matrix']
    expected_ids = {f'R{n:02d}' for n in range(1, 34)} | {f'G{n}' for n in range(10)}
    assert {r['id'] for r in requirements['master_requirements']} == expected_ids
    local = requirements['c27_local_acceptance']
    expected_local = {'candidate_source', 'master_traceability', 'isolated_target_and_flags',
        'migration_review_and_sql', 'native_preservation_and_failure', 'dispatch_drain',
        'legacy_compatibility', 'uncertain_execution_capacity', 'operator_recovery', 'approved_transfer'}
    assert {r['id'] for r in local} == expected_local and len(local) == len(expected_local)
    for row in local:
        assert row['status'] == 'passed' and row['evidence_class'] == 'local-preparation'
        assert row['evidence']
        for name in row['evidence']:
            safe(name)
    release = read(DIRECTORY / 'release-gates.json')
    pending = c26delivery['pending_release_requirements']
    assert release['requirements'] == pending and len(pending) == 20
    assert release['release_accepted'] is False and release['ready_to_deploy'] is False
    assert all(r['status'] == 'not_run' for r in release['requirements'])
    assert release['open_findings'] == c26delivery['open_findings']
    assert len(release['open_findings']) == 1 and release['open_findings'][0]['id'] == 'D26-07'
    baseline = read(DIRECTORY / 'baseline-checks.json')
    assert baseline['exit_code'] == 0 and baseline['passed'] == 5 and baseline['skipped'] == 0
    assert '5 passed, 1 warning in 0.34s' in (DIRECTORY / 'baseline-checks.stdout').read_text()
    return {'version': 'c27-package-verification-v1', 'verified': True,
        'accepted_software_commit': SOFTWARE, 'candidate_label': manifest['candidate_label'],
        'local_preparation_complete': True, 'package_artifacts_verified': len(artifacts['sha256']),
        'package_manifest_sha256': sha(DIRECTORY / 'package-artifacts.json'),
        'accepted_source_paths': len(expected_files),
        'prior_evidence_files_preserved': readiness['prior_evidence_files_preserved'],
        'protected_paths_preserved': readiness['protected_paths_preserved'],
        'master_rows': len(expected_ids), 'c27_local_criteria': len(local),
        'migration_checks': migration['checks'], 'migration_head': migration['head_revision'],
        'rollback_verified': True, 'baseline_tests': 5,
        'pending_release_gates': len(pending), 'open_P2': 'D26-07',
        'ready_to_deploy': False, 'release_accepted': False,
        'qualification': 'Local release preparation only; no tag, image build, live integration or promotion.'}


if __name__ == '__main__':
    print(json.dumps(verify(), indent=2))
