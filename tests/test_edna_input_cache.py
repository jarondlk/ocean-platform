"""Verified immutable inputs can be shared; bytes, budgets and policy cannot."""
from concurrent.futures import ThreadPoolExecutor
from threading import Event
import time

import pandas as pd
import pytest

from ingestion import edna_catalogue_inputs as inputs
from ingestion.edna_input_cache import ValidatedEDNAInputCache
from schema.edna_catalogue_fixtures import edna_fixture
from tests.test_edna_catalogue_inputs import frozen


def selected(tmp_path, name='one'):
    return frozen(tmp_path, edna_fixture(3, dataset_id='synthetic:cache:' + name))


def observe(monkeypatch):
    original = inputs.load_dataset
    calls = []

    def load(*args, **kwargs):
        calls.append(kwargs.get('decoded_budget'))
        return original(*args, **kwargs)

    monkeypatch.setattr(inputs, 'load_dataset', load)
    return calls


def test_hits_still_return_independently_mutable_frames_metadata_and_objects(tmp_path, monkeypatch):
    source = selected(tmp_path)
    expected = inputs.load_dataset(*source)
    calls = observe(monkeypatch)
    cache = ValidatedEDNAInputCache()
    first = cache.load(*source)
    first.metadata.methods.append('poisoned caller method')
    first.tables['detections'].iloc[0, 0] = 'poison'
    first.tables['occurrences'].columns.values[0] = 'poison'
    first.tables['assays'].index.values[0] = 999
    first.tables['classifications'].attrs['decoded_bytes'] = 0
    try:
        first.objects[0].source_id = 'synthetic:caller-poison'
    except ValueError:
        pass  # A frozen object rejects mutation instead of sharing it.
    second = cache.load(*source)
    assert len(calls) == 1
    assert second.metadata == expected.metadata and second.objects == expected.objects
    for role, frame in second.tables.items():
        pd.testing.assert_frame_equal(frame, expected.tables[role])
        assert frame.attrs == expected.tables[role].attrs


def test_every_warm_lookup_reverifies_owned_bytes(tmp_path, monkeypatch):
    manifest, contents, obj = selected(tmp_path)
    calls = observe(monkeypatch)
    cache = ValidatedEDNAInputCache()
    cache.load(manifest, contents, obj)
    damaged = dict(contents)
    table = next(item for item in manifest.objects if item.role == 'detections')
    raw = damaged[table.object_id]
    damaged[table.object_id] = bytes([raw[0] ^ 1]) + raw[1:]
    with pytest.raises(ValueError):
        cache.load(manifest, damaged, obj)
    assert len(calls) == 1


def test_generation_binding_changes_do_not_reuse_an_old_validation(tmp_path, monkeypatch):
    source = selected(tmp_path)
    calls = observe(monkeypatch)
    cache = ValidatedEDNAInputCache()
    cache.load(*source, generation_binding='a' * 64)
    cache.load(*source, generation_binding='a' * 64)
    cache.load(*source, generation_binding='b' * 64)
    assert len(calls) == 2


def test_cold_and_warm_decoded_budgets_are_enforced_without_failed_fill_retention(tmp_path, monkeypatch):
    source = selected(tmp_path)
    calls = observe(monkeypatch)
    cache = ValidatedEDNAInputCache()
    with pytest.raises(ValueError):
        cache.load(*source, decoded_budget=1)
    assert calls == [1] and cache.stats()['entries'] == 0
    cache.load(*source)
    with pytest.raises(ValueError):
        cache.load(*source, decoded_budget=1)
    assert len(calls) == 2


@pytest.mark.parametrize('budget', [True, -1, 1.0])
def test_invalid_remaining_budget_is_rejected_before_a_hit(tmp_path, budget):
    source = selected(tmp_path)
    cache = ValidatedEDNAInputCache()
    cache.load(*source)
    with pytest.raises(ValueError):
        cache.load(*source, decoded_budget=budget)


def test_eviction_reloads_and_oversized_entries_are_not_retained(tmp_path, monkeypatch):
    one, two = selected(tmp_path / 'a', 'one'), selected(tmp_path / 'b', 'two')
    calls = observe(monkeypatch)
    cache = ValidatedEDNAInputCache(maximum_entries=1)
    for source in [one, two, one]:
        cache.load(*source)
        assert cache.stats()['entries'] == 1
        assert cache.stats()['accounted_retained_bytes'] <= cache.maximum_bytes
    assert len(calls) == 3 and cache.stats()['evictions'] == 2
    tiny = ValidatedEDNAInputCache(maximum_bytes=1)
    tiny.load(*one)
    tiny.load(*one)
    assert len(calls) == 5 and tiny.stats()['entries'] == 0


@pytest.mark.parametrize('fail', [False, True])
def test_concurrent_fill_coalesces_and_failed_fills_do_not_poison_recovery(tmp_path, monkeypatch, fail):
    source = selected(tmp_path)
    cache = ValidatedEDNAInputCache()
    original = inputs.load_dataset
    entered, release = Event(), Event()
    calls = []

    def slow(*args, **kwargs):
        calls.append(1)
        entered.set()
        assert release.wait(5)
        if fail:
            raise ValueError('synthetic invalid source rows')
        return original(*args, **kwargs)

    monkeypatch.setattr(inputs, 'load_dataset', slow)
    with ThreadPoolExecutor(max_workers=4) as pool:
        work = [pool.submit(cache.load, *source) for _ in range(4)]
        assert entered.wait(3)
        until = time.monotonic() + 3
        while cache.stats()['coalesced'] < 3 and time.monotonic() < until:
            time.sleep(.01)
        release.set()
        if fail:
            for future in work:
                with pytest.raises(ValueError, match='invalid source rows'):
                    future.result()
            assert cache.stats()['entries'] == 0
        else:
            result = [future.result() for future in work]
            assert len({id(item.tables['detections']) for item in result}) == 4
        assert len(calls) == 1
    monkeypatch.setattr(inputs, 'load_dataset', original)
    cache.load(*source)
    assert cache.stats()['entries'] == 1


def test_dataset_policy_remains_current_after_warm_input_hits(tmp_path):
    from tests.test_beta_multisource_edna_catalogue import configured, request
    from schema.context_catalogue import CatalogueFilters
    index, adapter, identities, policy = configured(tmp_path)
    cache = ValidatedEDNAInputCache()
    adapter.adapters['edna_metabarcoding'].input_cache = cache
    query = request(index, filters=CatalogueFilters(kinds=['dataset']))
    assert {item.id for item in adapter.list(query).items} == identities
    policy['denied'].add('test:edna:a')
    assert {item.id for item in adapter.list(query).items} == identities - {'test:edna:a'}
    assert cache.stats()['hits'] > 0


def test_distinct_budget_fills_do_not_share_a_failure_or_double_charge_retention(tmp_path, monkeypatch):
    source = selected(tmp_path)
    cache = ValidatedEDNAInputCache()
    original = inputs.load_dataset
    entered, release = Event(), Event()

    def slow(*args, **kwargs):
        if kwargs['decoded_budget'] == 1:
            entered.set()
            assert release.wait(5)
        return original(*args, **kwargs)

    monkeypatch.setattr(inputs, 'load_dataset', slow)
    with ThreadPoolExecutor(max_workers=2) as pool:
        narrow = pool.submit(cache.load, *source, decoded_budget=1)
        assert entered.wait(3)
        valid = pool.submit(cache.load, *source)
        expected = valid.result(timeout=5)
        retained = cache.stats()['accounted_retained_bytes']
        release.set()
        with pytest.raises(ValueError):
            narrow.result()
    assert cache.stats()['entries'] == 1 and cache.stats()['inflight'] == 0
    pd.testing.assert_frame_equal(cache.load(*source).tables['detections'], expected.tables['detections'])
    assert cache.stats()['accounted_retained_bytes'] == retained


def test_distinct_cache_instances_and_bounded_inflight_fills(tmp_path, monkeypatch):
    one, two = selected(tmp_path / 'a', 'one'), selected(tmp_path / 'b', 'two')
    cache = ValidatedEDNAInputCache(maximum_inflight=1)
    original = inputs.load_dataset
    entered, release = Event(), Event()
    calls = []

    def slow(*args, **kwargs):
        calls.append(args[2].object_id)
        entered.set()
        assert release.wait(5)
        return original(*args, **kwargs)

    monkeypatch.setattr(inputs, 'load_dataset', slow)
    with ThreadPoolExecutor(max_workers=2) as pool:
        a = pool.submit(cache.load, *one)
        assert entered.wait(3)
        b = pool.submit(cache.load, *two)
        # The second distinct source must wait for a bounded fill slot.
        assert not b.done() and cache.stats()['inflight'] == 1
        release.set()
        a.result(timeout=5)
        b.result(timeout=5)
    assert len(calls) == 2 and cache.stats()['entries'] == 2
    ValidatedEDNAInputCache().load(*one)
    assert len(calls) == 3


@pytest.mark.parametrize('kwargs', [
    {'maximum_bytes': True}, {'maximum_bytes': 0}, {'maximum_bytes': 1024**3 + 1},
    {'maximum_entries': 65}, {'maximum_inflight': 0}, {'maximum_inflight': 5},
])
def test_only_explicit_bounded_capacity_is_supported(kwargs):
    with pytest.raises(ValueError):
        ValidatedEDNAInputCache(**kwargs)
