"""Real sealed CTD data through the production reader/composition boundaries."""
from dataclasses import replace
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

import pytest

from api.v1_catalogue_host import CatalogueHostConfigurationError, load_snapshot_catalogue
from ingestion.artifact_store import BoundedLocalStore
from orchestration.catalogue_service import CatalogueServiceError
from tests.catalogue_service_support import fixture_user
from tests.test_v1_host import independent as independent

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('beta_ctd_prepare',
    ROOT / 'deploy/gcp/beta/data/prepare_catalogue.py')
PREPARE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = PREPARE
SPEC.loader.exec_module(PREPARE)
RAW = (b'date\tlabel\tdepth\ttemperature\tsalinity\n'
    b'2024-04-12\t2024-04-O-s1\t-1\t11.5\t33.2\n'
    b'2024-04-12\t2024-04-O-s1\t1\t10.5\t33.3\n'
    b'2024-05-09\t2024-05-O-s2\t0\t14.5\t33.1\n')


@pytest.fixture
def sealed(tmp_path, monkeypatch):
    monkeypatch.setenv('DEPLOYMENT_ENV', 'test')
    monkeypatch.setenv('ENABLE_V1_CATALOGUE', 'true')
    monkeypatch.setenv('ENABLE_V1_CATALOGUE_BROWSER', 'true')
    output = tmp_path / 'private-operator-output'
    output.mkdir(mode=0o700)
    plan = PREPARE.planned_snapshots(RAW, source_sha256=hashlib.sha256(RAW).hexdigest())
    result = PREPARE.seal_catalogue(output, plan)
    key = result['activation_object_key']
    activation = output / 'store' / key
    activation.parent.mkdir(parents=True)
    activation.write_bytes((output / 'activation.json').read_bytes())
    binding = {'version': 'ocean-v1-gcs-catalogue-host-v1', 'project_id': PREPARE.PROJECT,
        'site_id': 'v1:' + PREPARE.PROJECT, 'bucket': PREPARE.PROJECT + '-snapshots',
        'prefix': 'v1/catalogue', 'activation_object': key,
        'activation_sha256': result['activation_sha256']}
    source = tmp_path / 'source.json'
    source.write_bytes(PREPARE.canonical(binding))
    source.chmod(0o444)
    return source, output, plan, result


def load(sealed):
    source, output, _, _ = sealed
    return load_snapshot_catalogue(source, project_id=PREPARE.PROJECT,
        site_id='v1:' + PREPARE.PROJECT, cursor_key=b'stable-private-test-cursor-key' * 2,
        _allow_test_owner=True, _test_store=BoundedLocalStore(output / 'store'))


def test_raw_normalization_retains_every_row_and_signed_source_semantics(sealed):
    _, _, plan, _ = sealed
    assert len(plan['frames']['casts']) == 2
    depths = plan['frames']['depth_observations']
    assert len(depths) == 3 and depths.depth.tolist() == [-1.0, 1.0, 0.0]
    assert depths.source_row.tolist() == [1, 2, 3]
    assert plan['dataset'].depth_convention == 'signed_source'
    assert plan['dataset'].collection_date_precision == 'day'
    assert not plan['registry'].analyses and not plan['registry'].relationships


def test_actual_sealed_dataset_discovery_and_inventory(sealed):
    service, browser = load(sealed)
    actor = fixture_user(role='admin')
    scope = PREPARE.scope().model_dump(mode='json')
    discovery = browser.discover({'scope': scope}, actor)
    assert discovery['total'] == 1 and discovery['latest_snapshot_id'] == sealed[2]['index_id']
    response = service.list({'snapshot_id': sealed[2]['index_id'], 'scope': scope,
        'filters': {'kinds': ['dataset']}, 'limit': 100}, actor)
    assert len(response['items']) == 1 and response['items'][0]['source_family'] == 'ctd'


def test_request_scopes_fence_authority_and_control_twice_without_cross_request_reuse(sealed, monkeypatch):
    service, browser = load(sealed)
    original, reads = BoundedLocalStore.read, []
    def counted(store, key, **kwargs):
        reads.append(key)
        return original(store, key, **kwargs)
    monkeypatch.setattr(BoundedLocalStore, 'read', counted)
    actor = fixture_user(role='admin')
    payload = {'scope': PREPARE.scope().model_dump(mode='json')}
    browser.discover(payload, actor)
    assert sum('/activations/' in key for key in reads) == 2
    assert sum(key.endswith('/control.json') for key in reads) == 2
    reads.clear()
    service.overview({'snapshot_id': sealed[2]['index_id'], **payload}, actor)
    assert sum('/activations/' in key for key in reads) == 2
    assert sum(key.endswith('/control.json') for key in reads) == 2


@pytest.mark.parametrize('change', ['removed', 'generation', 'bytes'])
def test_activation_change_during_verified_operation_is_rejected_at_return(sealed, monkeypatch, change):
    service, _ = load(sealed)
    path = sealed[1] / 'store' / sealed[3]['activation_object_key']
    original, changed = BoundedLocalStore.read, False
    def changing(store, key, **kwargs):
        nonlocal changed
        result = original(store, key, **kwargs)
        if '/objects/' in key and not changed:
            changed = True
            if change == 'removed':
                path.unlink()
            elif change == 'generation':
                path.write_bytes(path.read_bytes())
            else:
                path.write_bytes(path.read_bytes() + b' ')
        return result
    monkeypatch.setattr(BoundedLocalStore, 'read', changing)
    with pytest.raises(CatalogueServiceError):
        service.overview({'snapshot_id': sealed[2]['index_id'],
            'scope': PREPARE.scope().model_dump(mode='json')}, fixture_user(role='admin'))
    assert changed
    assert service.resolver.authority._scope.get() is None
    assert service.resolver.store._active_read_scope() is None


def test_concurrent_scopes_do_not_share_control_or_activation_observations(sealed, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    service, _ = load(sealed)
    original, reads = BoundedLocalStore.read, []
    def counted(store, key, **kwargs):
        reads.append(key)
        return original(store, key, **kwargs)
    monkeypatch.setattr(BoundedLocalStore, 'read', counted)
    payload = {'snapshot_id': sealed[2]['index_id'], 'scope': PREPARE.scope().model_dump(mode='json')}
    with ThreadPoolExecutor(max_workers=2) as pool:
        calls = [pool.submit(service.overview, payload, fixture_user(role='admin')) for _ in range(2)]
        assert all(call.result()['items'] for call in calls)
    assert sum('/activations/' in key for key in reads) == 4
    assert sum(key.endswith('/control.json') for key in reads) == 4


def test_discovery_closing_control_conflict_has_a_safe_retry_response(sealed, monkeypatch):
    import os
    _, browser = load(sealed)
    original, changed = BoundedLocalStore.read, False
    def changing(store, key, **kwargs):
        nonlocal changed
        result = original(store, key, **kwargs)
        if '/objects/' in key and not changed:
            changed = True
            path = sealed[1] / 'store/v1/catalogue/control.json'
            info = path.stat()
            os.utime(path, ns=(info.st_atime_ns, info.st_mtime_ns + 1_000_000_000))
        return result
    monkeypatch.setattr(BoundedLocalStore, 'read', changing)
    with pytest.raises(CatalogueServiceError) as failure:
        browser.discover({'scope': PREPARE.scope().model_dump(mode='json')}, fixture_user(role='admin'))
    assert changed and failure.value.status_code == 503
    assert failure.value.message == 'Catalogue is unavailable'


def test_sealed_mode_reaches_authenticated_host_without_enabling_research(sealed, independent, monkeypatch):
    from fastapi.testclient import TestClient
    from pydantic import SecretStr
    from sqlalchemy import select
    from api import v1_catalogue_host, v1_host
    from db.app_models import AppUser
    from tests.test_v1_host import SECRET, headers, settings
    _, factory = independent
    with factory.begin() as session:
        session.scalar(select(AppUser)).role = 'admin'
    original = v1_catalogue_host.load_snapshot_catalogue
    monkeypatch.setattr(v1_catalogue_host, 'load_snapshot_catalogue',
        lambda *a, **kw: original(*a, **kw, _allow_test_owner=True,
            _test_store=BoundedLocalStore(sealed[1] / 'store')))
    host = settings(project_id=PREPARE.PROJECT, site_id='v1:' + PREPARE.PROJECT)
    bundle = v1_host.catalogue_services_from_environment(host, SecretStr(SECRET), {
        'OCEAN_V1_CATALOGUE_MODE': 'sealed-gcs-v1', 'OCEAN_V1_CATALOGUE_CONFIG': str(sealed[0])})
    application = v1_host.create_host_app(settings=host, session_factory=factory,
        internal_secret=SecretStr(SECRET), services=bundle, _allow_test_sqlite=True)
    payload = {'scope': PREPARE.scope().model_dump(mode='json')}
    with TestClient(application, base_url='http://127.0.0.1:8000') as client:
        assert client.post('/catalogue/snapshots', json=payload).status_code == 401
        current = client.get('/v1/runtime', headers=headers()).json()
        assert current['capabilities']['catalogue']['status'] == 'ready'
        assert current['capabilities']['research']['status'] == 'unavailable'
        snapshots = client.post('/catalogue/snapshots', json=payload, headers=headers())
        assert snapshots.status_code == 200 and snapshots.json()['total'] == 1
        assert client.post('/research/investigations/create', json={}, headers=headers()).status_code == 403


@pytest.mark.parametrize('change', ['researcher', 'commercial', 'suspended'])
def test_current_account_is_required_before_dataset_visibility(sealed, change):
    service, browser = load(sealed)
    actor = fixture_user(role='admin')
    actor = replace(actor, **({'role': 'researcher'} if change == 'researcher'
        else {'account_type': 'commercial'} if change == 'commercial' else {'status': 'suspended'}))
    payload = {'scope': PREPARE.scope().model_dump(mode='json')}
    if change == 'suspended':
        with pytest.raises(CatalogueServiceError):
            browser.discover(payload, actor)
    else:
        assert browser.discover(payload, actor)['total'] == 0
    with pytest.raises(CatalogueServiceError):
        service.overview({'snapshot_id': sealed[2]['index_id'], **payload}, actor)


def test_withdrawn_snapshot_is_no_longer_discoverable(sealed):
    _, _, plan, result = sealed
    service, browser = load(sealed)
    result['store'].revoke(plan['child_id'])
    payload = {'scope': PREPARE.scope().model_dump(mode='json')}
    actor = fixture_user(role='admin')
    current = browser.discover(payload, actor)
    assert current['total'] == 0 and current['snapshots'] == []
    assert current['latest_snapshot_id'] is None
    with pytest.raises(CatalogueServiceError):
        service.overview({'snapshot_id': plan['index_id'], **payload}, actor)


@pytest.mark.parametrize('change', ['removed', 'replaced_same_bytes', 'tampered'])
def test_runtime_activation_authority_never_falls_back_on_change(sealed, change):
    _, browser = load(sealed)
    path = sealed[1] / 'store' / sealed[3]['activation_object_key']
    if change == 'removed':
        path.unlink()
    elif change == 'replaced_same_bytes':
        replacement = path.with_suffix('.new')
        replacement.write_bytes(path.read_bytes())
        replacement.replace(path)
    else:
        path.write_bytes(path.read_bytes() + b' ')
    with pytest.raises(CatalogueServiceError):
        browser.discover({'scope': PREPARE.scope().model_dump(mode='json')}, fixture_user(role='admin'))


def test_changed_root_binding_and_foreign_target_fail_closed(sealed):
    _, browser = load(sealed)
    source = sealed[0]
    source.chmod(0o644)
    with pytest.raises(CatalogueServiceError):
        browser.discover({'scope': PREPARE.scope().model_dump(mode='json')}, fixture_user(role='admin'))
    document = json.loads(source.read_bytes())
    document['bucket'] = 'data-infra-infobio-ocean-data'
    source.write_bytes(PREPARE.canonical(document))
    source.chmod(0o444)
    with pytest.raises(CatalogueHostConfigurationError):
        load(sealed)


@pytest.mark.parametrize('suffix', [b'bad\tlabel\t1\t10\t33\n',
    b'2024-04-12\t2024-04-O-s1\tNaN\t10\t33\n'])
def test_invalid_source_measurements_are_not_silently_dropped(suffix):
    value = RAW.splitlines(keepends=True)[0] + suffix
    with pytest.raises(PREPARE.CataloguePreparationError):
        PREPARE.ctd_dataset(value, source_sha256=hashlib.sha256(value).hexdigest())
