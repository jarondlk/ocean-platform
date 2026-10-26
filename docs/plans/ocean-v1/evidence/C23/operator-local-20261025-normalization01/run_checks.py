"""Source-bound host-safe C23 operator checks; no cloud/analysis execution."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import platform
import sqlite3
import subprocess
import time

ROOT = Path(__file__).resolve().parents[6]
OUT = Path(__file__).resolve().parent
BASE = ROOT / 'docs/plans/ocean-v1/evidence/C23'
SUITES = [f'tests/test_experiment_sandbox_{name}.py' for name in (
    'journal', 'trusted_init', 'profile_execution', 'linux_runtime',
    'operator_acceptance', 'integration', 'normalize_rootfs', 'image_materialization')]


def sha(path):
    checksum = hashlib.sha256()
    with path.open('rb') as stream:
        for raw in iter(lambda: stream.read(1024**2), b''):
            checksum.update(raw)
    return checksum.hexdigest()


def create(name, value):
    with (OUT / name).open('x') as stream:
        json.dump(value, stream, sort_keys=True, indent=2)
        stream.write('\n')


def sources():
    paths = {ROOT / name for name in SUITES}
    for directory in ('orchestration/experiment_sandbox', 'sandbox/experiment'):
        for path in (ROOT / directory).rglob('*'):
            if path.is_file() and '__pycache__' not in path.parts and (
                    path.suffix in {'.py', '.sh', '.json', '.lock', '.md'}
                    or path.name.startswith('Containerfile') or path.name == '.containerignore'):
                paths.add(path)
    paths.add(Path(__file__).resolve())
    return {str(p.relative_to(ROOT)): sha(p) for p in sorted(paths)}


def retained():
    original = json.loads((BASE / 'start-snapshot.json').read_text())
    original_source = dict(original['prior_source_files'])
    original_source.update(json.loads((BASE / 'checkpoint.json').read_text())['source_files'])
    amendment = json.loads((BASE / 'dependency-hosted.json').read_text())['source_files']
    original_source.update(amendment)
    unrelated = {}
    # These are preexisting user edits outside C23. Retain their current bytes
    # and name the historical difference; never silently bless another drift.
    for path in ('README.md', 'deploy/gcp/job-evaluation.template.yaml'):
        if path in original_source and sha(ROOT / path) != original_source[path]:
            unrelated[path] = {'original_sha256': original_source[path],
                               'preexisting_current_sha256': sha(ROOT / path)}
            original_source[path] = unrelated[path]['preexisting_current_sha256']
    evidence = original['prior_evidence_files']
    for group in (original_source, evidence):
        for path, expected in group.items():
            if sha(ROOT / path) != expected:
                raise AssertionError(f'Unrecorded prior source/evidence drift: {path}')
    return {'source_files': original_source, 'prior_evidence_files': evidence,
            'intentional_prior_source_supersessions': amendment,
            'preexisting_unrelated_source_differences': unrelated}


def protected():
    paths = [ROOT / 'README.md', ROOT / 'deploy/gcp/job-evaluation.template.yaml']
    for name in ('docs/LLM_MODEL_BENCHMARK_2026-10-09.md',
                 'docs/REPOSITORY_AUDIT_2026-10-09.md',
                 'docs/REPOSITORY_AUDIT_2026-10-12.md', 'tests/test_model_benchmark.py'):
        if (ROOT / name).exists():
            paths.append(ROOT / name)
    for name in ('docs/audits', 'docs/benchmarks', 'evaluation/model_benchmark'):
        paths.extend(p for p in (ROOT / name).rglob('*')
                     if p.is_file() and '__pycache__' not in p.parts)
    return {str(path.relative_to(ROOT)): sha(path) for path in sorted(paths)}


def main():
    assert (ROOT / '.git').exists() and (ROOT / '.venv/bin/python').exists()
    start = {'recorded_at': datetime.now(timezone.utc).isoformat(),
             'host': {'system': platform.system(), 'machine': platform.machine(),
                      'python': platform.python_version(), 'sqlite': sqlite3.sqlite_version},
             'source_files': sources(), 'retained': retained(), 'protected': protected()}
    create('start.json', start)
    checks = []
    python_sources = [p for p in start['source_files'] if p.endswith('.py')]
    commands = [
        ('pytest', [str(ROOT / '.venv/bin/python'), '-m', 'pytest', '-o', 'addopts=', '-q', *SUITES]),
        ('ruff', [str(ROOT / '.venv/bin/ruff'), 'check', *python_sources]),
        ('bash', ['bash', '-n', *[p for p in start['source_files'] if p.endswith('.sh')]]),
    ]
    for name, command in commands:
        began = time.monotonic()
        with (OUT / (name + '.stdout.txt')).open('xb') as stdout:
            with (OUT / (name + '.stderr.txt')).open('xb') as stderr:
                completed = subprocess.run(command, cwd=ROOT, stdout=stdout, stderr=stderr,
                                           timeout=600, check=False)
        checks.append({'name': name, 'command': command, 'exit_code': completed.returncode,
                       'seconds': round(time.monotonic() - began, 3)})
    end = {'source_files': sources(), 'retained': retained(), 'protected': protected()}
    steady = all(end[key] == start[key] for key in end)
    evidence = {str(path.relative_to(ROOT)): sha(path) for path in sorted(OUT.iterdir())
                if path.is_file()}
    result = {'version': 'c23-operator-local-verification-v1',
              'recorded_at': datetime.now(timezone.utc).isoformat(), 'checks': checks,
              'source_files': end['source_files'], 'source_steady': steady,
              'prior_source_paths_checked': len(end['retained']['source_files']),
              'preexisting_unrelated_source_differences': end['retained']['preexisting_unrelated_source_differences'],
              'prior_evidence_paths_preserved': len(end['retained']['prior_evidence_files']),
              'protected_paths_preserved': len(end['protected']), 'evidence_files': evidence,
              'cloud_operations_performed': False, 'actual_containment_verified': False,
              'C23_complete': False, 'production_dispatch': False, 'automation': 'PAUSED'}
    create('verification.json', result)
    print(json.dumps({'checks': checks, 'source_steady': steady,
                      'source_files': len(end['source_files'])}, sort_keys=True))
    if not steady or any(check['exit_code'] for check in checks):
        raise SystemExit(1)


if __name__ == '__main__':
    main()
