"""Read-only exact-flag source supersession and immutable prior evidence."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[6]
HERE = Path(__file__).resolve().parent


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    receipt = json.loads((HERE / 'receipt.json').read_text())
    assert sha(HERE.parent / 'receipt.json') == receipt['predecessor_receipt_sha256']
    assert (HERE / 'original-receipt.json').read_bytes() == (HERE.parent / 'receipt.json').read_bytes()
    prior = json.loads((HERE / 'original-receipt.json').read_text())
    for path, expected in prior['source_pins'].items():
        assert sha(HERE / 'frozen-original' / path) == expected, path
        if path != 'deploy/gcp/beta/enrollment/enroll.py':
            assert sha(ROOT / path) == expected, path
    for path, expected in prior['artifact_pins'].items():
        assert sha(HERE.parent / path) == expected, path
    for path, expected in prior['accepted_contract_pins'].items():
        assert sha(ROOT / path) == expected, path
    for path, expected in receipt['source_pins'].items():
        assert sha(ROOT / path) == expected, path
    for path, expected in receipt['artifact_pins'].items():
        assert sha(HERE / path) == expected, path
    before = (HERE / 'frozen-original/deploy/gcp/beta/enrollment/enroll.py').read_bytes()
    assert before.replace(b'parser = Parser(description=__doc__)\n',
        b'parser = Parser(description=__doc__, allow_abbrev=False)\n') == (
        ROOT / 'deploy/gcp/beta/enrollment/enroll.py').read_bytes()
    result = json.loads((HERE / 'checks.json').read_text())
    assert result['passed'] == 6 and not result['actual_network_db_or_proxy_calls']
    print(json.dumps({'state': 'verified_local_parser_amendment', 'new_checks': 6,
        'prior41_receipt_preserved': True, 'actual_identity_or_enrollment_claimed': False}, sort_keys=True))


if __name__ == '__main__':
    main()
