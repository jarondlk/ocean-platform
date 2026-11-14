"""Repair planner preserves original config guards and rejects phase/drift errors."""

from copy import deepcopy

import pytest

from scripts import beta_b1_repair_rollout as repair
from scripts import beta_b1_rollout as original
from scripts.beta_b0_preflight import Rejected
from tests.test_beta_b1_rollout import completed, make_material


@pytest.fixture
def material():
    serving, controller, contract = make_material()
    for kind, service in [('serving', serving), ('controller', controller)]:
        original.main_container(service, kind)['image'] = original.NEW
    contract['image'] = original.NEW.split('@')[0] + '@sha256:' + 'c' * 64
    contract['initial_revisions'] = {kind: service['latestReadyRevision'].split('/')[-1]
                                     for kind, service in [('serving', serving), ('controller', controller)]}
    return serving, controller, contract


def test_all_repair_phases_preserve_full_configuration_and_use_narrow_masks(material):
    serving, controller, contract = material
    proposal = repair.plan(controller, 'controller', contract)
    after = completed(controller, proposal)
    assert repair.readback(controller, after, proposal, contract)['all_other_configuration_preserved']
    assert proposal['update_mask'] == 'template.containers,template.revision'
    for phase in ('stage', 'promote', 'admit-stage', 'admit-promote'):
        proposal = repair.plan(serving, phase, contract)
        after = completed(serving, proposal)
        assert repair.readback(serving, after, proposal, contract)['all_other_configuration_preserved']
        if phase in {'promote', 'admit-promote'}:
            assert proposal['update_mask'] == 'traffic' and 'template' not in proposal['body']
        assert original.main_container(after, 'serving')['image'] == contract['image']
        assert after['template']['containers'][0] == serving['template']['containers'][0]
        serving = after


@pytest.mark.parametrize('phase', ['promote', 'admit-stage', 'admit-promote'])
def test_phase_cannot_skip_predecessor(material, phase):
    serving, _, contract = material
    with pytest.raises(Rejected):
        repair.plan(serving, phase, contract)


@pytest.mark.parametrize('change', ['identity', 'secret', 'proxy', 'frontend', 'network', 'ingress', 'scaling', 'timeout', 'image', 'traffic', 'etag', 'ready'])
def test_unreviewed_drift_cannot_enter_repair_plan(material, change):
    serving, _, contract = material
    template = serving['template']
    if change == 'identity':
        template['serviceAccount'] = 'other@example.com'
    elif change == 'secret':
        original.main_container(serving, 'serving')['env'][-1]['valueSource']['secretKeyRef']['version'] = 'latest'
    elif change in {'proxy', 'frontend'}:
        next(c for c in template['containers'] if c['name'] == ('sql-proxy' if change == 'proxy' else 'frontend'))['image'] = 'unreviewed:latest'
    elif change == 'network':
        template['vpcAccess']['egress'] = 'ALL_TRAFFIC'
    elif change == 'ingress':
        serving['ingress'] = 'INGRESS_TRAFFIC_ALL'
    elif change == 'scaling':
        template['scaling']['maxInstanceCount'] = 100
    elif change == 'timeout':
        template['timeout'] = '120s'
    elif change == 'image':
        original.main_container(serving, 'serving')['image'] = 'unreviewed:latest'
    elif change == 'traffic':
        serving['traffic'] = []
    elif change == 'etag':
        serving['etag'] = ''
    else:
        serving['latestReadyRevision'] += 'unreviewed'
    with pytest.raises(Rejected):
        repair.plan(serving, 'stage', contract)


def test_idle_staged_import_does_not_claim_runtime_startup(material):
    serving, _, contract = material
    proposal = repair.plan(serving, 'stage', contract)
    after = completed(serving, proposal)
    after['latestReadyRevision'] = serving['latestReadyRevision']
    staged = {**deepcopy(after['template']), 'name': after['latestCreatedRevision'],
              'service': after['name'].split('/')[-1], 'uid': 'fixed-revision', 'generation': '1', 'observedGeneration': '1',
              'conditions': [{'type': 'Ready', 'state': 'CONDITION_SUCCEEDED', 'revisionReason': 'RETIRED'},
                             {'type': 'ContainerReady', 'state': 'CONDITION_SUCCEEDED'}]}
    assert repair.readback(serving, after, proposal, contract, staged)['runtime_startup_verified'] is False
    with pytest.raises(Rejected):
        repair.readback(serving, after, proposal, contract)


def test_readback_rejects_concurrent_change_or_wrong_revision(material):
    serving, _, contract = material
    proposal = repair.plan(serving, 'stage', contract)
    after = completed(serving, proposal)
    after['template']['timeout'] = '120s'
    with pytest.raises(Rejected):
        repair.readback(serving, after, proposal, contract)
