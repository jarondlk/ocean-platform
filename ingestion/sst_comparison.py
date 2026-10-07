"""Unapproved, reproducible SST access/comparison packet and file diagnostics."""

from datetime import date, datetime, timedelta
from pathlib import Path

import numpy as np
import xarray as xr

from ingestion.anemone_catalogue import file_sha256
from ingestion.immutable_bundle import digest
from ingestion.sst_acquisition import MAX_FILE_BYTES, acquisition_plan
from ingestion.himawari_probe import (
    MAX_FILE_BYTES as MAX_HIMAWARI_BYTES,
    parse_remote_file,
)

REFERENCES = {
    "mur": "https://podaac.jpl.nasa.gov/MEaSUREs-MUR",
    "mur_mirror": "https://coastwatch.pfeg.noaa.gov/erddap/griddap/jplMURSST41.html",
    "himawari_archive": "https://www.eorc.jaxa.jp/ptree/faq.html",
    "himawari_format": "https://www.eorc.jaxa.jp/ptree/documents/README_HimawariGeo_en.txt",
    "himawari_reprocessing": "https://www.eorc.jaxa.jp/ptree/index.html?mode=day&prod=sst",
}


def build_comparison_packet(inventory):
    if inventory.get("inventory_id") != digest(
        {k: v for k, v in inventory.items() if k != "inventory_id"}
    ):
        raise ValueError("Comparison inventory checksum mismatch")
    locations = inventory["locations"]
    if not locations or not inventory["sampling_years"]:
        raise ValueError("Comparison requires reported coordinates and dates")
    # Fixed geographical extremes plus the original Miyagi diagnostic vicinity.
    # These are probe locations/dates, never inferred scientific sample events.
    representatives = {
        location["location_id"]: location
        for location in (
            min(
                locations,
                key=lambda location: (location["lat"], location["location_id"]),
            ),
            max(
                locations,
                key=lambda location: (location["lat"], location["location_id"]),
            ),
            max(
                locations,
                key=lambda location: (location["lon"], location["location_id"]),
            ),
            min(
                locations,
                key=lambda location: (
                    (location["lat"] - 38.62) ** 2 + (location["lon"] - 141.44) ** 2,
                    location["location_id"],
                ),
            ),
        )
    }
    first, last = inventory["sampling_years"][0], inventory["sampling_years"][-1]
    days = sorted({date(first, 12, 18).isoformat(), date(last, 7, 15).isoformat()})
    cases = []
    for identity, location in sorted(representatives.items()):
        lat, lon = location["lat"], location["lon"]
        # Keep the probe inside the existing pilot's bounded global support.
        if not -89.8 <= lat <= 89.8 or not -179.8 <= lon <= 179.8:
            continue
        footprint = {
            "south": round(lat - 0.05, 6),
            "north": round(lat + 0.05, 6),
            "west": round(lon - 0.05, 6),
            "east": round(lon + 0.05, 6),
        }
        plan = acquisition_plan(days, **footprint)
        cases.append(
            {
                "case_id": digest([identity, days, footprint]),
                "location_id": identity,
                "coordinate_basis": location["coordinate_basis"],
                "mur_plan": plan,
                "himawari_access_status": "requires_authenticated_historical_file_probe",
            }
        )
    packet = {
        "schema_version": 1,
        "kind": "historical_sst_product_comparison",
        "inventory_id": inventory["inventory_id"],
        "status": "comparison_pending",
        "scientific_approval": False,
        "references": REFERENCES,
        "cases": cases,
        "basis": "reported_coordinate_probe_not_reviewed_sample_area",
        "products": [
            {
                "product_id": "mur_l4_foundation_sst",
                "measurement_type": "satellite_in_situ_analysis",
                "temporal_basis": "daily_foundation_analysis",
                "grid_degrees": 0.01,
                "access": "public_bounded_erddap_subset",
            },
            {
                "product_id": "himawari_geophysical_sst",
                "measurement_type": "satellite_retrieval",
                "temporal_basis": "historical_file_statistic_must_be_verified",
                "grid_km": 2,
                "access": "registered_ptree_historical_geophysical_archive",
                "historical_checks": [
                    "algorithm_and_file_versions",
                    "daily_mean_versus_minimum",
                    "2022_10_03_to_2023_05_21_reprocessing",
                    "quality_and_sses",
                    "cloud_gaps",
                ],
            },
        ],
        "remaining": [
            "Himawari binary access and exact historical file versions",
            "Matched footprint/time/statistic and valid-ocean coverage comparison",
            "Independent scientific product/quality/time-window selection recorded in review ledger",
        ],
        "limitations": [
            "Product metadata describes different measurement/time semantics.",
            "No numeric product comparison is complete until both products have verified raw files.",
            "The probe margin and unfiltered diagnostics are not scientific quality/area approvals.",
        ],
    }
    packet["comparison_id"] = digest(packet)
    return packet


def inspect_mur_file(path: Path, entry):
    """Bounded raw-container diagnostics, without proposed scientific QC cutoffs."""
    if (
        path.is_symlink()
        or path.stat().st_size > MAX_FILE_BYTES
        or file_sha256(path) != entry["raw_sha256"]
    ):
        raise ValueError("Comparison raw file checksum/byte mismatch")
    with xr.open_dataset(path) as dataset:
        title = str(dataset.attrs.get("title") or "")
        if "MUR" not in title or "fv04.1" not in title:
            raise ValueError("MUR comparison product/version identity mismatch")
        if set(
            (
                "time",
                "latitude",
                "longitude",
                "analysed_sst",
                "analysis_error",
                "mask",
                "sea_ice_fraction",
            )
        ) - set(dataset.variables):
            raise ValueError("MUR comparison variable contract mismatch")
        if dataset.analysed_sst.size > 100_000 or dataset.time.size != 1:
            raise ValueError("Comparison grid limit exceeded")
        stamp = np.datetime_as_string(dataset.time.values[0], unit="s") + "Z"
        if stamp != entry["expected_time_utc"]:
            raise ValueError("MUR comparison timestamp mismatch")
        temperature = dataset.analysed_sst.values
        units = dataset.analysed_sst.attrs.get("units")
        if units == "K":
            temperature = temperature - 273.15
        elif units not in {
            "degree_C",
            "degrees_C",
            "degree_Celsius",
            "degrees_Celsius",
        }:
            raise ValueError("Unrecognized MUR comparison temperature units")
        ocean = dataset["mask"].values == 1
        valid = ocean & np.isfinite(temperature)
        error = dataset.analysis_error.values
        finite_error = error[ocean & np.isfinite(error)]
        values = temperature[valid]
        report = {
            "product_id": "mur_l4_foundation_sst",
            "raw_sha256": entry["raw_sha256"],
            "source_url": entry["source_url"],
            "time_utc": stamp,
            "title": dataset.attrs.get("title"),
            "dataset_version": dataset.attrs.get("version"),
            "version_basis": "mirror_title_fv04.1",
            "latitude_extent": [
                float(dataset.latitude.min()),
                float(dataset.latitude.max()),
            ],
            "longitude_extent": [
                float(dataset.longitude.min()),
                float(dataset.longitude.max()),
            ],
            "grid_values": int(temperature.size),
            "ocean_pixels": int(ocean.sum()),
            "finite_ocean_sst_pixels": int(valid.sum()),
            "sst_celsius_min": float(values.min()) if values.size else None,
            "sst_celsius_max": float(values.max()) if values.size else None,
            "sst_celsius_mean": float(values.mean()) if values.size else None,
            "analysis_error_units": dataset.analysis_error.attrs.get("units"),
            "finite_ocean_error_min": float(finite_error.min())
            if finite_error.size
            else None,
            "finite_ocean_error_max": float(finite_error.max())
            if finite_error.size
            else None,
            "scientific_quality_threshold_applied": False,
            "basis": "unfiltered_grid_diagnostic_not_reviewed_area_statistic",
        }
    if file_sha256(path) != entry["raw_sha256"]:
        raise ValueError("Comparison file changed during inspection")
    return report


def _finite_summary(values):
    values = np.asarray(values)
    finite = values[np.isfinite(values)]
    return {
        "finite_pixels": int(finite.size),
        "min": float(finite.min()) if finite.size else None,
        "max": float(finite.max()) if finite.size else None,
        "mean": float(finite.mean()) if finite.size else None,
    }


def inspect_himawari_file(path: Path, entry, footprint):
    """Inspect only a bounded footprint in a full-disk file, before any QC.

    Native-grid summaries are diagnostic; daily minima/means and hourly skin
    retrievals are not interchangeable with MUR daily foundation analysis.
    """
    fields = parse_remote_file(entry["remote_path"])
    if (
        path.is_symlink()
        or not path.is_file()
        or not 8 <= path.stat().st_size <= MAX_HIMAWARI_BYTES
        or path.stat().st_size != entry["byte_count"]
        or file_sha256(path) != entry["raw_sha256"]
    ):
        raise ValueError("Himawari comparison raw checksum/byte mismatch")
    south, north, west, east = (
        footprint[k] for k in ("south", "north", "west", "east")
    )
    if not (
        all(np.isfinite([south, north, west, east]))
        and -60 <= south < north <= 60
        and -180 <= west < east <= 180
        and north - south <= 2
        and east - west <= 2
    ):
        raise ValueError("Himawari comparison footprint limit exceeded")
    with xr.open_dataset(path, cache=False, decode_timedelta=False) as dataset:
        if (
            set(
                (
                    "time",
                    "lat",
                    "lon",
                    "sea_surface_temperature",
                    "quality_level",
                    "l2p_flags",
                )
            )
            - set(dataset.variables)
            or dataset.time.size != 1
            or dataset.attrs.get("product_version") != fields["algorithm_version"]
            or "AHI onboard Himawari-" not in str(dataset.attrs.get("title"))
            or not str(dataset.attrs.get("id", "")).startswith(
                fields["satellite"] + "_AHI-JAXA-L3C-"
            )
        ):
            raise ValueError("Himawari comparison product/variable contract mismatch")
        stamp = np.datetime_as_string(dataset.time.values[0], unit="s") + "Z"
        nominal = datetime.strptime(fields["nominal_time_utc"], "%Y-%m-%dT%H:%M:%SZ")
        offset = float(
            (dataset.time.values[0] - np.datetime64(nominal)) / np.timedelta64(1, "s")
        )
        time_comment = str(dataset.time.attrs.get("comment", ""))
        duration = (
            timedelta(days=1) if "_daily" in fields["filename"] else timedelta(hours=1)
        )
        if (
            dataset.attrs.get("time_coverage_start")
            != nominal.strftime("%Y%m%dT%H%M%SZ")
            or dataset.attrs.get("time_coverage_end")
            != (nominal + duration).strftime("%Y%m%dT%H%M%SZ")
            or not np.isfinite(offset)
            or (
                offset != 0
                and not (0 < offset <= 60 and "leap seconds" in time_comment.lower())
            )
        ):
            raise ValueError("Himawari comparison time/coverage contract mismatch")
        indexes = {}
        extents = {}
        longitude_wrap = False
        for axis, low, high in (("lat", south, north), ("lon", west, east)):
            variable = dataset[axis]
            if variable.dims != (axis,) or not 2 <= variable.size <= 6001:
                raise ValueError("Himawari comparison axis contract mismatch")
            values = variable.values
            original_values = values
            differences = np.diff(values)
            if axis == "lon" and np.count_nonzero(np.abs(differences) > 180) == 1:
                # JAXA's full disk crosses +180/-180. Unwrap the coordinate
                # axis for index selection only; keep native pixel provenance.
                values = np.rad2deg(np.unwrap(np.deg2rad(values.astype(float))))
                differences = np.diff(values)
                longitude_wrap = True
                if high < values.min() and low + 360 >= values.min():
                    low, high = low + 360, high + 360
            if not np.isfinite(values).all() or not (
                (differences > 0).all() or (differences < 0).all()
            ):
                raise ValueError(
                    "Himawari comparison axes must be finite and monotonic"
                )
            if values.min() > low or values.max() < high:
                raise ValueError("Himawari comparison footprint outside grid")
            selected = np.flatnonzero((values >= low) & (values <= high))
            if not selected.size:
                raise ValueError("Himawari comparison footprint has no pixel centres")
            indexes[axis] = slice(int(selected[0]), int(selected[-1]) + 1)
            extents[axis] = [
                float(original_values[selected].min()),
                float(original_values[selected].max()),
            ]
        subset = dataset.isel(indexes)
        if subset.lat.size * subset.lon.size > 100_000:
            raise ValueError("Himawari comparison grid resource limit exceeded")
        temperatures = {}
        names = [
            name
            for name in dataset.data_vars
            if name.startswith("sea_surface_temperature")
            or name in {"sst_daily_min", "sst_daily_max"}
        ]
        if len(names) > 6:
            raise ValueError("Himawari comparison temperature variable limit exceeded")
        for name in names:
            variable = subset[name]
            if variable.dims != ("time", "lat", "lon"):
                raise ValueError("Himawari temperature dimensions mismatch")
            if variable.attrs.get("units") not in {"K", "kelvin"}:
                raise ValueError("Himawari comparison temperature units mismatch")
            temperatures[name] = {
                "long_name": variable.attrs.get("long_name"),
                "comment": variable.attrs.get("comment"),
                "cell_methods": variable.attrs.get("cell_methods"),
                "celsius": _finite_summary(variable.values - 273.15),
            }
        diagnostics = {}
        for name in (
            "quality_level",
            "l2p_flags",
            "sses_bias",
            "sses_standard_deviation",
            "sst_dtime",
            "sst_count",
        ):
            if name not in subset:
                continue
            variable = subset[name]
            if variable.dims != ("time", "lat", "lon"):
                raise ValueError("Himawari diagnostic dimensions mismatch")
            item = {
                "units": variable.attrs.get("units"),
                "long_name": variable.attrs.get("long_name"),
                "comment": variable.attrs.get("comment"),
                **_finite_summary(variable.values),
            }
            if name in {"quality_level", "l2p_flags"}:
                values, counts = np.unique(
                    variable.values[np.isfinite(variable.values)], return_counts=True
                )
                ceiling = 5 if name == "quality_level" else 8191
                if (
                    values.size > 256
                    or (values != np.floor(values)).any()
                    or (values < 0).any()
                    or (values > ceiling).any()
                ):
                    raise ValueError("Himawari flag diagnostic limit exceeded")
                item["distribution"] = {
                    str(int(v)): int(n) for v, n in zip(values, counts)
                }
                item["flag_meanings"] = variable.attrs.get("flag_meanings")
                for key in ("flag_masks", "flag_values"):
                    if key in variable.attrs:
                        item[key] = np.asarray(variable.attrs[key]).tolist()
            diagnostics[name] = item
        report = {
            "product_id": "himawari_geophysical_sst",
            **fields,
            "raw_sha256": entry["raw_sha256"],
            "byte_count": entry["byte_count"],
            "source_uri": entry["source_uri"],
            "title": dataset.attrs.get("title"),
            "dataset_id": dataset.attrs.get("id"),
            "time_coverage_start": dataset.attrs.get("time_coverage_start"),
            "time_coverage_end": dataset.attrs.get("time_coverage_end"),
            "reference_time_cf_decoded": stamp,
            "reference_time_cf_offset_seconds": offset,
            "reference_time_comment": time_comment,
            "time_decoding_status": "exact_nominal_reference"
            if offset == 0
            else "provider_leap_second_encoding_requires_review_no_correction_applied",
            "grid_values": int(subset.lat.size * subset.lon.size),
            "requested_footprint": footprint,
            "native_pixel_centre_extents": extents,
            "longitude_axis_unwrapped_for_selection": longitude_wrap,
            "temperature_variables": temperatures,
            "diagnostics": diagnostics,
            "scientific_quality_threshold_applied": False,
            "basis": "unfiltered_native_grid_diagnostic_not_reviewed_area_statistic",
            "comparability": "different_grid_depth_and_time_statistics_no_bias_or_equivalence_claim",
        }
    if file_sha256(path) != entry["raw_sha256"]:
        raise ValueError("Himawari raw file changed during inspection")
    return report
