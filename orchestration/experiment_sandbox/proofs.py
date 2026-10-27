"""Canonical C23 Ed25519 authentication primitives and create-only receipts.

No physical issuer is implemented here. A pure signature authenticates the
assertions made by its configured key holder; it cannot establish Linux facts,
close a database fence, release capacity, launch Python or approve science.
Actual issuance remains unavailable until a trusted adapter rechecks Linux root,
current boot, its actual held DurableLease, durable terminal readback and original
kernel cgroup/delete observations together while that same lease is held.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import stat
from types import MappingProxyType

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from pydantic import ValidationError

from orchestration.experiment_sandbox.contracts import SandboxError
from schema.experiment_execution import (
    ClosedExecutionBinding, MAX_TERMINATION_PACKET_BYTES, TERMINATION_PACKET_VERSION,
    TerminationClaims, TerminationIssuerScope, TerminationPacketDocument,
)

TERMINATION_SIGNING_DOMAIN = b'ocean.c23.termination.ed25519.v1\x00'
_VERIFIED_TOKEN = object()
_SCOPES = {'synthetic-software-test', 'retained-operator'}


def _error(reason='sandbox_termination_packet_invalid'):
    raise SandboxError(reason)


def _canonical(document):
    return json.dumps(document, ensure_ascii=True, allow_nan=False,
                      sort_keys=True, separators=(',', ':')).encode('ascii')


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _pairs(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            _error()
        value[key] = item
    return value


def _reject_number(_):
    _error()


def _document(raw):
    if type(raw) is not bytes:
        _error()
    if not 1 <= len(raw) <= MAX_TERMINATION_PACKET_BYTES:
        _error('sandbox_termination_packet_limit')
    try:
        parsed = json.loads(raw.decode('ascii'), object_pairs_hook=_pairs,
                            parse_constant=_reject_number, parse_float=_reject_number)
        if type(parsed) is not dict:
            _error()
        document = TerminationPacketDocument.model_validate(parsed)
        if _canonical(document.model_dump(mode='json')) != raw:
            _error('sandbox_termination_packet_noncanonical')
        return document
    except SandboxError:
        raise
    except (ValidationError, ValueError, TypeError, UnicodeError, RecursionError):
        _error()


def _unsigned(document):
    return _canonical(document.model_dump(mode='json', exclude={'signature'}))


@dataclass(frozen=True, init=False)
class SignedTerminationPacket:
    """Detached, syntactically valid signed bytes. Signature is not yet trusted."""
    _packet_bytes: bytes

    def __init__(self, *args, **kwargs):
        raise TypeError('Use parse_signed_termination_packet or sign_termination_claims')

    @property
    def claims(self):
        return _document(self._packet_bytes).claims

    @property
    def authenticated(self):
        return False


def parse_signed_termination_packet(raw) -> SignedTerminationPacket:
    """Parse only bounded canonical bytes; this performs no authentication."""
    _document(raw)
    value = object.__new__(SignedTerminationPacket)
    object.__setattr__(value, '_packet_bytes', bytes(raw))
    return value


def canonical_packet_bytes(packet: SignedTerminationPacket) -> bytes:
    if type(packet) is not SignedTerminationPacket:
        _error()
    try:
        raw = packet._packet_bytes
    except AttributeError:
        _error()
    _document(raw)
    return bytes(raw)


def sign_termination_claims(claims, *, issuer_id, key_id, trust_scope,
                            private_key) -> SignedTerminationPacket:
    """Pure Ed25519 primitive; caller data and a private key prove no Linux facts.

    Synthetic tests must explicitly use ``synthetic-software-test`` and freshly
    generated test keys. Production registration/issuance is outside this API.
    """
    if type(claims) is not TerminationClaims or not isinstance(private_key, Ed25519PrivateKey):
        _error()
    try:
        claims = TerminationClaims.model_validate(claims.model_dump(mode='python', warnings='error'))
        document = TerminationPacketDocument.model_validate({
            'version': TERMINATION_PACKET_VERSION, 'algorithm': 'Ed25519',
            'trust_scope': trust_scope, 'issuer_id': issuer_id, 'key_id': key_id,
            'claims': claims, 'signature': '0' * 128})
        signature = private_key.sign(TERMINATION_SIGNING_DOMAIN + _unsigned(document))
        raw = _canonical(document.model_copy(update={'signature': signature.hex()}).model_dump(mode='json'))
        return parse_signed_termination_packet(raw)
    except SandboxError:
        raise
    except (ValidationError, ValueError, TypeError, UnicodeError, RecursionError):
        _error()


@dataclass(frozen=True, init=False)
class PinnedTerminationIssuer:
    """Trusted out-of-band configuration, never loaded from a result packet."""
    issuer_id: str
    key_id: str
    trust_scope: str
    public_key: bytes
    _scope_bytes: bytes

    def __init__(self, *, issuer_id, key_id, trust_scope, public_key, scope):
        try:
            # Reuse the exact wire header constraints without a second parser.
            for identity in (issuer_id, key_id):
                if (type(identity) is not str or not 1 <= len(identity) <= 96
                        or not identity.isascii() or not identity[0].isalnum()
                        or any(not (char.isalnum() or char in '_.:-') for char in identity)):
                    raise ValueError
            if (type(trust_scope) is not str or trust_scope not in _SCOPES
                    or type(public_key) is not bytes or len(public_key) != 32
                    or type(scope) is not TerminationIssuerScope):
                raise ValueError
            Ed25519PublicKey.from_public_bytes(public_key)
            scoped = TerminationIssuerScope.model_validate(scope.model_dump(mode='python'))
            fields = {'issuer_id': issuer_id, 'key_id': key_id, 'trust_scope': trust_scope,
                      'public_key': bytes(public_key), '_scope_bytes': _canonical(scoped.model_dump(mode='json'))}
            for name, value in fields.items():
                object.__setattr__(self, name, value)
        except (ValidationError, ValueError, TypeError, AttributeError):
            raise ValueError('Explicit pinned termination issuer configuration required') from None

    @property
    def scope(self):
        return TerminationIssuerScope.model_validate(json.loads(self._scope_bytes))


@dataclass(frozen=True, init=False)
class TerminationVerifierRegistry:
    """Default-off exact key/worker/material policy, configured outside packets.

    A registry has one trust scope. Synthetic keys cannot be reused in a
    retained-operator registry without an explicit out-of-band reconfiguration;
    no packet or verifier result can perform that promotion.
    """
    enabled: bool
    trust_scope: str
    policy_sha256: str
    _issuers: Mapping[tuple[str, str], PinnedTerminationIssuer]

    def __init__(self, *, issuers, trust_scope, enabled=False):
        if (type(enabled) is not bool or type(trust_scope) is not str
                or trust_scope not in _SCOPES or type(issuers) not in (list, tuple)
                or not 1 <= len(issuers) <= 64):
            raise ValueError('Explicit bounded termination verifier registry required')
        pinned = {}
        for entry in issuers:
            if type(entry) is not PinnedTerminationIssuer or entry.trust_scope != trust_scope:
                raise ValueError('Termination issuer trust scope mismatch')
            # Detach even a deliberately altered dataclass before pinning it.
            detached = PinnedTerminationIssuer(issuer_id=entry.issuer_id, key_id=entry.key_id,
                trust_scope=entry.trust_scope, public_key=entry.public_key, scope=entry.scope)
            key = detached.issuer_id, detached.key_id
            if key in pinned:
                raise ValueError('Duplicate termination issuer key identity')
            pinned[key] = detached
        policy = {'version': 'c23-termination-verifier-registry-v1', 'trust_scope': trust_scope,
            'issuers': [{'issuer_id': item.issuer_id, 'key_id': item.key_id,
                'public_key': item.public_key.hex(), 'scope': item.scope.model_dump(mode='json')}
                for _, item in sorted(pinned.items())]}
        for name, value in {'enabled': enabled, 'trust_scope': trust_scope,
                'policy_sha256': _sha(_canonical(policy)), '_issuers': MappingProxyType(pinned)}.items():
            object.__setattr__(self, name, value)


@dataclass(frozen=True, init=False)
class VerifiedTerminationPacket:
    """Authenticated claims only, with no launch/release/scientific authority."""
    _packet_bytes: bytes
    _token: object
    packet_sha256: str
    signature_sha256: str
    verification_policy_sha256: str
    verification_key_sha256: str
    trust_scope: str
    issuer_id: str
    key_id: str

    def __init__(self, *args, **kwargs):
        raise TypeError('Use verify_termination_packet')

    @property
    def claims(self):
        return _document(self._packet_bytes).claims

    @property
    def binding(self):
        return self.claims.binding

    @property
    def authenticated(self):
        return True

    @property
    def launch_authorized(self):
        return False

    @property
    def reservation_release_authorized(self):
        return False

    @property
    def scientific_approval(self):
        return 'not_independently_verified'

    @property
    def packet_bytes(self):
        return bytes(self._packet_bytes)


def verify_termination_packet(raw, *, expected, registry) -> VerifiedTerminationPacket:
    """Authenticate the full exact closed tuple against independently pinned policy.

    Exact replay is intentionally valid; the future immutable proof ledger must
    enforce idempotency. A changed execution, fence or journal epoch is rejected.
    ``expected`` must come from trusted retained state, never from the packet.
    """
    if type(registry) is not TerminationVerifierRegistry:
        _error('sandbox_termination_verifier_unavailable')
    if type(expected) is not ClosedExecutionBinding:
        _error('sandbox_termination_binding')
    try:
        if registry.enabled is not True:
            _error('sandbox_termination_verifier_unavailable')
        expected = ClosedExecutionBinding.model_validate(expected.model_dump(mode='python', warnings='error'))
        document = _document(raw)
        if document.trust_scope != registry.trust_scope:
            _error('sandbox_termination_issuer_scope')
        issuer = registry._issuers.get((document.issuer_id, document.key_id))
        if issuer is None:
            _error('sandbox_termination_unknown_issuer')
        binding = document.claims.binding
        if binding != expected:
            _error('sandbox_termination_binding')
        scoped = {field: getattr(binding, field) for field in TerminationIssuerScope.model_fields}
        if _canonical(scoped) != issuer._scope_bytes:
            _error('sandbox_termination_issuer_scope')
        signature = bytes.fromhex(document.signature)
        Ed25519PublicKey.from_public_bytes(issuer.public_key).verify(
            signature, TERMINATION_SIGNING_DOMAIN + _unsigned(document))
        value = object.__new__(VerifiedTerminationPacket)
        for name, item in {'_packet_bytes': bytes(raw), '_token': _VERIFIED_TOKEN,
                'packet_sha256': _sha(raw), 'signature_sha256': _sha(signature),
                'verification_policy_sha256': registry.policy_sha256,
                'verification_key_sha256': _sha(issuer.public_key),
                'trust_scope': document.trust_scope, 'issuer_id': document.issuer_id,
                'key_id': document.key_id}.items():
            object.__setattr__(value, name, item)
        return value
    except SandboxError:
        raise
    except InvalidSignature:
        _error('sandbox_termination_signature')
    except (ValidationError, ValueError, TypeError, AttributeError, UnicodeError, RecursionError):
        _error()


def issue_termination_packet(*, lease, binding, issuer):
    """Fail closed until real held-lease/durable-terminal/kernel hooks exist.

    Neither a DurableLease-shaped object nor a caller-created result/witness is
    substituted for the missing trusted physical issuer. This function signs
    nothing, regardless of host, caller data, keys or registry configuration.
    """
    _error('sandbox_termination_issuer_unavailable')


def _private(info, *, directory=False):
    kind = stat.S_ISDIR if directory else stat.S_ISREG
    if (not kind(info.st_mode) or info.st_uid != os.geteuid()
            or stat.S_IMODE(info.st_mode) != (0o700 if directory else 0o600)
            or (not directory and info.st_nlink != 1)):
        _error('sandbox_termination_receipt_path')


def _file_id(info):
    return info.st_dev, info.st_ino


def retain_termination_packet(root, verified) -> Path:
    """Create once per execution/closed fence; retain only exact byte retries.

    The existing trusted private directory is explicit. No key, environment,
    database, legacy receipt or parent directory is discovered or created.
    This is evidence retention and carries no reservation-release authority.
    """
    try:
        if (type(verified) is not VerifiedTerminationPacket
                or verified._token is not _VERIFIED_TOKEN):
            _error('sandbox_termination_unverified')
        raw = verified.packet_bytes
        document = _document(raw)
        if _sha(raw) != verified.packet_sha256:
            _error('sandbox_termination_unverified')
        root = Path(root)
        if not root.is_absolute() or root != root.resolve(strict=True):
            _error('sandbox_termination_receipt_path')
        before = root.lstat()
        _private(before, directory=True)
        parent = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
        try:
            _private(os.fstat(parent), directory=True)
            if _file_id(before) != _file_id(os.fstat(parent)):
                _error('sandbox_termination_receipt_path')
            binding = document.claims.binding
            name = f'c23-termination-{binding.execution_id}-{binding.closed_fence}.json'
            try:
                fd = os.open(name, os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW
                             | os.O_NONBLOCK | os.O_CLOEXEC, 0o600, dir_fd=parent)
                created = True
            except FileExistsError:
                existing = os.stat(name, dir_fd=parent, follow_symlinks=False)
                _private(existing)
                if existing.st_size > MAX_TERMINATION_PACKET_BYTES:
                    _error('sandbox_termination_receipt_conflict')
                fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC,
                             dir_fd=parent)
                created = False
            try:
                current = os.fstat(fd)
                _private(current)
                if not created and _file_id(current) != _file_id(existing):
                    _error('sandbox_termination_receipt_path')
                if created:
                    pending = memoryview(raw)
                    while pending:
                        written = os.write(fd, pending)
                        if written <= 0:
                            _error('sandbox_termination_receipt_path')
                        pending = pending[written:]
                    os.fsync(fd)
                if os.pread(fd, MAX_TERMINATION_PACKET_BYTES + 1, 0) != raw:
                    _error('sandbox_termination_receipt_conflict')
                retained = os.stat(name, dir_fd=parent, follow_symlinks=False)
                opened = os.fstat(fd)
                _private(retained)
                _private(opened)
                if _file_id(retained) != _file_id(opened) or retained.st_size != len(raw):
                    _error('sandbox_termination_receipt_path')
                # Detect a changed root before declaring durable retention.
                _private(root.lstat(), directory=True)
                if _file_id(root.lstat()) != _file_id(os.fstat(parent)):
                    _error('sandbox_termination_receipt_path')
                os.fsync(parent)
            finally:
                os.close(fd)
        finally:
            os.close(parent)
        return root / name
    except SandboxError:
        raise
    except AttributeError:
        _error('sandbox_termination_unverified')
    except (OSError, ValueError, TypeError):
        _error('sandbox_termination_receipt_path')
