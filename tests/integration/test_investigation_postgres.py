"""C17 acceptance on an explicitly identified disposable PostgreSQL database.

Only C17_TEST_DATABASE_URL is accepted. Each test owns a random schema, checks
the observed server before creating anything, and verifies its schema is gone.
The separate Alembic process receives only that validated database target.
"""
from __future__ import annotations

import importlib
import ipaddress
import os
from pathlib import Path
import re
import subprocess
import sys
import uuid

from alembic.migration import MigrationContext
from alembic.operations import Operations
import pytest
from sqlalchemy import create_engine, inspect, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError, DBAPIError
from sqlalchemy.orm import sessionmaker

from db.app_models import (
    AppUser,
    AuditEvent,
    ChatInteraction,
    ResearchContextOperation,
    ResearchContextRevision,
    ResearchConversation,
    ResearchInvestigation,
)


pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_POSTGRES_INTEGRATION") != "1",
    reason="requires explicitly verified disposable C17 PostgreSQL",
)

ROOT = Path(__file__).resolve().parents[2]
MIGRATION = "migrations.versions.20261018_0017_investigations"
TABLES = (
    "research_investigation", "research_conversation",
    "research_context_revision", "research_context_operation",
)


def allowed_disposable_server_address(address):
    """Require loopback, or the exact workflow-owned RFC1918 IPv4 peer."""
    try:
        observed = ipaddress.ip_address(address or "")
    except ValueError:
        return False
    if observed.is_loopback:
        return True
    if os.environ.get("GITHUB_ACTIONS") != "true":
        return False
    try:
        pinned = ipaddress.ip_address(os.environ.get("C17_TEST_SERVER_ADDRESS", ""))
    except ValueError:
        return False
    return observed == pinned and any(observed in ipaddress.ip_network(network) for network in (
        "10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16",
    ))


def configured_disposable_url():
    raw = os.environ.get("C17_TEST_DATABASE_URL")
    if not raw:
        raise ValueError("C17_TEST_DATABASE_URL is required; DATABASE_URL is never used")
    try:
        url = make_url(raw)
    except ArgumentError as error:
        raise ValueError("C17_TEST_DATABASE_URL must be a PostgreSQL URL") from error
    if (
        url.get_backend_name() != "postgresql"
        or url.host not in {"127.0.0.1", "localhost", "::1"}
        or not re.fullmatch(r"ocean_c17_[a-z0-9_]+", url.database or "")
        or url.query
    ):
        raise ValueError("C17 URL must identify a dedicated ocean_c17_* loopback PostgreSQL database without query overrides")
    return url


@pytest.fixture(scope="module")
def disposable_database():
    try:
        url = configured_disposable_url()
    except ValueError as error:
        pytest.fail(str(error))
    engine = create_engine(url, pool_pre_ping=True)
    try:
        with engine.connect() as connection:
            identity = connection.execute(text(
                "SELECT current_database(), host(inet_server_addr()), inet_server_port(), "
                "current_setting('server_version'), current_setting('transaction_isolation')"
            )).one()
            assert identity[0] == url.database
            assert allowed_disposable_server_address(identity[1]), "Observed server is not the verified disposable C17 server"
            assert identity[4] == "read committed"
        print(f"C17 disposable PostgreSQL identity: database={identity[0]} address={identity[1]} port={identity[2]} version={identity[3]} isolation={identity[4]}")
        yield engine, url
    finally:
        engine.dispose()


@pytest.fixture
def isolated(disposable_database):
    observer, url = disposable_database
    schema = f"c17_{uuid.uuid4().hex}"
    with observer.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    options = f"-csearch_path={schema} -clock_timeout=8000 -cstatement_timeout=20000"
    engine = create_engine(url, pool_pre_ping=True, connect_args={"options": options})
    bundle = {"engine": engine, "observer": observer, "schema": schema, "url": url, "options": options}
    try:
        yield bundle
    finally:
        engine.dispose()
        with observer.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
            remaining = connection.scalar(text("SELECT count(*) FROM pg_namespace WHERE nspname=:schema"), {"schema": schema})
            assert remaining == 0
        print(f"C17 disposable schema cleanup: {schema} remaining=0")


def alembic(database, action, target, *, succeeds=True):
    # The parent has already verified the dedicated target's actual identity.
    # Replace the child's application URL explicitly; never inherit an app URL.
    child = dict(os.environ)
    child.update(
        DATABASE_URL=database["url"].update_query_dict({"options": database["options"]}).render_as_string(hide_password=False),
        AUTH_MODE="disabled", DEPLOYMENT_ENV="test", ENABLE_MOCK_LOGIN="false",
        PERSIST_LOCAL_CHAT="false",
    )
    result = subprocess.run(
        [sys.executable, "-m", "alembic", action, target], cwd=ROOT, env=child,
        capture_output=True, text=True, timeout=90, check=False,
    )
    if succeeds:
        assert result.returncode == 0, result.stderr
    else:
        assert result.returncode != 0, "Populated downgrade unexpectedly succeeded"
    print(f"C17 Alembic {action} {target}: exit={result.returncode} schema={database['schema']}")
    return result


def revision(database):
    with database["engine"].connect() as connection:
        return connection.scalar(text("SELECT version_num FROM alembic_version"))


def assert_schema_matches_models(engine):
    reflected = inspect(engine)
    for model in (ResearchInvestigation, ResearchConversation, ResearchContextRevision, ResearchContextOperation):
        table = model.__table__
        columns = reflected.get_columns(table.name)
        assert [(column["name"], column["nullable"]) for column in columns] == [(column.name, column.nullable) for column in table.columns]
        assert {entry["name"] for entry in reflected.get_check_constraints(table.name)} == {
            constraint.name for constraint in table.constraints if constraint.__class__.__name__ == "CheckConstraint"
        }
        assert {entry["name"] for entry in reflected.get_unique_constraints(table.name)} == {
            constraint.name for constraint in table.constraints if constraint.__class__.__name__ == "UniqueConstraint"
        }
        assert {entry["name"] for entry in reflected.get_indexes(table.name) if not entry.get("duplicates_constraint")} == {index.name for index in table.indexes}
        actual_foreign_keys = {
            (tuple(entry["constrained_columns"]), entry["referred_table"], tuple(entry["referred_columns"]), entry["options"].get("ondelete"), entry["options"].get("deferrable", False), entry["options"].get("initially"))
            for entry in reflected.get_foreign_keys(table.name)
        }
        expected_foreign_keys = {
            (tuple(element.parent.name for element in constraint.elements), constraint.referred_table.name,
             tuple(element.column.name for element in constraint.elements), constraint.ondelete,
             bool(constraint.deferrable), constraint.initially)
            for constraint in table.foreign_key_constraints
        }
        assert actual_foreign_keys == expected_foreign_keys


def seed(database):
    factory = sessionmaker(database["engine"], expire_on_commit=False)
    owners = [uuid.uuid4(), uuid.uuid4()]
    investigations = [uuid.uuid4(), uuid.uuid4(), uuid.uuid4()]
    revisions = [uuid.uuid4(), uuid.uuid4(), uuid.uuid4()]
    with factory.begin() as session:
        session.add_all([
            AppUser(id=owner, auth_provider="synthetic-c17", auth_subject=str(owner), email=f"{owner}@invalid.test")
            for owner in owners
        ])
        session.flush()
        session.add_all([
            ResearchInvestigation(id=identity, user_id=owners[index == 2], name=f"Synthetic investigation {index}")
            for index, identity in enumerate(investigations)
        ])
        session.flush()
        session.add_all([
            ResearchContextRevision(id=identity, investigation_id=investigations[index], sequence=1,
                snapshot_id="a" * 64, payload_json='{"synthetic":true}', payload_sha256="b" * 64,
                created_by_user_id=owners[index == 2])
            for index, identity in enumerate(revisions)
        ])
        session.flush()
        for investigation, head in zip(investigations, revisions, strict=True):
            record = session.get(ResearchInvestigation, investigation)
            record.head_revision_id, record.status = head, "active"
        conversation = ResearchConversation(investigation_id=investigations[0], name="Synthetic conversation")
        operation = ResearchContextOperation(user_id=owners[0], investigation_id=investigations[0],
            idempotency_key="synthetic-operation", kind="attach", expected_head_id=revisions[0],
            candidate_revision_id=uuid.uuid4(), request_json="{}", request_sha256="c" * 64,
            candidate_json="{}", references_json="[]", state="prepared")
        session.add_all([conversation, operation])
    return {"owners": owners, "investigations": investigations, "revisions": revisions,
            "conversation": conversation.id, "operation": operation.id, "factory": factory}


@pytest.fixture
def stored(isolated):
    # Core guards execute the actual new migration with its prerequisites, while
    # dedicated acceptance below exercises the complete real Alembic history.
    AppUser.__table__.create(isolated["engine"])
    with isolated["engine"].begin() as connection:
        with Operations.context(MigrationContext.configure(connection)):
            importlib.import_module(MIGRATION).upgrade()
    isolated.update(seed(isolated))
    return isolated


def test_fresh_full_alembic_head_and_repeat_upgrade_match_models(isolated):
    alembic(isolated, "upgrade", "head")
    assert revision(isolated) == "20261019_0019"
    assert_schema_matches_models(isolated["engine"])
    isolated.update(seed(isolated))
    alembic(isolated, "upgrade", "head")
    assert revision(isolated) == "20261019_0019"
    with isolated["factory"]() as session:
        assert session.get(ResearchContextRevision, isolated["revisions"][0]).payload_json == '{"synthetic":true}'


def test_populated_0016_alembic_upgrade_preserves_prior_application_history(isolated):
    alembic(isolated, "upgrade", "20261005_0016")
    owner, chat, audit = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    factory = sessionmaker(isolated["engine"])
    with factory.begin() as session:
        session.add(AppUser(id=owner, auth_provider="synthetic-c17", auth_subject=str(owner), email=f"{owner}@invalid.test"))
        session.flush()
        session.add(ChatInteraction(id=chat, user_id=owner, status="completed", query="Synthetic prior query", answer="Preserved prior evidence", request_options={}, evidence_snapshot={"synthetic": True}, legal_hold=True))
        session.add(AuditEvent(id=audit, actor_user_id=owner, action="synthetic.c17.preexisting", metadata_json={"preserved": True}))
    alembic(isolated, "upgrade", "head")
    assert revision(isolated) == "20261019_0019"
    assert_schema_matches_models(isolated["engine"])
    with factory() as session:
        assert session.get(ChatInteraction, chat).evidence_snapshot == {"synthetic": True}
        assert session.get(ChatInteraction, chat).legal_hold is True
        assert session.get(AuditEvent, audit).metadata_json == {"preserved": True}


def test_empty_alembic_downgrade_and_reupgrade_are_reversible(isolated):
    alembic(isolated, "upgrade", "head")
    alembic(isolated, "downgrade", "20261005_0016")
    assert revision(isolated) == "20261005_0016"
    assert not set(TABLES) & set(inspect(isolated["engine"]).get_table_names())
    alembic(isolated, "upgrade", "head")
    assert_schema_matches_models(isolated["engine"])


def test_populated_alembic_downgrade_is_rejected_and_keeps_history(isolated):
    alembic(isolated, "upgrade", "head")
    isolated.update(seed(isolated))
    result = alembic(isolated, "downgrade", "20261005_0016", succeeds=False)
    assert "populated C17 storage cannot be downgraded" in result.stderr
    assert revision(isolated) == "20261019_0019"
    with isolated["factory"]() as session:
        assert session.get(ResearchContextRevision, isolated["revisions"][0]).payload_json == '{"synthetic":true}'
        assert session.get(ResearchConversation, isolated["conversation"])
        assert session.get(ResearchContextOperation, isolated["operation"])


@pytest.mark.parametrize("field,expression", [
    ("id", "gen_random_uuid()"), ("investigation_id", "gen_random_uuid()"),
    ("sequence", "99"), ("predecessor_revision_id", "gen_random_uuid()"),
    ("snapshot_id", "repeat('d',64)"), ("payload_json", "'{}'"),
    ("payload_sha256", "repeat('e',64)"), ("created_by_user_id", "gen_random_uuid()"),
    ("created_at", "CURRENT_TIMESTAMP + interval '1 day'"),
])
def test_direct_sql_revision_update_cannot_rewrite_any_evidence_field(stored, field, expression):
    with pytest.raises(DBAPIError, match="append-only"):
        with stored["engine"].begin() as connection:
            connection.execute(text(f"UPDATE research_context_revision SET {field}={expression} WHERE id=:identity"), {"identity": stored["revisions"][0]})


@pytest.mark.parametrize("field,expression", [
    ("id", "gen_random_uuid()"), ("user_id", "gen_random_uuid()"),
    ("investigation_id", "gen_random_uuid()"), ("idempotency_key", "'new-key'"),
    ("kind", "'pin'"), ("expected_head_id", "NULL"),
    ("candidate_revision_id", "gen_random_uuid()"), ("request_json", "'{\"changed\": true}'"),
    ("request_sha256", "repeat('d',64)"), ("candidate_json", "'{\"changed\": true}'"),
    ("references_json", "'[\"changed\"]'"), ("created_at", "CURRENT_TIMESTAMP + interval '1 day'"),
])
def test_direct_sql_operation_cannot_rewrite_prepared_inputs(stored, field, expression):
    with pytest.raises(DBAPIError, match="immutable"):
        with stored["engine"].begin() as connection:
            connection.execute(text(f"UPDATE research_context_operation SET {field}={expression} WHERE id=:identity"), {"identity": stored["operation"]})


@pytest.mark.parametrize("table,field,expression", [
    ("research_investigation", "id", "gen_random_uuid()"),
    ("research_investigation", "user_id", "gen_random_uuid()"),
    ("research_investigation", "predecessor_investigation_id", "gen_random_uuid()"),
    ("research_investigation", "predecessor_revision_id", "gen_random_uuid()"),
    ("research_investigation", "created_at", "CURRENT_TIMESTAMP + interval '1 day'"),
    ("research_conversation", "id", "gen_random_uuid()"),
    ("research_conversation", "investigation_id", "gen_random_uuid()"),
    ("research_conversation", "created_at", "CURRENT_TIMESTAMP + interval '1 day'"),
])
def test_direct_sql_cannot_transfer_investigation_or_conversation_identity(stored, table, field, expression):
    with pytest.raises(DBAPIError, match="immutable"):
        with stored["engine"].begin() as connection:
            connection.execute(text(f"UPDATE {table} SET {field}={expression}"))


@pytest.mark.parametrize("table", TABLES)
def test_direct_sql_delete_is_rejected_for_retained_history(stored, table):
    with pytest.raises(DBAPIError, match="append-only|retained"):
        with stored["engine"].begin() as connection:
            connection.execute(text(f"DELETE FROM {table}"))


@pytest.mark.parametrize("table", TABLES)
def test_direct_sql_truncate_cascade_is_rejected_for_retained_history(stored, table):
    with pytest.raises(DBAPIError, match="append-only"):
        with stored["engine"].begin() as connection:
            connection.execute(text(f"TRUNCATE {table} CASCADE"))
    with stored["factory"]() as session:
        assert session.get(ResearchContextRevision, stored["revisions"][0])
        assert session.get(ResearchContextOperation, stored["operation"])


def test_direct_sql_operation_state_and_retirement_can_advance_without_mutating_evidence(stored):
    with stored["engine"].begin() as connection:
        connection.execute(text("UPDATE research_context_operation SET state='uncertain', error_code='synthetic-commit-unknown', updated_at=CURRENT_TIMESTAMP"))
        connection.execute(text("UPDATE research_investigation SET legal_hold=true, status='retired', retired_at=CURRENT_TIMESTAMP, metadata_version=metadata_version+1"))
        connection.execute(text("UPDATE research_conversation SET name='Renamed synthetic conversation', metadata_version=metadata_version+1"))
    with stored["factory"]() as session:
        assert session.get(ResearchContextOperation, stored["operation"]).state == "uncertain"
        assert session.get(ResearchContextOperation, stored["operation"]).references_json == "[]"
        assert session.get(ResearchContextRevision, stored["revisions"][0]).payload_json == '{"synthetic":true}'
        assert session.get(ResearchInvestigation, stored["investigations"][0]).legal_hold is True


@pytest.mark.parametrize("kind", ["head", "revision_owner", "operation_owner", "operation_head", "branch_owner", "branch_revision"])
def test_database_rejects_cross_owner_and_cross_investigation_context_bindings(stored, kind):
    with pytest.raises(DBAPIError):
        with stored["factory"].begin() as session:
            if kind == "head":
                session.get(ResearchInvestigation, stored["investigations"][0]).head_revision_id = stored["revisions"][1]
            elif kind == "revision_owner":
                session.add(ResearchContextRevision(investigation_id=stored["investigations"][0], sequence=2, snapshot_id="a" * 64,
                    payload_json="{}", payload_sha256="b" * 64, created_by_user_id=stored["owners"][1]))
            elif kind.startswith("operation_"):
                session.add(ResearchContextOperation(user_id=stored["owners"][1] if kind == "operation_owner" else stored["owners"][0],
                    investigation_id=stored["investigations"][0], idempotency_key="new-operation", kind="pin",
                    expected_head_id=stored["revisions"][1] if kind == "operation_head" else None,
                    request_json="{}", request_sha256="c" * 64, candidate_json="{}", references_json="[]", state="prepared"))
            else:
                session.add(ResearchInvestigation(user_id=stored["owners"][1] if kind == "branch_owner" else stored["owners"][0], name="Invalid branch",
                    predecessor_investigation_id=stored["investigations"][0],
                    predecessor_revision_id=stored["revisions"][1] if kind == "branch_revision" else stored["revisions"][0]))


def test_corpus_metadata_drop_and_replace_preserves_all_private_application_records(stored):
    from db.models import AnchorEvent, CorpusBase, CtdProfile

    CorpusBase.metadata.create_all(stored["engine"], tables=[AnchorEvent.__table__, CtdProfile.__table__])
    with stored["engine"].begin() as connection:
        connection.execute(AnchorEvent.__table__.insert().values(event_id="synthetic-c17-anchor"))
        connection.execute(CtdProfile.__table__.insert().values(sample_id="synthetic-c17-sample", depth_m=-1.5))
    # Exercise the actual corpus metadata's replacement boundary. AppBase is
    # deliberately absent from this metadata graph and has no corpus FK.
    CorpusBase.metadata.drop_all(stored["engine"])
    CorpusBase.metadata.create_all(stored["engine"], tables=[AnchorEvent.__table__, CtdProfile.__table__])
    with stored["factory"]() as session:
        assert session.get(ResearchInvestigation, stored["investigations"][0]).head_revision_id == stored["revisions"][0]
        assert session.get(ResearchConversation, stored["conversation"])
        assert session.get(ResearchContextRevision, stored["revisions"][0]).payload_json == '{"synthetic":true}'
        assert session.get(ResearchContextOperation, stored["operation"])
        assert session.scalar(select(CtdProfile.id)) is None
