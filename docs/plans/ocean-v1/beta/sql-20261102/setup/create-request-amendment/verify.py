"""Read-only create-body amendment and unchanged predecessor/failure pins."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[7]
HERE = Path(__file__).resolve().parent


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    receipt = json.loads((HERE / 'receipt.json').read_text())
    for path, expected in receipt['source_pins'].items():
        assert sha(ROOT / path) == expected, path
    for path, expected in receipt['artifact_pins'].items():
        assert sha(HERE / path) == expected, path
    for path, expected in receipt['immutable_predecessor_and_provider_pins'].items():
        assert sha(ROOT / path) == expected, path
    original = json.loads((HERE.parent / 'receipt.json').read_text())
    for path, expected in original['source_pins'].items():
        actual = (HERE.parent / 'operator-revision-amendment/render_jobs.before.py'
            if path == 'deploy/gcp/beta/setup/render_jobs.py' else ROOT / path)
        assert sha(actual) == expected, path
    for path, expected in original['artifact_pins'].items():
        assert sha(HERE.parent / path) == expected, path
    before = (HERE / 'render_jobs.before.py').read_bytes()
    removed = b'            "name": "projects/" + PROJECT + "/locations/" + REGION + "/jobs/" + name,\n'
    assert before.count(removed) == 1
    assert before.replace(removed, b'') == (ROOT / 'deploy/gcp/beta/setup/render_jobs.py').read_bytes()
    result = json.loads((HERE / 'checks.json').read_text())
    assert result['stage_checks_passed'] == 4 and result['actual_cli_serialization_passed']
    assert not result['cloud_calls'] and not result['secret_generation']
    print(json.dumps({'state': 'verified_local_amendment', 'stage_checks': 4,
        'actual_cli_serialization_passed': True, 'historical_setup_receipt_preserved': True,
        'provider_revalidation_claimed': False, 'cloud_calls': False}, sort_keys=True))


if __name__ == '__main__':
    main()
