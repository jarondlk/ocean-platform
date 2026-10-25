"""Create-only source-bound preparation receipt for the tmpfs quota amendment."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[7]
BASE = Path(__file__).resolve().parent
SOURCES = (
    'sandbox/experiment/trusted_init.py',
    'orchestration/experiment_sandbox/profile_execution.py',
    'tests/test_experiment_sandbox_trusted_init.py',
    'tests/test_experiment_sandbox_profile_execution.py',
)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    target = BASE / 'local-acceptance-01'
    target.mkdir()
    original = json.loads((BASE.parents[1] / 'pushed-checkpoint.json').read_text())['source_files']
    prior = json.loads((BASE / 'prior-source.json').read_text())
    assert all(sha(BASE / 'prior-source' / path) == value for path, value in prior.items())
    assert all(sha(ROOT / path) == value for path, value in original.items())
    before = {path: sha(ROOT / path) for path in SOURCES}
    checks = []
    for number, argv in enumerate((
        [sys.executable, '-m', 'pytest', *SOURCES[2:], '-q', '--tb=short'],
        [sys.executable, '-m', 'ruff', 'check', *SOURCES],
    ), 1):
        run = subprocess.run(argv, cwd=ROOT, capture_output=True, text=True)
        log = target / f'check-{number}.txt'
        log.write_text(run.stdout + run.stderr)
        checks.append({'command': argv, 'exit_code': run.returncode,
                       'log': str(log.relative_to(ROOT)), 'log_sha256': sha(log)})
        print(json.dumps(checks[-1]))
    after = {path: sha(ROOT / path) for path in SOURCES}
    assert before == after
    assert all(sha(ROOT / path) == value for path, value in original.items())
    receipt = {
        'kind': 'Trusted-init-v2/profile-v3 tmpfs quota LOCAL PREPARATION amendment',
        'component': 'C23', 'recorded_at': datetime.now(timezone.utc).isoformat(),
        'source_files_before': before, 'source_files_after': after,
        'supersedes_additive_source_hashes': prior,
        'prior_source_snapshot_preserved': True,
        'original_78_case_receipt_immutable': True,
        'initial_built_image_not_replaced_by_this_recorder': True,
        'original_preparation_paths_unchanged': len(original),
        'checks': checks, 'passed': all(check['exit_code'] == 0 for check in checks),
        'recorder_sha256': sha(Path(__file__)), 'design_sha256': sha(BASE / 'design.md'),
        'development_runs': ['98 passed in3.60s; Ruff passed',
                             'Additional negative owner/capability-ABI/readback cases:106 passed in3.72s; Ruff passed'],
        'C23_complete': False, 'real_runtime_tested': False,
        'dispatch_eligible': False, 'reservation_released': False,
        'qualifications': [
            'All mount/capability/UID/process effects in local tests are refused or replaced by safe fakes',
            'Pinned source analysis is not actual quota/containment/termination evidence',
            'New image digest/rootfs inventory and actual Linux ENOSPC/write-denial/capability probes remain required',
            'Original C22 guard, public dispatch, source/access/revocation and reservation release remain unchanged',
        ],
    }
    with (target / 'verification.json').open('x') as stream:
        json.dump(receipt, stream, indent=2, sort_keys=True)
        stream.write('\n')
    print('receipt_sha256=' + sha(target / 'verification.json'))
    if not receipt['passed']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
