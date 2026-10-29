"""Append-only C25 history-read correction over the preserved 94ca8a4 checkpoint."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[6]
OUT = Path(__file__).resolve().parent
ORIGINAL = OUT.parent / 'implementation-20261028'
BASE = '94ca8a44010c0f2213a362b1ba8630b146468d02'
CHANGED = {'frontend-v1/src/experiment-execution-service.ts',
    'frontend-v1/tests/experiment-execution.test.ts', 'tests/test_experiment_workspace.py'}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify():
    baseline = json.loads((ORIGINAL / 'local-receipt.json').read_text())
    for name, expected in baseline['source_files'].items():
        actual = hashlib.sha256(subprocess.check_output(['git', 'show', BASE + ':' + name], cwd=ROOT)).hexdigest()
        assert actual == expected, name
    for name, expected in baseline['evidence_files'].items():
        assert sha(ORIGINAL / name) == expected, name
    spec = importlib.util.spec_from_file_location('c25_original_audit', ORIGINAL / 'audit.py')
    original_audit = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(original_audit)
    current = original_audit.verify()
    changed = {name for name, expected in baseline['source_files'].items() if current['source_files'][name] != expected}
    assert changed == CHANGED, changed
    current['source_files'][str(Path(__file__).relative_to(ROOT))] = sha(Path(__file__))
    assert '# tests 1051' in (OUT / 'frontend-tests.log').read_text() and '# fail 0' in (OUT / 'frontend-tests.log').read_text()
    assert '2 passed' in (OUT / 'backend-history.log').read_text()
    return {'version': 'c25-history-amendment-v1', 'recorded_utc': datetime.now(timezone.utc).isoformat(),
        'state': 'Amended local acceptance verified; amended exact-source hosted delivery required',
        'supersedes_source': BASE,
        'preserved_local_receipt': {'path': str((ORIGINAL / 'local-receipt.json').relative_to(ROOT)), 'sha256': sha(ORIGINAL / 'local-receipt.json')},
        'source_files': dict(sorted(current['source_files'].items())),
        'source_supersessions': {name: {'original_sha256': baseline['source_files'][name], 'amended_sha256': current['source_files'][name]} for name in sorted(CHANGED)},
        'prerequisites': current['prerequisites'], 'protected_unrelated_paths': current['protected_unrelated_paths'],
        'qualifications': current['qualifications'],
        'change': 'C22 version is a mutable head concurrency token even on historical revisions. Browser merges accept monotonic increased head tokens only when frozen revision/binding/hashes and retained execution continuity remain verified. Backend identity already excludes this token; no backend/public-contract change.',
        'verification': {'frontend_tests': 1051, 'backend_existing_cases': 24, 'new_backend_history_cases': 2,
            'scenarios': ['historical running/completed status/events/artifact/attachment/cancel reopening after a newer proposal',
                'stale token and cross-owner rejection', 'outward callback head race rejected',
                'head-token advance preserves same frozen execution', 'token/revision/binding/state rollback remains rejected']},
        'evidence_files': {p.name: sha(p) for p in sorted(OUT.iterdir()) if p.is_file() and p.name != 'receipt.json'}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--verify-only', action='store_true')
    args = parser.parse_args()
    value = verify()
    path = OUT / 'receipt.json'
    if args.verify_only:
        saved = json.loads(path.read_text())
        assert saved['source_files'] == value['source_files']
        assert saved['source_supersessions'] == value['source_supersessions']
        for name, expected in saved['evidence_files'].items():
            assert sha(OUT / name) == expected, name
    else:
        with path.open('x') as stream:
            stream.write(json.dumps(value, indent=2, sort_keys=True) + '\n')
    print(f"C25 amended acceptance: {len(value['source_files'])} exact source pins; original evidence preserved")


if __name__ == '__main__':
    main()
