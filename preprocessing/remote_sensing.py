"""
Remote sensing (satellite SST) preprocessing pipeline.

Handles two data sources:
  1. Pre-processed NetCDF subsets (onagawa_sst_subset/) – primary path
  2. Raw Himawari .DAT files (himawari_test_unzipped/) – optional, via satpy

Pipeline:
    list_sst_files → extract_point_timeseries / compute_daily_summary
"""
from __future__ import annotations

import logging
import re
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

from preprocessing.research_recipe import ReviewedArea

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# File discovery
# ---------------------------------------------------------------------------
def list_sst_files(root: Path, pattern: str = "*.nc") -> List[Path]:
    """Discover NetCDF SST files under *root* (recursive, sorted)."""
    files = sorted(root.rglob(pattern))
    logger.info("Found %d SST files under %s", len(files), root)
    return files


def parse_sst_time_from_filename(path: Path) -> pd.Timestamp:
    """
    Extract UTC timestamp from an SST NetCDF filename.

    Expected pattern: ``onagawa_sst_YYYYMMDD_HHMM.nc``
    """
    m = re.search(r"(\d{8})_(\d{4})", path.name)
    if not m:
        raise ValueError(f"Could not parse timestamp from filename: {path.name}")
    return pd.to_datetime(f"{m.group(1)} {m.group(2)}", format="%Y%m%d %H%M")


# ---------------------------------------------------------------------------
# Point time series  (extracted from app_v0_1_ocean.py lines 268-303)
# ---------------------------------------------------------------------------
def extract_point_timeseries(
    root: Path,
    target_lat: float,
    target_lon: float,
) -> pd.DataFrame:
    """
    For each NetCDF file under *root*, extract SST at the grid point
    nearest to (target_lat, target_lon).

    Returns DataFrame with columns:
        file, time_utc, time_jst, sst, nearest_lat, nearest_lon
    """
    import xarray as xr

    files = list_sst_files(root)
    rows: List[Dict[str, Any]] = []

    for fp in files:
        ds = xr.open_dataset(str(fp), engine="netcdf4", decode_times=False)
        try:
            point = (
                ds["SST"]
                .sel(latitude=target_lat, longitude=target_lon, method="nearest")
                .isel(time=0, depth=0)
            )

            nearest_lat = float(
                ds["latitude"]
                .sel(latitude=target_lat, method="nearest")
                .values
            )
            nearest_lon = float(
                ds["longitude"]
                .sel(longitude=target_lon, method="nearest")
                .values
            )

            t_utc = parse_sst_time_from_filename(fp)
            rows.append(
                {
                    "file": fp.name,
                    "time_utc": t_utc,
                    "time_jst": t_utc + pd.Timedelta(hours=9),
                    "sst": float(point.values),
                    "nearest_lat": nearest_lat,
                    "nearest_lon": nearest_lon,
                }
            )
        except Exception as e:
            logger.warning("Skipping %s: %s", fp.name, e)
        finally:
            ds.close()

    if not rows:
        return pd.DataFrame(
            columns=["file", "time_utc", "time_jst", "sst", "nearest_lat", "nearest_lon"]
        )

    df = pd.DataFrame(rows).sort_values("time_utc").reset_index(drop=True)
    logger.info("SST point time series: %d records", len(df))
    return df


# ---------------------------------------------------------------------------
# Daily regional summary
# ---------------------------------------------------------------------------
REGIONAL_MEAN_SEMANTICS = (
    "Unweighted mean of finite selected grid-centre values per source file; "
    "daily mean and standard deviation retain the mean of file statistics. "
    "This is regional context, not a point or provider-cell observation."
)
REGIONAL_GRID_CAVEATS = (
    "Bounds select grid centres inclusively and do not establish cell footprints.",
    "Valid-pixel coverage may differ between source files and does not prove full rectangle coverage.",
    "Grid spacing does not establish effective spatial resolution or coastal/sample-point applicability.",
    "Product metadata and units are retained without conversion or independent scientific approval.",
)


def _regional_support(lat_min, lat_max, lon_min, lon_max, reviewed_area):
    bounds = (lon_min, lon_max, lat_min, lat_max)
    if not all(isinstance(value, (int, float, np.integer, np.floating))
               and not isinstance(value, (bool, np.bool_)) and math.isfinite(value) for value in bounds):
        raise ValueError("Regional calculation bounds must be finite coordinates.")
    if not (-180 <= lon_min < lon_max <= 180 and -90 <= lat_min < lat_max <= 90):
        raise ValueError("Regional calculation bounds must describe an ordered nonempty rectangle.")
    support = {
        "kind": "unreviewed_regional_context_rectangle",
        "west": float(lon_min), "east": float(lon_max),
        "south": float(lat_min), "north": float(lat_max),
        "reference": None, "reviewed": False,
        "aggregation_semantics": REGIONAL_MEAN_SEMANTICS,
        "grid_caveats": list(REGIONAL_GRID_CAVEATS),
        "review_scope": "Regional geometry only; product values are not independently approved.",
    }
    if reviewed_area is None:
        return support
    if not isinstance(reviewed_area, ReviewedArea):
        raise ValueError("Spatial review must be an existing validated ReviewedArea.")
    # model_copy/model_construct can bypass validation; validate its serialized
    # fields again before carrying any reviewed-support claim into a result.
    area = ReviewedArea.model_validate(reviewed_area.model_dump(mode="json"))
    if area.geometry_type != "reviewed_regional_context_rectangle":
        raise ValueError("A regional mean cannot be labelled as a reviewed cell footprint.")
    if (area.west, area.east, area.south, area.north) != bounds:
        raise ValueError("Reviewed regional support must exactly match the calculation bounds.")
    area_record = area.model_dump(mode="json")
    area_hash = hashlib.sha256(json.dumps(area_record, sort_keys=True, separators=(",", ":"),
                                         ensure_ascii=False).encode()).hexdigest()
    support.update(kind=area.geometry_type, reviewed=True,
                   reference=area.decision.references[0], reviewed_area=area_record,
                   reviewed_area_sha256=area_hash)
    return support


def _metadata_value(value):
    if isinstance(value, np.ndarray):
        return _metadata_value(value.tolist())
    if isinstance(value, np.generic):
        return _metadata_value(value.item())
    if isinstance(value, (list, tuple)):
        return [_metadata_value(item) for item in value]
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def _grid_axis_metadata(values):
    values = np.asarray(values, dtype=float)
    spacings = np.unique(np.abs(np.diff(values)))
    return {"minimum": float(values.min()), "maximum": float(values.max()),
            "n_centres": int(values.size),
            "spacing_degrees": float(spacings[0]) if spacings.size == 1 else None}


def compute_daily_summary(
    root: Path,
    lat_min: float = 38.0,
    lat_max: float = 39.0,
    lon_min: float = 141.0,
    lon_max: float = 142.0,
    *,
    reviewed_area: ReviewedArea | None = None,
) -> pd.DataFrame:
    """
    For each NetCDF file, compute regional SST statistics (mean, min,
    max, std) over the specified lat/lon bounding box, then aggregate
    to daily summaries.

    Returns DataFrame with columns:
        date_jst, mean_sst, min_sst, max_sst, std_sst, n_files,
        spatial_support, input_provenance, source_metadata, aggregation_semantics

    Support is unreviewed by default. Configuration bounds never establish a
    historical review. An existing reviewed regional-context area may qualify
    exactly matching geometry; it cannot relabel regional values as point data.
    """
    import xarray as xr
    from netCDF4 import Dataset

    support = _regional_support(lat_min, lat_max, lon_min, lon_max, reviewed_area)
    support_json = json.dumps(support, sort_keys=True, ensure_ascii=False, allow_nan=False)
    files = list_sst_files(root)
    hourly_rows: List[Dict[str, Any]] = []
    input_hashes = {}

    for fp in files:
        ds = None
        memory_dataset = None
        try:
            source_path = str(fp.resolve())
            payload = fp.read_bytes()
            source_hash = hashlib.sha256(payload).hexdigest()
            input_hashes[source_path] = source_hash
            # NetCDF and xarray consume the exact immutable bytes that supplied
            # the receipt, not a separately reopened mutable source path.
            memory_dataset = Dataset(fp.name, mode="r", memory=payload)
            store = xr.backends.NetCDF4DataStore(memory_dataset)
            ds = xr.open_dataset(store, decode_times=False)
            sst = ds["SST"].isel(time=0, depth=0)
            lat = ds["latitude"].values
            lon = ds["longitude"].values

            lat_mask = (lat >= lat_min) & (lat <= lat_max)
            lon_mask = (lon >= lon_min) & (lon <= lon_max)

            region = sst.values[np.ix_(lat_mask, lon_mask)].astype("float32")
            valid = region[np.isfinite(region)]

            if valid.size == 0:
                continue

            t_utc = parse_sst_time_from_filename(fp)
            product_keys = ("title", "id", "product_id", "product_version", "source", "institution", "references")
            source_metadata = {
                "file": fp.name, "path": source_path, "sha256": source_hash,
                "time_utc_from_filename": t_utc.isoformat(),
                "product": {key: _metadata_value(ds.attrs[key]) for key in product_keys if key in ds.attrs},
                "sst_attributes": {key: _metadata_value(ds["SST"].attrs[key])
                                   for key in ("units", "standard_name", "long_name") if key in ds["SST"].attrs},
                "selected_latitude": _grid_axis_metadata(lat[lat_mask]),
                "selected_longitude": _grid_axis_metadata(lon[lon_mask]),
                "n_valid_pixels": int(valid.size),
            }
            hourly_rows.append(
                {
                    "file": fp.name,
                    "time_utc": t_utc,
                    "time_jst": t_utc + pd.Timedelta(hours=9),
                    "mean_sst": float(np.mean(valid)),
                    "min_sst": float(np.min(valid)),
                    "max_sst": float(np.max(valid)),
                    "std_sst": float(np.std(valid)),
                    "n_pixels": int(valid.size),
                    "source_path": source_path,
                    "source_hash": source_hash,
                    "source_metadata": source_metadata,
                }
            )
        except Exception as e:
            logger.warning("Skipping %s: %s", fp.name, e)
        finally:
            if ds is not None:
                ds.close()
            elif memory_dataset is not None:
                memory_dataset.close()

    if not hourly_rows:
        empty = pd.DataFrame(
            columns=["date", "date_jst", "mean_sst", "min_sst", "max_sst", "std_sst", "n_files",
                     "spatial_support", "input_provenance", "source_metadata", "aggregation_semantics"]
        )
        empty.attrs.update(spatial_support=support, input_provenance=input_hashes)
        return empty

    hourly = pd.DataFrame(hourly_rows)
    hourly["date_jst"] = hourly["time_jst"].dt.date

    daily = (
        hourly.groupby("date_jst")
        .agg(
            mean_sst=("mean_sst", "mean"),
            min_sst=("min_sst", "min"),
            max_sst=("max_sst", "max"),
            std_sst=("std_sst", "mean"),
            n_files=("file", "count"),
        )
        .reset_index()
    )
    provenance_by_day = {}
    metadata_by_day = {}
    for day, group in hourly.groupby("date_jst"):
        provenance_by_day[day] = json.dumps(dict(zip(group["source_path"], group["source_hash"])), sort_keys=True)
        metadata_by_day[day] = json.dumps(group["source_metadata"].tolist(), sort_keys=True,
                                          ensure_ascii=False, allow_nan=False)
    daily["spatial_support"] = support_json
    daily["input_provenance"] = daily["date_jst"].map(provenance_by_day)
    daily["source_metadata"] = daily["date_jst"].map(metadata_by_day)
    daily["aggregation_semantics"] = REGIONAL_MEAN_SEMANTICS
    daily.attrs.update(spatial_support=support, input_provenance=input_hashes)

    logger.info("SST daily summary: %d days", len(daily))
    return daily


# ---------------------------------------------------------------------------
# Himawari .DAT raw file parsing (optional)
# ---------------------------------------------------------------------------
def parse_himawari_dat(
    dat_path: Path,
    target_lat: float,
    target_lon: float,
) -> Optional[Dict[str, Any]]:
    """
    Parse a raw Himawari .DAT file via satpy and extract brightness
    temperature at the target point.

    Returns None if satpy is not available or parsing fails.
    """
    try:
        from satpy import Scene
    except ImportError:
        logger.warning("satpy not installed – skipping raw Himawari file: %s", dat_path)
        return None

    try:
        scn = Scene(reader="ahi_hsd", filenames=[str(dat_path)])
        scn.load(["B14"])  # 11.2 µm thermal IR band for SST proxy

        data = scn["B14"]
        lats, lons = data.attrs.get("area").get_lonlats()

        # Find nearest pixel
        dist = (lats - target_lat) ** 2 + (lons - target_lon) ** 2
        idx = np.unravel_index(np.argmin(dist), dist.shape)

        bt = float(data.values[idx])

        # Parse time from filename: HS_H09_YYYYMMDD_HHMM_...
        m = re.search(r"(\d{8})_(\d{4})", dat_path.name)
        if not m:
            return None

        t_utc = pd.to_datetime(f"{m.group(1)} {m.group(2)}", format="%Y%m%d %H%M")

        return {
            "file": dat_path.name,
            "time_utc": t_utc,
            "time_jst": t_utc + pd.Timedelta(hours=9),
            "brightness_temp": bt,
            "nearest_lat": float(lats[idx]),
            "nearest_lon": float(lons[idx]),
        }
    except Exception as e:
        logger.warning("Failed to parse Himawari DAT %s: %s", dat_path.name, e)
        return None
