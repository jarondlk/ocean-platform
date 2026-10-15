"""C11 source-owned SST metadata; shared C08 and C09 contracts stay intact."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
import hashlib
import json
import re
from typing import Literal
from zoneinfo import ZoneInfo

from pydantic import Field, model_validator

from schema.context_catalogue import (
    Availability,
    ContractModel,
    Identifier,
    LocalizedText,
    NonnegativeInt,
    QueryResult,
    SSTDescriptor,
    TextValue,
)

DATASET_VERSION = "catalogue-sst-dataset-v1"
TABLE_VERSION = "catalogue-sst-parquet-v1"
ADAPTER_VERSION = "c11-v1"
MAX_SAMPLING_DAYS = 36_600
TABLE_COLUMNS = (
    "observation_id",
    "time",
    "value",
    "status",
    "lat",
    "lon",
    "quality_flag",
    "uncertainty",
    "valid_fraction",
    "valid_ocean_pixels",
    "ocean_pixels",
    "source_sha256",
    "exclusion_reason",
)


def sst_product_node_id(
    source_id: str,
    product_id: str,
    product_version: str,
    processing_generation: str,
) -> str:
    """Canonical source-qualified product identity, including exact generation."""
    retained = json.dumps(
        [product_id, product_version, processing_generation],
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return f"c11:product:{source_id}:{hashlib.sha256(retained).hexdigest()[:24]}"


class SSTSupport(ContractModel):
    """Declared nonwrapping WGS84 support, never an inferred scientific area."""

    south: float = Field(ge=-90, le=90)
    north: float = Field(ge=-90, le=90)
    west: float = Field(ge=-180, le=180)
    east: float = Field(ge=-180, le=180)

    @model_validator(mode="after")
    def ordered(self):
        if self.south >= self.north or self.west >= self.east:
            raise ValueError("SST support must have positive, nonwrapping extent")
        return self


class SSTSampling(ContractModel):
    """Explicit inclusive daily calendar for the dataset's declared support."""

    frequency: Literal["daily"] = "daily"
    start: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    end: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    calendar: Literal["UTC", "Asia/Tokyo"]

    @model_validator(mode="after")
    def calendar_bounds(self):
        start, end = date.fromisoformat(self.start), date.fromisoformat(self.end)
        if start.isoformat() != self.start or end.isoformat() != self.end:
            raise ValueError("Sampling dates require exact ISO day precision")
        days = (end - start).days + 1
        if not 1 <= days <= MAX_SAMPLING_DAYS:
            raise ValueError("Sampling calendar exceeds explicit daily bounds")
        try:
            zone = ZoneInfo(self.calendar)
            datetime.combine(start, time(), zone).astimezone(timezone.utc)
            datetime.combine(end + timedelta(days=1), time(), zone).astimezone(
                timezone.utc
            )
        except OverflowError as exc:
            raise ValueError(
                "Sampling calendar must have representable UTC interval boundaries"
            ) from exc
        return self


class SSTTable(ContractModel):
    """One complete retained observation population, independent of result pages."""

    name: Literal["observations"] = "observations"
    object_id: Identifier | None
    row_count: NonnegativeInt | None
    availability: Availability
    completeness: Literal["complete", "partial", "unknown", "unavailable"]

    @model_validator(mode="after")
    def binding(self):
        if self.object_id is None:
            if self.row_count is not None or self.availability.status == "available":
                raise ValueError("Absent SST data must not claim a known row count")
            if self.completeness != self.availability.status:
                raise ValueError(
                    "Absent SST data requires matching unknown/unavailable status"
                )
        elif (
            self.row_count is None
            or self.availability.status != "available"
            or self.completeness == "unavailable"
        ):
            raise ValueError("Retained SST data requires known count and availability")
        return self


class SSTDataset(ContractModel):
    schema_version: Literal["catalogue-sst-dataset-v1"] = DATASET_VERSION
    family: Literal["remote_sensing"] = "remote_sensing"
    dataset_id: Identifier
    source_id: Identifier
    product_node_id: Identifier
    collection_id: Identifier
    title: LocalizedText
    purpose: LocalizedText
    descriptor: SSTDescriptor
    processing_generation: Literal["final", "interim", "unknown"]
    measurement_type: Literal[
        "satellite_retrieval", "satellite_in_situ_analysis", "model_assimilation"
    ]
    temporal_statistic: Literal[
        "daily_foundation_analysis", "daily_mean", "instant_retrieval", "model_instant"
    ]
    calendar: Literal["UTC", "Asia/Tokyo"]
    observation_precision: Literal["day", "datetime"]
    support: SSTSupport
    observation_entity: Literal["regional_daily_summary", "grid_observation"]
    sampling: SSTSampling | None
    spatial_resolution_basis: TextValue
    aggregation_method: TextValue
    quality_policy: TextValue
    uncertainty_policy: TextValue
    qualification: TextValue
    methods: list[TextValue] = Field(min_length=1, max_length=32)
    table: SSTTable
    related_ids: list[Identifier] = Field(default_factory=list, max_length=256)

    @model_validator(mode="after")
    def source_semantics(self):
        expected_product = sst_product_node_id(
            self.source_id,
            self.descriptor.product_id,
            self.descriptor.product_version,
            self.processing_generation,
        )
        if self.product_node_id != expected_product:
            raise ValueError(
                "Product identity must bind source, product, version and generation"
            )
        identities = [self.dataset_id, self.collection_id, self.product_node_id]
        if self.table.object_id is not None:
            identities.append(self.table.object_id)
        if len(identities) != len(set(identities)) or any(
            identity.startswith(("root:", "c11:source:", "c11:reference:"))
            or identity in {"c11:sst", "c11:reference"}
            or identity.startswith("c11:sst:")
            for identity in identities
        ):
            raise ValueError(
                "SST dataset, collection, product and table IDs must be distinct/nonreserved"
            )
        if any(
            identity.startswith("c11:product:")
            for identity in [
                self.dataset_id,
                self.collection_id,
                self.table.object_id or "",
            ]
        ):
            raise ValueError(
                "Only canonical product nodes may use the product namespace"
            )
        if (
            len(self.related_ids) != len(set(self.related_ids))
            or self.dataset_id in self.related_ids
        ):
            raise ValueError(
                "SST links must be distinct and cannot link to the dataset itself"
            )
        if self.sampling is not None:
            if self.sampling.calendar != self.calendar:
                raise ValueError("Expected sampling must retain the dataset calendar")
            if self.temporal_statistic not in {
                "daily_foundation_analysis",
                "daily_mean",
            }:
                raise ValueError(
                    "Instant observations cannot imply expected daily sampling"
                )
        if self.observation_entity == "regional_daily_summary":
            if self.temporal_statistic not in {
                "daily_foundation_analysis",
                "daily_mean",
            }:
                raise ValueError(
                    "Regional daily summaries require a daily temporal statistic"
                )
            if self.descriptor.spatial_role != "regional_summary":
                raise ValueError(
                    "Regional summaries must not claim retained native grid observations"
                )
        elif self.descriptor.spatial_role == "regional_summary":
            raise ValueError("Grid observations cannot be labeled regional summaries")
        if self.temporal_statistic == "daily_foundation_analysis" and (
            self.measurement_type != "satellite_in_situ_analysis"
        ):
            raise ValueError(
                "Foundation analysis must preserve its satellite/in-situ analysis meaning"
            )
        instant_measurements = {
            "instant_retrieval": "satellite_retrieval",
            "model_instant": "model_assimilation",
        }
        if self.temporal_statistic in instant_measurements and (
            self.measurement_type != instant_measurements[self.temporal_statistic]
        ):
            raise ValueError(
                "Instant temporal statistics must retain the source measurement type"
            )
        # MUR's product versions are distinct scientific generations. Never
        # relabel near-real-time observations as final or vice versa.
        if re.search(r"(^|[._:-])mur($|[._:-])", self.descriptor.product_id, re.I):
            expected = {"04.1": "final", "04.1nrt": "interim"}.get(
                self.descriptor.product_version
            )
            if expected is not None and self.processing_generation != expected:
                raise ValueError("MUR version and final/interim generation disagree")
            if expected is not None and (
                self.measurement_type != "satellite_in_situ_analysis"
                or self.temporal_statistic != "daily_foundation_analysis"
            ):
                raise ValueError(
                    "Known MUR products must retain daily satellite/in-situ foundation analysis"
                )
        return self


class SSTResponse(ContractModel):
    adapter_version: Literal["c11-v1"] = ADAPTER_VERSION
    result: QueryResult
    offset: NonnegativeInt = 0
    next_offset: NonnegativeInt | None = None
    qualifications: list[TextValue]
