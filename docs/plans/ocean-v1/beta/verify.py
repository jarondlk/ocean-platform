"""Read-only beta preparation check; no credentials, cloud calls or deployment."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess

DIRECTORY = Path(__file__).resolve().parent
ROOT = DIRECTORY.parents[3]
C27 = DIRECTORY.parent / 'evidence/C27'


def read(path):
    return json.loads(path.read_text())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def safe(name):
    path = (ROOT / name).resolve()
    assert path.is_relative_to(ROOT) and path.is_file(), name
    return path


def unresolved(value, prefix=''):
    paths = []
    if isinstance(value, dict):
        for name, child in value.items():
            paths.extend(unresolved(child, prefix + '.' + name if prefix else name))
    elif value is None and prefix != 'browser.cookie_domain':
        paths.append(prefix)
    return paths


def verify():
    audit = read(DIRECTORY / 'source-audit.json')
    assert subprocess.check_output(['git', 'branch', '--show-current'], cwd=ROOT, text=True).strip() == 'overhaul'
    subprocess.run(['git', 'merge-base', '--is-ancestor', audit['checkpoint'], 'HEAD'],
        cwd=ROOT, check=True, capture_output=True)
    for name, identity in audit['source_files'].items():
        path = safe(name)
        assert sha(path) == identity, name
        assert path.read_bytes() == subprocess.check_output(
            ['git', 'show', audit['checkpoint'] + ':' + name], cwd=ROOT), name
    c27_artifacts = C27 / 'package-artifacts.json'
    assert sha(c27_artifacts) == audit['c27_package_manifest_sha256']
    for name, identity in read(c27_artifacts)['sha256'].items():
        assert sha(safe(name)) == identity, name
    candidate = read(C27 / 'release-manifest.json')
    assert candidate['source']['accepted_software_commit'] == audit['accepted_runtime']
    for name, identity in candidate['source']['source_files'].items():
        assert sha(safe(name)) == identity, name
    gates = read(C27 / 'release-gates.json')
    assert len(gates['requirements']) == 20
    assert all(row['status'] == 'not_run' for row in gates['requirements'])
    assert not gates['release_accepted'] and not gates['ready_to_deploy']
    assert any(row['id'] == 'D26-07' and row['status'] == 'open' for row in gates['open_findings'])
    worksheet = read(DIRECTORY / 'cloud-worksheet.json')
    assert worksheet['mode'] == 'offline-planning-only'
    assert all(worksheet[key] is False for key in ('apply_allowed', 'sign_in_performed', 'resources_created'))
    pending = read(ROOT / 'deploy/gcp-v1/examples/site.operator.pending.json')
    assert worksheet['current_c24_input'] == pending
    assert worksheet['public_origin'] == pending['target']['public_origin'] == 'https://beta.oceaninfobio.com'
    assert pending['browser']['cookie_domain'] is None
    assert worksheet['unresolved_operator_fields'] == unresolved(pending)
    assert len(worksheet['unresolved_operator_fields']) == 67
    assert not worksheet['activation']['research_dispatch']
    assert not worksheet['activation']['experiment_dispatch']
    assert not worksheet['activation']['preview_as_production']
    for name, proposal in worksheet['proposals'].items():
        assert name in worksheet['unresolved_operator_fields']
        assert proposal['status'] == 'proposed_not_selected'
        assert isinstance(proposal['value'], str) and proposal['value']
    receipt = read(DIRECTORY / 'preparation-receipt.json')
    assert receipt['scope'] == 'offline-preparation-only' and receipt['implementation_started'] is False
    assert receipt['cloud_operations_performed'] is False and receipt['sign_in_needed_now'] is False
    for name, identity in receipt['artifact_sha256'].items():
        assert sha(safe(name)) == identity, name
    return {'verified': True, 'scope': 'offline-preparation-only',
        'inspected_source_paths': len(audit['source_files']),
        'accepted_runtime_paths_unchanged': len(candidate['source']['source_files']),
        'c27_package_artifacts_unchanged': len(read(c27_artifacts)['sha256']),
        'unresolved_operator_fields': len(worksheet['unresolved_operator_fields']),
        'separate_proposals': len(worksheet['proposals']), 'pending_live_gates': 20,
        'implementation_started': False, 'sign_in_needed_now': False,
        'cloud_operations_performed': False, 'ready_to_deploy': False}


if __name__ == '__main__':
    print(json.dumps(verify(), indent=2))
