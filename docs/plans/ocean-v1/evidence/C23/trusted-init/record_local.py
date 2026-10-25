"""Create-only scoped source-bound trusted-init preparation verification."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[6]
BASE = Path(__file__).resolve().parent
SOURCES = [
    'sandbox/experiment/trusted_init.py',
    'orchestration/experiment_sandbox/profile_execution.py',
    'tests/test_experiment_sandbox_trusted_init.py',
    'tests/test_experiment_sandbox_profile_execution.py',
]


def digest(path):
    return hashlib.sha256((ROOT / path).read_bytes()).hexdigest()


def main():
    target = BASE / 'local-acceptance-01'
    target.mkdir()
    old = json.loads((BASE.parent / 'pushed-checkpoint.json').read_text())['source_files']
    assert all(digest(path) == expected for path, expected in old.items())
    before = {path: digest(path) for path in SOURCES}
    commands = [
        [sys.executable, '-m', 'pytest', SOURCES[2], SOURCES[3], '-q', '--tb=short'],
        [sys.executable, '-m', 'ruff', 'check', *SOURCES],
    ]
    checks = []
    for index, command in enumerate(commands):
        run = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
        log = target / f'check-{index + 1}.txt'
        log.write_text(run.stdout + run.stderr)
        checks.append({'command': command, 'exit_code': run.returncode,
                       'log': str(log.relative_to(ROOT)),
                       'log_sha256': hashlib.sha256(log.read_bytes()).hexdigest()})
        print(json.dumps(checks[-1]))
    after = {path: digest(path) for path in SOURCES}
    assert before == after and all(digest(path) == expected for path, expected in old.items())
    receipt = {
        'kind': 'Additive trusted PID1/profile-v2 LOCAL PREPARATION only',
        'component': 'C23', 'recorded_at': datetime.now(timezone.utc).isoformat(),
        'source_files_before': before, 'source_files_after': after,
        'prior_preparation_paths_unchanged': len(old), 'checks': checks,
        'passed': all(check['exit_code'] == 0 for check in checks),
        'recorder_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'attempt_history': [
            'Initial unrecorded run: 77 passed/1 failed because macOS os lacks setresuid and the negative-guard test tried monkeypatch with raising=True; no privileged operation ran',
            'Initial Ruff identified one unused test import; removed, and negative guard spies use raising=False for absent Linux-only APIs',
            'Subsequent 78-case runs passed; root review identified supervisor-owned input-directory incompatibility for root Linux hosts',
            'New profile-v2 now validates application-owned0500 inputs independently and configures marker/outer cgroup; original v1 renderer remains unchanged',
            'This final recorded run binds exact source before/after and retains the earlier findings without claiming actual guest execution',
        ],
        'C23_complete': False, 'real_runtime_tested': False, 'dispatch_eligible': False,
        'limitations': [
            'Host tests refuse privileged guest operations; they do not test real fork, kill(-1), UID/cap transitions or runsc',
            'Actual pinned-gVisor marker, capabilities, mapping/gofer readability and descendant cleanup remain required',
            'Actual resource/pipe/control-frame isolation, outer-cgroup teardown, durability and numerical acceptance remain required',
            'No C22 API, production dispatch, reservation release, scientific approval or accepted legacy profile/source is changed',
        ],
    }
    with (target / 'verification.json').open('x') as stream:
        json.dump(receipt, stream, indent=2, sort_keys=True)
        stream.write('\n')
    if not receipt['passed']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
