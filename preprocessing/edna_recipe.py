"""Strict, versioned settings for descriptive eDNA analyses."""
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator
from schema.time_range import time_bounds

METHODS = ('qcauto_target', 'qcauto_95pct_3nn_target')


class StrictModel(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)


class Cohort(StrictModel):
    provider: Literal['anemone'] = 'anemone'
    provider_project_id: str | None = Field(None, min_length=1, max_length=255)
    provider_run_id: str | None = Field(None, min_length=1, max_length=255)
    sample_ids: list[str] = Field(default_factory=list, max_length=200)
    time_from: str | None = None
    time_to: str | None = None
    lat_min: float | None = Field(None, ge=-90, le=90)
    lat_max: float | None = Field(None, ge=-90, le=90)
    lon_min: float | None = Field(None, ge=-180, le=180)
    lon_max: float | None = Field(None, ge=-180, le=180)

    @model_validator(mode='after')
    def bounded(self):
        from ingestion.immutable_bundle import validate_id
        for value in self.sample_ids:
            validate_id(value)
        self.sample_ids = sorted(set(self.sample_ids))
        time_bounds(self.time_from, self.time_to)
        bbox = [self.lat_min, self.lat_max, self.lon_min, self.lon_max]
        if any(v is not None for v in bbox):
            if any(v is None for v in bbox) or self.lat_min > self.lat_max or self.lon_min > self.lon_max:
                raise ValueError('A complete ordered bounding box is required')
        if not (self.provider_project_id or self.provider_run_id or self.sample_ids or all(v is not None for v in bbox)):
            raise ValueError('Select an explicit project/run, sample list, or bounding box')
        return self


class MetadataField(StrictModel):
    variable: Literal['temperature', 'salinity', 'depth', 'volume']
    value_key: str = Field(min_length=1, max_length=100)
    unit_key: str = Field(min_length=1, max_length=100)
    unit: Literal['degC', 'PSU', 'm', 'mL']
    reference: str = Field(min_length=1, max_length=500)

    @model_validator(mode='after')
    def expected_unit(self):
        if self.unit != {'temperature': 'degC', 'salinity': 'PSU', 'depth': 'm', 'volume': 'mL'}[self.variable]:
            raise ValueError('Unsupported variable/unit mapping')
        return self


class SiteAssignment(StrictModel):
    sample_id: str = Field(pattern=r'^[a-f0-9]{64}$')
    site_id: str = Field(min_length=1, max_length=128)
    domain_id: str = Field(min_length=1, max_length=128)
    reference: str = Field(min_length=1, max_length=500)
    source_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    coordinate_uncertainty_km: float = Field(ge=0, le=100)


class LinkProfile(StrictModel):
    profile_id: str = Field(min_length=1, max_length=128)
    reviewed_by: str = Field(min_length=1, max_length=255)
    reference: str = Field(min_length=1, max_length=500)
    domain_id: str = Field(min_length=1, max_length=128)
    lat_min: float = Field(ge=-90, le=90)
    lat_max: float = Field(ge=-90, le=90)
    lon_min: float = Field(ge=-180, le=180)
    lon_max: float = Field(ge=-180, le=180)
    max_distance_km: float = Field(gt=0, le=1000)
    max_time_hours: float = Field(ge=0, le=8760)
    max_depth_difference_m: float = Field(ge=0, le=10000)
    min_valid_fraction: float = Field(gt=0, le=1)
    max_coordinate_uncertainty_km: float = Field(ge=0, le=100)
    allow_regional_sst: bool = False

    @model_validator(mode='after')
    def ordered(self):
        if self.lat_min > self.lat_max or self.lon_min > self.lon_max:
            raise ValueError('Invalid linkage domain bounds')
        return self


class AnalysisRecipe(StrictModel):
    schema_version: Literal[1] = 1
    source_family: Literal['edna_metabarcoding'] = 'edna_metabarcoding'
    cohort: Cohort
    assignment_methods: list[Literal['qcauto_target', 'qcauto_95pct_3nn_target']] = Field(min_length=1, max_length=2)
    rank: Literal['genus', 'species']
    control_policy: Literal['environmental_only']
    min_read_count: int = Field(default=1, ge=1)
    metadata_fields: list[MetadataField] = Field(default_factory=list, max_length=4)
    sites: list[SiteAssignment] = Field(default_factory=list, max_length=200)
    linkage_profile: LinkProfile | None = None
    max_assays: int = Field(default=200, ge=1, le=200)
    max_detection_rows: int = Field(default=250000, ge=1, le=250000)
    max_taxa: int = Field(default=5000, ge=1, le=5000)
    max_comparisons: int = Field(default=50000, ge=1, le=50000)

    @model_validator(mode='after')
    def unique(self):
        self.assignment_methods = sorted(set(self.assignment_methods))
        if len({s.sample_id for s in self.sites}) != len(self.sites):
            raise ValueError('Duplicate site assignment')
        if len({f.variable for f in self.metadata_fields}) != len(self.metadata_fields):
            raise ValueError('Duplicate metadata variable')
        self.sites.sort(key=lambda s: s.sample_id)
        self.metadata_fields.sort(key=lambda f: f.variable)
        return self
