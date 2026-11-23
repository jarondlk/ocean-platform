"""Restricted PostgreSQL readback for the authenticated experiment workspace."""
from contextlib import contextmanager
from dataclasses import dataclass

from sqlalchemy import text

from db.experiment_execution_models import ResearchExperimentExecution
from orchestration.experiment_sandbox.contracts import SandboxError
from orchestration.experiment_sandbox.execution_store import _identifier
from orchestration.experiment_sandbox.proofs import TerminationVerifierRegistry


_READ_COLUMNS = {
    'research_experiment_execution': tuple(ResearchExperimentExecution.__table__.columns.keys()),
    'research_experiment_execution_state': ('execution_id', 'state', 'fence', 'start_event_id', 'current_event_id'),
    'research_experiment_execution_event': ('execution_id', 'id', 'fence', 'kind', 'host_boot_id', 'journal_id',
        'journal_epoch', 'profile_sha256', 'result_sha256', 'terminal_sequence', 'terminal_head_sha256'),
    'research_experiment_release': ('id', 'execution_id', 'proof_id'),
    'research_experiment_termination_proof': ('id', 'closed_event_id', 'closed_fence', 'packet_bytes', 'packet_sha256'),
}
_EXPECTED_READS = {(table, column) for table, columns in _READ_COLUMNS.items() for column in columns}


@dataclass(frozen=True)
class RetainedLedgerReaderConfig:
    site_id: str
    database_name: str
    schema: str
    role: str
    session_factory: object
    verifier_registry: TerminationVerifierRegistry

    def __post_init__(self):
        for name in (self.database_name, self.schema, self.role):
            _identifier(name)
        if (type(self.site_id) is not str or not self.site_id.startswith('v1:')
                or not callable(self.session_factory)
                or type(self.verifier_registry) is not TerminationVerifierRegistry):
            raise ValueError('An explicit v1 ledger reader is required')


def _read_privileges(connection, config):
    parameters = {'role': config.role, 'schema': config.schema}
    safe = connection.scalar(text('''
        SELECT r.rolcanlogin AND NOT (r.rolsuper OR r.rolcreaterole OR r.rolcreatedb
            OR r.rolreplication OR r.rolbypassrls)
          AND NOT EXISTS (SELECT 1 FROM pg_auth_members m WHERE r.oid IN (m.member,m.roleid))
          AND NOT EXISTS (SELECT 1 FROM pg_database d WHERE d.datdba=r.oid)
          AND NOT EXISTS (SELECT 1 FROM pg_namespace n WHERE n.nspowner=r.oid)
          AND NOT has_database_privilege(r.oid,current_database(),'CREATE')
          AND NOT has_schema_privilege(r.oid,:schema,'CREATE')
          AND NOT EXISTS (
            SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
            WHERE n.nspname=:schema AND CASE
              WHEN c.relkind IN ('r','p','v','m','f') THEN
                has_table_privilege(r.oid,c.oid,'INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER')
                OR has_any_column_privilege(r.oid,c.oid,'INSERT,UPDATE,REFERENCES')
              WHEN c.relkind='S' THEN has_sequence_privilege(r.oid,c.oid,'USAGE,UPDATE,SELECT')
              ELSE false END)
          AND NOT EXISTS (
            SELECT 1 FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
            WHERE n.nspname=:schema AND (p.prosecdef OR p.proname LIKE 'ocean_c23_%')
              AND has_function_privilege(r.oid,p.oid,'EXECUTE'))
        FROM pg_roles r WHERE r.rolname=:role
    '''), parameters)
    if safe is not True:
        raise SandboxError('sandbox_ledger_reader_role_boundary')
    rows = connection.execute(text('''
        SELECT c.relname,a.attname FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
        JOIN pg_attribute a ON a.attrelid=c.oid
        WHERE n.nspname=:schema AND c.relkind IN ('r','p','v','m','f')
          AND a.attnum > 0 AND NOT a.attisdropped
          AND has_column_privilege(:role,c.oid,a.attnum,'SELECT')
    '''), parameters)
    return {tuple(row) for row in rows}


def bootstrap_ledger_reader(connection, *, config):
    """Grant exact projection columns to a pre-existing restricted login."""
    if type(config) is not RetainedLedgerReaderConfig or connection.dialect.name != 'postgresql':
        raise ValueError('Explicit PostgreSQL ledger reader setup required')
    row = connection.execute(text('''
        SELECT current_database(),current_schema(),current_user,session_user,pg_get_userbyid(n.nspowner)
        FROM pg_namespace n WHERE n.nspname=:schema
    '''), {'schema': config.schema}).one()
    if (tuple(row[:2]) != (config.database_name, config.schema)
            or row[2] != row[3] or row[2] != row[4]
            or not _read_privileges(connection, config) <= _EXPECTED_READS):
        raise SandboxError('sandbox_ledger_reader_role_boundary')
    connection.exec_driver_sql(f'GRANT USAGE ON SCHEMA {config.schema} TO {config.role}')
    for table, columns in _READ_COLUMNS.items():
        connection.exec_driver_sql(f'GRANT SELECT ({", ".join(columns)}) ON {config.schema}.{table} TO {config.role}')
    if _read_privileges(connection, config) != _EXPECTED_READS:
        raise SandboxError('sandbox_ledger_reader_role_boundary')


class RetainedLedgerReader:
    def __init__(self, *, config):
        if type(config) is not RetainedLedgerReaderConfig:
            raise ValueError('Explicit ledger reader configuration required')
        self.config = config

    @contextmanager
    def transaction(self):
        config = self.config
        with config.session_factory.begin() as session:
            if session.get_bind().dialect.name != 'postgresql':
                raise SandboxError('sandbox_ledger_reader_role_boundary')
            session.execute(text('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY'))
            identity = session.execute(text('SELECT current_database(),current_schema(),current_user,session_user')).one()
            if (tuple(identity) != (config.database_name, config.schema, config.role, config.role)
                    or _read_privileges(session, config) != _EXPECTED_READS):
                raise SandboxError('sandbox_ledger_reader_role_boundary')
            yield session
