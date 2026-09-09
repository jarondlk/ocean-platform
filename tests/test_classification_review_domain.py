from __future__ import annotations

import uuid
from contextlib import contextmanager
from dataclasses import replace
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import api.auth as api_auth
import api.classification_review_routes as review_routes
from api.auth import CurrentUser, ROLE_PERMISSIONS, route_permission
from api.main import app
from db.app_models import (
    AppBase,
    AppUser,
    ClassificationReview,
    ClassificationReviewEvent,
)
from db.models import (
    CorpusBase,
    EdnaAssay,
    EdnaDetection,
    EdnaInternalStandard,
    EdnaSample,
    ExternalSourceFile,
    ExternalSourceSnapshot,
)


SNAPSHOT_ID = "1" * 64
OTHER_SNAPSHOT_ID = "a" * 64
SAMPLE_FILE_ID = "2" * 64
SAMPLE_FILE_SHA = "3" * 64
EXPERIMENT_FILE_ID = "4" * 64
EXPERIMENT_FILE_SHA = "5" * 64
SAMPLE_ID = "6" * 64
ASSAY_ID = "7" * 64
QC_FILE_ID = "8" * 64
QC_FILE_SHA = "9" * 64
THREE_NN_FILE_ID = "b" * 64
THREE_NN_FILE_SHA = "c" * 64
PROVIDER_SAMPLE_ID = "ANEMONE-SAMPLE-1"


def _database():
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    AppBase.metadata.create_all(engine)
    CorpusBase.metadata.create_all(
        engine,
        tables=[
            ExternalSourceSnapshot.__table__,
            ExternalSourceFile.__table__,
            EdnaSample.__table__,
            EdnaAssay.__table__,
            EdnaDetection.__table__,
            EdnaInternalStandard.__table__,
        ],
    )
    return sessionmaker(bind=engine, expire_on_commit=False)


def _current(user: AppUser) -> CurrentUser:
    return CurrentUser(
        id=user.id,
        email=user.email,
        display_name=user.display_name,
        role=user.role,
        account_type=user.account_type,
        status=user.status,
        permissions=ROLE_PERMISSIONS[user.role],
        auth_provider=user.auth_provider,
    )


def _seed(factory, *, detection_prefixes=("d", "e")):
    with factory() as session:
        users = {}
        for role in ("viewer", "researcher", "admin"):
            user = AppUser(
                id=uuid.uuid4(),
                auth_provider="oidc",
                auth_subject=f"{role}-subject",
                email=f"{role}@example.org",
                display_name=f"{role.title()} User",
                role=role,
                account_type="research" if role == "researcher" else "internal",
                status="active",
            )
            session.add(user)
            users[role] = user

        for snapshot_id in (SNAPSHOT_ID, OTHER_SNAPSHOT_ID):
            session.add(
                ExternalSourceSnapshot(
                    snapshot_id=snapshot_id,
                    provider="anemone",
                    source_family="edna_metabarcoding",
                    scope_url="https://db.anemone.bio/dist/MiFish/ANEMONE/test/",
                    scope_level="sample",
                    source_collection_sha256="b" * 64,
                    contract_version=2,
                    contract_sha256="c" * 64,
                    selection_policy="interpreted_mifish",
                    generated_at=datetime.now(timezone.utc),
                    file_count=2,
                    selected_file_count=2,
                    total_bytes=200,
                    status="complete",
                    manifest_sha256="d" * 64,
                    manifest_summary_json="{}",
                )
            )
        session.flush()
        session.add_all(
            [
                ExternalSourceFile(
                    source_file_id=SAMPLE_FILE_ID,
                    snapshot_id=SNAPSHOT_ID,
                    relative_path="sample.tsv.xz",
                    source_url="https://db.anemone.bio/sample.tsv.xz",
                    sample_name=PROVIDER_SAMPLE_ID,
                    role="sample_metadata",
                    selection_status="selected",
                    size_bytes=100,
                    sha256=SAMPLE_FILE_SHA,
                    validation_status="valid",
                    row_count=2,
                ),
                ExternalSourceFile(
                    source_file_id=EXPERIMENT_FILE_ID,
                    snapshot_id=SNAPSHOT_ID,
                    relative_path="experiment.tsv.xz",
                    source_url="https://db.anemone.bio/experiment.tsv.xz",
                    sample_name=PROVIDER_SAMPLE_ID,
                    role="experiment_metadata",
                    selection_status="selected",
                    size_bytes=100,
                    sha256=EXPERIMENT_FILE_SHA,
                    validation_status="valid",
                    row_count=1,
                ),
                ExternalSourceFile(
                    source_file_id=QC_FILE_ID,
                    snapshot_id=SNAPSHOT_ID,
                    relative_path="community_qc_target.tsv.xz",
                    source_url="https://db.anemone.bio/community_qc_target.tsv.xz",
                    sample_name=PROVIDER_SAMPLE_ID,
                    role="community_qc_target",
                    selection_status="selected",
                    size_bytes=100,
                    sha256=QC_FILE_SHA,
                    validation_status="valid",
                    row_count=2,
                ),
                ExternalSourceFile(
                    source_file_id=THREE_NN_FILE_ID,
                    snapshot_id=SNAPSHOT_ID,
                    relative_path="community_qc3nn_target.tsv.xz",
                    source_url=(
                        "https://db.anemone.bio/community_qc3nn_target.tsv.xz"
                    ),
                    sample_name=PROVIDER_SAMPLE_ID,
                    role="community_qc3nn_target",
                    selection_status="selected",
                    size_bytes=100,
                    sha256=THREE_NN_FILE_SHA,
                    validation_status="valid",
                    row_count=2,
                ),
            ]
        )
        session.flush()
        session.add(
            EdnaSample(
                sample_id=SAMPLE_ID,
                provider="anemone",
                provider_sample_id=PROVIDER_SAMPLE_ID,
                provider_project_id="project",
                provider_run_id="run",
                project_name="Project",
                original_sample_label=PROVIDER_SAMPLE_ID,
                sample_kind="unknown",
                is_control=None,
                classification_basis="no_reviewed_classification_metadata",
                classification_review_json=None,
                collection_date_utc="2026-01-01",
                temporal_precision="date",
                lat=38.4,
                lon=141.5,
                raw_metadata_json=(
                    '{"control_type":"not_control",'
                    '"sampling_method":"surface water"}'
                ),
                anchor_event_id=None,
                source_snapshot_id=SNAPSHOT_ID,
                source_file_id=SAMPLE_FILE_ID,
                source_row_numbers_json="[2,3]",
                active=True,
                first_seen_snapshot_id=SNAPSHOT_ID,
                last_seen_snapshot_id=SNAPSHOT_ID,
                scientific_content_sha256="8" * 64,
                source_row_hash="9" * 64,
            )
        )
        session.flush()
        session.add(
            EdnaAssay(
                assay_id=ASSAY_ID,
                sample_id=SAMPLE_ID,
                target_gene="12S",
                primer_set="MiFish",
                sequencing_method="Illumina",
                library_layout="paired",
                instrument_model="MiSeq",
                raw_metadata_json='{"pcr_primers":"MiFish"}',
                source_snapshot_id=SNAPSHOT_ID,
                source_file_id=EXPERIMENT_FILE_ID,
                source_row_numbers_json="[2]",
                active=True,
                first_seen_snapshot_id=SNAPSHOT_ID,
                last_seen_snapshot_id=SNAPSHOT_ID,
                scientific_content_sha256="e" * 64,
                source_row_hash="f" * 64,
            )
        )
        session.flush()
        for method, file_id, prefix in (
            ("qcauto_target", QC_FILE_ID, detection_prefixes[0]),
            ("qcauto_95pct_3nn_target", THREE_NN_FILE_ID, detection_prefixes[1]),
        ):
            for index, (genus, species, reads) in enumerate(
                (("Alpha", "Alpha one", 1), ("Beta", "Beta two", 3)),
                start=2,
            ):
                session.add(
                    EdnaDetection(
                        detection_id=(prefix + str(index)) * 32,
                        assay_id=ASSAY_ID,
                        assignment_method=method,
                        sequence=f"ACGT{index}",
                        sequence_sha256=(str(index) + prefix) * 32,
                        read_count=reads,
                        copies_per_ml=None,
                        superkingdom="Eukaryota",
                        kingdom="Animalia",
                        phylum="Chordata",
                        class_="Actinopterygii",
                        order="Perciformes",
                        family="Exampleidae",
                        genus=genus,
                        species=species,
                        subspecies=None,
                        assigned_taxon_name=species,
                        assigned_taxon_rank="species",
                        taxonomy_json=(
                            '{"kingdom":"Animalia","genus":"'
                            + genus
                            + '","species":"'
                            + species
                            + '"}'
                        ),
                        source_snapshot_id=SNAPSHOT_ID,
                        source_file_id=file_id,
                        source_row_number=index,
                        active=True,
                        first_seen_snapshot_id=SNAPSHOT_ID,
                        last_seen_snapshot_id=SNAPSHOT_ID,
                        scientific_content_sha256=(prefix + "f") * 32,
                        source_row_hash=(prefix + "a") * 32,
                    )
                )
        session.commit()
        return {role: _current(user) for role, user in users.items()}


def _install_database(monkeypatch, factory):
    @contextmanager
    def fake_get_session():
        session = factory()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    monkeypatch.setattr(review_routes, "get_session", fake_get_session)


def _client(monkeypatch, user):
    monkeypatch.setattr(api_auth, "authenticate_request", lambda _request: user)
    return TestClient(app)


def _draft_payload(*, sample_kind="unknown", supersedes_review_id=None):
    payload = {
        "source_snapshot_id": SNAPSHOT_ID,
        "sample_id": SAMPLE_ID,
        "sample_kind": sample_kind,
        "rationale": "The cited metadata does not resolve sample classification.",
        "evidence": [
            {
                "source_role": "sample_metadata",
                "source_file_id": SAMPLE_FILE_ID,
                "source_sha256": SAMPLE_FILE_SHA,
                "row_number": 2,
                "key": "control_type",
                "value": "not_control",
            },
            {
                "source_role": "experiment_metadata",
                "source_file_id": EXPERIMENT_FILE_ID,
                "source_sha256": EXPERIMENT_FILE_SHA,
                "row_number": 2,
                "key": "pcr_primers",
                "value": "MiFish",
            },
        ],
    }
    if supersedes_review_id:
        payload["supersedes_review_id"] = supersedes_review_id
    return payload


def test_permissions_separate_scientific_decisions_from_application():
    assert route_permission("POST", "/classification-reviews") == "classification:decide"
    assert route_permission("PUT", f"/classification-reviews/{uuid.uuid4()}/draft") == "classification:decide"
    assert route_permission("POST", f"/classification-reviews/{uuid.uuid4()}/decision") == "classification:decide"
    assert route_permission("POST", f"/classification-reviews/{uuid.uuid4()}/application") is None
    assert route_permission("POST", f"/classification-reviews/{uuid.uuid4()}/preview") == "classification:read"
    assert route_permission("GET", "/classification-reviews") == "classification:read"
    assert "classification:decide" in ROLE_PERMISSIONS["researcher"]
    assert "classification:decide" not in ROLE_PERMISSIONS["admin"]
    assert "classification:apply" in ROLE_PERMISSIONS["admin"]
    assert "classification:apply" not in ROLE_PERMISSIONS["researcher"]
    assert "classification:read" not in ROLE_PERMISSIONS["viewer"]
    assert all(
        not path.endswith("/application")
        for path in app.openapi()["paths"]
    )


def test_service_rejects_identity_that_does_not_match_persisted_user(monkeypatch):
    factory = _database()
    users = _seed(factory)
    _install_database(monkeypatch, factory)
    forged = replace(
        _current(users["researcher"]),
        email="forged@example.org",
    )

    response = _client(monkeypatch, forged).post(
        "/classification-reviews",
        json=_draft_payload(),
    )

    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "authenticated_role_required"


def test_authenticated_unknown_review_and_operational_application(monkeypatch):
    factory = _database()
    users = _seed(factory)
    _install_database(monkeypatch, factory)
    researcher = _client(monkeypatch, users["researcher"])

    editable_identity = {
        **_draft_payload(),
        "reviewer": "Forged reviewer",
        "reviewed_at": "2020-01-01T00:00:00Z",
    }
    assert researcher.post("/classification-reviews", json=editable_identity).status_code == 422

    created = researcher.post("/classification-reviews", json=_draft_payload())
    assert created.status_code == 201
    draft = created.json()
    assert draft["state"] == "draft"
    assert draft["sample_kind"] == "unknown"
    assert draft["version"] == 1
    assert len(draft["content_sha256"]) == 64
    assert {
        (row["source_file_id"], row["row_number"]): row
        for row in draft["evidence"]
    } == {
        (row["source_file_id"], row["row_number"]): row
        for row in _draft_payload()["evidence"]
    }
    assert draft["events"][0]["actor_user_id"] == str(users["researcher"].id)
    assert draft["events"][0]["actor_identity"]["email"] == "researcher@example.org"
    assert draft["scientific_decided_at"] is None

    admin = _client(monkeypatch, users["admin"])
    invalid_application = admin.post(
        f"/classification-reviews/{draft['id']}/application",
        json={
            "expected_version": 1,
            "outcome": "applied",
            "application_reference": "must-not-apply-a-draft",
        },
    )
    assert invalid_application.status_code == 403
    assert admin.post(
        f"/classification-reviews/{draft['id']}/decision",
        json={"expected_version": 1, "decision": "approved"},
    ).status_code == 403

    researcher = _client(monkeypatch, users["researcher"])
    approved = researcher.post(
        f"/classification-reviews/{draft['id']}/decision",
        json={"expected_version": 1, "decision": "approved"},
    )
    assert approved.status_code == 200
    decision = approved.json()
    assert decision["state"] == "approved"
    assert decision["scientific_decided_by_user_id"] == str(users["researcher"].id)
    assert decision["scientific_decided_at"]
    assert decision["events"][-1]["event_type"] == "approved"

    admin = _client(monkeypatch, users["admin"])
    assert admin.post("/classification-reviews", json=_draft_payload()).status_code == 403
    applied = admin.post(
        f"/classification-reviews/{draft['id']}/application",
        json={
            "expected_version": 2,
            "outcome": "applied",
            "application_reference": "classification-job/operation-123",
        },
    )
    assert applied.status_code == 403
    listed = admin.get(
        "/classification-reviews",
        params={"sample_id": SAMPLE_ID, "state": "approved"},
    )
    assert listed.status_code == 200
    assert listed.json()["total"] == 1
    assert listed.json()["items"][0]["id"] == draft["id"]

    researcher = _client(monkeypatch, users["researcher"])
    assert researcher.post(
        f"/classification-reviews/{draft['id']}/application",
        json={
            "expected_version": 2,
            "outcome": "applied",
            "application_reference": "forbidden",
        },
    ).status_code == 403

    viewer = _client(monkeypatch, users["viewer"])
    assert viewer.get(f"/classification-reviews/{draft['id']}").status_code == 403


def test_rejected_and_superseded_states(monkeypatch):
    factory = _database()
    users = _seed(factory)
    _install_database(monkeypatch, factory)
    researcher = _client(monkeypatch, users["researcher"])

    rejected_draft = researcher.post(
        "/classification-reviews",
        json=_draft_payload(sample_kind="environmental"),
    ).json()
    rejected = researcher.post(
        f"/classification-reviews/{rejected_draft['id']}/decision",
        json={"expected_version": 1, "decision": "rejected"},
    )
    assert rejected.status_code == 200
    assert rejected.json()["state"] == "rejected"

    current_draft = researcher.post(
        "/classification-reviews",
        json=_draft_payload(sample_kind="unknown"),
    ).json()
    approved = researcher.post(
        f"/classification-reviews/{current_draft['id']}/decision",
        json={"expected_version": 1, "decision": "approved"},
    ).json()
    researcher = _client(monkeypatch, users["researcher"])
    replacement = researcher.post(
        "/classification-reviews",
        json=_draft_payload(
            sample_kind="environmental",
            supersedes_review_id=approved["id"],
        ),
    ).json()
    replacement = researcher.post(
        f"/classification-reviews/{replacement['id']}/decision",
        json={"expected_version": 1, "decision": "approved"},
    )
    assert replacement.status_code == 200
    assert replacement.json()["state"] == "approved"
    previous = researcher.get(f"/classification-reviews/{approved['id']}")
    assert previous.status_code == 200
    assert previous.json()["state"] == "superseded"
    assert previous.json()["events"][-1]["event_type"] == "superseded"


def test_stale_snapshot_tamper_and_optimistic_concurrency_fail_closed(monkeypatch):
    factory = _database()
    users = _seed(factory)
    _install_database(monkeypatch, factory)
    client = _client(monkeypatch, users["researcher"])

    draft = client.post("/classification-reviews", json=_draft_payload()).json()
    changed = {**_draft_payload(), "expected_version": 1}
    changed.pop("source_snapshot_id")
    changed.pop("sample_id")
    response = client.put(
        f"/classification-reviews/{draft['id']}/draft",
        json=changed,
    )
    assert response.status_code == 200
    assert response.json()["version"] == 2
    stale = client.put(
        f"/classification-reviews/{draft['id']}/draft",
        json=changed,
    )
    assert stale.status_code == 409
    assert stale.json()["detail"]["code"] == "stale_review_version"

    with factory() as session:
        events = session.scalars(
            select(ClassificationReviewEvent)
            .where(ClassificationReviewEvent.review_id == uuid.UUID(draft["id"]))
            .order_by(ClassificationReviewEvent.sequence)
        ).all()
        assert [event.sequence for event in events] == [1, 2]
        events[0].details_json = {"tampered": True}
        with pytest.raises(ValueError, match="append-only"):
            session.flush()
        session.rollback()

    with factory() as session:
        event_id = session.scalar(
            select(ClassificationReviewEvent.id).where(
                ClassificationReviewEvent.review_id == uuid.UUID(draft["id"]),
                ClassificationReviewEvent.sequence == 1,
            )
        )
        session.execute(
            text(
                "UPDATE classification_review_event "
                "SET details_json = :details WHERE id = :event_id"
            ),
            {"details": '{"tampered":true}', "event_id": event_id.hex},
        )
        session.commit()
    tampered = client.get(f"/classification-reviews/{draft['id']}")
    assert tampered.status_code == 409
    assert tampered.json()["detail"]["code"] == "event_integrity_failed"

    clean = client.post("/classification-reviews", json=_draft_payload()).json()
    with factory() as session:
        sample = session.get(EdnaSample, SAMPLE_ID)
        sample.source_snapshot_id = OTHER_SNAPSHOT_ID
        sample.last_seen_snapshot_id = OTHER_SNAPSHOT_ID
        session.commit()
    stale_snapshot = client.post(
        f"/classification-reviews/{clean['id']}/decision",
        json={"expected_version": 1, "decision": "approved"},
    )
    assert stale_snapshot.status_code == 409
    assert stale_snapshot.json()["detail"]["code"] == "stale_source_snapshot"


@pytest.mark.parametrize(
    "lineage",
    ["{", "[]", '{"schema_version":1}'],
)
def test_draft_fails_closed_on_corrupt_canonical_lineage(monkeypatch, lineage):
    factory = _database()
    users = _seed(factory)
    _install_database(monkeypatch, factory)
    with factory() as session:
        sample = session.get(EdnaSample, SAMPLE_ID)
        sample.classification_basis = "review:" + "a" * 64
        sample.classification_review_json = lineage
        session.commit()

    response = _client(monkeypatch, users["researcher"]).post(
        "/classification-reviews",
        json=_draft_payload(sample_kind="environmental"),
    )

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "canonical_lineage_corrupt"


def test_review_row_tamper_is_detected(monkeypatch):
    factory = _database()
    users = _seed(factory)
    _install_database(monkeypatch, factory)
    client = _client(monkeypatch, users["researcher"])
    draft = client.post("/classification-reviews", json=_draft_payload()).json()

    with factory() as session:
        review = session.get(ClassificationReview, uuid.UUID(draft["id"]))
        review.rationale = "Tampered rationale"
        session.commit()

    response = client.get(f"/classification-reviews/{draft['id']}")
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "review_integrity_failed"


@pytest.mark.parametrize(
    ("field", "value", "code"),
    [
        ("source_sha256", "0" * 64, "evidence_source_mismatch"),
        ("row_number", 99, "evidence_row_mismatch"),
        ("value", "forged", "evidence_row_mismatch"),
    ],
)
def test_evidence_hash_row_and_value_must_match(
    monkeypatch,
    field,
    value,
    code,
):
    factory = _database()
    users = _seed(factory)
    _install_database(monkeypatch, factory)
    client = _client(monkeypatch, users["researcher"])
    payload = _draft_payload()
    payload["evidence"][0][field] = value

    response = client.post("/classification-reviews", json=payload)

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == code


def test_preview_compares_existing_analysis_without_writing(monkeypatch):
    factory = _database()
    users = _seed(factory)
    _install_database(monkeypatch, factory)
    researcher = _client(monkeypatch, users["researcher"])
    review = researcher.post(
        "/classification-reviews",
        json=_draft_payload(sample_kind="environmental"),
    ).json()
    request = {
        "expected_version": 1,
        "assignment_methods": [
            "qcauto_target",
            "qcauto_95pct_3nn_target",
        ],
        "rank": "genus",
        "min_read_count": 2,
        "top_taxa_limit": 1,
    }

    response = researcher.post(
        f"/classification-reviews/{review['id']}/preview",
        json=request,
    )

    assert response.status_code == 200
    preview = response.json()
    assert preview["review_id"] == review["id"]
    assert preview["review_version"] == 1
    assert preview["algorithm_version"] == "edna-descriptive-v1"
    assert preview["baseline"]["eligibility"] == "excluded"
    assert preview["baseline"]["exclusion_reasons"] == ["control_or_unknown"]
    assert preview["proposed"]["eligibility"] == "included"
    assert preview["eligibility_changed"] is True
    assert preview["table_count_delta"]["diversity"] == 2
    assert preview["table_count_delta"]["composition"] == 2
    assert len(preview["proposed"]["methods"]) == 2
    for method in preview["proposed"]["methods"]:
        assert method["source_detection_count"] == 2
        assert method["retained_detection_count"] == 1
        assert method["excluded_detection_count"] == 1
        assert method["source_reads"] == 4
        assert method["retained_reads"] == 3
        assert method["excluded_reads"] == 1
        assert method["richness"] == 1
        assert method["top_taxa"] == [
            {"taxon": "Beta", "read_count": 3, "read_proportion": 1.0}
        ]
    repeated = researcher.post(
        f"/classification-reviews/{review['id']}/preview",
        json=request,
    )
    assert repeated.status_code == 200
    assert repeated.json()["preview_sha256"] == preview["preview_sha256"]
    lower_threshold = researcher.post(
        f"/classification-reviews/{review['id']}/preview",
        json={**request, "min_read_count": 1},
    )
    assert lower_threshold.status_code == 200
    assert lower_threshold.json()["preview_sha256"] != preview["preview_sha256"]
    assert all(
        row["retained_detection_count"] == 2
        and row["richness"] == 2
        for row in lower_threshold.json()["proposed"]["methods"]
    )

    admin = _client(monkeypatch, users["admin"])
    assert admin.post(
        f"/classification-reviews/{review['id']}/preview",
        json=request,
    ).status_code == 200
    viewer = _client(monkeypatch, users["viewer"])
    assert viewer.post(
        f"/classification-reviews/{review['id']}/preview",
        json=request,
    ).status_code == 403

    with factory() as session:
        sample = session.get(EdnaSample, SAMPLE_ID)
        stored = session.get(ClassificationReview, uuid.UUID(review["id"]))
        events = session.scalars(
            select(ClassificationReviewEvent).where(
                ClassificationReviewEvent.review_id == stored.id
            )
        ).all()
        assert sample.sample_kind == "unknown"
        assert sample.is_control is None
        assert stored.state == "draft"
        assert stored.version == 1
        assert len(events) == 1


@pytest.mark.parametrize("sample_kind", ["unknown", "negative_control"])
def test_preview_keeps_unknown_and_controls_excluded(monkeypatch, sample_kind):
    factory = _database()
    users = _seed(factory)
    _install_database(monkeypatch, factory)
    client = _client(monkeypatch, users["researcher"])
    review = client.post(
        "/classification-reviews",
        json=_draft_payload(sample_kind=sample_kind),
    ).json()

    response = client.post(
        f"/classification-reviews/{review['id']}/preview",
        json={"expected_version": 1},
    )

    assert response.status_code == 200
    preview = response.json()
    assert preview["proposed"]["sample_kind"] == sample_kind
    assert preview["proposed"]["eligibility"] == "excluded"
    assert preview["eligibility_changed"] is False
    assert preview["proposed"]["table_counts"]["diversity"] == 0
    assert all(
        row["reason"] == "control_or_unknown"
        for row in preview["proposed"]["methods"]
    )


def test_preview_rejects_stale_terminal_and_unbounded_requests(monkeypatch):
    factory = _database()
    users = _seed(factory)
    _install_database(monkeypatch, factory)
    client = _client(monkeypatch, users["researcher"])
    review = client.post(
        "/classification-reviews",
        json=_draft_payload(sample_kind="environmental"),
    ).json()
    path = f"/classification-reviews/{review['id']}/preview"

    stale = client.post(path, json={"expected_version": 2})
    assert stale.status_code == 409
    assert stale.json()["detail"]["code"] == "stale_review_version"
    assert client.post(
        path,
        json={
            "expected_version": 1,
            "assignment_methods": ["qcauto_target", "qcauto_target"],
        },
    ).status_code == 422
    assert client.post(
        path,
        json={"expected_version": 1, "top_taxa_limit": 26},
    ).status_code == 422

    rejected = client.post(
        f"/classification-reviews/{review['id']}/decision",
        json={"expected_version": 1, "decision": "rejected"},
    )
    assert rejected.status_code == 200
    terminal = client.post(path, json={"expected_version": 2})
    assert terminal.status_code == 409
    assert terminal.json()["detail"]["code"] == "invalid_preview_state"

    approved_review = client.post(
        "/classification-reviews",
        json=_draft_payload(sample_kind="environmental"),
    ).json()
    approved = client.post(
        f"/classification-reviews/{approved_review['id']}/decision",
        json={"expected_version": 1, "decision": "approved"},
    )
    assert approved.status_code == 200
    approved_path = (
        f"/classification-reviews/{approved_review['id']}/preview"
    )
    assert client.post(
        approved_path,
        json={"expected_version": 2},
    ).status_code == 200

    admin = _client(monkeypatch, users["admin"])
    approved_preview = admin.post(
        approved_path,
        json={"expected_version": 2},
    )
    assert approved_preview.status_code == 200


def test_preview_resource_limit_fails_closed(monkeypatch):
    factory = _database()
    users = _seed(factory)
    _install_database(monkeypatch, factory)
    monkeypatch.setattr(
        "api.classification_review_service.PREVIEW_DETECTION_LIMIT",
        1,
    )
    client = _client(monkeypatch, users["researcher"])
    review = client.post(
        "/classification-reviews",
        json=_draft_payload(sample_kind="environmental"),
    ).json()

    response = client.post(
        f"/classification-reviews/{review['id']}/preview",
        json={"expected_version": 1},
    )

    assert response.status_code == 413
    assert response.json()["detail"]["code"] == "preview_resource_limit"


def test_preview_rejects_unverified_canonical_provenance(monkeypatch):
    factory = _database()
    users = _seed(factory)
    _install_database(monkeypatch, factory)
    client = _client(monkeypatch, users["researcher"])
    review = client.post(
        "/classification-reviews",
        json=_draft_payload(sample_kind="environmental"),
    ).json()
    with factory() as session:
        source = session.get(ExternalSourceFile, QC_FILE_ID)
        source.selection_status = "metadata_only"
        source.validation_status = "invalid"
        session.commit()

    response = client.post(
        f"/classification-reviews/{review['id']}/preview",
        json={"expected_version": 1},
    )

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "preview_provenance_unverified"


def test_database_prevents_competing_current_reviews():
    factory = _database()
    users = _seed(factory)
    decided_at = datetime.now(timezone.utc)

    def approved_review() -> ClassificationReview:
        return ClassificationReview(
            id=uuid.uuid4(),
            source_snapshot_id=SNAPSHOT_ID,
            sample_id=SAMPLE_ID,
            provider_sample_id=PROVIDER_SAMPLE_ID,
            sample_kind="unknown",
            rationale="Retain unknown because the evidence is inconclusive.",
            evidence_json=_draft_payload()["evidence"],
            content_sha256=uuid.uuid4().hex * 2,
            state="approved",
            version=2,
            created_by_user_id=users["researcher"].id,
            scientific_decided_by_user_id=users["researcher"].id,
            scientific_decided_at=decided_at,
        )

    with factory() as session:
        session.add(approved_review())
        session.commit()
        session.add(approved_review())
        with pytest.raises(IntegrityError):
            session.commit()
