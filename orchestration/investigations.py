"""C17 private application context with conservative cross-store coordination.

No ambient database, legacy history, model or scientific-source acquisition is
available here. A host supplies an independent application session factory and
explicit registered frozen snapshots. Prepared operations survive interrupted
reference writes; failed/uncertain operations never compensate by releasing data.
"""
from __future__ import annotations

from contextlib import contextmanager, nullcontext
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import json
from typing import Callable
import uuid

from pydantic import ValidationError
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm.exc import StaleDataError

import config
from api.auth import CurrentUser, permissions_for_role
from db.app_models import (
    AppUser, AuditEvent, ResearchContextOperation, ResearchContextRevision,
    ResearchConversation, ResearchInvestigation,
)
from ingestion.catalogue_snapshot import SnapshotCommitUncertain
from orchestration.catalogue_registration import ScientificCatalogueRegistration
from orchestration.catalogue_service import CatalogueService, CatalogueServiceError
from schema.context_catalogue import canonical_json
from schema.investigations import (
    ContextReference, INVESTIGATION_REQUEST_MODELS, MAX_CONTEXT_REFERENCES,
    finite_utf8_json,
)


class InvestigationError(Exception):
    def __init__(self, status_code: int, code: str, message: str):
        super().__init__(message)
        self.status_code, self.code, self.message = status_code, code, message


def _error(code, operation_id=None):
    status, message = {
        "unauthorized": (401, "Authentication is required"),
        "forbidden": (403, "Investigation access is restricted"),
        "not_found": (404, "Investigation content is unavailable"),
        "conflict": (409, "Investigation version has changed"),
        "unresolved_context": (409, "Resolve unavailable context before submission"),
        "invalid_request": (422, "Investigation request is invalid"),
        "unavailable": (503, "Investigation service is unavailable"),
        "operation_pending": (503, "Investigation operation requires reconciliation"),
    }[code]
    if operation_id is not None:
        message += f" ({operation_id})"
    return InvestigationError(status, code, message)


def _json(value):
    finite_utf8_json(value)
    text = canonical_json(value)
    if len(text.encode("utf-8")) > 512 * 1024:
        raise _error("invalid_request")
    return text


def _hash(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _key(reference):
    return _hash(_json(reference))


def _stamp(value):
    return value.isoformat() if value is not None else None


@dataclass(frozen=True)
class RetainedArtifactBinding:
    """A trusted retained-artifact adapter supplies a current immutable binding."""

    id: str
    snapshot_id: str
    sha256: str
    owner_user_id: uuid.UUID


class InvestigationService:
    def __init__(
        self, *, session_factory: Callable, site_id: str,
        catalogue_service: CatalogueService, snapshot_store,
        registrations: dict[str, ScientificCatalogueRegistration],
        artifact_resolver: Callable | None = None,
        evidence_protection=None,
    ):
        if not callable(session_factory) or not isinstance(site_id, str) or not site_id.startswith("v1:") or not 3 < len(site_id) <= 128:
            raise ValueError("Explicit independent v1 application binding required")
        if not isinstance(catalogue_service, CatalogueService):
            raise ValueError("Explicit catalogue service required")
        if not all(callable(getattr(snapshot_store, name, None)) for name in ("add_reference", "read", "lifecycle")):
            raise ValueError("Explicit retained snapshot store required")
        if not registrations or len(registrations) > 128 or any(
            not isinstance(item, ScientificCatalogueRegistration) or identity != item.snapshot_id
            for identity, item in registrations.items()
        ):
            raise ValueError("Explicit scientific snapshot registrations required")
        if artifact_resolver is not None and not callable(artifact_resolver):
            raise ValueError("Artifact resolver must be a trusted callable")
        if evidence_protection is not None and not all(callable(getattr(evidence_protection, name, None)) for name in ("prepare_context", "activate_context")):
            raise ValueError("Evidence protection must implement same-session context hooks")
        self.session_factory, self.site_id = session_factory, site_id
        self.catalogue, self.store = catalogue_service, snapshot_store
        self.registrations, self.artifact_resolver = dict(registrations), artifact_resolver
        self.evidence_protection = evidence_protection

    @contextmanager
    def _transaction(self):
        # Creation, transaction release and closure all occur inside one worker.
        with self.session_factory() as session:
            with session.begin():
                yield session

    @staticmethod
    def _actor(session, user):
        if not isinstance(user, CurrentUser) or user.status != "active":
            raise _error("unauthorized")
        if "data:read" not in user.permissions:
            raise _error("forbidden")
        if not config.v1_investigations_enabled():
            raise _error("unavailable")
        current = session.get(AppUser, user.id)
        if current is None or current.status != "active" or "data:read" not in permissions_for_role(current.role):
            raise _error("forbidden")
        if current.role != user.role or current.auth_provider != user.auth_provider or current.email != user.email or current.account_type != user.account_type or user.permissions != permissions_for_role(current.role):
            raise _error("forbidden")

    @staticmethod
    def _owned(session, identity, user, *, lock=False, preparing=False):
        statement = select(ResearchInvestigation).where(
            ResearchInvestigation.id == uuid.UUID(str(identity)),
            ResearchInvestigation.user_id == user.id,
        )
        if lock:
            statement = statement.with_for_update()
        item = session.scalar(statement)
        if item is None or item.status == "retired" or (item.status == "preparing" and not preparing):
            raise _error("not_found")
        return item

    @staticmethod
    def _revision(session, investigation, identity=None):
        identity = identity or investigation.head_revision_id
        item = session.scalar(select(ResearchContextRevision).where(
            ResearchContextRevision.id == identity,
            ResearchContextRevision.investigation_id == investigation.id,
        )) if identity is not None else None
        if item is None:
            raise _error("not_found")
        if _hash(item.payload_json) != item.payload_sha256:
            raise _error("unavailable")
        payload = json.loads(item.payload_json)
        if payload.get("snapshot_id") != item.snapshot_id:
            raise _error("unavailable")
        return item, payload

    @staticmethod
    def _metadata(item):
        return {
            "id": str(item.id), "name": item.name, "metadata_version": item.metadata_version,
            "status": item.status, "head_revision_id": str(item.head_revision_id) if item.head_revision_id else None,
            "predecessor_investigation_id": str(item.predecessor_investigation_id) if item.predecessor_investigation_id else None,
            "predecessor_revision_id": str(item.predecessor_revision_id) if item.predecessor_revision_id else None,
            "legal_hold": item.legal_hold, "created_at": _stamp(item.created_at),
            "updated_at": _stamp(item.updated_at),
        }

    @staticmethod
    def _conversation(item):
        return {
            "id": str(item.id), "investigation_id": str(item.investigation_id), "name": item.name,
            "metadata_version": item.metadata_version, "created_at": _stamp(item.created_at),
            "updated_at": _stamp(item.updated_at), "history_status": "unavailable_until_c20_c21",
        }

    @staticmethod
    def _operation(item):
        return {
            "id": str(item.id), "investigation_id": str(item.investigation_id),
            "kind": item.kind, "state": item.state, "error_code": item.error_code,
            "candidate_revision_id": str(item.candidate_revision_id) if item.candidate_revision_id else None,
        }

    @staticmethod
    def _audit(session, user, action, target, metadata):
        session.add(AuditEvent(
            actor_user_id=user.id, action="research." + action,
            target_type="research_investigation", target_id=str(target), metadata_json=metadata,
        ))

    def _snapshot(self, snapshot_id, scope, user):
        registration = self.registrations.get(snapshot_id)
        if registration is None:
            raise _error("unavailable")
        try:
            registration.require_current(self.store)
            self.catalogue.overview({"snapshot_id": snapshot_id, "scope": scope}, user)
        except CatalogueServiceError as exc:
            raise _error("not_found" if exc.status_code == 404 else "unavailable") from None
        except Exception:
            raise _error("unavailable") from None
        return registration

    def _bindings(self, snapshot_id, investigation_id):
        registration = self.registrations.get(snapshot_id)
        if registration is None:
            raise _error("unavailable")
        # Same-snapshot revisions share these independent retention references.
        # Every immutable operation still retains its complete dependency set.
        return [{"snapshot_id": identity, "reference": "c17:dependency:" + _hash(_json([
            self.site_id, str(investigation_id), snapshot_id, identity,
        ]))} for identity in (snapshot_id, *registration.child_snapshot_ids)]

    def _artifact_actor(self, session, user):
        authorize = getattr(self.artifact_resolver, "authorize_in_session", None)
        if callable(authorize):
            authorize(session, user)

    def _resolve(self, payload, user, session=None):
        self._snapshot(payload["snapshot_id"], payload["scope"], user)
        artifact_keys = {_key(reference) for reference in [*payload["attachments"], *payload["pins"]] if reference["kind"] == "artifact"}
        resolution, artifact_bindings = [], {key: value for key, value in payload.get("artifact_bindings", {}).items() if key in artifact_keys}
        for reference in [*payload["attachments"], *payload["pins"]]:
            reference = ContextReference.model_validate(reference).model_dump(mode="json")
            status = "available"
            if reference["kind"] == "catalogue":
                if reference["snapshot_id"] != payload["snapshot_id"]:
                    raise _error("unavailable")
                try:
                    self.catalogue.open({
                        "snapshot_id": reference["snapshot_id"], "scope": payload["scope"],
                        "object_id": reference["id"],
                    }, user)
                except CatalogueServiceError as exc:
                    if exc.status_code in (403, 404):
                        status = "unavailable"
                    else:
                        raise _error("unavailable") from None
            elif self.artifact_resolver is None:
                status = "artifact_capability_unavailable"
            else:
                try:
                    in_session = getattr(self.artifact_resolver, "resolve_in_session", None)
                    binding = in_session(session, user, dict(reference)) if session is not None and callable(in_session) else self.artifact_resolver(user, dict(reference))
                except PermissionError:
                    binding = None
                except Exception:
                    raise _error("unavailable") from None
                if binding is None:
                    status = "unavailable"
                elif not isinstance(binding, RetainedArtifactBinding) or binding.owner_user_id != user.id or binding.id != reference["id"] or binding.snapshot_id != reference["snapshot_id"] or len(binding.sha256) != 64 or any(c not in "0123456789abcdef" for c in binding.sha256):
                    raise _error("unavailable")
                else:
                    key = _key(reference)
                    previous = artifact_bindings.setdefault(key, binding.sha256)
                    if previous != binding.sha256:
                        raise _error("unavailable")
            resolution.append({"reference": reference, "status": status})
        return resolution, artifact_bindings

    def _context(self, revision, payload, user, session=None):
        resolution, _ = self._resolve(payload, user, session)
        return {
            "id": str(revision.id), "investigation_id": str(revision.investigation_id),
            "sequence": revision.sequence, "predecessor_revision_id": str(revision.predecessor_revision_id) if revision.predecessor_revision_id else None,
            "snapshot_id": revision.snapshot_id, "payload_sha256": revision.payload_sha256,
            "scope": payload["scope"], "attachments": payload["attachments"], "pins": payload["pins"],
            "resolution": resolution, "refresh_unresolved": payload.get("refresh_unresolved", []),
            "created_by_user_id": str(revision.created_by_user_id), "created_at": _stamp(revision.created_at),
            "artifact_capability": "configured" if self.artifact_resolver else "unavailable",
        }

    def invoke(self, name, payload, user):
        if not isinstance(user, CurrentUser) or user.status != "active":
            raise _error("unauthorized")
        if "data:read" not in user.permissions:
            raise _error("forbidden")
        if not config.v1_investigations_enabled():
            raise _error("unavailable")
        try:
            model = INVESTIGATION_REQUEST_MODELS.get(name)
            if model is None:
                raise _error("invalid_request")
            data = model.model_validate(payload).model_dump(mode="json", exclude_none=True)
            _json(data)
            if name in ("create", "context/change", "refresh"):
                result = self._apply(self._prepare(name, data, user), user)
            elif name == "operations/retry":
                result = self._apply(uuid.UUID(data["operation_id"]), user)
            elif name in ("rename", "archive", "conversations/create", "conversations/rename"):
                result = self._metadata_change(name, data, user)
            else:
                result = self._read(name, data, user)
            return {"version": "investigations-v1", **result}
        except InvestigationError:
            raise
        except (ValidationError, ValueError, TypeError, UnicodeError):
            raise _error("invalid_request") from None
        except (IntegrityError, StaleDataError):
            raise _error("conflict") from None
        except SQLAlchemyError:
            raise _error("operation_pending") from None

    def _read(self, name, data, user, session=None):
        with self._transaction() if session is None else nullcontext(session) as session:
            self._actor(session, user)
            if name == "operations/get":
                op = session.scalar(select(ResearchContextOperation).where(
                    ResearchContextOperation.id == uuid.UUID(data["operation_id"]),
                    ResearchContextOperation.user_id == user.id,
                ))
                if op is None:
                    raise _error("not_found")
                return {"operation": self._operation(op)}
            if name == "list":
                query = select(ResearchInvestigation).where(
                    ResearchInvestigation.user_id == user.id,
                    ResearchInvestigation.status.in_(("active", "archived")),
                )
                if data.get("after_id"):
                    query = query.where(ResearchInvestigation.id > uuid.UUID(data["after_id"]))
                items = list(session.scalars(query.order_by(ResearchInvestigation.id).limit(data["limit"] + 1)))
                page = items[:data["limit"]]
                return {"items": [self._metadata(item) for item in page], "next_after_id": str(page[-1].id) if len(items) > len(page) else None}
            item = self._owned(session, data["investigation_id"], user)
            revision, context = self._revision(session, item, uuid.UUID(data["revision_id"]) if data.get("revision_id") else None)
            if name == "context/get":
                return {"context": self._context(revision, context, user, session)}
            self._snapshot(revision.snapshot_id, context["scope"], user)
            if name == "get":
                return {"investigation": self._metadata(item), "context": self._context(revision, context, user, session), "legacy_history_import": "unavailable"}
            query = select(ResearchConversation).where(ResearchConversation.investigation_id == item.id)
            if name == "conversations/get":
                conversation = session.scalar(query.where(ResearchConversation.id == uuid.UUID(data["conversation_id"])))
                if conversation is None:
                    raise _error("not_found")
                return {"conversation": self._conversation(conversation)}
            if name == "conversations/list":
                if data.get("after_id"):
                    query = query.where(ResearchConversation.id > uuid.UUID(data["after_id"]))
                items = list(session.scalars(query.order_by(ResearchConversation.id).limit(data["limit"] + 1)))
                page = items[:data["limit"]]
                return {"items": [self._conversation(entry) for entry in page], "next_after_id": str(page[-1].id) if len(items) > len(page) else None}
            raise _error("invalid_request")

    @staticmethod
    def _existing_operation(session, user, data, name):
        text = _json({"operation": name, "request": data})
        existing = session.scalar(select(ResearchContextOperation).where(
            ResearchContextOperation.user_id == user.id,
            ResearchContextOperation.idempotency_key == data["idempotency_key"],
        ))
        if existing is not None and (existing.request_sha256 != _hash(text) or existing.request_json != text):
            raise _error("conflict")
        return existing, text

    def _prepare(self, name, data, user):
        with self._transaction() as session:
            self._actor(session, user)
            self._artifact_actor(session, user)
            # Preparation and retirement share one lock before investigation
            # locks. Session-aware artifact providers reuse this transaction.
            self._retention_lock(session)
            existing, request = self._existing_operation(session, user, data, name)
            if existing is not None:
                return existing.id
            predecessor = None
            if name == "create":
                item = ResearchInvestigation(id=uuid.uuid4(), user_id=user.id, name=data["name"], status="preparing")
                candidate = {"snapshot_id": data["snapshot_id"], "scope": data["scope"], "attachments": [], "pins": [], "artifact_bindings": {}}
                expected = None
            else:
                original = self._owned(session, data["investigation_id"], user, lock=True)
                if str(original.head_revision_id) != data["expected_revision_id"]:
                    raise _error("conflict")
                previous, candidate = self._revision(session, original)
                candidate = json.loads(_json(candidate))
                if name == "refresh":
                    item = ResearchInvestigation(
                        id=uuid.uuid4(), user_id=user.id, name=data["name"], status="preparing",
                        predecessor_investigation_id=original.id, predecessor_revision_id=previous.id,
                    )
                    candidate["snapshot_id"] = data["target_snapshot_id"]
                    for reference in [*candidate["attachments"], *candidate["pins"]]:
                        if reference["kind"] == "catalogue":
                            reference["snapshot_id"] = data["target_snapshot_id"]
                    expected = None
                    predecessor = previous.id
                else:
                    if original.status != "active":
                        raise _error("conflict")
                    item, expected = original, previous.id
                    change = data["change"]
                    if change["op"] == "scope":
                        candidate["scope"] = change["scope"]
                    else:
                        field = "attachments" if change["op"] in ("attach", "detach") else "pins"
                        reference = change["reference"]
                        if reference["kind"] == "catalogue" and reference["snapshot_id"] != candidate["snapshot_id"]:
                            raise _error("invalid_request")
                        entries = {_key(entry): entry for entry in candidate[field]}
                        if change["op"] in ("attach", "pin"):
                            entries[_key(reference)] = reference
                        else:
                            entries.pop(_key(reference), None)
                        candidate[field] = [entries[key] for key in sorted(entries)]
                    if any(len(candidate[field]) > MAX_CONTEXT_REFERENCES for field in ("attachments", "pins")):
                        raise _error("invalid_request")
            resolution, artifacts = self._resolve(candidate, user, session)
            if name == "context/change" and data["change"]["op"] in ("attach", "pin"):
                added = data["change"]["reference"]
                unresolved = next(entry for entry in resolution if entry["reference"] == added)
                if unresolved["status"] != "available":
                    raise _error("unavailable" if added["kind"] == "artifact" else "not_found")
            candidate["artifact_bindings"] = artifacts
            if name == "refresh":
                candidate["refresh_unresolved"] = [entry for entry in resolution if entry["status"] != "available"]
                candidate["refresh_from_revision_id"] = str(predecessor)
            session.add(item)
            session.flush()
            operation = ResearchContextOperation(
                id=uuid.uuid4(), user_id=user.id, investigation_id=item.id,
                idempotency_key=data["idempotency_key"], kind=name,
                expected_head_id=expected, candidate_revision_id=uuid.uuid4(),
                request_json=request, request_sha256=_hash(request), candidate_json=_json(candidate),
                references_json=_json(self._bindings(candidate["snapshot_id"], item.id)), state="prepared",
            )
            session.add(operation)
            session.flush()
            if self.evidence_protection is not None:
                self.evidence_protection.prepare_context(session, operation, candidate, user)
            self._audit(session, user, "context_prepared", item.id, {"operation_id": str(operation.id)})
            return operation.id

    def _mark_pending(self, identity, user, state):
        # Failure here is itself ambiguous. It cannot release a reference.
        try:
            with self._transaction() as session:
                self._actor(session, user)
                self._artifact_actor(session, user)
                self._retention_lock(session)
                op = session.scalar(select(ResearchContextOperation).where(
                    ResearchContextOperation.id == identity,
                    ResearchContextOperation.user_id == user.id,
                ).with_for_update())
                if op is not None and op.state not in ("committed", "conflict"):
                    op.state, op.error_code = state, "reference_registration_pending"
        except Exception:
            pass

    def _apply(self, identity, user):
        with self._transaction() as session:
            self._actor(session, user)
            op = session.scalar(select(ResearchContextOperation).where(
                ResearchContextOperation.id == identity, ResearchContextOperation.user_id == user.id,
            ))
            if op is None:
                raise _error("not_found")
            if op.state == "conflict":
                raise _error("conflict")
            if op.candidate_revision_id is None:
                return {"operation": self._operation(op)}
            candidate = json.loads(op.candidate_json)
            references = json.loads(op.references_json)
            if references != self._bindings(candidate["snapshot_id"], op.investigation_id):
                raise _error("unavailable")
            self._resolve(candidate, user, session)
        try:
            for binding in references:
                self.store.add_reference(binding["snapshot_id"], binding["reference"])
        except Exception as exc:
            self._mark_pending(identity, user, "uncertain" if isinstance(exc, SnapshotCommitUncertain) else "unavailable")
            raise _error("operation_pending", identity) from None
        conflict = False
        try:
            with self._transaction() as session:
                self._actor(session, user)
                self._artifact_actor(session, user)
                self._retention_lock(session)
                op = session.scalar(select(ResearchContextOperation).where(
                    ResearchContextOperation.id == identity, ResearchContextOperation.user_id == user.id,
                ).with_for_update())
                if op is None:
                    raise _error("not_found")
                item = self._owned(session, op.investigation_id, user, lock=True, preparing=True)
                existing = session.get(ResearchContextRevision, op.candidate_revision_id)
                if existing is not None:
                    if existing.investigation_id != item.id or existing.payload_json != op.candidate_json:
                        raise _error("unavailable")
                    if op.state != "committed":
                        raise _error("unavailable")
                    existing, persisted = self._revision(session, item, op.candidate_revision_id)
                    return {"operation": self._operation(op), "investigation": self._metadata(item), "context": self._context(existing, persisted, user, session)}
                if item.head_revision_id != op.expected_head_id or op.state == "conflict" or (op.kind == "context/change" and item.status != "active"):
                    op.state, op.error_code, conflict = "conflict", "stale_context_head", True
                    self._audit(session, user, "context_conflict", item.id, {"operation_id": str(op.id)})
                else:
                    self._resolve(candidate, user, session)
                    lifecycle = self.store.lifecycle()
                    for binding in references:
                        entry = lifecycle["snapshots"].get(binding["snapshot_id"])
                        if lifecycle["references"].get(binding["reference"]) != binding["snapshot_id"] or not entry or entry["revoked"] or entry["retired"]:
                            raise _error("operation_pending", identity)
                    previous = self._revision(session, item)[0] if item.head_revision_id else None
                    revision = ResearchContextRevision(
                        id=op.candidate_revision_id, investigation_id=item.id,
                        sequence=previous.sequence + 1 if previous else 1,
                        predecessor_revision_id=previous.id if previous else None,
                        snapshot_id=candidate["snapshot_id"], payload_json=op.candidate_json,
                        payload_sha256=_hash(op.candidate_json), created_by_user_id=user.id,
                    )
                    session.add(revision)
                    session.flush()
                    if self.evidence_protection is not None:
                        self.evidence_protection.activate_context(session, op, candidate, user)
                    item.head_revision_id = revision.id
                    if item.status == "preparing":
                        item.status = "active"
                    op.state, op.error_code = "committed", None
                    session.flush()
                    self._audit(session, user, "context_committed", item.id, {
                        "operation_id": str(op.id), "revision_id": str(revision.id),
                        "payload_sha256": revision.payload_sha256,
                    })
                    result = {"operation": self._operation(op), "investigation": self._metadata(item), "context": self._context(revision, candidate, user, session)}
        except InvestigationError:
            raise
        except SQLAlchemyError:
            # A failed COMMIT may already have committed. Retry inspects the exact
            # immutable candidate. No compensation removes any snapshot binding.
            raise _error("operation_pending", identity) from None
        if conflict:
            raise _error("conflict")
        return result

    def _metadata_change(self, name, data, user):
        with self._transaction() as session:
            self._actor(session, user)
            existing, request = self._existing_operation(session, user, data, name)
            if existing is not None:
                item = self._owned(session, existing.investigation_id, user)
                revision, context = self._revision(session, item)
                self._snapshot(revision.snapshot_id, context["scope"], user)
                if existing.state != "committed":
                    raise _error("operation_pending", existing.id)
                return {"operation": self._operation(existing), **json.loads(existing.candidate_json)}
            item = self._owned(session, data["investigation_id"], user, lock=True)
            revision, payload = self._revision(session, item)
            self._snapshot(revision.snapshot_id, payload["scope"], user)
            result = {}
            if name.startswith("conversations/"):
                if item.status != "active":
                    raise _error("conflict")
                if name == "conversations/create":
                    conversation = ResearchConversation(id=uuid.uuid4(), investigation_id=item.id, name=data["name"])
                    session.add(conversation)
                else:
                    conversation = session.scalar(select(ResearchConversation).where(
                        ResearchConversation.id == uuid.UUID(data["conversation_id"]),
                        ResearchConversation.investigation_id == item.id,
                    ).with_for_update())
                    if conversation is None:
                        raise _error("not_found")
                    if conversation.metadata_version != data["expected_version"]:
                        raise _error("conflict")
                    conversation.name = data["name"]
                item.updated_at = datetime.now(timezone.utc)
                session.flush()
                result["conversation"] = self._conversation(conversation)
            else:
                if item.metadata_version != data["expected_version"]:
                    raise _error("conflict")
                if name == "rename":
                    item.name = data["name"]
                else:
                    item.status = "archived" if data["archived"] else "active"
                session.flush()
                result["investigation"] = self._metadata(item)
            op = ResearchContextOperation(
                id=uuid.uuid4(), user_id=user.id, investigation_id=item.id,
                idempotency_key=data["idempotency_key"], kind=name, request_json=request,
                request_sha256=_hash(request), candidate_json=_json(result), references_json="[]", state="committed",
            )
            session.add(op)
            session.flush()
            self._audit(session, user, name.replace("/", "_"), item.id, {"operation_id": str(op.id)})
            return {"operation": self._operation(op), **result}

    def load_for_submission(self, *, investigation_id, conversation_id, revision_id, user, session=None):
        """Freeze one explicit revision; C20 owns requests/events/execution later."""
        with self._transaction() if session is None else nullcontext(session) as session:
            self._actor(session, user)
            item = self._owned(session, investigation_id, user)
            if item.status != "active":
                raise _error("conflict")
            conversation = session.scalar(select(ResearchConversation).where(
                ResearchConversation.id == uuid.UUID(str(conversation_id)), ResearchConversation.investigation_id == item.id,
            ))
            if conversation is None:
                raise _error("not_found")
            revision, payload = self._revision(session, item, uuid.UUID(str(revision_id)))
            resolution, _ = self._resolve(payload, user, session)
            if any(entry["status"] != "available" for entry in resolution):
                raise _error("unresolved_context")
            return {"investigation_id": str(item.id), "conversation_id": str(conversation.id),
                    "revision_id": str(revision.id), "snapshot_id": revision.snapshot_id,
                    "payload_sha256": revision.payload_sha256, "context": json.loads(revision.payload_json)}

    def set_hold(self, *, investigation_id, held: bool, user):
        """Trusted metadata-only operator; no private context/content is returned."""
        if type(held) is not bool or not isinstance(user, CurrentUser) or "retention:manage" not in user.permissions:
            raise _error("forbidden")
        with self._transaction() as session:
            self._actor(session, user)
            self._retention_lock(session)
            item = session.scalar(select(ResearchInvestigation).where(
                ResearchInvestigation.id == uuid.UUID(str(investigation_id)),
                ResearchInvestigation.status != "retired",
            ).with_for_update())
            if item is None:
                raise _error("not_found")
            item.legal_hold = held
            self._audit(session, user, "hold_changed", item.id, {"held": held})

    def retire_expired(self, *, retention_days: int, user, now=None, dry_run=True):
        """Metadata-only operator retirement; all retained bytes/references remain."""
        if type(retention_days) is not int or retention_days < 1 or type(dry_run) is not bool:
            raise _error("invalid_request")
        if not isinstance(user, CurrentUser) or "retention:manage" not in user.permissions:
            raise _error("forbidden")
        cutoff = (now or datetime.now(timezone.utc)) - timedelta(days=retention_days)
        with self._transaction() as session:
            self._actor(session, user)
            self._retention_lock(session)
            candidates = list(session.scalars(select(ResearchInvestigation).where(
                ResearchInvestigation.status == "archived",
                ResearchInvestigation.updated_at < cutoff, ResearchInvestigation.legal_hold.is_(False),
            ).order_by(ResearchInvestigation.id).with_for_update()))
            eligible = []
            for item in candidates:
                pending = session.scalar(select(ResearchContextOperation.id).where(
                    ResearchContextOperation.investigation_id == item.id,
                    ResearchContextOperation.state.in_(("prepared", "uncertain", "unavailable")),
                ).limit(1))
                descendants = session.scalar(select(ResearchInvestigation.id).where(
                    ResearchInvestigation.predecessor_investigation_id == item.id,
                    ResearchInvestigation.status != "retired",
                ).limit(1))
                # Retention applies independently of C21 feature flags and
                # runtime wiring. Prepared/uncertain evidence and queued answer
                # jobs remain dependencies even before publication.
                from db.app_models import (
                    ResearchAnswerJob, ResearchEvidenceContextDependency, ResearchEvidenceReceipt,
                    ResearchExperiment, ResearchExperimentOperation,
                )
                protected = any(session.scalar(select(model).where(model.investigation_id == item.id).limit(1)) is not None
                    for model in (ResearchAnswerJob, ResearchEvidenceContextDependency, ResearchEvidenceReceipt,
                                  ResearchExperiment, ResearchExperimentOperation))
                # Immutable historical context references retain foreign artifacts
                # independently of today's provider wiring or feature flags.
                for revision in session.scalars(select(ResearchContextRevision).where(
                        ResearchContextRevision.investigation_id == item.id)):
                    try:
                        payload = json.loads(revision.payload_json)
                        if _hash(revision.payload_json) != revision.payload_sha256 or any(
                                entry["kind"] == "artifact" for entry in [*payload["attachments"], *payload["pins"]]):
                            protected = True
                    except (ValueError, KeyError, TypeError):
                        protected = True
                if pending is None and descendants is None and not protected and not self._held_ancestor(session, item):
                    eligible.append(item)
            if not dry_run:
                for item in eligible:
                    item.status, item.retired_at = "retired", now or datetime.now(timezone.utc)
                    self._audit(session, user, "investigation_retired", item.id, {"physical_deleted_count": 0})
            return {"eligible_count": len(eligible), "retired_count": 0 if dry_run else len(eligible),
                    "physical_deleted_count": 0, "released_reference_count": 0, "dry_run": dry_run}

    def _retention_lock(self, session):
        # Holds and retirement of any branch in this independent site serialize.
        # PostgreSQL acceptance exercises the actual transaction/lock ordering.
        if session.bind.dialect.name == "postgresql":
            identity = int(_hash(self.site_id)[:15], 16)
            session.execute(text("SELECT pg_advisory_xact_lock(:identity)"), {"identity": identity})

    @staticmethod
    def _held_ancestor(session, item):
        seen = {item.id}
        parent = item.predecessor_investigation_id
        while parent is not None:
            if parent in seen or len(seen) >= 1024:
                return True  # Corrupt/unbounded ancestry must retain protection.
            seen.add(parent)
            ancestor = session.get(ResearchInvestigation, parent)
            if ancestor is None or ancestor.legal_hold:
                return True
            parent = ancestor.predecessor_investigation_id
        return False

    def reconcile(self, *, operation_id, user, retry=False):
        """Explicit owner recovery; observes/retries protection, never releases it."""
        if type(retry) is not bool:
            raise _error("invalid_request")
        identity = uuid.UUID(str(operation_id))
        if retry:
            return self._apply(identity, user)
        with self._transaction() as session:
            self._actor(session, user)
            op = session.scalar(select(ResearchContextOperation).where(
                ResearchContextOperation.id == identity, ResearchContextOperation.user_id == user.id,
            ))
            if op is None:
                raise _error("not_found")
            state = self.store.lifecycle()
            bindings = json.loads(op.references_json)
            return {"operation": self._operation(op), "bindings": [{**binding, "protected": state["references"].get(binding["reference"]) == binding["snapshot_id"]} for binding in bindings],
                    "reference_release": "unavailable_conservative_retention"}
