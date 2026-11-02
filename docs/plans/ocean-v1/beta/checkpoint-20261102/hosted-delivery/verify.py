"""Read-only reconciliation of captured hosted CI and current application source."""
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[5]


def read(name):
    return json.loads((HERE / name).read_text())


def verify():
    delivery, run, jobs = read('delivery.json'), read('run.json'), read('jobs.json')
    for name, expected in delivery['artifact_sha256'].items():
        assert hashlib.sha256((HERE / name).read_bytes()).hexdigest() == expected, name
    assert run['id'] == delivery['run_id'] == 41322838746
    assert run['head_sha'] == delivery['source_commit'] == '50566b7cfa4a0d8ee19686f0109e74f3a2a45d45'
    assert run['status'] == 'completed' and run['conclusion'] == 'success'
    assert run['head_branch'] == 'overhaul'
    required = {'Backend tests and security boundary', 'Frontend typecheck and build',
                'OCEAN v1 prototype tests and build', 'OCEAN v1 authenticated host tests and build',
                'PostgreSQL migration and metadata integration'}
    accepted = {job['name']: job for job in jobs['jobs'] if job['name'] in required}
    assert set(accepted) == required and len(accepted) == delivery['required_jobs_passed'] == 5
    assert all(job['status'] == 'completed' and job['conclusion'] == 'success'
               and job['run_id'] == run['id'] and job['head_sha'] == run['head_sha']
               for job in accepted.values())
    spec = importlib.util.spec_from_file_location('beta_checkpoint_verifier', HERE.parent / 'verify.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    predecessor = module.verify()
    source = json.loads((HERE.parent / 'source-supersession.json').read_text())
    inventory = json.loads((ROOT / 'docs/plans/ocean-v1/evidence/C27/release-manifest.json').read_text())['source']['source_files']
    files = sorted(set(inventory) | set(source['additive_app_sha256']))
    assert len(files) == delivery['source_paths'] == 880
    assert source['composed_source_revision'] == delivery['composed_source_revision'] == predecessor['composed_source_revision']
    diff = subprocess.run(['git', '--literal-pathspecs', 'diff', '--quiet', run['head_sha'], '--', *files],
                          cwd=ROOT, capture_output=True, check=False)
    assert diff.returncode == 0, 'Current application differs from the accepted hosted source'
    assert delivery['backend']['total_passed'] == 1 + 17 + 6729 == 6747
    assert delivery['backend']['combined_coverage_percent'] == '83.67'
    assert delivery['live_release_accepted'] is False and delivery['cloud_or_google_callback_acceptance'] is False
    return {'verified': True, 'source_commit': run['head_sha'], 'required_jobs_passed': 5,
            'application_source_paths': len(files), 'backend_passed': 6747, 'coverage_percent': '83.67',
            'prior_evidence_preserved': predecessor['preserved_evidence_files'],
            'protected_paths_preserved': predecessor['protected_paths'], 'live_release_accepted': False}


if __name__ == '__main__':
    print(json.dumps(verify(), indent=2))
