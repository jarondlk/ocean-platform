"""C21 real disposable PostgreSQL guards, retention fences and local receipts."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import os
import threading
import uuid

import pytest
from sqlalchemy import inspect, select, text
from sqlalchemy.exc import DBAPIError

from db import app_models as models
from orchestration.research_evidence import ResearchEvidenceError
from schema.research_controller import canonical_json
from tests import research_evidence_postgres_support as pg
from tests.research_evidence_support import make_evidence_fixture

disposable_database, isolated = pg.disposable_database, pg.isolated
pytestmark = pytest.mark.skipif(os.environ.get("RUN_POSTGRES_INTEGRATION") != "1",
    reason="requires explicitly verified disposable C21 PostgreSQL")
NEW_MODELS = tuple(model for model in vars(models).values() if isinstance(model, type)
    and hasattr(model, "__tablename__") and model.__tablename__.startswith(("research_evidence_", "research_answer")))


@pytest.fixture
def actual(isolated, tmp_path, monkeypatch):
    for name in ("ENABLE_V1_CATALOGUE", "ENABLE_V1_INVESTIGATIONS", "ENABLE_V1_RESEARCH_CONTROLLER"):
        monkeypatch.setenv(name, "true")
    pg.alembic(isolated, "upgrade", "head")
    return make_evidence_fixture(isolated["engine"], tmp_path)


def completed(fixture):
    run = fixture.submit()
    fixture.service.execute_delivery(**fixture.delivery(run))
    return run


def retained(actual):
    fixture, evidence = actual
    run = completed(fixture)
    return run, evidence.ensure_retained(run["id"], 1, fixture.user).receipts[0]


def test_migration_exact_schema_repeat_and_empty_downgrade(isolated):
    pg.alembic(isolated, "upgrade", "head")
    assert pg.revision(isolated) == "20261027_0021"
    reflected = inspect(isolated["engine"])
    for model in NEW_MODELS:
        table = model.__table__
        assert [(entry["name"], entry["nullable"]) for entry in reflected.get_columns(table.name)] == [(column.name, column.nullable) for column in table.columns]
        assert {entry["name"] for entry in reflected.get_check_constraints(table.name)} == {constraint.name for constraint in table.constraints if constraint.__class__.__name__ == "CheckConstraint"}
        assert {(tuple(entry["constrained_columns"]), entry["referred_table"], tuple(entry["referred_columns"])) for entry in reflected.get_foreign_keys(table.name)} == {
            (tuple(element.parent.name for element in constraint.elements), constraint.referred_table.name, tuple(element.column.name for element in constraint.elements))
            for constraint in table.foreign_key_constraints}
    pg.alembic(isolated, "upgrade", "head")
    pg.alembic(isolated, "downgrade", "20261019_0018")
    assert not {model.__tablename__ for model in NEW_MODELS} & set(inspect(isolated["engine"]).get_table_names())
    pg.alembic(isolated, "upgrade", "head")


def test_actual_pg_count_retention_reopen_and_no_c20_mutation(actual):
    fixture, evidence = actual
    run = completed(fixture)
    with fixture.retained.factory() as session:
        before = session.scalar(text("SELECT row_to_json(r)::text FROM research_run r WHERE id=:id"), {"id": run["id"]})
    receipt = evidence.ensure_retained(run["id"], 1, fixture.user).receipts[0]
    assert receipt.counts[0].value == 4
    assert evidence.invoke("open", {"receipt_id": receipt.id, "expected_sha256": receipt.sha256}, fixture.user)["receipt"]["id"] == receipt.id
    with fixture.retained.factory() as session:
        assert session.scalar(text("SELECT row_to_json(r)::text FROM research_run r WHERE id=:id"), {"id": run["id"]}) == before
    assert fixture.service.invoke("status", fixture.address(run), fixture.user)["run"]["status"] == "completed"


@pytest.mark.parametrize("table,statement", [
    ("research_evidence_blob", "UPDATE research_evidence_blob SET inputs_json='[]'"),
    ("research_evidence_receipt", "UPDATE research_evidence_receipt SET receipt_json='{}'"),
    ("research_evidence_receipt", "UPDATE research_evidence_receipt SET state='prepared'"),
    ("research_evidence_protection", "UPDATE research_evidence_protection SET state='uncertain'"),
    ("research_evidence_receipt", "DELETE FROM research_evidence_receipt"),
    ("research_evidence_blob", "TRUNCATE research_evidence_blob CASCADE"),
])
def test_native_sql_cannot_rewrite_or_delete_retained_records(actual, table, statement):
    fixture, _ = actual
    retained(actual)
    with pytest.raises(DBAPIError), fixture.retained.factory.begin() as session:
        session.execute(text(statement))


def test_populated_downgrade_is_rejected_without_losing_receipts(actual, isolated):
    fixture, evidence = actual
    _, receipt = retained(actual)
    pg.alembic(isolated, "downgrade", "20261019_0018", succeeds=False)
    assert evidence.resolve_attachment(fixture.user, receipt.attachment_reference.model_dump(mode="json")) is not None


def archive(fixture, investigation_id):
    with fixture.retained.factory.begin() as session:
        row = session.get(models.ResearchInvestigation, uuid.UUID(investigation_id))
        row.status, row.updated_at = "archived", datetime.now(timezone.utc) - timedelta(days=400)


def test_retirement_retains_origin_even_when_c21_unwired_and_disabled(actual, monkeypatch):
    fixture, evidence = actual
    _, receipt = retained(actual)
    archive(fixture, receipt.binding.investigation_id)
    fixture.retained.service.evidence_protection = None
    monkeypatch.setattr(evidence, "enabled", lambda: False)
    report = fixture.retained.service.retire_expired(retention_days=30, user=fixture.retained.admin, dry_run=False)
    assert report["retired_count"] == report["eligible_count"] == 0
    with pytest.raises(DBAPIError), fixture.retained.factory.begin() as session:
        session.execute(text("UPDATE research_investigation SET status='retired' WHERE id=:id"), {"id": receipt.binding.investigation_id})


def test_concurrent_receipt_retention_has_one_identity_and_ready_protection(actual):
    fixture, evidence = actual
    run = completed(fixture)
    barrier = threading.Barrier(2)

    def retain():
        barrier.wait(timeout=5)
        return evidence.ensure_retained(run["id"], 1, fixture.user).receipts[0]

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(retain) for _ in range(2)]
        first, second = [future.result(timeout=25) for future in futures]
    assert first == second
    with fixture.retained.factory() as session:
        assert len(session.scalars(select(models.ResearchEvidenceReceipt)).all()) == 1
        assert session.get(models.ResearchEvidenceProtection, first.id).state == "ready"


def test_actual_reference_commit_ack_loss_keeps_uncertain_protection_and_retry(actual, monkeypatch):
    fixture, evidence = actual
    run = completed(fixture)
    original, fired = fixture.retained.store.add_reference, []

    def uncertain(snapshot, reference):
        result = original(snapshot, reference)
        if reference.startswith("c21:") and not fired:
            fired.append(reference)
            raise RuntimeError("Synthetic lost reference acknowledgement after actual C09 commit")
        return result

    monkeypatch.setattr(fixture.retained.store, "add_reference", uncertain)
    with pytest.raises(ResearchEvidenceError, match="evidence_protection_pending"):
        evidence.ensure_retained(run["id"], 1, fixture.user)
    with fixture.retained.factory() as session:
        row = session.scalars(select(models.ResearchEvidenceReceipt)).one()
        assert row.state == "prepared"
        assert session.get(models.ResearchEvidenceProtection, row.id).state == "uncertain"
    assert fired[0] in fixture.retained.store.lifecycle()["references"]
    monkeypatch.setattr(fixture.retained.store, "add_reference", original)
    receipt = evidence.ensure_retained(run["id"], 1, fixture.user).receipts[0]
    assert evidence.resolve_attachment(fixture.user, receipt.attachment_reference.model_dump(mode="json"))


def test_prepared_context_edge_and_old_snapshot_origin_block_retirement(actual):
    fixture, evidence = actual
    _, receipt = retained(actual)
    created = fixture.retained.service.invoke("create", {"name": "Explicit newer snapshot",
        "snapshot_id": fixture.retained.snapshots[1], "scope": fixture.retained.scope,
        "idempotency_key": str(uuid.uuid4())}, fixture.user)
    operation = fixture.retained.service._prepare("context/change", {
        "investigation_id": created["investigation"]["id"], "expected_revision_id": created["context"]["id"],
        "idempotency_key": str(uuid.uuid4()), "change": {"op": "attach",
            "reference": receipt.attachment_reference.model_dump(mode="json")}}, fixture.user)
    with fixture.retained.factory() as session:
        assert session.get(models.ResearchEvidenceContextDependency, (operation, receipt.id)).state == "prepared"
    archive(fixture, receipt.binding.investigation_id)
    assert fixture.retained.service.retire_expired(retention_days=30, user=fixture.retained.admin, dry_run=False)["retired_count"] == 0
    result = fixture.retained.service._apply(operation, fixture.user)
    assert result["context"]["resolution"][0]["status"] == "available"
    with fixture.retained.factory() as session:
        assert session.get(models.ResearchEvidenceContextDependency, (operation, receipt.id)).state == "committed"


def test_queued_answer_job_protects_origin_before_receipt_exists(actual):
    fixture, evidence = actual
    run = completed(fixture)
    with fixture.retained.factory.begin() as session:
        source = session.get(models.ResearchRun, uuid.UUID(run["id"]))
        job = models.ResearchAnswerJob(id=uuid.uuid4(), user_id=source.user_id, run_id=source.id,
            **{key: getattr(source, key) for key in ("investigation_id", "conversation_id", "revision_id", "snapshot_id", "payload_sha256")},
            input_version=1, locale="en", idempotency_key=str(uuid.uuid4()), request_json="{}", request_sha256="0" * 64,
            budget_floor_json=canonical_json(fixture.service._budget(source)), active_elapsed_ms=source.active_elapsed_ms,
            tool_actions=source.tool_actions, model_calls=source.model_calls, malformed_repairs=source.malformed_repairs)
        session.add(job)
    archive(fixture, run["context"]["binding"]["investigation_id"])
    assert fixture.retained.service.retire_expired(retention_days=30, user=fixture.retained.admin, dry_run=False)["retired_count"] == 0
    with pytest.raises(DBAPIError), fixture.retained.factory.begin() as session:
        session.execute(text("UPDATE research_answer_job SET tool_actions=0"))


def test_retirement_race_has_protected_receipt_or_explicit_retired_denial(actual):
    fixture, evidence = actual
    run = completed(fixture)
    investigation_id = run["context"]["binding"]["investigation_id"]
    archive(fixture, investigation_id)
    barrier = threading.Barrier(2)

    def retain():
        barrier.wait(timeout=5)
        try:
            return evidence.ensure_retained(run["id"], 1, fixture.user).receipts[0]
        except ResearchEvidenceError as error:
            return error

    def retire():
        barrier.wait(timeout=5)
        return fixture.retained.service.retire_expired(retention_days=30, user=fixture.retained.admin, dry_run=False)

    with ThreadPoolExecutor(max_workers=2) as pool:
        retained_future, retirement_future = pool.submit(retain), pool.submit(retire)
        receipt, report = retained_future.result(timeout=25), retirement_future.result(timeout=25)
    with fixture.retained.factory() as session:
        source = session.get(models.ResearchInvestigation, uuid.UUID(investigation_id))
        rows = session.scalars(select(models.ResearchEvidenceReceipt)).all()
        if isinstance(receipt, ResearchEvidenceError):
            assert receipt.status_code == 403 and source.status == "retired" and report["retired_count"] == 1 and not rows
        else:
            assert source.status == "archived" and report["retired_count"] == 0
            assert len(rows) == 1 and rows[0].state == "ready"


def test_concurrent_answer_submit_and_claim_share_one_budget_head(actual):
    from tests.test_research_answers import delivery, request, service
    fixture, _, answers = service(actual)
    _, data = request(fixture)
    barrier = threading.Barrier(2)

    def submit():
        barrier.wait(timeout=5)
        return answers.invoke("submit", data, fixture.user)["job"]

    with ThreadPoolExecutor(max_workers=2) as pool:
        jobs = [future.result(timeout=25) for future in (pool.submit(submit), pool.submit(submit))]
    assert jobs[0] == jobs[1]
    barrier = threading.Barrier(2)

    def claim():
        barrier.wait(timeout=5)
        return answers.claim(**delivery(fixture, jobs[0]))

    with ThreadPoolExecutor(max_workers=2) as pool:
        leases = [future.result(timeout=25) for future in (pool.submit(claim), pool.submit(claim))]
    assert sum(lease is not None for lease in leases) == 1
    with fixture.retained.factory() as session:
        assert len(session.scalars(select(models.ResearchAnswerJob)).all()) == 1
        assert len(session.scalars(select(models.ResearchAnswerOutbox)).all()) == 1
        assert len(session.scalars(select(models.ResearchAnswerInputHistory)).all()) == 1


@pytest.mark.parametrize("committed", [False, True])
def test_answer_actual_pg_raw_commit_or_uncertain_response_preserves_reservations(actual, monkeypatch, committed):
    from sqlalchemy import event
    from sqlalchemy.exc import SQLAlchemyError
    from tests.test_research_answers import delivery, model_request
    from tests.test_research_answers import SELECTION
    fixture, _, answers, job = model_request(actual, actions=(SELECTION, SELECTION))
    fired = []
    if committed:
        def before_flush(session, _context, _instances):
            if any(isinstance(item, models.ResearchAnswerStep) and item.state == "committed" for item in session.dirty):
                session.info["c21_step_commit"] = True

        def after_commit(session):
            if session.info.get("c21_step_commit") and not fired:
                fired.append(True)
                raise SQLAlchemyError("Synthetic lost acknowledgement after actual PostgreSQL commit")

        event.listen(fixture.retained.factory, "before_flush", before_flush)
        event.listen(fixture.retained.factory, "after_commit", after_commit)
    else:
        generate = answers.runtime.structured_chat_result

        def interrupted(**kwargs):
            value = generate(**kwargs)
            if not fired:
                fired.append(True)
                raise RuntimeError("Synthetic physical response loss")
            return value

        monkeypatch.setattr(answers.runtime, "structured_chat_result", interrupted)
    try:
        with pytest.raises((SQLAlchemyError, RuntimeError)):
            answers.execute_delivery(**delivery(fixture, job))
    finally:
        if committed:
            event.remove(fixture.retained.factory, "before_flush", before_flush)
            event.remove(fixture.retained.factory, "after_commit", after_commit)
    fixture.clock.advance(6)
    outcome = answers.execute_delivery(**delivery(fixture, job))["job"]
    assert outcome["status"] == "completed"
    assert len(answers.runtime.calls) == (1 if committed else 2)
    assert outcome["budget"]["model_calls"] == job["budget"]["model_calls"] + (1 if committed else 2)
    assert outcome["active_elapsed_ms"] >= job["active_elapsed_ms"] + 6000


@pytest.mark.parametrize("revoke", [False, True])
def test_cancel_or_policy_change_after_candidate_before_answer_commit_fences_publication(actual, monkeypatch, revoke):
    from orchestration.research_answers import ResearchAnswerError
    from tests.test_research_answers import address, delivery, model_request
    fixture, _, answers, job = model_request(actual)
    candidate, release = threading.Event(), threading.Event()
    finish = answers._finish

    def waiting(lease, *, answer=None, reason=None):
        if answer is not None:
            candidate.set()
            assert release.wait(timeout=15)
        return finish(lease, answer=answer, reason=reason)

    monkeypatch.setattr(answers, "_finish", waiting)
    with ThreadPoolExecutor(max_workers=1) as pool:
        worker = pool.submit(answers.execute_delivery, **delivery(fixture, job))
        try:
            assert candidate.wait(timeout=15)
            if revoke:
                fixture.retained.policy[job["binding"]["snapshot_id"]].add("synthetic-revocation-before-publication")
            else:
                answers.invoke("cancel", {**address(job), "idempotency_key": str(uuid.uuid4())}, fixture.user)
        finally:
            release.set()
        with pytest.raises(ResearchAnswerError) as error:
            worker.result(timeout=15)
        assert error.value.status_code == (403 if revoke else 409)
    with fixture.retained.factory() as session:
        assert not session.scalars(select(models.ResearchAnswer)).all()
        assert not session.scalars(select(models.ResearchAnswerEvent).where(models.ResearchAnswerEvent.kind == "completed")).all()


def graph_receipts(session, base, count):
    """Synthetic native-constraint nodes sharing actual C20 owner/binding/blob.

    These rows exercise only the private database graph guard; they are never
    exposed as verified C20 observations or independent scientific publications.
    """
    from orchestration.research_evidence import _receipt
    template = session.get(models.ResearchEvidenceReceipt, base.id)
    nodes = []
    for index in range(count):
        value = base.model_dump(mode="json")
        value["parameters"] = {**value["parameters"], "native_graph_fixture": str(uuid.uuid4()), "index": index}
        descriptor = _receipt(value)
        node = models.ResearchEvidenceReceipt(id=descriptor.id, sha256=descriptor.sha256,
            receipt_json=canonical_json(descriptor.model_dump(mode="json")), state="prepared",
            **{key: getattr(template, key) for key in ("user_id", "run_id", "input_version", "investigation_id",
                "conversation_id", "revision_id", "snapshot_id", "payload_sha256", "blob_sha256")})
        session.add(node)
        nodes.append(node)
    session.flush()
    return nodes


def graph_edge(session, consumer, producer):
    session.add(models.ResearchEvidenceDependency(receipt_id=consumer.id,
        origin_receipt_id=producer.id, user_id=consumer.user_id))
    session.flush()


def test_shared_fibonacci_dag_is_bounded_by_distinct_nodes_not_paths(actual):
    fixture, _ = actual
    _, receipt = retained(actual)
    with fixture.retained.factory.begin() as session:
        # A 36-node shared DAG represents millions of paths in the old UNION
        # ALL(depth) traversal. Each new insertion must stay a tiny graph query.
        session.execute(text("SET LOCAL statement_timeout='1500ms'"))
        nodes = graph_receipts(session, receipt, 36)
        for index, node in enumerate(nodes):
            for parent in nodes[max(0, index - 2):index]:
                graph_edge(session, node, parent)
            node.state = "ready"
            session.flush()
        closure = session.scalar(text("""WITH RECURSIVE closure(id) AS (
            SELECT CAST(:root AS VARCHAR(76)) UNION SELECT d.origin_receipt_id FROM research_evidence_dependency d
            JOIN closure c ON d.receipt_id=c.id) SELECT count(*) FROM closure"""), {"root": nodes[-1].id})
        assert closure == 36


def test_combined_dependency_closure_allows_1024_nodes_and_rejects_1025(actual):
    fixture, _ = actual
    _, receipt = retained(actual)
    with fixture.retained.factory.begin() as session:
        nodes = graph_receipts(session, receipt, 1025)
        # Two disjoint chains:512+511 ancestors plus their consumer=1024.
        for start, end in ((0, 512), (512, 1023)):
            for index in range(start, end):
                if index > start:
                    graph_edge(session, nodes[index], nodes[index - 1])
                nodes[index].state = "ready"
                session.flush()
        nodes[1024].state = "ready"
        session.flush()
        consumer = nodes[1023]
        graph_edge(session, consumer, nodes[511])
        graph_edge(session, consumer, nodes[1022])
        assert len(session.scalars(select(models.ResearchEvidenceDependency).where(
            models.ResearchEvidenceDependency.receipt_id == consumer.id)).all()) == 2
        with pytest.raises(DBAPIError, match="unbounded closure"), session.begin_nested():
            graph_edge(session, consumer, nodes[1024])
        assert len(session.scalars(select(models.ResearchEvidenceDependency).where(
            models.ResearchEvidenceDependency.receipt_id == consumer.id)).all()) == 2


def test_dependency_guard_rejects_cycle_reachable_from_proposed_origin(actual):
    fixture, _ = actual
    _, receipt = retained(actual)
    with fixture.retained.factory.begin() as session:
        consumer, producer = graph_receipts(session, receipt, 2)
        producer.state = "ready"
        session.flush()
        # Seed an invalid older/externally-corrupt edge in the disposable test
        # schema only. The new guarded insert must detect that origin->consumer
        # closure even though state rules normally prevent creating such a graph.
        session.execute(text("ALTER TABLE research_evidence_dependency DISABLE TRIGGER research_evidence_dependency_guard"))
        graph_edge(session, producer, consumer)
        session.execute(text("ALTER TABLE research_evidence_dependency ENABLE TRIGGER research_evidence_dependency_guard"))
        with pytest.raises(DBAPIError, match="cycle"), session.begin_nested():
            graph_edge(session, consumer, producer)
