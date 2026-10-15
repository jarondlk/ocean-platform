"""C10 source-owned frozen table contracts; C08 transport contracts stay intact."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import Field, model_validator

from schema.context_catalogue import (
    Availability,
    ContractModel,
    CTDDescriptor,
    Identifier,
    LocalizedText,
    MetagenomeDescriptor,
    NonnegativeInt,
    QueryResult,
    TextValue,
)

DATASET_VERSION = "catalogue-dataset-v1"
TABLE_VERSION = "catalogue-parquet-v1"
ADAPTER_VERSION = "c10-v1"
ROLES = {
    "ctd": ("casts", "depth_observations"),
    "metagenome": (
        "collections",
        "run_qc",
        "kraken_abundance",
        "metaeuk_abundance",
        "ranked_taxa",
    ),
}
REQUIRED_COLUMNS = {
    "casts": {
        "cast_id": "string",
        "sample_id": "string",
        "collection_date": "string",
        "bay": "string",
        "station": "string",
    },
    "depth_observations": {
        "observation_id": "string",
        "cast_id": "string",
        "depth": "number",
    },
    "collections": {
        "library_id": "string",
        "sample_id": "string",
        "collection_date": "string",
        "bay": "string",
        "station": "string",
        "has_kraken": "boolean",
        "has_metaeuk": "boolean",
    },
    "run_qc": {"run_id": "string", "library_id": "string", "run_date": "string"},
    "kraken_abundance": {
        "measurement_id": "string",
        "library_id": "string",
        "taxon": "string",
        "method": "string",
        "taxonomic_rank": "string",
        "abundance": "number",
    },
    "metaeuk_abundance": {
        "measurement_id": "string",
        "library_id": "string",
        "taxon": "string",
        "method": "string",
        "taxonomic_rank": "string",
        "abundance": "number",
    },
    "ranked_taxa": {
        "summary_id": "string",
        "library_id": "string",
        "taxon": "string",
        "method": "string",
        "abundance": "number",
    },
}
KEYS = {role: next(iter(columns)) for role, columns in REQUIRED_COLUMNS.items()}


class FrozenColumn(ContractModel):
    name: Identifier
    dtype: Literal["string", "number", "integer", "boolean"]
    nullable: bool = True
    unit: TextValue | None = None
    description: TextValue

    @model_validator(mode="after")
    def numeric_unit(self):
        if self.dtype in {"number", "integer"} and self.unit is None:
            raise ValueError("Numeric columns require declared units/counting entities")
        return self


class FrozenTable(ContractModel):
    name: Literal[
        "casts",
        "depth_observations",
        "collections",
        "run_qc",
        "kraken_abundance",
        "metaeuk_abundance",
        "ranked_taxa",
    ]
    object_id: Identifier | None
    row_count: NonnegativeInt | None
    entity: TextValue
    denominator: TextValue
    columns: list[FrozenColumn] = Field(min_length=1, max_length=64)
    availability: Availability
    completeness: Literal["complete", "partial", "unknown", "unavailable"]
    method: TextValue | None = None
    taxonomic_rank: TextValue | None = None
    abundance_denominator: TextValue | None = None

    @model_validator(mode="after")
    def bindings(self):
        if len({c.name for c in self.columns}) != len(self.columns):
            raise ValueError("Frozen columns must be unique")
        types = {c.name: c.dtype for c in self.columns}
        if any(types.get(k) != v for k, v in REQUIRED_COLUMNS[self.name].items()):
            raise ValueError("Missing/wrong source-owned columns")
        if self.object_id is None:
            if (
                self.row_count is not None
                or self.availability.status == "available"
                or self.completeness != "unavailable"
            ):
                raise ValueError(
                    "Missing tables require unknown counts and explicit unavailability"
                )
        elif (
            self.row_count is None
            or self.availability.status != "available"
            or self.completeness == "unavailable"
        ):
            raise ValueError("Retained tables require a count and availability")
        if self.name in {"kraken_abundance", "metaeuk_abundance"}:
            expected = "Kraken" if self.name == "kraken_abundance" else "MetaEuk"
            if (
                self.method != expected
                or self.taxonomic_rank is None
                or self.abundance_denominator is None
            ):
                raise ValueError(
                    "Abundance tables require explicit assignment method and rank"
                )
        if self.name == "ranked_taxa" and self.completeness == "complete":
            raise ValueError(
                "Ranked summaries cannot declare complete normalized abundance"
            )
        return self


Descriptor = Annotated[
    CTDDescriptor | MetagenomeDescriptor, Field(discriminator="family")
]


class FrozenDataset(ContractModel):
    schema_version: Literal["catalogue-dataset-v1"] = DATASET_VERSION
    dataset_id: Identifier
    source_id: Identifier
    family: Literal["ctd", "metagenome"]
    collection_id: Identifier
    title: LocalizedText
    purpose: LocalizedText
    descriptor: Descriptor
    collection_date_precision: Literal[
        "day", "month", "year", "datetime", "unknown", "mixed"
    ]
    depth_convention: Literal["positive_down", "signed_source"] | None = None
    qualification: TextValue
    methods: list[TextValue] = Field(min_length=1, max_length=32)
    tables: list[FrozenTable] = Field(min_length=1, max_length=8)
    related_ids: list[Identifier] = Field(default_factory=list, max_length=256)

    @model_validator(mode="after")
    def source_semantics(self):
        if self.descriptor.family != self.family:
            raise ValueError("Descriptor family mismatch")
        if self.family == "ctd" and self.depth_convention is None:
            raise ValueError("CTD requires an explicit retained depth sign convention")
        names = [t.name for t in self.tables]
        if len(names) != len(set(names)) or set(names) != set(ROLES[self.family]):
            raise ValueError(
                "All source roles require unique retained or unavailable table descriptors"
            )
        if ("casts" if self.family == "ctd" else "collections") not in names:
            raise ValueError("A source anchor table must have an explicit descriptor")
        identifiers = [t.object_id for t in self.tables if t.object_id is not None]
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("Table objects must have unique identities")
        identities = [self.dataset_id, self.collection_id] + identifiers
        if len(identities) != len(set(identities)) or any(
            key.startswith(("root:", "c10:source:")) for key in identities
        ):
            raise ValueError(
                "Dataset, collection and table identities must be distinct and nonreserved"
            )
        if (
            len(self.related_ids) != len(set(self.related_ids))
            or self.dataset_id in self.related_ids
        ):
            raise ValueError("Related links must be distinct and cannot be self-links")
        return self


class AdapterResponse(ContractModel):
    """C08 result plus source-owned paging/schema qualifications for C14 consumers."""

    adapter_version: Literal["c10-v1"] = ADAPTER_VERSION
    result: QueryResult
    table: FrozenTable | None = None
    offset: NonnegativeInt = 0
    next_offset: NonnegativeInt | None = None
    qualifications: list[TextValue]
