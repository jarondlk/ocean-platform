"""A new index must not strand retained evidence from unchanged B1 sources."""
import hashlib

import pytest

from api.v1_catalogue_host import _canonical, load_snapshot_catalogue
from deploy.gcp.beta.data.append_catalogue import append_groups
from ingestion.artifact_store import BoundedLocalStore
from ingestion.catalogue_snapshot import LocalCatalogueSnapshotStore
from ingestion.edna_catalogue_inputs import dataset_exports
from orchestration.catalogue_service import CatalogueServiceError, FrozenCatalogueResolver
from schema.edna_catalogue_fixtures import edna_fixture
from schema.catalogue_adapter_fixtures import adapter_scope
from tests.catalogue_service_support import fixture_user
from tests.test_beta_research_edna_preparation import selected as selected
from tests.test_beta_snapshot_catalogue import sealed as sealed


def host(root, activation, tmp_path, label):
    digest = hashlib.sha256(_canonical(activation)).hexdigest()
    key = 'v1/catalogue/activations/' + digest + '.json'
    path = root / key
    if not path.exists():
        path.write_bytes(_canonical(activation))
    binding = {'version': 'ocean-v1-gcs-catalogue-host-v1', 'project_id': activation['project_id'],
        'site_id': activation['site_id'], 'bucket': activation['project_id'] + '-snapshots',
        'prefix': 'v1/catalogue', 'activation_object': key, 'activation_sha256': digest}
    config = tmp_path / (label + '-binding.json')
    config.write_bytes(_canonical(binding))
    config.chmod(0o444)
    return load_snapshot_catalogue(config, project_id=activation['project_id'], site_id=activation['site_id'],
        cursor_key=b'synthetic-b2-retained-revision-' * 2, context_retention=True,
        research_retention=True, _allow_test_owner=True, _test_store=BoundedLocalStore(root))[0]


@pytest.fixture
def appended(selected, tmp_path):
    root, _, _, old = selected
    actor = fixture_user(role='admin')
    before = host(root, old, tmp_path, 'before')
    index = old['snapshots'][0]['descriptor']['snapshot_id']
    revision = before.resolver.resolve(actor, index).revision
    before._b2_cursor_request = {'snapshot_id': index,
        'scope': adapter_scope('ctd').model_dump(mode='json'), 'limit': 1}
    before._b2_cursor = before.list(before._b2_cursor_request, actor)['next_cursor']
    assert before._b2_cursor is not None
    store = LocalCatalogueSnapshotStore(root=root, access_gate=lambda _: True)
    dataset, frames = edna_fixture(3)
    new, _ = append_groups(store=store, activation=old, groups=[{
        'label': {'en': 'Synthetic new eDNA', 'ja': '合成の新規eDNA'},
        'qualifications': ['Synthetic only; no scientific approval'],
        'datasets': [(dataset, frames, dataset_exports(dataset, frames, generation='synthetic-b2-new'))]}],
        authorization_ref='synthetic-b2-only', research_enabled=True)
    after = host(root, new, tmp_path, 'after')
    return root, old, new, before, after, index, actor, revision, store


def test_old_and_new_activation_can_prove_retained_revision_after_unrelated_append(appended):
    _, old, new, before, after, index, actor, expected, _ = appended
    assert new['policy_revision'] == old['policy_revision']
    assert after.resolver.resolve(actor, index).revision != expected
    assert before.resolver.revision_compatible(actor, index, expected)
    assert after.resolver.revision_compatible(actor, index, expected)


def test_policy_change_is_never_treated_as_a_compatible_append(appended, tmp_path):
    root, _, new, _, _, index, actor, expected, _ = appended
    altered = dict(new, policy_revision='synthetic:changed-current-policy')
    changed = host(root, altered, tmp_path, 'changed-policy')
    assert not changed.resolver.revision_compatible(actor, index, expected)


@pytest.mark.parametrize('action', ['revoke', 'unreference', 'hold', 'promote'])
def test_current_denial_and_nonadditive_epochs_are_never_skipped(appended, action):
    _, old, _, _, after, index, actor, expected, store = appended
    child = old['snapshots'][0]['registration']['child_snapshot_ids'][0]
    if action == 'revoke':
        store.revoke(child)
    elif action == 'unreference':
        reference = next(pair[0] for pair in old['snapshots'][0]['registration']['references'] if pair[1] == child)
        store.remove_reference(child, reference)
    elif action == 'hold':
        store.set_hold(child, True)
    else:
        store.promote(child, expected_generation=0)
    if action in {'revoke', 'unreference'}:
        with pytest.raises((CatalogueServiceError, PermissionError)):
            after.resolver.revision_compatible(actor, index, expected)
    else:
        assert not after.resolver.revision_compatible(actor, index, expected)


def test_fallback_replays_whole_control_before_ignoring_an_unrelated_seal(appended):
    _, _, _, _, _, index, _, _, store = appended
    lifecycle = store.lifecycle()
    lifecycle['audits'][-1]['snapshot_id'] = 'f' * 64
    with pytest.raises(ValueError, match='lifecycle|audit'):
        FrozenCatalogueResolver._access_epoch(lifecycle, protected_snapshots={index})


def test_retained_evidence_compatibility_does_not_accept_an_old_cursor(appended):
    # The current-revision algorithm remains global; only the retained evidence
    # proof may accept an old hash through an unchanged exact dependency graph.
    _, _, _, before, after, index, actor, expected, _ = appended
    current = after.resolver.resolve(actor, index).revision
    assert current != expected
    assert after.resolver.revision_compatible(actor, index, expected)
    assert after.resolver.resolve(actor, index).revision == current
    with pytest.raises(CatalogueServiceError) as failure:
        after.list({**before._b2_cursor_request, 'cursor': before._b2_cursor}, actor)
    assert failure.value.code == 'invalid_cursor'


def test_original_disabled_mode_still_versions_its_policy_for_legacy_operators(selected):
    root, _, _, old = selected
    old = dict(old, research_enabled=False)
    dataset, frames = edna_fixture(3)
    new, _ = append_groups(store=LocalCatalogueSnapshotStore(root=root, access_gate=lambda _: True),
        activation=old, groups=[{'label': {'en': 'Synthetic', 'ja': '合成'},
            'qualifications': ['Synthetic only'],
            'datasets': [(dataset, frames, dataset_exports(dataset, frames, generation='synthetic-b2-new'))]}],
        authorization_ref='synthetic-b2-only')
    assert new['policy_revision'] != old['policy_revision'] and new['research_enabled'] is False
