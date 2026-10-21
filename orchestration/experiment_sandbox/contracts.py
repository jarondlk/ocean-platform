"""Exact C22 bytes and identities, without granting execution authority.

Verification is deliberately pure. Fresh admission, runtime containment and
termination are separate supervisor gates; a checksum cannot grant permission.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import hashlib
import json
from types import MappingProxyType
from typing import Annotated, Literal

from pydantic import StringConstraints

from orchestration.frozen_experiment_export import FrozenExperimentExport
from schema.context_catalogue import canonical_json
from schema.investigations import InvestigationRequest, UUIDString
from schema.research_experiments import (
    EnvironmentDescriptor, ExperimentContextBinding, ExperimentHashes,
    ExperimentProposal, content_sha256,
)

VERSION = 'c23-sandbox-contract-v1'


class SandboxError(ValueError):
    """Safe fixed reason; never return raw runtime paths, logs or exceptions."""
    def __init__(self, reason='sandbox_integrity'):
        self.reason = reason
        super().__init__(reason)


class ExecutionMetadata(InvestigationRequest):
    version: Literal['c22-execution-envelope-v1']
    site_id: Annotated[str, StringConstraints(min_length=4, max_length=128, pattern=r'^v1:[A-Za-z0-9_.:-]+$')]
    experiment_id: UUIDString
    proposal_revision_id: UUIDString
    owner_user_id: UUIDString
    reservation_id: UUIDString
    approval_id: UUIDString
    binding: ExperimentContextBinding
    proposal: ExperimentProposal
    environment: EnvironmentDescriptor
    hashes: ExperimentHashes
    manifest: dict
    authority: Literal['experimental']
    scientific_approval: Literal['not_independently_verified']
    execution_performed: Literal[False]


@dataclass(frozen=True, init=False)
class VerifiedEnvelope:
    """Detached immutable inputs. Construction is internal to the verifier."""
    _metadata_json: str
    _files: Mapping
    envelope_sha256: str
    job_id: str

    def __init__(self, *args, **kwargs):
        raise TypeError('Use verify_execution_envelope')

    @property
    def metadata(self):
        return json.loads(self._metadata_json)

    @property
    def files(self):
        return self._files

    @property
    def proposal(self):
        return self.metadata['proposal']

    @property
    def resources(self):
        return self.proposal['resources']

    @property
    def environment(self):
        return self.metadata['environment']

    @property
    def code(self):
        return self.proposal['python_code'].encode('utf-8')

    @property
    def manifest_bytes(self):
        return canonical_json(self.metadata['manifest']).encode('utf-8')

    @property
    def input_size_bytes(self):
        return len(self.code) + len(self.manifest_bytes) + sum(map(len, self.files.values()))


def verify_execution_envelope(envelope, *, expected_envelope_sha256, environments):
    """Bind exact retained reservation hash and trusted environment registry.

    ``expected_envelope_sha256`` must come from the retained C22 reservation,
    never a caller's assertion. This pure function is no fresh-access check.
    Fake environments remain fake; they cannot be upgraded to a Linux image.
    """
    try:
        if not isinstance(envelope, Mapping) or set(envelope) != {'metadata', 'files'}:
            raise ValueError
        raw = envelope['metadata']
        metadata = ExecutionMetadata.model_validate(raw).model_dump(mode='json')
        if canonical_json(raw) != canonical_json(metadata):
            raise ValueError
        identity = content_sha256(metadata)
        if type(expected_envelope_sha256) is not str or identity != expected_envelope_sha256:
            raise ValueError
        proposal, environment, hashes = metadata['proposal'], metadata['environment'], metadata['hashes']
        registered = EnvironmentDescriptor.model_validate(environments[proposal['environment_id']]).model_dump(mode='json')
        if registered != environment:
            raise ValueError
        expected = {
            'proposal_sha256': content_sha256(proposal),
            'code_sha256': hashlib.sha256(proposal['python_code'].encode('utf-8')).hexdigest(),
            'input_manifest_sha256': content_sha256(metadata['manifest']),
            'environment_sha256': content_sha256(environment),
            'resources_sha256': content_sha256(proposal['resources']),
        }
        if hashes != expected or proposal['environment_id'] != expected['environment_sha256']:
            raise ValueError
        exported = FrozenExperimentExport(manifest_json=canonical_json(metadata['manifest']), files=envelope['files'])
        binding = metadata['binding']
        manifest_binding = {'investigation_id': binding['investigation_id'], 'conversation_id': binding['conversation_id'],
            'revision_id': binding['context_revision_id'], 'snapshot_id': binding['snapshot_id'],
            'payload_sha256': binding['context_payload_sha256']}
        if (exported.manifest['binding'] != manifest_binding
                or exported.manifest['proposal_sha256'] != expected['proposal_sha256']
                or exported.manifest['cohort'] != proposal['cohort']
                or exported.manifest['question'] != proposal['question']
                or exported.manifest['authority'] != 'experimental'
                or exported.manifest['independent_scientific_approval'] is not False
                or exported.manifest['execution_performed'] is not False
                or exported.manifest['max_input_bytes'] != proposal['resources']['max_input_bytes']):
            raise ValueError
        if exported.size_bytes + len(proposal['python_code'].encode('utf-8')) > proposal['resources']['max_input_bytes']:
            raise SandboxError('sandbox_input_limit')
        value = object.__new__(VerifiedEnvelope)
        fields = {'_metadata_json': canonical_json(metadata), '_files': MappingProxyType(dict(exported.files)),
            'envelope_sha256': identity,
            'job_id': 'c23-' + content_sha256({'site': metadata['site_id'], 'reservation': metadata['reservation_id'], 'envelope': identity})[:48]}
        for name, item in fields.items():
            object.__setattr__(value, name, item)
        return value
    except SandboxError:
        raise
    except (ValueError, TypeError, KeyError, AttributeError, UnicodeError, RecursionError):
        raise SandboxError() from None
