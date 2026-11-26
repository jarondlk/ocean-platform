from contextlib import nullcontext
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys
from unittest.mock import MagicMock

import pytest

from deploy.gcp.beta.b4 import outbox_health as health
from scripts import beta_b4_outbox_trial as trial
from tests.test_beta_b0_preflight import material as material


@pytest.mark.parametrize('rows, state', [
    ([(2, 0, 0, 0, 0), (1, 0, 0, 0, 0)], 'clear'),
    ([(4, 1, 1, 1, 1), (2, 0, 1, 0, 0)], 'review_required'),
])
def test_aggregate_projection_uses_current_outboxes_in_one_transaction(rows, state):
    conn = MagicMock()
    cursor = conn.cursor.return_value
    conn.cursor.return_value = nullcontext(cursor)
    cursor.fetchone.return_value = ('ocean_v1_research_controller', 'ocean_v1_beta', 'on', 'repeatable read')
    cursor.fetchall.side_effect = [[row] for row in rows]
    assert health.collect(conn) == {
        'state': state, 'transaction_read_only_verified': True,
        'counts': {kind: dict(zip(health.FIELDS, row, strict=True)) for kind, row in zip(health.TABLES, rows, strict=True)},
    }
    queries = cursor.execute.call_args_list
    assert len(queries) == 3 and conn.__enter__.call_count == 1
    assert 'o.input_version = h.input_version' in queries[1].args[0]
    for call in queries[1:]:
        assert call.args[1] == (600, 3900) and 'CURRENT_TIMESTAMP' in call.args[0]


def test_writable_connection_is_denied_before_research_reads():
    conn = MagicMock()
    cursor = conn.cursor.return_value
    conn.cursor.return_value = nullcontext(cursor)
    cursor.fetchone.return_value = ('ocean_v1_research_controller', 'ocean_v1_beta', 'off', 'repeatable read')
    with pytest.raises(ValueError, match='observer identity'):
        health.collect(conn)
    assert cursor.execute.call_count == 1


def test_failure_log_discards_details_and_counts_after_proxy_failure(monkeypatch, capsys):
    import psycopg2

    def unexpected():
        raise ValueError('private failure details')

    monkeypatch.setattr(health.sys, 'argv', ['outbox_health.py'])
    monkeypatch.setattr(health.observer, 'configuration', lambda _: {})
    monkeypatch.setattr(psycopg2, 'connect', lambda **_: MagicMock())
    monkeypatch.setattr(health, 'collect', lambda _: {'state': 'clear', 'counts': {'private values': 'discard'}})
    monkeypatch.setattr(health, 'stop_proxy', unexpected)
    assert health.main() == 2
    raw = capsys.readouterr().out
    assert json.loads(raw)['state'] == 'read_failed'
    assert '"counts"' not in raw and 'private' not in raw


def test_embedded_observer_arguments_reject_drift_and_never_run_binding_main():
    binding = "marker = 'verified'\nif __name__ == '__main__': raise ValueError('old main')"
    source = 'from scripts import beta_b1_diagnostic as base\nprint(base.marker)'
    bootstrap, payload = trial.arguments(binding, source)
    result = subprocess.run([sys.executable, '-c', bootstrap, payload], capture_output=True, text=True, check=True)
    assert result.stdout.strip() == 'verified'
    refused = subprocess.run([sys.executable, '-c', bootstrap, payload + ' '], capture_output=True, text=True)
    assert refused.returncode == 2 and json.loads(refused.stdout)['state'] == 'outbox_observer_source_rejected'


def test_policy_matches_only_counts_from_the_fixed_beta_observer():
    path = Path(health.__file__).with_name('outbox-health-alert.json')
    policy = json.loads(path.read_bytes())
    assert policy['enabled'] is False
    where = policy['conditions'][0]['conditionMatchedLog']['filter']
    for term in (health.VERSION, health.observer.PROJECT, 'ocean-v1-beta-provider-preflight-20261111',
                 'asia-northeast1', 'review_required', 'read_failed'):
        assert f'"{term}"' in where
    assert '"clear"' not in where


def test_override_execution_keeps_pinned_job_identity_proxy_and_limits(material):
    contract, _, execution, _ = material
    source = trial.arguments('shared = True', 'print("counts")')
    request = {'overrides': {'containerOverrides': [{'name': 'diagnostics', 'args': source}]}}
    task = execution['spec']['template']['spec']
    task['containers'][0]['args'] = source
    proof = {'name': execution['metadata']['name'],
             'not_before': datetime(2026, 11, 14, 7, 29, tzinfo=timezone.utc),
             'now': datetime(2026, 11, 14, 7, 30, tzinfo=timezone.utc),
             'index_raw': (trial.guard.PROOF / 'proxy-index.json').read_bytes(),
             'child_raw': (trial.guard.PROOF / 'proxy-linux-amd64.json').read_bytes()}
    assert trial.verify_execution(execution, contract, request, **proof)['proxy_proof']['platform'] == 'linux/amd64'
    task['timeoutSeconds'] = '121'
    with pytest.raises(trial.guard.Rejected):
        trial.verify_execution(execution, contract, request, **proof)


@pytest.mark.parametrize('change', ['healthy', 'extra_field', 'bool_count', 'false_clear'])
def test_hosted_report_is_counts_only_and_consistent(change):
    proof = {'start_utc': '2026-11-26T07:00:00Z', 'completion_utc': '2026-11-26T07:00:10Z'}
    report = {'version': health.VERSION, 'project': health.observer.PROJECT, 'state': 'clear',
              'counts': {kind: dict.fromkeys(health.FIELDS, 0) for kind in health.TABLES},
              'pending_threshold_seconds': 600, 'sent_threshold_seconds': 3900,
              'counts_only': True, 'transaction_read_only_verified': True, 'proxy_shutdown_verified': True,
              'captured_utc': '2026-11-26T07:00:05Z'}
    if change == 'extra_field':
        report['details'] = 'Unexpected raw fields'
    if change == 'bool_count':
        report['counts']['answers']['active'] = False
    if change == 'false_clear':
        report['counts']['answers'].update(active=1, aged_sent=1)
    now = datetime(2026, 11, 26, 7, 0, 20, tzinfo=timezone.utc)
    if change == 'healthy':
        assert trial.verify_report(report, proof, now=now) == report
    else:
        with pytest.raises(trial.guard.Rejected):
            trial.verify_report(report, proof, now=now)
