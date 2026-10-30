"""Verify immutable local C26 owner receipts; optionally compare current source."""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import xml.etree.ElementTree as ET


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--verify-current', action='store_true')
    args = parser.parse_args()
    directory = Path(__file__).resolve().parent
    root = directory.parents[5]
    receipt = json.loads((directory / 'receipt.json').read_text())
    for name, item in receipt['artifacts'].items():
        packed = (directory / item['path']).read_bytes()
        assert sha(packed) == item['gzip_sha256'], name
        raw = gzip.decompress(packed)
        assert len(raw) == item['raw_bytes'] and sha(raw) == item['raw_sha256'], name
        if 'junit' in item:
            cases = list(ET.fromstring(raw).iter('testcase'))
            observed = {'cases': len(cases),
                'failures': sum(case.find('failure') is not None for case in cases),
                'errors': sum(case.find('error') is not None for case in cases),
                'skipped': sum(case.find('skipped') is not None for case in cases)}
            assert observed == item['junit'], name
    for name, expected in receipt['owned_source_files'].items():
        assert sha((directory / 'source' / name).read_bytes()) == expected, name
    if args.verify_current:
        for name, expected in receipt['selected_source_files'].items():
            assert sha((root / name).read_bytes()) == expected, name
        for name, expected in receipt['owned_source_files'].items():
            assert sha((root / name).read_bytes()) == expected, name
    for name, count in [('ocean-c26-retention-combined-final-20261030.xml', 15),
            ('ocean-c26-answer-event-race-positive-20261030.xml', 21),
            ('ocean-c26-retention-native-final-20261030.xml', 2)]:
        assert receipt['artifacts'][name]['junit'] == {'cases': count, 'failures': 0, 'errors': 0, 'skipped': 0}, name
    assert receipt['native_identity_after']['fixture_schemas'] == 0
    assert receipt['native_identity_after']['ephemeral_roles'] == 0
    assert receipt['native_cleanup'] == {'tcp_refused': True, 'pidfile_absent': True, 'pg_ctl_status_exit': 3}
    assert receipt['performance']['after_response_equal'] is True
    print(json.dumps({'verified': True, 'artifacts': len(receipt['artifacts']),
        'source_revision': receipt['source_revision'], 'current_source_checked': args.verify_current}))


if __name__ == '__main__':
    main()
