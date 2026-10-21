"""Record one local C23 checkpoint. Never establishes runtime containment.

Run only after the new source has stopped changing. All outputs are create-only.
No provider, subprocess analysis, VM, container, cloud, migration or Git write.
"""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess
import time

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]


def digest(path):
    return hashlib.sha256((ROOT / path).read_bytes()).hexdigest()


def pins(paths):
    return {str(path): digest(path) if (ROOT / path).is_file() else None for path in sorted(set(paths))}


def inventory():
    tests = sorted(str(path.relative_to(ROOT)) for path in (ROOT / 'tests').glob('test_experiment_sandbox*.py'))
    paths = [path for prefix in ('orchestration/experiment_sandbox', 'sandbox/experiment')
             for path in (ROOT / prefix).rglob('*') if path.is_file() and '__pycache__' not in path.parts]
    if any(path.is_symlink() for path in paths) or any((ROOT / path).is_symlink() for path in tests):
        raise SystemExit('C23 source/test files cannot be symlinks')
    return tests, sorted(str(path.relative_to(ROOT)) for path in paths) + tests


def save(path, value):
    with path.open('x') as stream:
        json.dump(value, stream, indent=2, sort_keys=True)
        stream.write('\n')


def main():
    start = json.loads((HERE / 'start-snapshot.json').read_text())
    directory = HERE / 'local-checkpoint-01'
    directory.mkdir(exist_ok=False)
    tests, new = inventory()
    if len(tests) != 5 or not new:
        raise SystemExit('Expected all five C23 suites and final new source files')
    selected = sorted(set(start['prior_source_files']) | set(new))
    before = pins(selected)
    save(directory / 'source-before.json', before)
    commands = [
        ('tests', [str(ROOT / '.venv/bin/python'), '-m', 'pytest', *tests,
                   'tests/test_artifact_store.py', 'tests/test_security_config.py',
                   'tests/test_research_experiments.py', 'tests/test_frozen_experiment_export.py',
                   '-q', '--color=no']),
        ('ruff', [str(ROOT / '.venv/bin/ruff'), 'check', 'orchestration/experiment_sandbox', *tests]),
    ]
    results = []
    for name, command in commands:
        at = time.monotonic()
        log = directory / (name + '.txt')
        with log.open('x') as stream:
            outcome = subprocess.run(command, cwd=ROOT, stdout=stream, stderr=subprocess.STDOUT, timeout=300, check=False)
        results.append({'name': name, 'argv': command, 'exit_code': outcome.returncode,
                        'elapsed_seconds': time.monotonic() - at, 'log': str(log.relative_to(ROOT)),
                        'log_sha256': digest(log.relative_to(ROOT))})
    tests_after, new_after = inventory()
    added = sorted(set(new_after) - set(new))
    removed = sorted(set(new) - set(new_after))
    after = pins(sorted(set(selected) | set(new_after)))
    save(directory / 'source-after.json', after)
    drift = [name for name in before if before[name] != after[name]]
    preserved = {**start['prior_source_files'], **start['prior_evidence_files']}
    for group in start['preservation'].values():
        preserved.update(group)
    changed_prior = [name for name, expected in preserved.items()
                     if not (ROOT / name).is_file() or digest(name) != expected]
    logs = (directory / 'tests.txt').read_text()
    passed = re.findall(r'\b(\d+) passed\b', logs)
    result = {'component': 'C23', 'recorded_at': datetime.now(timezone.utc).isoformat(),
              'checkpoint': 'Local contracts, synthetic supervisor, staging/output validation and fixed profile preparation',
              'local_checks_passed': all(item['exit_code'] == 0 for item in results)
                  and not drift and not changed_prior and not added and not removed and tests == tests_after,
              'C23_complete': False, 'real_execution_eligible': False, 'runtime_containment_verified': False,
              'source_files': {name: after[name] for name in new}, 'tested_transitive_source_files': after,
              'new_test_files': tests, 'tests_passed': int(passed[-1]) if passed else None,
              'commands': results, 'changed_during_checks': drift, 'changed_prior_files': changed_prior,
              'source_inventory_added': added, 'source_inventory_removed': removed,
              'preserved_prior_source_count': len(start['prior_source_files']),
              'preserved_prior_evidence_count': len(start['prior_evidence_files']),
              'protected_counts': {key: len(group) for key, group in start['preservation'].items()},
              'external_gates': ['No accepted Linux/gVisor host, runtime or image',
                  'No actual containment/resource/termination/numerical acceptance',
                  'Real runtime adapter, durable journal, safe extraction and verified reservation-release integration remain gated',
                  'No production dispatch path, VM/runtime provisioning, real experiments or cloud deployment'],
              'source_supersessions': [], 'automation': 'Still PAUSED by user; manual C23 start only'}
    save(directory / 'verification.json', result)
    print(json.dumps({key: result[key] for key in ('component', 'local_checks_passed', 'tests_passed',
                                                'C23_complete', 'real_execution_eligible')}))
    if not result['local_checks_passed']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
