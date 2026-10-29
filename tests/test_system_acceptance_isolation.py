"""Integrated local transfer/configuration observations; no cloud access."""
import hashlib
import json
import socket

from evaluation.system_acceptance_isolation import run_isolation_acceptance


def test_local_site_copy_withdrawal_and_isolation_compose_without_live_calls(tmp_path, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError('A local C26 fixture must not open a network connection')
    monkeypatch.setattr(socket, 'create_connection', forbidden)
    report = run_isolation_acceptance(tmp_path)
    assert report['fixture']['classification'] == 'synthetic-local-actual-services'
    assert report['fixture']['live_calls_performed'] is False
    statuses = {item['id']: item['status'] for item in report['checks']}
    assert statuses == {'transfer-independent': 'passed', 'transfer-rejections': 'passed',
        'transfer-withdrawal': 'passed', 'isolation-offline-contract': 'passed',
        'isolation-legacy-denial': 'passed', 'live-site-isolation': 'not_run'}
    assert report['fixture']['source_snapshot_id'] != report['fixture']['copy_snapshot_id']
    for item in report['checks']:
        payload = {key: value for key, value in item.items() if key != 'evidence'}
        encoded = json.dumps(payload, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()
        assert item['evidence']['sha256'] == hashlib.sha256(encoded).hexdigest()
    assert list((tmp_path / 'quarantine').iterdir()) == []
