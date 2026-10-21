"""C23 consumes real C22 synthetic services; approved Python remains inert."""
from copy import deepcopy
from dataclasses import FrozenInstanceError
import hashlib
import json
import uuid

import pytest
from sqlalchemy import create_engine, event, select

from db.app_models import AppBase, ResearchExperimentReservation
from orchestration.experiment_sandbox.contracts import (
    SandboxError, VerifiedEnvelope, verify_execution_envelope,
)
from schema.research_experiments import content_sha256
from tests.research_experiment_support import make_experiment_fixture


@pytest.fixture(scope='module')
def approved_envelope(tmp_path_factory):
    directory = tmp_path_factory.mktemp('c23-contract')
    patch = pytest.MonkeyPatch()
    for name in ('ENABLE_V1_CATALOGUE', 'ENABLE_V1_INVESTIGATIONS'):
        patch.setenv(name, 'true')
    engine = create_engine('sqlite+pysqlite:///' + str(directory / 'private.sqlite'))
    @event.listens_for(engine, 'connect')
    def keys(connection, _):
        connection.execute('PRAGMA foreign_keys=ON')
    AppBase.metadata.create_all(engine)
    fixture = make_experiment_fixture(engine, directory)
    sentinel = directory / 'C23-MUST-NOT-EXECUTE'
    request = fixture.request()
    request['proposal']['python_code'] = f'from pathlib import Path\nPath({str(sentinel)!r}).write_text("bad")\n'
    first = fixture.service.invoke('create', request, fixture.user)['experiment']
    approved = fixture.service.invoke('approve', fixture.decision(first), fixture.user)['experiment']
    dispatched = fixture.service.invoke('dispatch', fixture.decision(approved), fixture.user)['experiment']
    reservation = dispatched['dispatch']['reservation_id']
    envelope = fixture.service.load_execution_envelope(reservation, user=fixture.user)
    with fixture.factory() as session:
        expected = session.scalar(select(ResearchExperimentReservation.envelope_sha256).where(
            ResearchExperimentReservation.id == uuid.UUID(reservation)))
    registry = {fixture.environment.identity_sha256: fixture.environment.model_dump(mode='json')}
    yield envelope, expected, registry, sentinel, fixture
    engine.dispose()
    patch.undo()


def verify(raw, approved_envelope, *, expected=None, registry=None):
    _, actual, environments, _, _ = approved_envelope
    return verify_execution_envelope(raw, expected_envelope_sha256=actual if expected is None else expected,
                                     environments=environments if registry is None else registry)


def test_real_retained_reservation_exact_bytes_no_execution(approved_envelope):
    raw, expected, _, sentinel, _ = approved_envelope
    parsed = verify(raw, approved_envelope)
    assert parsed.envelope_sha256 == expected == content_sha256(raw['metadata'])
    assert dict(parsed.files) == dict(raw['files'])
    assert parsed.code == raw['metadata']['proposal']['python_code'].encode()
    assert parsed.input_size_bytes <= parsed.resources['max_input_bytes']
    assert parsed.metadata['execution_performed'] is False
    assert parsed.environment['kind'] == 'c22-fake' and parsed.environment['test_only'] is True
    assert not sentinel.exists()


def test_detached_metadata_and_mapping_are_immutable(approved_envelope):
    raw, _, _, _, _ = approved_envelope
    copied = {'metadata': deepcopy(raw['metadata']), 'files': dict(raw['files'])}
    parsed = verify(copied, approved_envelope)
    original = parsed.metadata
    copied['metadata']['proposal']['question'] = 'mutated caller'
    copied['files'].clear()
    parsed.metadata['proposal']['question'] = 'mutated accessor'
    assert parsed.metadata == original and parsed.files
    with pytest.raises(TypeError):
        parsed.files['extra.json'] = b'{}'
    with pytest.raises(FrozenInstanceError):
        parsed.envelope_sha256 = '0' * 64
    with pytest.raises(TypeError):
        VerifiedEnvelope()


@pytest.mark.parametrize('field', [
    'site_id', 'experiment_id', 'proposal_revision_id', 'owner_user_id',
    'reservation_id', 'approval_id', 'binding', 'proposal', 'environment',
    'hashes', 'manifest', 'authority', 'scientific_approval', 'execution_performed',
])
def test_retained_reservation_rejects_any_metadata_tamper(approved_envelope, field):
    raw, _, _, _, _ = approved_envelope
    changed = {'metadata': deepcopy(raw['metadata']), 'files': dict(raw['files'])}
    changed['metadata'][field] = None
    with pytest.raises(SandboxError, match='sandbox_integrity'):
        verify(changed, approved_envelope)


@pytest.mark.parametrize('change', ['missing', 'extra', 'bytes', 'bytearray', 'path'])
def test_frozen_file_set_and_exact_bytes_are_bound(approved_envelope, change):
    raw, _, _, _, _ = approved_envelope
    files = dict(raw['files'])
    name = next(iter(files))
    if change == 'missing':
        del files[name]
    elif change == 'extra':
        files['extra.json'] = b'{}'
    elif change == 'bytes':
        files[name] += b' '
    elif change == 'bytearray':
        files[name] = bytearray(files[name])
    else:
        files['../escape.json'] = files.pop(name)
    with pytest.raises(SandboxError):
        verify({'metadata': deepcopy(raw['metadata']), 'files': files}, approved_envelope)


@pytest.mark.parametrize('change', ['code', 'resources', 'environment', 'cohort', 'manifest_binding', 'seed', 'bool'])
def test_internal_binding_rejects_even_resigned_outer_metadata(approved_envelope, change):
    raw, _, _, _, _ = approved_envelope
    metadata = deepcopy(raw['metadata'])
    if change == 'code':
        metadata['proposal']['python_code'] = 'print("changed")\n'
    elif change == 'resources':
        metadata['proposal']['resources']['wall_seconds'] = 1
    elif change == 'environment':
        metadata['proposal']['environment_id'] = '0' * 64
    elif change == 'cohort':
        metadata['proposal']['cohort']['selections'][0]['columns'] = ['wrong']
    elif change == 'manifest_binding':
        metadata['manifest']['binding']['revision_id'] = str(uuid.uuid4())
        metadata['hashes']['input_manifest_sha256'] = content_sha256(metadata['manifest'])
    elif change == 'seed':
        metadata['proposal']['seeds']['numpy'] += 1
    else:
        metadata['execution_performed'] = 0
    with pytest.raises(SandboxError):
        verify({'metadata': metadata, 'files': dict(raw['files'])}, approved_envelope,
               expected=content_sha256(metadata))


def test_registry_required_and_fake_environment_cannot_upgrade(approved_envelope):
    raw, _, registry, _, _ = approved_envelope
    with pytest.raises(SandboxError):
        verify(raw, approved_envelope, registry={})
    changed = deepcopy(registry)
    identity = next(iter(changed))
    changed[identity]['kind'] = 'linux-gvisor'
    with pytest.raises(SandboxError):
        verify(raw, approved_envelope, registry=changed)


def test_identity_stable_and_fresh_access_is_a_separate_gate(approved_envelope):
    raw, _, _, _, fixture = approved_envelope
    parsed = verify(raw, approved_envelope)
    assert parsed.job_id == verify(raw, approved_envelope).job_id
    assert len(parsed.job_id) == 52 and parsed.job_id.startswith('c23-')
    # The trusted service, not pure checksum validation, owns current admission.
    fixture.state['dispatch_enabled'] = False
    try:
        with pytest.raises(Exception, match='unavailable'):
            fixture.service.load_execution_envelope(raw['metadata']['reservation_id'], user=fixture.user)
        assert verify(raw, approved_envelope).envelope_sha256 == parsed.envelope_sha256
    finally:
        fixture.state['dispatch_enabled'] = True


def test_machine_int64_bytes_preserved_without_browser_number_conversion(approved_envelope):
    raw, _, _, _, _ = approved_envelope
    metadata = deepcopy(raw['metadata'])
    files = dict(raw['files'])
    name = next(item['name'] for item in metadata['manifest']['files'] if item['kind'] == 'machine_table')
    machine = json.loads(files[name])
    # Deliberately private bytes; no preview conversion or numerical execution.
    machine['c23_private_integer_probe'] = 9223372036854775807
    exact = json.dumps(machine, ensure_ascii=False, separators=(',', ':')).encode()
    files[name] = exact
    descriptor = next(item for item in metadata['manifest']['files'] if item['name'] == name)
    descriptor.update(sha256=hashlib.sha256(exact).hexdigest(), size_bytes=len(exact))
    metadata['hashes']['input_manifest_sha256'] = content_sha256(metadata['manifest'])
    value = verify({'metadata': metadata, 'files': files}, approved_envelope, expected=content_sha256(metadata))
    assert value.files[name] == exact and b'9223372036854775807' in value.files[name]
    # This pure synthetic reconstruction does not claim the altered bytes were
    # approved by the retained service; production admission must bind its hash.


@pytest.mark.parametrize('payload', [None, {}, {'metadata': {}}, {'metadata': {}, 'files': {}, 'command': 'python'}])
def test_no_arbitrary_transport_or_runtime_overrides(approved_envelope, payload):
    with pytest.raises(SandboxError):
        verify(payload, approved_envelope)


def test_input_budget_includes_approved_code_and_manifest(approved_envelope):
    raw, _, _, _, _ = approved_envelope
    metadata = deepcopy(raw['metadata'])
    files = dict(raw['files'])
    # Solve the small decimal-length dependency while binding every inner hash.
    # The manifest+files fit exactly; stored code must still be counted.
    from schema.context_catalogue import canonical_json
    for _ in range(5):
        limit = sum(map(len, files.values())) + len(canonical_json(metadata['manifest']).encode())
        metadata['proposal']['resources']['max_input_bytes'] = limit
        metadata['manifest']['max_input_bytes'] = limit
        metadata['hashes']['resources_sha256'] = content_sha256(metadata['proposal']['resources'])
        metadata['hashes']['proposal_sha256'] = content_sha256(metadata['proposal'])
        metadata['manifest']['proposal_sha256'] = metadata['hashes']['proposal_sha256']
        metadata['hashes']['input_manifest_sha256'] = content_sha256(metadata['manifest'])
    with pytest.raises(SandboxError, match='sandbox_input_limit'):
        verify({'metadata': metadata, 'files': files}, approved_envelope, expected=content_sha256(metadata))
