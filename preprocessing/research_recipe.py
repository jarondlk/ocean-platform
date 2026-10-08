"""Versioned research contracts; evidence decisions are separate from source rows."""

from __future__ import annotations

from datetime import date
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

Hash = Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
Name = Annotated[str, Field(min_length=1, max_length=255)]


class ResearchModel(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False, frozen=True)


class EvidenceDecision(ResearchModel):
    reviewer: Name
    rationale: str = Field(min_length=1, max_length=4000)
    references: tuple[Annotated[str, Field(min_length=1, max_length=1000)], ...] = (
        Field(min_length=1, max_length=20)
    )
    evidence_sha256: Hash


class OccurrenceBinding(ResearchModel):
    sample_id: Hash
    scientific_content_sha256: Hash


class PhysicalMembership(ResearchModel):
    physical_sample_id: Hash
    occurrences: tuple[OccurrenceBinding, ...] = Field(min_length=1, max_length=100)
    representative_assay_id: Hash
    representative_assay_sha256: Hash
    area_id: Name
    area_version: Hash
    decision: EvidenceDecision
    representative_policy: Literal["reviewed_original_assay"] = (
        "reviewed_original_assay"
    )

    @model_validator(mode="after")
    def unique(self):
        if len({o.sample_id for o in self.occurrences}) != len(self.occurrences):
            raise ValueError("Duplicate occurrence membership")
        return self


class ReviewedArea(ResearchModel):
    area_id: Name
    region_id: Name
    label: Name
    # A regional context rectangle never asserts a provider cell/station footprint.
    geometry_type: Literal[
        "reviewed_cell_footprint", "reviewed_regional_context_rectangle"
    ] = "reviewed_cell_footprint"
    west: float = Field(strict=True, ge=-180, le=180)
    east: float = Field(strict=True, ge=-180, le=180)
    south: float = Field(strict=True, ge=-90, le=90)
    north: float = Field(strict=True, ge=-90, le=90)
    coordinate_uncertainty_km: float | None = Field(strict=True, ge=0, le=100)
    decision: EvidenceDecision

    @model_validator(mode="after")
    def ordered(self):
        if self.west >= self.east or self.south >= self.north:
            raise ValueError("Area requires a nonempty ordered footprint")
        if (
            self.geometry_type == "reviewed_cell_footprint"
            and self.coordinate_uncertainty_km is None
        ):
            raise ValueError(
                "Cell footprints require established coordinate uncertainty"
            )
        return self


class SamplingRegistry(ResearchModel):
    schema_version: Literal[1] = 1
    region_id: Name
    areas: tuple[ReviewedArea, ...] = Field(min_length=1, max_length=1000)
    memberships: tuple[PhysicalMembership, ...] = Field(min_length=1, max_length=10000)

    @model_validator(mode="after")
    def consistent(self):
        from ingestion.immutable_bundle import digest

        areas = {a.area_id: a for a in self.areas}
        if len(areas) != len(self.areas) or any(
            a.region_id != self.region_id for a in self.areas
        ):
            raise ValueError("Registry areas must be unique and belong to its region")
        seen, physical = set(), set()
        for membership in self.memberships:
            ids = {o.sample_id for o in membership.occurrences}
            area = areas.get(membership.area_id)
            if seen & ids or membership.physical_sample_id in physical:
                raise ValueError(
                    "Registry physical/occurrence membership must be unique"
                )
            if (
                not area
                or digest(area.model_dump(mode="json")) != membership.area_version
            ):
                raise ValueError(
                    "Membership must reference the exact reviewed area version"
                )
            seen.update(ids)
            physical.add(membership.physical_sample_id)
        return self


class TemperaturePartition(ResearchModel):
    kind: Literal["fixed_celsius", "cohort_thirds"]
    low_max: float | None = Field(None, strict=True, ge=-3, le=45)
    high_min: float | None = Field(None, strict=True, ge=-3, le=45)

    @model_validator(mode="after")
    def bounds(self):
        if self.kind == "fixed_celsius":
            if (
                self.low_max is None
                or self.high_min is None
                or self.low_max >= self.high_min
            ):
                raise ValueError(
                    "Fixed Celsius cut points must be explicit and ordered"
                )
        elif self.low_max is not None or self.high_min is not None:
            raise ValueError(
                "Cohort thirds derive cut points from the complete matched cohort"
            )
        return self


class DetectionFrequencyRecipe(ResearchModel):
    schema_version: Literal[2] = 2
    analysis_kind: Literal["detection_frequency"] = "detection_frequency"
    region_id: Name
    region_version: Hash
    identity_version: Hash
    classification_generation: Hash
    canonical_generation: Hash
    time_from: date
    time_to: date
    calendar: Literal["Asia/Tokyo"] = "Asia/Tokyo"
    date_only_policy: Literal["exclude_until_calendar_review"] = (
        "exclude_until_calendar_review"
    )
    season_policy: Literal["MAM_JJA_SON_DJF_january_year"] = (
        "MAM_JJA_SON_DJF_january_year"
    )
    analysis_unit: Literal["reviewed_physical_sample"] = "reviewed_physical_sample"
    control_policy: Literal["environmental_only"] = "environmental_only"
    assignment_method: Literal["qcauto_target", "qcauto_95pct_3nn_target"]
    rank: Literal["species"] = "species"
    min_read_count: int = Field(1, strict=True, ge=1, le=1_000_000)
    threshold_level: Literal["assay_taxon_sum"] = "assay_taxon_sum"
    empty_table_policy: Literal["exclude_without_successful_qc_evidence"] = (
        "exclude_without_successful_qc_evidence"
    )
    fish_classes: tuple[Name, ...] = Field(min_length=1, max_length=20)
    taxonomy_policy_reference: str = Field(min_length=1, max_length=1000)
    spatial_taxon_key: Hash
    endpoint_from: int = Field(strict=True, ge=1900, le=2100)
    endpoint_to: int = Field(strict=True, ge=1900, le=2100)
    spatial_year: int = Field(strict=True, ge=1900, le=2100)
    min_stratum_samples: int = Field(3, strict=True, ge=1, le=1000)
    temperature_partition: TemperaturePartition
    representative_temperature_metric: Literal[
        "equal_supported_area_season_stratum_difference"
    ] = "equal_supported_area_season_stratum_difference"
    sst_panel_id: Hash | None = None
    sst_max_time_hours: float = Field(24, strict=True, ge=0, le=48)
    sst_min_month_day_fraction: float = Field(0.8, strict=True, gt=0, le=1)

    @model_validator(mode="after")
    def ordered(self):
        if self.time_from > self.time_to or (self.time_to - self.time_from).days > 3660:
            raise ValueError("Research interval must be ordered and at most ten years")
        if (
            not self.time_from.year
            <= self.endpoint_from
            < self.endpoint_to
            <= self.time_to.year
        ):
            raise ValueError(
                "Endpoint years must be ordered within the selected interval"
            )
        if not self.time_from.year <= self.spatial_year <= self.time_to.year:
            raise ValueError("Spatial year must fall within the selected interval")
        if len(set(self.fish_classes)) != len(self.fish_classes):
            raise ValueError("Duplicate fish class")
        return self
