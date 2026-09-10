from __future__ import annotations

import json
import uuid
from dataclasses import replace

import pytest
from sqlalchemy import func, select

from api.classification_application_service import (
    APPLICATION_STAGES,
    ClassificationApplicationError,
    application_summary,
    begin_application,
    complete_stage,
    database_review_artifact,
    fail_application,
    finalize_application,
    start_stage,
    workload_actor,
)
from api.classification_review_service import (
    _digest as review_event_digest,
    _event_payload as review_event_payload,
    create_draft,
    decide_review,
    review_response,
)
from api.classification_review_service import ClassificationReviewDomainError
from api.schemas import (
    ClassificationReviewDecisionRequest,
    ClassificationReviewDraftCreate,
)
from db.app_models import (
    AppUser,
    ClassificationApplication,
    ClassificationApplicationEvent,
    ClassificationReview,
    ClassificationReviewEvent,
)
from db.models import EdnaSample
from preprocessing.anemone_classification import (
    build_review_lineage,
    canonical_sha256,
    parse_review,
    sample_kind_control_status,
)
from scripts.register_classification_workload import register_workload
from tests.test_classification_review_domain import (
    _database,
    _draft_payload,
    _seed,
)


def _approved(factory, users, *, kind="environmental", supersedes=None):
    with factory() as session:
        draft = create_draft(
            session,
            request=ClassificationReviewDraftCreate.model_validate(
                _draft_payload(
                    sample_kind=kind,
                    supersedes_review_id=str(supersedes) if supersedes else None,
                )
            ),
            actor=users["researcher"],
        )
        approved = decide_review(
            session,
            review_id=draft.id,
            request=ClassificationReviewDecisionRequest(
                expected_version=draft.version,
                decision="approved",
            ),
            actor=users["researcher"],
        )
        session.commit()
        return approved


def _canonicalize(factory, application_id):
    with factory() as session:
        application = session.get(ClassificationApplication, application_id)
        review = session.get(ClassificationReview, application.review_id)
        sample = session.get(EdnaSample, review.sample_id)
        artifact = database_review_artifact(
            session,
            review,
            approved_version=application.review_version,
        )
        lineage = build_review_lineage(
            artifact,
            artifact["decisions"][0],
            provider_classification_basis=sample.classification_basis,
        )
        sample.sample_kind = review.sample_kind
        sample.is_control = sample_kind_control_status(review.sample_kind)
        sample.classification_basis = "review:" + canonical_sha256(lineage)
        sample.classification_review_json = json.dumps(lineage)
        session.commit()


def _complete_application(factory, users, approved, *, operation_id="apply-one"):
    with factory() as session:
        application = begin_application(
            session,
            review_id=approved.id,
            operation_id=operation_id,
            actor=users["admin"],
        )
        session.commit()
        application_id = application.id
    for stage in APPLICATION_STAGES[:-1]:
        with factory() as session:
            _, execute = start_stage(session, application_id, stage)
            session.commit()
        if not execute:
            continue
        if stage == "import":
            _canonicalize(factory, application_id)
        with factory() as session:
            complete_stage(
                session,
                application_id,
                stage,
                {"stage": stage, f"{stage}_artifact_id": "a" * 64},
            )
            session.commit()
    with factory() as session:
        _, execute = start_stage(session, application_id, "finalize")
        assert execute
        session.commit()
    with factory() as session:
        result = finalize_application(session, application_id, users["admin"])
        session.commit()
        return result


def test_application_records_ordered_stages_and_idempotent_replay():
    factory = _database()
    users = _seed(factory)
    approved = _approved(factory, users)
    completed = _complete_application(factory, users, approved)

    assert completed.status == "applied"
    assert completed.completed_stages_json == list(APPLICATION_STAGES)
    with factory() as session:
        review = session.get(ClassificationReview, approved.id)
        assert review.state == "applied"
        assert review.application_reference == "apply-one"
        events = list(
            session.scalars(
                select(ClassificationApplicationEvent)
                .where(ClassificationApplicationEvent.application_id == completed.id)
                .order_by(ClassificationApplicationEvent.sequence)
            )
        )
        assert events[-1].event_type == "run_applied"
        review_event = session.scalar(
            select(ClassificationReviewEvent)
            .where(
                ClassificationReviewEvent.review_id == approved.id,
                ClassificationReviewEvent.event_type == "applied",
            )
        )
        assert review_event.details_json == {
            "schema_version": 1,
            "application_id": str(completed.id),
            "application_event_id": str(events[-1].id),
            "application_event_sequence": events[-1].sequence,
            "application_event_sha256": events[-1].event_sha256,
            "operation_id": "apply-one",
            "review_id": str(approved.id),
            "approved_review_version": 2,
            "expected_review_version": 2,
            "review_content_sha256": approved.content_sha256,
            "workload_actor_user_id": str(users["admin"].id),
            "workload_actor_identity": events[0].result_json["actor_identity"],
            "terminal_event_type": "run_applied",
            "application_status": "applied",
            "stage": "finalize",
            "stage_result": {"application_reference": "apply-one"},
            "error_code": None,
            "recovery": [],
        }
        application_event_count = len(events)
        review_event_count = session.scalar(
            select(func.count(ClassificationReviewEvent.id)).where(
                ClassificationReviewEvent.review_id == approved.id
            )
        )
        replayed_final = finalize_application(session, completed.id, users["admin"])
        assert replayed_final.id == completed.id
        assert session.scalar(
            select(func.count(ClassificationApplicationEvent.id)).where(
                ClassificationApplicationEvent.application_id == completed.id
            )
        ) == application_event_count
        assert session.scalar(
            select(func.count(ClassificationReviewEvent.id)).where(
                ClassificationReviewEvent.review_id == approved.id
            )
        ) == review_event_count
        replay = begin_application(
            session,
            review_id=approved.id,
            operation_id="apply-one",
            actor=users["admin"],
        )
        assert replay.id == completed.id
        assert application_summary(replay)["status"] == "applied"


def test_application_rejects_competing_run_and_tampered_receipts():
    factory = _database()
    users = _seed(factory)
    approved = _approved(factory, users)
    with factory() as session:
        application = begin_application(
            session,
            review_id=approved.id,
            operation_id="first-run",
            actor=users["admin"],
        )
        start_stage(session, application.id, "register_review")
        session.commit()
        application_id = application.id
    with factory() as session:
        with pytest.raises(ClassificationApplicationError, match="already running"):
            begin_application(
                session,
                review_id=approved.id,
                operation_id="competing-run",
                actor=users["admin"],
            )
    with factory() as session:
        event = session.scalar(
            select(ClassificationApplicationEvent).where(
                ClassificationApplicationEvent.application_id == application_id
            )
        )
        event.result_json = {"tampered": True}
        with pytest.raises(ValueError, match="append-only"):
            session.flush()
    with factory() as session:
        application = session.get(ClassificationApplication, application_id)
        application.completed_stages_json = ["register_review"]
        session.commit()
    with factory() as session:
        with pytest.raises(ClassificationApplicationError, match="event history"):
            start_stage(session, application_id, "normalize")


def test_failed_started_stage_resumes_without_repeating_completed_stage():
    factory = _database()
    users = _seed(factory)
    approved = _approved(factory, users)
    with factory() as session:
        application = begin_application(
            session,
            review_id=approved.id,
            operation_id="resume-one",
            actor=users["admin"],
        )
        session.commit()
        application_id = application.id
    with factory() as session:
        start_stage(session, application_id, "register_review")
        complete_stage(
            session,
            application_id,
            "register_review",
            {"review_artifact_id": "b" * 64},
        )
        start_stage(session, application_id, "normalize")
        session.commit()
    with factory() as session:
        failed = fail_application(
            session,
            application_id,
            stage="normalize",
            error_code="normalize_failed",
            actor=users["admin"],
        )
        session.commit()
        assert failed.recovery_json
        failed_event_count = session.scalar(
            select(func.count(ClassificationApplicationEvent.id)).where(
                ClassificationApplicationEvent.application_id == application_id
            )
        )
        review = session.get(ClassificationReview, approved.id)
        review_event_count = session.scalar(
            select(func.count(ClassificationReviewEvent.id)).where(
                ClassificationReviewEvent.review_id == approved.id
            )
        )
        assert review.state == "failed"
        assert review.application_reference == "resume-one"
    with factory() as session:
        replacement_run = begin_application(
            session,
            review_id=approved.id,
            operation_id="replacement-after-failure",
            actor=users["admin"],
        )
        assert replacement_run.review_version == 2
        session.rollback()
    with factory() as session:
        replay = fail_application(
            session,
            application_id,
            stage="normalize",
            error_code="normalize_failed",
            actor=users["admin"],
        )
        assert replay.status == "failed"
        assert session.scalar(
            select(func.count(ClassificationApplicationEvent.id)).where(
                ClassificationApplicationEvent.application_id == application_id
            )
        ) == failed_event_count
        assert session.scalar(
            select(func.count(ClassificationReviewEvent.id)).where(
                ClassificationReviewEvent.review_id == approved.id
            )
        ) == review_event_count
    with factory() as session:
        resumed = begin_application(
            session,
            review_id=approved.id,
            operation_id="resume-one",
            actor=users["admin"],
        )
        assert resumed.status == "running"
        _, rerun = start_stage(session, application_id, "register_review")
        assert not rerun
        _, rerun = start_stage(session, application_id, "normalize")
        assert rerun
    completed = _complete_application(
        factory,
        users,
        approved,
        operation_id="resume-one",
    )
    with factory() as session:
        review = session.get(ClassificationReview, approved.id)
        applied_event = session.scalar(
            select(ClassificationReviewEvent).where(
                ClassificationReviewEvent.review_id == approved.id,
                ClassificationReviewEvent.event_type == "applied",
            )
        )
        assert completed.status == "applied"
        assert review.state == "applied"
        assert review.version == 4
        assert applied_event.details_json["approved_review_version"] == 2
        assert applied_event.details_json["expected_review_version"] == 3


def test_terminal_outcome_rejects_identity_mismatch_and_unsafe_failure():
    factory = _database()
    users = _seed(factory)
    approved = _approved(factory, users)
    with factory() as session:
        application = begin_application(
            session,
            review_id=approved.id,
            operation_id="identity-bound",
            actor=users["admin"],
        )
        start_stage(session, application.id, "register_review")
        session.commit()
        application_id = application.id

    other_id = uuid.uuid4()
    with factory() as session:
        session.add(
            AppUser(
                id=other_id,
                auth_provider="oidc",
                auth_subject="other-admin-subject",
                email="other-admin@example.org",
                display_name="Other Admin",
                role="admin",
                account_type="internal",
                status="active",
            )
        )
        session.commit()
    other_admin = replace(
        users["admin"],
        id=other_id,
        email="other-admin@example.org",
        display_name="Other Admin",
    )
    with factory() as session:
        with pytest.raises(ClassificationApplicationError) as exc:
            fail_application(
                session,
                application_id,
                stage="register_review",
                error_code="register_failed",
                actor=other_admin,
            )
        assert exc.value.code == "operation_actor_conflict"
        session.rollback()

    with factory() as session:
        with pytest.raises(ClassificationApplicationError) as exc:
            fail_application(
                session,
                application_id,
                stage="normalize",
                error_code="normalize_failed",
                actor=users["admin"],
            )
        assert exc.value.code == "application_stage_order"
        session.rollback()
    with factory() as session:
        application = session.get(ClassificationApplication, application_id)
        review = session.get(ClassificationReview, approved.id)
        assert application.status == "running"
        assert review.state == "approved"
        assert not session.scalars(
            select(ClassificationApplicationEvent).where(
                ClassificationApplicationEvent.application_id == application_id,
                ClassificationApplicationEvent.event_type == "run_failed",
            )
        ).all()


def test_fabricated_operational_binding_fails_closed():
    factory = _database()
    users = _seed(factory)
    approved = _approved(factory, users)
    completed = _complete_application(factory, users, approved, operation_id="bound-receipt")
    with factory() as session:
        event = session.scalar(
            select(ClassificationReviewEvent).where(
                ClassificationReviewEvent.review_id == approved.id,
                ClassificationReviewEvent.event_type == "applied",
            )
        )
        fabricated = {**event.details_json, "application_id": str(uuid.uuid4())}
        payload = review_event_payload(
            review_id=event.review_id,
            sequence=event.sequence,
            event_type=event.event_type,
            from_state=event.from_state,
            to_state=event.to_state,
            actor_user_id=event.actor_user_id,
            actor_role=event.actor_role,
            actor_identity=event.actor_identity_json,
            occurred_at=event.occurred_at,
            content_sha256=event.content_sha256,
            review_snapshot=event.review_snapshot_json,
            details=fabricated,
        )
        session.execute(
            ClassificationReviewEvent.__table__.update()
            .where(ClassificationReviewEvent.id == event.id)
            .values(details_json=fabricated, event_sha256=review_event_digest(payload))
        )
        session.commit()
    with factory() as session:
        review = session.get(ClassificationReview, approved.id)
        with pytest.raises(ClassificationReviewDomainError) as exc:
            review_response(session, review)
        assert exc.value.code == "operational_receipt_invalid"
        assert completed.status == "applied"


def test_superseded_approval_stops_an_existing_application():
    factory = _database()
    users = _seed(factory)
    approved = _approved(factory, users)
    with factory() as session:
        application = begin_application(
            session,
            review_id=approved.id,
            operation_id="stale-one",
            actor=users["admin"],
        )
        session.commit()
    _approved(factory, users, kind="unknown", supersedes=approved.id)
    with factory() as session:
        with pytest.raises(ClassificationApplicationError, match="no longer approved"):
            start_stage(session, application.id, "register_review")
        session.rollback()
    with factory() as session:
        with pytest.raises(ClassificationApplicationError, match="no longer approved"):
            fail_application(
                session,
                application.id,
                stage="register_review",
                error_code="register_failed",
                actor=users["admin"],
            )
        session.rollback()
    with factory() as session:
        assert not session.scalars(
            select(ClassificationApplicationEvent).where(
                ClassificationApplicationEvent.application_id == application.id,
                ClassificationApplicationEvent.event_type == "run_failed",
            )
        ).all()


def test_explicit_rollback_requires_matching_superseding_review():
    factory = _database()
    users = _seed(factory)
    original = _approved(factory, users)
    applied = _complete_application(factory, users, original, operation_id="original")
    correction = _approved(factory, users, kind="unknown", supersedes=original.id)
    with factory() as session:
        rollback = begin_application(
            session,
            review_id=correction.id,
            operation_id="rollback-one",
            actor=users["admin"],
            rollback_of_application_id=applied.id,
        )
        assert rollback.mode == "rollback"
        assert rollback.rollback_of_application_id == applied.id
    _complete_application(
        factory,
        users,
        correction,
        operation_id="correction-applied",
    )
    with factory() as session:
        sample = session.get(EdnaSample, correction.sample_id)
        lineage = json.loads(sample.classification_review_json)
        assert sample.sample_kind == "unknown"
        assert sample.is_control is None
        assert lineage["decision"]["review_id"] == str(correction.id)
    next_correction = _approved(
        factory,
        users,
        kind="negative_control",
        supersedes=correction.id,
    )
    with factory() as session:
        with pytest.raises(ClassificationApplicationError, match="supersede"):
            begin_application(
                session,
                review_id=next_correction.id,
                operation_id="rollback-wrong",
                actor=users["admin"],
                rollback_of_application_id=applied.id,
            )


def test_applied_unknown_requires_explicit_supersession():
    factory = _database()
    users = _seed(factory)
    approved = _approved(factory, users, kind="unknown")
    _complete_application(factory, users, approved, operation_id="apply-unknown")

    with factory() as session:
        with pytest.raises(ClassificationReviewDomainError) as exc:
            create_draft(
                session,
                request=ClassificationReviewDraftCreate.model_validate(
                    _draft_payload(sample_kind="environmental")
                ),
                actor=users["researcher"],
            )
        assert exc.value.code == "classification_already_known"

    with factory() as session:
        replacement = create_draft(
            session,
            request=ClassificationReviewDraftCreate.model_validate(
                _draft_payload(
                    sample_kind="environmental",
                    supersedes_review_id=str(approved.id),
                )
            ),
            actor=users["researcher"],
        )
        assert replacement.supersedes_review_id == approved.id


@pytest.mark.parametrize(
    "corruption",
    ["malformed_json", "wrong_shape", "missing_fields", "invalid_kind", "digest"],
)
def test_application_rejects_corrupt_canonical_lineage(corruption):
    factory = _database()
    users = _seed(factory)
    approved = _approved(factory, users)
    with factory() as session:
        application = begin_application(
            session,
            review_id=approved.id,
            operation_id=f"corrupt-{corruption}",
            actor=users["admin"],
        )
        session.commit()
        application_id = application.id
    _canonicalize(factory, application_id)

    with factory() as session:
        sample = session.get(EdnaSample, approved.sample_id)
        if corruption == "malformed_json":
            sample.classification_review_json = "{"
        elif corruption == "wrong_shape":
            sample.classification_review_json = "[]"
        elif corruption == "missing_fields":
            sample.classification_review_json = json.dumps({"schema_version": 1})
        else:
            lineage = json.loads(sample.classification_review_json)
            if corruption == "invalid_kind":
                lineage["decision"]["sample_kind"] = "field"
            else:
                lineage["decision"]["review_content_sha256"] = "f" * 64
            sample.classification_review_json = json.dumps(lineage)
        session.commit()

    with factory() as session:
        with pytest.raises(ClassificationApplicationError) as exc:
            start_stage(session, application_id, "register_review")
        assert exc.value.code == "canonical_lineage_corrupt"


def test_application_rejects_rehashed_wrong_review_content_digest():
    factory = _database()
    users = _seed(factory)
    approved = _approved(factory, users)
    with factory() as session:
        application = begin_application(
            session,
            review_id=approved.id,
            operation_id="rehashed-wrong-content",
            actor=users["admin"],
        )
        session.commit()
        application_id = application.id
    _canonicalize(factory, application_id)

    with factory() as session:
        sample = session.get(EdnaSample, approved.sample_id)
        lineage = json.loads(sample.classification_review_json)
        lineage["decision"]["review_content_sha256"] = "f" * 64
        artifact = {
            "schema_version": 1,
            "status": "approved",
            "source_snapshot_id": lineage["source_snapshot_id"],
            "decisions": [lineage["decision"]],
        }
        lineage["review_sha256"] = canonical_sha256(artifact)
        sample.classification_basis = "review:" + canonical_sha256(lineage)
        sample.classification_review_json = json.dumps(lineage)
        session.commit()

    with factory() as session:
        with pytest.raises(ClassificationApplicationError) as exc:
            start_stage(session, application_id, "register_review")
        assert exc.value.code == "canonical_application_mismatch"


def test_database_artifact_retains_authenticated_decision_and_unknown():
    factory = _database()
    users = _seed(factory)
    approved = _approved(factory, users, kind="unknown")
    with factory() as session:
        review = session.get(ClassificationReview, approved.id)
        artifact = database_review_artifact(
            session,
            review,
            approved_version=approved.version,
        )
        parsed = parse_review(json.dumps(artifact).encode())
    decision = parsed["decisions"][0]
    assert decision["sample_kind"] == "unknown"
    assert decision["review_id"] == str(approved.id)
    assert decision["review_version"] == approved.version
    assert decision["review_content_sha256"] == approved.content_sha256
    assert decision["reviewer"] == "Researcher User"


def test_workload_actor_is_derived_from_registered_service_identity(monkeypatch):
    factory = _database()
    users = _seed(factory)
    subject = "ocean-jobs@example.iam.gserviceaccount.com"
    with factory() as session:
        admin = session.get(AppUser, users["admin"].id)
        admin.auth_provider = "workload_identity"
        admin.auth_subject = subject
        session.commit()
    monkeypatch.setenv("CLASSIFICATION_APPLICATION_ACTOR_SUBJECT", subject)
    with factory() as session:
        actor = workload_actor(session)
        assert actor.id == users["admin"].id
        assert actor.auth_provider == "workload_identity"


def test_workload_registration_is_audited_idempotent_and_conflict_safe():
    factory = _database()
    subject = "ocean-jobs@example-project.iam.gserviceaccount.com"
    with factory() as session:
        user, created = register_workload(session, subject)
        session.commit()
        assert created and user.role == "admin" and user.account_type == "internal"
    with factory() as session:
        replay, created = register_workload(session, subject)
        assert not created and replay.id == user.id
    with factory() as session:
        existing = session.get(AppUser, user.id)
        existing.status = "suspended"
        session.commit()
    with factory() as session:
        with pytest.raises(ValueError, match="conflicting"):
            register_workload(session, subject)
