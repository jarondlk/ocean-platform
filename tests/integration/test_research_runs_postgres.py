"""C20 real PostgreSQL migration, lock, fencing and crash transaction acceptance."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import os
import threading
import uuid

import pytest
from sqlalchemy import event, inspect, select, text
from sqlalchemy.exc import DBAPIError, SQLAlchemyError

from db import app_models as models
from orchestration.research_runs import ResearchRunError, RunJournal
from schema.research_controller import canonical_hash
from tests import research_run_postgres_support as pg
from tests.integration import test_investigation_postgres as old_pg
from tests.research_run_support import make_run_fixture

disposable_database, isolated = pg.disposable_database, pg.isolated
pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_POSTGRES_INTEGRATION") != "1",
    reason="requires explicitly verified disposable C20 PostgreSQL",
)
RUN_MODELS = (
    models.ResearchRun, models.ResearchRunInputHistory, models.ResearchRunEvent,
    models.ResearchRunPayload, models.ResearchRunStep, models.ResearchRunAttempt,
    models.ResearchRunManifest, models.ResearchRunOutbox,
)


def key():
    return str(uuid.uuid4())


@pytest.fixture
def fixture(isolated, tmp_path, monkeypatch):
    for flag in ("CATALOGUE", "INVESTIGATIONS", "RESEARCH_CONTROLLER", "RESEARCH_RUNS", "RESEARCH_DISPATCH"):
        monkeypatch.setenv("ENABLE_V1_" + flag, "true")
    pg.alembic(isolated, "upgrade", "head")
    value = make_run_fixture(isolated["engine"], tmp_path)
    yield value


def assert_run_schema(engine):
    reflected = inspect(engine)
    for model in RUN_MODELS:
        table = model.__table__
        assert [(c["name"], c["nullable"]) for c in reflected.get_columns(table.name)] == [(c.name, c.nullable) for c in table.columns]
        assert {entry["name"] for entry in reflected.get_check_constraints(table.name)} == {
            c.name for c in table.constraints if c.__class__.__name__ == "CheckConstraint"
        }
        actual_uniques = {tuple(entry["column_names"]): entry["name"] for entry in reflected.get_unique_constraints(table.name)}
        expected_uniques = {tuple(c.columns.keys()): c.name for c in table.constraints if c.__class__.__name__ == "UniqueConstraint"}
        assert actual_uniques.keys() == expected_uniques.keys()
        # PostgreSQL generates names for unnamed unique constraints. Compare
        # their actual columns; retain exact checks for all explicitly named ones.
        assert all(actual_uniques[columns] == name for columns, name in expected_uniques.items() if name is not None)
        assert {entry["name"] for entry in reflected.get_indexes(table.name) if not entry.get("duplicates_constraint")} == {index.name for index in table.indexes}
        actual = {(tuple(e["constrained_columns"]), e["referred_table"], tuple(e["referred_columns"]), e["options"].get("ondelete")) for e in reflected.get_foreign_keys(table.name)}
        expected = {(tuple(e.parent.name for e in c.elements), c.referred_table.name, tuple(e.column.name for e in c.elements), c.ondelete) for c in table.foreign_key_constraints}
        assert actual == expected


def test_new_head_repeat_upgrade_and_empty_downgrade_match_all_run_models(isolated):
    pg.alembic(isolated, "upgrade", "head")
    assert pg.revision(isolated) == "20261019_0019"
    assert_run_schema(isolated["engine"])
    pg.alembic(isolated, "upgrade", "head")
    pg.alembic(isolated, "downgrade", "20261018_0017")
    assert not {m.__tablename__ for m in RUN_MODELS} & set(inspect(isolated["engine"]).get_table_names())
    pg.alembic(isolated, "upgrade", "head")
    assert_run_schema(isolated["engine"])


def test_additive_upgrade_preserves_populated_c17_bytes(isolated):
    pg.alembic(isolated, "upgrade", "20261018_0017")
    old_pg.seed(isolated)
    tables = ("research_investigation", "research_context_revision", "research_context_operation", "research_conversation")

    def rows():
        with isolated["engine"].connect() as connection:
            return {name: list(connection.scalars(text(f"SELECT row_to_json(t)::text FROM {name} t ORDER BY id"))) for name in tables}

    before = rows()
    pg.alembic(isolated, "upgrade", "head")
    assert rows() == before
    assert_run_schema(isolated["engine"])


@pytest.mark.parametrize("ambiguous", [False, True])
def test_submit_actual_commit_failure_or_lost_ack_has_atomic_outbox_input_event(fixture, ambiguous):
    body = fixture.request()
    fired = []

    def before_flush(session, _context, _instances):
        if any(isinstance(item, models.ResearchRun) for item in session.new):
            session.info["c20_submit"] = True

    def fail(session):
        if session.info.get("c20_submit") and not fired:
            fired.append(True)
            raise SQLAlchemyError("Synthetic lost transaction acknowledgement")

    when = "after_commit" if ambiguous else "before_commit"
    event.listen(fixture.retained.factory, "before_flush", before_flush)
    event.listen(fixture.retained.factory, when, fail)
    try:
        with pytest.raises(SQLAlchemyError):
            fixture.service.invoke("submit", body, fixture.user)
    finally:
        event.remove(fixture.retained.factory, "before_flush", before_flush)
        event.remove(fixture.retained.factory, when, fail)
    with fixture.retained.factory() as session:
        for model in (models.ResearchRun, models.ResearchRunInputHistory, models.ResearchRunEvent, models.ResearchRunOutbox):
            assert len(session.scalars(select(model)).all()) == int(ambiguous)
    result = fixture.service.invoke("submit", body, fixture.user)["run"]
    assert fixture.service.invoke("submit", body, fixture.user)["run"] == result
    with fixture.retained.factory() as session:
        assert len(session.scalars(select(models.ResearchRun)).all()) == 1


def test_concurrent_submit_has_one_run_outbox_and_cursor(fixture):
    body = fixture.request()
    barrier = threading.Barrier(2)

    def submit():
        barrier.wait(timeout=5)
        return fixture.service.invoke("submit", body, fixture.user)

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(submit) for _ in range(2)]
        results = [future.result(timeout=20) for future in futures]
    assert results[0] == results[1]
    with fixture.retained.factory() as session:
        for model in (models.ResearchRun, models.ResearchRunInputHistory, models.ResearchRunEvent, models.ResearchRunOutbox):
            assert len(session.scalars(select(model)).all()) == 1


def test_concurrent_claim_has_one_epoch_and_no_duplicate_started_event(fixture):
    run = fixture.submit()
    delivery = fixture.delivery(run)
    barrier = threading.Barrier(2)

    def claim():
        barrier.wait(timeout=5)
        return fixture.service.claim(**delivery)

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(claim) for _ in range(2)]
        results = [future.result(timeout=20) for future in futures]
    assert sum(item is not None for item in results) == 1
    with fixture.retained.factory() as session:
        assert session.get(models.ResearchRun, uuid.UUID(run["id"])).lease_epoch == 1
        events = session.scalars(select(models.ResearchRunEvent).order_by(models.ResearchRunEvent.cursor)).all()
        assert [item.kind for item in events] == ["accepted", "started"]


def test_lost_actual_step_commit_ack_replays_without_another_scientific_call(fixture, monkeypatch):
    from orchestration.research_controller import ControllerAdmissionError

    run = fixture.submit()
    fired, outbound = [], []
    catalogue = fixture.retained.service.catalogue
    execute = catalogue.execute

    def observe(*args, **kwargs):
        if args[0] == "catalogue.query":
            outbound.append(args[0])
        return execute(*args, **kwargs)

    def before_flush(session, _context, _instances):
        if any(isinstance(item, models.ResearchRunStep) and item.state == "committed" for item in session.dirty):
            session.info["c20_step_commit"] = True

    def after_commit(session):
        if session.info.get("c20_step_commit") and not fired:
            fired.append(True)
            raise SQLAlchemyError("Synthetic lost acknowledgement after actual step commit")

    monkeypatch.setattr(catalogue, "execute", observe)
    event.listen(fixture.retained.factory, "before_flush", before_flush)
    event.listen(fixture.retained.factory, "after_commit", after_commit)
    try:
        with pytest.raises(ControllerAdmissionError):
            fixture.service.execute_delivery(**fixture.delivery(run))
    finally:
        event.remove(fixture.retained.factory, "before_flush", before_flush)
        event.remove(fixture.retained.factory, "after_commit", after_commit)
    assert fired and len(outbound) == 1
    fixture.clock.advance(6)
    assert fixture.service.execute_delivery(**fixture.delivery(run))["run"]["status"] == "completed"
    assert len(outbound) == 1
    with fixture.retained.factory() as session:
        row = session.get(models.ResearchRun, uuid.UUID(run["id"]))
        assert row.tool_actions == 1 and row.active_elapsed_ms >= 6000
        assert len(session.scalars(select(models.ResearchRunStep)).all()) == 1
        assert len(session.scalars(select(models.ResearchRunAttempt)).all()) == 1
        assert list(session.scalars(select(models.ResearchRunEvent.kind).order_by(models.ResearchRunEvent.cursor))) == ["accepted", "started", "progress", "completed"]


def test_expired_epoch_fences_late_commit_and_charges_unresolved_interval(fixture):
    run = fixture.submit()
    delivery = fixture.delivery(run)
    earlier = fixture.service.claim(**delivery)
    journal = RunJournal(fixture.service, earlier)
    request = {"synthetic": "reservation"}
    budget = {"active_elapsed_seconds": 0.0, "tool_actions": 1, "model_calls": 0, "malformed_repairs": 0, "cancellation_requested": False}
    token = journal.prepare_step("inventory:0:synthetic", "tool", canonical_hash(request), request, budget, {})
    fixture.clock.advance(20)
    later = fixture.service.claim(**delivery)
    assert later.epoch > earlier.epoch
    with pytest.raises(ResearchRunError) as error:
        journal.commit_step(token, {"synthetic": "late"}, budget, {})
    assert error.value.code == "lease_lost"
    with fixture.retained.factory() as session:
        stored = session.get(models.ResearchRun, uuid.UUID(run["id"]))
        assert stored.tool_actions == 1 and stored.active_elapsed_ms == 20000
        assert session.scalar(select(models.ResearchRunPayload)) is None
        assert len(session.scalars(select(models.ResearchRunEvent)).all()) == 2


@pytest.mark.parametrize("cancel_first", [False, True])
def test_cancel_and_complete_share_actual_row_lock_and_preserve_winner(fixture, monkeypatch, cancel_first):
    run = fixture.submit()
    # Hold exactly the final publication transaction or the cancellation
    # transaction after acquiring the shared run lock. The other must wait.
    locked, release = threading.Event(), threading.Event()
    controller_ready, publish = threading.Event(), threading.Event()
    original = fixture.service._event
    factory = fixture.service.controller_factory

    def controller_factory(identity):
        controller = factory(identity)
        execute = controller.execute

        def execute_then_wait(*args, **kwargs):
            result = execute(*args, **kwargs)
            controller_ready.set()
            if cancel_first:
                assert publish.wait(10)
            return result

        controller.execute = execute_then_wait
        return controller

    monkeypatch.setattr(fixture.service, "controller_factory", controller_factory)

    def intercept(session, row, kind):
        if kind == ("cancelled" if cancel_first else "completed"):
            locked.set()
            assert release.wait(10)
        return original(session, row, kind)

    monkeypatch.setattr(fixture.service, "_event", intercept)

    def complete():
        try:
            return fixture.service.execute_delivery(**fixture.delivery(run))
        except ResearchRunError as error:
            return error.code

    def cancel():
        return fixture.service.invoke("cancel", {**fixture.address(run), "idempotency_key": key()}, fixture.user)

    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(complete)
        try:
            if cancel_first:
                assert controller_ready.wait(10)
                second = pool.submit(cancel)
            assert locked.wait(10)
            if not cancel_first:
                second = pool.submit(cancel)
                assert not second.done()
            else:
                publish.set()
                assert not first.done()
        finally:
            publish.set()
            release.set()
        first.result(timeout=20)
        second.result(timeout=20)
    stored = fixture.service.invoke("status", fixture.address(run), fixture.user)["run"]
    assert stored["status"] == ("cancelled" if cancel_first else "completed")
    with fixture.retained.factory() as session:
        kinds = list(session.scalars(select(models.ResearchRunEvent.kind).order_by(models.ResearchRunEvent.cursor)))
        assert kinds.count("completed") == int(not cancel_first)
        assert kinds.count("cancelled") == int(cancel_first)


def test_actual_database_clock_and_terminal_redelivery_do_not_repeat_calls(fixture):
    fixture.service.db_clock = None
    run = fixture.submit()
    completed = fixture.service.execute_delivery(**fixture.delivery(run))["run"]
    assert completed["status"] == "completed" and completed["active_elapsed_ms"] >= 0
    assert fixture.service.execute_delivery(**fixture.delivery(run))["run"] == completed
    assert fixture.state["factory_calls"] == 1
    with fixture.retained.factory() as session:
        row = session.get(models.ResearchRun, uuid.UUID(run["id"]))
        assert row.updated_at > datetime(2026, 1, 1, tzinfo=timezone.utc)


def test_policy_change_during_terminal_flush_rolls_back_completion(fixture, monkeypatch):
    run = fixture.submit()
    original = fixture.service._event

    def change_after_event(session, row, kind):
        original(session, row, kind)
        if kind == "completed":
            fixture.retained.policy[run["context"]["binding"]["snapshot_id"]].add(fixture.retained.source_dataset_ids["ctd"])

    monkeypatch.setattr(fixture.service, "_event", change_after_event)
    with pytest.raises(ResearchRunError) as error:
        fixture.service.execute_delivery(**fixture.delivery(run))
    assert error.value.status_code == 403
    with fixture.retained.factory() as session:
        stored = session.get(models.ResearchRun, uuid.UUID(run["id"]))
        assert stored.status == "running" and stored.controller_result_json is None
        assert list(session.scalars(select(models.ResearchRunEvent.kind).order_by(models.ResearchRunEvent.cursor))) == ["accepted", "started", "progress"]
        assert session.scalar(select(models.ResearchRunPayload)) is not None


@pytest.mark.parametrize("column,value", [
    ("conversation_id", uuid.uuid4()), ("revision_id", uuid.uuid4()),
    ("snapshot_id", "f" * 64), ("payload_sha256", "e" * 64), ("user_id", uuid.uuid4()),
    ("tool_actions", -1), ("tool_actions", 13), ("malformed_repairs", 2), ("active_elapsed_ms", -1),
])
def test_database_rejects_incoherent_run_binding_and_budget(fixture, column, value):
    run = fixture.submit()
    with fixture.retained.factory() as session:
        row = session.get(models.ResearchRun, uuid.UUID(run["id"]))
        copied = {item.name: getattr(row, item.name) for item in models.ResearchRun.__table__.columns}
    copied.update(id=uuid.uuid4())
    copied[column] = value
    with pytest.raises(DBAPIError), fixture.retained.factory.begin() as session:
        session.execute(models.ResearchRun.__table__.insert().values(**copied))


@pytest.mark.parametrize("table", ["research_run_input_history", "research_run_event", "research_run_payload", "research_run_attempt", "research_run_manifest"])
@pytest.mark.parametrize("operation", ["UPDATE", "DELETE", "TRUNCATE"])
def test_native_sql_cannot_rewrite_immutable_execution_history(fixture, table, operation):
    run = fixture.submit()
    assert fixture.service.execute_delivery(**fixture.delivery(run))["run"]["status"] == "completed"
    statement = f"UPDATE {table} SET run_id=run_id" if operation == "UPDATE" else f"{operation} {table}" + (" CASCADE" if operation == "TRUNCATE" else "")
    with pytest.raises(DBAPIError), fixture.retained.factory.begin() as session:
        session.execute(text(statement))


@pytest.mark.parametrize("assignment", [
    "status='queued'", "controller_result_json=NULL", "tool_actions=0",
    "event_cursor=0", "lease_epoch=0", "version=1", "active_elapsed_ms=-1",
])
def test_native_sql_cannot_reset_terminal_history_or_budget(fixture, assignment):
    run = fixture.submit()
    terminal = fixture.service.execute_delivery(**fixture.delivery(run))
    with pytest.raises(DBAPIError), fixture.retained.factory.begin() as session:
        session.execute(text(f"UPDATE research_run SET {assignment} WHERE id=:id"), {"id": run["id"]})
    assert fixture.service.invoke("status", fixture.address(run), fixture.user) == terminal


def test_populated_downgrade_is_refused_with_history_intact(fixture, isolated):
    run = fixture.submit()
    result = pg.alembic(isolated, "downgrade", "20261018_0017", succeeds=False)
    assert "populated C20 storage cannot be downgraded" in result.stderr
    assert pg.revision(isolated) == "20261019_0019"
    assert fixture.service.invoke("status", fixture.address(run), fixture.user)["run"] == run
