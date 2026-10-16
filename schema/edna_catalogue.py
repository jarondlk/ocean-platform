"""C12 source-owned frozen canonical eDNA inventory contracts.

Raw descriptors describe retained records; C01 eligibility and recipe methods
remain independently restricted to supported scientific populations.
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field, model_validator

from schema.context_catalogue import (
    Availability,
    ContractModel,
    EDNADescriptor,
    Identifier,
    LocalizedText,
    NonnegativeInt,
    QueryResult,
    TextValue,
)

DATASET_VERSION = "catalogue-edna-dataset-v1"
TABLE_VERSION = "catalogue-edna-parquet-v1"
ADAPTER_VERSION = "c12-v1"
RAW_METHODS = (
    "qcauto_target",
    "qcauto_95pct_3nn_target",
    "qcauto_nontarget",
    "qcauto_95pct_3nn_nontarget",
)
ROLES = ("occurrences", "assays", "detections", "classifications")
TABLE_COLUMNS = {
    "occurrences": (
        "sample_id",
        "source_occurrence_id",
        "provider",
        "provider_locus",
        "provider_team",
        "provider_project_id",
        "provider_run_id",
        "collection_date_utc",
        "temporal_precision",
        "lat",
        "lon",
        "coordinate_precision",
        "identity_status",
        "physical_sample_id",
        "active",
        "source_snapshot_id",
        "provider_sample_id",
        "scientific_content_sha256",
    ),
    "classifications": (
        "sample_id",
        "sample_kind",
        "is_control",
        "classification_basis",
        "classification_review_json",
        "source_snapshot_id",
        "provider_sample_id",
    ),
    "assays": (
        "assay_id",
        "sample_id",
        "target_gene",
        "primer_set",
        "sequencing_method",
        "library_layout",
        "instrument_model",
        "community_availability_json",
        "active",
        "scientific_content_sha256",
    ),
    "detections": (
        "detection_id",
        "assay_id",
        "assignment_method",
        "target_status",
        "read_count",
        "copies_per_ml",
        "concentration_status",
        "sequence_sha256",
        "assigned_taxon_name",
        "assigned_taxon_rank",
        "taxonomy_json",
        "active",
        "scientific_content_sha256",
    ),
}


class EDNATable(ContractModel):
    name: Literal["occurrences", "assays", "detections", "classifications"]
    object_id: Identifier | None
    row_count: NonnegativeInt | None
    availability: Availability
    completeness: Literal["complete", "partial", "unknown", "unavailable"]

    @model_validator(mode="after")
    def binding(self):
        if self.object_id is None:
            if self.row_count is not None or self.availability.status == "available":
                raise ValueError("Absent eDNA table cannot claim a retained count")
            if self.completeness != self.availability.status:
                raise ValueError(
                    "Absent eDNA table requires matching unknown/unavailable state"
                )
        elif (
            self.row_count is None
            or self.availability.status != "available"
            or self.completeness == "unavailable"
        ):
            raise ValueError(
                "Retained eDNA table requires known count and availability"
            )
        return self


class EDNADataset(ContractModel):
    schema_version: Literal["catalogue-edna-dataset-v1"] = DATASET_VERSION
    family: Literal["edna_metabarcoding"] = "edna_metabarcoding"
    dataset_id: Identifier
    source_id: Identifier
    provider: TextValue
    provider_locus: TextValue | None
    provider_team: TextValue | None
    provider_project_id: TextValue
    collection_id: Identifier
    title: LocalizedText
    purpose: LocalizedText
    descriptor: EDNADescriptor
    qualification: TextValue
    methods: list[TextValue] = Field(min_length=1, max_length=32)
    tables: list[EDNATable] = Field(min_length=4, max_length=4)
    related_ids: list[Identifier] = Field(default_factory=list, max_length=256)

    @model_validator(mode="after")
    def source_semantics(self):
        if self.descriptor.population != "raw_inventory":
            raise ValueError(
                "Canonical eDNA datasets require an explicit raw inventory descriptor"
            )
        names = [table.name for table in self.tables]
        if set(names) != set(ROLES) or len(set(names)) != len(names):
            raise ValueError(
                "Every eDNA table role requires one retained or absent descriptor"
            )
        tables = {table.name: table for table in self.tables}
        if (
            tables["occurrences"].object_id is not None
            and tables["classifications"].object_id is None
        ):
            raise ValueError(
                "Retained occurrences require their frozen classifications"
            )
        identities = [self.dataset_id, self.collection_id] + [
            table.object_id for table in self.tables if table.object_id is not None
        ]
        if len(set(identities)) != len(identities) or any(
            identity.startswith(
                (
                    "root:",
                    "c12:source:",
                    "c12:provider:",
                    "c12:project:",
                    "c12:reference:",
                )
            )
            or identity in {"c12:edna", "c12:reference"}
            or identity.startswith("c12:edna:")
            for identity in identities
        ):
            raise ValueError(
                "eDNA dataset, collection and table IDs must be distinct and nonreserved"
            )
        if (
            len(set(self.related_ids)) != len(self.related_ids)
            or self.dataset_id in self.related_ids
        ):
            raise ValueError(
                "Related eDNA links must be distinct and cannot be self-links"
            )
        return self


class EDNAResponse(ContractModel):
    adapter_version: Literal["c12-v1"] = ADAPTER_VERSION
    result: QueryResult
    offset: NonnegativeInt = 0
    next_offset: NonnegativeInt | None = None
    qualifications: list[TextValue]
