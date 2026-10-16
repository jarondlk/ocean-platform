"""Synthetic C13 relationship evidence: no database, provider, or approval writes."""

from copy import deepcopy
from types import SimpleNamespace

import pandas as pd
import pytest

from ingestion.immutable_bundle import digest
from preprocessing.scientific_catalogue_relationships import (
    endpoint_content_sha256,
    validate_relationship,
)
from schema.catalogue_adapter_fixtures import ctd_fixture
from schema.edna_catalogue_fixtures import edna_fixture
from schema.scientific_catalogue_relationships import Definition, Relationship


def relationship_fixture(category="unresolved"):
    metadata, frames = edna_fixture(3)
    data = SimpleNamespace(metadata=metadata, tables=frames, objects=())
    datasets = {metadata.dataset_id: data}
    endpoints = [
        dict(
            dataset_id=metadata.dataset_id,
            entity_id=row.sample_id,
            scientific_content_sha256=row.scientific_content_sha256,
        )
        for row in frames["occurrences"].iloc[:2].itertuples()
    ]
    qualification = "Synthetic frozen relationship; no scientific comparison authorized"
    evidence = {"reason": "Physical identity is unresolved"}
    if category == "proximity":
        ctd_metadata, ctd_frames = ctd_fixture(1)
        ctd = SimpleNamespace(metadata=ctd_metadata, tables=ctd_frames, objects=())
        datasets[ctd_metadata.dataset_id] = ctd
        observation = ctd_frames["depth_observations"].iloc[0].observation_id
        endpoints[1] = dict(
            dataset_id=ctd_metadata.dataset_id,
            entity_id=observation,
            scientific_content_sha256=endpoint_content_sha256(ctd, observation),
        )
        evidence = dict(
            kind="environmental_context",
            profile_id="synthetic-profile",
            profile_sha256=digest("synthetic profile"),
            source_reference="fixture://context",
            context_status="candidate",
            measurement_type="ctd_bulk",
            distance_km=0.1,
            time_separation_min_hours=0.0,
            time_separation_max_hours=24.0,
            selected=False,
        )
    elif category == "reviewed_matching":
        content = dict(
            schema_version="catalogue-reviewed-matching-v1",
            relation="reviewed_matching",
            endpoints=endpoints,
            qualification=qualification,
        )
        evidence = dict(
            content=content,
            decision=dict(
                reviewer="synthetic reviewer",
                rationale="Synthetic retained matching decision",
                references=["fixture://matching"],
                evidence_sha256=digest(content),
            ),
        )
    result = dict(
        id="synthetic:relationship",
        title=dict(en="Synthetic relationship", ja="合成関係"),
        purpose=dict(en="Retained evidence only", ja="保持された証拠のみ"),
        category=category,
        input_dataset_ids=list(datasets),
        endpoints=endpoints,
        qualification=qualification,
        evidence=evidence,
        comparison_authorized=False,
        provenance=dict(references=["fixture://relationship"]),
    )
    return result, datasets


def physical_relationship_fixture():
    """Produce a full synthetic applied review chain without invoking review APIs."""
    relationship, datasets = relationship_fixture()
    data = next(iter(datasets.values()))
    occurrences = data.tables["occurrences"].iloc[:2].to_dict("records")
    assay = data.tables["assays"].iloc[0].to_dict()
    decision = dict(
        reviewer="synthetic researcher",
        rationale="Synthetic identity and area evidence",
        references=["fixture://identity"],
        evidence_sha256=digest("external synthetic evidence"),
    )
    area = dict(
        area_id="synthetic-area",
        region_id="synthetic-region",
        label="Synthetic area",
        geometry_type="reviewed_cell_footprint",
        west=141.0,
        east=142.0,
        south=38.0,
        north=39.0,
        coordinate_uncertainty_km=0.5,
        decision=decision,
    )
    member = dict(
        physical_sample_id=digest("synthetic physical sample"),
        occurrences=[
            dict(
                sample_id=row["sample_id"],
                scientific_content_sha256=row["scientific_content_sha256"],
            )
            for row in occurrences
        ],
        representative_assay_id=assay["assay_id"],
        representative_assay_sha256=assay["scientific_content_sha256"],
        area_id=area["area_id"],
        area_version=digest(area),
        decision=decision,
        representative_policy="reviewed_original_assay",
    )
    definition = dict(
        schema_version=1,
        region_id="synthetic-region",
        areas=[area],
        memberships=[member],
    )
    content = dict(
        kind="sampling", registry_key="sampling:synthetic-region", definition=definition
    )
    review_id = "00000000-0000-4000-8000-000000000001"
    review = dict(
        review_id=review_id,
        kind="sampling",
        registry_key=content["registry_key"],
        definition_json=definition,
        state="applied",
        version=3,
        content_sha256=digest(content),
        created_by_user_id="00000000-0000-4000-8000-000000000002",
        decided_by_user_id="00000000-0000-4000-8000-000000000002",
        applied_by_user_id="00000000-0000-4000-8000-000000000003",
    )
    events = []
    previous = None
    for sequence, (event_type, state, role, actor) in enumerate(
        zip(
            ("created", "approved", "applied"),
            ("draft", "approved", "applied"),
            ("researcher", "researcher", "admin"),
            (
                "00000000-0000-4000-8000-000000000002",
                "00000000-0000-4000-8000-000000000002",
                "00000000-0000-4000-8000-000000000003",
            ),
            strict=True,
        ),
        1,
    ):
        payload = dict(
            review_id=review_id,
            sequence=sequence,
            event_type=event_type,
            state=state,
            actor=dict(user_id=actor, role=role),
            content_sha256=review["content_sha256"],
            previous_event_sha256=previous,
            at=f"2026-10-16T00:00:0{sequence}+00:00",
            details={"synthetic": True},
        )
        event = dict(
            sequence=sequence, event_sha256=digest(payload), payload_json=payload
        )
        events.append(event)
        previous = event["event_sha256"]
    payload = dict(
        schema_version=1,
        **content,
        review_id=review_id,
        scientific_approval_sha256=events[1]["event_sha256"],
    )
    relationship.update(
        category="verified_physical_identity",
        evidence=dict(
            physical_sample_id=member["physical_sample_id"],
            registry_id=digest(payload),
            payload=payload,
            review=review,
            events=events,
        ),
    )
    return relationship, datasets


def test_unresolved_retains_source_identity_without_approval():
    relationship, datasets = relationship_fixture()
    result = validate_relationship(relationship, datasets)
    assert result["validation_status"] == "unresolved"
    assert result["comparison_authorized"] is False
    assert result["physical_identity"] == "not_established"


@pytest.mark.parametrize("category", ["reviewed_matching", "proximity"])
def test_matching_and_proximity_are_context_not_physical_identity(category):
    relationship, datasets = relationship_fixture(category)
    result = validate_relationship(relationship, datasets)
    assert result["physical_identity"] == "not_established"
    assert result["comparison_authorized"] is False


def test_physical_identity_verifies_full_ledger_without_changing_classification():
    relationship, datasets = physical_relationship_fixture()
    original = deepcopy(relationship)
    classifications = (
        next(iter(datasets.values())).tables["classifications"].copy(deep=True)
    )
    result = validate_relationship(relationship, datasets)
    assert result["validation_status"] == "verified_retained_registry"
    assert result["source_occurrences"] == 2
    assert result["classification_approval"] == "independent_not_granted"
    assert result["comparison_authorized"] is False
    assert relationship == original
    pd.testing.assert_frame_equal(
        classifications, next(iter(datasets.values())).tables["classifications"]
    )
    assert (
        next(iter(datasets.values()))
        .tables["occurrences"]
        .physical_sample_id.isna()
        .all()
    )


@pytest.mark.parametrize(
    "path,value",
    [
        (("evidence", "registry_id"), "a" * 64),
        (("evidence", "physical_sample_id"), "a" * 64),
        (("evidence", "payload", "scientific_approval_sha256"), "a" * 64),
        (("evidence", "review", "state"), "approved"),
        (("evidence", "review", "version"), 2),
        (("evidence", "review", "content_sha256"), "a" * 64),
        (("evidence", "review", "registry_key"), "sampling:other"),
        (("evidence", "review", "decided_by_user_id"), "different-researcher"),
        (("evidence", "events", 1, "event_sha256"), "a" * 64),
        (("evidence", "events", 1, "payload_json", "event_type"), "rejected"),
        (("evidence", "events", 1, "payload_json", "sequence"), True),
        (("evidence", "events", 1, "payload_json", "actor"), "not-an-actor"),
        (("evidence", "events", 2, "payload_json", "actor", "role"), "researcher"),
        (("evidence", "events", 2, "payload_json", "previous_event_sha256"), None),
        (
            ("evidence", "review", "definition_json", "memberships", 0, "area_version"),
            "a" * 64,
        ),
    ],
)
def test_physical_proof_rejects_changed_or_unapplied_claim(path, value):
    relationship, datasets = physical_relationship_fixture()
    target = relationship
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    with pytest.raises(ValueError):
        validate_relationship(relationship, datasets)


@pytest.mark.parametrize(
    "role,field,value",
    [
        ("occurrences", "scientific_content_sha256", "a" * 64),
        ("occurrences", "active", False),
        ("assays", "scientific_content_sha256", "a" * 64),
        ("assays", "active", False),
        ("assays", "sample_id", "a" * 64),
    ],
)
def test_physical_registry_rejects_stale_current_evidence(role, field, value):
    relationship, datasets = physical_relationship_fixture()
    next(iter(datasets.values())).tables[role].at[0, field] = value
    with pytest.raises(ValueError):
        validate_relationship(relationship, datasets)


def test_physical_membership_cannot_drop_endpoint_or_bind_sibling_occurrence():
    relationship, datasets = physical_relationship_fixture()
    relationship["endpoints"].pop()
    with pytest.raises(ValueError, match="exactly bind"):
        validate_relationship(relationship, datasets)


def test_physical_single_occurrence_membership_is_not_replicate_inference():
    relationship, datasets = physical_relationship_fixture()
    # A second source occurrence is not required to establish one reviewed sample;
    # preserve a fully re-bound synthetic ledger with only that occurrence.
    proof = relationship["evidence"]
    proof["review"]["definition_json"]["memberships"][0]["occurrences"].pop()
    relationship["endpoints"].pop()
    content = dict(
        kind="sampling",
        registry_key=proof["review"]["registry_key"],
        definition=proof["review"]["definition_json"],
    )
    proof["review"]["content_sha256"] = digest(content)
    previous = None
    for event in proof["events"]:
        event["payload_json"].update(
            content_sha256=proof["review"]["content_sha256"],
            previous_event_sha256=previous,
        )
        event["event_sha256"] = digest(event["payload_json"])
        previous = event["event_sha256"]
    proof["payload"] = dict(
        schema_version=1,
        **content,
        review_id=proof["review"]["review_id"],
        scientific_approval_sha256=proof["events"][1]["event_sha256"],
    )
    proof["registry_id"] = digest(proof["payload"])
    assert validate_relationship(relationship, datasets)["source_occurrences"] == 1


@pytest.mark.parametrize(
    "field,value",
    [
        ("comparison_authorized", True),
        ("comparison_authorized", 0),
        ("input_dataset_ids", []),
        ("input_dataset_ids", ["synthetic:edna:project-a"] * 2),
    ],
)
def test_relationship_contract_rejects_authority_or_identity_shortcuts(field, value):
    relationship, _ = relationship_fixture()
    relationship[field] = value
    with pytest.raises(ValueError):
        Relationship.model_validate(relationship)


@pytest.mark.parametrize(
    "change",
    [
        "unknown_dataset",
        "unknown_entity",
        "wrong_hash",
        "duplicate_endpoint",
        "missing_declared_dataset",
    ],
)
def test_endpoint_integrity_is_checked_for_even_unresolved_links(change):
    relationship, datasets = relationship_fixture()
    if change == "unknown_dataset":
        relationship["endpoints"][0]["dataset_id"] = "missing:dataset"
    elif change == "unknown_entity":
        relationship["endpoints"][0]["entity_id"] = "missing:entity"
    elif change == "wrong_hash":
        relationship["endpoints"][0]["scientific_content_sha256"] = "a" * 64
    elif change == "duplicate_endpoint":
        relationship["endpoints"].append(deepcopy(relationship["endpoints"][0]))
    else:
        relationship["input_dataset_ids"].append("missing:dataset")
    with pytest.raises(ValueError):
        validate_relationship(relationship, datasets)


@pytest.mark.parametrize(
    "change",
    ["decision_hash", "endpoint_order", "qualification", "extra_identity_claim"],
)
def test_matching_review_binds_exact_content(change):
    relationship, datasets = relationship_fixture("reviewed_matching")
    if change == "decision_hash":
        relationship["evidence"]["decision"]["evidence_sha256"] = "a" * 64
    elif change == "endpoint_order":
        relationship["endpoints"].reverse()
    elif change == "qualification":
        relationship["qualification"] = "Changed qualification"
    else:
        relationship["evidence"]["physical_sample_id"] = "a" * 64
    with pytest.raises(ValueError):
        validate_relationship(relationship, datasets)


@pytest.mark.parametrize(
    "updates",
    [
        {"context_status": "qualified", "distance_km": None},
        {
            "context_status": "qualified",
            "time_separation_min_hours": None,
            "time_separation_max_hours": None,
        },
        {"selected": True},
        {"distance_km": -0.1},
        {"time_separation_min_hours": 30.0},
        {"time_separation_max_hours": None},
        {"physical_sample_id": "a" * 64},
    ],
)
def test_proximity_contract_preserves_unknown_context_and_no_identity(updates):
    relationship, _ = relationship_fixture("proximity")
    relationship["evidence"].update(updates)
    with pytest.raises(ValueError):
        Relationship.model_validate(relationship)


def test_qualified_context_still_does_not_approve_comparison():
    relationship, datasets = relationship_fixture("proximity")
    relationship["evidence"].update(context_status="qualified", selected=True)
    result = validate_relationship(relationship, datasets)
    assert result["scientific_approval"] == "not_granted"
    assert result["comparison_authorized"] is False


@pytest.mark.parametrize(
    "change", ["wrong_measurement_family", "dna_pair", "cast_instead_of_observation"]
)
def test_proximity_binds_actual_environmental_source_and_observation_type(change):
    relationship, datasets = relationship_fixture("proximity")
    if change == "wrong_measurement_family":
        relationship["evidence"]["measurement_type"] = "sst_regional"
    elif change == "dna_pair":
        data = next(
            data
            for data in datasets.values()
            if data.metadata.family == "edna_metabarcoding"
        )
        row = data.tables["occurrences"].iloc[1]
        relationship["endpoints"][1] = dict(
            dataset_id=data.metadata.dataset_id,
            entity_id=row.sample_id,
            scientific_content_sha256=row.scientific_content_sha256,
        )
    else:
        data = next(data for data in datasets.values() if data.metadata.family == "ctd")
        entity = data.tables["casts"].iloc[0].cast_id
        relationship["endpoints"][1].update(
            entity_id=entity,
            scientific_content_sha256=endpoint_content_sha256(data, entity),
        )
    with pytest.raises(ValueError, match="compatible retained"):
        validate_relationship(relationship, datasets)


def test_physical_review_ids_are_database_uuid_identities():
    relationship, datasets = physical_relationship_fixture()
    relationship["evidence"]["review"]["review_id"] = "self-declared-review"
    with pytest.raises(ValueError):
        validate_relationship(relationship, datasets)


def test_physical_registry_requires_every_retained_registry_binding_current():
    relationship, datasets = physical_relationship_fixture()
    data = next(iter(datasets.values()))
    data.tables["occurrences"] = data.tables["occurrences"].iloc[:1].copy()
    relationship["endpoints"] = relationship["endpoints"][:1]
    with pytest.raises(ValueError, match="occurrence evidence"):
        validate_relationship(relationship, datasets)


def test_physical_registry_rejects_ambiguous_entity_ownership_across_datasets():
    relationship, datasets = physical_relationship_fixture()
    data = next(iter(datasets.values()))
    clone = SimpleNamespace(
        metadata=data.metadata.model_copy(
            update={"dataset_id": "synthetic:duplicate-owner"}
        ),
        tables={role: frame.copy(deep=True) for role, frame in data.tables.items()},
        objects=(),
    )
    datasets[clone.metadata.dataset_id] = clone
    relationship["input_dataset_ids"].append(clone.metadata.dataset_id)
    with pytest.raises(ValueError, match="ambiguous"):
        validate_relationship(relationship, datasets)


def test_qualified_sst_context_uses_retained_sst_observation_without_approval():
    from schema.sst_catalogue_fixtures import sst_fixture

    relationship, datasets = relationship_fixture("proximity")
    metadata, frames = sst_fixture(1)
    data = SimpleNamespace(metadata=metadata, tables=frames, objects=())
    datasets = {
        identity: value
        for identity, value in datasets.items()
        if value.metadata.family != "ctd"
    }
    datasets[metadata.dataset_id] = data
    entity = frames["observations"].iloc[0].observation_id
    relationship["input_dataset_ids"] = list(datasets)
    relationship["endpoints"][1] = dict(
        dataset_id=metadata.dataset_id,
        entity_id=entity,
        scientific_content_sha256=endpoint_content_sha256(data, entity),
    )
    relationship["evidence"].update(
        measurement_type="sst_regional", context_status="qualified", selected=True
    )
    result = validate_relationship(relationship, datasets)
    assert result["measurement_type"] == "sst_regional"
    assert result["physical_identity"] == "not_established"


def test_c10_endpoint_digest_binds_complete_row_and_dataset_owner():
    metadata, frames = ctd_fixture(2)
    data = SimpleNamespace(metadata=metadata, tables=frames, objects=())
    entity = frames["depth_observations"].iloc[0].observation_id
    first = endpoint_content_sha256(data, entity)
    frames["depth_observations"].at[0, "temperature"] = 123.0
    assert endpoint_content_sha256(data, entity) != first
    with pytest.raises(ValueError, match="one retained"):
        endpoint_content_sha256(data, "shared-label")


def definition_fixture():
    return dict(
        id="synthetic:definition",
        title=dict(en="Temperature", ja="水温"),
        purpose=dict(en="Retained variable definition", ja="保持された変数定義"),
        category="variable",
        values=dict(
            variable="temperature",
            unit="degC",
            temporal_precision="day",
            missing=None,
            zero=0,
        ),
        input_dataset_ids=["synthetic:ctd:campaign-a"],
        provenance=dict(references=["fixture://documentation"]),
    )


def test_metadata_preserves_zero_missing_units_precision_and_documentation():
    result = Definition.model_validate(definition_fixture())
    assert result.values["zero"] == 0 and result.values["missing"] is None
    assert result.values["unit"] == "degC"


@pytest.mark.parametrize(
    "claim",
    [
        "physical_sample_id",
        "physical_sample_ids",
        "physical_identity_verified",
        "verified_physical_identity",
        "comparison_authorized",
        "approval_granted",
    ],
)
def test_metadata_cannot_assert_physical_or_comparison_authority(claim):
    value = definition_fixture()
    value["values"]["nested"] = {claim: True}
    with pytest.raises(ValueError, match="cannot assert"):
        Definition.model_validate(value)


@pytest.mark.parametrize(
    "values",
    [
        {"temperature": float("nan")},
        {"temperature": float("inf")},
        {"text": "x" * 65536},
    ],
)
def test_metadata_is_finite_bounded_json(values):
    value = definition_fixture()
    value["values"] = values
    with pytest.raises(ValueError):
        Definition.model_validate(value)


def test_mutated_prevalidated_relationship_is_revalidated():
    relationship, datasets = relationship_fixture()
    model = Relationship.model_validate(relationship)
    model.evidence["reason"] = ""
    with pytest.raises(ValueError):
        validate_relationship(model, datasets)
