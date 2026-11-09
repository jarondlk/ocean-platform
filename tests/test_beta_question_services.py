"""Real retained services + synthetic sources/SQL and explicit cloud transport.

No provider, GCS, Cloud Tasks or production SQL operation is performed here.
"""
import base64
import hashlib
import json
import time
import uuid
from dataclasses import replace

from fastapi.testclient import TestClient
from pydantic import SecretStr
import pytest

from api.v1_beta_question_services import BetaModelSettings, compose_beta_question_services
from api.v1_host import HostConfigurationError, create_host_app
from api.v1_research_controller_host import create_controller_app
from tests.test_beta_research_host import context as context
from tests.test_beta_snapshot_catalogue import sealed as sealed
from tests.test_cloud_research_dispatch import Transport, cloud_settings
from tests.test_v1_host import SECRET, headers, settings
from tests.test_v1_host import independent as independent


@pytest.fixture
def questions(context, monkeypatch):
    services, actor, factory, sealed = context
    from api.v1_catalogue_host import _canonical, load_snapshot_catalogue
    # Append a distinct synthetic activation; never reinterpret a context-only
    # activation as Research authority or overwrite its original immutable bytes.
    activation = json.loads((sealed[1] / "activation.json").read_text())
    activation["research_enabled"] = True
    activation["authorization_ref"] = "chat-20261105-prioritize-beta-research-questions"
    raw = _canonical(activation)
    digest = hashlib.sha256(raw).hexdigest()
    key = "v1/catalogue/activations/" + digest + ".json"
    path = sealed[1] / "store" / key
    with path.open("xb") as handle:
        handle.write(raw)
    source = sealed[0].with_name("research-source.json")
    binding = json.loads(sealed[0].read_text())
    binding.update(activation_object=key, activation_sha256=digest)
    source.write_bytes(_canonical(binding))
    source.chmod(0o444)
    catalogue, browser = load_snapshot_catalogue(source, project_id="ocean-v1-beta-20261101",
        site_id=services.investigation_service.site_id, cursor_key=b"synthetic-independent-test-cursor" * 2,
        context_retention=True, research_retention=True, _allow_test_owner=True,
        _test_store=services.catalogue_service.resolver.store._store)
    for flag in ("SHELL", "CATALOGUE", "CATALOGUE_BROWSER", "INVESTIGATIONS", "RESEARCH_RUNS",
                 "RESEARCH_CONTROLLER", "RESEARCH_DISPATCH", "EVIDENCE", "SYNTHESIS"):
        monkeypatch.setenv("ENABLE_V1_" + flag, "true")
    for flag in ("EXPERIMENTS", "EXPERIMENT_DISPATCH", "EXPERIMENT_WORKSPACE"):
        monkeypatch.setenv("ENABLE_V1_" + flag, "false")
    bundle = compose_beta_question_services(session_factory=factory,
        catalogue_service=catalogue, catalogue_browser=browser,
        cloud_settings=cloud_settings(), model_settings=BetaModelSettings.model_validate({
            "model": "gemini-3.8-flash", "location": "global", "max_output_tokens": 4096}))
    for service in (bundle.research_run_service, bundle.research_answer_service):
        service.queue._session = Transport()
    def no_model(**kwargs):
        pytest.fail("Deterministic inventory acceptance must not call a provider")
    monkeypatch.setattr(bundle.research_answer_service.runtime, "structured_chat_result", no_model)
    return bundle, actor, factory, sealed


def public_app(questions):
    bundle, _, factory, _ = questions
    return create_host_app(settings=settings(project_id="ocean-v1-beta-20261101", site_id=bundle.investigation_service.site_id),
        session_factory=factory, internal_secret=SecretStr(SECRET), services=bundle,
        context_mutations=True, research_execution=True, _allow_test_sqlite=True)


def invoker(settings, **changes):
    return {"iss": "https://accounts.google.com", "aud": settings.controller_origin,
        "sub": settings.task_invoker_subject, "email": settings.task_invoker_email,
        "email_verified": True, "iat": int(time.time()), "exp": int(time.time()) + 3600, **changes}


def private_app(questions, **claims):
    bundle = questions[0]
    return create_controller_app(settings=bundle.cloud_settings, runs=bundle.research_run_service,
        answers=bundle.research_answer_service,
        token_verifier=lambda token, audience: invoker(bundle.cloud_settings, **claims))


def submitted(questions):
    bundle, actor, _, sealed = questions
    investigation = bundle.investigation_service.invoke("create", {"name": "Synthetic research integration",
        "snapshot_id": sealed[2]["index_id"], "scope": {"version": 1, "sources": {
            family: {"enabled": True, "filters": {}} for family in
            ("ctd", "metagenome", "remote_sensing", "edna_metabarcoding")}},
        "idempotency_key": str(uuid.uuid4())}, actor)
    conversation = bundle.investigation_service.invoke("conversations/create", {
        "investigation_id": investigation["investigation"]["id"], "name": "Synthetic question",
        "idempotency_key": str(uuid.uuid4())}, actor)["conversation"]
    request = {"investigation_id": investigation["investigation"]["id"], "conversation_id": conversation["id"],
        "revision_id": investigation["context"]["id"], "expected_snapshot_id": investigation["context"]["snapshot_id"],
        "expected_payload_sha256": investigation["context"]["payload_sha256"], "question": "Count all datasets",
        "idempotency_key": str(uuid.uuid4())}
    with TestClient(public_app(questions), base_url="http://127.0.0.1:8000") as client:
        bootstrap = client.get("/v1/runtime", headers=headers(actor, sub="subject-1"))
        assert bootstrap.status_code == 200, bootstrap.text
        runtime = bootstrap.json()
        assert runtime["research_runs"]["submit_enabled"] is True
        response = client.post("/research/runs/submit", json=request, headers=headers(actor, sub="subject-1"))
        assert response.status_code == 200, response.text
        return response.json()["run"]


def test_question_is_durable_before_private_delivery_and_answer_reopens(questions):
    bundle, actor, _, _ = questions
    run = submitted(questions)
    assert run["status"] == "queued"
    task = bundle.research_run_service.queue._session.task
    payload = base64.b64decode(task["httpRequest"]["body"])
    with TestClient(private_app(questions)) as worker:
        for _ in range(2):  # Duplicate delivery must retain the same result.
            response = worker.post("/internal/research/run", content=payload,
                headers={"Authorization": "Bearer synthetic-test", "Content-Type": "application/json"})
            assert response.status_code == 200, response.text
    address = {"run_id": run["id"], "investigation_id": run["context"]["binding"]["investigation_id"],
               "conversation_id": run["context"]["binding"]["conversation_id"]}
    with TestClient(public_app(questions), base_url="http://127.0.0.1:8000") as client:
        completed = client.post("/research/runs/status", json=address, headers=headers(actor, sub="subject-1"))
        assert completed.status_code == 200
        assert completed.json()["run"]["status"] == "completed"
        with questions[2].begin() as session:
            bundle.research_evidence_service._verified(session, run["id"], 1, actor)
        response = client.post("/research/answers/submit", json={**address, "input_version": 1,
            "locale": "en", "idempotency_key": str(uuid.uuid4())}, headers=headers(actor, sub="subject-1"))
        assert response.status_code == 200, response.text
        job = response.json()["job"]
    task = bundle.research_answer_service.queue._session.task
    with TestClient(private_app(questions)) as worker:
        response = worker.post("/internal/research/answer", content=base64.b64decode(task["httpRequest"]["body"]),
            headers={"Authorization": "Bearer synthetic-test", "Content-Type": "application/json"})
        assert response.status_code == 200, response.text
    # A newly built public app reads the committed answer and current authority.
    with TestClient(public_app(questions), base_url="http://127.0.0.1:8000") as client:
        response = client.post("/research/answers/status", json={**address, "job_id": job["id"]}, headers=headers(actor, sub="subject-1"))
        assert response.status_code == 200, response.text
        from db.app_models import ResearchAnswerJob
        with questions[2]() as session:
            reason = session.get(ResearchAnswerJob, uuid.UUID(job["id"])).reason_code
        assert response.json()["job"]["status"] == "completed", reason
        assert response.json()["job"]["answer"] is not None


@pytest.mark.parametrize("claims", [{"sub": "999999999999999999999"}, {"email_verified": False},
    {"email": "other@ocean-v1-beta-20261101.iam.gserviceaccount.com"}, {"aud": "https://legacy.invalid"},
    {"iss": "https://evil.invalid"}, {"exp": 1}, {"iat": 1}])
def test_private_delivery_requires_exact_current_google_invoker(questions, claims):
    bundle = questions[0]
    with TestClient(private_app(questions, **claims)) as client:
        response = client.post("/internal/research/run", json={"version": "research-cloud-delivery-v1",
            "run_id": str(uuid.uuid4()), "delivery_id": str(uuid.uuid4())},
            headers={"Authorization": "Bearer synthetic-test", "X-CloudTasks-TaskName": "spoofed"})
        assert response.status_code == 401
    assert bundle.research_run_service.queue._session.calls == []


def test_read_only_host_cannot_accept_question_bundle_or_execution_flags(questions):
    bundle, _, factory, _ = questions
    with pytest.raises(HostConfigurationError):
        create_host_app(settings=settings(), session_factory=factory, internal_secret=SecretStr(SECRET),
            services=bundle, _allow_test_sqlite=True)
    with pytest.raises(HostConfigurationError):
        replace(bundle, research_run_service=replace_queue(bundle.research_run_service)).validate(
            session_factory=factory, site_id=bundle.investigation_service.site_id, research_execution=True)


def replace_queue(service):
    from copy import copy
    from orchestration.research_dispatch import FakeResearchQueue
    result = copy(service)
    result.queue = FakeResearchQueue()
    return result


@pytest.mark.parametrize("body,status", [
    ('{"version":"research-cloud-delivery-v1","run_id":"invalid","delivery_id":"invalid"}', 422),
    ('{"version":"research-cloud-delivery-v1","version":"duplicate"}', 422),
    ('{"owner_id":"never-accept-task-owner"}', 422),
    ('x' * 1025, 413),
])
def test_private_delivery_rejects_malformed_and_task_supplied_authority(questions, body, status):
    with TestClient(private_app(questions)) as client:
        response = client.post("/internal/research/run", content=body,
            headers={"Authorization": "Bearer synthetic-test", "Content-Type": "application/json"})
        assert response.status_code == status


def test_cloud_task_headers_cannot_replace_authentication(questions):
    with TestClient(private_app(questions)) as client:
        response = client.post("/internal/research/run", json={}, headers={"X-CloudTasks-TaskName": "spoofed"})
        assert response.status_code == 401


def test_busy_duplicate_is_retried_instead_of_acknowledging_unfinished_execution(questions, monkeypatch):
    bundle = questions[0]
    run = submitted(questions)
    task = bundle.research_run_service.queue._session.task
    monkeypatch.setattr(bundle.research_run_service, "execute_delivery", lambda **kw: {"run": {"status": "running"}})
    with TestClient(private_app(questions)) as client:
        response = client.post("/internal/research/run", content=base64.b64decode(task["httpRequest"]["body"]),
            headers={"Authorization": "Bearer synthetic-test", "Content-Type": "application/json"})
        assert response.status_code == 503
    assert bundle.research_run_service.invoke("status", {
        "run_id": run["id"], "investigation_id": run["context"]["binding"]["investigation_id"],
        "conversation_id": run["context"]["binding"]["conversation_id"]}, questions[1])["run"]["status"] == "queued"


def test_pending_outbox_recovers_from_lost_transport_without_resubmitting_question(questions):
    from sqlalchemy import select
    from db.app_models import ResearchRunOutbox
    bundle, _, factory, _ = questions
    transport = bundle.research_run_service.queue._session
    transport.post_status = 503
    run = submitted(questions)  # Accepted SQL mutation survives queue failure.
    with factory() as session:
        row = session.scalar(select(ResearchRunOutbox))
        assert str(row.run_id) == run["id"] and row.state == "pending"
        original_delivery = str(row.delivery_id)
    transport.post_status = 200
    with TestClient(private_app(questions)) as client:
        response = client.post("/internal/research/dispatch", json={"version": "research-cloud-dispatch-v1"},
            headers={"Authorization": "Bearer synthetic-test"})
        assert response.status_code == 200
    with factory() as session:
        rows = list(session.scalars(select(ResearchRunOutbox)))
        assert len(rows) == 1 and rows[0].state == "sent" and str(rows[0].delivery_id) == original_delivery
