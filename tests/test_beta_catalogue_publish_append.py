"""Synthetic append publication: preserve concurrent retention and original bytes."""
from copy import deepcopy
import hashlib
import json

import pytest

from deploy.gcp.beta.data import publish_append as operator
from deploy.gcp.beta.data.append_catalogue import append_groups
from ingestion.immutable_bundle import canonical_bytes
from ingestion.provenance_snapshot import SnapshotConflict, StoredObject
from tests.test_beta_catalogue_append import group
from tests.test_beta_snapshot_catalogue import sealed as sealed


class Memory:
    def __init__(self, objects):
        self.objects = deepcopy(objects)
        self.calls = []
        self.hook = None
        self.replace_error = None
        self.commit_before_error = False

    def read(self, key, *, max_bytes):
        self.calls.append(('read', key))
        if self.hook:
            self.hook('read', key)
        obj = self.objects[key]
        if len(obj.data) > max_bytes:
            raise ValueError('Synthetic bounded read')
        return obj

    def create(self, key, data):
        self.calls.append(('create', key))
        if self.hook:
            self.hook('create', key)
        if key in self.objects:
            raise SnapshotConflict('Synthetic ifGenerationMatch=0 refusal')
        self.objects[key] = StoredObject(data, 100 + len(self.objects))
        return self.objects[key].generation

    def replace(self, key, data, *, expected_generation):
        self.calls.append(('replace', key))
        if self.objects[key].generation != expected_generation:
            raise SnapshotConflict('Synthetic stale control')
        if self.replace_error and not self.commit_before_error:
            raise self.replace_error
        self.objects[key] = StoredObject(data, expected_generation + 1)
        if self.replace_error:
            raise self.replace_error
        return self.objects[key].generation


def descriptor(root, path, **extra):
    data = path.read_bytes()
    return {'path':path.relative_to(root).as_posix(), 'bytes':len(data),
        'sha256':hashlib.sha256(data).hexdigest(), **extra}


@pytest.fixture
def bundle(sealed, monkeypatch):
    monkeypatch.setenv('DEPLOYMENT_ENV', 'test')
    monkeypatch.setattr(operator, '_source_guard', lambda document: None)
    _, output, plan, prepared = sealed
    store = prepared['store']
    store.access_gate = lambda manifest: True  # explicit synthetic operator authority
    store.add_reference(plan['index_id'], 'c17:dependency:' + 'c' * 64)
    root = output / 'append-publication'
    root.mkdir(mode=0o700)
    base = canonical_bytes(store.lifecycle())
    (root / 'base-control.json').write_bytes(base)
    base_activation = (output / 'activation.json').read_bytes()
    (root / 'base-activation.json').write_bytes(base_activation)
    remote = {operator.CONTROL:StoredObject(base, 51)}
    for directory in ['objects', 'manifests']:
        for path in (store.root / operator.PREFIX / directory).iterdir():
            remote[path.relative_to(store.root).as_posix()] = StoredObject(path.read_bytes(), 40)
    activation, _ = append_groups(store=store, activation=json.loads(base_activation),
        groups=[group()], authorization_ref='synthetic-publish-current-user')
    from api.v1_catalogue_host import _canonical
    new_activation = _canonical(activation)
    (root / 'activation.json').write_bytes(new_activation)
    (root / 'new-control.json').write_bytes(canonical_bytes(store.lifecycle()))
    files = []
    for directory in ['objects', 'manifests']:
        for path in sorted((store.root / operator.PREFIX / directory).iterdir()):
            relative = path.relative_to(store.root)
            target = root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(path.read_bytes())
            files.append(descriptor(root, target, object_key=relative.as_posix()))
    manifest = {'version':operator.VERSION, 'project_id':operator.PROJECT,
        'bucket':operator.BUCKET, 'prefix':operator.PREFIX, 'source_revision':'0' * 40,
        'source_pins':{}, 'base_control':descriptor(root, root / 'base-control.json', generation=51),
        'new_control':descriptor(root, root / 'new-control.json'),
        'base_activation':descriptor(root, root / 'base-activation.json'),
        'activation':descriptor(root, root / 'activation.json',
            object_key=operator.PREFIX + '/activations/' + hashlib.sha256(new_activation).hexdigest() + '.json'),
        'files':files}
    return root, manifest, Memory(remote)


def apply(bundle):
    root, manifest, memory = bundle
    return operator.publish(root, manifest, memory, applying=True, _test_transport=True)


def test_default_plan_has_zero_cloud_calls(bundle):
    root, manifest, memory = bundle
    result = operator.publish(root, manifest, memory)
    assert result['state'] == 'local_append_bundle_verified'
    assert result['cloud_operations'] is result['control_cas_committed'] is False
    assert memory.calls == []


def test_createonly_immutable_publication_and_control_cas_are_verified(bundle):
    root, manifest, memory = bundle
    original = deepcopy(memory.objects)
    result = apply(bundle)
    assert result['state'] == 'append_publication_committed_and_verified'
    assert result['control_generation'] == 52 and result['immutable_reused_exact'] > 0
    assert result['immutable_created'] > 0 and not result['automatic_retries']
    assert [item for item in memory.calls if item[0] == 'replace'] == [('replace', operator.CONTROL)]
    assert memory.calls[-1] == ('read', operator.CONTROL)
    for key, value in original.items():
        if key != operator.CONTROL:
            assert memory.objects[key] == value
    old = json.loads(original[operator.CONTROL].data)
    new = json.loads(memory.objects[operator.CONTROL].data)
    assert all(new['references'][key] == value for key, value in old['references'].items())
    assert new['audits'][:old['revision']] == old['audits']
    assert memory.objects[operator.CONTROL].data == (root / manifest['new_control']['path']).read_bytes()


def test_stale_control_before_upload_changes_no_objects(bundle):
    _, _, memory = bundle
    previous = memory.objects[operator.CONTROL]
    memory.objects[operator.CONTROL] = StoredObject(previous.data, previous.generation + 1)
    with pytest.raises(operator.AppendPublicationError, match='Current control changed'):
        apply(bundle)
    assert not any(action in {'create', 'replace'} for action, _ in memory.calls)


def test_concurrent_context_reference_survives_without_control_overwrite(bundle):
    _, manifest, memory = bundle
    changed = False

    def hook(action, key):
        nonlocal changed
        if action != 'create' or key != manifest['activation']['object_key'] or changed:
            return
        changed = True
        before = memory.objects[operator.CONTROL]
        state = json.loads(before.data)
        identity = next(iter(state['snapshots']))
        reference = 'c17:dependency:' + 'd' * 64
        state['revision'] += 1
        state['references'][reference] = identity
        state['audits'].append({'revision':state['revision'], 'action':'reference',
            'snapshot_id':identity, 'reference':reference})
        memory.objects[operator.CONTROL] = StoredObject(canonical_bytes(state), before.generation + 1)

    memory.hook = hook
    with pytest.raises(operator.AppendPublicationError, match='Current control changed'):
        apply(bundle)
    assert not any(action == 'replace' for action, _ in memory.calls)
    assert 'c17:dependency:' + 'd' * 64 in json.loads(memory.objects[operator.CONTROL].data)['references']


@pytest.mark.parametrize('committed', [False, True])
@pytest.mark.parametrize('failure', [OSError, SnapshotConflict])
def test_lost_control_ack_never_causes_second_mutation(bundle, committed, failure):
    _, _, memory = bundle
    memory.replace_error = failure('Synthetic unavailable acknowledgement')
    memory.commit_before_error = committed
    if committed:
        assert apply(bundle)['control_cas_committed'] is True
    else:
        with pytest.raises(operator.AppendPublicationUncertain, match='may have committed'):
            apply(bundle)
    assert sum(action == 'replace' for action, _ in memory.calls) == 1


def test_existing_content_address_cannot_be_overwritten(bundle):
    _, _, memory = bundle
    key = next(key for key in memory.objects if '/objects/' in key)
    original = memory.objects[key]
    memory.objects[key] = StoredObject(b'!' * len(original.data), original.generation + 1)
    with pytest.raises(operator.AppendPublicationError, match='immutable generation/hash'):
        apply(bundle)
    assert memory.objects[key].data == b'!' * len(original.data)
    assert not any(action == 'replace' for action, _ in memory.calls)


def test_caller_cannot_change_manifest_after_cloud_preflight(bundle):
    _, manifest, memory = bundle
    original_keys = {entry['object_key'] for entry in manifest['files']}

    def hook(action, key):
        if action == 'read' and key == operator.CONTROL:
            manifest['files'][0]['object_key'] = 'legacy/never-allowed'

    memory.hook = hook
    assert apply(bundle)['control_cas_committed']
    assert all(key in original_keys | {manifest['activation']['object_key']}
        for action, key in memory.calls if action == 'create')


@pytest.mark.parametrize('change', [
    lambda m: m.update(bucket='data-infra-infobio'),
    lambda m: m.update(prefix='legacy/catalogue'),
    lambda m: m['base_control'].update(generation=True),
    lambda m: m['files'][0].update(path='../outside'),
    lambda m: m['files'][0].update(object_key='v1/catalogue/control.json'),
    lambda m: m['files'][0].update(sha256='0' * 64),
    lambda m: m['files'].append(deepcopy(m['files'][0])),
    lambda m: m['files'].clear(),
    lambda m: m['activation'].update(object_key='v1/catalogue/activations/' + '0' * 64 + '.json'),
])
def test_malformed_or_foreign_manifest_never_reaches_cloud(bundle, change):
    _, manifest, memory = bundle
    change(manifest)
    with pytest.raises(ValueError):
        apply(bundle)
    assert memory.calls == []


@pytest.mark.parametrize('generation', [0, 51])
def test_provider_mutations_explicitly_disable_sdk_write_retry(generation):
    class Blob:
        def upload_from_string(self, data, **kwargs):
            assert data == b'synthetic-selected-bytes'
            assert kwargs == {'content_type':'application/json',
                'if_generation_match':generation, 'retry':None}
            self.generation = 52
    class Bucket:
        def blob(self, key):
            assert key == operator.CONTROL
            return Blob()
    class Store:
        bucket = Bucket()
        def _name(self, key):
            return key
    assert operator._write_once(Store(), operator.CONTROL,
        b'synthetic-selected-bytes', generation) == 52


def test_changed_private_file_rejected_before_cloud_operations(bundle):
    root, manifest, memory = bundle
    path = root / manifest['files'][0]['path']
    path.write_bytes(path.read_bytes() + b'!')
    with pytest.raises(operator.AppendPublicationError, match='bytes differ'):
        apply(bundle)
    assert memory.calls == []


def test_private_symlink_rejected_before_cloud_operations(bundle):
    root, manifest, memory = bundle
    path = root / manifest['files'][0]['path']
    replacement = path.with_suffix('.replacement')
    path.rename(replacement)
    path.symlink_to(replacement)
    with pytest.raises(ValueError):
        apply(bundle)
    assert memory.calls == []


def test_old_activation_labels_and_order_cannot_be_rewritten(bundle):
    root, manifest, memory = bundle
    path = root / manifest['activation']['path']
    value = json.loads(path.read_bytes())
    value['snapshots'][0]['descriptor']['label']['en'] = 'Unexpected replacement'
    from api.v1_catalogue_host import _canonical
    path.write_bytes(_canonical(value))
    manifest['activation'] = descriptor(root, path, object_key=operator.PREFIX + '/activations/'
        + hashlib.sha256(path.read_bytes()).hexdigest() + '.json')
    with pytest.raises(operator.AppendPublicationError, match='Existing activation entries'):
        apply(bundle)
    assert memory.calls == []


def test_removing_old_context_reference_is_not_append(bundle):
    root, manifest, memory = bundle
    path = root / manifest['new_control']['path']
    value = json.loads(path.read_bytes())
    reference = 'c17:dependency:' + 'c' * 64
    identity = value['references'].pop(reference)
    value['revision'] += 1
    value['audits'].append({'revision':value['revision'], 'action':'unreference',
        'snapshot_id':identity, 'reference':reference})
    path.write_bytes(canonical_bytes(value))
    manifest['new_control'] = descriptor(root, path)
    with pytest.raises(operator.AppendPublicationError, match='preserve every existing'):
        apply(bundle)
    assert memory.calls == []


def test_transport_injection_is_not_production_escape(bundle, monkeypatch):
    root, manifest, memory = bundle
    monkeypatch.setenv('DEPLOYMENT_ENV', 'production')
    with pytest.raises(operator.AppendPublicationError, match='test environment'):
        operator.publish(root, manifest, memory, applying=True, _test_transport=True)
    with pytest.raises(operator.AppendPublicationError, match='authorized bounded transport'):
        operator.publish(root, manifest, memory, applying=True)
    assert memory.calls == []

