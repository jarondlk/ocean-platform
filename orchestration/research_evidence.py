"""C21 verified immutable evidence, owner-scoped receipts and retention fences.

This service reads committed C20 bytes. It never executes a controller, resumes
a run, searches for ambient stores, or deletes retained bytes or references.
"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import replace
import hashlib
import json
import math
import uuid

import config
from sqlalchemy import select

from api.csv_serialization import rows_to_csv
from db.app_models import (
    ResearchAnswerJob, ResearchContextRevision, ResearchConversation,
    ResearchEvidenceBlob, ResearchEvidenceContextDependency, ResearchEvidenceDependency,
    ResearchEvidenceProtection, ResearchEvidenceReceipt, ResearchInvestigation,
    ResearchRun, ResearchRunAttempt, ResearchRunInputHistory, ResearchRunManifest,
    ResearchRunPayload, ResearchRunStep,
)
from orchestration.catalogue_service import FrozenCatalogueResolver, catalogue_access_binding
from orchestration.investigations import InvestigationService, RetainedArtifactBinding
from orchestration.research_evidence_projection import project_retained_run
from orchestration.retained_artifacts import RetainedArtifactProvider, SessionAttachmentResolver
from orchestration.research_runs import ResearchRunError, ResearchRunService
from retrieval.source_scope import EvidenceScope
from schema.research_controller import (
    BudgetSnapshot, ControllerBinding, ControllerLimits, ControllerResult,
    canonical_hash, canonical_json,
)
from schema.research_evidence import (
    EVIDENCE_REQUEST_MODELS, EVIDENCE_RESPONSE_MODELS, EVIDENCE_VERSION,
    EvidenceReceipt, RunEvidenceAnchor, VerifiedEvidenceSet,
)

MAX_CLOSURE = 1024
MAX_EXPORT_BYTES = 8 * 1024 * 1024
MAX_PAGE_BYTES = 8 * 1024 * 1024


class ResearchEvidenceError(Exception):
    def __init__(self, code="evidence_unavailable", status_code=503):
        self.code, self.status_code = code, status_code
        self.message = {"authentication_required": "Authentication is required",
            "access_denied": "Evidence access is denied", "not_found": "Evidence was not found",
            "invalid_request": "Evidence request is invalid", "conflict": "Evidence identity conflicts with retained state"}.get(code, "Retained evidence is unavailable")
        super().__init__(code)


def _decoded(raw, expected=None):
    value = json.loads(raw)
    if canonical_json(value) != raw or (expected is not None and canonical_hash(value) != expected):
        raise ResearchEvidenceError()
    return value


def receipt_content_hash(value):
    if isinstance(value, EvidenceReceipt):
        value = value.model_dump(mode="json")
    return canonical_hash({key: item for key, item in value.items()
        if key not in {"id", "sha256", "attachment_reference"}})


def _receipt(value):
    # Hash the exact public typed projection, including its normalized scope,
    # before deriving the three identity fields. Raw input defaults are not a
    # second hash domain.
    placeholder = "0" * 64
    normalized = EvidenceReceipt.model_validate({**value, "id": "c21:receipt:" + placeholder,
        "sha256": placeholder, "attachment_reference": {"kind": "artifact",
            "id": "c21:receipt:" + placeholder, "snapshot_id": value["binding"]["snapshot_id"]}})
    value = normalized.model_dump(mode="json")
    digest = receipt_content_hash(value)
    identity = "c21:receipt:" + digest
    return EvidenceReceipt.model_validate({**value, "id": identity, "sha256": digest,
        "attachment_reference": {"kind": "artifact", "id": identity,
            "snapshot_id": value["binding"]["snapshot_id"]}})


def _payload_inputs(payload):
    return payload.get("receipt", {}).get("inputs", payload.get("inputs", []))


def _payload_rows(payload):
    if "rows" in payload:
        return payload["rows"]
    if payload.get("operation") == "c19.inventory_union":
        return [{"entity": "datasets", "count": payload["count"]}]
    if payload.get("version") == "c21-documentary-search-v1":
        return payload["excerpts"]
    if "items" in payload:
        return payload["items"]
    return [payload.get("node", payload)]


class ResearchEvidenceService:
    def __init__(self, *, session_factory, site_id, investigations, runs,
                 enabled=None, documentary_provider=None, external_artifact_providers=()):
        if (not isinstance(investigations, InvestigationService)
                or not isinstance(runs, ResearchRunService)
                or runs.investigations is not investigations
                or runs.session_factory is not session_factory
                or investigations.session_factory is not session_factory
                or runs.site_id != site_id or investigations.site_id != site_id):
            raise ValueError("Explicit matching independent v1 evidence dependencies required")
        if documentary_provider is not None:
            from orchestration.frozen_documentary import FrozenDocumentaryProvider
            if (not isinstance(documentary_provider, FrozenDocumentaryProvider)
                    or documentary_provider.store is not investigations.store
                    or documentary_provider.catalogue is not investigations.catalogue
                    or investigations.registrations.get(documentary_provider.registration.snapshot_id) is not documentary_provider.registration):
                raise ValueError("Explicit same-store documentary provider required")
        self.session_factory, self.site_id = session_factory, site_id
        self.investigations, self.runs = investigations, runs
        self.catalogue, self.store = investigations.catalogue, investigations.store
        self.enabled = enabled if enabled is not None else config.v1_evidence_enabled
        self.documentary_provider = documentary_provider
        if (not isinstance(external_artifact_providers, tuple)
                or len({id(provider) for provider in external_artifact_providers}) != len(external_artifact_providers)
                or any(not isinstance(provider, RetainedArtifactProvider)
                    or provider.investigations is not investigations or provider.site_id != site_id
                    or provider.session_factory is not session_factory for provider in external_artifact_providers)):
            raise ValueError("Explicit same-site retained artifact providers required")
        self.external_artifact_providers = external_artifact_providers

    @contextmanager
    def _transaction(self):
        with self.session_factory() as session:
            with session.begin():
                yield session

    def _principal(self, session, user):
        if not self.enabled():
            raise ResearchEvidenceError()
        try:
            return self.runs._principal(session, user=user)
        except ResearchRunError as exc:
            raise ResearchEvidenceError(exc.code, exc.status_code) from None

    def _source(self, session, run, actor, manifest):
        """Read-only direct authorization, deliberately no C17 resolver recursion."""
        investigation = session.get(ResearchInvestigation, run.investigation_id)
        conversation = session.get(ResearchConversation, run.conversation_id)
        revision = session.get(ResearchContextRevision, run.revision_id)
        frozen = _decoded(run.context_json)
        if (investigation is None or investigation.user_id != actor.id or investigation.status == "retired"
                or conversation is None or conversation.investigation_id != investigation.id
                or revision is None or revision.investigation_id != investigation.id
                or revision.snapshot_id != run.snapshot_id or revision.payload_sha256 != run.payload_sha256
                or _decoded(revision.payload_json, run.payload_sha256) != frozen.get("context")
                or {key: frozen.get(key) for key in ControllerBinding.model_fields} != self.runs._binding(run)):
            raise ResearchEvidenceError("access_denied", 403)
        try:
            if manifest.get("actor_binding") != catalogue_access_binding(actor):
                raise ValueError("Source authorization epoch changed")
            self._policy(run.snapshot_id, actor, manifest["catalogue_policy_revision"])
            self.investigations._snapshot(run.snapshot_id, frozen["context"]["scope"], actor)
            # Reopening an already retained receipt must still close authority
            # over its experimental context. Native C21 receipt dependencies
            # are traversed separately by _read_receipt; never recurse through
            # those IDs here or promote a foreign output to scientific evidence.
            for reference in [*frozen["context"]["attachments"], *frozen["context"]["pins"]]:
                if reference["kind"] != "artifact" or reference["id"].startswith("c21:receipt:"):
                    continue
                expected = frozen["context"].get("artifact_bindings", {}).get(canonical_hash(reference))
                provider, binding = self._external_artifact(session, actor, reference)
                if binding.sha256 != expected:
                    raise ValueError("Retained experimental context changed")
                provider.verify_context(session, run.revision_id, reference, expected, actor)
        except Exception:
            raise ResearchEvidenceError("access_denied", 403) from None
        return frozen

    def _policy(self, snapshot_id, actor, expected):
        """Use the central C14 proof; never rewrite the old C20 manifest."""
        resolver = self.catalogue.resolver
        resolved = resolver.resolve(actor, snapshot_id)
        if resolved.revision == expected:
            return resolved.revision
        if isinstance(resolver, FrozenCatalogueResolver) and resolver.revision_compatible(actor, snapshot_id, expected):
            return resolved.revision
        raise ResearchEvidenceError("access_denied", 403)

    def authorize_run(self, session, run, actor):
        """Fresh C21 guard usable by the separately durable answer worker."""
        if run.user_id != actor.id:
            raise ResearchEvidenceError("not_found", 404)
        manifest = self._manifest(session, run, run.input_version)
        self._source(session, run, actor, manifest)
        return self._policy(run.snapshot_id, actor, manifest["catalogue_policy_revision"])

    @staticmethod
    def _manifest(session, run, version):
        row = session.get(ResearchRunManifest, (run.id, version))
        if row is None:
            raise ResearchEvidenceError()
        return _decoded(row.manifest_json, row.manifest_sha256)

    def _steps(self, session, run, version, manifest, seen=None):
        seen = set() if seen is None else seen
        if run.id in seen or len(seen) >= MAX_CLOSURE:
            raise ResearchEvidenceError()
        seen.add(run.id)
        prefix, result = f"input:{version}:", {}
        rows = session.scalars(select(ResearchRunStep).where(ResearchRunStep.run_id == run.id,
            ResearchRunStep.step_id.startswith(prefix))).all()
        parent_steps = None
        for row in rows:
            # An uncommitted reservation contributes no scientific observation.
            if row.state != "committed":
                continue
            logical = row.step_id[len(prefix):]
            request = _decoded(row.request_json, row.request_sha256)
            payload = session.get(ResearchRunPayload, (run.id, row.outcome_sha256))
            if payload is None:
                raise ResearchEvidenceError()
            outcome = _decoded(payload.payload_json, payload.sha256)
            attempts = session.scalars(select(ResearchRunAttempt).where(
                ResearchRunAttempt.run_id == run.id, ResearchRunAttempt.step_id == row.step_id)).all()
            origin = (f"{run.id}:{row.step_id}",)
            if not attempts:
                if run.continuation_of is None or not logical.startswith(("pin:", "inventory:")):
                    raise ResearchEvidenceError()
                parent = session.get(ResearchRun, run.continuation_of)
                if (parent is None or parent.user_id != run.user_id
                        or self.runs._binding(parent) != self.runs._binding(run)
                        or parent.context_json != run.context_json
                        or self._manifest(session, parent, parent.input_version) != manifest):
                    raise ResearchEvidenceError()
                if parent_steps is None:
                    parent_steps = self._steps(session, parent, parent.input_version, manifest, seen)
                prior = parent_steps.get(logical)
                if prior is None or prior["request"] != request or prior["outcome"] != outcome:
                    raise ResearchEvidenceError()
                origin = prior["origin_step_refs"]
            else:
                ordinals = [item.ordinal for item in sorted(attempts, key=lambda item: item.ordinal)]
                if ordinals != list(range(1, len(attempts) + 1)) or any(item.lease_epoch < 1 for item in attempts):
                    raise ResearchEvidenceError()
                for attempt in attempts:
                    BudgetSnapshot.model_validate(_decoded(attempt.budget_json))
            result[logical] = {"kind": row.kind, "request": request, "outcome": outcome,
                "origin_step_refs": origin}
        seen.remove(run.id)
        return result

    def _verified(self, session, run_id, input_version, actor):
        run = session.get(ResearchRun, uuid.UUID(str(run_id)))
        if run is None or run.user_id != actor.id:
            raise ResearchEvidenceError("not_found", 404)
        if run.input_version != input_version or run.status not in {"completed", "partial"} or run.controller_result_json is None:
            raise ResearchEvidenceError("evidence_ineligible", 409)
        manifest = self._manifest(session, run, input_version)
        frozen = self._source(session, run, actor, manifest)
        # Every effective input is immutable and content addressed. A child may
        # be introduced by its parent's explicit continuation history.
        history = session.scalars(select(ResearchRunInputHistory).where(
            ResearchRunInputHistory.result_run_id == run.id).order_by(ResearchRunInputHistory.created_at, ResearchRunInputHistory.sequence)).all()
        if not history or any(_decoded(item.request_json, item.request_sha256) is None for item in history):
            raise ResearchEvidenceError()
        questions = [item.effective_question for item in history if item.kind in {"submit", "clarify", "continue"}]
        if not questions or questions[-1] != run.effective_question:
            raise ResearchEvidenceError()
        result_json = _decoded(run.controller_result_json)
        projected = project_retained_run(frozen=frozen, question=run.effective_question, manifest=manifest,
            result=result_json, steps=self._steps(session, run, input_version, manifest))
        result = ControllerResult.model_validate_json(canonical_json(result_json))
        # C20 stores integer milliseconds using truncation; preserve the closed
        # controller high water conservatively by rounding it up, never down.
        active_ms = max(run.active_elapsed_ms, min(180000, math.ceil(result.budget.active_elapsed_seconds * 1000)))
        budget = BudgetSnapshot(active_elapsed_seconds=active_ms / 1000,
            tool_actions=run.tool_actions, model_calls=run.model_calls, malformed_repairs=run.malformed_repairs,
            cancellation_requested=run.cancellation_requested)
        if any(getattr(result.budget, key) > getattr(budget, key) for key in ("tool_actions", "model_calls", "malformed_repairs")):
            raise ResearchEvidenceError()
        attached, attached_payloads, external_qualifications = [], {}, []
        for reference in [*frozen["context"]["attachments"], *frozen["context"]["pins"]]:
            if reference["kind"] == "artifact":
                key = canonical_hash(reference)
                expected = frozen["context"].get("artifact_bindings", {}).get(key)
                if reference["id"].startswith("c21:receipt:"):
                    receipt, attached_payload, _ = self._read_receipt(session, reference["id"], actor)
                    if reference != receipt.attachment_reference.model_dump(mode="json") or expected != receipt.sha256:
                        raise ResearchEvidenceError("access_denied", 403)
                    if reference in frozen["context"]["attachments"] and receipt.id not in attached_payloads:
                        attached.append(receipt)
                        attached_payloads[receipt.id] = attached_payload
                else:
                    provider, binding = self._external_artifact(session, actor, reference)
                    if binding.sha256 != expected:
                        raise ResearchEvidenceError("access_denied", 403)
                    provider.verify_context(session, run.revision_id, reference, expected, actor)
                    external_qualifications.append("Attached experimental context is retained but is not independently verified scientific evidence: " + reference["id"])
        anchor = RunEvidenceAnchor(run_id=str(run.id), input_version=input_version, owner_id=str(actor.id),
            binding=result.binding, effective_question=run.effective_question,
            effective_question_sha256=hashlib.sha256(run.effective_question.encode("utf-8")).hexdigest(),
            controller_result=result, controller_result_sha256=canonical_hash(result_json),
            execution_manifest_sha256=canonical_hash(manifest), effective_scope=EvidenceScope.model_validate(projected.resolution.effective_scope),
            scope_witness_sha256=projected.resolution.sha256, limits=ControllerLimits.model_validate(manifest["limits"]),
            run_budget_high_water=budget, actor_binding=catalogue_access_binding(actor),
            catalogue_policy_revision=self._policy(run.snapshot_id, actor, manifest["catalogue_policy_revision"]), clock_invalid=run.reason_code == "invalid_clock",
            frozen_context=frozen, execution_manifest=manifest,
            allowed_dataset_ids=tuple(sorted(projected.resolution.allowed_dataset_ids)) if projected.resolution.allowed_dataset_ids is not None else None)
        receipts, payloads, inputs = [], {}, {}
        by_payload = {}
        for observation in projected.collector.observations:
            payload = projected.collector.payload(observation)
            origin_ids = [by_payload[item] for item in payload.get("derived_from", [])]
            parameters = projected.requests[observation.observation_id]
            scientific = "receipt" in payload or payload.get("operation") == "c19.inventory_union"
            total = payload.get("receipt", {}).get("total_rows", payload.get("total"))
            if payload.get("operation") == "c19.inventory_union":
                total = {"state": "known", "value": 1, "reason": None}
            elif total is None:
                total = {"state": "unknown", "value": None, "reason": "This retained operation does not report a row total"}
            raw_total = {"state": total["state"], "value": total.get("value"), "reason": total.get("reason")}
            if raw_total["state"] == "known":
                raw_total["reason"] = None
            elif not raw_total["reason"]:
                raw_total["reason"] = "The retained source did not report a complete total"
            preview = json.loads(observation.preview_json)[:20]
            receipt = _receipt({"run_id": str(run.id), "input_version": input_version,
                "binding": observation.binding.model_dump(mode="json"), "observation_id": observation.observation_id,
                "kind": "scientific" if scientific else "catalogue", "authority": observation.authority,
                "operation_id": observation.operation_id, "operation_version": observation.operation_version,
                "parameters": parameters, "parameters_sha256": observation.parameters_sha256,
                "scope": json.loads(observation.scope_json), "input_count": observation.input_count,
                "input_sha256": observation.input_sha256, "payload_sha256": observation.full_payload_sha256,
                "result_content_sha256": observation.result_content_sha256,
                "availability": observation.availability, "source_completeness": observation.source_completeness,
                "query_completion": observation.query_completion, "counts": [item.model_dump(mode="json") for item in observation.counts],
                "total_rows": raw_total, "returned_count": payload.get("receipt", {}).get("returned_count", payload.get("returned_count", len(_payload_rows(payload)))),
                "offset": payload.get("offset", 0), "next_offset": payload.get("next_offset"),
                "preview_rows": preview, "preview_truncated": observation.preview_truncated or len(_payload_rows(payload)) > len(preview),
                "columns": payload.get("columns", []), "qualifications": list(observation.qualifications), "origin_receipt_ids": origin_ids})
            receipts.append(receipt)
            payloads[receipt.id], inputs[receipt.id] = payload, _payload_inputs(payload)
            by_payload[observation.full_payload_ref] = receipt.id
        unresolved = tuple(dict.fromkeys([*(fact.reason for fact in result.completion.facts if fact.state != "supported" and fact.reason), *result.completion.unresolved_cohorts, *external_qualifications]))
        return VerifiedEvidenceSet(anchor=anchor, receipts=tuple(receipts), full_payloads_by_receipt=payloads,
            input_manifests_by_receipt=inputs, attached_receipts=tuple(attached),
            attached_full_payloads_by_receipt=attached_payloads, unresolved_work=unresolved)

    def load_verified(self, run_id, input_version, user):
        try:
            with self._transaction() as session:
                actor = self._principal(session, user)
                return self._verified(session, run_id, input_version, actor)
        except ResearchEvidenceError:
            raise
        except Exception:
            raise ResearchEvidenceError() from None

    def _references(self, receipt):
        registration = self.investigations.registrations.get(receipt.binding.snapshot_id)
        if registration is None:
            raise ResearchEvidenceError()
        return [{"snapshot_id": snapshot, "reference": "c21:dependency:" + canonical_hash([self.site_id, receipt.id, snapshot])}
            for snapshot in (receipt.binding.snapshot_id, *registration.child_snapshot_ids)]

    def _retain(self, verified, user):
        """Prepare app protection before any independent C09 reference write."""
        with self._transaction() as session:
            actor = self._principal(session, user)
            self.investigations._retention_lock(session)
            source = session.scalar(select(ResearchInvestigation).where(
                ResearchInvestigation.id == uuid.UUID(verified.anchor.binding.investigation_id)).with_for_update())
            if source is None or source.status == "retired" or source.user_id != actor.id:
                raise ResearchEvidenceError("access_denied", 403)
            # Recheck authorization after the serialized origin lock.
            run = session.get(ResearchRun, uuid.UUID(verified.anchor.run_id))
            self._source(session, run, actor, verified.anchor.execution_manifest)
            for receipt in verified.receipts:
                payload, inputs = verified.full_payloads_by_receipt[receipt.id], verified.input_manifests_by_receipt[receipt.id]
                blob_sha = canonical_hash({"payload": payload, "inputs": inputs})
                row = session.get(ResearchEvidenceReceipt, receipt.id)
                if row is not None:
                    if row.user_id != actor.id or row.receipt_json != canonical_json(receipt.model_dump(mode="json")) or row.blob_sha256 != blob_sha:
                        raise ResearchEvidenceError("conflict", 409)
                    continue
                blob = session.get(ResearchEvidenceBlob, (actor.id, blob_sha))
                if blob is None:
                    session.add(ResearchEvidenceBlob(user_id=actor.id, sha256=blob_sha,
                        payload_json=canonical_json(payload), inputs_json=canonical_json(inputs)))
                    session.flush()
                row = ResearchEvidenceReceipt(id=receipt.id, user_id=actor.id,
                    run_id=uuid.UUID(receipt.run_id), input_version=receipt.input_version,
                    **{key: uuid.UUID(getattr(receipt.binding, key)) for key in ("investigation_id", "conversation_id", "revision_id")},
                    snapshot_id=receipt.binding.snapshot_id, payload_sha256=receipt.binding.payload_sha256,
                    sha256=receipt.sha256, blob_sha256=blob_sha, receipt_json=canonical_json(receipt.model_dump(mode="json")), state="prepared")
                session.add(row)
                session.flush()
                session.add(ResearchEvidenceProtection(receipt_id=receipt.id, user_id=actor.id,
                    references_json=canonical_json(self._references(receipt)), state="prepared"))
                # Prepared edges protect older ready source receipts. Derived
                # siblings become ready in observation order before edges below.
        for receipt in verified.receipts:
            try:
                for binding in self._references(receipt):
                    self.store.add_reference(binding["snapshot_id"], binding["reference"])
            except Exception:
                with self._transaction() as session:
                    protection = session.get(ResearchEvidenceProtection, receipt.id)
                    if protection is not None and protection.state != "ready":
                        protection.state = "uncertain"
                raise ResearchEvidenceError("evidence_protection_pending", 503) from None
            with self._transaction() as session:
                actor = self._principal(session, user)
                self.investigations._retention_lock(session)
                row = session.scalar(select(ResearchEvidenceReceipt).where(ResearchEvidenceReceipt.id == receipt.id).with_for_update())
                protection = session.get(ResearchEvidenceProtection, receipt.id)
                run = session.get(ResearchRun, row.run_id)
                self._source(session, run, actor, verified.anchor.execution_manifest)
                lifecycle = self.store.lifecycle()
                for binding in self._references(receipt):
                    entry = lifecycle["snapshots"].get(binding["snapshot_id"])
                    if lifecycle["references"].get(binding["reference"]) != binding["snapshot_id"] or not entry or entry["revoked"] or entry["retired"]:
                        raise ResearchEvidenceError("evidence_protection_pending", 503)
                if row.state == "ready":
                    continue
                for identity in dict.fromkeys([*receipt.origin_receipt_ids, *(item.id for item in verified.attached_receipts)]):
                    self._read_receipt(session, identity, actor)
                    if session.get(ResearchEvidenceDependency, (receipt.id, identity)) is None:
                        session.add(ResearchEvidenceDependency(receipt_id=receipt.id, origin_receipt_id=identity, user_id=actor.id))
                session.flush()
                row.state, protection.state = "ready", "ready"
        with self._transaction() as session:
            actor = self._principal(session, user)
            run = session.get(ResearchRun, uuid.UUID(verified.anchor.run_id))
            current_policy = self.authorize_run(session, run, actor)
            return replace(verified, anchor=replace(verified.anchor, catalogue_policy_revision=current_policy))

    def ensure_retained(self, run_id, input_version, user):
        return self._retain(self.load_verified(run_id, input_version, user), user)

    def _read_receipt(self, session, identity, actor, seen=None, memo=None):
        seen = set() if seen is None else seen
        memo = {} if memo is None else memo
        if identity in memo:
            return memo[identity]
        if identity in seen or len(seen) + len(memo) >= MAX_CLOSURE:
            raise ResearchEvidenceError()
        seen.add(identity)
        row = session.get(ResearchEvidenceReceipt, identity)
        if row is None or row.user_id != actor.id or row.state != "ready":
            raise ResearchEvidenceError("not_found", 404)
        receipt = EvidenceReceipt.model_validate(_decoded(row.receipt_json))
        if (receipt.id != row.id or receipt.sha256 != row.sha256 or receipt_content_hash(receipt) != receipt.sha256
                or receipt.run_id != str(row.run_id) or receipt.input_version != row.input_version
                or receipt.binding.model_dump(mode="json") != self.runs._binding(row)):
            raise ResearchEvidenceError()
        run = session.get(ResearchRun, row.run_id)
        if run is None or run.user_id != actor.id:
            raise ResearchEvidenceError()
        manifest = self._manifest(session, run, row.input_version)
        self._source(session, run, actor, manifest)
        protection = session.get(ResearchEvidenceProtection, row.id)
        if protection is None or protection.state != "ready" or _decoded(protection.references_json) != self._references(receipt):
            raise ResearchEvidenceError()
        lifecycle = self.store.lifecycle()
        for binding in self._references(receipt):
            entry = lifecycle["snapshots"].get(binding["snapshot_id"])
            if lifecycle["references"].get(binding["reference"]) != binding["snapshot_id"] or not entry or entry["revoked"] or entry["retired"]:
                raise ResearchEvidenceError("access_denied", 403)
        blob = session.get(ResearchEvidenceBlob, (actor.id, row.blob_sha256))
        if blob is None:
            raise ResearchEvidenceError()
        payload, inputs = _decoded(blob.payload_json), _decoded(blob.inputs_json)
        if canonical_hash({"payload": payload, "inputs": inputs}) != blob.sha256 or canonical_hash(payload) != receipt.payload_sha256 or canonical_hash(inputs) != receipt.input_sha256 or len(inputs) != receipt.input_count:
            raise ResearchEvidenceError()
        dependencies = session.scalars(select(ResearchEvidenceDependency).where(ResearchEvidenceDependency.receipt_id == identity)).all()
        if not set(receipt.origin_receipt_ids) <= {item.origin_receipt_id for item in dependencies}:
            raise ResearchEvidenceError()
        for dependency in dependencies:
            if dependency.user_id != actor.id:
                raise ResearchEvidenceError()
            self._read_receipt(session, dependency.origin_receipt_id, actor, seen, memo)
        seen.remove(identity)
        memo[identity] = (receipt, payload, inputs)
        return memo[identity]

    def _external_artifact(self, session, user, reference):
        matches = []
        for provider in self.external_artifact_providers:
            if (not isinstance(provider, RetainedArtifactProvider)
                    or provider.investigations is not self.investigations
                    or provider.site_id != self.site_id or provider.session_factory is not self.session_factory):
                raise ResearchEvidenceError()
            binding = provider.resolve(session, user, reference)
            if binding is not None:
                if (not isinstance(binding, RetainedArtifactBinding) or binding.owner_user_id != user.id
                        or binding.id != reference["id"] or binding.snapshot_id != reference["snapshot_id"]
                        or len(binding.sha256) != 64 or any(c not in "0123456789abcdef" for c in binding.sha256)):
                    raise ResearchEvidenceError()
                matches.append((provider, binding))
        # Unknown, unavailable and ambiguous ownership fail closed. A C21
        # namespace always follows native receipt verification, never providers.
        if len(matches) != 1:
            raise ResearchEvidenceError()
        return matches[0]

    def authorize_attachment_owner(self, session, user):
        for provider in self.external_artifact_providers:
            if provider.investigations is not self.investigations or provider.session_factory is not self.session_factory or provider.site_id != self.site_id:
                raise ResearchEvidenceError()
            provider.authorize_owner(session, user)

    def attachment_resolver(self):
        return SessionAttachmentResolver(self)

    def resolve_attachment_in_session(self, session, user, reference):
        if not self.enabled():
            raise ResearchEvidenceError()
        self.investigations._actor(session, user)
        if reference["id"].startswith("c21:receipt:"):
            receipt, _, _ = self._read_receipt(session, reference["id"], user)
            if receipt.attachment_reference.model_dump(mode="json") != reference:
                raise ResearchEvidenceError("access_denied", 403)
            return RetainedArtifactBinding(id=receipt.id, snapshot_id=receipt.binding.snapshot_id,
                sha256=receipt.sha256, owner_user_id=user.id)
        return self._external_artifact(session, user, reference)[1]

    def resolve_attachment(self, user, reference):
        """Read-only callable form for a host outside an application transaction."""
        try:
            with self._transaction() as session:
                return self.resolve_attachment_in_session(session, user, reference)
        except Exception:
            return None

    def prepare_context(self, session, operation, candidate, user):
        for reference in [*candidate["attachments"], *candidate["pins"]]:
            if reference["kind"] != "artifact":
                continue
            if not reference["id"].startswith("c21:receipt:"):
                provider, _ = self._external_artifact(session, user, reference)
                provider.prepare_context(session, operation, candidate, reference, user)
                continue
            receipt, _, _ = self._read_receipt(session, reference["id"], user)
            if reference != receipt.attachment_reference.model_dump(mode="json"):
                raise ResearchEvidenceError("access_denied", 403)
            if session.get(ResearchEvidenceContextDependency, (operation.id, receipt.id)) is None:
                session.add(ResearchEvidenceContextDependency(operation_id=operation.id, receipt_id=receipt.id,
                    user_id=user.id, investigation_id=operation.investigation_id, state="prepared"))

    def activate_context(self, session, operation, candidate, user):
        self.prepare_context(session, operation, candidate, user)
        for reference in [*candidate["attachments"], *candidate["pins"]]:
            if reference["kind"] == "artifact" and not reference["id"].startswith("c21:receipt:"):
                provider, _ = self._external_artifact(session, user, reference)
                provider.activate_context(session, operation, candidate, reference, user)
        dependencies = session.scalars(select(ResearchEvidenceContextDependency).where(
            ResearchEvidenceContextDependency.operation_id == operation.id)).all()
        for item in dependencies:
            self._read_receipt(session, item.receipt_id, user)
            if item.state != "committed":
                item.state = "committed"

    @staticmethod
    def blocks_retirement(session, investigation):
        for model in (ResearchEvidenceReceipt, ResearchAnswerJob, ResearchEvidenceContextDependency):
            if session.scalar(select(model).where(model.investigation_id == investigation.id).limit(1)) is not None:
                return True
        return False

    def invoke(self, name, payload, user):
        try:
            request = EVIDENCE_REQUEST_MODELS[name].model_validate(payload)
        except (KeyError, ValueError, TypeError):
            raise ResearchEvidenceError("invalid_request", 422) from None
        try:
            if name == "list":
                verified = self.ensure_retained(request.run_id, request.input_version, user)
                binding = verified.anchor.binding
                if binding.investigation_id != request.investigation_id or binding.conversation_id != request.conversation_id:
                    raise ResearchEvidenceError("not_found", 404)
                with self._transaction() as session:
                    actor = self._principal(session, user)
                    items = []
                    retained_ids = session.scalars(select(ResearchEvidenceReceipt.id).where(
                        ResearchEvidenceReceipt.user_id == actor.id,
                        ResearchEvidenceReceipt.run_id == uuid.UUID(request.run_id),
                        ResearchEvidenceReceipt.input_version == request.input_version,
                        ResearchEvidenceReceipt.state == "ready")).all()
                    for receipt in dict.fromkeys([*retained_ids, *(item.id for item in verified.attached_receipts)]):
                        items.append(self._read_receipt(session, receipt, actor)[0])
                    items.sort(key=lambda item: item.id)
                    page, size = [], 0
                    for item in items[request.offset:request.offset + request.limit]:
                        item_size = len(canonical_json(item.model_dump(mode="json")).encode("utf-8"))
                        if size + item_size > MAX_PAGE_BYTES:
                            if not page:
                                raise ResearchEvidenceError("evidence_page_too_large", 503)
                            break
                        page.append(item)
                        size += item_size
                    result = {"version": EVIDENCE_VERSION, "access_revision": canonical_hash([catalogue_access_binding(actor), verified.anchor.catalogue_policy_revision, [item.sha256 for item in items]]),
                        "run_id": request.run_id, "input_version": request.input_version, "offset": request.offset,
                        "items": [item.model_dump(mode="json") for item in page],
                        "next_offset": request.offset + len(page) if request.offset + len(page) < len(items) else None,
                        "total": len(items)}
            else:
                with self._transaction() as session:
                    actor = self._principal(session, user)
                    receipt, raw, inputs = self._read_receipt(session, request.receipt_id, actor)
                    if receipt.sha256 != request.expected_sha256:
                        raise ResearchEvidenceError("conflict", 409)
                    run = session.get(ResearchRun, uuid.UUID(receipt.run_id))
                    current_policy = self.authorize_run(session, run, actor)
                    result = {"version": EVIDENCE_VERSION, "access_revision": canonical_hash([catalogue_access_binding(actor), current_policy, receipt.sha256]),
                        "receipt": receipt.model_dump(mode="json")}
                    if name in {"page", "export"}:
                        rows = inputs if request.section == "inputs" else _payload_rows(raw)
                        page = rows[request.offset:request.offset + request.limit]
                        while len(canonical_json(page).encode("utf-8")) > MAX_PAGE_BYTES:
                            if len(page) == 1:
                                raise ResearchEvidenceError("evidence_page_too_large", 503)
                            page.pop()
                        total = {"state": "known", "value": len(inputs), "reason": None} if request.section == "inputs" else receipt.total_rows.model_dump(mode="json")
                        next_offset = request.offset + len(page) if request.offset + len(page) < len(rows) else None
                        result.update(section=request.section, offset=request.offset, rows=page,
                            next_offset=next_offset, section_total=total)
                        if name == "export":
                            if "data:export" not in actor.permissions:
                                raise ResearchEvidenceError("access_denied", 403)
                            provenance = {"receipt_id": receipt.id, "receipt_sha256": receipt.sha256,
                                "binding": receipt.binding.model_dump(mode="json"), "operation_id": receipt.operation_id,
                                "operation_version": receipt.operation_version, "parameters": receipt.parameters,
                                "executed_request_sha256": canonical_hash(receipt.parameters),
                                "parameters_sha256": receipt.parameters_sha256,
                                "parameters_sha256_domain": "C19 normalized scientific receipt parameters; transport limit/offset excluded",
                                "scope": receipt.scope.canonical(), "input_count": receipt.input_count,
                                "input_sha256": receipt.input_sha256, "payload_sha256": receipt.payload_sha256,
                                "result_content_sha256": receipt.result_content_sha256,
                                "qualifications": receipt.qualifications, "section": request.section,
                                "offset": request.offset, "returned_count": len(page), "next_offset": next_offset,
                                "section_total": total, "retained_source_page_offset": receipt.offset,
                                "retained_source_page_returned_count": receipt.returned_count,
                                "retained_source_page_next_offset": receipt.next_offset,
                                "pagination_basis": "Retained bytes only; source operation is not re-executed"}
                            content = canonical_json({"provenance": provenance, "rows": page}) if request.format == "json" else rows_to_csv(page, list(dict.fromkeys(key for row in page for key in row)))
                            if len(content.encode("utf-8")) > MAX_EXPORT_BYTES:
                                raise ResearchEvidenceError("export_page_too_large", 422)
                            result.pop("rows")
                            result.update(format=request.format, filename=f"evidence-{receipt.sha256[:16]}-{request.section}-{request.offset}.{request.format}",
                                mime_type="application/json; charset=utf-8" if request.format == "json" else "text/csv; charset=utf-8",
                                content_text=content, content_sha256=hashlib.sha256(content.encode("utf-8")).hexdigest(),
                                provenance=provenance, returned_count=len(page))
            return EVIDENCE_RESPONSE_MODELS[name].model_validate(result).model_dump(mode="json")
        except ResearchEvidenceError:
            raise
        except Exception:
            raise ResearchEvidenceError() from None

    def retain_documentary(self, run_id, input_version, payload, user, *, remaining_timeout=None):
        verified = self.ensure_retained(run_id, input_version, user)
        provider = self.documentary_provider
        if provider is None or not callable(getattr(provider, "verify_result", None)):
            raise ResearchEvidenceError()
        permitted = {}
        for values in verified.input_manifests_by_receipt.values():
            for item in values:
                if item["object_id"] in permitted and permitted[item["object_id"]] != item:
                    raise ResearchEvidenceError()
                permitted[item["object_id"]] = item
        remaining = max(0, verified.anchor.limits.active_seconds - verified.anchor.run_budget_high_water.active_elapsed_seconds)
        if remaining_timeout is not None:
            if type(remaining_timeout) not in (int, float) or not math.isfinite(remaining_timeout) or remaining_timeout <= 0:
                raise ResearchEvidenceError()
            remaining = min(remaining, remaining_timeout)
        if remaining <= 0:
            raise ResearchEvidenceError("budget_exhausted", 409)
        try:
            provider.verify_result(payload, query=verified.anchor.effective_question,
                binding=verified.anchor.binding.model_dump(mode="json"), effective_scope=verified.anchor.effective_scope.canonical(),
                permitted_input_manifest=[permitted[key] for key in sorted(permitted)], current_actor=user,
                expected_policy_revision=verified.anchor.catalogue_policy_revision,
                limit=payload["limit"], remaining_timeout=remaining)
        except Exception:
            raise ResearchEvidenceError() from None
        inputs = payload["inputs"]
        if payload["input_sha256"] != canonical_hash(inputs) or payload["input_count"] != len(inputs):
            raise ResearchEvidenceError()
        receipt = _receipt({"run_id": run_id, "input_version": input_version,
            "binding": verified.anchor.binding.model_dump(mode="json"),
            "observation_id": "c21:documentary:" + canonical_hash(payload), "kind": "documentary", "authority": "documentary",
            "operation_id": payload["operation_id"], "operation_version": payload["operation_version"],
            "parameters": {"query_sha256": payload["query_sha256"], "ranking_version": payload["ranking_version"], "limit": payload["limit"], "index_object_sha256": payload["index_object_sha256"]},
            "parameters_sha256": canonical_hash({"query_sha256": payload["query_sha256"], "ranking_version": payload["ranking_version"], "limit": payload["limit"]}),
            "scope": verified.anchor.effective_scope.canonical(), "input_count": len(inputs), "input_sha256": canonical_hash(inputs),
            "payload_sha256": canonical_hash(payload), "result_content_sha256": canonical_hash(payload["excerpts"]),
            "availability": "available", "source_completeness": "unknown", "query_completion": "complete",
            "counts": [], "total_rows": {"state": "unknown", "value": None, "reason": "Ranked top-k excerpts do not establish exhaustive coverage"},
            "returned_count": len(payload["excerpts"]), "offset": 0, "next_offset": None,
            "preview_rows": payload["excerpts"][:20], "preview_truncated": len(payload["excerpts"]) > 20,
            "columns": [], "qualifications": payload["qualifications"], "origin_receipt_ids": [item.id for item in verified.receipts]})
        self._retain(replace(verified, receipts=(receipt,), full_payloads_by_receipt={receipt.id: payload},
            input_manifests_by_receipt={receipt.id: inputs}), user)
        return receipt
