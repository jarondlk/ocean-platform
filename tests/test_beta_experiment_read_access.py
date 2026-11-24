from copy import deepcopy

import pytest

from deploy.gcp.beta.b3.experiment_read_access import RESULTS_BUCKET, storage_grant_plan


@pytest.fixture
def inputs():
    bucket = {'name': RESULTS_BUCKET, 'projectNumber': '534831104543', 'location': 'ASIA-NORTHEAST1',
        'iamConfiguration': {'uniformBucketLevelAccess': {'enabled': True}, 'publicAccessPrevention': 'enforced'}}
    policy = {'version': 1, 'etag': 'current-provider-etag', 'bindings': [
        {'role': 'roles/storage.admin', 'members': ['group:fixture@example.invalid']}]}
    return bucket, policy


def test_storage_plan_preserves_existing_policy_and_adds_only_exact_object_permissions(inputs):
    bucket, policy = inputs
    before = deepcopy(policy)
    proposal = storage_grant_plan(bucket, policy)
    rendered = proposal['proposed_policy']
    assert policy == before
    assert rendered['version'] == 3 and rendered['etag'] == before['etag']
    assert rendered['bindings'][:1] == before['bindings']
    first, second = rendered['bindings'][1:]
    assert 'ocean-v1-beta-serving@' in first['members'][0]
    assert 'ocean-v1-beta-supervisor@' in second['members'][0]
    assert proposal['role_permissions'][first['role']] == ('storage.objects.get',)
    assert proposal['role_permissions'][second['role']] == ('storage.objects.create', 'storage.objects.get')
    assert first['condition'] == second['condition']
    assert first['condition']['expression'] == ("resource.type == 'storage.googleapis.com/Object' && "
        "resource.name.startsWith('projects/_/buckets/ocean-v1-beta-20261101-results/objects/c23/outputs-v1/')")
    assert storage_grant_plan(bucket, rendered) == proposal


@pytest.mark.parametrize('variant', ['project', 'public-access', 'etag', 'unscoped-existing', 'granted-elsewhere'])
def test_storage_plan_refuses_unexpected_live_boundaries(inputs, variant):
    bucket, policy = inputs
    exact = storage_grant_plan(bucket, policy)['proposed_policy']['bindings'][1]
    if variant == 'project':
        bucket['projectNumber'] = '123'
    elif variant == 'public-access':
        bucket['iamConfiguration']['publicAccessPrevention'] = 'inherited'
    elif variant == 'etag':
        del policy['etag']
    elif variant == 'unscoped-existing':
        policy['bindings'].append({**exact, 'condition': {'title': 'other', 'expression': 'true'}})
    else:
        policy['bindings'][0]['members'].extend(exact['members'])
    with pytest.raises(ValueError):
        storage_grant_plan(bucket, policy)
