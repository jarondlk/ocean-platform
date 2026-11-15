"""The list-read candidate extends the fixed writer without widening its scope."""
from copy import deepcopy
import json

import pytest

from scripts import beta_b1_repair_rollout as repair
from scripts import beta_b1_rollout as original
from scripts.beta_b0_preflight import Rejected
from tests.test_beta_b1_repair_rollout import material as material
from tests.test_beta_b1_rollout import completed


@pytest.fixture
def listed(material):
    serving, controller, contract = deepcopy(material)
    contract.update(version=repair.LIST_VERSION, initial_image=repair.PREVIOUS,
        initial_admitted_revision=serving['latestReadyRevision'].split('/')[-1])
    contract['initial_revisions']['serving'] = 'ocean-v1-beta-serving-list-drain-test'
    for kind, service in [('serving', serving), ('controller', controller)]:
        original.main_container(service, kind)['image'] = repair.PREVIOUS
    for item in original.main_container(serving, 'serving')['env']:
        if item['name'] in original.FLAGS:
            item['value'] = 'true'
    serving['traffic'] = original.fixed_traffic(contract['initial_admitted_revision'])
    return serving, controller, contract


def test_exact_list_candidate_drains_then_preserves_all_existing_phase_guards(listed):
    serving, controller, contract = listed
    drained = repair.plan(serving, 'drain', contract)
    after = completed(serving, drained)
    assert repair.readback(serving, after, drained, contract)['image'] == repair.PREVIOUS
    assert not original.flag_state(after)
    assert original.main_container(after, 'serving')['image'] == repair.PREVIOUS
    assert drained['update_mask'] == 'template.containers,template.revision,traffic'
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


@pytest.mark.parametrize('change', ['image', 'initial_image', 'contract', 'flags', 'traffic', 'revision',
                                   'identity', 'secret', 'sidecar', 'network', 'timeout'])
def test_list_drain_rejects_wrong_predecessor_or_unreviewed_configuration(listed, change):
    serving, _, contract = listed
    main = original.main_container(serving, 'serving')
    if change == 'image':
        main['image'] = original.NEW
    elif change == 'initial_image':
        contract['initial_image'] = original.NEW
    elif change == 'contract':
        contract['version'] = 'other'
    elif change == 'flags':
        next(e for e in main['env'] if e['name'] in original.FLAGS)['value'] = 'false'
    elif change == 'traffic':
        serving['traffic'] = [{'type': 'TRAFFIC_TARGET_ALLOCATION_TYPE_LATEST', 'percent': 100}]
    elif change == 'revision':
        serving['latestReadyRevision'] += '-other'
    elif change == 'identity':
        serving['template']['serviceAccount'] = 'other@example.com'
    elif change == 'secret':
        next(e for e in main['env'] if 'valueSource' in e)['valueSource']['secretKeyRef']['version'] = 'latest'
    elif change == 'sidecar':
        serving['template']['containers'][0]['image'] = 'unreviewed:latest'
    elif change == 'network':
        serving['template']['vpcAccess']['egress'] = 'ALL_TRAFFIC'
    else:
        serving['template']['timeout'] = '120s'
    with pytest.raises(Rejected):
        repair.plan(serving, 'drain', contract)


def test_list_writer_cannot_skip_drain_or_rewrite_old_contract(material, listed):
    original_serving, _, old = material
    with pytest.raises(Rejected):
        repair.plan(original_serving, 'drain', old)
    serving, _, contract = listed
    before = deepcopy(serving)
    with pytest.raises(Rejected):
        repair.plan(serving, 'stage', contract)
    assert serving == before


@pytest.mark.parametrize('amount', [700, 1000])
def test_allowance_requires_its_exact_source_bound_authorization(monkeypatch, tmp_path, amount):
    monkeypatch.setattr(repair, 'PROOF', tmp_path)
    name = 'question06-budget-authorization0' + ('2' if amount == 700 else '3') + '.json'
    value = {'approved_initial_validation_allowance_jpy': amount, 'monthly_beta_target_jpy': 50000,
        'authorization_basis': 'standing_approval_for_this_and_future_requests', 'new_question_admitted': False}
    (tmp_path / name).write_text(json.dumps(value))
    assert repair.approved_allowance({'budget_authorization_receipt': name}) == amount
    value['approved_initial_validation_allowance_jpy'] = amount + 1
    (tmp_path / name).write_text(json.dumps(value))
    with pytest.raises(Rejected):
        repair.approved_allowance({'budget_authorization_receipt': name})


@pytest.mark.parametrize('name', ['../authorization.json', 'unrecognized.json', 1000])
def test_allowance_rejects_unreviewed_authority_paths(name):
    with pytest.raises(Rejected):
        repair.approved_allowance({'budget_authorization_receipt': name})
