"""Read-only verification of the preserved C27 native migration observations."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

DIRECTORY = Path(__file__).resolve().parent
ROOT = DIRECTORY.parents[5]


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def read(path):
    return json.loads(path.read_text())


def verify():
    summary = read(DIRECTORY/'receipt.json')
    for name, expected in summary['artifact_sha256'].items():
        path = (DIRECTORY/name).resolve()
        assert path.is_relative_to(DIRECTORY)
        assert sha(path.read_bytes()) == expected, name
    run = DIRECTORY/'run02'
    receipt = read(run/'receipt.json')
    assert receipt['status'] == 'passed' and len(receipt['checks']) == 20
    assert all(row['status']=='passed' and row['observed']==row['expected'] for row in receipt['checks'])
    for name, expected in receipt['artifact_sha256'].items():
        assert sha((run/name).read_bytes()) == expected, name
    for name, expected in receipt['source_sha256'].items():
        assert sha((ROOT/name).read_bytes()) == expected, name
    assert receipt['cleanup']['cluster_stopped'] and receipt['cleanup']['temporary_files_removed']
    assert not Path(receipt['cleanup']['temporary_directory']).exists()
    commands = {row['label']:row for row in receipt['commands']}
    assert commands['pg-stop']['returncode'] == 0
    assert commands['pg-stopped-status']['returncode'] == 3
    for label in ('controlled-duplicate-table-upgrade-failure','populated-downgrade-refused',
            'offline-base-to-head-unsupported'):
        assert commands[label]['returncode'] != 0 and commands[label]['expected'] != 0
    for label in ('fresh-upgrade-head','baseline-upgrade-0016','retry-upgrade-0017',
            'retry-upgrade-head','offline-database-baseline-0013','apply-offline-sql',
            'repeat-head-with-history','offline-0013-to-head','offline-0016-to-head'):
        assert commands[label]['returncode'] == 0
    assert 'already exists' in (run/'controlled-duplicate-table-upgrade-failure.stderr').read_text()
    assert 'conservative retention' in (run/'populated-downgrade-refused.stderr').read_text()
    assert 'NoInspectionAvailable' in (run/'offline-base-to-head-unsupported.stderr').read_text()
    before, failed = [read(run/(name+'.json')) for name in
        ('before-controlled-failure','after-controlled-failure')]
    assert before == failed and before['revision']=='20261005_0016'
    before, repeat, retained = [read(run/(name+'.json')) for name in
        ('populated-current-history','reapplied-current-history','after-refused-downgrade')]
    assert before == repeat == retained and retained['revision']=='20261027_0021'
    fresh, upgraded, offline = [read(run/(name+'.json')) for name in
        ('fresh-head','upgraded-head','offline-applied-head')]
    assert fresh['schema_sha256']==upgraded['schema_sha256']==offline['schema_sha256']==receipt['schema_sha256']
    baseline = read(run/'baseline-seeded-0016.json')
    assert baseline['rows']['chat_interaction']==upgraded['rows']['chat_interaction']
    context = read(run/'seeded-context-0017.json')
    for table in ('research_investigation','research_context_revision','research_conversation'):
        assert context['rows'][table]==upgraded['rows'][table]
    a, b = [(run/(name+'.sql')).read_bytes() for name in
        ('offline-0013-to-head','offline-0016-to-head')]
    marker = b'-- Running upgrade 20261005_0016 -> 20261018_0017'
    assert a.count(marker)==b.count(marker)==1
    assert a[a.index(marker):]==b[b.index(marker):]
    assert sha(b[b.index(marker):])==summary['offline_0016_applied_subset_sha256']
    original = read(DIRECTORY/'run01/receipt.json')
    assert original['status']=='failed' and original['cleanup']['temporary_files_removed']
    assert not receipt['production_backup_tested'] and not receipt['live_runtime_tested']
    assert not receipt['prior_binary_compatibility_tested'] and not receipt['scientific_execution_performed']
    return {'verified':True,'checks':20,'head_revision':receipt['head_revision'],
        'schema_sha256':receipt['schema_sha256'],'schema_summary':receipt['schema_summary'],
        'owned_cluster_stopped_removed':True,'historical_full_base_offline':'unsupported',
        'release_accepted':False}


if __name__=='__main__':
    print(json.dumps(verify(),indent=2))
