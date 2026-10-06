"""Unapproved, reproducible SST access/comparison packet and file diagnostics."""

from datetime import date
from pathlib import Path

import numpy as np
import xarray as xr

from ingestion.anemone_catalogue import file_sha256
from ingestion.immutable_bundle import digest
from ingestion.sst_acquisition import MAX_FILE_BYTES, acquisition_plan

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
