"""Warm semantic inputs never replace current hosted authority or data reads."""
import hashlib
import json

import pytest

from api.v1_catalogue_host import _canonical, load_snapshot_catalogue
from deploy.gcp.beta.data.append_catalogue import append_groups
from ingestion.artifact_store import BoundedLocalStore
from ingestion.edna_catalogue_inputs import dataset_exports
from orchestration.catalogue_service import CatalogueServiceError
from schema.edna_catalogue_fixtures import edna_fixture, edna_scope
from tests.catalogue_service_support import fixture_user
from tests.test_beta_snapshot_catalogue import sealed as sealed


@pytest.fixture
def cached(sealed):
    source, output, _, prepared = sealed
    store = prepared['store']
    store.access_gate = lambda _: True
    old = json.loads((output / 'activation.json').read_bytes())
    old['research_enabled'] = True
    metadata, tables = edna_fixture(3)
    captured = dataset_exports(metadata, tables, generation='synthetic:b2-cache-host')
    activation, _ = append_groups(store=store, activation=old, groups=[{
        'label': {'en': 'Synthetic eDNA', 'ja': '合成eDNA'},
        'qualifications': ['Synthetic only; scientific approval false'],
        'datasets': [(metadata, tables, captured)]}],
        authorization_ref='synthetic-b2', research_enabled=True)
    raw = _canonical(activation)
    digest = hashlib.sha256(raw).hexdigest()
    key = 'v1/catalogue/activations/' + digest + '.json'
    (output / 'store' / key).write_bytes(raw)
    binding = json.loads(source.read_bytes())
    binding.update(activation_object=key, activation_sha256=digest)
    selected = source.with_name('edna-source.json')
    selected.write_bytes(_canonical(binding))
    selected.chmod(0o444)
    service, _ = load_snapshot_catalogue(selected, project_id=activation['project_id'],
        site_id=activation['site_id'], cursor_key=b'synthetic-b2-cache-host-key-' * 2,
        context_retention=True, research_retention=True, _allow_test_owner=True,
        _test_store=BoundedLocalStore(output / 'store'))
    entry = activation['snapshots'][-1]
    request = {'snapshot_id': entry['descriptor']['snapshot_id'],
        'scope': edna_scope().model_dump(mode='json')}
    user = fixture_user(role='admin')
    service.overview(request, user)
    cache = service.resolver.edna_input_cache
    assert cache.stats()['entries'] == 1
    return service, request, user, store, output, key, entry, cache


@pytest.mark.parametrize('change', ['revoke', 'registration'])
def test_warm_cached_host_fails_closed_on_current_source_withdrawal(cached, change):
    service, request, user, store, _, _, entry, cache = cached
    child = entry['registration']['child_snapshot_ids'][0]
    if change == 'revoke':
        store.revoke(child)
    else:
        reference = next(pair[0] for pair in entry['registration']['references'] if pair[1] == child)
        store.remove_reference(child, reference)
    with pytest.raises(CatalogueServiceError):
        service.overview(request, user)
    assert cache.stats()['entries'] == 1


@pytest.mark.parametrize('change', ['activation', 'control', 'payload'])
def test_warm_cached_host_rechecks_bytes_and_closing_fences(cached, monkeypatch, change):
    service, request, user, _, output, activation, _, cache = cached
    original, changed = BoundedLocalStore.read, False

    def changing(store, key, **kwargs):
        nonlocal changed
        # Payload integrity applies to bytes actually read. Authority/control
        # changes made after that read must also fail their closing fences.
        result = None if change == 'payload' else original(store, key, **kwargs)
        if '/objects/' in key and not changed:
            changed = True
            target = activation if change == 'activation' else (
                'v1/catalogue/control.json' if change == 'control' else key)
            path = output / 'store' / target
            path.write_bytes(path.read_bytes() + b' ')
        return original(store, key, **kwargs) if change == 'payload' else result

    monkeypatch.setattr(BoundedLocalStore, 'read', changing)
    with pytest.raises(CatalogueServiceError):
        service.overview(request, user)
    assert changed and cache.stats()['entries'] == 1
    assert service.resolver.store._active_read_scope() is None


def test_cached_host_does_not_share_a_previous_users_authority(cached):
    service, request, user, _, _, _, _, cache = cached
    before = cache.stats()['hits']
    assert service.overview(request, user)['items']
    assert cache.stats()['hits'] > before
    with pytest.raises(CatalogueServiceError):
        service.overview(request, fixture_user(role='viewer'))
