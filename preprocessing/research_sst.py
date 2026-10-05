"""Bounded local SST normalization and indexed area/day linkage.

Product definitions are reviewed inputs, not guesses from filenames. This module
does not download products or weaken the legacy point/depth linker.
"""

from __future__ import annotations

from bisect import bisect_left, bisect_right
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated, Literal

import numpy as np
from pydantic import Field, model_validator
import xarray as xr

from ingestion.anemone_catalogue import file_sha256
from ingestion.immutable_bundle import digest, validate_id
from preprocessing.research_recipe import (
    EvidenceDecision,
    Hash,
    Name,
    ResearchModel,
    ReviewedArea,
)

MAX_GRANULE_BYTES = 256 * 1024 * 1024
MAX_GRID_VALUES = 2_000_000
MAX_OBSERVATIONS = 200_000


class SSTProductDefinition(ResearchModel):
    product_id: Literal[
        "himawari_geophysical_sst", "mur_l4_foundation_sst", "jcope_model_sst"
    ]
    provider: Name
    version: Name
    measurement_type: Literal[
        "satellite_retrieval", "satellite_in_situ_analysis", "model_assimilation"
    ]
    processing_level: Name
    source_reference: str = Field(min_length=1, max_length=1000)
    expected_title: str = Field(min_length=1, max_length=1000)
    temperature_variable: Literal["sst", "sea_surface_temperature", "analysed_sst"]
    time_variable: Name = "time"
    latitude_variable: Name = "lat"
    longitude_variable: Name = "lon"
    ocean_mask_variable: Name
    ocean_mask_values: tuple[Annotated[int, Field(strict=True)], ...] = Field(
        min_length=1, max_length=10
    )
    quality_variable: Name | None = None
    accepted_quality_values: tuple[Annotated[int, Field(strict=True)], ...] = Field(
        default=(), max_length=20
    )
    uncertainty_variable: Name | None = None
    max_uncertainty_celsius: float | None = Field(None, strict=True, gt=0, le=5)
    temporal_statistic: Literal[
        "instant_retrieval", "daily_foundation_analysis", "daily_mean", "model_instant"
    ] = "daily_foundation_analysis"
    surface_depth_variable: Name | None = None
    min_valid_fraction: float = Field(strict=True, ge=0.01, le=1)
    min_ocean_pixels: int = Field(strict=True, ge=1, le=100000)
    decision: EvidenceDecision

    @model_validator(mode="after")
    def product_semantics(self):
        expected = {
            "himawari_geophysical_sst": "satellite_retrieval",
            "mur_l4_foundation_sst": "satellite_in_situ_analysis",
            "jcope_model_sst": "model_assimilation",
        }[self.product_id]
        if self.measurement_type != expected:
            raise ValueError("Product measurement type mismatch")
        if bool(self.quality_variable) != bool(self.accepted_quality_values):
            raise ValueError("Quality variable and accepted flags must be paired")
        if bool(self.uncertainty_variable) != (
            self.max_uncertainty_celsius is not None
        ):
            raise ValueError("Uncertainty variable and threshold must be paired")
        if not self.quality_variable and not self.uncertainty_variable:
            raise ValueError("A reviewed quality or uncertainty rule is required")
        allowed = {
            "mur_l4_foundation_sst": {"daily_foundation_analysis"},
            "himawari_geophysical_sst": {"instant_retrieval", "daily_mean"},
            "jcope_model_sst": {"model_instant"},
        }[self.product_id]
        if self.temporal_statistic not in allowed:
            raise ValueError("Product temporal statistic mismatch")
        return self


class GranuleInput(ResearchModel):
    granule_id: Hash
    raw_sha256: Hash
    source_url: str = Field(min_length=1, max_length=2000)
    expected_time_utc: datetime

    @model_validator(mode="after")
    def qualified(self):
        if self.expected_time_utc.tzinfo is None:
            raise ValueError("Expected granule time must be timezone qualified")
        return self


def _axis(ds, name):
    axis = ds[name]
    if axis.dims != (name,) or axis.size < 2:
        raise ValueError("SST grid requires one-dimensional nonsingleton axes")
    values = np.asarray(axis.values, dtype=float)
    differences = np.diff(values)
    if not np.isfinite(values).all() or not (
        np.all(differences > 0) or np.all(differences < 0)
    ):
        raise ValueError("SST grid axes must be finite, unique and monotonic")
    # CF coordinates commonly use float32: quantization grows with longitude.
    precision = (
        np.finfo(axis.dtype).eps if np.issubdtype(axis.dtype, np.floating) else 0
    )
    tolerance = max(1e-7, precision * max(1, abs(values).max()) * 4)
    spacing = float(np.median(np.abs(differences)))
    if not np.allclose(np.abs(differences), spacing, rtol=1e-5, atol=tolerance):
        raise ValueError("Initial SST adapter requires a regular grid")
    return values, spacing


def normalize_granule(
    path: Path,
    granule: GranuleInput,
    product: SSTProductDefinition,
    areas: list[ReviewedArea],
) -> list[dict]:
    if (
        path.is_symlink()
        or path.stat().st_size > MAX_GRANULE_BYTES
        or len(areas) > 1000
    ):
        raise ValueError("SST granule/area resource limit exceeded")
    if file_sha256(path) != granule.raw_sha256:
        raise ValueError("SST raw granule checksum mismatch")
    with xr.open_dataset(path, decode_cf=True, mask_and_scale=True) as ds:
        if ds.attrs.get("title") != product.expected_title:
            raise ValueError("SST product title does not match reviewed definition")
        time, lat, lon = (
            product.time_variable,
            product.latitude_variable,
            product.longitude_variable,
        )
        t = ds[product.temperature_variable]
        if product.surface_depth_variable:
            depth = product.surface_depth_variable
            if ds[depth].size != 1 or float(ds[depth].values[0]) != 0:
                raise ValueError("Only explicit surface depth zero is supported")
            t = t.isel({depth: 0}, drop=True)
        if (
            set(t.dims) != {time, lat, lon}
            or ds[time].size != 1
            or t.size > MAX_GRID_VALUES
        ):
            raise ValueError(
                "SST granule dimensions exceed the reviewed surface contract"
            )
        latitudes, dy = _axis(ds, lat)
        longitudes, dx = _axis(ds, lon)
        if (
            latitudes.min() < -90
            or latitudes.max() > 90
            or longitudes.min() < -180
            or longitudes.max() > 180
        ):
            raise ValueError(
                "SST axes must use geographic degrees in -180..180 longitude"
            )
        stamp = ds[time].values[0]
        if not np.issubdtype(type(stamp), np.datetime64) or np.isnat(stamp):
            raise ValueError("SST adapter requires a valid Gregorian CF time")
        seconds = int(stamp.astype("datetime64[s]").astype(np.int64))
        when = datetime.fromtimestamp(seconds, timezone.utc)
        if when != granule.expected_time_utc.astimezone(timezone.utc):
            raise ValueError(
                "SST filename/inventory time disagrees with file coordinate"
            )
        units = t.attrs.get("units")
        if units not in {
            "K",
            "kelvin",
            "degC",
            "degree_C",
            "degree_Celsius",
            "degrees_Celsius",
        }:
            raise ValueError("Unsupported SST units")
        values = np.asarray(t.transpose(time, lat, lon).values[0], dtype=float)
        if units in {"K", "kelvin"}:
            values = values - 273.15

        def grid(variable):
            field = ds[variable]
            if time in field.dims:
                field = field.isel({time: 0}, drop=True)
            if set(field.dims) != {lat, lon}:
                raise ValueError("SST mask/quality grid dimensions disagree")
            return np.asarray(field.transpose(lat, lon).values)

        ocean = np.isin(grid(product.ocean_mask_variable), product.ocean_mask_values)
        quality = np.ones(values.shape, dtype=bool)
        if product.quality_variable:
            quality &= np.isin(
                grid(product.quality_variable), product.accepted_quality_values
            )
        if product.uncertainty_variable:
            uncertainty = grid(product.uncertainty_variable).astype(float)
            uncertainty_units = ds[product.uncertainty_variable].attrs.get("units")
            if uncertainty_units not in {
                "K",
                "kelvin",
                "degC",
                "degree_C",
                "degree_Celsius",
                "degrees_Celsius",
            }:
                raise ValueError("Unsupported SST uncertainty units")
            # A Kelvin uncertainty is a temperature difference: no 273.15 offset.
            quality &= (
                np.isfinite(uncertainty)
                & (uncertainty >= 0)
                & (uncertainty <= product.max_uncertainty_celsius)
            )
        valid = ocean & quality & np.isfinite(values) & (values >= -3) & (values <= 45)
        rows = []
        footprint = (
            longitudes.min() - dx / 2,
            longitudes.max() + dx / 2,
            latitudes.min() - dy / 2,
            latitudes.max() + dy / 2,
        )
        for area in sorted(areas, key=lambda a: a.area_id):
            in_footprint = (
                area.west >= footprint[0]
                and area.east <= footprint[1]
                and area.south >= footprint[2]
                and area.north <= footprint[3]
            )
            y = np.flatnonzero((latitudes >= area.south) & (latitudes < area.north))
            x = np.flatnonzero((longitudes >= area.west) & (longitudes < area.east))
            indexes = np.ix_(y, x)
            n_ocean = int(ocean[indexes].sum())
            n_valid = int(valid[indexes].sum())
            fraction = n_valid / n_ocean if n_ocean else None
            status = (
                "valid"
                if in_footprint
                and n_ocean >= product.min_ocean_pixels
                and fraction >= product.min_valid_fraction
                else "no_valid_footprint"
                if not in_footprint
                else "insufficient_valid_ocean_pixels"
            )
            # Spherical pixel areas vary with latitude; longitude spacing is fixed.
            weights = np.broadcast_to(
                np.cos(np.deg2rad(latitudes[y]))[:, None], (len(y), len(x))
            )
            mask = valid[indexes]
            mean = (
                float(np.average(values[indexes][mask], weights=weights[mask]))
                if status == "valid"
                else None
            )
            row = {
                "area_id": area.area_id,
                "area_version": digest(area.model_dump(mode="json")),
                "product_definition_id": digest(product.model_dump(mode="json")),
                "granule_id": granule.granule_id,
                "raw_sha256": granule.raw_sha256,
                "source_url": granule.source_url,
                "time_utc": when.isoformat(),
                "product_id": product.product_id,
                "product_version": product.version,
                "measurement_type": product.measurement_type,
                "temporal_statistic": product.temporal_statistic,
                "status": status,
                "sst_celsius": mean,
                "valid_fraction": fraction,
                "valid_ocean_pixels": n_valid,
                "ocean_pixels": n_ocean,
                "pixel_rows": y.tolist(),
                "pixel_columns": x.tolist(),
                "weighting": "cosine_latitude_area_weighted_valid_ocean_pixels",
                "temperature_basis": "granule_time",
            }
            row["observation_id"] = digest(row)
            rows.append(row)
    return rows


def link_sample_time(
    members: list[dict],
    observations: list[dict],
    panel_id: str,
    *,
    max_time_hours: float,
) -> tuple[list[dict], list[dict]]:
    """Indexed area/time windows. Ties use stable observation IDs, not SST values."""
    validate_id(panel_id)
    if (
        not 0 <= max_time_hours <= 48
        or len(members) > 10000
        or len(observations) > MAX_OBSERVATIONS
    ):
        raise ValueError("SST linkage resource/window limit exceeded")
    index = defaultdict(list)
    ids, products = set(), set()
    for row in observations:
        identity = validate_id(row["observation_id"])
        if identity in ids or identity != digest(
            {k: v for k, v in row.items() if k != "observation_id"}
        ):
            raise ValueError("SST observation identity conflict")
        ids.add(identity)
        products.add(row["product_definition_id"])
        if row["status"] == "valid":
            when = datetime.fromisoformat(row["time_utc"])
            if when.tzinfo is None:
                raise ValueError("SST observation time is unqualified")
            index[(row["area_id"], row["area_version"])].append(
                (when.timestamp(), identity, row)
            )
    if len(products) > 1:
        raise ValueError("An SST panel must pin one product definition")
    for rows in index.values():
        rows.sort(key=lambda r: (r[0], r[1]))
    timestamps = {key: [row[0] for row in rows] for key, rows in index.items()}
    links, excluded = [], []
    for member in sorted(members, key=lambda m: m["physical_sample_id"]):
        # A local date is insufficient for a sample-time link. Preserve original
        # collection UTC in membership; never invent midnight for date-only rows.
        raw = member.get("collection_time_utc")
        when = datetime.fromisoformat(raw.replace("Z", "+00:00")) if raw else None
        rows = index.get((member["area_id"], member["area_version"]), [])
        reason = (
            "collection_time_unavailable"
            if when is None or when.tzinfo is None
            else "sst_unavailable"
        )
        if when is not None and when.tzinfo is not None:
            stamp, window = when.timestamp(), max_time_hours * 3600
            stamps = timestamps.get((member["area_id"], member["area_version"]), [])
            candidates = rows[
                bisect_left(stamps, stamp - window) : bisect_right(
                    stamps, stamp + window
                )
            ]
            if candidates:
                distance, _, observation = min(
                    candidates, key=lambda row: (abs(row[0] - stamp), row[1])
                )
                links.append(
                    {
                        "physical_sample_id": member["physical_sample_id"],
                        "panel_id": panel_id,
                        "status": "matched",
                        "area_id": member["area_id"],
                        "area_version": member["area_version"],
                        "sst_celsius": observation["sst_celsius"],
                        "observation_ids": [observation["observation_id"]],
                        "source_granule_ids": [observation["granule_id"]],
                        "time_difference_hours": abs(distance - stamp) / 3600,
                        "temperature_basis": "sample_time_surface_context",
                        "measurement_type": observation["measurement_type"],
                        "temporal_statistic": observation.get("temporal_statistic"),
                    }
                )
                continue
        excluded.append(
            {"physical_sample_id": member["physical_sample_id"], "status": reason}
        )
    return links, excluded


def monthly_area_context(observations, areas, year, *, min_day_fraction=0.8):
    """Full calendar-month daily SST context, separate from sampled timestamps.

    Missing days remain missing. Daily analyses are not direct satellite
    observations; multiple rows for the same area/day are a contract error.
    """
    import calendar
    from zoneinfo import ZoneInfo

    if (
        not 1900 <= year <= 2100
        or not 0 < min_day_fraction <= 1
        or len(observations) > MAX_OBSERVATIONS
        or len(areas) > 1000
    ):
        raise ValueError("Monthly SST context resource/calendar limit exceeded")
    groups, seen, products = defaultdict(list), set(), set()
    area_versions = {a.area_id: digest(a.model_dump(mode="json")) for a in areas}
    if len(area_versions) != len(areas):
        raise ValueError("Duplicate monthly SST area")
    for row in observations:
        if row["observation_id"] != digest(
            {k: v for k, v in row.items() if k != "observation_id"}
        ):
            raise ValueError("Monthly SST observation identity mismatch")
        if row.get("temporal_statistic") not in {
            "daily_foundation_analysis",
            "daily_mean",
        }:
            raise ValueError("Monthly context requires a declared daily SST product")
        when = datetime.fromisoformat(row["time_utc"])
        if when.tzinfo is None:
            raise ValueError("Monthly SST time is unqualified")
        local = when.astimezone(ZoneInfo("Asia/Tokyo")).date()
        if local.year != year:
            continue
        if row["area_version"] != area_versions.get(row["area_id"]):
            raise ValueError("Monthly SST area version mismatch")
        products.add(row["product_definition_id"])
        key = row["area_id"], local.isoformat()
        if key in seen:
            raise ValueError("Multiple daily SST observations for one area/date")
        seen.add(key)
        if row["status"] == "valid":
            value = row["sst_celsius"]
            if (
                not isinstance(value, (int, float))
                or not np.isfinite(value)
                or not -3 <= value <= 45
            ):
                raise ValueError("Invalid monthly SST value")
            groups[(row["area_id"], local.month)].append(row)
    if len(products) > 1:
        raise ValueError("Monthly context requires one fixed product definition")
    results = []
    for area in sorted(areas, key=lambda a: a.area_id):
        for month in range(1, 13):
            rows = sorted(
                groups[(area.area_id, month)], key=lambda r: r["observation_id"]
            )
            expected = calendar.monthrange(year, month)[1]
            supported = len(rows) / expected >= min_day_fraction
            results.append(
                {
                    "area_id": area.area_id,
                    "area_version": area_versions[area.area_id],
                    "month": f"{year}-{month:02d}",
                    "calendar": "Asia/Tokyo",
                    "expected_days": expected,
                    "valid_days": len(rows),
                    "missing_days": expected - len(rows),
                    "min_day_fraction": min_day_fraction,
                    "status": "supported"
                    if supported
                    else "insufficient_daily_coverage",
                    "sst_celsius": sum(r["sst_celsius"] for r in rows) / len(rows)
                    if supported
                    else None,
                    "temperature_basis": "full_month_daily_area_context",
                    "weighting": "equal_valid_days",
                    "observation_ids": [r["observation_id"] for r in rows],
                    "source_granule_ids": sorted({r["granule_id"] for r in rows}),
                    "product_definition_id": next(iter(products), None),
                }
            )
    return results
