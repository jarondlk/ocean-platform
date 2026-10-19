"""C20 owner-scoped durable run state and lease-fenced replay journal.

Only explicitly supplied v1 stores, controllers and queues are used. External
controller calls execute after database transactions have closed.
"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import json
import uuid

import config

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from api.auth import CurrentUser, current_user_from_model
from db.app_models import (
    AppUser, ResearchConversation, ResearchInvestigation, ResearchRun,
    ResearchRunAttempt, ResearchRunEvent, ResearchRunInputHistory,
    ResearchRunManifest, ResearchRunOutbox, ResearchRunPayload, ResearchRunStep,
)
from schema.research_controller import BudgetSnapshot, ControllerLimits, ControllerResult, canonical_json
from orchestration.catalogue_service import catalogue_access_binding

VERSION = "research-runs-v1"
MAX_LIST_PAGE_BYTES = 8 * 1024 * 1024
TERMINAL = frozenset({"completed", "partial", "cancelled", "failed"})
TEXT = {
    "accepted": ("Research question accepted", "質問を受け付けました"),
    "started": ("Research execution started", "調査を開始しました"),
    "progress": ("Research step retained", "調査のステップを保存しました"),
    "clarification": ("A complete clarified question is required", "確認した質問の全文を入力してください"),
    "resumed": ("Research execution resumed", "調査を再開しました"),
    "completed": ("Requested evidence exploration completed", "要求された根拠の探索が完了しました"),
    "partial": ("Exploration stopped with partial evidence", "一部の根拠を保存して探索を停止しました"),
    "cancelled": ("Research execution cancelled", "調査をキャンセルしました"),
    "failed": ("Research execution is unavailable", "調査を実行できません"),
}


def _json(value):
    return canonical_json(value)


def _hash(value):
    return hashlib.sha256(_json(value).encode("utf-8")).hexdigest()


def _text(kind):
    en, ja = TEXT[kind]
    return {"en": en, "ja": ja}


def _utc(value):
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


class ResearchRunError(Exception):
    def __init__(self, code="runs_unavailable", status_code=503):
        super().__init__(code)
        self.code, self.status_code = code, status_code
        self.message = {
            "authentication_required": "Authentication is required",
            "access_denied": "Research run access is denied",
            "not_found": "Research run was not found",
            "conflict": "Research run request conflicts with retained state",
            "invalid_request": "Research run request is invalid",
        }.get(code, "Research execution is unavailable")


@dataclass(frozen=True)
class RunLease:
    run_id: str
    epoch: int
    input_version: int


class ResearchRunService:
    def __init__(self, *, session_factory, site_id, investigations,
                 controller_factory=None, queue=None, enabled=None,
                 dispatch_enabled=None, lease_seconds=180, db_clock=None):
        if (not callable(session_factory) or not isinstance(site_id, str)
                or not site_id.startswith("v1:") or investigations.site_id != site_id
                or investigations.session_factory is not session_factory
                or not callable(getattr(investigations, "load_for_submission", None))):
            raise ValueError("Explicit matching independent v1 stores required")
        if controller_factory is not None and not callable(controller_factory):
            raise ValueError("Controller factory must be explicit")
        if queue is not None and not callable(getattr(queue, "enqueue", None)):
            raise ValueError("Queue must implement enqueue")
        if type(lease_seconds) not in (int, float) or not 0 < lease_seconds <= 180:
            raise ValueError("Lease must be bounded by the active execution limit")
        self.session_factory, self.site_id, self.investigations = session_factory, site_id, investigations
        self.controller_factory, self.queue = controller_factory, queue
        self.enabled = enabled if enabled is not None else config.v1_research_runs_enabled
        self.dispatch_enabled = dispatch_enabled if dispatch_enabled is not None else config.v1_research_dispatch_enabled
        self.lease_seconds, self.db_clock = float(lease_seconds), db_clock

    @property
    def dispatch_available(self):
        return self.queue is not None and self.controller_factory is not None

    @contextmanager
    def _transaction(self):
        with self.session_factory() as session:
            with session.begin():
                yield session

    def _now(self, session):
        if self.db_clock is not None:
            value = self.db_clock()
        else:
            expression = func.clock_timestamp() if session.bind.dialect.name == "postgresql" else func.current_timestamp()
            value = session.scalar(select(expression))
        if not isinstance(value, datetime):
            raise ResearchRunError()
        return _utc(value)

    def _principal(self, session, *, user=None, owner_id=None):
        if user is not None and not isinstance(user, CurrentUser):
            raise ResearchRunError("authentication_required", 401)
        identity = user.id if user is not None else owner_id
        # NO KEY UPDATE fences role/status changes while allowing C17 audit/FK
        # KEY SHARE checks, avoiding an owner/investigation lock-order cycle.
        current = session.scalar(select(AppUser).where(AppUser.id == identity).with_for_update(key_share=True))
        if current is None:
            raise ResearchRunError("access_denied", 403)
        actor = current_user_from_model(current)
        if actor.status != "active" or not {"chat:use", "data:read"} <= actor.permissions:
            raise ResearchRunError("access_denied", 403)
        if user is not None and any(getattr(actor, key) != getattr(user, key) for key in (
            "id", "email", "role", "status", "account_type", "auth_provider", "permissions",
        )):
            raise ResearchRunError("access_denied", 403)
        return actor

    def _dispatch_required(self):
        try:
            if not self.enabled() or not self.dispatch_enabled() or not self.dispatch_available or not config.v1_research_controller_enabled():
                raise ResearchRunError()
        except ResearchRunError:
            raise
        except Exception:
            raise ResearchRunError() from None

    def _owned(self, session, data, actor):
        run = session.scalar(select(ResearchRun).where(
            ResearchRun.id == uuid.UUID(str(data["run_id"])),
            ResearchRun.user_id == actor.id,
            ResearchRun.investigation_id == uuid.UUID(str(data["investigation_id"])),
            ResearchRun.conversation_id == uuid.UUID(str(data["conversation_id"])),
        ).with_for_update())
        if run is None:
            raise ResearchRunError("not_found", 404)
        self._check_context(run, actor, session=session)
        return run

    def _check_context(self, run, actor, *, require_active=False, session=None):
        try:
            frozen = json.loads(run.context_json)
            if {key: frozen[key] for key in self._binding(run)} != self._binding(run) or _hash(frozen["context"]) != run.payload_sha256:
                raise ValueError("Changed frozen binding")
            if require_active:
                if session is not None:
                    investigation = session.scalar(select(ResearchInvestigation).where(
                        ResearchInvestigation.id == run.investigation_id,
                        ResearchInvestigation.user_id == actor.id,
                    ).with_for_update().execution_options(populate_existing=True))
                    if investigation is None or investigation.status != "active":
                        raise ValueError("Investigation is no longer active")
                current = self.investigations.load_for_submission(
                    investigation_id=str(run.investigation_id), conversation_id=str(run.conversation_id),
                    revision_id=str(run.revision_id), user=actor)
                if current != frozen:
                    raise ValueError("Changed frozen context")
            else:
                context = self.investigations.invoke("context/get", {
                    "investigation_id": str(run.investigation_id), "revision_id": str(run.revision_id),
                }, actor)["context"]
                if (context["snapshot_id"] != run.snapshot_id or context["payload_sha256"] != run.payload_sha256
                        or any(entry["status"] != "available" for entry in context["resolution"])):
                    raise ValueError("Context access changed")
            if session is not None:
                manifest = session.get(ResearchRunManifest, (run.id, run.input_version))
                if manifest is not None:
                    witness = json.loads(manifest.manifest_json)
                    if witness.get("actor_binding") is not None and witness["actor_binding"] != catalogue_access_binding(actor):
                        raise ValueError("Changed owner access epoch")
                    if witness.get("catalogue_policy_revision") is not None and witness["catalogue_policy_revision"] != self.investigations.catalogue.resolver.resolve(actor, run.snapshot_id).revision:
                        raise ValueError("Changed current source policy")
        except Exception:
            raise ResearchRunError("access_denied", 403) from None

    @staticmethod
    def _binding(run):
        return {key: str(getattr(run, key)) for key in (
            "investigation_id", "conversation_id", "revision_id", "snapshot_id", "payload_sha256",
        )}

    def _public(self, run):
        frozen = json.loads(run.context_json)["context"]
        return {
            "id": str(run.id), "context": {"binding": self._binding(run),
                "scope": frozen["scope"], "attachments": frozen["attachments"], "pins": frozen["pins"]},
            "question": run.original_question, "status": run.status,
            "active_elapsed_ms": run.active_elapsed_ms, "event_cursor": 0,
            "latest_event_cursor": run.event_cursor, "activity": [],
            "continuation_of": str(run.continuation_of) if run.continuation_of else None,
            "clarification": _text("clarification") if run.status == "awaiting_clarification" else None,
            "clarification_id": str(run.clarification_id) if run.clarification_id else None,
            "result": None, "error": _text("failed") if run.status == "failed" else None, "synthetic": False,
        }

    def _envelope(self, run):
        return {"version": VERSION, "run": self._public(run)}

    def _event(self, session, run, kind):
        run.event_cursor += 1
        session.add(ResearchRunEvent(run_id=run.id, cursor=run.event_cursor, kind=kind,
                                    elapsed_ms=run.active_elapsed_ms, summary_json=_json(_text(kind))))

    def _outbox(self, session, run):
        session.add(ResearchRunOutbox(run_id=run.id, input_version=run.input_version))

    @staticmethod
    def _input(session, run, user, name, data, *, result=None):
        sequence = (session.scalar(select(func.max(ResearchRunInputHistory.sequence)).where(ResearchRunInputHistory.run_id == run.id)) or 0) + 1
        session.add(ResearchRunInputHistory(user_id=user.id, run_id=run.id,
            sequence=sequence, kind=name, idempotency_key=data["idempotency_key"],
            request_json=_json({"operation": name, "request": data}), request_sha256=_hash({"operation": name, "request": data}),
            effective_question=(result or run).effective_question, result_run_id=(result or run).id))

    def _replay(self, session, actor, name, data):
        old = session.scalar(select(ResearchRunInputHistory).where(
            ResearchRunInputHistory.user_id == actor.id,
            ResearchRunInputHistory.idempotency_key == data["idempotency_key"],
        ))
        if old is None:
            return None
        if old.request_sha256 != _hash({"operation": name, "request": data}):
            raise ResearchRunError("conflict", 409)
        run = session.get(ResearchRun, old.result_run_id)
        self._check_context(run, actor, session=session)
        return self._envelope(run)

    def invoke(self, name, payload, user):
        # The shared strict DTO is also applied to direct service callers.
        from schema.research_runs import RUN_REQUEST_MODELS
        try:
            model = RUN_REQUEST_MODELS[name]
            data = model.model_validate(payload).model_dump(mode="json")
        except (KeyError, ValueError, TypeError):
            raise ResearchRunError("invalid_request", 422) from None
        if not self.enabled():
            raise ResearchRunError()
        for attempt in range(2):
            try:
                with self._transaction() as session:
                    actor = self._principal(session, user=user)
                    if name in {"submit", "cancel", "clarify", "continue"}:
                        replay = self._replay(session, actor, name, data)
                        if replay is not None:
                            return replay
                    if name == "submit":
                        self._dispatch_required()
                        frozen = self.investigations.load_for_submission(
                            investigation_id=data["investigation_id"], conversation_id=data["conversation_id"],
                            revision_id=data["revision_id"], user=actor,
                        )
                        if frozen["snapshot_id"] != data["expected_snapshot_id"] or frozen["payload_sha256"] != data["expected_payload_sha256"]:
                            raise ResearchRunError("conflict", 409)
                        run = self._new_run(session, actor, frozen, data["question"])
                        self._input(session, run, actor, name, data)
                        return self._envelope(run)
                    if name == "list":
                        return self._list(session, actor, data)
                    run = self._owned(session, data, actor)
                    if name == "status":
                        return self._envelope(run)
                    if name == "events":
                        return self._events(session, run, data)
                    if name == "cancel":
                        if run.status not in TERMINAL:
                            self._settle(session, run)
                            run.cancellation_requested, run.status = True, "cancelled"
                            run.lease_epoch += 1
                            run.lease_until = run.active_started_at = run.clarification_id = None
                            run.version += 1
                            self._event(session, run, "cancelled")
                        self._input(session, run, actor, name, data)
                        return self._envelope(run)
                    self._dispatch_required()
                    if name == "clarify":
                        self._check_context(run, actor, require_active=True, session=session)
                        if run.status != "awaiting_clarification" or str(run.clarification_id) != data["clarification_id"]:
                            raise ResearchRunError("conflict", 409)
                        run.effective_question = data["answer"]
                        run.input_version += 1
                        run.status, run.clarification_id, run.checkpoint_json = "queued", None, "{}"
                        run.controller_result_json = None
                        run.version += 1
                        self._input(session, run, actor, name, data)
                        self._event(session, run, "resumed")
                        self._outbox(session, run)
                        return self._envelope(run)
                    if name == "continue":
                        self._check_context(run, actor, require_active=True, session=session)
                        if run.status not in {"partial", "cancelled", "failed"}:
                            raise ResearchRunError("conflict", 409)
                        child = self._new_run(session, actor, json.loads(run.context_json), run.effective_question, parent=run)
                        self._input(session, run, actor, name, data, result=child)
                        return self._envelope(child)
            except IntegrityError:
                if attempt:
                    raise ResearchRunError("conflict", 409) from None
        raise ResearchRunError()

    def _new_run(self, session, actor, frozen, question, *, parent=None):
        run = ResearchRun(id=uuid.uuid4(), user_id=actor.id,
            **{key: uuid.UUID(frozen[key]) for key in ("investigation_id", "conversation_id", "revision_id")},
            snapshot_id=frozen["snapshot_id"], payload_sha256=frozen["payload_sha256"],
            context_json=_json(frozen), original_question=question, effective_question=question,
            continuation_of=parent.id if parent else None, status="queued", version=1, input_version=1,
            event_cursor=0, active_elapsed_ms=0, tool_actions=0, model_calls=0, malformed_repairs=0,
            lease_epoch=0, cancellation_requested=False, checkpoint_json="{}",
            created_at=self._now(session), updated_at=self._now(session))
        session.add(run)
        self._check_context(run, actor, require_active=True, session=session)
        session.flush()
        self._event(session, run, "accepted")
        self._outbox(session, run)
        return run

    def _list(self, session, actor, data):
        investigation = session.scalar(select(ResearchInvestigation).where(
            ResearchInvestigation.id == uuid.UUID(data["investigation_id"]), ResearchInvestigation.user_id == actor.id))
        conversation = session.scalar(select(ResearchConversation).where(
            ResearchConversation.id == uuid.UUID(data["conversation_id"]), ResearchConversation.investigation_id == uuid.UUID(data["investigation_id"])))
        if investigation is None or conversation is None:
            raise ResearchRunError("not_found", 404)
        statement = select(ResearchRun.id).where(ResearchRun.user_id == actor.id,
            ResearchRun.investigation_id == investigation.id, ResearchRun.conversation_id == conversation.id)
        snapshots = session.scalars(select(ResearchRun.snapshot_id).where(
            ResearchRun.user_id == actor.id, ResearchRun.investigation_id == investigation.id,
            ResearchRun.conversation_id == conversation.id).distinct()).all()
        policies = [(sid, self.investigations.catalogue.resolver.resolve(actor, sid).revision) for sid in sorted(snapshots)]
        access_epoch = [catalogue_access_binding(actor), policies]
        cursor = data.get("cursor")
        if cursor:
            try:
                before, witness = cursor.split(".", 1)
                if witness != _hash([access_epoch, str(investigation.id), str(conversation.id), before]):
                    raise ValueError()
                statement = statement.where(ResearchRun.id > uuid.UUID(before))
            except (ValueError, AttributeError):
                raise ResearchRunError("invalid_request", 422) from None
        identities = session.scalars(statement.order_by(ResearchRun.id).limit(data["limit"] + 1)).all()
        page, page_ids, size = [], [], 0
        for identity in identities[:data["limit"]]:
            run = session.get(ResearchRun, identity)
            self._check_context(run, actor, session=session)
            value = self._public(run)
            value_size = len(_json(value).encode("utf-8"))
            if page and size + value_size > MAX_LIST_PAGE_BYTES:
                break
            if value_size > MAX_LIST_PAGE_BYTES:
                raise ResearchRunError()
            page.append(value)
            page_ids.append(identity)
            size += value_size
        next_cursor = None
        if len(identities) > len(page):
            before = str(page_ids[-1])
            next_cursor = before + "." + _hash([access_epoch, str(investigation.id), str(conversation.id), before])
        return {"version": VERSION, "items": page, "next_cursor": next_cursor}

    def _events(self, session, run, data):
        after = data["after_cursor"]
        if after > run.event_cursor:
            raise ResearchRunError("conflict", 409)
        rows = session.scalars(select(ResearchRunEvent).where(ResearchRunEvent.run_id == run.id,
            ResearchRunEvent.cursor > after).order_by(ResearchRunEvent.cursor).limit(data["limit"])).all()
        events = [{"cursor": row.cursor, "run_id": str(run.id), "elapsed_ms": row.elapsed_ms,
                   "kind": row.kind, "summary": json.loads(row.summary_json)} for row in rows]
        next_cursor = rows[-1].cursor if rows else after
        return {"version": VERSION, "run_id": str(run.id), "binding": self._binding(run),
                "after_cursor": after, "next_cursor": next_cursor, "latest_event_cursor": run.event_cursor,
                "has_more": next_cursor < run.event_cursor, "events": events}

    def _settle(self, session, run, budget=None, *, recovering=False):
        now = self._now(session)
        invalid_clock = ((run.updated_at is not None and now < _utc(run.updated_at))
                         or (run.active_started_at is not None and now < _utc(run.active_started_at)))
        if invalid_clock:
            run.active_elapsed_ms = max(run.active_elapsed_ms, 180000)
            run.reason_code = "invalid_clock"
        if run.active_started_at is not None:
            # Lease expiry fences publication; it does not prove an old RPC
            # stopped. Charge the complete unresolved interval conservatively.
            end = now
            delta = max(0, int((end - _utc(run.active_started_at)).total_seconds() * 1000))
            run.active_elapsed_ms = min(180000, run.active_elapsed_ms + delta)
            run.active_started_at = now
        if budget is not None:
            parsed = BudgetSnapshot.model_validate(budget)
            run.active_elapsed_ms = min(180000, max(run.active_elapsed_ms, int(parsed.active_elapsed_seconds * 1000)))
            for key in ("tool_actions", "model_calls", "malformed_repairs"):
                value = getattr(parsed, key)
                if value < getattr(run, key):
                    raise ResearchRunError("conflict", 409)
                setattr(run, key, value)
        run.updated_at = max(now, _utc(run.updated_at)) if run.updated_at is not None else now
        return now

    @staticmethod
    def _budget(run):
        return {"active_elapsed_seconds": run.active_elapsed_ms / 1000,
                "tool_actions": run.tool_actions, "model_calls": run.model_calls,
                "malformed_repairs": run.malformed_repairs,
                "cancellation_requested": run.cancellation_requested}

    def fresh_owner(self, run_id):
        with self._transaction() as session:
            found = session.get(ResearchRun, uuid.UUID(str(run_id)))
            if found is None:
                raise ResearchRunError("not_found", 404)
            return self._principal(session, owner_id=found.user_id)

    def claim(self, run_id, delivery_id):
        # A delivery contains only identity; it never supplies an owner principal.
        uuid.UUID(str(delivery_id))
        with self._transaction() as session:
            found = session.get(ResearchRun, uuid.UUID(str(run_id)))
            if found is None:
                raise ResearchRunError("not_found", 404)
            actor = self._principal(session, owner_id=found.user_id)
            run = session.scalar(select(ResearchRun).where(ResearchRun.id == found.id).with_for_update().execution_options(populate_existing=True))
            self._check_context(run, actor, session=session)
            delivery = session.scalar(select(ResearchRunOutbox).where(
                ResearchRunOutbox.run_id == run.id, ResearchRunOutbox.delivery_id == uuid.UUID(str(delivery_id))))
            if delivery is None:
                raise ResearchRunError("not_found", 404)
            if delivery.input_version != run.input_version:
                return None
            if run.status in TERMINAL or run.status in {"awaiting_clarification", "awaiting_approval"}:
                return None
            self._dispatch_required()
            now = self._now(session)
            if now < _utc(run.updated_at) or (run.active_started_at is not None and now < _utc(run.active_started_at)):
                self._settle(session, run)
                run.status, run.reason_code = "partial", "invalid_clock"
                run.lease_epoch += 1
                run.lease_until = run.active_started_at = None
                run.version += 1
                self._event(session, run, "partial")
                return None
            if run.lease_until is not None and _utc(run.lease_until) > now:
                return None
            self._check_context(run, actor, require_active=True, session=session)
            self._settle(session, run, recovering=True)
            run.lease_epoch += 1
            run.lease_until = now + timedelta(seconds=self.lease_seconds)
            run.active_started_at, run.status = now, "running"
            run.version += 1
            # Recovery is internal; it must not duplicate the started event.
            if not session.scalar(select(ResearchRunEvent.cursor).where(ResearchRunEvent.run_id == run.id, ResearchRunEvent.kind == "started").limit(1)):
                self._event(session, run, "started")
            return RunLease(str(run.id), run.lease_epoch, run.input_version)

    def _leased(self, session, lease, *, check_time=True):
        found = session.get(ResearchRun, uuid.UUID(lease.run_id))
        if found is None:
            raise ResearchRunError("not_found", 404)
        actor = self._principal(session, owner_id=found.user_id)
        run = session.scalar(select(ResearchRun).where(ResearchRun.id == found.id).with_for_update().execution_options(populate_existing=True))
        if (run.lease_epoch != lease.epoch or run.input_version != lease.input_version
                or run.status != "running" or run.cancellation_requested
                or (check_time and (run.lease_until is None or _utc(run.lease_until) <= self._now(session)))):
            raise ResearchRunError("lease_lost", 409)
        self._check_context(run, actor, require_active=True, session=session)
        return run

    def execute_delivery(self, run_id, delivery_id):
        lease = self.claim(run_id, delivery_id)
        if lease is None:
            with self._transaction() as session:
                run = session.get(ResearchRun, uuid.UUID(str(run_id)))
                actor = self._principal(session, owner_id=run.user_id)
                self._check_context(run, actor, session=session)
                return self._envelope(run)
        with self._transaction() as session:
            run = self._leased(session, lease)
            request = {**{key: str(getattr(run, key)) for key in ("investigation_id", "conversation_id", "revision_id")}, "question": run.effective_question}
            budget = self._budget(run)
        controller = self.controller_factory(lambda: self.fresh_owner(run_id))
        from orchestration.research_controller import ResearchController
        if (not isinstance(controller, ResearchController)
                or controller.investigations is not self.investigations
                or controller.catalogue is not self.investigations.catalogue):
            raise ResearchRunError()
        try:
            result = controller.execute(request, journal=RunJournal(self, lease),
                restored_budget=BudgetSnapshot.model_validate(budget), cancelled=lambda: self._cancelled(lease))
        except Exception:
            # A failed callback/provider or lost lease cannot invent success.
            # Keep the lease/checkpoint for explicit redelivery after expiry.
            raise
        result = ControllerResult.model_validate(result)
        with self._transaction() as session:
            run = self._leased(session, lease)
            self._settle(session, run, result.budget.model_dump(mode="json"))
            if result.binding.model_dump(mode="json") != self._binding(run):
                raise ResearchRunError("conflict", 409)
            outcome = result.outcome
            run.status = {"clarification": "awaiting_clarification", "unavailable": "failed"}.get(outcome, outcome)
            if (run.active_elapsed_ms >= 180000 or run.reason_code == "invalid_clock") and run.status == "completed":
                run.status = "partial"
            run.controller_result_json = _json(result.model_dump(mode="json"))
            run.reason_code = run.reason_code or result.reason
            run.clarification_id = uuid.uuid4() if run.status == "awaiting_clarification" else None
            run.lease_until = run.active_started_at = None
            run.version += 1
            self._event(session, run, "clarification" if run.status == "awaiting_clarification" else run.status)
            session.flush()
            self._check_context(run, self._principal(session, owner_id=run.user_id), require_active=True, session=session)
            return self._envelope(run)

    def _cancelled(self, lease):
        with self._transaction() as session:
            run = session.get(ResearchRun, uuid.UUID(lease.run_id))
            return run is None or run.cancellation_requested or run.lease_epoch != lease.epoch

    def dispatch_outbox(self, queue=None):
        self._dispatch_required()
        target = queue if queue is not None else self.queue
        with self._transaction() as session:
            ids = list(session.scalars(select(ResearchRunOutbox.id).where(ResearchRunOutbox.state == "pending").order_by(ResearchRunOutbox.created_at, ResearchRunOutbox.id)))
        count = 0
        for identity in ids:
            self._dispatch_required()
            with self._transaction() as session:
                row = session.get(ResearchRunOutbox, identity)
                if row.state != "pending":
                    continue
                run = session.get(ResearchRun, row.run_id)
                if run.status not in {"queued", "running"} or run.input_version != row.input_version:
                    continue
                try:
                    actor = self._principal(session, owner_id=run.user_id)
                    self._check_context(run, actor, require_active=True, session=session)
                except ResearchRunError:
                    continue
                run_id, delivery_id = str(row.run_id), str(row.delivery_id)
                row.attempts += 1
            target.enqueue(run_id=run_id, delivery_id=delivery_id)
            with self._transaction() as session:
                row = session.get(ResearchRunOutbox, identity)
                row.state, row.sent_at = "sent", self._now(session)
            count += 1
        return count


class RunJournal:
    def __init__(self, service, lease):
        self.service, self.lease = service, lease

    def _key(self, step_id):
        if not isinstance(step_id, str) or not 0 < len(step_id) <= 220:
            raise ResearchRunError("invalid_request", 422)
        return f"input:{self.lease.input_version}:{step_id}"

    def bind(self, manifest):
        service = self.service
        with service._transaction() as session:
            run = service._leased(session, self.lease)
            old = session.get(ResearchRunManifest, (run.id, self.lease.input_version))
            if old is None:
                session.add(ResearchRunManifest(run_id=run.id, input_version=self.lease.input_version,
                    manifest_json=_json(manifest), manifest_sha256=_hash(manifest)))
            elif old.manifest_sha256 != _hash(manifest) or old.manifest_json != _json(manifest):
                raise ResearchRunError("replay_integrity", 409)
            service._settle(session, run)
            checkpoint = json.loads(run.checkpoint_json)
            if run.reason_code == "invalid_clock":
                checkpoint["clock_invalid"] = True
            prefix = f"input:{self.lease.input_version}:"
            repair_steps = session.scalars(select(ResearchRunStep.step_id).where(
                ResearchRunStep.run_id == run.id, ResearchRunStep.kind == "repair",
                ResearchRunStep.step_id.startswith(prefix))).all()
            return {"budget": service._budget(run), "reserved_repair_steps": [key[len(prefix):] for key in repair_steps], **{key: checkpoint[key] for key in (
                "clock_invalid", "actor_binding", "catalogue_policy_revision",
            ) if key in checkpoint}}

    def lookup_step(self, step_id, request_sha256):
        service = self.service
        with service._transaction() as session:
            run = service._leased(session, self.lease)
            step = session.get(ResearchRunStep, (run.id, self._key(step_id)))
            if step is None and run.continuation_of and step_id.startswith(("pin:", "inventory:")):
                parent = session.get(ResearchRun, run.continuation_of)
                current_manifest = session.get(ResearchRunManifest, (run.id, run.input_version))
                parent_manifest = session.get(ResearchRunManifest, (parent.id, parent.input_version))
                if current_manifest and parent_manifest and current_manifest.manifest_json == parent_manifest.manifest_json:
                    prior = session.get(ResearchRunStep, (parent.id, f"input:{parent.input_version}:{step_id}"))
                    if prior and prior.kind == "tool" and prior.state == "committed" and prior.request_sha256 == request_sha256:
                        payload = session.get(ResearchRunPayload, (parent.id, prior.outcome_sha256))
                        if payload is None or hashlib.sha256(payload.payload_json.encode("utf-8")).hexdigest() != prior.outcome_sha256:
                            raise ResearchRunError("replay_integrity", 409)
                        if session.get(ResearchRunPayload, (run.id, payload.sha256)) is None:
                            session.add(ResearchRunPayload(run_id=run.id, sha256=payload.sha256, payload_json=payload.payload_json))
                            session.flush()
                        step = ResearchRunStep(run_id=run.id, step_id=self._key(step_id), kind="tool",
                            request_sha256=prior.request_sha256, request_json=prior.request_json,
                            outcome_sha256=payload.sha256, state="committed")
                        session.add(step)
                        session.flush()
            if step is None:
                return None
            if step.request_sha256 != request_sha256:
                raise ResearchRunError("replay_integrity", 409)
            if step.state != "committed":
                return None
            payload = session.get(ResearchRunPayload, (run.id, step.outcome_sha256))
            if payload is None or hashlib.sha256(payload.payload_json.encode("utf-8")).hexdigest() != payload.sha256:
                raise ResearchRunError("replay_integrity", 409)
            return {"outcome": json.loads(payload.payload_json), "outcome_sha256": payload.sha256}

    def prepare_step(self, step_id, kind, request_sha256, request, budget, checkpoint):
        service = self.service
        with service._transaction() as session:
            run = service._leased(session, self.lease)
            key = self._key(step_id)
            step = session.get(ResearchRunStep, (run.id, key))
            existing_repair = kind == "repair" and step is not None
            if request_sha256 != _hash(request) or kind not in {"tool", "model", "repair"}:
                raise ResearchRunError("replay_integrity", 409)
            if step is None:
                step = ResearchRunStep(run_id=run.id, step_id=key, kind=kind,
                    request_sha256=request_sha256, request_json=_json(request), state="prepared")
                session.add(step)
                session.flush()
            elif step.request_sha256 != request_sha256 or step.request_json != _json(request) or step.kind != kind or step.state == "committed":
                raise ResearchRunError("replay_integrity", 409)
            previous = service._budget(run)
            manifest = session.get(ResearchRunManifest, (run.id, run.input_version))
            limits = ControllerLimits.model_validate(json.loads(manifest.manifest_json).get("limits", {}) if manifest else {})
            caps = {"tool_actions": limits.tool_actions, "model_calls": limits.tool_actions + limits.malformed_repairs + 1,
                    "malformed_repairs": limits.malformed_repairs}
            if any(budget.get(name, 0) > maximum for name, maximum in caps.items()):
                raise ResearchRunError("budget_exhausted", 409)
            now = service._settle(session, run, budget)
            counter = {"tool": "tool_actions", "model": "model_calls", "repair": "malformed_repairs"}[kind]
            if getattr(run, counter) != previous[counter] + (0 if existing_repair else 1) or run.active_elapsed_ms >= limits.active_seconds * 1000:
                raise ResearchRunError("budget_exhausted", 409)
            if any(getattr(run, name) != previous[name] for name in ("tool_actions", "model_calls", "malformed_repairs") if name != counter):
                raise ResearchRunError("replay_integrity", 409)
            run.checkpoint_json = _json(checkpoint)
            run.lease_until = now + timedelta(seconds=min(service.lease_seconds, max(0.001, limits.active_seconds - run.active_elapsed_ms / 1000)))
            ordinal = (session.scalar(select(func.max(ResearchRunAttempt.ordinal)).where(
                ResearchRunAttempt.run_id == run.id, ResearchRunAttempt.step_id == key)) or 0) + 1
            token = uuid.uuid4()
            session.add(ResearchRunAttempt(id=token, run_id=run.id, step_id=key, ordinal=ordinal,
                lease_epoch=self.lease.epoch, budget_json=_json(service._budget(run))))
            return str(token)

    def commit_step(self, token, outcome, budget, checkpoint):
        service = self.service
        with service._transaction() as session:
            run = service._leased(session, self.lease)
            attempt = session.get(ResearchRunAttempt, uuid.UUID(str(token)))
            if attempt is None or attempt.run_id != run.id or attempt.lease_epoch != self.lease.epoch:
                raise ResearchRunError("lease_lost", 409)
            step = session.get(ResearchRunStep, (run.id, attempt.step_id))
            if step.state != "prepared":
                raise ResearchRunError("replay_integrity", 409)
            parsed_budget = BudgetSnapshot.model_validate(budget)
            reservation = json.loads(attempt.budget_json)
            if any(getattr(parsed_budget, key) != getattr(run, key) or reservation[key] != getattr(run, key)
                   for key in ("tool_actions", "model_calls", "malformed_repairs")):
                raise ResearchRunError("replay_integrity", 409)
            service._settle(session, run, budget)
            value, digest = _json(outcome), _hash(outcome)
            payload = session.get(ResearchRunPayload, (run.id, digest))
            if payload is None:
                session.add(ResearchRunPayload(run_id=run.id, sha256=digest, payload_json=value))
                session.flush()
            elif payload.payload_json != value:
                raise ResearchRunError("replay_integrity", 409)
            step.state, step.outcome_sha256 = "committed", digest
            run.checkpoint_json = _json(checkpoint)
            run.version += 1
            service._event(session, run, "progress")
