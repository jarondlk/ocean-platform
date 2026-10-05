from contextlib import contextmanager
from copy import deepcopy
import uuid

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import select

import api.auth as auth
from api.main import app
from api import research_registry_routes as routes
from api import research_registry_service as service
from api.classification_review_service import ClassificationReviewDomainError
from db.app_models import (
    ResearchRegistryEvent,
    ResearchRegistryHead,
    ResearchRegistryReview,
    ResearchRegistryVersion,
)
from db.models import EdnaAssay, EdnaSample
from tests.research_fixtures import h, research_fixture
from tests.test_classification_review_domain import (
    _database,
    _seed,
    SAMPLE_ID,
    ASSAY_ID,
)


@pytest.fixture
def registry_database():
    factory = _database()
    actors = _seed(factory)
    f = research_fixture()
    value = {
        "schema_version": 1,
        "region_id": "fixture-region",
        "areas": [f[2][0].model_dump(mode="json")],
        "memberships": [f[3][0].model_dump(mode="json")],
    }
    value["memberships"][0].update(
        occurrences=[dict(sample_id=SAMPLE_ID, scientific_content_sha256="8" * 64)],
        representative_assay_id=ASSAY_ID,
        representative_assay_sha256="e" * 64,
    )
    return factory, actors, value


def draft(factory, actors, value):
    with factory.begin() as session:
        return service.create_draft(
            session, kind="sampling", payload=value, actor=actors["researcher"]
        )


def approve(factory, actors, d):
    with factory.begin() as session:
        return service.decide(
            session,
            uuid.UUID(d["review_id"]),
            approve=True,
            version=d["version"],
            content_sha256=d["content_sha256"],
            rationale="Fixture sampling evidence reviewed independently.",
            actor=actors["researcher"],
        )


def apply(factory, actors, approved):
    with factory.begin() as session:
        return service.apply(
            session,
            uuid.UUID(approved["review_id"]),
            version=approved["version"],
            content_sha256=approved["content_sha256"],
            actor=actors["admin"],
        )


def test_approval_application_history_and_replay_leave_source_untouched(
    registry_database,
):
    factory, actors, value = registry_database
    d = draft(factory, actors, value)
    approved = approve(factory, actors, d)
    applied = apply(factory, actors, approved)
    assert applied["state"] == "applied" and applied["version"] == 3
    assert apply(factory, actors, approved)["reused"] is True
    with factory() as session:
        payload = service.read_registry(session, applied["registry_id"])
        assert payload["definition"] == value
        events = session.scalars(select(ResearchRegistryEvent)).all()
        assert len(events) == 3
        assert (
            session.get(ResearchRegistryHead, "sampling:fixture-region").registry_id
            == applied["registry_id"]
        )
        sample = session.get(EdnaSample, SAMPLE_ID)
        assert (
            sample.physical_sample_id is None
        )  # Identity ledger does not rewrite provider rows.
        assert sample.scientific_content_sha256 == "8" * 64
        assert (
            sample.sample_kind == "unknown"
        )  # Identity approval is not classification approval.


def test_stale_hash_blocks_application_without_partial_records(registry_database):
    factory, actors, value = registry_database
    approved = approve(factory, actors, draft(factory, actors, value))
    with factory.begin() as session:
        session.get(EdnaSample, SAMPLE_ID).scientific_content_sha256 = h(
            "provider-changed"
        )
    with pytest.raises(
        ClassificationReviewDomainError, match="Source evidence changed"
    ):
        apply(factory, actors, approved)
    with factory() as session:
        assert session.scalar(select(ResearchRegistryVersion)) is None
        assert len(session.scalars(select(ResearchRegistryEvent)).all()) == 2
        assert (
            session.get(ResearchRegistryReview, uuid.UUID(approved["review_id"])).state
            == "approved"
        )


def test_old_replay_does_not_replace_a_new_head(registry_database):
    factory, actors, value = registry_database
    first_approval = approve(factory, actors, draft(factory, actors, value))
    first = apply(factory, actors, first_approval)
    newer = deepcopy(value)
    newer["memberships"][0]["decision"]["rationale"] += " Additional evidence."
    second = apply(
        factory, actors, approve(factory, actors, draft(factory, actors, newer))
    )
    assert first["registry_id"] != second["registry_id"]
    apply(factory, actors, first_approval)
    with factory() as session:
        assert (
            session.get(ResearchRegistryHead, "sampling:fixture-region").registry_id
            == second["registry_id"]
        )
        assert service.read_registry(session, first["registry_id"])


def test_same_physical_id_cannot_get_conflicting_assays_in_disjoint_regions(
    registry_database,
):
    factory, actors, value = registry_database
    apply(factory, actors, approve(factory, actors, draft(factory, actors, value)))
    sid, aid = h("another-occurrence"), h("another-assay")
    with factory.begin() as session:
        sample = session.get(EdnaSample, SAMPLE_ID)
        assay = session.get(EdnaAssay, ASSAY_ID)
        session.add(
            EdnaSample(
                **{
                    **{
                        c.name: getattr(sample, c.name)
                        for c in EdnaSample.__table__.columns
                    },
                    "sample_id": sid,
                    "provider_sample_id": "another-occurrence",
                }
            )
        )
        session.add(
            EdnaAssay(
                **{
                    **{
                        c.name: getattr(assay, c.name)
                        for c in EdnaAssay.__table__.columns
                    },
                    "assay_id": aid,
                    "sample_id": sid,
                }
            )
        )
    other = deepcopy(value)
    other["region_id"] = "another-region"
    other["areas"][0]["region_id"] = other["region_id"]
    member = other["memberships"][0]
    member.update(
        occurrences=[dict(sample_id=sid, scientific_content_sha256="8" * 64)],
        representative_assay_id=aid,
        area_version=service.digest(other["areas"][0]),
    )
    approved = approve(factory, actors, draft(factory, actors, other))
    with pytest.raises(
        ClassificationReviewDomainError, match="conflicting identity/assay"
    ):
        apply(factory, actors, approved)
    with factory() as session:
        assert session.get(ResearchRegistryHead, "sampling:another-region") is None
        assert len(session.scalars(select(ResearchRegistryVersion)).all()) == 1


def test_roles_expected_version_and_event_immutability(registry_database):
    factory, actors, value = registry_database
    for role in ("viewer", "admin"):
        with pytest.raises(
            ClassificationReviewDomainError, match="authenticated researcher"
        ):
            with factory.begin() as session:
                service.create_draft(
                    session, kind="sampling", payload=value, actor=actors[role]
                )
    d = draft(factory, actors, value)
    with pytest.raises(
        ClassificationReviewDomainError, match="version/content changed"
    ):
        with factory.begin() as session:
            service.decide(
                session,
                uuid.UUID(d["review_id"]),
                approve=True,
                version=2,
                content_sha256=d["content_sha256"],
                rationale="Reviewed",
                actor=actors["researcher"],
            )
    approved = approve(factory, actors, d)
    with pytest.raises(ClassificationReviewDomainError, match="authenticated admin"):
        with factory.begin() as session:
            service.apply(
                session,
                uuid.UUID(d["review_id"]),
                version=2,
                content_sha256=d["content_sha256"],
                actor=actors["researcher"],
            )
    apply(factory, actors, approved)
    with pytest.raises(ValueError, match="immutable"):
        with factory.begin() as session:
            event = session.scalar(select(ResearchRegistryEvent))
            event.payload_json = {"forged": True}


def test_api_permissions_and_preview_are_separate_from_application(
    registry_database, monkeypatch
):
    factory, actors, value = registry_database

    @contextmanager
    def sessions():
        with factory.begin() as session:
            yield session

    monkeypatch.setattr(routes, "get_session", sessions)
    monkeypatch.setattr(
        auth, "authenticate_request", lambda request: actors["researcher"]
    )
    client = TestClient(app)
    created = client.post(
        "/research-registry-reviews", json={"kind": "sampling", "definition": value}
    )
    assert created.status_code == 201
    d = created.json()
    base = "/research-registry-reviews/" + d["review_id"]
    preview = client.post(base + "/preview").json()
    assert preview["preview"]["status"] == "evidence_bindings_current"
    assert preview["preview"]["environmental_occurrences"] == 0
    request = {"version": d["version"], "content_sha256": d["content_sha256"]}
    assert client.post(base + "/apply", json=request).status_code == 403
    assert client.get("/research-registry-reviews").json()["total"] == 1
    assert client.get(base).json()["state"] == "draft"
    monkeypatch.setattr(auth, "authenticate_request", lambda request: actors["viewer"])
    assert client.get(base).status_code == 403
    assert auth.route_permission("PATCH", base) is None
    assert auth.route_permission("POST", base + "/apply") == "classification:apply"
