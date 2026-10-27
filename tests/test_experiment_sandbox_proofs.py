"""Synthetic-key C23 protocol tests; no Linux, launch, release or science proof."""
from copy import deepcopy
from dataclasses import FrozenInstanceError
import hashlib
import json
import os
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from pydantic import ValidationError
import pytest

from orchestration.experiment_sandbox.contracts import SandboxError
from orchestration.experiment_sandbox import proofs
from orchestration.experiment_sandbox.proofs import (
    PinnedTerminationIssuer, SignedTerminationPacket, TerminationVerifierRegistry,
    VerifiedTerminationPacket, canonical_packet_bytes, issue_termination_packet,
    parse_signed_termination_packet, retain_termination_packet,
    sign_termination_claims, verify_termination_packet,
)
from schema.experiment_execution import (
    ClosedExecutionBinding, MAX_TERMINATION_PACKET_BYTES, TerminationClaims,
    TerminationIssuerScope,
)

SYNTHETIC_SCOPE = 'synthetic-software-test'
SYNTHETIC_ISSUER = 'synthetic-test-issuer'
SYNTHETIC_KEY_ID = 'synthetic-ephemeral-key'
_UNSPECIFIED = object()


def _canonical(value):
    return json.dumps(value, ensure_ascii=True, allow_nan=False,
                      sort_keys=True, separators=(',', ':')).encode('ascii')


def _hash(label):
    return hashlib.sha256(label.encode()).hexdigest()


def _uuid(number):
    return f'00000000-0000-4000-8000-{number:012d}'


def _job(binding):
    return 'c23-' + hashlib.sha256(_canonical({'site': binding['site_id'],
        'reservation': binding['reservation_id'], 'envelope': binding['envelope_sha256']})).hexdigest()[:48]


def _claims():
    binding = {'site_id': 'v1:synthetic-protocol-test', 'execution_id': _uuid(1),
        'reservation_id': _uuid(2), 'owner_user_id': _uuid(3), 'experiment_id': _uuid(4),
        'proposal_revision_id': _uuid(5), 'approval_id': _uuid(6),
        'approval_request_sha256': _hash('approval-request'),
        'execution_request_sha256': _hash('execution-request'),
        'envelope_sha256': _hash('envelope'), 'closed_fence': 3,
        'worker_id': _hash('worker'), 'host_boot_id': _uuid(7), 'journal_id': _uuid(8),
        'journal_epoch': 2, 'source_sha256': _hash('frozen-c22-source'),
        'source_policy_sha256': _hash('source-policy'),
        'worker_source_sha256': _hash('worker-source'),
        'environment_sha256': _hash('environment'), 'image_digest': 'sha256:' + _hash('image'),
        'runtime_sha256': _hash('runtime'), 'profile_policy_sha256': _hash('profile-policy'),
        'profile_sha256': _hash('prepared-profile'), 'trusted_init_sha256': _hash('init'),
        'adapter_source_sha256': _hash('adapter')}
    binding['job_id'] = _job(binding)
    return TerminationClaims.model_validate({'binding': binding,
        'journal': {'create_intent_sequence': 3, 'create_intent_sha256': _hash('create'),
            'cleanup_intent_sequence': 8, 'cleanup_intent_sha256': _hash('cleanup'),
            'termination_sequence': 9, 'termination_sha256': _hash('termination'),
            'terminal_sequence': 10, 'terminal_head_sha256': _hash('finished'),
            'terminal_result_sha256': _hash('durable-result')},
        'kernel': {'cgroup_path': '/ocean-c23/' + binding['job_id'],
            'cgroup_device': 29, 'cgroup_inode': 10042, 'populated': 0,
            'delete_exit_code': 0, 'delete_job_id': binding['job_id'],
            'delete_runtime_sha256': binding['runtime_sha256'],
            'delete_host_boot_id': binding['host_boot_id'],
            'delete_command_sha256': _hash('delete-command'),
            'delete_acknowledgement_sha256': _hash('delete-ack'),
            'raw_observation_sha256': _hash('raw-observation'),
            'cleanup_started_monotonic_ns': 100, 'delete_acknowledged_monotonic_ns': 110,
            'populated_zero_monotonic_ns': 120, 'terminal_recorded_monotonic_ns': 130,
            'issued_monotonic_ns': 140}})


def _scope(claims):
    return TerminationIssuerScope.model_validate({
        name: getattr(claims.binding, name) for name in TerminationIssuerScope.model_fields})


def _issuer(key, claims, *, trust_scope=SYNTHETIC_SCOPE, key_id=SYNTHETIC_KEY_ID,
            issuer_id=SYNTHETIC_ISSUER):
    return PinnedTerminationIssuer(issuer_id=issuer_id, key_id=key_id,
        trust_scope=trust_scope, public_key=key.public_key().public_bytes_raw(), scope=_scope(claims))


def _sign(key, claims, *, trust_scope=SYNTHETIC_SCOPE, key_id=SYNTHETIC_KEY_ID,
          issuer_id=SYNTHETIC_ISSUER):
    return sign_termination_claims(claims, issuer_id=issuer_id, key_id=key_id,
                                  trust_scope=trust_scope, private_key=key)


@pytest.fixture
def protocol():
    # Only ephemeral synthetic software-test keys are created by this suite.
    key, claims = Ed25519PrivateKey.generate(), _claims()
    registry = TerminationVerifierRegistry(issuers=[_issuer(key, claims)],
                                          trust_scope=SYNTHETIC_SCOPE, enabled=True)
    signed = _sign(key, claims)
    raw = canonical_packet_bytes(signed)
    return key, claims, registry, signed, raw


def _verify(protocol, raw=_UNSPECIFIED, *, expected=None, registry=None):
    _, claims, configured, _, retained = protocol
    return verify_termination_packet(retained if raw is _UNSPECIFIED else raw,
        expected=claims.binding if expected is None else expected,
        registry=configured if registry is None else registry)


def test_ephemeral_synthetic_signature_is_exact_detached_authentication_only(protocol):
    key, claims, registry, signed, raw = protocol
    assert len(raw) < MAX_TERMINATION_PACKET_BYTES
    assert canonical_packet_bytes(parse_signed_termination_packet(raw)) == raw
    assert canonical_packet_bytes(_sign(key, claims)) == raw
    verified = _verify(protocol)
    assert signed.authenticated is False
    assert verified.authenticated is True
    assert verified.claims == claims and verified.claims is not claims
    assert verified.binding is not verified.binding
    assert verified.packet_bytes == raw
    assert verified.packet_sha256 == hashlib.sha256(raw).hexdigest()
    assert verified.verification_policy_sha256 == registry.policy_sha256
    assert verified.verification_key_sha256 == hashlib.sha256(key.public_key().public_bytes_raw()).hexdigest()
    assert verified.trust_scope == SYNTHETIC_SCOPE
    assert verified.launch_authorized is False
    assert verified.reservation_release_authorized is False
    assert verified.scientific_approval == 'not_independently_verified'
    assert _verify(protocol).packet_sha256 == verified.packet_sha256  # Exact retry.
    with pytest.raises(FrozenInstanceError):
        verified.issuer_id = 'changed'
    with pytest.raises(ValidationError):
        verified.claims.kernel.populated = 1
    detached = verified.claims.model_dump(mode='json')
    detached['binding']['source_sha256'] = _hash('changed')
    assert verified.binding.source_sha256 == claims.binding.source_sha256


@pytest.mark.parametrize('value', [None, False, True, {}, {'checksum': '0' * 64}, b'', b'true', b'{}'])
def test_json_booleans_checksums_and_unsigned_objects_are_never_packets(protocol, value):
    with pytest.raises(SandboxError):
        _verify(protocol, value)


@pytest.mark.parametrize('cls', [SignedTerminationPacket, VerifiedTerminationPacket])
def test_detached_packet_constructors_are_private(cls):
    with pytest.raises(TypeError):
        cls()


@pytest.mark.parametrize('factory', [lambda: False, lambda: {}, lambda: object.__new__(VerifiedTerminationPacket)])
def test_unverified_objects_cannot_be_retained(tmp_path, factory):
    tmp_path.chmod(0o700)
    with pytest.raises(SandboxError, match='unverified'):
        retain_termination_packet(tmp_path, factory())
    assert list(tmp_path.iterdir()) == []


def test_default_off_registry_and_wrong_shape_cannot_authenticate(protocol):
    key, claims, _, _, _ = protocol
    disabled = TerminationVerifierRegistry(issuers=[_issuer(key, claims)], trust_scope=SYNTHETIC_SCOPE)
    assert disabled.enabled is False
    for registry in (disabled, True, {}, None):
        with pytest.raises(SandboxError, match='verifier_unavailable'):
            verify_termination_packet(protocol[-1], expected=claims.binding, registry=registry)


def test_forged_registry_or_expected_model_cannot_bypass_validation(protocol):
    _, claims, registry, _, raw = protocol
    for expected in (True, None, claims.binding.model_dump(mode='json'),
                     claims.binding.model_copy(update={'closed_fence': False})):
        with pytest.raises(SandboxError):
            verify_termination_packet(raw, expected=expected, registry=registry)
    with pytest.raises(SandboxError):
        verify_termination_packet(raw, expected=claims.binding,
                                  registry=object.__new__(TerminationVerifierRegistry))


def test_packet_key_is_not_authority_and_wrong_registered_key_fails(protocol):
    _, claims, _, _, raw = protocol
    attacker = Ed25519PrivateKey.generate()
    wrong = TerminationVerifierRegistry(issuers=[_issuer(attacker, claims)],
                                       trust_scope=SYNTHETIC_SCOPE, enabled=True)
    with pytest.raises(SandboxError, match='termination_signature'):
        _verify(protocol, registry=wrong)
    packet = json.loads(raw)
    packet['public_key'] = attacker.public_key().public_bytes_raw().hex()
    with pytest.raises(SandboxError):
        _verify(protocol, _canonical(packet))
    forged = canonical_packet_bytes(_sign(attacker, claims))
    with pytest.raises(SandboxError, match='termination_signature'):
        _verify(protocol, forged)


@pytest.mark.parametrize('field,replacement', [
    ('issuer_id', 'unregistered-issuer'), ('key_id', 'unregistered-key'),
    ('trust_scope', 'retained-operator'), ('algorithm', 'HS256'),
    ('version', 'other-v1'), ('signature', 'A' * 128), ('signature', '00'),
    ('signature', True), ('signature', '0' * 128),
])
def test_headers_scope_algorithm_and_signature_are_strict(protocol, field, replacement):
    packet = json.loads(protocol[-1])
    packet[field] = replacement
    with pytest.raises(SandboxError):
        _verify(protocol, _canonical(packet))


def test_signature_covers_domain_issuer_key_and_every_claim(protocol):
    key, claims, _, _, raw = protocol
    original = json.loads(raw)
    unsigned = {name: value for name, value in original.items() if name != 'signature'}
    for message in (_canonical(unsigned), b'wrong-domain\x00' + _canonical(unsigned)):
        packet = {**original, 'signature': key.sign(message).hex()}
        with pytest.raises(SandboxError, match='termination_signature'):
            _verify(protocol, _canonical(packet))
    # Register the same key under two identities to ensure a changed header
    # fails cryptographically rather than only failing a registry lookup.
    registry = TerminationVerifierRegistry(issuers=[_issuer(key, claims),
        _issuer(key, claims, key_id='alternate-key', issuer_id='alternate-issuer')],
        trust_scope=SYNTHETIC_SCOPE, enabled=True)
    packet = {**original, 'issuer_id': 'alternate-issuer', 'key_id': 'alternate-key'}
    with pytest.raises(SandboxError, match='termination_signature'):
        _verify(protocol, _canonical(packet), registry=registry)
    for path in [('journal', 'terminal_result_sha256'), ('kernel', 'raw_observation_sha256')]:
        packet = deepcopy(original)
        packet['claims'][path[0]][path[1]] = _hash('tampered')
        with pytest.raises(SandboxError, match='termination_signature'):
            _verify(protocol, _canonical(packet))


@pytest.mark.parametrize('field', list(ClosedExecutionBinding.model_fields))
def test_every_closed_binding_field_must_match_independent_expected_state(protocol, field):
    _, claims, _, _, _ = protocol
    binding = claims.binding.model_dump(mode='json')
    old = binding[field]
    if type(old) is int:
        binding[field] += 1
    elif field == 'site_id':
        binding[field] = 'v1:other-site'
    elif field == 'job_id':
        # A changed retained envelope also gets its deterministic job identity.
        binding['envelope_sha256'] = _hash('other-envelope')
    elif field == 'image_digest':
        binding[field] = 'sha256:' + _hash('other-image')
    elif len(old) == 36:
        binding[field] = _uuid(99)
    else:
        binding[field] = _hash('different-' + field)
    binding['job_id'] = _job(binding)
    expected = ClosedExecutionBinding.model_validate(binding)
    with pytest.raises(SandboxError, match='termination_binding'):
        _verify(protocol, expected=expected)


@pytest.mark.parametrize('field', list(TerminationIssuerScope.model_fields))
def test_even_valid_signature_is_rejected_outside_pinned_worker_material_scope(protocol, field):
    key, claims, _, _, _ = protocol
    scope = _scope(claims).model_dump(mode='json')
    if field == 'site_id':
        scope[field] = 'v1:untrusted-site'
    elif field == 'image_digest':
        scope[field] = 'sha256:' + _hash('untrusted-image')
    else:
        scope[field] = _hash('untrusted-' + field)
    issuer = PinnedTerminationIssuer(issuer_id=SYNTHETIC_ISSUER, key_id=SYNTHETIC_KEY_ID,
        trust_scope=SYNTHETIC_SCOPE, public_key=key.public_key().public_bytes_raw(),
        scope=TerminationIssuerScope.model_validate(scope))
    registry = TerminationVerifierRegistry(issuers=[issuer], trust_scope=SYNTHETIC_SCOPE, enabled=True)
    with pytest.raises(SandboxError, match='issuer_scope'):
        _verify(protocol, registry=registry)


def test_synthetic_registry_cannot_be_silently_promoted_or_changed(protocol):
    key, claims, registry, _, _ = protocol
    entry = _issuer(key, claims)
    with pytest.raises(ValueError, match='trust scope'):
        TerminationVerifierRegistry(issuers=[entry], trust_scope='retained-operator', enabled=True)
    with pytest.raises(FrozenInstanceError):
        registry.trust_scope = 'retained-operator'
    with pytest.raises(TypeError):
        registry._issuers[(entry.issuer_id, entry.key_id)] = entry
    with pytest.raises(ValueError, match='Duplicate'):
        TerminationVerifierRegistry(issuers=[entry, entry], trust_scope=SYNTHETIC_SCOPE)
    for value in (b'x' * 31, b'x' * 33, 'x' * 32, bytearray(b'x' * 32), True):
        with pytest.raises(ValueError):
            PinnedTerminationIssuer(issuer_id=SYNTHETIC_ISSUER, key_id=SYNTHETIC_KEY_ID,
                trust_scope=SYNTHETIC_SCOPE, public_key=value, scope=_scope(claims))


@pytest.mark.parametrize('raw', [
    b' ' * (MAX_TERMINATION_PACKET_BYTES + 1), b'\xff', b'\xef\xbb\xbf{}',
    b'{"version":NaN}', b'{"version":Infinity}', b'{"version":-Infinity}',
    b'{"version":1.0}', b'{"version":true,"version":false}',
    b'[' * 1200 + b'0' + b']' * 1200,
    b'{"a":' * 1200 + b'0' + b'}' * 1200,
    b'{"a":' + b'1' * 5000 + b'}',
])
def test_parsing_is_bounded_duplicate_free_ascii_finite_and_recursion_safe(protocol, raw):
    with pytest.raises(SandboxError):
        _verify(protocol, raw)


def test_noncanonical_json_and_duplicate_nested_keys_are_rejected(protocol):
    raw = protocol[-1]
    for changed in (raw + b'\n', b' ' + raw, json.dumps(json.loads(raw), indent=2).encode(),
                    raw.replace(b'"closed_fence":3', b'"closed_fence":03'),
                    raw.replace(b'"issuer_id"', b'"issuer_\\u0069d"'),
                    raw.replace(b'"closed_fence":3', b'"closed_fence":3,"closed_fence":3')):
        assert changed != raw
        with pytest.raises(SandboxError):
            _verify(protocol, changed)


@pytest.mark.parametrize('path,value', [
    (('kernel', 'populated'), False), (('kernel', 'populated'), 1),
    (('kernel', 'delete_exit_code'), False), (('kernel', 'delete_exit_code'), 1),
    (('kernel', 'cgroup_device'), True), (('kernel', 'cgroup_device'), -1),
    (('kernel', 'cgroup_inode'), 0), (('kernel', 'cgroup_inode'), '10042'),
    (('kernel', 'issued_monotonic_ns'), 2**63),
    (('binding', 'closed_fence'), True), (('binding', 'journal_epoch'), 0),
    (('journal', 'terminal_sequence'), 4097), (('journal', 'terminal_sequence'), 9),
    (('journal', 'cleanup_intent_sequence'), 3),
    (('kernel', 'delete_job_id'), 'c23-' + 'a' * 48),
    (('kernel', 'delete_runtime_sha256'), 'a' * 64),
    (('kernel', 'delete_host_boot_id'), _uuid(88)),
    (('kernel', 'cgroup_path'), '/ocean-c23/c23-' + 'a' * 48),
    (('kernel', 'populated_zero_monotonic_ns'), 109),
    (('kernel', 'terminal_recorded_monotonic_ns'), 119),
    (('kernel', 'issued_monotonic_ns'), 129),
    (('binding', 'worker_id'), 'A' * 64),
])
def test_claims_reject_bool_coercion_uncertainty_mismatches_and_bad_order(protocol, path, value):
    claims = protocol[1].model_dump(mode='json')
    claims[path[0]][path[1]] = value
    with pytest.raises(ValidationError):
        TerminationClaims.model_validate(claims)
    packet = json.loads(protocol[-1])
    packet['claims'] = claims
    with pytest.raises(SandboxError):
        _verify(protocol, _canonical(packet))


def test_constructed_unvalidated_claims_do_not_bypass_signing_validation(protocol):
    key, claims, _, _, _ = protocol
    forged = claims.model_copy(update={'kernel': {'populated': False}})
    with pytest.raises(SandboxError):
        _sign(key, forged)
    for value in (claims.model_dump(mode='json'), True, {'termination_verified': True}):
        with pytest.raises(SandboxError):
            _sign(key, value)


@pytest.mark.parametrize('lease', [None, True, {}, {'epoch': 1, 'terminal': True}, object()])
def test_missing_physical_issuer_never_signs_caller_result_or_lease(protocol, lease, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail('Physical unavailable gate invoked a signing primitive')
    monkeypatch.setattr(proofs, 'sign_termination_claims', forbidden)
    with pytest.raises(SandboxError, match='termination_issuer_unavailable'):
        issue_termination_packet(lease=lease, binding=protocol[1].binding, issuer=protocol[0])


def test_create_only_receipt_exact_replay_is_stable_and_changed_packet_conflicts(protocol, tmp_path):
    tmp_path.chmod(0o700)
    verified = _verify(protocol)
    receipt = retain_termination_packet(tmp_path, verified)
    assert receipt.name == f'c23-termination-{verified.binding.execution_id}-3.json'
    assert receipt.read_bytes() == protocol[-1]
    before = receipt.stat()
    assert before.st_mode & 0o777 == 0o600 and before.st_nlink == 1
    assert retain_termination_packet(tmp_path, _verify(protocol)) == receipt
    assert receipt.stat() == before
    key, claims, _, _, _ = protocol
    changed = claims.model_dump(mode='json')
    changed['kernel']['raw_observation_sha256'] = _hash('another-observation')
    altered = canonical_packet_bytes(_sign(key, TerminationClaims.model_validate(changed)))
    verified_altered = _verify(protocol, altered)
    with pytest.raises(SandboxError, match='receipt_conflict'):
        retain_termination_packet(tmp_path, verified_altered)
    assert receipt.read_bytes() == protocol[-1] and receipt.stat() == before


@pytest.mark.parametrize('kind', ['symlink', 'hardlink', 'directory', 'fifo', 'public', 'oversize', 'partial'])
def test_receipt_existing_unsafe_or_conflicting_file_is_never_replaced(protocol, tmp_path, kind):
    tmp_path.chmod(0o700)
    verified = _verify(protocol)
    receipt = tmp_path / f'c23-termination-{verified.binding.execution_id}-3.json'
    target = tmp_path / 'target'
    target.write_bytes(protocol[-1])
    target.chmod(0o600)
    if kind == 'symlink':
        receipt.symlink_to(target)
    elif kind == 'hardlink':
        receipt.hardlink_to(target)
    elif kind == 'directory':
        receipt.mkdir(mode=0o700)
    elif kind == 'fifo':
        os.mkfifo(receipt, 0o600)
    else:
        receipt.write_bytes(b'x' * (MAX_TERMINATION_PACKET_BYTES + 1) if kind == 'oversize'
                            else b'partial' if kind == 'partial' else protocol[-1])
        receipt.chmod(0o644 if kind == 'public' else 0o600)
    original = receipt.lstat()
    with pytest.raises(SandboxError, match='receipt_'):
        retain_termination_packet(tmp_path, verified)
    assert receipt.lstat() == original
    assert target.read_bytes() == protocol[-1]


def test_receipt_requires_existing_absolute_canonical_private_root(protocol, tmp_path):
    tmp_path.chmod(0o700)
    verified = _verify(protocol)
    private = tmp_path / 'private'
    private.mkdir(mode=0o700)
    link = tmp_path / 'link'
    link.symlink_to(private, target_is_directory=True)
    public = tmp_path / 'public'
    public.mkdir(mode=0o755)
    for root in (Path('relative'), tmp_path / 'absent', link, public):
        with pytest.raises(SandboxError, match='receipt_path'):
            retain_termination_packet(root, verified)
    assert list(private.iterdir()) == []
