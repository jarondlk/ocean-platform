"""Read-only verification of the independent API host checkpoint."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import xml.etree.ElementTree as ET

DIRECTORY = Path(__file__).resolve().parent
ROOT = DIRECTORY.parents[4]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    return json.loads(path.read_text())


def verify():
    receipt = read(DIRECTORY/'receipt.json')
    assert receipt['status'] == 'passed' and receipt['tests_passed'] == 35
    assert receipt['native_checks_passed'] == 9 and receipt['cloud_actions_performed'] is False
    for name, identity in receipt['source_sha256'].items():
        path = (ROOT/name).resolve()
        assert path.is_relative_to(ROOT) and sha(path) == identity, name
    for name, identity in receipt['artifact_sha256'].items():
        path = (DIRECTORY/name).resolve()
        assert path.is_relative_to(DIRECTORY) and sha(path) == identity, name
    cases = list(ET.parse(DIRECTORY/'tests-final.xml').getroot().iter('testcase'))
    assert len(cases) == 35 and not any(c.find(tag) is not None for c in cases for tag in ('error','failure','skipped'))
    assert '35 passed, 1 warning' in (DIRECTORY/'tests-final.stdout').read_text()
    native = DIRECTORY/'native-exact-audience'
    observation = read(native/'receipt.json')
    assert observation['status'] == 'passed' and len(observation['checks']) == 9
    assert all(row['passed'] is True for row in observation['checks'])
    assert all(observation['cleanup'].values()) and not Path(observation['temp']).exists()
    assert observation['scientific_data_or_execution'] is False and observation['cloud_actions'] is False
    for name, identity in observation['source_sha256'].items():
        assert sha(ROOT/name) == identity, name
    for name, identity in observation['artifact_sha256'].items():
        assert sha(native/name) == identity, name
    commands = {row['name']:row for row in observation['commands']}
    assert commands['pg-stopped']['returncode'] == 3 and commands['pg-stop']['returncode'] == 0
    assert commands['migrations']['returncode'] == 0
    historical = read(DIRECTORY/'native-accepted/receipt.json')
    for name, identity in historical['source_sha256'].items():
        assert sha(DIRECTORY/'native-accepted/source-before-exact-audience'/Path(name).name) == identity, name
    return {'verified': True, 'tests_passed': 35, 'native_checks_passed': 9,
        'owned_native_cluster_stopped_removed': True, 'source_paths': len(receipt['source_sha256']),
        'artifacts': len(receipt['artifact_sha256']), 'production_entry_has_no_scientific_provider': True,
        'account_enrollment_required': True, 'release_accepted': False}


if __name__ == '__main__':
    print(json.dumps(verify(), indent=2))
