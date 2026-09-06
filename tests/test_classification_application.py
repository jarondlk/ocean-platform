from __future__ import annotations

import json

import pytest
from sqlalchemy import select

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
from api.classification_review_service import create_draft, decide_review
from api.schemas import (
    ClassificationReviewDecisionRequest,
    ClassificationReviewDraftCreate,
)
from db.app_models import (
    AppUser,
    ClassificationApplication,
    ClassificationApplicationEvent,
    ClassificationReview,
)
from db.models import EdnaSample
from preprocessing.anemone_classification import parse_review
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
        sample.sample_kind = review.sample_kind
        sample.is_control = (
            None if review.sample_kind == "unknown" else review.sample_kind != "environmental"
        )
        sample.classification_review_json = json.dumps(
            {
                "decision": {
                    "review_id": str(review.id),
                    "review_version": application.review_version,
                    "review_content_sha256": review.content_sha256,
                }
            }
        )
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
            assert execute
            session.commit()
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
