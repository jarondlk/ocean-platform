"""Pure C13 relationship verification against caller-supplied frozen inputs.

No registry head, database, publication pointer, source, or model is discovered.
Historical applied decisions remain historical evidence and never execute a
comparison or change classification/identity approvals.
"""

from __future__ import annotations

import math

import pandas as pd

from ingestion.immutable_bundle import digest
from preprocessing.research_recipe import SamplingRegistry
from schema.scientific_catalogue_relationships import (
    AppliedRegistryEvidence,
    ProximityEvidence,
    Relationship,
    ReviewedMatchingEvidence,
)

KEYS = {
    "casts": "cast_id",
    "depth_observations": "observation_id",
    "collections": "library_id",
    "run_qc": "run_id",
    "kraken_abundance": "measurement_id",
    "metaeuk_abundance": "measurement_id",
    "ranked_taxa": "summary_id",
    "observations": "observation_id",
    "occurrences": "sample_id",
    "assays": "assay_id",
    "detections": "detection_id",
}


def _primitive(value):
    if (
        value is pd.NA
        or value is None
        or isinstance(value, float)
        and math.isnan(value)
    ):
        return None
    if hasattr(value, "item"):
        value = value.item()
    return value


def _endpoint_row(data, entity_id):
    matches = []
    for role, key in KEYS.items():
        frame = data.tables.get(role)
        if frame is None or key not in frame:
            continue
        matches += [
            (role, {name: _primitive(value) for name, value in row.items()})
            for row in frame.loc[frame[key].eq(entity_id)].to_dict("records")
        ]
    if len(matches) != 1:
        raise ValueError(
            "Relationship endpoint must identify one retained canonical source row"
        )
    role, row = matches[0]
    if "active" in row and row["active"] is not True:
        raise ValueError("Relationship endpoint is not an active retained source row")
    return role, row


def endpoint_content_sha256(data, entity_id):
    """C12 scientific hash, or exact complete C10/C11 retained row digest."""
    _, row = _endpoint_row(data, entity_id)
    return row.get("scientific_content_sha256") or digest(row)


def _rows_by_id(datasets, declared):
    occurrences, assays = {}, {}
    for identity in declared:
        data = datasets[identity]
        if data.metadata.family != "edna_metabarcoding":
            continue
        for role, result, key in (
            ("occurrences", occurrences, "sample_id"),
            ("assays", assays, "assay_id"),
        ):
            frame = data.tables.get(role)
            if frame is None:
                continue
            for row in frame.to_dict("records"):
                row = {name: _primitive(value) for name, value in row.items()}
                if row[key] in result:
                    raise ValueError(
                        "Physical evidence has ambiguous canonical source entity ownership"
                    )
                result[row[key]] = (identity, row)
    return occurrences, assays


def _validate_applied_registry(proof):
    review = proof.review
    registry = SamplingRegistry.model_validate(review.definition_json)
    definition = registry.model_dump(mode="json")
    definition["areas"].sort(key=lambda item: item["area_id"])
    definition["memberships"].sort(key=lambda item: item["physical_sample_id"])
    content = {
        "kind": "sampling",
        "registry_key": "sampling:" + registry.region_id,
        "definition": definition,
    }
    if (
        review.registry_key != content["registry_key"]
        or review.definition_json != definition
        or digest(content) != review.content_sha256
    ):
        raise ValueError(
            "Physical registry review content or canonical definition digest is invalid"
        )
    previous = None
    for sequence, (event, kind, state, role, actor) in enumerate(
        zip(
            proof.events,
            ("created", "approved", "applied"),
            ("draft", "approved", "applied"),
            ("researcher", "researcher", "admin"),
            (
                review.created_by_user_id,
                review.decided_by_user_id,
                review.applied_by_user_id,
            ),
            strict=True,
        ),
        1,
    ):
        payload = event.payload_json
        identity = payload.get("actor", {})
        if not isinstance(identity, dict):
            raise ValueError("Physical registry event actor is invalid")
        if (
            event.sequence != sequence
            or payload.get("sequence") != sequence
            or type(payload.get("sequence")) is not int
            or payload.get("review_id") != review.review_id
            or payload.get("event_type") != kind
            or payload.get("state") != state
            or payload.get("content_sha256") != review.content_sha256
            or payload.get("previous_event_sha256") != previous
            or identity.get("user_id") != actor
            or identity.get("role") != role
            or digest(payload) != event.event_sha256
        ):
            raise ValueError(
                "Physical registry immutable approval/application event chain is invalid"
            )
        previous = event.event_sha256
    expected = {
        "schema_version": 1,
        **content,
        "review_id": review.review_id,
        "scientific_approval_sha256": proof.events[1].event_sha256,
    }
    if proof.payload != expected or digest(proof.payload) != proof.registry_id:
        raise ValueError(
            "Physical registry retained application/approval binding is invalid"
        )
    return registry


def _physical(relationship, datasets):
    proof = AppliedRegistryEvidence.model_validate(relationship.evidence)
    registry = _validate_applied_registry(proof)
    occurrences, assays = _rows_by_id(datasets, relationship.input_dataset_ids)
    selected = None
    for member in registry.memberships:
        for binding in member.occurrences:
            current = occurrences.get(binding.sample_id)
            if (
                current is None
                or current[1].get("active") is not True
                or current[1].get("scientific_content_sha256")
                != binding.scientific_content_sha256
            ):
                raise ValueError(
                    "Physical registry occurrence evidence is absent, inactive, or stale"
                )
        assay = assays.get(member.representative_assay_id)
        if (
            assay is None
            or assay[1].get("active") is not True
            or assay[1].get("scientific_content_sha256")
            != member.representative_assay_sha256
            or assay[1].get("sample_id")
            not in {item.sample_id for item in member.occurrences}
        ):
            raise ValueError(
                "Physical registry representative assay evidence is absent, inactive, or stale"
            )
        if member.physical_sample_id == proof.physical_sample_id:
            selected = member
    if selected is None:
        raise ValueError(
            "Physical relationship selects no retained reviewed membership"
        )
    expected = {
        (occurrences[item.sample_id][0], item.sample_id, item.scientific_content_sha256)
        for item in selected.occurrences
    }
    actual = {
        (item.dataset_id, item.entity_id, item.scientific_content_sha256)
        for item in relationship.endpoints
    }
    if expected != actual:
        raise ValueError(
            "Physical relationship endpoints must exactly bind its reviewed occurrence membership"
        )
    return {
        "validation_status": "verified_retained_registry",
        "registry_id": proof.registry_id,
        "physical_sample_id": selected.physical_sample_id,
        "source_occurrences": len(selected.occurrences),
        "representative_assay_id": selected.representative_assay_id,
        "area_id": selected.area_id,
        "area_version": selected.area_version,
        "scientific_approval_sha256": proof.events[1].event_sha256,
        "classification_approval": "independent_not_granted",
    }


def validate_relationship(relationship, datasets):
    """Return explicit qualifications, or reject unverifiable frozen claims."""
    if isinstance(relationship, Relationship):
        relationship = relationship.model_dump(mode="json")
    relationship = Relationship.model_validate(relationship)
    if not set(relationship.input_dataset_ids) <= set(datasets):
        raise ValueError("Relationship input datasets are unavailable")
    for endpoint in relationship.endpoints:
        data = datasets[endpoint.dataset_id]
        if (
            data.metadata.dataset_id != endpoint.dataset_id
            or endpoint_content_sha256(data, endpoint.entity_id)
            != endpoint.scientific_content_sha256
        ):
            raise ValueError(
                "Relationship endpoint source ownership or scientific content hash is stale"
            )
    result = {
        "category": relationship.category,
        "qualification": relationship.qualification,
        "comparison_authorized": False,
        "input_dataset_ids": relationship.input_dataset_ids,
    }
    if relationship.category == "verified_physical_identity":
        result.update(_physical(relationship, datasets))
    elif relationship.category == "reviewed_matching":
        proof = ReviewedMatchingEvidence.model_validate(relationship.evidence)
        if (
            proof.content.endpoints != relationship.endpoints
            or proof.content.qualification != relationship.qualification
        ):
            raise ValueError(
                "Reviewed matching content must bind exact ordered endpoints and qualification"
            )
        result.update(
            validation_status="reviewed_retained_matching",
            reviewer=proof.decision.reviewer,
            decision_evidence_sha256=proof.decision.evidence_sha256,
            physical_identity="not_established",
        )
    elif relationship.category == "proximity":
        proof = ProximityEvidence.model_validate(relationship.evidence)
        expected_environment = (
            ("ctd", "depth_observations")
            if proof.measurement_type == "ctd_bulk"
            else ("remote_sensing", "observations")
        )
        actual_endpoints = []
        for endpoint in relationship.endpoints:
            data = datasets[endpoint.dataset_id]
            role, _ = _endpoint_row(data, endpoint.entity_id)
            actual_endpoints.append((data.metadata.family, role))
        if sorted(actual_endpoints) != sorted(
            [("edna_metabarcoding", "occurrences"), expected_environment]
        ):
            raise ValueError(
                "Environmental proximity must bind one eDNA occurrence and one compatible retained CTD/SST observation"
            )
        result.update(
            validation_status="retained_environmental_context",
            context_status=proof.context_status,
            measurement_type=proof.measurement_type,
            profile_id=proof.profile_id,
            profile_sha256=proof.profile_sha256,
            physical_identity="not_established",
            scientific_approval="not_granted",
        )
    else:
        result.update(
            validation_status="unresolved",
            physical_identity="not_established",
            scientific_approval="not_granted",
            reason=relationship.evidence["reason"],
        )
    return result
