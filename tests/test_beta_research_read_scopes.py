"""Beta-only authority fences over actual retained synthetic SQL/C09 services."""
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
import base64
import json
import os
from threading import get_ident
from types import MethodType
import uuid

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import func, select

from api.v1_beta_question_services import BetaResearchAnswerService, BetaResearchEvidenceService
from db.app_models import ResearchAnswerJob, ResearchAnswerOutbox, ResearchInvestigation, ResearchRun, ResearchRunOutbox
from ingestion.artifact_store import BoundedLocalStore
from ingestion.provenance_snapshot import SnapshotConflict
from orchestration.research_answers import ResearchAnswerError, ResearchAnswerService
from orchestration.research_evidence import ResearchEvidenceService
from tests.test_beta_question_services import public_app, questions as questions, submitted
from tests.test_beta_research_host import context as context
from tests.test_beta_snapshot_catalogue import sealed as sealed
from tests.test_v1_host import headers, independent as independent


@pytest.fixture
def completed(questions, monkeypatch):
    bundle, actor, _, _ = questions
    evidence, answers = bundle.research_evidence_service, bundle.research_answer_service
    assert isinstance(evidence, BetaResearchEvidenceService)
    assert isinstance(answers, BetaResearchAnswerService)
    assert not evidence.external_artifact_providers and evidence.documentary_provider is None
    store, original = evidence.store, evidence.store.add_reference
    references = []

    def outside_read_scope(identity, reference):
        assert store._active_read_scope() is None
        assert evidence.catalogue.resolver.authority._scope.get() is None
        references.append(reference)
        return original(identity, reference)

    monkeypatch.setattr(store, "add_reference", outside_read_scope)
    run = submitted(questions)
    task = json.loads(base64.b64decode(bundle.research_run_service.queue._session.task["httpRequest"]["body"]))
    result = bundle.research_run_service.execute_delivery(run_id=task["run_id"], delivery_id=task["delivery_id"])
    assert result["run"]["status"] == "completed"
    address = {"run_id": run["id"], "investigation_id": run["context"]["binding"]["investigation_id"],
        "conversation_id": run["context"]["binding"]["conversation_id"]}
    job = answers.invoke("submit", {**address, "input_version": 1, "locale": "en", "idempotency_key": str(uuid.uuid4())}, actor)["job"]
    answers.dispatch_outbox(job_id=job["id"])
    task = json.loads(base64.b64decode(answers.queue._session.task["httpRequest"]["body"]))
    result = answers.execute_delivery(job_id=task["job_id"], delivery_id=task["delivery_id"])
    assert result["job"]["status"] == "completed" and result["job"]["answer"]["model_used"] is False
    assert references  # Actual submission/retention/delivery exercised the guard.
    return questions, address, job


def _category(key):
    return ("activation" if "/activations/" in key else "control" if key.endswith("/control.json")
        else "manifest" if "/manifests/" in key else "object")


def _transport_counter(monkeypatch):
    reads, original = [], BoundedLocalStore.read

    def counted(store, key, **kwargs):
        reads.append((get_ident(), key))
        return original(store, key, **kwargs)

    monkeypatch.setattr(BoundedLocalStore, "read", counted)
    return reads


def _bytes(value):
    return json.dumps(value, separators=(",", ":"), ensure_ascii=False).encode()


def test_evidence_list_keeps_replay_authorization_and_payload_reads_while_reducing_authority(completed, monkeypatch):
    questions, address, _ = completed
    bundle, actor, _, _ = questions
    evidence = bundle.research_evidence_service
    calls, reads = Counter(), _transport_counter(monkeypatch)
    for owner, names in [(evidence, ("_verified", "_retain", "_source", "_policy", "_read_receipt", "_principal")),
                         (evidence.catalogue.resolver, ("resolve",)), (evidence.store, ("add_reference",))]:
        for name in names:
            original = getattr(owner, name)

            def counted(*args, _original=original, _name=name, **kwargs):
                calls[_name] += 1
                return _original(*args, **kwargs)

            monkeypatch.setattr(owner, name, counted)
    transaction = evidence._transaction
    monkeypatch.setattr(evidence, "_transaction", MethodType(ResearchEvidenceService._transaction, evidence))
    baseline = evidence.invoke("list", {**address, "input_version": 1}, actor)
    baseline_reads, baseline_calls = Counter(_category(key) for _, key in reads), calls.copy()
    monkeypatch.setattr(evidence, "_transaction", transaction)
    reads.clear()
    calls.clear()
    result = evidence.invoke("list", {**address, "input_version": 1}, actor)
    scoped_reads = Counter(_category(key) for _, key in reads)
    assert _bytes(result) == _bytes(baseline) and result["total"] == 1
    assert calls == baseline_calls
    assert calls["_verified"] == 1 and calls["_source"] == 5 and calls["_policy"] == 7
    assert calls["resolve"] == 12 and calls["add_reference"] == 2
    assert baseline_reads == {"activation": 30, "control": 37, "manifest": 17, "object": 39}
    assert scoped_reads == {"activation": 16, "control": 16, "manifest": 17, "object": 39}


@pytest.mark.parametrize("name", ["list", "status", "events"])
def test_answer_reads_keep_response_and_core_checks_with_one_current_fence(completed, monkeypatch, name):
    questions, address, job = completed
    bundle, actor, _, _ = questions
    answers = bundle.research_answer_service
    payload = address if name == "list" else {**address, "job_id": job["id"]}
    if name == "events":
        payload = {**payload, "after_cursor": 0, "limit": 100}
    calls, reads = Counter(), _transport_counter(monkeypatch)
    for owner, method in [(answers, "_actor"), (answers, "_source"), (answers.runs, "_principal"),
                          (answers.investigations.catalogue.resolver, "resolve")]:
        original = getattr(owner, method)

        def counted(*args, _original=original, _name=method, **kwargs):
            calls[_name] += 1
            return _original(*args, **kwargs)

        monkeypatch.setattr(owner, method, counted)
    baseline = ResearchAnswerService.invoke(answers, name, payload, actor)
    baseline_reads, baseline_calls = Counter(_category(key) for _, key in reads), calls.copy()
    reads.clear()
    calls.clear()
    result = answers.invoke(name, payload, actor)
    assert _bytes(result) == _bytes(baseline) and calls == baseline_calls
    assert calls["resolve"] == 3 and calls["_principal"] == 2
    assert baseline_reads == {"activation": 6, "control": 7, "manifest": 3, "object": 7}
    assert Counter(_category(key) for _, key in reads) == {"activation": 2, "control": 2, "manifest": 3, "object": 7}


@pytest.mark.parametrize("group,name", [("answers", "list"), ("answers", "status"), ("answers", "events"), ("evidence", "list")])
@pytest.mark.parametrize("change", ["control_generation", "activation_generation", "activation_bytes", "read_error"])
def test_closing_authority_failure_never_returns_ready_private_result(completed, monkeypatch, group, name, change):
    questions, address, job = completed
    bundle, actor, _, sealed = questions
    payload = {**address, "input_version": 1} if group == "evidence" else address
    if name in {"status", "events"}:
        payload = {**payload, "job_id": job["id"]}
    if name == "events":
        payload = {**payload, "after_cursor": 0, "limit": 100}
    evidence = bundle.research_evidence_service
    armed, changed = False, False
    if group == "answers":
        original = ResearchAnswerService.invoke

        def after_result(*args, **kwargs):
            nonlocal armed
            result = original(*args, **kwargs)
            armed = True
            return result

        monkeypatch.setattr(ResearchAnswerService, "invoke", after_result)
    else:
        original = evidence._read_receipt

        def after_receipt(*args, **kwargs):
            nonlocal armed
            result = original(*args, **kwargs)
            armed = True
            return result

        monkeypatch.setattr(evidence, "_read_receipt", after_receipt)
    original_read = BoundedLocalStore.read

    def changing(store, key, **kwargs):
        nonlocal changed
        target = key.endswith("/control.json") if change in {"control_generation", "read_error"} else "/activations/" in key
        if armed and target and not changed:
            changed = True
            if change == "read_error":
                raise RuntimeError("private-authority-failure-content")
            path = sealed[1] / "store" / key
            if change == "activation_bytes":
                path.write_bytes(path.read_bytes() + b" ")
            else:
                stat = path.stat()
                os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns + 1_000_000_000))
        return original_read(store, key, **kwargs)

    with TestClient(public_app(questions), base_url="http://127.0.0.1:8000") as client:
        monkeypatch.setattr(BoundedLocalStore, "read", changing)
        response = client.post("/research/" + group + "/" + name, json=payload, headers=headers(actor, sub="subject-1"))
    assert changed and response.status_code == 503
    assert set(response.json()) == {"error"}
    assert "private-authority-failure-content" not in response.text
    assert "receipt" not in response.text and job["id"] not in response.text


def test_nested_evidence_scopes_cleanup_after_failure_and_next_operation_is_fresh(completed, monkeypatch):
    questions, _, _ = completed
    bundle, _, _, _ = questions
    evidence = bundle.research_evidence_service
    reads = _transport_counter(monkeypatch)
    with pytest.raises(RuntimeError, match="body failed"):
        with evidence._transaction():
            with evidence.catalogue.read_scope():
                evidence.store.lifecycle()
                raise RuntimeError("body failed")
    assert evidence.store._active_read_scope() is None
    assert evidence.catalogue.resolver.authority._scope.get() is None
    with evidence._transaction():
        evidence.store.lifecycle()
    assert Counter(_category(key) for _, key in reads) == {"activation": 3, "control": 3}
    assert evidence.store._active_read_scope() is None
    assert evidence.catalogue.resolver.authority._scope.get() is None


def test_concurrent_answer_reads_have_independent_current_fences(completed, monkeypatch):
    questions, address, _ = completed
    bundle, actor, _, _ = questions
    reads = _transport_counter(monkeypatch)
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(bundle.research_answer_service.invoke, "list", address, actor) for _ in range(2)]
        values = [future.result() for future in futures]
    assert _bytes(values[0]) == _bytes(values[1])
    by_thread = {}
    for thread, key in reads:
        by_thread.setdefault(thread, Counter())[_category(key)] += 1
    assert len(by_thread) == 2
    assert all(counts == {"activation": 2, "control": 2, "manifest": 3, "object": 7} for counts in by_thread.values())


def test_evidence_closing_fence_runs_before_sql_commit(completed, monkeypatch):
    questions, address, _ = completed
    bundle, _, factory, sealed = questions
    evidence, armed, changed = bundle.research_evidence_service, False, False
    original = BoundedLocalStore.read

    def control_changes(store, key, **kwargs):
        nonlocal changed
        if armed and key.endswith("/control.json") and not changed:
            changed = True
            path = sealed[1] / "store" / key
            stat = path.stat()
            os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns + 1_000_000_000))
        return original(store, key, **kwargs)

    monkeypatch.setattr(BoundedLocalStore, "read", control_changes)
    with pytest.raises(SnapshotConflict):
        with evidence._transaction() as session:
            row = session.get(ResearchInvestigation, uuid.UUID(address["investigation_id"]))
            identity = row.id
            original_name = row.name
            row.name = "Synthetic metadata that must roll back"
            session.flush()
            armed = True
    with factory() as session:
        assert session.get(ResearchInvestigation, identity).name == original_name
    assert changed and evidence.store._active_read_scope() is None
    assert evidence.catalogue.resolver.authority._scope.get() is None


@pytest.mark.parametrize("name", ["submit", "cancel"])
def test_answer_mutations_are_not_surrounded_by_the_read_only_invoke_scope(questions, monkeypatch, name):
    bundle, actor, _, _ = questions
    answers = bundle.research_answer_service

    def mutation(_self, action, payload, user, **kwargs):
        assert action == name and user is actor
        assert answers.investigations.store._active_read_scope() is None
        assert answers.investigations.catalogue.resolver.authority._scope.get() is None
        return {"mutation": name}

    monkeypatch.setattr(ResearchAnswerService, "invoke", mutation)
    assert answers.invoke(name, {}, actor) == {"mutation": name}


def test_answer_domain_denial_is_preserved_and_scope_is_cleared(questions, monkeypatch):
    bundle, actor, _, _ = questions
    error = ResearchAnswerError("access_denied", 403)

    def denied(*args, **kwargs):
        raise error

    monkeypatch.setattr(ResearchAnswerService, "invoke", denied)
    with pytest.raises(ResearchAnswerError) as caught:
        bundle.research_answer_service.invoke("list", {}, actor)
    assert caught.value is error and caught.value.status_code == 403
    assert bundle.catalogue_service.resolver.store._active_read_scope() is None
    assert bundle.catalogue_service.resolver.authority._scope.get() is None


def test_exact_rollout_drain_keeps_history_and_cancellation_but_creates_no_new_work(questions, monkeypatch):
    bundle, actor, factory, _ = questions
    runs, answers = bundle.research_run_service, bundle.research_answer_service

    def finish(run):
        task = json.loads(base64.b64decode(runs.queue._session.task["httpRequest"]["body"]))
        result = runs.execute_delivery(run_id=task["run_id"], delivery_id=task["delivery_id"])
        assert result["run"]["status"] == "completed"
        return {"run_id": run["id"], "investigation_id": run["context"]["binding"]["investigation_id"],
            "conversation_id": run["context"]["binding"]["conversation_id"]}

    first = submitted(questions)
    first_address = finish(first)
    queued_answer = answers.invoke("submit", {**first_address, "input_version": 1, "locale": "en",
        "idempotency_key": str(uuid.uuid4())}, actor)["job"]
    queued_run = submitted(questions)
    third = submitted(questions)
    third_address = finish(third)  # Eligible for its first answer, but none exists.
    binding = third["context"]["binding"]
    new_run = {"investigation_id": binding["investigation_id"], "conversation_id": binding["conversation_id"],
        "revision_id": binding["revision_id"], "expected_snapshot_id": binding["snapshot_id"],
        "expected_payload_sha256": binding["payload_sha256"], "question": "Count all datasets",
        "idempotency_key": str(uuid.uuid4())}

    def counts():
        with factory() as session:
            return [session.scalar(select(func.count()).select_from(model))
                for model in [ResearchRun, ResearchRunOutbox, ResearchAnswerJob, ResearchAnswerOutbox]]

    before, calls = counts(), [len(runs.queue._session.calls), len(answers.queue._session.calls)]
    monkeypatch.setenv("ENABLE_V1_RESEARCH_DISPATCH", "false")
    monkeypatch.setenv("ENABLE_V1_SYNTHESIS", "false")
    with TestClient(public_app(questions), base_url="http://127.0.0.1:8000") as client:
        auth = headers(actor, sub="subject-1")
        assert client.get("/health/live").json() == {"status": "live", "execution_enabled": True}
        history = client.post("/research/answers/list", json=first_address, headers=auth)
        assert history.status_code == 200 and history.json()["items"][0]["id"] == queued_answer["id"]
        evidence = client.post("/research/evidence/list", json={**first_address, "input_version": 1}, headers=auth)
        assert evidence.status_code == 200 and evidence.json()["total"] == 1
        denied_run = client.post("/research/runs/submit", json=new_run, headers=auth)
        denied_answer = client.post("/research/answers/submit", json={**third_address, "input_version": 1,
            "locale": "en", "idempotency_key": str(uuid.uuid4())}, headers=auth)
        assert denied_run.status_code == denied_answer.status_code == 503
        assert counts() == before
        assert [len(runs.queue._session.calls), len(answers.queue._session.calls)] == calls
        cancelled_answer = client.post("/research/answers/cancel", json={**first_address,
            "job_id": queued_answer["id"], "idempotency_key": str(uuid.uuid4())}, headers=auth)
        queued_address = {"run_id": queued_run["id"],
            "investigation_id": queued_run["context"]["binding"]["investigation_id"],
            "conversation_id": queued_run["context"]["binding"]["conversation_id"]}
        cancelled_run = client.post("/research/runs/cancel", json={**queued_address,
            "idempotency_key": str(uuid.uuid4())}, headers=auth)
        assert cancelled_answer.status_code == cancelled_run.status_code == 200
        assert cancelled_answer.json()["job"]["status"] == cancelled_run.json()["run"]["status"] == "cancelled"
