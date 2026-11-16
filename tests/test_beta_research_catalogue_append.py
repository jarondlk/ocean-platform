"""Enabled Research appends require an independently bound existing activation."""
import hashlib
import json

import pytest

from deploy.gcp.beta.data import publish_append as operator
from api.v1_catalogue_host import _canonical
from ingestion.provenance_snapshot import StoredObject
from tests.test_beta_catalogue_publish_append import bundle as bundle, descriptor
from tests.test_beta_snapshot_catalogue import sealed as sealed


def enabled(bundle, *, base=True, new=True):
    root, manifest, memory = bundle
    for name, selected in [('base_activation', base), ('activation', new)]:
        path = root / manifest[name]['path']
        value = json.loads(path.read_bytes())
        value['research_enabled'] = selected
        path.write_bytes(_canonical(value))
        extra = {'object_key': operator.PREFIX + '/activations/' + hashlib.sha256(path.read_bytes()).hexdigest() + '.json'} if name == 'activation' else {}
        manifest[name] = descriptor(root, path, **extra)
    digest = manifest['base_activation']['sha256']
    key = operator.PREFIX + '/activations/' + digest + '.json'
    memory.objects[key] = StoredObject((root / manifest['base_activation']['path']).read_bytes(), 40)
    return digest, key


def publish(bundle, digest):
    root, manifest, memory = bundle
    return operator.publish(root, manifest, memory, applying=True, _test_transport=True,
        research_enabled=True, expected_base_activation_sha256=digest)


def test_enabled_mode_is_preserved_with_independently_bound_remote_base(bundle):
    digest, key = enabled(bundle)
    result = publish(bundle, digest)
    assert result['control_cas_committed'] and result['research_enabled']
    assert result['base_activation_generation'] == 40
    assert result['scientific_approval'] is False
    calls = bundle[2].calls
    assert calls.index(('read', key)) < next(i for i, call in enumerate(calls) if call[0] == 'create')
    assert sum(call[0] == 'replace' for call in calls) == 1


def test_default_mode_cannot_silently_adopt_an_enabled_base(bundle):
    enabled(bundle)
    with pytest.raises(ValueError):
        operator.publish(*bundle)
    assert bundle[2].calls == []


@pytest.mark.parametrize('digest', [None, '', '0' * 64, True])
def test_missing_or_wrong_independent_activation_pin_rejects_before_io(bundle, digest):
    enabled(bundle)
    with pytest.raises(ValueError):
        publish(bundle, digest)
    assert bundle[2].calls == []


@pytest.mark.parametrize('base,new', [(False, True), (True, False), (False, False)])
def test_explicit_mode_neither_enables_nor_disables_the_baseline(bundle, base, new):
    digest, _ = enabled(bundle, base=base, new=new)
    with pytest.raises(ValueError):
        publish(bundle, digest)
    assert bundle[2].calls == []


def test_remote_activation_mismatch_rejects_before_writes(bundle):
    digest, key = enabled(bundle)
    bundle[2].objects[key] = StoredObject(b'{}', 41)
    with pytest.raises(ValueError, match='remotely retained'):
        publish(bundle, digest)
    assert not any(call[0] != 'read' for call in bundle[2].calls)


@pytest.mark.parametrize('missing', [True, False])
def test_remote_baseline_read_failure_is_sanitized_and_writes_nothing(bundle, missing):
    digest, key = enabled(bundle)
    if missing:
        del bundle[2].objects[key]
    else:
        def fail(operation, selected):
            if operation == 'read' and selected == key:
                raise RuntimeError('synthetic private provider message')
        bundle[2].hook = fail
    with pytest.raises(operator.AppendPublicationError, match='baseline read unavailable') as error:
        publish(bundle, digest)
    assert 'private provider message' not in str(error.value)
    assert not any(call[0] != 'read' for call in bundle[2].calls)


def test_mode_must_be_a_primitive_boolean(bundle):
    digest, _ = enabled(bundle)
    with pytest.raises(ValueError, match='trusted Research mode'):
        operator.publish(*bundle, research_enabled=1, expected_base_activation_sha256=digest)
    assert bundle[2].calls == []
