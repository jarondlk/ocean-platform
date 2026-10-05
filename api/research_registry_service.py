"""Authenticated scientific review and atomic application of immutable registries."""

from __future__ import annotations

from datetime import datetime, timezone
import uuid

from sqlalchemy import or_, select, text

from api.classification_review_service import (
    ClassificationReviewDomainError,
    _actor_identity,
    _require_actor,
)
from db.app_models import (
    ResearchAreaDefinition,
    ResearchPhysicalMembership,
    ResearchRegistryEvent,
    ResearchRegistryHead,
    ResearchRegistryReview,
    ResearchRegistryVersion,
)
from db.models import EdnaAssay, EdnaSample
from ingestion.immutable_bundle import canonical_bytes, digest
from preprocessing.research_recipe import SamplingRegistry
from preprocessing.research_sst import SSTProductDefinition

MAX_DEFINITION_BYTES = 16 * 1024 * 1024


def fail(code, detail, status=409):
    raise ClassificationReviewDomainError(status, code, detail)


def definition(kind, payload):
    if kind == "sampling":
        parsed = SamplingRegistry.model_validate(payload)
        key = "sampling:" + parsed.region_id
        value = parsed.model_dump(mode="json")
        value["areas"].sort(key=lambda a: a["area_id"])
        value["memberships"].sort(key=lambda m: m["physical_sample_id"])
    elif kind == "sst_product":
        parsed = SSTProductDefinition.model_validate(payload)
        key = "sst_product:" + parsed.product_id
        value = parsed.model_dump(mode="json")
    else:
        fail("registry_kind_invalid", "Unsupported registry kind", 400)
    if len(key) > 255 or len(canonical_bytes(value)) > MAX_DEFINITION_BYTES:
        fail(
            "registry_definition_limit",
            "Registry definition exceeds resource limit",
            400,
        )
    return key, value


def review_content(review):
    return {
        "kind": review.kind,
        "registry_key": review.registry_key,
        "definition": review.definition_json,
    }


def response(review, *, details=False):
    result = {
        "review_id": str(review.id),
        "kind": review.kind,
        "registry_key": review.registry_key,
        "state": review.state,
        "version": review.version,
        "content_sha256": review.content_sha256,
        "created_by_user_id": str(review.created_by_user_id),
        "decided_by_user_id": str(review.decided_by_user_id)
        if review.decided_by_user_id
        else None,
        "applied_by_user_id": str(review.applied_by_user_id)
        if review.applied_by_user_id
        else None,
    }
    if details:
        result["definition"] = review.definition_json
    return result


def append_event(session, review, actor, event_type, previous=None, details=None):
    payload = {
        "review_id": str(review.id),
        "sequence": review.version,
        "event_type": event_type,
        "state": review.state,
        "actor": _actor_identity(actor),
        "content_sha256": review.content_sha256,
        "previous_event_sha256": previous,
        "at": datetime.now(timezone.utc).isoformat(),
        "details": details or {},
    }
    row = ResearchRegistryEvent(
        review_id=review.id,
        sequence=review.version,
        event_sha256=digest(payload),
        payload_json=payload,
    )
    session.add(row)
    return row


def load_review(session, review_id, *, lock=False):
    query = select(ResearchRegistryReview).where(ResearchRegistryReview.id == review_id)
    review = session.scalar(query.with_for_update() if lock else query)
    if review is None:
        fail("registry_review_missing", "Unknown research registry review", 404)
    key, value = definition(review.kind, review.definition_json)
    if (
        key != review.registry_key
        or value != review.definition_json
        or digest(review_content(review)) != review.content_sha256
    ):
        fail("registry_review_integrity", "Registry review content integrity failure")
    events = session.scalars(
        select(ResearchRegistryEvent)
        .where(ResearchRegistryEvent.review_id == review.id)
        .order_by(ResearchRegistryEvent.sequence)
    ).all()
    previous = None
    state = None
    for sequence, event in enumerate(events, 1):
        p = event.payload_json
        expected_role = "admin" if p.get("event_type") == "applied" else "researcher"
        next_state = {
            "created": "draft",
            "approved": "approved",
            "rejected": "rejected",
            "applied": "applied",
        }.get(p.get("event_type"))
        valid_transition = (
            sequence == 1
            and next_state == "draft"
            or sequence == 2
            and state == "draft"
            and next_state in {"approved", "rejected"}
            or sequence == 3
            and state == "approved"
            and next_state == "applied"
        )
        if (
            event.sequence != sequence
            or p.get("sequence") != sequence
            or p.get("review_id") != str(review.id)
            or p.get("content_sha256") != review.content_sha256
            or p.get("previous_event_sha256") != previous
            or digest(p) != event.event_sha256
            or p.get("actor", {}).get("role") != expected_role
            or p.get("state") != next_state
            or not valid_transition
        ):
            fail(
                "registry_event_integrity",
                "Registry review event chain integrity failure",
            )
        expected_actor = (
            review.created_by_user_id
            if sequence == 1
            else review.decided_by_user_id
            if sequence == 2
            else review.applied_by_user_id
        )
        if p["actor"].get("user_id") != str(expected_actor):
            fail(
                "registry_event_actor_mismatch", "Registry review actor binding failure"
            )
        previous, state = event.event_sha256, next_state
    if not events or len(events) != review.version or state != review.state:
        fail(
            "registry_event_projection",
            "Registry review state does not match its event history",
        )
    return review, events


def preview_definition(session, kind, value, *, lock=False):
    if kind == "sst_product":
        return {
            "status": "requires_scientific_product_review",
            "product_id": value["product_id"],
            "measurement_type": value["measurement_type"],
            "historical_acquisition_verified": False,
            "limitations": [
                "Product approval does not verify archive access or actual granule coverage."
            ],
        }
    registry = SamplingRegistry.model_validate(value)
    bindings = {o.sample_id: o for m in registry.memberships for o in m.occurrences}
    sample_query = select(EdnaSample).where(EdnaSample.sample_id.in_(sorted(bindings)))
    assay_ids = sorted({m.representative_assay_id for m in registry.memberships})
    assay_query = select(EdnaAssay).where(EdnaAssay.assay_id.in_(assay_ids))
    samples = {
        s.sample_id: s
        for s in session.scalars(
            sample_query.with_for_update() if lock else sample_query
        )
    }
    assays = {
        a.assay_id: a
        for a in session.scalars(assay_query.with_for_update() if lock else assay_query)
    }
    stale = []
    for sid, binding in sorted(bindings.items()):
        sample = samples.get(sid)
        if (
            not sample
            or not sample.active
            or sample.scientific_content_sha256 != binding.scientific_content_sha256
        ):
            stale.append({"sample_id": sid, "reason": "stale_occurrence_evidence"})
    for membership in registry.memberships:
        assay = assays.get(membership.representative_assay_id)
        if (
            not assay
            or not assay.active
            or assay.sample_id not in {o.sample_id for o in membership.occurrences}
            or assay.scientific_content_sha256 != membership.representative_assay_sha256
        ):
            stale.append(
                {
                    "physical_sample_id": membership.physical_sample_id,
                    "reason": "stale_representative_assay",
                }
            )
    return {
        "status": "stale_evidence" if stale else "evidence_bindings_current",
        "source_occurrences": len(bindings),
        "physical_samples": len(registry.memberships),
        "areas": len(registry.areas),
        "environmental_occurrences": sum(
            s.sample_kind == "environmental" and s.is_control is False
            for s in samples.values()
        ),
        "stale_count": len(stale),
        "stale": stale[:100],
        "truncated": len(stale) > 100,
        "limitations": [
            "Classification and physical identity are separate approvals.",
            "Source hash matches verify bindings; the researcher must review the external identity/geography evidence.",
        ],
    }


def create_draft(session, *, kind, payload, actor):
    _require_actor(
        session, actor, role="researcher", permission="classification:decide"
    )
    key, value = definition(kind, payload)
    review = ResearchRegistryReview(
        id=uuid.uuid4(),
        kind=kind,
        registry_key=key,
        definition_json=value,
        state="draft",
        version=1,
        created_by_user_id=actor.id,
    )
    review.content_sha256 = digest(review_content(review))
    session.add(review)
    session.flush()
    append_event(session, review, actor, "created")
    session.flush()
    return response(review, details=True)


def check_expected(review, version, content_sha256):
    if review.version != version or review.content_sha256 != content_sha256:
        fail(
            "registry_review_conflict",
            "The reviewed version/content changed; reload its preview",
        )


def decide(session, review_id, *, approve, version, content_sha256, rationale, actor):
    _require_actor(
        session, actor, role="researcher", permission="classification:decide"
    )
    if not isinstance(rationale, str) or not rationale.strip() or len(rationale) > 4000:
        fail(
            "registry_decision_rationale",
            "A bounded scientific decision rationale is required",
            400,
        )
    review, events = load_review(session, review_id, lock=True)
    check_expected(review, version, content_sha256)
    if review.state != "draft":
        fail("registry_review_state", "Only a draft can receive a scientific decision")
    preview = preview_definition(
        session, review.kind, review.definition_json, lock=True
    )
    if approve and preview.get("stale_count", 0):
        fail(
            "registry_evidence_stale",
            "Source evidence changed; create a new exact review",
        )
    review.state = "approved" if approve else "rejected"
    review.version += 1
    review.decided_by_user_id = actor.id
    append_event(
        session,
        review,
        actor,
        review.state,
        events[-1].event_sha256,
        {"rationale": rationale, "preview": preview},
    )
    session.flush()
    return response(review, details=True)


def apply(session, review_id, *, version, content_sha256, actor):
    _require_actor(session, actor, role="admin", permission="classification:apply")
    review, events = load_review(session, review_id, lock=True)
    if review.state == "applied":
        # A replay does not reactivate an old generation over a newer head.
        record = session.scalar(
            select(ResearchRegistryVersion).where(
                ResearchRegistryVersion.review_id == review.id
            )
        )
        if record is None or digest(record.payload_json) != record.registry_id:
            fail(
                "registry_version_integrity",
                "Applied registry record is unavailable or corrupt",
            )
        if content_sha256 != review.content_sha256 or version != review.version - 1:
            fail(
                "registry_application_conflict",
                "Replay must use the exact approved version/content",
            )
        return {**response(review), "registry_id": record.registry_id, "reused": True}
    check_expected(review, version, content_sha256)
    if review.state != "approved":
        fail(
            "registry_review_state",
            "Scientific approval is required before application",
        )
    if session.get_bind().dialect.name == "postgresql":
        if review.kind == "sampling":
            session.execute(
                text("SELECT pg_advisory_xact_lock(:key)"),
                {"key": int(digest("research_sampling_identity")[:15], 16)},
            )
        session.execute(
            text("SELECT pg_advisory_xact_lock(:key)"),
            {"key": int(digest(review.registry_key)[:15], 16)},
        )
    preview = preview_definition(
        session, review.kind, review.definition_json, lock=True
    )
    if preview.get("stale_count", 0):
        fail(
            "registry_evidence_stale",
            "Source evidence changed after scientific approval",
        )
    payload = {
        "schema_version": 1,
        **review_content(review),
        "review_id": str(review.id),
        "scientific_approval_sha256": events[-1].event_sha256,
    }
    identity = digest(payload)
    session.add(
        ResearchRegistryVersion(
            registry_id=identity,
            review_id=review.id,
            registry_key=review.registry_key,
            payload_json=payload,
        )
    )
    session.flush()
    if review.kind == "sampling":
        registry = SamplingRegistry.model_validate(review.definition_json)
        bindings = {o.sample_id: m for m in registry.memberships for o in m.occurrences}
        physical = {m.physical_sample_id: m for m in registry.memberships}
        current = session.scalars(
            select(ResearchPhysicalMembership)
            .join(
                ResearchRegistryHead,
                ResearchRegistryHead.registry_id
                == ResearchPhysicalMembership.registry_id,
            )
            .where(
                ResearchRegistryHead.registry_key != review.registry_key,
                or_(
                    ResearchPhysicalMembership.sample_id.in_(sorted(bindings)),
                    ResearchPhysicalMembership.physical_sample_id.in_(sorted(physical)),
                ),
            )
        )
        for row in current:
            member = bindings.get(row.sample_id) or physical[row.physical_sample_id]
            if (
                row.physical_sample_id != member.physical_sample_id
                or row.representative_assay_id != member.representative_assay_id
            ):
                fail(
                    "registry_identity_conflict",
                    "An active regional registry has a conflicting identity/assay decision",
                )
        for area in registry.areas:
            value = area.model_dump(mode="json")
            session.add(
                ResearchAreaDefinition(
                    registry_id=identity,
                    area_id=area.area_id,
                    area_version=digest(value),
                    definition_json=value,
                )
            )
        for membership in registry.memberships:
            for occurrence in membership.occurrences:
                session.add(
                    ResearchPhysicalMembership(
                        registry_id=identity,
                        **occurrence.model_dump(),
                        physical_sample_id=membership.physical_sample_id,
                        representative_assay_id=membership.representative_assay_id,
                        representative_assay_sha256=membership.representative_assay_sha256,
                        area_id=membership.area_id,
                        area_version=membership.area_version,
                    )
                )
    head = session.get(ResearchRegistryHead, review.registry_key)
    if head is None:
        session.add(
            ResearchRegistryHead(registry_key=review.registry_key, registry_id=identity)
        )
    else:
        head.registry_id = identity
    review.state = "applied"
    review.version += 1
    review.applied_by_user_id = actor.id
    append_event(
        session,
        review,
        actor,
        "applied",
        events[-1].event_sha256,
        {"registry_id": identity, "preview": preview},
    )
    session.flush()
    return {**response(review), "registry_id": identity, "reused": False}


def read_registry(session, identity):
    from ingestion.immutable_bundle import validate_id

    validate_id(identity)
    record = session.get(ResearchRegistryVersion, identity)
    if record is None:
        fail("registry_version_missing", "Unknown applied registry", 404)
    review, events = load_review(session, record.review_id)
    payload = record.payload_json
    expected = {
        "schema_version": 1,
        **review_content(review),
        "review_id": str(review.id),
        "scientific_approval_sha256": events[1].event_sha256,
    }
    if review.state != "applied" or digest(payload) != identity or payload != expected:
        fail(
            "registry_version_integrity",
            "Registry application/approval integrity failure",
        )
    return payload
