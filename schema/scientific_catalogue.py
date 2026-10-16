"""C13 frozen scientific index; the CTD carrier is transport, never evidence."""

from __future__ import annotations

from typing import Literal

from pydantic import Field, JsonValue, field_validator, model_validator

from retrieval.source_scope import EvidenceScope
from schema.context_catalogue import (
    Availability,
    ContractModel,
    Identifier,
    LocalizedText,
    NonnegativeInt,
    Provenance,
    QueryResult,
    ResultColumn,
    Sha256,
    SourceFamily,
    TextValue,
    _finite_json,
    _strict_scope,
)
from schema.scientific_catalogue_relationships import Definition, Relationship

DATASET_VERSION = "catalogue-scientific-registry-v1"
TABLE_VERSION = "catalogue-scientific-table-v1"
ADAPTER_VERSION = "c13-v1"
INDEX_OBJECT_ID = "scientific:registry"
INDEX_DATASET_ID = "scientific:index"
INDEX_SOURCE_ID = "scientific:registry"
TRANSPORT_QUALIFICATION = (
    "The CTD source family is an immutable index storage carrier only; it does "
    "not assert CTD measurements, a raw dataset, or scientific source eligibility."
)


class DatasetBinding(ContractModel):
    dataset_id: Identifier
    source_family: SourceFamily
    source_id: Identifier
    snapshot_id: Sha256


class ScientificTable(ContractModel):
    name: Identifier
    object_id: Identifier | None
    columns: list[ResultColumn] = Field(min_length=1, max_length=256)
    row_count: NonnegativeInt | None
    availability: Availability
    completeness: Literal["complete", "partial", "unknown", "unavailable"]

    @model_validator(mode="after")
    def binding(self):
        if len({c.key for c in self.columns}) != len(self.columns):
            raise ValueError("Scientific table columns must have distinct identities")
        if self.object_id is None:
            if self.row_count is not None or self.availability.status == "available":
                raise ValueError("Absent scientific tables cannot claim a known count")
            if self.completeness != self.availability.status:
                raise ValueError(
                    "Absent table availability and completeness must agree"
                )
        elif (
            self.row_count is None
            or self.availability.status != "available"
            or self.completeness == "unavailable"
        ):
            raise ValueError(
                "Retained scientific tables require availability and count"
            )
        return self


class PublishedAnalysis(ContractModel):
    id: Identifier
    title: LocalizedText
    purpose: LocalizedText
    input_dataset_ids: list[Identifier] = Field(min_length=1, max_length=4000)
    method_id: Identifier
    method_version: Identifier
    scope: EvidenceScope
    publication_status: Literal[
        "published", "unpublished", "historical", "experimental"
    ]
    approval_basis: TextValue
    # C13 retains operational publications. Independent review/endorsement
    # integration requires a later explicit, verifiable authority contract.
    independent_researcher_approval: Literal[False] = False
    provider_endorsement: Literal[False] = False
    availability: Availability
    tables: list[ScientificTable] = Field(min_length=1, max_length=256)
    limitations: list[TextValue] = Field(min_length=1, max_length=256)
    provenance: Provenance
    scope_option: dict[str, JsonValue] | None = None
    derived_receipt: dict[str, JsonValue] | None = None

    @field_validator(
        "independent_researcher_approval", "provider_endorsement", mode="before"
    )
    @classmethod
    def no_unverified_authority(cls, value):
        if value is not False:
            raise ValueError(
                "Operational publication cannot grant independent approval or provider endorsement"
            )
        return value

    @field_validator("scope", mode="before")
    @classmethod
    def strict_scope(cls, value):
        return _strict_scope(value)

    @field_validator("scope_option", "derived_receipt", mode="before")
    @classmethod
    def finite_metadata(cls, value):
        return _finite_json(value)

    @model_validator(mode="after")
    def semantics(self):
        if len(set(self.input_dataset_ids)) != len(self.input_dataset_ids):
            raise ValueError("Analysis input datasets must be unique")
        if len({t.name for t in self.tables}) != len(self.tables):
            raise ValueError("Analysis table names must be unique")
        if (
            self.scope_option is not None
            and self.scope_option.get("analysis_id") != self.id
        ):
            raise ValueError("Publication scope option must bind the analysis identity")
        if self.approval_basis == "explicit_user_accepted_operational_publication" and (
            self.independent_researcher_approval or self.provider_endorsement
        ):
            raise ValueError(
                "Operational publication cannot grant independent approval"
            )
        return self


class Workflow(ContractModel):
    id: Identifier
    title: LocalizedText
    purpose: LocalizedText
    workflow_kind: Identifier
    required_sources: list[SourceFamily] = Field(min_length=1, max_length=4)
    availability: Availability
    input_dataset_ids: list[Identifier] = Field(default_factory=list, max_length=4000)
    analysis_ids: list[Identifier] = Field(default_factory=list, max_length=4000)
    limitations: list[TextValue] = Field(min_length=1, max_length=256)
    provenance: Provenance

    @model_validator(mode="after")
    def unique(self):
        for name in ("required_sources", "input_dataset_ids", "analysis_ids"):
            values = getattr(self, name)
            if len(values) != len(set(values)):
                raise ValueError("Workflow links and required sources must be unique")
        return self


class ScientificRegistry(ContractModel):
    schema_version: Literal["catalogue-scientific-registry-v1"] = DATASET_VERSION
    qualification: Literal[TRANSPORT_QUALIFICATION] = TRANSPORT_QUALIFICATION
    datasets: list[DatasetBinding] = Field(min_length=1, max_length=4000)
    analyses: list[PublishedAnalysis] = Field(default_factory=list, max_length=4000)
    workflows: list[Workflow] = Field(default_factory=list, max_length=4000)
    definitions: list[Definition] = Field(default_factory=list, max_length=4000)
    relationships: list[Relationship] = Field(default_factory=list, max_length=4000)
    superseded_generations: list[Sha256] = Field(default_factory=list, max_length=4000)

    @model_validator(mode="after")
    def identity_and_links(self):
        dataset_ids = {d.dataset_id for d in self.datasets}
        if len(dataset_ids) != len(self.datasets):
            raise ValueError("Frozen dataset bindings must have unique canonical IDs")
        scientific = [
            *self.analyses,
            *self.workflows,
            *self.definitions,
            *self.relationships,
        ]
        identities = [*dataset_ids, *(o.id for o in scientific)]
        identities.extend(
            t.object_id
            for a in self.analyses
            for t in a.tables
            if t.object_id is not None
        )
        if len(identities) != len(set(identities)) or any(
            value in {INDEX_OBJECT_ID, INDEX_DATASET_ID}
            or value.startswith(("root:", "c13:"))
            for value in identities
        ):
            raise ValueError("Scientific canonical IDs must be unique and nonreserved")
        analyses = {a.id for a in self.analyses}
        families = {d.dataset_id: d.source_family for d in self.datasets}
        for item in scientific:
            if not set(item.input_dataset_ids) <= dataset_ids:
                raise ValueError(
                    "Scientific object references an unbound input dataset"
                )
        for analysis in self.analyses:
            enabled = {
                family
                for family in (
                    "ctd",
                    "metagenome",
                    "remote_sensing",
                    "edna_metabarcoding",
                )
                if getattr(analysis.scope.sources, family).enabled
            }
            if enabled != {families[d] for d in analysis.input_dataset_ids}:
                raise ValueError(
                    "Analysis scope must enable exactly its declared input source families"
                )
            if analysis.scope.sources.edna_metabarcoding.analysis_id not in {
                None,
                analysis.id,
            }:
                raise ValueError("Analysis scope cannot bind a different publication")
        for workflow in self.workflows:
            if not set(workflow.analysis_ids) <= analyses:
                raise ValueError("Workflow references an unbound analysis")
            if not {families[d] for d in workflow.input_dataset_ids} <= set(
                workflow.required_sources
            ):
                raise ValueError("Workflow required sources must cover its inputs")
        if len(set(self.superseded_generations)) != len(self.superseded_generations):
            raise ValueError("Superseded generation tombstones must be unique")
        return self


class ScientificResponse(QueryResult):
    adapter_version: Literal["c13-v1"] = ADAPTER_VERSION
    offset: NonnegativeInt = 0
    next_offset: NonnegativeInt | None = None
    qualifications: list[TextValue] = Field(default_factory=list)
