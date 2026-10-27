"""Bounded C23 termination claims, without execution or release authority.

These models describe assertions. Only an independently configured verifier can
authenticate them, and authentication alone does not establish physical facts.
The frozen C22 source, worker implementation, profile policy and prepared
per-job profile deliberately have different identities.
"""
from __future__ import annotations

import hashlib
import json
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

TERMINATION_PACKET_VERSION = 'c23-authenticated-termination-v1'
MAX_TERMINATION_PACKET_BYTES = 16 * 1024
MAX_TERMINATION_JOURNAL_SEQUENCE = 4096

Hash = Annotated[str, StringConstraints(min_length=64, max_length=64, pattern=r'^[a-f0-9]{64}$')]
UUID = Annotated[str, StringConstraints(min_length=36, max_length=36,
    pattern=r'^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$')]
Job = Annotated[str, StringConstraints(min_length=52, max_length=52, pattern=r'^c23-[a-f0-9]{48}$')]
Site = Annotated[str, StringConstraints(min_length=4, max_length=128, pattern=r'^v1:[A-Za-z0-9][A-Za-z0-9_.:-]*$')]
IssuerIdentifier = Annotated[str, StringConstraints(min_length=1, max_length=96,
    pattern=r'^[A-Za-z0-9][A-Za-z0-9_.:-]*$')]
Digest = Annotated[str, StringConstraints(min_length=71, max_length=71, pattern=r'^sha256:[a-f0-9]{64}$')]
Positive = Annotated[int, Field(strict=True, ge=1, le=2**63 - 1)]
Nonnegative = Annotated[int, Field(strict=True, ge=0, le=2**63 - 1)]
Zero = Annotated[int, Field(strict=True, ge=0, le=0)]
Sequence = Annotated[int, Field(strict=True, ge=1, le=MAX_TERMINATION_JOURNAL_SEQUENCE)]
TrustScope = Literal['synthetic-software-test', 'retained-operator']


class TerminationContract(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True, frozen=True,
                              allow_inf_nan=False, revalidate_instances='always')


class ClosedExecutionBinding(TerminationContract):
    """Expected immutable identity loaded by a trusted controller.

    Constructing this schema does not close an execution, acquire a lease,
    authenticate a worker or authorize a future database mutation.
    """
    site_id: Site
    execution_id: UUID
    reservation_id: UUID
    owner_user_id: UUID
    experiment_id: UUID
    proposal_revision_id: UUID
    approval_id: UUID
    approval_request_sha256: Hash
    execution_request_sha256: Hash
    envelope_sha256: Hash
    closed_fence: Positive
    job_id: Job
    worker_id: Hash
    host_boot_id: UUID
    journal_id: UUID
    journal_epoch: Positive
    source_sha256: Hash
    source_policy_sha256: Hash
    worker_source_sha256: Hash
    environment_sha256: Hash
    image_digest: Digest
    runtime_sha256: Hash
    profile_policy_sha256: Hash
    profile_sha256: Hash
    trusted_init_sha256: Hash
    adapter_source_sha256: Hash

    @model_validator(mode='after')
    def deterministic_job(self):
        raw = json.dumps({'site': self.site_id, 'reservation': self.reservation_id,
                          'envelope': self.envelope_sha256}, sort_keys=True,
                         ensure_ascii=False, separators=(',', ':')).encode('utf-8')
        if self.job_id != 'c23-' + hashlib.sha256(raw).hexdigest()[:48]:
            raise ValueError('Termination job does not match its retained envelope')
        return self


class TerminationIssuerScope(TerminationContract):
    """Pinned worker/material policy; per-job profile and C22 source stay bound above."""
    site_id: Site
    worker_id: Hash
    source_policy_sha256: Hash
    worker_source_sha256: Hash
    environment_sha256: Hash
    image_digest: Digest
    runtime_sha256: Hash
    profile_policy_sha256: Hash
    trusted_init_sha256: Hash
    adapter_source_sha256: Hash


class TerminationJournalWitness(TerminationContract):
    create_intent_sequence: Sequence
    create_intent_sha256: Hash
    cleanup_intent_sequence: Sequence
    cleanup_intent_sha256: Hash
    termination_sequence: Sequence
    termination_sha256: Hash
    terminal_sequence: Sequence
    terminal_head_sha256: Hash
    terminal_result_sha256: Hash

    @model_validator(mode='after')
    def ordered_events(self):
        if not (self.create_intent_sequence < self.cleanup_intent_sequence
                < self.termination_sequence < self.terminal_sequence):
            raise ValueError('Termination journal events must be strictly ordered')
        return self


class TerminationKernelWitness(TerminationContract):
    """Signed observation assertions, never caller-supplied physical authority."""
    cgroup_path: Annotated[str, StringConstraints(min_length=63, max_length=63,
        pattern=r'^/ocean-c23/c23-[a-f0-9]{48}$')]
    cgroup_device: Nonnegative
    cgroup_inode: Positive
    populated: Zero
    delete_exit_code: Zero
    delete_job_id: Job
    delete_runtime_sha256: Hash
    delete_host_boot_id: UUID
    delete_command_sha256: Hash
    delete_acknowledgement_sha256: Hash
    raw_observation_sha256: Hash
    cleanup_started_monotonic_ns: Nonnegative
    delete_acknowledged_monotonic_ns: Nonnegative
    populated_zero_monotonic_ns: Nonnegative
    terminal_recorded_monotonic_ns: Nonnegative
    issued_monotonic_ns: Nonnegative

    @model_validator(mode='after')
    def ordered_observations(self):
        if not (self.cleanup_started_monotonic_ns <= self.delete_acknowledged_monotonic_ns
                <= self.populated_zero_monotonic_ns <= self.terminal_recorded_monotonic_ns
                <= self.issued_monotonic_ns):
            raise ValueError('Termination observations must be ordered on one boot clock')
        return self


class TerminationClaims(TerminationContract):
    binding: ClosedExecutionBinding
    journal: TerminationJournalWitness
    kernel: TerminationKernelWitness

    @model_validator(mode='after')
    def correlated_cleanup(self):
        binding, kernel = self.binding, self.kernel
        if (kernel.cgroup_path != '/ocean-c23/' + binding.job_id
                or kernel.delete_job_id != binding.job_id
                or kernel.delete_runtime_sha256 != binding.runtime_sha256
                or kernel.delete_host_boot_id != binding.host_boot_id):
            raise ValueError('Termination cleanup must match its exact worker job and boot')
        return self


class TerminationPacketDocument(TerminationContract):
    """Untrusted wire schema. It contains no verification key or authority bit."""
    version: Literal['c23-authenticated-termination-v1']
    algorithm: Literal['Ed25519']
    trust_scope: TrustScope
    issuer_id: IssuerIdentifier
    key_id: IssuerIdentifier
    claims: TerminationClaims
    signature: Annotated[str, StringConstraints(min_length=128, max_length=128,
        pattern=r'^[a-f0-9]{128}$')]
