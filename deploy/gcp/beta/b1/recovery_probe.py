"""Current-image recovery exercise over one non-login fixture, never Q6.

Actual services/SQL/GCS/Cloud Tasks are used in production. The only injected
fault is loss of a successful task-create acknowledgement before its outbox
commit. Fixed count questions take C19's deterministic branch; answer admission
also requires a deterministic selection. No scientific payload is emitted.
"""
from dataclasses import replace
import datetime
import hashlib
import json
import os
from pathlib import Path
import uuid
import urllib.request

from sqlalchemy import select

VERSION = "ocean-beta-b1-recovery-v1"
ACTOR_ID = "e59c73d1-b9f1-4d0f-a48c-1e2dc773b334"
PROFILE = ("b1_recovery_fixture", VERSION, "b1-recovery@fixture.invalid", "B1 recovery fixture", "admin", "internal")
SNAPSHOT = "50bfdf551337e0b2ff1db4f1df83fe075c6a6b980cb8659f36d614d4d8bca459"
SOURCE_REVISION = "4872d04323c7e7b2bc1946ece41bd0a6333f39c0"
PHASES = {"prepare", "prepare-answer", "verify", "revoked"}


def key(name):
    return str(uuid.uuid5(uuid.UUID(ACTOR_ID), VERSION + ":" + name))


def fixture_actor(services, *, revoked=False):
    from api.auth import current_user_from_model
    from db.app_models import AppUser
    with services.research_run_service.session_factory() as session:
        row = session.get(AppUser, uuid.UUID(ACTOR_ID))
        if (row is None or (row.auth_provider, row.auth_subject, row.email, row.display_name, row.role, row.account_type) != PROFILE
                or row.status != ("suspended" if revoked else "active")):
            raise ValueError("Exact isolated recovery fixture required")
        actor = current_user_from_model(row)
    return replace(actor, status="active") if revoked else actor


def address(run):
    binding = run["context"]["binding"]
    return {"run_id": run["id"], "investigation_id": binding["investigation_id"], "conversation_id": binding["conversation_id"]}


class AckLoss:
    """One real successful create is observed, then its acknowledgement is lost."""
    def __init__(self, delegate):
        self.delegate, self.created = delegate, None

    def post(self, url, **kwargs):
        response = self.delegate.post(url, **kwargs)
        if response.status_code not in {200, 201} or response.json().get("name") != kwargs["json"]["task"]["name"]:
            raise ValueError("Task was not created; no fault-injection proof")
        self.created = response.json()["name"]
        from requests import ReadTimeout
        raise ReadTimeout("Injected lost acknowledgement after actual task creation")


class TraceRecovery:
    def __init__(self, delegate):
        self.delegate, self.post_status, self.get_status = delegate, None, None

    def post(self, url, **kwargs):
        response = self.delegate.post(url, **kwargs)
        self.post_status = response.status_code
        return response

    def get(self, url, **kwargs):
        response = self.delegate.get(url, **kwargs)
        self.get_status = response.status_code
        return response


def outbox(services, run_id):
    from db.app_models import ResearchRunOutbox
    with services.research_run_service.session_factory() as session:
        row = session.scalars(select(ResearchRunOutbox).where(ResearchRunOutbox.run_id == uuid.UUID(run_id))).one()
        return {"delivery_id": str(row.delivery_id), "state": row.state, "attempts": row.attempts}


def prepare(services, actor, snapshot):
    from db.app_models import ResearchInvestigation
    from orchestration.cloud_research_dispatch import CloudDispatchError
    runs, investigations = services.research_run_service, services.investigation_service
    with runs.session_factory() as session:
        if session.scalar(select(ResearchInvestigation.id).where(
                ResearchInvestigation.user_id == actor.id, ResearchInvestigation.name == VERSION)) is not None:
            raise ValueError("Recovery context exists; inspect rather than replay preparation")
    created = investigations.invoke("create", {"name": VERSION, "snapshot_id": snapshot,
        "scope": {"version": 1, "sources": {family: {"enabled": True, "filters": {}} for family in
            ("ctd", "metagenome", "remote_sensing", "edna_metabarcoding")}}, "idempotency_key": key("investigation")}, actor)
    investigation = created["investigation"]["id"]
    conversation = investigations.invoke("conversations/create", {"investigation_id": investigation,
        "name": "Recovery delivery", "idempotency_key": key("conversation")}, actor)["conversation"]["id"]
    investigations.invoke("conversations/create", {"investigation_id": investigation,
        "name": "Cross-context denial", "idempotency_key": key("other-conversation")}, actor)
    request = {"investigation_id": investigation, "conversation_id": conversation,
        "revision_id": created["context"]["id"], "expected_snapshot_id": created["context"]["snapshot_id"],
        "expected_payload_sha256": created["context"]["payload_sha256"], "question": "Count all datasets"}
    cancelled = runs.invoke("submit", {**request, "idempotency_key": key("cancel-submission")}, actor)["run"]
    if runs.dispatch_outbox(run_id=cancelled["id"], limit=1) != 1:
        raise ValueError("Cancelled fixture task was not durably dispatched")
    cancelled = runs.invoke("cancel", {**address(cancelled), "idempotency_key": key("cancel")}, actor)["run"]
    if cancelled["status"] != "cancelled":
        raise ValueError("Queued cancellation failed")
    retry = runs.invoke("submit", {**request, "idempotency_key": key("uncertain-submission")}, actor)["run"]
    real = runs.queue._transport()
    loss = AckLoss(real)
    runs.queue._session = loss
    try:
        try:
            runs.dispatch_outbox(run_id=retry["id"], limit=1)
        except CloudDispatchError:
            pass
        else:
            raise ValueError("Expected lost create acknowledgement")
    finally:
        runs.queue._session = real
    pending = outbox(services, retry["id"])
    if not loss.created or pending["state"] != "pending" or pending["attempts"] != 1:
        raise ValueError("Lost acknowledgement did not leave the exact pending outbox")
    trace = TraceRecovery(real)
    runs.queue._session = trace
    try:
        sent = runs.dispatch_outbox(run_id=retry["id"], limit=1)
    finally:
        runs.queue._session = real
    recovered = outbox(services, retry["id"])
    if (sent != 1 or recovered["state"] != "sent" or recovered["attempts"] != 2
            or trace.post_status != 409 or trace.get_status != 200):
        raise ValueError("Actual task conflict/readback did not recover the same delivery")
    child = runs.invoke("continue", {**address(cancelled), "idempotency_key": key("continue")}, actor)["run"]
    if child["continuation_of"] != cancelled["id"] or child["context"] != cancelled["context"]:
        raise ValueError("Continuation changed the submitted context")
    if runs.dispatch_outbox(run_id=child["id"], limit=1) != 1:
        raise ValueError("Continuation not durably dispatched")
    tasks = {kind: runs.queue.task(run_id=run["id"], delivery_id=outbox(services, run["id"])["delivery_id"])
        for kind, run in [("cancel", cancelled), ("uncertain", retry), ("continue", child)]}
    return {"state": "recovery_prepared", "tasks": tasks, "run_ids": {kind: run["id"] for kind, run in
        [("cancel", cancelled), ("uncertain", retry), ("continue", child)]},
        "lost_ack_after_provider_create_verified": True, "same_delivery_409_full_readback_recovered": True,
        "continuation_frozen_context_preserved": True, "new_fixed_count_questions": 3}


def heads(services, actor):
    from db.app_models import ResearchInvestigation, ResearchRun, ResearchRunAttempt, ResearchRunStep
    with services.research_run_service.session_factory() as session:
        investigation = session.scalars(select(ResearchInvestigation).where(
            ResearchInvestigation.user_id == actor.id, ResearchInvestigation.name == VERSION)).one()
        rows = session.scalars(select(ResearchRun).where(ResearchRun.user_id == actor.id,
            ResearchRun.investigation_id == investigation.id)).all()
        if len(rows) != 3 or any(row.original_question != "Count all datasets" or row.model_calls for row in rows):
            raise ValueError("Exactly three deterministic recovery runs required")
        child = [row for row in rows if row.continuation_of is not None]
        if len(child) != 1:
            raise ValueError("One exact recovery continuation required")
        parent = next(row for row in rows if row.id == child[0].continuation_of)
        retry = next(row for row in rows if row.id not in {parent.id, child[0].id})
        grouped = {"cancel": parent, "uncertain": retry, "continue": child[0]}
        result = {}
        for label, row in grouped.items():
            if (row.status != ("cancelled" if label == "cancel" else "completed") or row.lease_until is not None
                    or row.active_started_at is not None or session.scalar(select(ResearchRunAttempt.run_id).join(
                        ResearchRunStep, (ResearchRunStep.run_id == ResearchRunAttempt.run_id)
                        & (ResearchRunStep.step_id == ResearchRunAttempt.step_id)).where(
                        ResearchRunAttempt.run_id == row.id, ResearchRunStep.kind == "model").limit(1)) is not None):
                raise ValueError("Closed zero-model recovery runs required")
            result[label] = {"run_id": str(row.id), "investigation_id": str(row.investigation_id),
                "conversation_id": str(row.conversation_id), "event_cursor": row.event_cursor,
                "status": row.status, "model_calls": row.model_calls, "lease_closed": True,
                "revision_id": str(row.revision_id), "snapshot_id": row.snapshot_id,
                "payload_sha256": row.payload_sha256}
    return result


def prepare_answer(services, actor):
    from orchestration.research_synthesis import build_synthesis_pack, deterministic_selection
    current = heads(services, actor)
    target = current["uncertain"]
    verified = services.research_evidence_service.ensure_retained(run_id=target["run_id"], input_version=1, user=actor)
    if deterministic_selection(build_synthesis_pack(verified)) is None:
        raise ValueError("Recovery answer must not admit a provider call")
    request = {k: target[k] for k in ("run_id", "investigation_id", "conversation_id")}
    answer = services.research_answer_service.invoke("submit", {**request, "input_version": 1,
        "locale": "en", "idempotency_key": key("answer")}, actor)["job"]
    if services.research_answer_service.dispatch_outbox(job_id=answer["id"], limit=1) != 1:
        raise ValueError("Deterministic answer not dispatched")
    from db.app_models import ResearchAnswerOutbox
    with services.research_run_service.session_factory() as session:
        delivery = session.scalars(select(ResearchAnswerOutbox).where(ResearchAnswerOutbox.job_id == uuid.UUID(answer["id"]))).one()
        task = services.research_answer_service.queue.task(job_id=answer["id"], delivery_id=str(delivery.delivery_id))
    return {"state": "deterministic_answer_prepared", "heads": current, "job_id": answer["id"], "task": task,
        "deterministic_selection_checked_before_answer_admission": True}


def verify(services, actor, *, revoked=False):
    from db.app_models import ResearchAnswerJob, ResearchConversation
    from orchestration.research_runs import ResearchRunError
    from orchestration.research_evidence import ResearchEvidenceError
    current = heads(services, actor)
    target = current["uncertain"]
    request = {k: target[k] for k in ("run_id", "investigation_id", "conversation_id")}
    if revoked:
        for service, name, payload, error_type in [
            (services.research_run_service, "status", request, ResearchRunError),
            (services.research_evidence_service, "list", {**request, "input_version": 1}, ResearchEvidenceError),
        ]:
            try:
                service.invoke(name, payload, actor)
            except error_type as error:
                if error.status_code != 403:
                    raise ValueError("Revocation did not deny current owner") from None
            else:
                raise ValueError("Stale active principal exposed revoked evidence")
        return {"state": "revoked_fixture_reads_denied", "heads": current, "stale_principal_denied": True}
    with services.research_run_service.session_factory() as session:
        other = session.scalars(select(ResearchConversation).where(
            ResearchConversation.investigation_id == uuid.UUID(target["investigation_id"]),
            ResearchConversation.name == "Cross-context denial")).one()
        job = session.scalars(select(ResearchAnswerJob).where(ResearchAnswerJob.run_id == uuid.UUID(target["run_id"]))).one()
        job_id, cursor = str(job.id), job.event_cursor
        if job.status != "completed" or job.model_calls or job.lease_until is not None or job.active_started_at is not None:
            raise ValueError("Completed closed deterministic answer required")
    try:
        services.research_run_service.invoke("status", {**request, "conversation_id": str(other.id)}, actor)
    except ResearchRunError as error:
        if error.status_code != 404:
            raise ValueError("Wrong-context request did not fail closed") from None
    else:
        raise ValueError("Cross-context run substitution accepted")
    result = services.research_answer_service.invoke("status", {**request, "job_id": job_id}, actor)["job"]
    if result["answer"] is None or result["answer"]["model_used"] is not False:
        raise ValueError("Actual retained deterministic answer missing")
    return {"state": "current_image_recovery_verified", "heads": current, "job_id": job_id,
        "answer_event_cursor": cursor, "wrong_context_denied": True, "retained_answer_currently_readable": True,
        "model_calls": 0}


def main(phase):
    app = None
    result, code = {"version": VERSION, "state": "recovery_probe_rejected_or_uncertain", "phase": phase}, 2
    try:
        if phase not in PHASES:
            raise ValueError("Fixed recovery phase required")
        from api.v1_beta_question_entry import validate_environment
        from beta_entry import validate_serving_source
        validate_environment(os.environ, "api")
        validate_serving_source(os.environ)
        manifest = json.loads(Path("/opt/ocean/source-manifest.json").read_text())
        if manifest["revision"] != SOURCE_REVISION or len(manifest["sources"]) != 180:
            raise ValueError("Exact current API source image required")
        for name, digest in manifest["sources"].items():
            if name in {"deploy/gcp/beta/api/Dockerfile", "deploy/gcp/beta/api/prepare_context.py", "requirements/runtime.txt"}:
                continue
            path = Path("/opt/ocean") / ("beta_entry.py" if name == "deploy/gcp/beta/api/entry.py" else name)
            if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
                raise ValueError("Current image source bytes differ")
        host = json.loads(Path(os.environ["OCEAN_V1_HOST_CONFIG"]).read_text())
        if PROFILE[0] in host["allowed_providers"]:
            raise ValueError("Fixture must never gain public sign-in")
        from api.v1_host import create_from_environment
        app = create_from_environment()
        services = app.state.v1_services
        actor = fixture_actor(services, revoked=phase == "revoked")
        if phase == "prepare":
            result = prepare(services, actor, SNAPSHOT)
        elif phase == "prepare-answer":
            result = prepare_answer(services, actor)
        else:
            result = verify(services, actor, revoked=phase == "revoked")
        result.update(version=VERSION, phase=phase, source_revision=SOURCE_REVISION, fixture_id=ACTOR_ID,
            scientific_payloads_or_credentials_emitted=False, experiment_execution_enabled=False)
        code = 0
    except Exception:
        pass  # Never emit DB/provider exceptions, URLs with credentials or scientific rows.
    finally:
        if app is not None:
            app.state.v1_owned_engine.dispose()
        try:
            request = urllib.request.Request("http://127.0.0.1:9091/quitquitquit", data=b"", method="POST")
            with urllib.request.urlopen(request, timeout=5) as response:
                if response.status != 200:
                    raise ValueError("Proxy shutdown failed")
            result["proxy_shutdown_requested"] = True
        except Exception:
            code, result["state"] = 2, "proxy_shutdown_uncertain"
        result["captured_utc"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        print(json.dumps(result, sort_keys=True))
    return code
