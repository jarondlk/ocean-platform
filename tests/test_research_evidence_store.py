"""C21 actual committed C20 projection and receipt protection, local fakes only."""
import json
import uuid

import pytest
from sqlalchemy import create_engine, event, select

from db.app_models import AppBase, ResearchEvidenceReceipt
from tests.research_evidence_support import make_evidence_fixture
from tests.test_research_controller import FakeRuntime, tool


@pytest.fixture(scope="module")
def retained(tmp_path_factory):
    directory = tmp_path_factory.mktemp("c21-store")
    engine = create_engine("sqlite+pysqlite:///" + str(directory / "app.sqlite"))

    @event.listens_for(engine, "connect")
    def foreign_keys(connection, _):
        connection.execute("PRAGMA foreign_keys=ON")

    AppBase.metadata.create_all(engine)
    fixture, evidence = make_evidence_fixture(engine, directory)
    yield fixture, evidence
    engine.dispose()


@pytest.fixture
def actual(retained, monkeypatch):
    for name in ("ENABLE_V1_CATALOGUE", "ENABLE_V1_INVESTIGATIONS", "ENABLE_V1_RESEARCH_CONTROLLER"):
        monkeypatch.setenv(name, "true")
    fixture, evidence = retained
    fixture.state["runtime"] = None
    for values in fixture.retained.policy.values():
        values.clear()
    return fixture, evidence


def finished(fixture, question="Count all datasets"):
    run = fixture.submit(question)
    fixture.service.execute_delivery(**fixture.delivery(run))
    return run


def test_actual_committed_count_projection_is_deterministic_and_retained(actual):
    fixture, evidence = actual
    run = finished(fixture)
    verified = evidence.load_verified(run["id"], 1, fixture.user)
    assert verified.anchor.controller_result.outcome == "completed"
    assert len(verified.receipts) == 1 and verified.receipts[0].counts[0].value == 4
    retained = evidence.ensure_retained(run["id"], 1, fixture.user)
    assert retained.receipts == verified.receipts
    assert retained.anchor.execution_manifest == verified.anchor.execution_manifest
    assert retained.anchor.catalogue_policy_revision == verified.anchor.catalogue_policy_revision
    assert evidence.ensure_retained(run["id"], 1, fixture.user) == retained
    receipt = verified.receipts[0]
    assert evidence.resolve_attachment(fixture.user, receipt.attachment_reference.model_dump(mode="json")).sha256 == receipt.sha256
    with fixture.retained.factory() as session:
        assert session.get(ResearchEvidenceReceipt, receipt.id).state == "ready"
    opened = evidence.invoke("open", {"receipt_id": receipt.id, "expected_sha256": receipt.sha256}, fixture.user)
    assert opened["receipt"] == receipt.model_dump(mode="json")
    listing = evidence.invoke("list", {**fixture.address(run), "input_version": 1}, fixture.user)
    assert listing["total"] == 1 and listing["items"] == [opened["receipt"]]
    page = evidence.invoke("page", {"receipt_id": receipt.id, "expected_sha256": receipt.sha256, "section": "inputs", "limit": 2}, fixture.user)
    assert len(page["rows"]) == 2 and page["next_offset"] == 2
    exported = evidence.invoke("export", {"receipt_id": receipt.id, "expected_sha256": receipt.sha256, "format": "json"}, fixture.user)
    assert json.loads(exported["content_text"])["provenance"]["receipt_id"] == receipt.id


def test_owner_and_expected_hash_do_not_disclose_receipts(actual):
    from orchestration.research_evidence import ResearchEvidenceError
    fixture, evidence = actual
    run = finished(fixture)
    receipt = evidence.ensure_retained(run["id"], 1, fixture.user).receipts[0]
    for user in (fixture.retained.other, fixture.retained.admin):
        with pytest.raises(ResearchEvidenceError) as failure:
            evidence.invoke("open", {"receipt_id": receipt.id, "expected_sha256": receipt.sha256}, user)
        assert failure.value.status_code == 404
    with pytest.raises(ResearchEvidenceError) as failure:
        evidence.invoke("open", {"receipt_id": receipt.id, "expected_sha256": "0" * 64}, fixture.user)
    assert failure.value.status_code == 422


def test_reopen_current_policy_revocation_fails_but_retains_bytes(actual):
    from orchestration.research_evidence import ResearchEvidenceError
    fixture, evidence = actual
    run = finished(fixture)
    receipt = evidence.ensure_retained(run["id"], 1, fixture.user).receipts[0]
    fixture.retained.policy[receipt.binding.snapshot_id].add("synthetic-policy-epoch-change")
    with pytest.raises(ResearchEvidenceError) as failure:
        evidence.invoke("open", {"receipt_id": receipt.id, "expected_sha256": receipt.sha256}, fixture.user)
    assert failure.value.status_code == 403
    assert evidence.resolve_attachment(fixture.user, receipt.attachment_reference.model_dump(mode="json")) is None
    with fixture.retained.factory() as session:
        assert session.get(ResearchEvidenceReceipt, receipt.id).state == "ready"


def test_explicit_old_snapshot_receipt_attachment_preserves_original_binding(actual):
    fixture, evidence = actual
    receipt = evidence.ensure_retained(finished(fixture)["id"], 1, fixture.user).receipts[0]
    inv = fixture.retained.service.invoke("create", {"name": "C21 newer chat", "snapshot_id": fixture.retained.snapshots[1],
        "scope": fixture.retained.scope, "idempotency_key": str(uuid.uuid4())}, fixture.user)
    attached = fixture.retained.service.invoke("context/change", {"investigation_id": inv["investigation"]["id"],
        "expected_revision_id": inv["context"]["id"], "idempotency_key": str(uuid.uuid4()),
        "change": {"op": "attach", "reference": receipt.attachment_reference.model_dump(mode="json")}}, fixture.user)
    assert attached["context"]["snapshot_id"] != receipt.binding.snapshot_id
    assert attached["context"]["attachments"][0]["snapshot_id"] == receipt.binding.snapshot_id
    assert attached["context"]["resolution"][0]["status"] == "available"
    from db.app_models import ResearchEvidenceContextDependency
    with fixture.retained.factory() as session:
        assert session.scalar(select(ResearchEvidenceContextDependency).where(
            ResearchEvidenceContextDependency.operation_id == uuid.UUID(attached["operation"]["id"]))).state == "committed"


def test_distinct_dataset_pins_do_not_invent_a_union_or_synthesis_scope(actual):
    from orchestration.research_evidence import ResearchEvidenceError
    fixture, evidence = actual
    request = fixture.request()
    for identity in (fixture.retained.dataset_ids["ctd"], fixture.retained.dataset_ids["metagenome"]):
        changed = fixture.retained.service.invoke("context/change", {
            "investigation_id": request["investigation_id"], "expected_revision_id": request["revision_id"],
            "idempotency_key": str(uuid.uuid4()), "change": {"op": "pin", "reference": {
                "kind": "catalogue", "snapshot_id": request["expected_snapshot_id"], "id": identity}}}, fixture.user)
        request.update(revision_id=changed["context"]["id"], expected_payload_sha256=changed["context"]["payload_sha256"])
    run = fixture.service.invoke("submit", request, fixture.user)["run"]
    result = fixture.service.execute_delivery(**fixture.delivery(run))
    assert result["run"]["status"] == "awaiting_clarification"
    with pytest.raises(ResearchEvidenceError, match="evidence_ineligible"):
        evidence.ensure_retained(run["id"], 1, fixture.user)


@pytest.mark.parametrize("malformed", [False, True])
def test_committed_model_and_optional_repair_are_verified_before_open_projection(actual, malformed):
    fixture, evidence = actual
    identity = fixture.retained.dataset_ids["ctd"]
    actions = [tool("catalogue.open", object_id=identity, include_details=True)]
    fixture.state["runtime"] = FakeRuntime((["malformed"] if malformed else []) + actions)
    run = finished(fixture, f'Find dataset "{identity}"')
    verified = evidence.ensure_retained(run["id"], 1, fixture.user)
    assert verified.anchor.controller_result.outcome == "completed"
    assert verified.anchor.run_budget_high_water.model_calls >= 1
    assert verified.anchor.run_budget_high_water.malformed_repairs == int(malformed)
    assert len(verified.receipts) == 2 and verified.receipts[-1].kind == "catalogue"
    assert evidence.invoke("page", {"receipt_id": verified.receipts[-1].id,
        "expected_sha256": verified.receipts[-1].sha256}, fixture.user)["rows"][0]["id"] == identity


def test_unfinished_generation_preserves_honest_partial_receipts(actual):
    fixture, evidence = actual
    fixture.state["runtime"] = FakeRuntime(status="output_limit")
    run = finished(fixture, f'Find dataset "{fixture.retained.dataset_ids["ctd"]}"')
    verified = evidence.ensure_retained(run["id"], 1, fixture.user)
    assert verified.anchor.controller_result.outcome == "partial"
    assert verified.unresolved_work and len(verified.receipts) == 1


@pytest.mark.parametrize("table,column", [("research_run_payload", "payload_json"), ("research_run_step", "request_json"),
    ("research_run_manifest", "manifest_json"), ("research_run_input_history", "request_json")])
def test_retained_hash_corruption_fails_closed_without_new_effects(actual, table, column):
    from sqlalchemy import text
    from orchestration.research_evidence import ResearchEvidenceError
    fixture, evidence = actual
    run = finished(fixture)
    before = fixture.state["factory_calls"]
    with fixture.retained.factory.begin() as session:
        # SQLite intentionally has no native migration triggers. Verify the
        # independent read verifier against corrupt retained bytes directly.
        session.execute(text(f"UPDATE {table} SET {column} = '{{}}' WHERE run_id=:run_id"),
            {"run_id": uuid.UUID(run["id"]).hex})
    with pytest.raises(ResearchEvidenceError):
        evidence.load_verified(run["id"], 1, fixture.user)
    assert fixture.state["factory_calls"] == before


def test_ineligible_run_and_wrong_input_version_never_start_execution(actual):
    from orchestration.research_evidence import ResearchEvidenceError
    fixture, evidence = actual
    run = fixture.submit()
    before = fixture.state["factory_calls"]
    for version in (1, 2):
        with pytest.raises(ResearchEvidenceError) as failure:
            evidence.load_verified(run["id"], version, fixture.user)
        assert failure.value.code == "evidence_ineligible"
    assert fixture.state["factory_calls"] == before


def test_actual_declared_multi_input_analysis_reconstructs_derived_union(actual):
    from tests.research_evidence_support import make_union_fixture
    fixture, evidence = make_union_fixture(actual[0])
    request = fixture.request()
    changed = fixture.retained.service.invoke("context/change", {
        "investigation_id": request["investigation_id"], "expected_revision_id": request["revision_id"],
        "idempotency_key": str(uuid.uuid4()), "change": {"op": "pin", "reference": {
            "kind": "catalogue", "snapshot_id": request["expected_snapshot_id"], "id": "c21:synthetic:two-inputs"}}}, fixture.user)
    request.update(revision_id=changed["context"]["id"], expected_payload_sha256=changed["context"]["payload_sha256"])
    run = fixture.service.invoke("submit", request, fixture.user)["run"]
    assert fixture.service.execute_delivery(**fixture.delivery(run))["run"]["status"] == "completed"
    verified = evidence.ensure_retained(run["id"], 1, fixture.user)
    union = next(item for item in verified.receipts if item.operation_id == "c19.inventory_union")
    assert union.counts[0].value == 2 and len(union.origin_receipt_ids) == 2
    assert len(verified.receipts) == 4
    assert evidence.invoke("open", {"receipt_id": union.id, "expected_sha256": union.sha256}, fixture.user)["receipt"]["origin_receipt_ids"] == union.origin_receipt_ids


def test_continuation_prefix_requires_verified_parent_physical_origin(actual):
    from db.app_models import ResearchRunAttempt, ResearchRunStep
    fixture, evidence = actual
    identity = fixture.retained.dataset_ids["ctd"]
    fixture.state["runtime"] = FakeRuntime(status="output_limit")
    parent = finished(fixture, f'Find dataset "{identity}"')
    fixture.state["runtime"] = FakeRuntime([tool("catalogue.open", object_id=identity, include_details=True)])
    child = fixture.service.invoke("continue", {**fixture.address(parent), "idempotency_key": str(uuid.uuid4())}, fixture.user)["run"]
    assert fixture.service.execute_delivery(**fixture.delivery(child))["run"]["status"] == "completed"
    verified = evidence.ensure_retained(child["id"], 1, fixture.user)
    assert len(verified.receipts) == 2 and verified.anchor.run_budget_high_water.tool_actions == 1
    with fixture.retained.factory() as session:
        prefix = session.get(ResearchRunStep, (uuid.UUID(child["id"]), "input:1:inventory:1"))
        assert prefix.state == "committed"
        assert not session.scalars(select(ResearchRunAttempt).where(ResearchRunAttempt.run_id == prefix.run_id,
            ResearchRunAttempt.step_id == prefix.step_id)).all()


def test_actual_documentary_receipt_retains_exact_normalized_inputs_and_rejects_changed_search(actual):
    from copy import deepcopy
    from orchestration.frozen_documentary import FrozenDocumentaryProvider
    from orchestration.research_evidence import ResearchEvidenceError
    from tests.research_evidence_support import make_union_fixture
    fixture, evidence = make_union_fixture(actual[0])
    run = finished(fixture)
    verified = evidence.ensure_retained(run["id"], 1, fixture.user)
    provider = FrozenDocumentaryProvider(store=evidence.store, catalogue=evidence.catalogue,
        registration=fixture.retained.registrations[verified.anchor.binding.snapshot_id])
    evidence.documentary_provider = provider
    args = {"query": verified.anchor.effective_question, "binding": verified.anchor.binding,
        "effective_scope": verified.anchor.effective_scope, "current_actor": fixture.user,
        "expected_policy_revision": verified.anchor.catalogue_policy_revision,
        "permitted_input_manifest": [row for rows in verified.input_manifests_by_receipt.values() for row in rows]}
    raw = provider.search(**args)
    assert raw["excerpts"] and "採水手順" in raw["excerpts"][0]["text"]
    receipt = evidence.retain_documentary(run["id"], 1, raw, fixture.user, remaining_timeout=30)
    assert receipt.authority == "documentary" and receipt.total_rows.state == "unknown"
    page = evidence.invoke("page", {"receipt_id": receipt.id, "expected_sha256": receipt.sha256,
        "section": "inputs"}, fixture.user)
    assert page["rows"] == raw["inputs"] and page["section_total"]["value"] == len(raw["inputs"])
    assert evidence.invoke("list", {**fixture.address(run), "input_version": 1}, fixture.user)["total"] == 2
    changed = deepcopy(raw)
    changed["query_sha256"] = "0" * 64
    with pytest.raises(ResearchEvidenceError):
        evidence.retain_documentary(run["id"], 1, changed, fixture.user, remaining_timeout=30)
    evidence.documentary_provider = None
