"""Record one create-only, source-steady focused profile acceptance attempt."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import time

ROOT = Path(__file__).resolve().parents[6]
HERE = Path(__file__).resolve().parent
OWNED = [
    'orchestration/experiment_sandbox/profile.py',
    'tests/test_experiment_sandbox_profile.py',
    *[str(p.relative_to(ROOT)) for p in sorted((ROOT / 'sandbox/experiment').iterdir()) if p.is_file()],
]
SHARED = ['orchestration/experiment_sandbox/contracts.py', 'tests/test_experiment_sandbox_contracts.py']


def pins(names):
    return {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in names}


def main():
    report = HERE / 'verification.json'
    if report.exists():
        raise SystemExit('Original profile acceptance is immutable')
    before = pins(OWNED + SHARED)
    commands = [
        ('.venv/bin/python', '-m', 'pytest', 'tests/test_experiment_sandbox_profile.py', '-q'),
        ('.venv/bin/python', '-m', 'ruff', 'check', 'orchestration/experiment_sandbox/profile.py',
         'tests/test_experiment_sandbox_profile.py', 'sandbox/experiment/verify_image.py'),
    ]
    checks = []
    for index, command in enumerate(commands, 1):
        log = HERE / ('pytest.txt' if index == 1 else 'ruff.txt')
        started = time.monotonic()
        with log.open('x') as output:
            result = subprocess.run(command, cwd=ROOT, stdout=output, stderr=subprocess.STDOUT, check=False)
        checks.append({'command': list(command), 'exit_code': result.returncode,
                       'duration_seconds': time.monotonic() - started,
                       'log': str(log.relative_to(ROOT)), 'sha256': hashlib.sha256(log.read_bytes()).hexdigest()})
    after = pins(OWNED + SHARED)
    changes = sorted(name for name in before if before[name] != after[name])
    data = {'component': 'C23', 'checkpoint': 'Fixed profile and offline image preparation only',
        'recorded_at': datetime.now(timezone.utc).isoformat(),
        'success': all(item['exit_code'] == 0 for item in checks) and not changes,
        'files': {name: after[name] for name in OWNED},
        'tested_shared_sources': {name: after[name] for name in SHARED},
        'source_before': before, 'source_after': after, 'source_changed_during_run': changes,
        'checks': checks, 'configuration_only': True, 'dispatch_eligible': False,
        'actual_containment_tested': False, 'built_image_digest': None,
        'not_performed': ['No downloads, installs, builds or runtime/container execution',
                          'No generated Python, real scientific data, cloud or provider operation'],
        'remaining_gates': ['Compatible authorized Linux/gVisor target and complete pinned runtime installation',
            'Verified scientific image/lock/wheels and authenticated immutable rootfs provenance',
            'Actual identity/namespace/mapping/resource/tmpfs/log enforcement and containment acceptance',
            'Race-free guest tmpfs output extraction and verified whole-job teardown',
            'Repeated numerical fixtures under declared seeds and tolerances'],
        'harness_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    with report.open('x') as output:
        json.dump(data, output, indent=2, sort_keys=True)
        output.write('\n')
    print(json.dumps({'success': data['success'], 'source_changed': changes, 'checks': checks,
                      'receipt_sha256': hashlib.sha256(report.read_bytes()).hexdigest()}))
    raise SystemExit(0 if data['success'] else 1)


if __name__ == '__main__':
    main()
