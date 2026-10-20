"""C21 reference protection cannot revoke authentic historical research."""
import copy
import uuid

import pytest

from orchestration.catalogue_service import FrozenCatalogueResolver
from orchestration.research_runs import ResearchRunError
from tests import test_research_runs as run_fixtures

actual = run_fixtures.actual
retained = run_fixtures.retained


def test_additive_reference_keeps_access_and_old_raw_revision_hash_reopens_history(actual):
    run = actual.submit()
    actual.service.execute_delivery(**actual.delivery(run))
    resolver = actual.retained.service.catalogue.resolver
    snapshot = run['context']['binding']['snapshot_id']
    before = resolver.resolve(actual.user, snapshot).revision
    raw_before = resolver.store.lifecycle()['revision']
    policy = resolver.policy_resolver(actual.user, snapshot)
    old_raw_hash = resolver._revision(policy.revision, raw_before)
    resolver.store.add_reference(snapshot, 'c21:regression:' + str(uuid.uuid4()))
    assert resolver.resolve(actual.user, snapshot).revision == before
    assert resolver.revision_compatible(actual.user, snapshot, old_raw_hash)
    reopened = actual.service.invoke('status', actual.address(run), actual.user)
    assert reopened['run']['status'] == 'completed'


def test_current_policy_or_non_additive_control_change_cannot_reuse_old_epoch(actual):
    run = actual.submit()
    actual.service.execute_delivery(**actual.delivery(run))
    resolver = actual.retained.service.catalogue.resolver
    snapshot = run['context']['binding']['snapshot_id']
    old = resolver.resolve(actual.user, snapshot).revision
    reference = 'c21:remove:' + str(uuid.uuid4())
    resolver.store.add_reference(snapshot, reference)
    resolver.store.remove_reference(snapshot, reference)
    assert resolver.resolve(actual.user, snapshot).revision != old
    assert not resolver.revision_compatible(actual.user, snapshot, old)
    with pytest.raises(ResearchRunError, match='denied'):
        actual.service.invoke('status', actual.address(run), actual.user)


@pytest.mark.parametrize('action', ['seal', 'promote', 'unreference', 'hold', 'revoke', 'retire'])
def test_every_non_reference_lifecycle_action_advances_epoch(action):
    state = {'revision': 2, 'audits': [{'revision': 1, 'action': action},
             {'revision': 2, 'action': 'reference', 'reference': 'r', 'snapshot_id': 's'}],
             'references': {'r': 's'}}
    assert FrozenCatalogueResolver._access_epoch(state) == 1


@pytest.mark.parametrize('corruption', ['gap', 'missing', 'boolean', 'action', 'map', 'empty_reference', 'missing_binding'])
def test_incomplete_or_forged_audit_tail_cannot_attest_historical_access(corruption):
    state = {'revision': 1, 'audits': [{'revision': 1, 'action': 'reference', 'reference': 'r', 'snapshot_id': 's'}],
             'references': {'r': 's'}}
    value = copy.deepcopy(state)
    if corruption == 'gap':
        value['audits'][0]['revision'] = 2
    elif corruption == 'missing':
        value['audits'] = []
    elif corruption == 'boolean':
        value['audits'][0]['revision'] = True
    elif corruption == 'action':
        value['audits'][0]['action'] = 'unknown'
    elif corruption == 'empty_reference':
        value['audits'][0]['reference'] = ''
        value['references'] = {'': 's'}
    elif corruption == 'missing_binding':
        value['audits'][0] = {'revision': 1, 'action': 'reference'}
        value['references'] = {}
    else:
        value['references'] = {}
    with pytest.raises(ValueError):
        FrozenCatalogueResolver._access_epoch(value)
