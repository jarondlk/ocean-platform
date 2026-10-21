"""C22 exposure controls use explicit opt-in and exact authorized routes."""
import pytest

import config
from api.auth import ROLE_PERMISSIONS, route_permission
from api.rate_limit import policy_for_request


@pytest.mark.parametrize('name,helper', [
    ('ENABLE_V1_EXPERIMENTS', config.v1_experiments_enabled),
    ('ENABLE_V1_EXPERIMENT_DISPATCH', config.v1_experiment_dispatch_enabled),
])
def test_independent_opt_in_defaults_and_live_disable(monkeypatch, name, helper):
    monkeypatch.setattr(config, name, 'false')
    assert helper({}) is False
    assert helper({name: 'true'}) is True
    monkeypatch.setenv(name, 'true')
    assert helper() is True
    monkeypatch.setenv(name, 'false')
    assert helper() is False
    assert helper({name: ''}) is False
    for invalid in ('maybe', 'null', 'enabled', '2'):
        with pytest.raises(config.SecurityConfigurationError):
            helper({name: invalid})


@pytest.mark.parametrize('action,permission,scope', [
    *[(action, 'data:export', 'experiment_mutation') for action in ('create', 'revise', 'approve', 'dispatch', 'retry')],
    *[(action, 'chat:use', 'experiment_history') for action in ('get', 'status', 'events', 'list')],
])
def test_exact_action_permissions_and_shared_rate_buckets(action, permission, scope):
    path = '/research/experiments/' + action
    assert route_permission('POST', path) == permission
    for method in ('GET', 'PUT', 'PATCH', 'DELETE'):
        assert route_permission(method, path) is None
        assert policy_for_request(method, path) is None
    policy = policy_for_request('POST', path)
    assert policy.scope == scope and policy.limit == (10 if scope == 'experiment_mutation' else 120)
    assert policy.window_seconds == 60


@pytest.mark.parametrize('suffix', ['', '/', '/execute', '/publish', '/approve/other', '/dispatch.json', '/get/'])
def test_unknown_experiment_actions_never_inherit_a_permission_or_rate_policy(suffix):
    path = '/research/experiments' + suffix
    assert route_permission('POST', path) is None
    assert policy_for_request('POST', path) is None


def test_experiments_reuse_roles_without_expanding_existing_permission_epochs():
    assert 'data:read' not in ROLE_PERMISSIONS['viewer']
    assert all({'chat:use', 'data:read', 'data:export'} <= ROLE_PERMISSIONS[role] for role in ('researcher', 'admin'))
    assert not any(permission.startswith('experiments:') for values in ROLE_PERMISSIONS.values() for permission in values)
