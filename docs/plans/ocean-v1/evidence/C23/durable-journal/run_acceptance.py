"""Capture the final C23 journal acceptance with before/after source pins."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import platform
import sqlite3
import subprocess
import time

ROOT = Path(__file__).resolve().parents[6]
BASE = Path(__file__).resolve().parent
SOURCES = ('orchestration/experiment_sandbox/journal.py',
           'tests/test_experiment_sandbox_journal.py')


def pins():
    return {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in SOURCES}


def write(name, value):
    with (BASE / name).open('x') as stream:
        json.dump(value, stream, indent=2, sort_keys=True)
        stream.write('\n')


def main():
    before = pins()
    write('acceptance-start.json', {'recorded_at': datetime.now(timezone.utc).isoformat(),
                                  'source_files': before, 'platform': platform.platform(),
                                  'python': platform.python_version(),
                                  'sqlite_runtime_version': sqlite3.sqlite_version,
                                  'recorder_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest()})
    results = []
    commands = [
        ('pytest', [str(ROOT / '.venv/bin/python'), '-m', 'pytest',
                    'tests/test_experiment_sandbox_journal.py', '-q', '--tb=short']),
        ('ruff', [str(ROOT / '.venv/bin/ruff'), 'check', *SOURCES]),
    ]
    for label, command in commands:
        start = time.monotonic()
        with (BASE / f'{label}.stdout.txt').open('x') as stdout:
            with (BASE / f'{label}.stderr.txt').open('x') as stderr:
                result = subprocess.run(command, cwd=ROOT, stdout=stdout, stderr=stderr)
        item = {'check': label, 'command': command, 'exit_code': result.returncode,
                'seconds': round(time.monotonic() - start, 3)}
        results.append(item)
        print(json.dumps(item), flush=True)
    after = pins()
    value = {'recorded_at': datetime.now(timezone.utc).isoformat(), 'results': results,
             'source_files_before': before, 'source_files_after': after,
             'source_steady': before == after,
             'passed': before == after and all(item['exit_code'] == 0 for item in results),
             'real_sqlite_flock_process_tests': True, 'linux_gvisor_execution_performed': False,
             'C23_complete': False, 'reservation_release_authority': False}
    write('acceptance.json', value)
    print(json.dumps(value), flush=True)
    raise SystemExit(0 if value['passed'] else 1)


if __name__ == '__main__':
    main()
