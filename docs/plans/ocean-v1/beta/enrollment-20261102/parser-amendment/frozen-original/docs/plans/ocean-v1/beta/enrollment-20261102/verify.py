"""Read-only first-account source and local evidence pins; no tests or IO calls."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
HERE = Path(__file__).resolve().parent


def main():
    receipt = json.loads((HERE / 'receipt.json').read_text())
    for path, expected in receipt['source_pins'].items():
        assert hashlib.sha256((ROOT / path).read_bytes()).hexdigest() == expected, path
    for path, expected in receipt['artifact_pins'].items():
        assert hashlib.sha256((HERE / path).read_bytes()).hexdigest() == expected, path
    for path, expected in receipt['accepted_contract_pins'].items():
        assert hashlib.sha256((ROOT / path).read_bytes()).hexdigest() == expected, path
    result = json.loads((HERE / 'checks.json').read_text())
    assert result['passed'] == 41 and len(result['checks']) == 41
    assert not result['native_postgresql_or_cloud_calls']
    assert not result['real_google_or_sdk_token_acquired'] and not result['actual_user_enrolled']
    assert json.loads((HERE / 'default-plan.json').read_text())['state'] == 'plan_only'
    print(json.dumps({'state': 'verified_preparation_only', 'offline_checks': 41,
        'source_pins': len(receipt['source_pins']), 'real_identity_or_cloud_calls': False,
        'native_or_live_enrollment_accepted': False}, sort_keys=True))


if __name__ == '__main__':
    main()
