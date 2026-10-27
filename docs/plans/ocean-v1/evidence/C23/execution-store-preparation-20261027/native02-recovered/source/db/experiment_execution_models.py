"""Opt-in C23 operator persistence; importing C22 serving models does not load it.

Immutable identity/history is separate from monotonic admission state. PostgreSQL
triggers and restricted named functions provide the native boundary; SQLite
metadata is useful for schema inspection only and cannot authorize execution.
"""
from __future__ import annotations

from sqlalchemy import (BigInteger, CheckConstraint, Column, DateTime,
                        ForeignKey, ForeignKeyConstraint, Integer, LargeBinary,
                        String, Text, UniqueConstraint, Uuid, event, func)

from db.app_models import AppBase, _context_sha256_check


IDENTITY_HASH_FIELDS = (
    'approval_request_sha256', 'execution_request_sha256', 'envelope_sha256',
    'worker_id', 'source_sha256', 'source_policy_sha256', 'worker_source_sha256',
    'environment_sha256', 'runtime_sha256', 'profile_policy_sha256',
    'trusted_init_sha256', 'adapter_source_sha256',
)
BINDING_FIELDS = ('execution_id', 'reservation_id', 'owner_user_id', 'envelope_sha256')


def _hash_checks(prefix, names):
    return tuple(CheckConstraint(_context_sha256_check(name), name=f'ck_{prefix}_{name}') for name in names)


def _execution_fk(prefix):
    return ForeignKeyConstraint(BINDING_FIELDS, tuple('research_experiment_execution.' + name
        for name in BINDING_FIELDS), name=f'fk_{prefix}_execution', ondelete='RESTRICT')


class ResearchExperimentExecution(AppBase):
    __tablename__ = 'research_experiment_execution'
    execution_id = Column(Uuid(as_uuid=True), primary_key=True)
    reservation_id = Column(Uuid(as_uuid=True), nullable=False, unique=True)
    owner_user_id = Column(Uuid(as_uuid=True), nullable=False)
    experiment_id = Column(Uuid(as_uuid=True), nullable=False)
    proposal_revision_id = Column(Uuid(as_uuid=True), nullable=False)
    approval_id = Column(Uuid(as_uuid=True), nullable=False)
    site_id = Column(String(128), nullable=False)
    idempotency_key = Column(String(128), nullable=False)
    request_json = Column(Text, nullable=False)
    envelope_json = Column(Text, nullable=False)
    job_id = Column(String(52), nullable=False, unique=True)
    image_digest = Column(String(71), nullable=False)
    for _name in IDENTITY_HASH_FIELDS:
        locals()[_name] = Column(String(64), nullable=False)
    del _name
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    __table_args__ = (
        UniqueConstraint(*BINDING_FIELDS, name='uq_c23_execution_binding'),
        UniqueConstraint('site_id', 'owner_user_id', 'idempotency_key', name='uq_c23_execution_key'),
        ForeignKeyConstraint(['reservation_id', 'owner_user_id'],
            ['research_experiment_reservation.id', 'research_experiment_reservation.user_id'],
            name='fk_c23_execution_reservation', ondelete='RESTRICT'),
        ForeignKeyConstraint(['approval_id', 'experiment_id', 'proposal_revision_id', 'owner_user_id'],
            ['research_experiment_approval.id', 'research_experiment_approval.experiment_id',
             'research_experiment_approval.revision_id', 'research_experiment_approval.user_id'],
            name='fk_c23_execution_approval', ondelete='RESTRICT'),
        CheckConstraint("length(site_id) BETWEEN 4 AND 128 AND substr(site_id,1,3)='v1:' AND length(idempotency_key) BETWEEN 1 AND 128", name='ck_c23_execution_site_key'),
        CheckConstraint("length(request_json) BETWEEN 2 AND 65536 AND length(envelope_json) BETWEEN 2 AND 1048576", name='ck_c23_execution_bytes'),
        CheckConstraint("length(job_id)=52 AND substr(job_id,1,4)='c23-' AND length(image_digest)=71 AND substr(image_digest,1,7)='sha256:'", name='ck_c23_execution_material'),
        *_hash_checks('c23_execution', IDENTITY_HASH_FIELDS),
    )


class ResearchExperimentExecutionEvent(AppBase):
    __tablename__ = 'research_experiment_execution_event'
    id = Column(Uuid(as_uuid=True), primary_key=True)
    execution_id = Column(Uuid(as_uuid=True), nullable=False)
    reservation_id = Column(Uuid(as_uuid=True), nullable=False)
    owner_user_id = Column(Uuid(as_uuid=True), nullable=False)
    envelope_sha256 = Column(String(64), nullable=False)
    fence = Column(BigInteger, nullable=False)
    kind = Column(String(24), nullable=False)
    start_id = Column(Uuid(as_uuid=True), nullable=False)
    host_boot_id = Column(Uuid(as_uuid=True), nullable=False)
    journal_id = Column(Uuid(as_uuid=True), nullable=False)
    journal_epoch = Column(BigInteger, nullable=False)
    profile_sha256 = Column(String(64), nullable=False)
    preceding_journal_sha256 = Column(String(64), nullable=False)
    result_sha256 = Column(String(64))
    terminal_sequence = Column(Integer)
    terminal_head_sha256 = Column(String(64))
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    __table_args__ = (
        _execution_fk('c23_event'),
        UniqueConstraint('execution_id', 'fence', name='uq_c23_event_fence'),
        UniqueConstraint('id', 'execution_id', 'fence', name='uq_c23_event_state'),
        CheckConstraint("fence >= 2 AND journal_epoch >= 1 AND kind IN ('start_consumed','publication_retained','closed')", name='ck_c23_event_state'),
        CheckConstraint("kind <> 'publication_retained' OR result_sha256 IS NOT NULL", name='ck_c23_event_publication'),
        CheckConstraint("(kind='closed' AND terminal_sequence IS NOT NULL AND terminal_sequence BETWEEN 1 AND 4096 AND terminal_head_sha256 IS NOT NULL AND result_sha256 IS NOT NULL) OR (kind<>'closed' AND terminal_sequence IS NULL AND terminal_head_sha256 IS NULL)", name='ck_c23_event_terminal'),
        *_hash_checks('c23_event', ('envelope_sha256', 'profile_sha256', 'preceding_journal_sha256', 'result_sha256', 'terminal_head_sha256')),
    )


class ResearchExperimentExecutionState(AppBase):
    __tablename__ = 'research_experiment_execution_state'
    execution_id = Column(Uuid(as_uuid=True), ForeignKey('research_experiment_execution.execution_id', ondelete='RESTRICT'), primary_key=True)
    fence = Column(BigInteger, nullable=False)
    state = Column(String(24), nullable=False)
    start_event_id = Column(Uuid(as_uuid=True), ForeignKey('research_experiment_execution_event.id', ondelete='RESTRICT'))
    current_event_id = Column(Uuid(as_uuid=True))
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    __table_args__ = (
        ForeignKeyConstraint(['current_event_id', 'execution_id', 'fence'],
            ['research_experiment_execution_event.id', 'research_experiment_execution_event.execution_id',
             'research_experiment_execution_event.fence'], name='fk_c23_state_event', ondelete='RESTRICT'),
        CheckConstraint("(state='reserved' AND fence=1 AND start_event_id IS NULL AND current_event_id IS NULL) OR (state IN ('start_consumed','publication_retained','closed') AND fence>=2 AND start_event_id IS NOT NULL AND current_event_id IS NOT NULL)", name='ck_c23_state_fence'),
    )


class ResearchExperimentTerminationProof(AppBase):
    __tablename__ = 'research_experiment_termination_proof'
    id = Column(Uuid(as_uuid=True), primary_key=True)
    execution_id = Column(Uuid(as_uuid=True), nullable=False, unique=True)
    reservation_id = Column(Uuid(as_uuid=True), nullable=False)
    owner_user_id = Column(Uuid(as_uuid=True), nullable=False)
    envelope_sha256 = Column(String(64), nullable=False)
    closed_event_id = Column(Uuid(as_uuid=True), nullable=False)
    closed_fence = Column(BigInteger, nullable=False)
    binding_json = Column(Text, nullable=False)
    host_boot_id = Column(Uuid(as_uuid=True), nullable=False)
    journal_id = Column(Uuid(as_uuid=True), nullable=False)
    journal_epoch = Column(BigInteger, nullable=False)
    profile_sha256 = Column(String(64), nullable=False)
    cgroup_path = Column(String(63), nullable=False)
    cgroup_device = Column(BigInteger, nullable=False)
    cgroup_inode = Column(BigInteger, nullable=False)
    populated = Column(Integer, nullable=False)
    delete_exit_code = Column(Integer, nullable=False)
    create_intent_sequence = Column(Integer, nullable=False)
    cleanup_intent_sequence = Column(Integer, nullable=False)
    termination_sequence = Column(Integer, nullable=False)
    terminal_sequence = Column(Integer, nullable=False)
    cleanup_started_monotonic_ns = Column(BigInteger, nullable=False)
    delete_acknowledged_monotonic_ns = Column(BigInteger, nullable=False)
    populated_zero_monotonic_ns = Column(BigInteger, nullable=False)
    terminal_recorded_monotonic_ns = Column(BigInteger, nullable=False)
    issued_monotonic_ns = Column(BigInteger, nullable=False)
    trust_scope = Column(String(32), nullable=False)
    issuer_id = Column(String(96), nullable=False)
    key_id = Column(String(96), nullable=False)
    packet_bytes = Column(LargeBinary, nullable=False)
    for _name in ('create_intent_sha256', 'cleanup_intent_sha256', 'termination_sha256',
                  'terminal_head_sha256', 'terminal_result_sha256', 'delete_command_sha256',
                  'delete_acknowledgement_sha256', 'raw_observation_sha256', 'packet_sha256',
                  'signature_sha256', 'verification_policy_sha256', 'verification_key_sha256'):
        locals()[_name] = Column(String(64), nullable=False)
    del _name
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    __table_args__ = (
        _execution_fk('c23_proof'),
        ForeignKeyConstraint(['closed_event_id', 'execution_id', 'closed_fence'],
            ['research_experiment_execution_event.id', 'research_experiment_execution_event.execution_id',
             'research_experiment_execution_event.fence'], name='fk_c23_proof_closed_event', ondelete='RESTRICT'),
        UniqueConstraint('id', *BINDING_FIELDS, 'closed_fence', name='uq_c23_proof_release'),
        UniqueConstraint('packet_sha256', name='uq_c23_proof_packet'),
        CheckConstraint("closed_fence>=3 AND journal_epoch>=1 AND cgroup_device>=0 AND cgroup_inode>=1 AND populated=0 AND delete_exit_code=0", name='ck_c23_proof_kernel'),
        CheckConstraint("1<=create_intent_sequence AND create_intent_sequence<cleanup_intent_sequence AND cleanup_intent_sequence<termination_sequence AND termination_sequence<terminal_sequence AND terminal_sequence<=4096", name='ck_c23_proof_sequence'),
        CheckConstraint("0<=cleanup_started_monotonic_ns AND cleanup_started_monotonic_ns<=delete_acknowledged_monotonic_ns AND delete_acknowledged_monotonic_ns<=populated_zero_monotonic_ns AND populated_zero_monotonic_ns<=terminal_recorded_monotonic_ns AND terminal_recorded_monotonic_ns<=issued_monotonic_ns", name='ck_c23_proof_clock'),
        CheckConstraint("length(packet_bytes) BETWEEN 1 AND 16384 AND length(binding_json) BETWEEN 2 AND 8192 AND length(cgroup_path)=63", name='ck_c23_proof_bytes'),
        CheckConstraint("trust_scope IN ('synthetic-software-test','retained-operator') AND length(issuer_id) BETWEEN 1 AND 96 AND length(key_id) BETWEEN 1 AND 96", name='ck_c23_proof_issuer'),
        *_hash_checks('c23_proof', ('envelope_sha256', 'profile_sha256', 'create_intent_sha256', 'cleanup_intent_sha256', 'termination_sha256', 'terminal_head_sha256', 'terminal_result_sha256', 'delete_command_sha256', 'delete_acknowledgement_sha256', 'raw_observation_sha256', 'packet_sha256', 'signature_sha256', 'verification_policy_sha256', 'verification_key_sha256')),
    )


class ResearchExperimentRelease(AppBase):
    __tablename__ = 'research_experiment_release'
    id = Column(Uuid(as_uuid=True), primary_key=True)
    execution_id = Column(Uuid(as_uuid=True), nullable=False, unique=True)
    reservation_id = Column(Uuid(as_uuid=True), nullable=False, unique=True)
    owner_user_id = Column(Uuid(as_uuid=True), nullable=False)
    envelope_sha256 = Column(String(64), nullable=False)
    proof_id = Column(Uuid(as_uuid=True), nullable=False, unique=True)
    closed_fence = Column(BigInteger, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    __table_args__ = (
        _execution_fk('c23_release'),
        ForeignKeyConstraint(['proof_id', *BINDING_FIELDS, 'closed_fence'],
            ['research_experiment_termination_proof.' + name for name in ('id', *BINDING_FIELDS, 'closed_fence')],
            name='fk_c23_release_proof', ondelete='RESTRICT'),
        CheckConstraint('closed_fence>=3', name='ck_c23_release_fence'),
        *_hash_checks('c23_release', ('envelope_sha256',)),
    )


EXECUTION_MODELS = (ResearchExperimentExecution, ResearchExperimentExecutionEvent,
                    ResearchExperimentExecutionState, ResearchExperimentTerminationProof,
                    ResearchExperimentRelease)


def _immutable(*_):
    raise ValueError('C23 execution identity and history are immutable')


for _model in EXECUTION_MODELS:
    event.listen(_model, 'before_delete', _immutable)
    # State is mutated only by the privileged SQL functions, never generic ORM.
    event.listen(_model, 'before_update', _immutable)
