"""Default-off low-level C23 transactions on an explicitly isolated operator DB.

This store does not supply current C22 owner/source admission, a host proof
issuer, physical termination authority or scientific approval. The bridge must
hold C22's authority locks and repeat its callbacks/closing fence before reserve,
start and publication. Cleanup and release use independent recorder authority.
No serving route, worker registration or environment/database discovery exists.
"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
import hashlib
import json
import re
from typing import Callable
import uuid

from pydantic import BaseModel, ConfigDict, StringConstraints, model_validator
from typing import Annotated
from sqlalchemy import text

from db.experiment_execution_models import EXECUTION_MODELS
from orchestration.experiment_sandbox.contracts import SandboxError
from orchestration.experiment_sandbox.proofs import TerminationVerifierRegistry, verify_termination_packet
from schema.context_catalogue import canonical_json
from schema.experiment_execution import ClosedExecutionBinding, Digest, Hash, Job, Site, UUID

_IDENTIFIER = re.compile(r'^[a-z][a-z0-9_]{0,62}$')
_NAMESPACE = uuid.UUID('4188090c-7b91-4fb9-a91b-45b327deba09')


def _canonical(value):
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(',', ':'), allow_nan=False)


def _hash(raw):
    return hashlib.sha256(raw).hexdigest()


def _identifier(value):
    if type(value) is not str or not _IDENTIFIER.fullmatch(value):
        raise ValueError('Explicit simple PostgreSQL identifiers required')
    return value


def _disabled():
    return False


def planned_reservation_ids(*, site_id, owner_user_id, idempotency_key):
    """Stable new-operation IDs; this helper grants no reservation authority."""
    if type(idempotency_key) is not str or not 1 <= len(idempotency_key) <= 128:
        raise ValueError('Bounded idempotency key required')
    owner = str(uuid.UUID(owner_user_id))
    seed = _canonical({'site': site_id, 'owner': owner, 'key': idempotency_key})
    return (str(uuid.uuid5(_NAMESPACE, 'execution:' + seed)),
            str(uuid.uuid5(_NAMESPACE, 'reservation:' + seed)))


def execution_job_id(*, site_id, reservation_id, envelope_sha256):
    return 'c23-' + _hash(_canonical({'site': site_id, 'reservation': reservation_id,
                                     'envelope': envelope_sha256}).encode())[:48]


class ExecutionReservationBinding(BaseModel):
    """Trusted controller input, never evidence of current launch permission."""
    model_config = ConfigDict(extra='forbid', strict=True, frozen=True)
    execution_id: UUID
    reservation_id: UUID
    owner_user_id: UUID
    experiment_id: UUID
    proposal_revision_id: UUID
    approval_id: UUID
    site_id: Site
    idempotency_key: Annotated[str, StringConstraints(min_length=1, max_length=128)]
    request_json: Annotated[str, StringConstraints(min_length=2, max_length=65536)]
    envelope_json: Annotated[str, StringConstraints(min_length=2, max_length=1048576)]
    job_id: Job
    image_digest: Digest
    approval_request_sha256: Hash
    execution_request_sha256: Hash
    envelope_sha256: Hash
    worker_id: Hash
    source_sha256: Hash
    source_policy_sha256: Hash
    worker_source_sha256: Hash
    environment_sha256: Hash
    runtime_sha256: Hash
    profile_policy_sha256: Hash
    trusted_init_sha256: Hash
    adapter_source_sha256: Hash

    @model_validator(mode='after')
    def exact_bytes_and_ids(self):
        for name, digest in (('request_json', self.execution_request_sha256),
                             ('envelope_json', self.envelope_sha256)):
            raw = getattr(self, name)
            if canonical_json(json.loads(raw)) != raw or _hash(raw.encode()) != digest:
                raise ValueError('Exact canonical retained request/envelope required')
        if (self.execution_id, self.reservation_id) != planned_reservation_ids(
                site_id=self.site_id, owner_user_id=self.owner_user_id, idempotency_key=self.idempotency_key):
            raise ValueError('Execution operation IDs must be deterministic')
        if self.job_id != execution_job_id(site_id=self.site_id, reservation_id=self.reservation_id,
                                           envelope_sha256=self.envelope_sha256):
            raise ValueError('Job must match exact retained envelope')
        return self


@dataclass(frozen=True)
class ExecutionRolePolicy:
    serving_role: str
    controller_role: str
    verifier_role: str
    function_owner_role: str

    def __post_init__(self):
        names = [getattr(self, name) for name in self.__dataclass_fields__]
        for value in names:
            _identifier(value)
        if len(set(names)) != len(names):
            raise ValueError('Serving, controller, verifier and function owner must be separate roles')


@dataclass(frozen=True)
class ExecutionStoreConfig:
    site_id: str
    database_name: str
    schema: str
    controller_session_factory: object
    recorder_session_factory: object
    roles: ExecutionRolePolicy
    verifier_registry: TerminationVerifierRegistry
    store_scope: str
    enabled: Callable[[], bool] = _disabled

    def __post_init__(self):
        _identifier(self.database_name)
        _identifier(self.schema)
        if (type(self.site_id) is not str or not self.site_id.startswith('v1:')
                or self.store_scope != 'isolated-unmounted-operator'
                or not callable(self.controller_session_factory)
                or not callable(self.recorder_session_factory)
                or self.controller_session_factory is self.recorder_session_factory
                or type(self.roles) is not ExecutionRolePolicy
                or type(self.verifier_registry) is not TerminationVerifierRegistry
                or not callable(self.enabled)):
            raise ValueError('Explicit separate isolated operator factories, roles and verifier required')


# Objects are fixed names, interpolated schema/role identifiers are validated.
_TABLES = tuple(model.__tablename__ for model in EXECUTION_MODELS)
_FUNCTIONS = ('ocean_c23_execution_insert_guard()', 'ocean_c23_outbox_insert_guard()',
              'ocean_c23_state_guard()', 'ocean_c23_event_insert_guard()',
              'ocean_c23_closed_binding(uuid)', 'ocean_c23_proof_insert_guard()',
              'ocean_c23_release_insert_guard()', 'ocean_c23_reserve(jsonb)',
              'ocean_c23_record_event(jsonb,bigint)', 'ocean_c23_record_proof(jsonb)',
              'ocean_c23_release(uuid,uuid,bigint,uuid)')


def bootstrap_execution_roles(connection, *, schema, policy):
    """Explicit admin-only grants to existing roles; creates no role/credential.

    Use only on a dedicated unmounted operator schema. The migration cannot
    choose trusted principals. This function verifies exact existing role
    attributes and absence of role memberships before applying minimal grants.
    The schema owner remains trusted and may undo enforcement.
    """
    schema = _identifier(schema)
    if type(policy) is not ExecutionRolePolicy or connection.dialect.name != 'postgresql':
        raise ValueError('PostgreSQL and explicit role policy required')
    names = [getattr(policy, field) for field in policy.__dataclass_fields__]
    rows = connection.execute(text('SELECT rolname,rolsuper,rolcreaterole,rolcreatedb,rolreplication,rolbypassrls,rolcanlogin FROM pg_roles WHERE rolname=ANY(:names)'), {'names': names}).all()
    by_name = {row[0]: row for row in rows}
    if set(by_name) != set(names):
        raise ValueError('Explicit pre-existing execution roles required')
    for name in names:
        row = by_name[name]
        if any(row[1:6]) or row[6] != (name != policy.function_owner_role):
            raise ValueError('Restricted LOGIN principals and dedicated NOLOGIN function owner required')
    if connection.scalar(text('SELECT EXISTS(SELECT 1 FROM pg_auth_members m JOIN pg_roles a ON a.oid=m.member JOIN pg_roles b ON b.oid=m.roleid WHERE a.rolname=ANY(:names) OR b.rolname=ANY(:names))'), {'names': names}):
        raise ValueError('Execution roles must have no inherited membership or members')
    if connection.scalar(text('SELECT EXISTS(SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace JOIN pg_roles r ON r.oid=c.relowner WHERE n.nspname=:schema AND r.rolname=ANY(:names))'), {'schema': schema, 'names': names}):
        raise ValueError('Execution roles must not own operator tables')
    if connection.scalar(text('SELECT EXISTS(SELECT 1 FROM pg_namespace n JOIN pg_roles r ON r.oid=n.nspowner WHERE n.nspname=:schema AND r.rolname=ANY(:names)) OR EXISTS(SELECT 1 FROM pg_database d JOIN pg_roles r ON r.oid=d.datdba WHERE d.datname=current_database() AND r.rolname=ANY(:names))'), {'schema': schema, 'names': names}):
        raise ValueError('Execution roles must not own the operator schema or database')
    owner, controller, verifier, serving = (policy.function_owner_role, policy.controller_role,
                                         policy.verifier_role, policy.serving_role)
    # Revoke existing direct rights on every C23 object; do not change C22
    # serving grants or grant a recorder unrestricted ownership of its tables.
    connection.exec_driver_sql(f'REVOKE CREATE ON SCHEMA {schema} FROM PUBLIC')
    for role in names:
        connection.exec_driver_sql(f'REVOKE CREATE ON SCHEMA {schema} FROM {role}')
        connection.exec_driver_sql(f'GRANT USAGE ON SCHEMA {schema} TO {role}')
        for table in _TABLES:
            connection.exec_driver_sql(f'REVOKE ALL ON TABLE {schema}.{table} FROM {role}')
        for signature in _FUNCTIONS:
            connection.exec_driver_sql(f'REVOKE ALL ON FUNCTION {schema}.{signature} FROM {role}, PUBLIC')
    for table in _TABLES:
        connection.exec_driver_sql(f'GRANT SELECT ON TABLE {schema}.{table} TO {owner}, {controller}, {verifier}')
    for table in ('research_experiment_capacity','research_experiment_reservation','research_experiment_outbox',
                  'research_experiment_revision','research_experiment_approval','research_experiment','research_investigation'):
        connection.exec_driver_sql(f'GRANT SELECT ON TABLE {schema}.{table} TO {owner}')
    connection.exec_driver_sql(f'GRANT UPDATE(id) ON TABLE {schema}.research_experiment_capacity TO {owner}')
    connection.exec_driver_sql(f'GRANT INSERT, UPDATE(state,updated_at) ON TABLE {schema}.research_experiment_reservation TO {owner}')
    for table in _TABLES:
        connection.exec_driver_sql(f'GRANT INSERT ON TABLE {schema}.{table} TO {owner}')
    connection.exec_driver_sql(f'GRANT UPDATE ON TABLE {schema}.research_experiment_execution_state TO {owner}')
    # PostgreSQL requires temporary CREATE for ALTER FUNCTION OWNER. Revoke it
    # before returning, inside the same transaction.
    connection.exec_driver_sql(f'GRANT CREATE ON SCHEMA {schema} TO {owner}')
    for signature in _FUNCTIONS:
        connection.exec_driver_sql(f'ALTER FUNCTION {schema}.{signature} OWNER TO {owner}')
    connection.exec_driver_sql(f'REVOKE CREATE ON SCHEMA {schema} FROM {owner}')
    for signature in ('ocean_c23_reserve(jsonb)', 'ocean_c23_record_event(jsonb,bigint)'):
        connection.exec_driver_sql(f'GRANT EXECUTE ON FUNCTION {schema}.{signature} TO {controller}')
    for signature in ('ocean_c23_closed_binding(uuid)', 'ocean_c23_record_proof(jsonb)',
                      'ocean_c23_release(uuid,uuid,bigint,uuid)'):
        connection.exec_driver_sql(f'GRANT EXECUTE ON FUNCTION {schema}.{signature} TO {verifier}')
    # serving deliberately receives no execution-table or function privilege.
    assert serving not in (controller, verifier, owner)


class C23ExecutionStore:
    def __init__(self, *, config):
        if type(config) is not ExecutionStoreConfig:
            raise ValueError('Explicit execution store configuration required')
        self.config = config
        self._controller_token = object()

    def _enabled(self):
        if self.config.enabled() is not True:
            raise SandboxError('sandbox_execution_store_disabled')

    def _check_session(self, session, role):
        if session.get_bind().dialect.name != 'postgresql':
            raise SandboxError('sandbox_execution_postgresql_required')
        row = session.execute(text('SELECT current_user,session_user,current_database(),current_schema(),'
            '(SELECT rolsuper OR rolcreaterole OR rolcreatedb OR rolreplication OR rolbypassrls FROM pg_roles WHERE rolname=current_user)')).one()
        if (tuple(row[:4]) != (role, role, self.config.database_name, self.config.schema) or row[4] is not False):
            raise SandboxError('sandbox_execution_role_boundary')
        # Ensure the named SECURITY DEFINER operation is independently owned and
        # serving cannot execute it, even when the supplied factory is wrong.
        policy = self.config.roles
        checks = session.execute(text('SELECT p.proname,p.prosecdef,r.rolname,p.proconfig,'
            'has_function_privilege(:serving,p.oid,\'EXECUTE\'),'
            'has_function_privilege(:controller,p.oid,\'EXECUTE\'),'
            'has_function_privilege(:verifier,p.oid,\'EXECUTE\') FROM pg_proc p '
            'JOIN pg_namespace n ON n.oid=p.pronamespace JOIN pg_roles r ON r.oid=p.proowner '
            "WHERE n.nspname=:schema AND p.proname LIKE 'ocean_c23_%'"),
            {'serving': policy.serving_role, 'controller': policy.controller_role,
             'verifier': policy.verifier_role, 'schema': self.config.schema}).all()
        expected_functions = {signature.split('(', 1)[0] for signature in _FUNCTIONS}
        if len(checks) != len(expected_functions) or {entry[0] for entry in checks} != expected_functions:
            raise SandboxError('sandbox_execution_role_boundary')
        expected_path = ['pg_catalog', self.config.schema, 'pg_temp']
        for name, security_definer, owner, settings, serving_execute, controller_execute, verifier_execute in checks:
            paths = [value.split('=', 1)[1] for value in (settings or []) if value.startswith('search_path=')]
            expected_controller = name in {'ocean_c23_reserve', 'ocean_c23_record_event'}
            expected_verifier = name in {'ocean_c23_closed_binding', 'ocean_c23_record_proof', 'ocean_c23_release'}
            if (security_definer is not True or owner != policy.function_owner_role or serving_execute is not False
                    or controller_execute != expected_controller or verifier_execute != expected_verifier
                    or len(paths) != 1 or [part.strip().strip(chr(34)) for part in paths[0].split(',')] != expected_path):
                raise SandboxError('sandbox_execution_role_boundary')
        unsafe = session.scalar(text('SELECT EXISTS(SELECT 1 FROM pg_roles r WHERE r.rolname=ANY(:names) AND '
            '(r.rolsuper OR r.rolcreaterole OR r.rolcreatedb OR r.rolreplication OR r.rolbypassrls '
            'OR r.rolcanlogin<>(r.rolname<>:owner))) OR '
            'EXISTS(SELECT 1 FROM pg_auth_members m JOIN pg_roles r ON r.oid=m.member OR r.oid=m.roleid WHERE r.rolname=ANY(:names)) OR '
            'EXISTS(SELECT 1 FROM pg_namespace n JOIN pg_roles r ON r.oid=n.nspowner WHERE n.nspname=:schema AND r.rolname=ANY(:names)) OR '
            'EXISTS(SELECT 1 FROM pg_database d JOIN pg_roles r ON r.oid=d.datdba WHERE d.datname=current_database() AND r.rolname=ANY(:names)) OR '
            'EXISTS(SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname=:schema '
            "AND c.relname=ANY(:tables) AND (has_table_privilege(:serving,c.oid,'INSERT,UPDATE,DELETE,TRUNCATE,TRIGGER,REFERENCES') "
            "OR has_table_privilege(:controller,c.oid,'INSERT,UPDATE,DELETE,TRUNCATE,TRIGGER,REFERENCES') "
            "OR has_table_privilege(:verifier,c.oid,'INSERT,UPDATE,DELETE,TRUNCATE,TRIGGER,REFERENCES') "
            "OR has_any_column_privilege(:serving,c.oid,'INSERT,UPDATE,REFERENCES') "
            "OR has_any_column_privilege(:controller,c.oid,'INSERT,UPDATE,REFERENCES') "
            "OR has_any_column_privilege(:verifier,c.oid,'INSERT,UPDATE,REFERENCES')))"),
            {'names': [getattr(policy, field) for field in policy.__dataclass_fields__],
             'owner': policy.function_owner_role, 'schema': self.config.schema,
             'serving': policy.serving_role, 'controller': policy.controller_role,
             'verifier': policy.verifier_role, 'tables': list(_TABLES)})
        if unsafe is not False:
            raise SandboxError('sandbox_execution_role_boundary')

    @contextmanager
    def controller_transaction(self, *, cleanup=False):
        """Only sessions yielded here are accepted for bridge-side mutations."""
        if cleanup is not True:
            self._enabled()
        with self.config.controller_session_factory.begin() as session:
            self._check_session(session, self.config.roles.controller_role)
            session.info[self._controller_token] = self
            try:
                yield session
            finally:
                session.info.pop(self._controller_token, None)

    def _controller(self, session, *, cleanup=False):
        if cleanup is not True:
            self._enabled()
        if session.info.get(self._controller_token) is not self or not session.in_transaction():
            raise SandboxError('sandbox_execution_controller_transaction')
        self._check_session(session, self.config.roles.controller_role)

    def _call(self, session, expression, parameters):
        return str(session.scalar(text(f'SELECT {self.config.schema}.{expression}'), parameters))

    def reserve_in_transaction(self, session, binding):
        """Call only after current C22 callbacks and closing fence in this txn."""
        self._controller(session)
        if type(binding) is not ExecutionReservationBinding or binding.site_id != self.config.site_id:
            raise SandboxError('sandbox_execution_binding')
        binding = ExecutionReservationBinding.model_validate(binding.model_dump(mode='python'))
        return self._call(session, 'ocean_c23_reserve(CAST(:p AS jsonb))', {'p': _canonical(binding.model_dump())})

    def record_event_in_transaction(self, session, *, execution_id, expected_fence,
                                    event_id, kind, start_id, host_boot_id, journal_id,
                                    journal_epoch, profile_sha256, preceding_journal_sha256,
                                    result_sha256=None):
        """Consume one start or retain publication/close history; no host permit.

        Replayed start intent is reconciliation data. It must never trigger a
        second physical start. Publication admission belongs to the root bridge.
        Closing remains independent of owner/source permission.
        """
        self._controller(session, cleanup=kind == 'closed')
        if kind not in {'start_consumed', 'publication_retained', 'closed'}:
            raise SandboxError('sandbox_execution_event')
        row = session.execute(text(f'SELECT reservation_id,owner_user_id,envelope_sha256 FROM {self.config.schema}.research_experiment_execution WHERE execution_id=CAST(:id AS uuid) AND site_id=:site'),
            {'id': execution_id, 'site': self.config.site_id}).one()
        p = {'id': str(uuid.UUID(event_id)), 'execution_id': str(uuid.UUID(execution_id)),
             'reservation_id': str(row[0]), 'owner_user_id': str(row[1]), 'envelope_sha256': row[2],
             'fence': expected_fence + 1, 'kind': kind, 'start_id': str(uuid.UUID(start_id)),
             'host_boot_id': str(uuid.UUID(host_boot_id)), 'journal_id': str(uuid.UUID(journal_id)),
             'journal_epoch': journal_epoch, 'profile_sha256': profile_sha256,
             'preceding_journal_sha256': preceding_journal_sha256, 'result_sha256': result_sha256}
        return self._call(session, 'ocean_c23_record_event(CAST(:p AS jsonb),:f)', {'p': _canonical(p), 'f': expected_fence})

    @contextmanager
    def _recorder_transaction(self):
        # Cleanup/proof/release deliberately do not consult launch enablement.
        # Independent configured recorder authority remains after revocation.
        with self.config.recorder_session_factory.begin() as session:
            self._check_session(session, self.config.roles.verifier_role)
            yield session

    def load_closed_binding(self, execution_id):
        with self._recorder_transaction() as session:
            raw = session.scalar(text(f'SELECT {self.config.schema}.ocean_c23_closed_binding(CAST(:id AS uuid))'), {'id': execution_id})
            binding = ClosedExecutionBinding.model_validate(raw)
            if binding.site_id != self.config.site_id:
                raise SandboxError('sandbox_execution_binding')
            return binding

    def record_verified_termination(self, *, execution_id, packet_bytes):
        """Reverify raw bytes against retained closed rows and pinned registry.

        A caller-created VerifiedTerminationPacket or Boolean is not accepted.
        Restricted recorder credentials are the DB authentication boundary.
        Protocol authentication still establishes assertions only; the real
        physical issuer/adapter and acceptance remain separate requirements.
        """
        if type(packet_bytes) is not bytes:
            raise SandboxError('sandbox_termination_unverified')
        with self._recorder_transaction() as session:
            raw = session.scalar(text(f'SELECT {self.config.schema}.ocean_c23_closed_binding(CAST(:id AS uuid))'), {'id': execution_id})
            expected = ClosedExecutionBinding.model_validate(raw)
            if expected.site_id != self.config.site_id:
                raise SandboxError('sandbox_execution_binding')
            verified = verify_termination_packet(packet_bytes, expected=expected, registry=self.config.verifier_registry)
            claims = verified.claims
            b, j, k = claims.binding, claims.journal, claims.kernel
            event = session.scalar(text(f'SELECT current_event_id FROM {self.config.schema}.research_experiment_execution_state WHERE execution_id=CAST(:id AS uuid)'), {'id': execution_id})
            proof_id = str(uuid.uuid5(_NAMESPACE, 'proof:' + verified.packet_sha256))
            p = {'id': proof_id, 'execution_id': b.execution_id, 'reservation_id': b.reservation_id,
                'owner_user_id': b.owner_user_id, 'envelope_sha256': b.envelope_sha256,
                'closed_event_id': str(event), 'closed_fence': b.closed_fence,
                'binding_json': _canonical(b.model_dump()), 'host_boot_id': b.host_boot_id,
                'journal_id': b.journal_id, 'journal_epoch': b.journal_epoch, 'profile_sha256': b.profile_sha256,
                **j.model_dump(), **k.model_dump(exclude={'delete_job_id','delete_runtime_sha256','delete_host_boot_id'}),
                'trust_scope': verified.trust_scope, 'issuer_id': verified.issuer_id, 'key_id': verified.key_id,
                'packet_bytes': '\\x' + packet_bytes.hex(), 'packet_sha256': verified.packet_sha256,
                'signature_sha256': verified.signature_sha256,
                'verification_policy_sha256': verified.verification_policy_sha256,
                'verification_key_sha256': verified.verification_key_sha256}
            return self._call(session, 'ocean_c23_record_proof(CAST(:p AS jsonb))', {'p': _canonical(p)})

    def release_terminated(self, *, execution_id, proof_id, expected_fence):
        """Atomic proof-correlated capacity release; conveys no result success."""
        release_id = str(uuid.uuid5(_NAMESPACE, 'release:' + str(execution_id) + ':' + str(proof_id)))
        with self._recorder_transaction() as session:
            site = session.scalar(text(f'SELECT site_id FROM {self.config.schema}.research_experiment_execution WHERE execution_id=CAST(:e AS uuid)'), {'e': execution_id})
            if site != self.config.site_id:
                raise SandboxError('sandbox_execution_binding')
            return self._call(session, 'ocean_c23_release(CAST(:e AS uuid),CAST(:p AS uuid),:f,CAST(:r AS uuid))',
                {'e': execution_id, 'p': proof_id, 'f': expected_fence, 'r': release_id})
