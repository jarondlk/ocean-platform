"""Read-only C23 candidates over actual retained synthetic C22 Linux approvals."""
from contextlib import contextmanager
from copy import copy, deepcopy
from dataclasses import FrozenInstanceError
import hashlib
import json
from types import SimpleNamespace
import uuid

import pytest
from sqlalchemy import create_engine, event, select, text
from sqlalchemy.orm import sessionmaker

from db.app_models import (
    AppBase, ResearchExperimentApproval, ResearchExperimentInputBlob,
    ResearchExperimentOutbox, ResearchExperimentReservation, ResearchExperimentRevisionFile,
)
from orchestration.experiment_sandbox.operator_inspection import (
    ApprovedCandidate, C23OperatorInspection, OperatorInspectionConfig,
)
from orchestration.research_experiments import ResearchExperimentError
from schema.context_catalogue import canonical_json
from schema.research_experiments import EnvironmentDescriptor, content_sha256
from tests.research_experiment_support import make_experiment_fixture


@pytest.fixture(scope='module')
def operator_store(tmp_path_factory):
    directory = tmp_path_factory.mktemp('c23-inspection')
    patch = pytest.MonkeyPatch()
    for name in ('ENABLE_V1_CATALOGUE', 'ENABLE_V1_INVESTIGATIONS'):
        patch.setenv(name, 'true')
    engine = create_engine('sqlite+pysqlite:///' + str(directory / 'operator.sqlite'))

    @event.listens_for(engine, 'connect')
    def foreign_keys(connection, _):
        connection.execute('PRAGMA foreign_keys=ON')

    AppBase.metadata.create_all(engine)
    fixture = make_experiment_fixture(engine, directory)
    fake = fixture.environment
    # Explicit software fixture identity, not runtime acceptance or production
    # image eligibility. This module never materializes or launches the image.
    fixture.environment = EnvironmentDescriptor(kind='linux-gvisor', test_only=False,
        python_version='3.12.15', image_digest='sha256:' + 'a' * 64,
        lockfile_sha256='b' * 64,
        packages={name: '1.0.0' for name in ('numpy', 'pandas', 'pyarrow', 'scipy', 'statsmodels', 'matplotlib')},
        description='Synthetic operator inspection descriptor only; no runtime acceptance')
    fixture.service.environments[fixture.environment.identity_sha256] = fixture.environment.model_dump(mode='json')
    yield SimpleNamespace(fixture=fixture, engine=engine, directory=directory, fake=fake)
    engine.dispose()
    patch.undo()


def config_for(fixture, **changes):
    options = {'site_id': fixture.service.site_id, 'session_factory': fixture.factory,
        'environments': {fixture.environment.identity_sha256: fixture.environment},
        'store_scope': 'isolated-unmounted-operator'}
    options.update(changes)
    return OperatorInspectionConfig(**options)


@pytest.fixture
def case(operator_store):
    fixture = operator_store.fixture
    fixture.state.update(enabled=True, dispatch_enabled=True)
    for denied in fixture.retained.policy.values():
        denied.clear()
    request = fixture.request()
    sentinel = operator_store.directory / ('MUST-NOT-EXECUTE-' + str(uuid.uuid4()))
    request['proposal']['python_code'] = f'from pathlib import Path\nPath({str(sentinel)!r}).write_bytes(b"bad")\n'
    initial = fixture.service.invoke('create', request, fixture.user)['experiment']
    approval_request = fixture.decision(initial)
    approved = fixture.service.invoke('approve', approval_request, fixture.user)['experiment']
    inspection = {key: value for key, value in fixture.decision(approved).items() if key != 'idempotency_key'}
    state = {'enabled': True}
    bridge = C23OperatorInspection(service=fixture.service,
        config=config_for(fixture, enabled=lambda: state['enabled']))
    with fixture.factory() as session:
        blobs = [(row.user_id.hex, row.sha256, bytes(row.content))
            for row in session.scalars(select(ResearchExperimentInputBlob))]
    yield SimpleNamespace(fixture=fixture, engine=operator_store.engine, bridge=bridge,
        request=inspection, approval_request=approval_request, experiment=approved,
        sentinel=sentinel, state=state, store=operator_store)
    with fixture.factory.begin() as session:
        for owner, identity, content in blobs:
            session.execute(text('UPDATE research_experiment_input_blob SET content=:raw WHERE user_id=:owner AND sha256=:hash'),
                {'raw': content, 'owner': owner, 'hash': identity})


def inspect(case, request=None, *, owner=None):
    return case.bridge.inspect_approved(case.request if request is None else request,
        current_owner=case.fixture.user if owner is None else owner)


def dump(engine):
    connection = engine.raw_connection()
    try:
        return tuple(connection.driver_connection.iterdump())
    finally:
        connection.close()


@contextmanager
def no_writes(case):
    before = dump(case.engine)
    mutations = []

    def observe(_, __, statement, *args):
        if statement.lstrip().split()[0].upper() in {'INSERT', 'UPDATE', 'DELETE', 'CREATE', 'DROP', 'ALTER', 'REPLACE'}:
            mutations.append(statement)

    event.listen(case.engine, 'before_cursor_execute', observe)
    try:
        yield
    finally:
        event.remove(case.engine, 'before_cursor_execute', observe)
        assert mutations == []
        assert dump(case.engine) == before
        assert not case.sentinel.exists()


def test_exact_retained_approval_bytes_and_explicit_non_authority(case):
    with no_writes(case):
        candidate = inspect(case)
        assert inspect(case) == candidate
    fixture = case.fixture
    with fixture.factory() as session:
        approval = session.scalar(select(ResearchExperimentApproval).where(
            ResearchExperimentApproval.revision_id == uuid.UUID(candidate.proposal_revision_id)))
        assert candidate.approval_id == str(approval.id)
        assert candidate.approval_request_sha256 == approval.request_sha256
        assert candidate.approval_request_bytes == approval.request_json.encode()
        assert json.loads(candidate.approval_request_bytes) == case.approval_request
        assert session.scalar(select(ResearchExperimentReservation).where(
            ResearchExperimentReservation.revision_id == approval.revision_id)) is None
        assert session.scalar(select(ResearchExperimentOutbox)) is None
    assert candidate.site_id == fixture.service.site_id
    assert candidate.owner_user_id == str(fixture.user.id)
    assert candidate.experiment_id == case.experiment['id']
    assert candidate.proposal_version == case.experiment['version']
    assert candidate.proposal_revision_id == case.experiment['proposal_revision_id']
    assert candidate.environment == case.experiment['environment']
    assert candidate.proposal == case.experiment['proposal']
    assert candidate.manifest == case.experiment['manifest']
    assert candidate.source_sha256 == content_sha256(candidate.manifest['sources'])
    assert candidate.hashes.proposal_sha256 == hashlib.sha256(candidate.proposal_bytes).hexdigest()
    assert candidate.hashes.code_sha256 == hashlib.sha256(candidate.proposal['python_code'].encode()).hexdigest()
    assert candidate.hashes.input_manifest_sha256 == hashlib.sha256(candidate.manifest_bytes).hexdigest()
    assert candidate.hashes.environment_sha256 == hashlib.sha256(candidate.environment_bytes).hexdigest()
    assert candidate.hashes.resources_sha256 == content_sha256(candidate.proposal['resources'])
    assert candidate.files
    assert candidate.inspection_only is True
    assert candidate.execution_authorized is candidate.capacity_reserved is candidate.execution_performed is False
    assert candidate.authority == 'experimental'
    assert candidate.scientific_approval == 'not_independently_verified'
    assert not any(hasattr(candidate, name) for name in ('reservation_id', 'envelope_sha256', 'job_id', 'start_permit'))
    assert fixture.executor.deliveries == []


def test_candidate_detaches_every_mutable_accessor_and_has_no_public_constructor(case):
    candidate = inspect(case)
    original = candidate.proposal_bytes
    candidate.proposal['python_code'] = 'print("changed")'
    candidate.environment['packages'].clear()
    candidate.manifest['sources'].clear()
    case.request['expected_hashes'].clear()
    assert candidate.proposal_bytes == original
    assert candidate.environment['packages'] and candidate.manifest['sources']
    with pytest.raises(TypeError):
        candidate.files['extra'] = b'bad'
    with pytest.raises(FrozenInstanceError):
        candidate.hashes.code_sha256 = 'c' * 64
    with pytest.raises(FrozenInstanceError):
        candidate.execution_authorized = True
    with pytest.raises(TypeError):
        ApprovedCandidate()


def test_configuration_is_default_off_and_binds_exact_store(case):
    disabled = C23OperatorInspection(service=case.fixture.service, config=config_for(case.fixture))
    with no_writes(case), pytest.raises(ResearchExperimentError, match='unavailable'):
        disabled.inspect_approved(case.request, current_owner=case.fixture.user)
    for changes in ({'site_id': 'v1:wrong-store'}, {'session_factory': lambda: None}):
        with pytest.raises(ValueError, match='exact configured'):
            C23OperatorInspection(service=case.fixture.service, config=config_for(case.fixture, **changes))
    with pytest.raises(ValueError, match='isolated unmounted'):
        config_for(case.fixture, store_scope='serving')
    with pytest.raises(ValueError, match='isolated unmounted'):
        config_for(case.fixture, enabled=True)


def test_config_registry_is_detached_and_fake_descriptors_cannot_be_trusted(case):
    environment = case.fixture.environment
    registry = {environment.identity_sha256: environment.model_dump(mode='json')}
    config = config_for(case.fixture, environments=registry, enabled=lambda: True)
    registry[environment.identity_sha256]['packages'].clear()
    bridge = C23OperatorInspection(service=case.fixture.service, config=config)
    assert bridge.inspect_approved(case.request, current_owner=case.fixture.user).environment['packages']
    fake = case.store.fake
    with pytest.raises(ValueError, match='trusted Linux'):
        config_for(case.fixture, environments={fake.identity_sha256: fake})
    with pytest.raises(ValueError, match='trusted Linux'):
        config_for(case.fixture, environments={'c' * 64: environment})


@pytest.mark.parametrize('field', ['exporter', 'session_factory'])
def test_final_enable_callback_cannot_rebind_equivalent_sources_or_store(case, field):
    service = case.fixture.service
    original = getattr(service, field)
    replacement = copy(service.exporter) if field == 'exporter' else sessionmaker(
        bind=case.engine, expire_on_commit=False)
    calls = 0

    def enabled():
        nonlocal calls
        calls += 1
        if calls == 3:
            # Equivalent source data and identical DB rows do not permit
            # replacement of the explicitly configured service dependencies.
            setattr(service, field, replacement)
        return True

    bridge = C23OperatorInspection(service=service, config=config_for(case.fixture, enabled=enabled))
    try:
        with no_writes(case), pytest.raises(ValueError, match='exact configured'):
            bridge.inspect_approved(case.request, current_owner=case.fixture.user)
        assert calls == 3
    finally:
        setattr(service, field, original)


@pytest.mark.parametrize('owner', ['other', 'admin'])
def test_other_owner_and_admin_cannot_inspect_private_approval(case, owner):
    with no_writes(case), pytest.raises(ResearchExperimentError) as failure:
        inspect(case, owner=getattr(case.fixture, owner))
    assert failure.value.code == 'not_found'


@pytest.mark.parametrize('payload', [True, False, {'approved': True}, {'envelope_sha256': 'a' * 64}])
def test_boolean_approval_or_new_hash_is_not_a_retained_request(case, payload):
    with no_writes(case), pytest.raises(ResearchExperimentError) as failure:
        inspect(case, payload)
    assert failure.value.code == 'invalid_request'


@pytest.mark.parametrize('field', ['expected_version', 'expected_proposal_revision_id',
    'snapshot_id', 'context_payload_sha256', 'proposal_sha256', 'code_sha256',
    'input_manifest_sha256', 'environment_sha256', 'resources_sha256'])
def test_all_current_request_heads_context_and_five_hashes_are_exact(case, field):
    request = deepcopy(case.request)
    if field.endswith('_sha256') and field in request['expected_hashes']:
        request['expected_hashes'][field] = 'c' * 64
    elif field == 'expected_version':
        request[field] += 1
    elif field == 'expected_proposal_revision_id':
        request[field] = str(uuid.uuid4())
    else:
        request[field] = 'c' * 64
    with no_writes(case), pytest.raises(ResearchExperimentError) as failure:
        inspect(case, request)
    assert failure.value.code == 'conflict'


def test_fake_dispatch_flag_does_not_enable_or_gate_read_only_inspection(case):
    case.fixture.state['dispatch_enabled'] = False
    with no_writes(case):
        assert inspect(case).execution_authorized is False
    with pytest.raises(ResearchExperimentError) as failure:
        case.fixture.service.invoke('dispatch', case.fixture.decision(case.experiment), case.fixture.user)
    assert failure.value.code == 'dispatch_unavailable'
    case.fixture.state['dispatch_enabled'] = True
    with no_writes(case), pytest.raises(ResearchExperimentError) as failure:
        case.fixture.service.invoke('dispatch', case.fixture.decision(case.experiment), case.fixture.user)
    assert failure.value.code == 'dispatch_unavailable'


def test_retained_fake_approval_cannot_be_promoted_by_operator_registry(case):
    request = case.fixture.request()
    request['proposal']['environment_id'] = case.store.fake.identity_sha256
    initial = case.fixture.service.invoke('create', request, case.fixture.user)['experiment']
    approved = case.fixture.service.invoke('approve', case.fixture.decision(initial), case.fixture.user)['experiment']
    request = {key: value for key, value in case.fixture.decision(approved).items() if key != 'idempotency_key'}
    with no_writes(case), pytest.raises(ResearchExperimentError) as failure:
        inspect(case, request)
    assert failure.value.code == 'environment_unavailable'


@pytest.mark.parametrize('mutation', ['missing', 'hash', 'request_binding', 'recomputed_request_hash'])
def test_retained_approval_is_required_and_request_integrity_is_independent(case, mutation):
    with case.fixture.factory.begin() as session:
        approval = session.scalar(select(ResearchExperimentApproval).where(
            ResearchExperimentApproval.revision_id == uuid.UUID(case.experiment['proposal_revision_id'])))
        identity = approval.id.hex
        if mutation == 'missing':
            session.execute(text('DELETE FROM research_experiment_approval WHERE id=:id'), {'id': identity})
        elif mutation == 'hash':
            session.execute(text('UPDATE research_experiment_approval SET request_sha256=:hash WHERE id=:id'),
                {'id': identity, 'hash': 'c' * 64})
        else:
            request = json.loads(approval.request_json)
            request['expected_hashes']['code_sha256'] = 'c' * 64
            raw = canonical_json(request)
            session.execute(text('UPDATE research_experiment_approval SET request_json=:raw, request_sha256=:hash WHERE id=:id'),
                {'id': identity, 'raw': raw, 'hash': content_sha256(request) if mutation == 'recomputed_request_hash' else approval.request_sha256})
    with no_writes(case), pytest.raises(ResearchExperimentError) as failure:
        inspect(case)
    assert failure.value.code in {'integrity_error', 'conflict'}


def callback_mutation(case, mutation):
    fixture = case.fixture
    if mutation == 'owner':
        with fixture.factory.begin() as session:
            session.execute(text('UPDATE app_user SET status=:status WHERE id=:id'),
                {'status': 'suspended', 'id': fixture.user.id.hex})
    elif mutation == 'proposal_head':
        proposal = deepcopy(case.experiment['proposal'])
        proposal['python_code'] += '# New retained revision requires a new approval.\n'
        fixture.service.invoke('revise', {**case.experiment['binding'],
            'experiment_id': case.experiment['id'], 'proposal': proposal,
            'expected_version': case.experiment['version'],
            'expected_proposal_revision_id': case.experiment['proposal_revision_id'],
            'idempotency_key': str(uuid.uuid4())}, fixture.user)
    elif mutation == 'context_head':
        fixture.investigations.invoke('context/change', {
            'investigation_id': case.experiment['binding']['investigation_id'],
            'expected_revision_id': case.experiment['binding']['context_revision_id'],
            'idempotency_key': str(uuid.uuid4()), 'change': {'op': 'attach', 'reference': {
                'kind': 'catalogue', 'id': fixture.retained.dataset_ids['ctd'],
                'snapshot_id': case.experiment['binding']['snapshot_id']}}}, fixture.user)
    elif mutation == 'source':
        fixture.retained.policy[case.experiment['binding']['snapshot_id']].add(fixture.retained.dataset_ids['ctd'])
    elif mutation == 'publication':
        fixture.exporter.publication_policy = None
    elif mutation == 'enabled':
        fixture.state['enabled'] = False
    elif mutation == 'operator_enabled':
        case.state['enabled'] = False
    elif mutation == 'environment':
        fixture.service.environments.pop(fixture.environment.identity_sha256)
    elif mutation == 'blob':
        with fixture.factory.begin() as session:
            reference = session.scalar(select(ResearchExperimentRevisionFile).where(
                ResearchExperimentRevisionFile.revision_id == uuid.UUID(case.experiment['proposal_revision_id'])))
            blob = session.get(ResearchExperimentInputBlob, (fixture.user.id, reference.sha256))
            session.execute(text('UPDATE research_experiment_input_blob SET content=:raw WHERE user_id=:owner AND sha256=:hash'),
                {'raw': b'x' * len(blob.content), 'owner': fixture.user.id.hex, 'hash': reference.sha256})


@pytest.mark.parametrize('phase', ['full', 'access'])
@pytest.mark.parametrize('mutation', ['owner', 'proposal_head', 'context_head', 'source',
    'publication', 'enabled', 'operator_enabled', 'environment', 'blob'])
def test_callback_time_revocation_and_mutation_never_return_candidate(case, monkeypatch, phase, mutation):
    fixture = case.fixture
    full = fixture.exporter.verify
    access = fixture.exporter.verify_access
    policy = fixture.exporter.publication_policy
    registry = deepcopy(fixture.service.environments)
    invoked = False
    in_full = False

    def verify_full(**kwargs):
        nonlocal invoked, in_full
        in_full = True
        try:
            full(**kwargs)
        finally:
            in_full = False
        if phase == 'full' and not invoked:
            invoked = True
            callback_mutation(case, mutation)

    def verify_access(**kwargs):
        nonlocal invoked
        if phase != 'access' or in_full or invoked:
            return access(**kwargs)
        invoked = True
        # A source decision must be current when checked; there is no atomic
        # transaction spanning future policy changes outside this DB. DB/flag
        # mutations after this callback returns are caught by the closing gate.
        if mutation in {'source', 'publication'}:
            callback_mutation(case, mutation)
            return access(**kwargs)
        access(**kwargs)
        callback_mutation(case, mutation)

    monkeypatch.setattr(fixture.exporter, 'verify', verify_full)
    monkeypatch.setattr(fixture.exporter, 'verify_access', verify_access)
    try:
        with pytest.raises(ResearchExperimentError):
            inspect(case)
        assert invoked and not case.sentinel.exists()
        with fixture.factory() as session:
            assert session.scalar(select(ResearchExperimentReservation)) is None
            assert session.scalar(select(ResearchExperimentOutbox)) is None
    finally:
        fixture.exporter.publication_policy = policy
        fixture.service.environments = registry
        with fixture.factory.begin() as session:
            session.execute(text('UPDATE app_user SET status=:status WHERE id=:id'),
                {'status': 'active', 'id': fixture.user.id.hex})


@pytest.mark.parametrize('mutation', ['source', 'publication', 'enabled', 'operator_enabled', 'environment', 'blob'])
def test_preexisting_revocation_or_byte_change_is_read_only_denial(case, mutation):
    fixture = case.fixture
    policy = fixture.exporter.publication_policy
    registry = deepcopy(fixture.service.environments)
    callback_mutation(case, mutation)
    try:
        with no_writes(case), pytest.raises(ResearchExperimentError):
            inspect(case)
    finally:
        fixture.exporter.publication_policy = policy
        fixture.service.environments = registry


def test_owner_is_required_as_current_user_not_boolean_or_id(case):
    for owner in (True, str(case.fixture.user.id), None):
        with no_writes(case), pytest.raises(ResearchExperimentError) as failure:
            case.bridge.inspect_approved(case.request, current_owner=owner)
        assert failure.value.code == 'authentication_required'
