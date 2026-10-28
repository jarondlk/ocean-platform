"""Host-safe native-boundary simulations; no real Linux termination acceptance.

Real SQLite/flock/journal references and Ed25519 are used. Kernel files, native
delete, read-only material/source checks and DB rows are explicitly simulated.
No runsc command, generated Python, cgroup, service, cloud or DB is launched.
"""
from copy import copy
from dataclasses import FrozenInstanceError
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import sys
import time
from types import ModuleType, SimpleNamespace
import uuid

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
import pytest

from orchestration.experiment_sandbox import physical_termination as module
from orchestration.experiment_sandbox.contracts import SandboxError
from orchestration.experiment_sandbox.execution_store import (
    C23ExecutionStore, ExecutionRolePolicy, ExecutionStoreConfig,
)
from orchestration.experiment_sandbox.journal import DurableExecutionJournal, DurableLease, _safe_sqlite_version
from orchestration.experiment_sandbox.linux_runtime import LinuxExecutionAdapter
from orchestration.experiment_sandbox.physical_termination import (
    HostTerminationObservation, LinuxTerminationIssuer, OriginalCgroupHandle, PhysicalIssuerConfig,
    cleanup_under_lease, open_original_cgroup,
)
from orchestration.experiment_sandbox.profile_execution import render_execution_profile
from orchestration.experiment_sandbox.proofs import (
    PinnedTerminationIssuer, TerminationVerifierRegistry, canonical_packet_bytes,
    issue_termination_packet, verify_termination_packet,
)
from schema.context_catalogue import canonical_json
from schema.experiment_execution import ClosedExecutionBinding, TerminationIssuerScope
from tests.test_experiment_sandbox_contracts import approved_envelope as _retained_fixture
from tests.test_experiment_sandbox_journal import BOOT, HOST
from tests.test_experiment_sandbox_profile_execution import layout as _profile_fixture

approved_envelope, layout = _retained_fixture, _profile_fixture
_ACTUAL_HOST_GUARD = module._host_guard
_ACTUAL_SOURCE_CHECK = module._source_files


def _loaded_source_fixture(directory, monkeypatch):
    root = directory.resolve()
    files = {}
    for relative in sorted(module.WORKER_FILES):
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b'Literal synthetic module provenance fixture; never imported.\n')
        files[relative] = _hash(path.read_bytes())
        if relative != 'sandbox/experiment/trusted_init.py':
            name = relative[:-3].replace('/', '.')
            loaded = ModuleType(name)
            loaded.__file__ = str(path)
            monkeypatch.setitem(sys.modules, name, loaded)
    return root, files


def test_loaded_source_check_requires_every_host_module_but_does_not_import_guest_or_optional_files(tmp_path, monkeypatch):
    root, files = _loaded_source_fixture(tmp_path, monkeypatch)
    files['orchestration/experiment_sandbox/optional_source.py'] = _hash(b'not loaded')
    calls = []
    assert module.require_loaded_source_provenance(root, files, check=lambda: calls.append(True)) is None
    assert len(calls) >= 2 * (len(module.WORKER_FILES) - 1)
    assert 'orchestration.experiment_sandbox.optional_source' not in sys.modules


@pytest.mark.parametrize('relative', sorted(module.WORKER_FILES - {'sandbox/experiment/trusted_init.py'}))
def test_each_required_host_module_must_be_loaded_from_the_configured_archive(tmp_path, monkeypatch, relative):
    root, files = _loaded_source_fixture(tmp_path, monkeypatch)
    name = relative[:-3].replace('/', '.')
    foreign = root / 'different-loaded-source.py'
    foreign.write_bytes(b'Synthetic foreign module fixture; never imported.\n')
    sys.modules[name].__file__ = str(foreign)
    with pytest.raises(SandboxError, match='source_policy'):
        module.require_loaded_source_provenance(root, files, check=lambda: None)


@pytest.mark.parametrize('change', ['missing', 'wrong_type', 'missing_origin', 'relative_origin'])
def test_loaded_source_check_refuses_missing_or_untyped_host_origins(tmp_path, monkeypatch, change):
    root, files = _loaded_source_fixture(tmp_path, monkeypatch)
    name = 'orchestration.experiment_sandbox.journal'
    if change == 'missing':
        monkeypatch.delitem(sys.modules, name)
    elif change == 'wrong_type':
        monkeypatch.setitem(sys.modules, name, SimpleNamespace(__file__=str(root / 'orchestration/experiment_sandbox/journal.py')))
    elif change == 'missing_origin':
        del sys.modules[name].__file__
    else:
        sys.modules[name].__file__ = 'orchestration/experiment_sandbox/journal.py'
    with pytest.raises(SandboxError, match='source_policy'):
        module.require_loaded_source_provenance(root, files, check=lambda: None)


@pytest.mark.parametrize('relative', ['orchestration/additional_loaded.py', 'additional_package/__init__.py'])
def test_additional_configured_loaded_modules_also_require_exact_source_origins(tmp_path, monkeypatch, relative):
    root, files = _loaded_source_fixture(tmp_path, monkeypatch)
    actual = root / relative
    actual.parent.mkdir(parents=True, exist_ok=True)
    actual.write_bytes(b'Additional configured source fixture; never imported.\n')
    files[relative] = _hash(actual.read_bytes())
    name = relative[:-3].replace('/', '.').removesuffix('.__init__')
    loaded = ModuleType(name)
    loaded.__file__ = str(actual)
    monkeypatch.setitem(sys.modules, name, loaded)
    module.require_loaded_source_provenance(root, files, check=lambda: None)
    loaded.__file__ = str(root / 'orchestration/experiment_sandbox/journal.py')
    with pytest.raises(SandboxError, match='source_policy'):
        module.require_loaded_source_provenance(root, files, check=lambda: None)


def test_loaded_source_check_propagates_actual_fence_loss_without_importing_or_granting_authority(tmp_path, monkeypatch):
    root, files = _loaded_source_fixture(tmp_path, monkeypatch)
    def lost():
        raise SandboxError('sandbox_stale_journal_lease')
    with pytest.raises(SandboxError, match='stale_journal_lease'):
        module.require_loaded_source_provenance(root, files, check=lost)


def _hash(value):
    return hashlib.sha256(value.encode() if type(value) is str else value).hexdigest()


def _json(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode()


@pytest.fixture
def physical(layout, tmp_path, monkeypatch):
    if not _safe_sqlite_version(sqlite3.sqlite_version_info):
        pytest.skip('Actual physical-observation tests require SQLite with the WAL-reset fix')
    envelope, options, _ = layout
    profile = render_execution_profile(envelope, **options)
    control = tmp_path / 'actual-journal'
    control.mkdir(mode=0o700)
    with DurableExecutionJournal(control.resolve(), host_id=HOST, host_boot_id=BOOT) as journal:
        adapter = object.__new__(LinuxExecutionAdapter)
        adapter.worker_root = Path(options['job_root']).parent
        adapter.runtime_directory = tmp_path / 'simulated-runtime'
        adapter._runtime_json = canonical_json(options['runtime_manifest'])
        adapter._helper_sha256 = _hash(Path(module.native.__file__).read_bytes())
        adapter.journal, adapter.cgroup_root = journal, tmp_path / 'simulated-cgroup2'
        adapter.clock = time.monotonic
        outer, _, _ = adapter._paths(envelope.job_id)
        outer.mkdir(mode=0o700, parents=True)
        for name, raw in {'cgroup.type': b'domain\n', 'cgroup.events': b'populated 0\nfrozen 0\n',
                          'cgroup.kill': b''}.items():
            (outer / name).write_bytes(raw)
        identity = (outer.stat().st_dev, outer.stat().st_ino)

        def host_boundary(a, e, p, lease):
            module._lease(a, e, p, lease)
            return a.journal.identity_reference(lease)

        def material_boundary(a, e, p, lease):
            module._lease(a, e, p, lease)
            return Path(options['job_root']), p.document, _hash(a._runtime_json)

        def delete_boundary(a, e, p, lease, handle, sidecapture):
            module._handle(handle, a, e, p, lease)
            command = {'argv': [str(a.runtime_directory / 'runsc'), *p.runtime_args,
                                'delete', '--force', e.job_id],
                'runtime_sha256': _hash(a._runtime_json),
                'runsc_sha256': json.loads(a._runtime_json)['files']['runsc']}
            return {'command': command, 'command_sha256': _hash(_json(command)),
                'exit_code': 0, 'pid': 123456, 'pipes_eof': True,
                'stdout_size_bytes': 0, 'stdout_sha256': _hash(b''),
                'stderr_size_bytes': 0, 'stderr_sha256': _hash(b''),
                'acknowledged_monotonic_ns': module._now()}

        monkeypatch.setattr(module, '_host_guard', host_boundary)
        monkeypatch.setattr(module, '_materials', material_boundary)
        monkeypatch.setattr(module, '_run_delete', delete_boundary)
        monkeypatch.setattr(module, '_source_files', lambda c, a, e, p, lease: module._lease(a, e, p, lease))
        with journal.claim(envelope.job_id, envelope.envelope_sha256) as lease:
            lease.append('prepared', {'profile_sha256': profile.profile_sha256,
                                     'runtime_sha256': _hash(adapter._runtime_json)})
            create = lease.append('create_intent', {'profile_sha256': profile.profile_sha256,
                                                   'cgroup_identity': list(identity)})
            ref = journal.identity_reference(lease)
            execution_id, start_id = str(uuid.uuid4()), str(uuid.uuid4())
            row = {'state': 'closed', 'fence': 3, 'start_event_id': start_id,
                'current_event_id': str(uuid.uuid4()), 'start_id': start_id, 'start_fence': 2,
                'start_boot_id': BOOT, 'start_journal_id': ref.journal_id,
                'start_journal_epoch': lease.epoch, 'start_profile_sha256': profile.profile_sha256,
                'preceding_journal_sha256': create.sha256}
            payload = {'version': module.START_INTENT_VERSION, 'execution_id': execution_id,
                'reservation_id': envelope.metadata['reservation_id'], 'start_id': start_id,
                'start_event_id': start_id, 'start_fence': 2, 'journal_id': ref.journal_id,
                'journal_epoch': lease.epoch, 'worker_id': HOST, 'host_boot_id': BOOT,
                'job_id': envelope.job_id, 'envelope_sha256': envelope.envelope_sha256,
                'profile_sha256': profile.profile_sha256, 'preceding_journal_sha256': create.sha256}
            lease.append('start_intent', payload)
            handle = open_original_cgroup(adapter, envelope, profile, lease, identity)
            case = SimpleNamespace(adapter=adapter, envelope=envelope, profile=profile,
                journal=journal, lease=lease, handle=handle, row=row, execution_id=execution_id,
                outer=outer, tmp=tmp_path, observation=None, binding=None)
            try:
                yield case
            finally:
                handle.close()


def _cleanup(case):
    case.observation = cleanup_under_lease(case.adapter, case.envelope, case.profile, case.lease, case.handle)
    return case.observation


def _issuer(case, monkeypatch, *, enabled=True):
    observation = case.observation or _cleanup(case)
    case.lease.finish({'version': 'synthetic-host-safe-result-v1', 'analysis': 'not-run',
                       'audit': observation.audit_record})
    terminal = case.journal.terminal_reference(case.lease)
    files = {name: _hash('simulated source:' + name) for name in module.WORKER_FILES}
    files['orchestration/experiment_sandbox/linux_runtime.py'] = case.adapter._helper_sha256
    files['sandbox/experiment/trusted_init.py'] = case.profile.document['trusted_init']['sha256']
    profile_files = {name: files[name] for name in module.PROFILE_FILES}
    worker_hash = _hash(_json({'version': module.WORKER_POLICY_VERSION, 'files': files}))
    profile_hash = _hash(_json({'version': module.PROFILE_POLICY_VERSION, 'files': profile_files}))
    scope = {'site_id': case.envelope.metadata['site_id'], 'worker_id': HOST,
        'source_policy_sha256': '0' * 64, 'worker_source_sha256': worker_hash,
        'environment_sha256': case.envelope.metadata['hashes']['environment_sha256'],
        'image_digest': case.envelope.environment['image_digest'],
        'runtime_sha256': _hash(case.adapter._runtime_json), 'profile_policy_sha256': profile_hash,
        'trusted_init_sha256': case.profile.document['trusted_init']['sha256'],
        'adapter_source_sha256': case.adapter._helper_sha256}
    policy = _json({'version': module.SOURCE_POLICY_VERSION, 'trust_scope': 'synthetic-software-test',
        **{name: value for name, value in scope.items() if name not in {'site_id', 'source_policy_sha256'}}})
    scope['source_policy_sha256'] = _hash(policy)
    scope = TerminationIssuerScope.model_validate(scope)
    # Synthetic ephemeral key only; actual native and DB acceptance is not run.
    key = Ed25519PrivateKey.generate()
    pinned = PinnedTerminationIssuer(issuer_id='synthetic-native-boundary-test', key_id='ephemeral-test-key',
        trust_scope='synthetic-software-test', public_key=key.public_key().public_bytes_raw(), scope=scope)
    registry = TerminationVerifierRegistry(issuers=[pinned], trust_scope='synthetic-software-test', enabled=True)
    store = C23ExecutionStore(config=ExecutionStoreConfig(site_id=scope.site_id, database_name='ocean_c23_no_connection',
        schema='c23_no_connection', controller_session_factory=lambda: None, recorder_session_factory=lambda: None,
        roles=ExecutionRolePolicy('synthetic_serving', 'synthetic_controller', 'synthetic_verifier', 'synthetic_owner'),
        verifier_registry=registry, store_scope='isolated-unmounted-operator'))
    metadata = case.envelope.metadata
    binding = {**scope.model_dump(), **{name: metadata[name] for name in (
        'site_id', 'reservation_id', 'owner_user_id', 'experiment_id', 'proposal_revision_id', 'approval_id')},
        'execution_id': case.execution_id, 'approval_request_sha256': _hash('synthetic-approved-request'),
        'execution_request_sha256': _hash('synthetic-execution-request'),
        'envelope_sha256': case.envelope.envelope_sha256, 'closed_fence': 3,
        'job_id': case.envelope.job_id, 'host_boot_id': BOOT, 'journal_id': terminal.journal_id,
        'journal_epoch': case.lease.epoch, 'source_sha256': _hash('frozen-c22-source'),
        'profile_sha256': case.profile.profile_sha256}
    case.binding = ClosedExecutionBinding.model_validate(binding)
    case.row.update(terminal_sequence=terminal.terminal_sequence,
        terminal_head_sha256=terminal.terminal_head_sha256, terminal_result_sha256=terminal.terminal_result_sha256)
    monkeypatch.setattr(module, '_closed_rows', lambda s, e: (case.binding, dict(case.row)))
    source, evidence = case.tmp / 'synthetic-source-policy', case.tmp / 'issuer-evidence'
    source.mkdir(mode=0o700)
    evidence.mkdir(mode=0o700)
    for name in files:
        raw = ('simulated source:' + name).encode()
        if name == 'orchestration/experiment_sandbox/linux_runtime.py':
            raw = Path(module.native.__file__).read_bytes()
        elif name == 'sandbox/experiment/trusted_init.py':
            raw = Path(name).read_bytes()
        path = source / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
        path.chmod(0o400)
        assert _hash(raw) == files[name]
    args = dict(store=store, registry=registry, scope=scope,
        issuer_id=pinned.issuer_id, key_id=pinned.key_id, private_key=key,
        source_root=source.resolve(), evidence_root=evidence.resolve(), worker_source_files=files,
        profile_source_files=profile_files, source_policy_bytes=policy, enabled=enabled)
    config = PhysicalIssuerConfig(**args)
    return LinuxTerminationIssuer(config=config), args


def _issue(case, issuer):
    return issuer.issue_under_lease(case.execution_id, case.adapter, case.envelope,
        case.profile, case.lease, case.observation)


def test_native_simulation_keeps_actual_lease_and_create_chain_but_no_physical_acceptance(physical):
    case = physical
    observation = _cleanup(case)
    assert type(observation) is HostTerminationObservation
    assert observation.cleanup_intent_sequence < observation.termination_sequence
    assert (case.outer / 'cgroup.kill').read_bytes() == b'1\n'
    assert case.handle._observation is observation
    assert observation._native_path.read_bytes() == observation._native_bytes
    assert observation.native_observation_sha256 == _hash(observation._native_bytes)
    audit = observation.audit_record
    assert audit['reservation_release_authorized'] is False
    audit['native_observation']['populated'] = 1
    assert observation.audit_record['native_observation']['populated'] == 0
    assert case.lease.snapshot().terminal is False
    with pytest.raises(SandboxError, match='cleanup_replay'):
        _cleanup(case)


def test_host_safe_issuer_authenticates_exact_terminal_binding_and_byte_retry_only(physical, monkeypatch):
    issuer, _ = _issuer(physical, monkeypatch)
    signed = _issue(physical, issuer)
    raw = canonical_packet_bytes(signed)
    verified = verify_termination_packet(raw, expected=physical.binding, registry=issuer.config.registry)
    assert verified.claims.journal.terminal_result_sha256 == physical.row['terminal_result_sha256']
    assert verified.claims.kernel.raw_observation_sha256 == physical.observation.native_observation_sha256
    assert verified.reservation_release_authorized is False
    assert verified.scientific_approval == 'not_independently_verified'
    assert canonical_packet_bytes(_issue(physical, issuer)) == raw
    assert len(list(issuer.config.evidence_root.iterdir())) == 2
    assert physical.lease.snapshot().events[-1].kind == 'finished'
    with pytest.raises(SandboxError, match='termination_issuer_unavailable'):
        issue_termination_packet(lease=physical.lease, binding=physical.binding, issuer=issuer)


@pytest.mark.parametrize('kind', [OriginalCgroupHandle, HostTerminationObservation])
def test_observation_and_original_handle_constructors_are_private(kind):
    with pytest.raises(TypeError):
        kind()


@pytest.mark.parametrize('fake', [None, True, {}, {'populated': 0, 'runtime_delete_acknowledged': True},
    object.__new__(HostTerminationObservation)])
def test_no_json_boolean_result_or_forged_observation_can_reach_issuer(physical, monkeypatch, fake):
    issuer, _ = _issuer(physical, monkeypatch)
    with pytest.raises(SandboxError):
        issuer.issue_under_lease(physical.execution_id, physical.adapter, physical.envelope,
            physical.profile, physical.lease, fake)


@pytest.mark.parametrize('fake', [None, True, {}, object.__new__(DurableLease)])
def test_actual_registered_lease_required_before_native_effect(physical, fake):
    before = (physical.outer / 'cgroup.kill').read_bytes()
    with pytest.raises(SandboxError):
        cleanup_under_lease(physical.adapter, physical.envelope, physical.profile, fake, physical.handle)
    assert (physical.outer / 'cgroup.kill').read_bytes() == before


def test_copied_or_closed_handle_cannot_supply_native_authority(physical):
    with pytest.raises(SandboxError):
        cleanup_under_lease(physical.adapter, physical.envelope, physical.profile, physical.lease, copy(physical.handle))
    physical.handle.close()
    with pytest.raises(SandboxError):
        _cleanup(physical)


@pytest.mark.parametrize('raw', [b'populated 1\n', b'populated 0\npopulated 0\n',
    b'populated false\n', b'frozen 0\n', b'populated 0\nother 0\n', b'\xff'])
def test_missing_duplicate_uncertain_or_malformed_kernel_empty_observation_denied(physical, monkeypatch, raw):
    (physical.outer / 'cgroup.events').write_bytes(raw)
    if raw == b'populated 1\n':
        monkeypatch.setattr(module.time, 'monotonic', lambda: 10**30)
        with pytest.raises(SandboxError):
            module._empty(physical.handle, 0)
    else:
        with pytest.raises(SandboxError):
            _cleanup(physical)
    assert physical.handle._observation is None


def test_original_cgroup_replacement_is_not_absence_or_empty_proof(physical):
    physical.outer.rename(physical.outer.with_name('original-cgroup'))
    physical.outer.mkdir(mode=0o700)
    with pytest.raises(SandboxError, match='cgroup_identity'):
        _cleanup(physical)


def test_original_fd_loss_duplicate_handle_and_mutable_adapter_methods_are_denied(physical):
    with pytest.raises(SandboxError, match='already_open'):
        open_original_cgroup(physical.adapter, physical.envelope, physical.profile, physical.lease,
                             physical.handle._identity)
    physical.adapter._spawn = lambda *args, **kwargs: True
    with pytest.raises(SandboxError, match='adapter_changed'):
        _cleanup(physical)
    del physical.adapter._spawn
    os.close(physical.handle._fd)
    with pytest.raises(SandboxError, match='cgroup_identity'):
        _cleanup(physical)


def test_even_combined_handle_path_fd_identity_substitution_cannot_retarget_cleanup(physical):
    case = physical
    with pytest.raises(FrozenInstanceError):
        case.handle._identity = (1, 2)
    other = case.outer.with_name('unrelated-owned-domain')
    other.mkdir(mode=0o700)
    for name, raw in {'cgroup.type': b'domain\n', 'cgroup.events': b'populated 0\n',
                      'cgroup.kill': b''}.items():
        (other / name).write_bytes(raw)
    descriptor = os.open(other, os.O_RDONLY | os.O_DIRECTORY)
    try:
        # Deliberately bypass frozen fields to exercise the independent registry
        # and durable create-intent pins, not just Python assignment protection.
        object.__setattr__(case.handle, '_path', other)
        object.__setattr__(case.handle, '_fd', descriptor)
        object.__setattr__(case.handle, '_identity', (other.stat().st_dev, other.stat().st_ino))
        with pytest.raises(SandboxError):
            _cleanup(case)
        assert (case.outer / 'cgroup.kill').read_bytes() == b''
        assert (other / 'cgroup.kill').read_bytes() == b''
        case.handle.close()  # Closes the independently registered original FD.
        os.fstat(descriptor)  # Never closes the injected unrelated FD.
    finally:
        os.close(descriptor)


def test_unprotected_cgroup_parent_is_refused_before_a_native_write(physical):
    physical.outer.parent.chmod(0o777)
    with pytest.raises(SandboxError, match='cgroup_identity'):
        _cleanup(physical)
    assert (physical.outer / 'cgroup.kill').read_bytes() == b''


@pytest.mark.parametrize('target', ['adapter', 'journal'])
def test_physical_timestamps_cannot_use_supplied_fake_clocks(physical, target):
    if target == 'adapter':
        physical.adapter.clock = lambda: 0
    else:
        physical.journal._clock_ns = lambda: 0
    with pytest.raises(SandboxError, match='physical_clock'):
        _cleanup(physical)
    assert (physical.outer / 'cgroup.kill').read_bytes() == b''


@pytest.mark.parametrize('method', ['require_current', 'identity_reference', 'terminal_reference', '_connection', 'append'])
def test_instance_journal_callbacks_cannot_substitute_for_actual_held_lease(physical, method):
    setattr(physical.journal, method, lambda *args, **kwargs: True)
    try:
        with pytest.raises(SandboxError, match='journal_changed'):
            _cleanup(physical)
        assert (physical.outer / 'cgroup.kill').read_bytes() == b''
    finally:
        delattr(physical.journal, method)


def test_failed_delete_ack_still_kills_again_and_never_mints_observation(physical, monkeypatch):
    kills = []
    actual = module._kill
    monkeypatch.setattr(module, '_kill', lambda handle: (kills.append(True), actual(handle))[1])
    def fail(*args):
        raise SandboxError('sandbox_physical_delete_uncertain')
    monkeypatch.setattr(module, '_run_delete', fail)
    with pytest.raises(SandboxError, match='delete_uncertain'):
        _cleanup(physical)
    assert len(kills) == 2 and physical.handle._observation is None
    assert not physical.lease.snapshot().terminal


def test_cleanup_kills_before_expensive_material_revalidation_and_rekills_on_failure(physical, monkeypatch):
    kills = []
    actual = module._kill
    monkeypatch.setattr(module, '_kill', lambda handle: (kills.append(True), actual(handle))[1])
    def failed_materials(*args):
        assert (physical.outer / 'cgroup.kill').read_bytes() == b'1\n'
        raise SandboxError('sandbox_physical_materials_unavailable')
    monkeypatch.setattr(module, '_materials', failed_materials)
    with pytest.raises(SandboxError, match='materials_unavailable'):
        _cleanup(physical)
    assert len(kills) == 2 and physical.handle._observation is None


@pytest.mark.parametrize('field,value', [('exit_code', False), ('exit_code', 1),
    ('pipes_eof', False), ('pid', True), ('pid', 0), ('stdout_size_bytes', True),
    ('stdout_size_bytes', module.native.MAX_COMMAND_BYTES + 1), ('stderr_sha256', 'A' * 64),
    ('acknowledged_monotonic_ns', True), ('command_sha256', '0' * 64)])
def test_uncertain_or_malformed_internal_delete_readback_never_becomes_observation(physical, monkeypatch, field, value):
    real_boundary = module._run_delete
    def altered(*args):
        result = real_boundary(*args)
        result[field] = value
        return result
    monkeypatch.setattr(module, '_run_delete', altered)
    with pytest.raises(SandboxError, match='delete_uncertain'):
        _cleanup(physical)
    assert physical.handle._observation is None


@pytest.mark.parametrize('field', ['terminal_sequence', 'terminal_head_sha256', 'terminal_result_sha256',
    'start_fence', 'start_journal_epoch', 'start_profile_sha256', 'preceding_journal_sha256', 'start_boot_id'])
def test_db_start_and_closed_terminal_pins_independently_checked(physical, monkeypatch, field):
    issuer, _ = _issuer(physical, monkeypatch)
    old = physical.row[field]
    physical.row[field] = old + 1 if type(old) is int else ('f' * 64 if len(old) == 64 else str(uuid.uuid4()))
    with pytest.raises(SandboxError):
        _issue(physical, issuer)
    assert list(issuer.config.evidence_root.iterdir()) == []


def test_original_live_observation_cannot_be_replaced_by_copied_or_closed_lease(physical, monkeypatch):
    issuer, _ = _issuer(physical, monkeypatch)
    with pytest.raises(SandboxError):
        issuer.issue_under_lease(physical.execution_id, physical.adapter, physical.envelope,
            physical.profile, physical.lease, copy(physical.observation))
    physical.lease.close()
    with pytest.raises(SandboxError):
        _issue(physical, issuer)


def test_terminal_reacquisition_cannot_reconstruct_live_native_authority_from_saved_json(physical, monkeypatch):
    issuer, _ = _issuer(physical, monkeypatch)
    raw = canonical_packet_bytes(_issue(physical, issuer))
    physical.handle.close()
    physical.lease.close()
    with physical.journal.claim(physical.envelope.job_id, physical.envelope.envelope_sha256) as recovered:
        assert recovered.epoch == physical.binding.journal_epoch
        with pytest.raises(SandboxError):
            issuer.issue_under_lease(physical.execution_id, physical.adapter, physical.envelope,
                                    physical.profile, recovered, physical.observation)
        fresh = open_original_cgroup(physical.adapter, physical.envelope, physical.profile,
                                     recovered, (physical.outer.stat().st_dev, physical.outer.stat().st_ino))
        try:
            with pytest.raises(SandboxError, match='cleanup_replay'):
                cleanup_under_lease(physical.adapter, physical.envelope, physical.profile, recovered, fresh)
        finally:
            fresh.close()
    # Already retained authenticated packet bytes remain independently
    # verifiable for delivery; no fresh physical observation is reconstructed.
    assert verify_termination_packet(raw, expected=physical.binding,
        registry=issuer.config.registry).packet_bytes == raw


def test_disabled_issuer_and_incomplete_source_policy_do_not_sign(physical, monkeypatch):
    issuer, args = _issuer(physical, monkeypatch, enabled=False)
    with pytest.raises(SandboxError, match='issuer_unavailable'):
        _issue(physical, issuer)
    with pytest.raises(ValueError):
        PhysicalIssuerConfig(**{**args, 'worker_source_files': {}})
    with pytest.raises(ValueError):
        PhysicalIssuerConfig(**{**args, 'source_policy_bytes': b'{"accepted":true}'})
    with pytest.raises(ValueError):
        PhysicalIssuerConfig(**{**args, 'private_key': Ed25519PrivateKey.generate()})
    assert list(issuer.config.evidence_root.iterdir()) == []


def test_instance_store_callback_cannot_substitute_for_restricted_db_boundary(physical, monkeypatch):
    issuer, _ = _issuer(physical, monkeypatch)
    issuer.config.store._recorder_transaction = lambda: True
    try:
        with pytest.raises(SandboxError, match='store_changed'):
            _issue(physical, issuer)
        assert list(issuer.config.evidence_root.iterdir()) == []
    finally:
        del issuer.config.store._recorder_transaction


def test_complete_source_manifest_is_required_and_mutable_missing_source_bytes_are_refused(physical, monkeypatch):
    issuer, args = _issuer(physical, monkeypatch)
    for missing in module.WORKER_FILES:
        files = dict(args['worker_source_files'])
        del files[missing]
        with pytest.raises(ValueError):
            PhysicalIssuerConfig(**{**args, 'worker_source_files': files})
    monkeypatch.setattr(module, '_source_files', _ACTUAL_SOURCE_CHECK)
    # Protected dummy bytes are configuration fixtures, not the loaded native
    # code's actual source root. They cannot satisfy issuance provenance.
    with pytest.raises(SandboxError):
        _issue(physical, issuer)
    assert list(issuer.config.evidence_root.iterdir()) == []


@pytest.mark.parametrize('kind', ['missing', 'writable', 'hardlink', 'symlink', 'changed', 'parent-writable'])
def test_constructor_requires_real_protected_admission_source_bytes_before_configuration(physical, monkeypatch, kind):
    _, args = _issuer(physical, monkeypatch)
    path = args['source_root'] / 'orchestration/experiment_sandbox/retained_admission.py'
    if kind == 'missing':
        path.unlink()
    elif kind == 'writable':
        path.chmod(0o600)
    elif kind == 'hardlink':
        path.with_name('another-link.py').hardlink_to(path)
    elif kind == 'symlink':
        target = path.with_name('saved.py')
        path.rename(target)
        path.symlink_to(target)
    elif kind == 'parent-writable':
        path.parent.chmod(0o777)
    else:
        path.chmod(0o600)
        path.write_bytes(b'changed protected source')
        path.chmod(0o400)
    with pytest.raises(ValueError, match='protected source'):
        PhysicalIssuerConfig(**args)


@pytest.mark.parametrize('kind', ['symlink', 'hardlink', 'public', 'partial'])
def test_native_evidence_unsafe_paths_and_partial_writes_are_preserved_and_refused(physical, monkeypatch, kind):
    issuer, _ = _issuer(physical, monkeypatch)
    path = physical.observation._native_path
    raw = path.read_bytes()
    target = path.with_name('saved-native.json')
    if kind == 'symlink':
        path.rename(target)
        path.symlink_to(target)
    elif kind == 'hardlink':
        target.hardlink_to(path)
    elif kind == 'public':
        path.chmod(0o644)
    else:
        path.write_bytes(b'partial')
    before = path.lstat()
    with pytest.raises(SandboxError):
        _issue(physical, issuer)
    assert path.lstat() == before
    if kind != 'partial':
        assert path.read_bytes() == raw
    assert list(issuer.config.evidence_root.iterdir()) == []


def test_native_evidence_tamper_and_issuance_conflict_do_not_overwrite(physical, monkeypatch):
    issuer, _ = _issuer(physical, monkeypatch)
    signed = _issue(physical, issuer)
    initial = canonical_packet_bytes(signed)
    intent = next(issuer.config.evidence_root.glob('issuance-*'))
    original = intent.read_bytes()
    altered = json.loads(original)
    altered['claims']['kernel']['cgroup_inode'] += 1
    intent.write_bytes(_json(altered))
    with pytest.raises(SandboxError, match='evidence_conflict'):
        _issue(physical, issuer)
    assert intent.read_bytes() == _json(altered)
    packet = next(issuer.config.evidence_root.glob('c23-termination-*'))
    assert packet.read_bytes() == initial


def test_real_host_guard_refuses_simulated_host_without_effects(physical):
    before = (physical.outer / 'cgroup.kill').read_bytes()
    with pytest.raises(SandboxError):
        _ACTUAL_HOST_GUARD(physical.adapter, physical.envelope, physical.profile, physical.lease)
    assert (physical.outer / 'cgroup.kill').read_bytes() == before


def test_observation_is_frozen_and_audit_frame_is_not_physical_input(physical):
    observation = _cleanup(physical)
    with pytest.raises(FrozenInstanceError):
        observation.native_observation_sha256 = 'f' * 64
    with pytest.raises(SandboxError):
        module._observation(observation.audit_record, physical.adapter, physical.envelope, physical.profile, physical.lease)
