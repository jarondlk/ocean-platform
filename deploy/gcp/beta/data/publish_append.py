"""Source-bound, append-only beta catalogue publication by a trusted operator.

No authentication acquisition, role changes, listing or automatic retry exists.
The caller supplies its already authorized bounded GCS transport. Default mode
validates the explicit private local bundle and performs zero cloud operations.
Immutable writes are create-only; one exact current lifecycle CAS is last.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import subprocess

from ingestion.artifact_store import BoundedGcsStore, safe_key
from ingestion.catalogue_snapshot import MAX_CONTROL_BYTES
from ingestion.gcs_catalogue_snapshot import BUCKET, PREFIX, validated_lifecycle
from ingestion.immutable_bundle import validate_id
from ingestion.provenance_snapshot import SnapshotConflict, StoredObject
from schema.catalogue_snapshot import MAX_BYTES, MAX_MANIFEST_BYTES, manifest_bytes, validated_manifest

ROOT = Path(__file__).resolve().parents[4]
PROJECT = 'ocean-v1-beta-20261101'
VERSION = 'ocean-beta-catalogue-append-publication-v1'
CONTROL = PREFIX + '/control.json'
MAX_FILES = 16000
MAX_BUNDLE_BYTES = 2 * 1024 * 1024 * 1024
REQUIRED_SOURCES = frozenset({
    'deploy/gcp/beta/data/publish_append.py', 'deploy/gcp/beta/data/prepare_quarantine.py',
    'ingestion/gcs_catalogue_snapshot.py', 'ingestion/catalogue_snapshot.py',
    'ingestion/artifact_store.py', 'ingestion/provenance_snapshot.py',
    'ingestion/immutable_bundle.py', 'api/v1_catalogue_host.py',
    'orchestration/catalogue_registration.py', 'schema/catalogue_snapshot.py',
    'ingestion/scientific_catalogue_inputs.py', 'schema/scientific_catalogue.py',
})


class AppendPublicationError(ValueError):
    """Fixed diagnostics; no scientific payload, credentials or provider errors."""


class AppendPublicationUncertain(RuntimeError):
    """A control write might have committed. Preserve receipts; never retry."""


def require(value, message):
    if not value:
        raise AppendPublicationError(message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def _source_guard(document):
    revision, pins = document['source_revision'], document['source_pins']
    require(type(revision) is str and re.fullmatch(r'[a-f0-9]{40}', revision)
        and type(pins) is dict and REQUIRED_SOURCES <= set(pins), 'Complete committed operator source pins required')
    for name, expected in pins.items():
        safe_key(name)
        validate_id(expected)
        path = ROOT / name
        require(path.is_file() and not path.is_symlink()
            and not any(p.is_symlink() for p in path.parents if p.is_relative_to(ROOT)),
            'Pinned source must be a regular checkout file')
        data = path.read_bytes()
        result = subprocess.run(['git', '-C', str(ROOT), 'show', revision + ':' + name],
            capture_output=True, check=False, timeout=15)
        require(result.returncode == 0 and result.stdout == data and sha(data) == expected,
            'Current publication operator differs from its selected source checkpoint')


def _read(root, descriptor, maximum, *, required_bytes=True):
    from deploy.gcp.beta.data.prepare_quarantine import source_file
    require(type(descriptor) is dict and {'path', 'sha256'} <= set(descriptor),
        'Explicit private file descriptor required')
    relative = safe_key(descriptor['path'])
    validate_id(descriptor['sha256'])
    size = descriptor.get('bytes')
    require(not required_bytes or type(size) is int, 'Explicit immutable file length required')
    if size is not None:
        require(type(size) is int and 0 <= size <= maximum, 'Bounded private file length required')
    with source_file(root, relative) as (stream, info):
        require(0 <= info[4] <= maximum, 'Private publication file exceeds its finite bound')
        data = stream.read(maximum + 1)
    require(len(data) <= maximum and (size is None or len(data) == size)
        and sha(data) == descriptor['sha256'], 'Private publication bytes differ from their exact manifest')
    return data


def _activation(root, descriptor):
    from api.v1_catalogue_host import _activation as validate, MAX_ACTIVATION_BYTES
    data = _read(root, descriptor, MAX_ACTIVATION_BYTES, required_bytes=False)
    validate(data)
    return json.loads(data)


def validate_transition(before, after):
    """Permit only new seals and additive C14 references, retaining all history."""
    require(after['revision'] > before['revision']
        and after['audits'][:before['revision']] == before['audits']
        and all(after['snapshots'].get(k) == v for k, v in before['snapshots'].items())
        and all(after['references'].get(k) == v for k, v in before['references'].items())
        and (after['latest'], after['latest_generation']) == (before['latest'], before['latest_generation']),
        'Publication must preserve every existing lifecycle, reference, audit and latest identity')
    added = set(after['snapshots']) - set(before['snapshots'])
    require(bool(added), 'A publication must seal explicit new snapshots')
    for audit in after['audits'][before['revision']:]:
        require(audit['action'] in {'seal', 'reference'} and audit['snapshot_id'] in added,
            'Only new snapshot seals and their own registration references are allowed')
        if audit['action'] == 'reference':
            require(re.fullmatch(r'c14:dependency:[a-f0-9]{64}', audit['reference']) is not None,
                'Only canonical new C14 dependency bindings are allowed')
    return added


def validate_bundle(root, manifest):
    """Validate complete private inputs before any storage read/write is allowed."""
    from deploy.gcp.beta.data.prepare_quarantine import clean_absolute, safe_ancestors
    from api.v1_catalogue_host import _activation as validate_activation, _canonical
    root = clean_absolute(root)
    safe_ancestors(root)
    require(root.is_dir() and not root.is_relative_to(ROOT), 'An explicit private bundle outside the checkout is required')
    require(type(manifest) is dict and set(manifest) == {
        'version', 'project_id', 'bucket', 'prefix', 'source_revision', 'source_pins',
        'base_control', 'new_control', 'base_activation', 'activation', 'files'}
        and manifest['version'] == VERSION and manifest['project_id'] == PROJECT
        and manifest['bucket'] == BUCKET and manifest['prefix'] == PREFIX,
        'Exact isolated beta append publication manifest required')
    require(type(manifest['base_control']) is dict and {'path', 'sha256', 'generation'} <= set(manifest['base_control'])
        and set(manifest['base_control']) <= {'path', 'sha256', 'generation', 'bytes'}
        and type(manifest['new_control']) is dict and set(manifest['new_control']) == {'path', 'sha256', 'bytes'}
        and type(manifest['base_activation']) is dict and {'path', 'sha256'} <= set(manifest['base_activation'])
        and set(manifest['base_activation']) <= {'path', 'sha256', 'bytes'},
        'Exact base/control/activation descriptor fields required')
    _source_guard(manifest)
    require(type(manifest['base_control'].get('generation')) is int
        and manifest['base_control']['generation'] > 0, 'Exact positive base GCS control generation required')
    before = validated_lifecycle(_read(root, manifest['base_control'], MAX_CONTROL_BYTES, required_bytes=False))
    after = validated_lifecycle(_read(root, manifest['new_control'], MAX_CONTROL_BYTES))
    added = validate_transition(before, after)
    old, activation = _activation(root, manifest['base_activation']), _activation(root, manifest['activation'])
    require(len(activation['snapshots']) > len(old['snapshots'])
        and activation['snapshots'][:len(old['snapshots'])] == old['snapshots']
        and activation['qualifications'][:len(old['qualifications'])] == old['qualifications'],
        'Existing activation entries and order must remain unchanged')
    require(activation['access'] == old['access'] and activation['scientific_mode'] == old['scientific_mode']
        and activation['scientific_approval'] is False and activation['research_enabled'] is False,
        'Append publication cannot expand user or scientific execution authority')
    # Both old and new registrations must bind the actual matching lifecycle.
    for document, state in [(old, before), (activation, after)]:
        _, _, registrations, _ = validate_activation(_canonical(document))
        for registration in registrations.values():
            for reference, identity in registration.references:
                entry = state['snapshots'].get(identity)
                require(state['references'].get(reference) == identity and entry is not None
                    and not entry['retired'] and not entry['revoked'], 'Activation registration is not currently retained')
    require(type(manifest['files']) is list and 0 < len(manifest['files']) <= MAX_FILES,
        'Bounded explicit immutable publication inventory required')
    activation_key = PREFIX + '/activations/' + manifest['activation']['sha256'] + '.json'
    require(manifest['activation'].get('object_key') == activation_key,
        'Activation object must be its exact content-addressed private beta key')
    entries = [*manifest['files'], manifest['activation']]
    keys, objects, manifests, total = set(), {}, {}, 0
    for entry in entries:
        require(type(entry) is dict and set(entry) == {'path', 'object_key', 'sha256', 'bytes'},
            'Exact immutable file descriptor fields required')
        key = safe_key(entry['object_key'])
        require(key not in keys and key != CONTROL, 'Immutable objects must be distinct and cannot target control')
        match = re.fullmatch(re.escape(PREFIX) + r'/(objects|manifests|activations)/([a-f0-9]{64})(\.json)?', key)
        require(match is not None and ((match[1] == 'objects' and match[3] is None)
            or (match[1] in {'manifests', 'activations'} and match[3] == '.json')),
            'Only exact beta content-addressed keys may be created')
        maximum = MAX_BYTES if match[1] == 'objects' else MAX_MANIFEST_BYTES
        data = _read(root, entry, maximum)
        require(sha(data) == match[2], 'Object key is not bound to exact local bytes')
        if match[1] == 'objects':
            objects[match[2]] = entry
        elif match[1] == 'manifests':
            model = validated_manifest(json.loads(data))
            require(manifest_bytes(model) == data, 'Snapshot manifest is not canonical')
            manifests[match[2]] = model
        else:
            require(key == activation_key, 'Only the selected new activation may be published')
        total += len(data)
        require(total <= MAX_BUNDLE_BYTES, 'Publication byte inventory exceeds its finite bound')
        keys.add(key)
    require(added <= set(manifests), 'Every newly sealed snapshot manifest must be provided')
    for model in manifests.values():
        for obj in model.objects:
            require(obj.sha256 in objects and objects[obj.sha256]['bytes'] == obj.size_bytes,
                'Every manifest object needs explicit exact local immutable bytes')
    from ingestion.scientific_catalogue_inputs import load_registry
    from schema.scientific_catalogue import DatasetBinding
    for entry in activation['snapshots'][len(old['snapshots']):]:
        identity = entry['descriptor']['snapshot_id']
        require(identity in added and identity in manifests,
            'Every new activation index must be newly sealed and explicitly provided')
        model = manifests[identity]
        contents = {obj.object_id:_read(root, objects[obj.sha256], obj.size_bytes) for obj in model.objects}
        registry = load_registry(model, contents).metadata
        bindings = [DatasetBinding.model_validate(value) for value in entry['datasets']]
        require(list(registry.datasets) == bindings and not registry.analyses and not registry.workflows
            and not registry.definitions and not registry.relationships and not registry.superseded_generations,
            'New activation must match its exact datasets-only scientific index')
    return {'version': VERSION, 'state':'local_append_bundle_verified', 'project_id':PROJECT,
        'source_revision':manifest['source_revision'], 'base_revision':before['revision'],
        'new_revision':after['revision'], 'base_control_generation':manifest['base_control']['generation'],
        'base_control_sha256':manifest['base_control']['sha256'],
        'new_control_sha256':manifest['new_control']['sha256'],
        'activation_sha256':manifest['activation']['sha256'], 'new_snapshot_count':len(added),
        'immutable_files':len(entries), 'immutable_bytes':total, 'scientific_approval':False,
        'cloud_operations':False, 'control_cas_committed':False}


def _read_control(store):
    obj = store.read(CONTROL, max_bytes=MAX_CONTROL_BYTES)
    require(isinstance(obj, StoredObject) and type(obj.data) is bytes
        and type(obj.generation) is int and obj.generation > 0, 'Generation-bound current control read required')
    validated_lifecycle(obj.data)
    return obj


def _same_base(observed, manifest):
    require(observed.generation == manifest['base_control']['generation']
        and sha(observed.data) == manifest['base_control']['sha256'],
        'Current control changed; preserve new bytes and reprepare without retry')


def _write_once(store, key, data, expected_generation, *, test_transport=False):
    if test_transport:
        return store.create(key, data) if expected_generation == 0 else store.replace(
            key, data, expected_generation=expected_generation)
    # The inherited store's write methods use SDK conditional-retry defaults.
    # An acknowledged 412 after a lost successful response could otherwise
    # conceal an earlier committed request. Disable SDK write retries here.
    blob = store.bucket.blob(store._name(key))
    try:
        blob.upload_from_string(data, content_type='application/json',
            if_generation_match=expected_generation, retry=None)
    except Exception as error:
        raise store._translate_error(error, key=key) from None
    return int(blob.generation or 0)


def publish(root, manifest, store=None, applying=False, *, _test_transport=False):
    """Publish once through explicit authority; caller persists selection/evidence.

    Caller MUST retain an exclusive one-attempt selection before applying and
    preserve partial failures. This function never retries a mutation. A lost
    control acknowledgement is reconciled only by an exact current readback;
    every other uncertain outcome raises AppendPublicationUncertain.
    """
    # Freeze caller-owned metadata before provider callbacks or concurrent code
    # could alter selected targets, keys, hashes or the base CAS generation.
    try:
        encoded = json.dumps(manifest, allow_nan=False).encode()
        require(len(encoded) <= MAX_CONTROL_BYTES, 'Publication metadata exceeds its finite bound')
        manifest = json.loads(encoded)
    except (TypeError, ValueError):
        raise AppendPublicationError('Explicit bounded JSON publication metadata required') from None
    info = validate_bundle(root, manifest)
    require(type(applying) is bool, 'Explicit publication selection required')
    if not applying:
        return info
    if _test_transport:
        require(os.environ.get('DEPLOYMENT_ENV') == 'test', 'Synthetic publication transport requires test environment')
    else:
        require(isinstance(store, BoundedGcsStore) and store.bucket.name == BUCKET and store.prefix == '',
            'Explicit authorized bounded transport for the exact beta bucket required')
    require(all(callable(getattr(store, method, None)) for method in ('read', 'create', 'replace')),
        'Explicit generation-conditional publication transport required')
    _same_base(_read_control(store), manifest)
    created = reused = 0
    for entry in [*manifest['files'], manifest['activation']]:
        maximum = MAX_BYTES if '/objects/' in entry['object_key'] else MAX_MANIFEST_BYTES
        data = _read(Path(root), entry, maximum)
        try:
            generation = _write_once(store, entry['object_key'], data, 0,
                test_transport=_test_transport)
        except SnapshotConflict:
            generation = None
            reused += 1
        except Exception:
            raise AppendPublicationUncertain('Immutable upload acknowledgement unavailable; inspect exact key before retry') from None
        else:
            require(type(generation) is int and generation > 0, 'Immutable create generation acknowledgement required')
            created += 1
        observed = store.read(entry['object_key'], max_bytes=len(data))
        require(isinstance(observed, StoredObject) and type(observed.generation) is int and observed.generation > 0
            and observed.data == data and sha(observed.data) == entry['sha256']
            and (generation is None or observed.generation == generation),
            'Exact immutable generation/hash readback required; no object may be overwritten')
    # Concurrent C17 reference writes make this candidate stale rather than lost.
    _same_base(_read_control(store), manifest)
    new_data = _read(Path(root), manifest['new_control'], MAX_CONTROL_BYTES)
    try:
        generation = _write_once(store, CONTROL, new_data, manifest['base_control']['generation'],
            test_transport=_test_transport)
    except Exception:
        # Even a translated precondition error is reconciled conservatively:
        # only an exact current installation establishes a completed write.
        try:
            observed = _read_control(store)
        except Exception:
            raise AppendPublicationUncertain('Control may have committed; preserve receipts and inspect before retry') from None
        if observed.data != new_data or observed.generation == manifest['base_control']['generation']:
            raise AppendPublicationUncertain('Control may have committed; preserve receipts and inspect before retry') from None
        generation = observed.generation
    observed = _read_control(store)
    if (type(generation) is not int or generation <= 0
            or generation == manifest['base_control']['generation']
            or observed.generation != generation or observed.data != new_data):
        raise AppendPublicationUncertain('Control committed state is not exactly established; preserve receipts before recovery')
    return {**info, 'state':'append_publication_committed_and_verified', 'cloud_operations':True,
        'immutable_created':created, 'immutable_reused_exact':reused,
        'control_cas_committed':True, 'control_generation':observed.generation,
        'source_or_legacy_mutation':False, 'automatic_retries':False,
        'provider_write_retry_policy':'retry=None; one SDK mutation call per selected key'}
