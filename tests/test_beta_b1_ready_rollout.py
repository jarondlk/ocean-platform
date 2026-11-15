"""Exact83ce predecessor, preserved full rollout fences and closed-model budget."""
from copy import deepcopy
from datetime import datetime, timezone

import pytest

from scripts import beta_b1_repair_rollout as repair
from scripts import beta_b1_rollout as original
from scripts.beta_b0_preflight import Rejected
from tests.test_beta_b1_list_rollout import listed as listed
from tests.test_beta_b1_repair_rollout import material as material
from tests.test_beta_b1_rollout import completed


@pytest.fixture
def ready(listed):
    serving, controller, contract = deepcopy(listed)
    contract.update(version=repair.READY_VERSION, initial_image=repair.READY_PREVIOUS)
    for kind, service in [('serving', serving), ('controller', controller)]:
        original.main_container(service, kind)['image'] = repair.READY_PREVIOUS
    return serving, controller, contract


def test_ready_rollout_preserves_every_phase_guard_and_configuration(ready):
    serving, controller, contract = ready
    drain = repair.plan(serving, 'drain', contract)
    after = completed(serving, drain)
    assert repair.readback(serving, after, drain, contract)['image'] == repair.READY_PREVIOUS
    assert not original.flag_state(after)
    serving = after
    proposal = repair.plan(controller, 'controller', contract)
    assert repair.readback(controller, completed(controller, proposal), proposal, contract)['all_other_configuration_preserved']
    for phase in ('stage', 'promote', 'admit-stage', 'admit-promote'):
        proposal = repair.plan(serving, phase, contract)
        after = completed(serving, proposal)
        assert repair.readback(serving, after, proposal, contract)['all_other_configuration_preserved']
        assert after['template']['containers'][0] == serving['template']['containers'][0]
        if phase in {'promote', 'admit-promote'}:
            assert proposal['update_mask'] == 'traffic' and 'template' not in proposal['body']
        serving = after


@pytest.mark.parametrize('change', ['old_image', 'foreign_image', 'old_contract', 'old_predecessor', 'identity', 'network', 'secret'])
def test_ready_rollout_rejects_stale_predecessor_and_unreviewed_changes(ready, change):
    serving, _, contract = ready
    if change in {'old_image', 'foreign_image'}:
        original.main_container(serving, 'serving')['image'] = repair.PREVIOUS if change == 'old_image' else 'foreign:latest'
    elif change == 'old_contract':
        contract['version'] = repair.LIST_VERSION
    elif change == 'old_predecessor':
        contract['initial_image'] = repair.PREVIOUS
    elif change == 'identity':
        serving['template']['serviceAccount'] = 'foreign@example.com'
    elif change == 'network':
        serving['template']['vpcAccess']['egress'] = 'ALL_TRAFFIC'
    else:
        next(e for e in original.main_container(serving, 'serving')['env'] if 'valueSource' in e)['valueSource']['secretKeyRef']['version'] = 'latest'
    with pytest.raises(Rejected):
        repair.plan(serving, 'drain', contract)


@pytest.fixture
def reservation():
    return {'version': 'ocean-beta-b1-q6-terminal-reconciliation-v1',
        'terminal_run_id': 'f7e35a7a-4196-4431-9f3f-d5edbca66bc8',
        'terminal_answer_job_id': '3d707667-ef41-4b6a-b790-a77a9c91ae9c',
        'native_model_calls': '8', 'terminal_status': 'completed', 'total_planned_jpy': '550',
        'one_question_model_reserve_jpy': '0', 'automatic_continuation_admitted': False,
        'new_paid_question_admitted': False, 'captured_utc': datetime.now(timezone.utc).isoformat()}


def test_closed_q6_budget_funds_read_repair_without_admitting_a_model(reservation):
    repair.verify_read_reservation(reservation, {'budget_authorization_receipt': 'question06-budget-authorization03.json'}, ready=True)


@pytest.mark.parametrize('key,value', [('version', 'ocean-beta-b1-q6-pending-reconciliation-v1'),
    ('native_model_calls', '7'), ('native_model_calls', '9'), ('terminal_status', 'running'),
    ('terminal_answer_job_id', 'other'), ('one_question_model_reserve_jpy', '300'),
    ('automatic_continuation_admitted', True), ('new_paid_question_admitted', True),
    ('total_planned_jpy', '1000.01'), ('captured_utc', '2026-01-01T00:00:00Z')])
def test_read_repair_refuses_stale_or_new_model_admission(reservation, key, value):
    reservation[key] = value
    with pytest.raises(Rejected):
        repair.verify_read_reservation(reservation, {'budget_authorization_receipt': 'question06-budget-authorization03.json'}, ready=True)
