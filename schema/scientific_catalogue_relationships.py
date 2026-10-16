"""C13 descriptive metadata and qualified, non-authorizing relationships.

These contracts retain evidence. A category or copied review flag is never an
identity decision; the pure validator checks supplied frozen source rows.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import Field, StringConstraints, field_validator, model_validator

from ingestion.immutable_bundle import canonical_bytes, digest
from preprocessing.research_recipe import EvidenceDecision
from schema.context_catalogue import (
    ContractModel,
    Identifier,
    LocalizedText,
    Provenance,
    Sha256,
    TextValue,
    _finite_json,
)

MAX_DEFINITION_BYTES = 64 * 1024
MAX_RELATIONSHIP_BYTES = 4 * 1024 * 1024
UUIDText = Annotated[
    str,
    StringConstraints(
        pattern=r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
    ),
]


def _bounded(value, limit):
    _finite_json(value)
    if len(canonical_bytes(value)) > limit:
        raise ValueError("Scientific metadata/evidence byte limit exceeded")
    return value


def _unique_inputs(value):
    if len(value) != len(set(value)):
        raise ValueError("Scientific input dataset identities must be distinct")
    return value


class Definition(ContractModel):
    id: Identifier
    title: LocalizedText
    purpose: LocalizedText
    category: Literal[
        "variable",
        "unit",
        "temporal_precision",
        "sampling",
        "assay",
        "method",
        "source_documentation",
        "publication_manifest",
    ]
    values: dict
    input_dataset_ids: list[Identifier] = Field(min_length=1, max_length=256)
    provenance: Provenance

    @field_validator("input_dataset_ids")
    @classmethod
    def unique_inputs(cls, value):
        return _unique_inputs(value)

    @field_validator("values")
    @classmethod
    def descriptive_values(cls, value):
        _bounded(value, MAX_DEFINITION_BYTES)

        def inspect(item):
            if isinstance(item, dict):
                if set(item) & {
                    "physical_sample_id",
                    "physical_sample_ids",
                    "physical_identity_verified",
                    "verified_physical_identity",
                    "comparison_authorized",
                    "approval_granted",
                }:
                    raise ValueError(
                        "Metadata definitions cannot assert identity or comparison authority"
                    )
                for child in item.values():
                    inspect(child)
            elif isinstance(item, (list, tuple)):
                for child in item:
                    inspect(child)

        inspect(value)
        return value


class DatasetEndpoint(ContractModel):
    dataset_id: Identifier
    entity_id: Identifier
    scientific_content_sha256: Sha256


class RegistryReview(ContractModel):
    review_id: UUIDText
    kind: Literal["sampling"]
    registry_key: str = Field(min_length=1, max_length=255)
    definition_json: dict
    state: Literal["applied"]
    version: Literal[3]
    content_sha256: Sha256
    created_by_user_id: UUIDText
    decided_by_user_id: UUIDText
    applied_by_user_id: UUIDText


class RegistryEvent(ContractModel):
    sequence: int = Field(strict=True, ge=1, le=3)
    event_sha256: Sha256
    payload_json: dict


class AppliedRegistryEvidence(ContractModel):
    physical_sample_id: Sha256
    registry_id: Sha256
    payload: dict
    review: RegistryReview
    events: list[RegistryEvent] = Field(min_length=3, max_length=3)


class ReviewedMatchingContent(ContractModel):
    schema_version: Literal["catalogue-reviewed-matching-v1"] = (
        "catalogue-reviewed-matching-v1"
    )
    relation: Literal["reviewed_matching"] = "reviewed_matching"
    endpoints: list[DatasetEndpoint] = Field(min_length=2, max_length=100)
    qualification: TextValue


class ReviewedMatchingEvidence(ContractModel):
    content: ReviewedMatchingContent
    decision: EvidenceDecision

    @model_validator(mode="after")
    def evidence_binding(self):
        if (
            digest(self.content.model_dump(mode="json"))
            != self.decision.evidence_sha256
        ):
            raise ValueError(
                "Reviewed matching decision must bind its exact retained content"
            )
        return self


class ProximityEvidence(ContractModel):
    kind: Literal["environmental_context"] = "environmental_context"
    profile_id: Identifier
    profile_sha256: Sha256
    source_reference: TextValue
    context_status: Literal["qualified", "candidate", "rejected", "unavailable"]
    measurement_type: Literal["ctd_bulk", "sst_skin", "sst_regional"]
    distance_km: float | None = Field(ge=0, le=40075)
    time_separation_min_hours: float | None = Field(ge=0)
    time_separation_max_hours: float | None = Field(ge=0)
    selected: bool = False

    @model_validator(mode="after")
    def qualified_context(self):
        lower, upper = self.time_separation_min_hours, self.time_separation_max_hours
        if (lower is None) != (upper is None) or (lower is not None and lower > upper):
            raise ValueError(
                "Context time separation requires ordered complete bounds or unknown bounds"
            )
        if self.context_status == "qualified" and (
            self.distance_km is None or lower is None
        ):
            raise ValueError(
                "Qualified context requires retained distance and time bounds"
            )
        if self.selected and self.context_status != "qualified":
            raise ValueError("Only qualified retained context may be selected")
        return self


class UnresolvedEvidence(ContractModel):
    reason: TextValue


EVIDENCE_MODELS = {
    "verified_physical_identity": AppliedRegistryEvidence,
    "reviewed_matching": ReviewedMatchingEvidence,
    "proximity": ProximityEvidence,
    "unresolved": UnresolvedEvidence,
}


class Relationship(ContractModel):
    id: Identifier
    title: LocalizedText
    purpose: LocalizedText
    category: Literal[
        "verified_physical_identity",
        "reviewed_matching",
        "proximity",
        "unresolved",
    ]
    input_dataset_ids: list[Identifier] = Field(min_length=1, max_length=256)
    endpoints: list[DatasetEndpoint] = Field(min_length=1, max_length=100)
    qualification: TextValue
    evidence: dict
    comparison_authorized: Literal[False] = False
    provenance: Provenance

    @field_validator("comparison_authorized", mode="before")
    @classmethod
    def no_comparison_authority(cls, value):
        if value is not False:
            raise ValueError(
                "Catalogue relationships cannot authorize scientific comparison"
            )
        return value

    @field_validator("input_dataset_ids")
    @classmethod
    def unique_inputs(cls, value):
        return _unique_inputs(value)

    @field_validator("evidence")
    @classmethod
    def bounded_evidence(cls, value):
        return _bounded(value, MAX_RELATIONSHIP_BYTES)

    @model_validator(mode="after")
    def relationship_binding(self):
        keys = [(item.dataset_id, item.entity_id) for item in self.endpoints]
        if len(set(keys)) != len(keys):
            raise ValueError(
                "Relationship endpoints must be distinct canonical entities"
            )
        if not {item.dataset_id for item in self.endpoints} <= set(
            self.input_dataset_ids
        ):
            raise ValueError(
                "Relationship endpoints must reference declared input datasets"
            )
        if (
            self.category in {"reviewed_matching", "proximity"}
            and len(self.endpoints) < 2
        ):
            raise ValueError("Qualified relationships require at least two endpoints")
        EVIDENCE_MODELS[self.category].model_validate(self.evidence)
        return self
