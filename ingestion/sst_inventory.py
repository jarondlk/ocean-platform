"""Read-only acquisition census; reported coordinates are not reviewed areas."""

from collections import Counter
from datetime import date, datetime
import json
import math
from zoneinfo import ZoneInfo

from ingestion.immutable_bundle import canonical_bytes, digest, validate_id
from ingestion.research_readiness import MAX_OCCURRENCES

CALENDAR = "Asia/Tokyo"
MAX_SNAPSHOT_BYTES = 32 * 1024 * 1024
FIELDS = (
    "sample_id",
    "scientific_content_sha256",
    "source_snapshot_id",
    "source_file_id",
    "provider",
    "provider_project_id",
    "provider_run_id",
    "collection_date_utc",
    "temporal_precision",
    "lat",
    "lon",
    "coordinate_precision",
    "sample_kind",
    "is_control",
    "active",
    "raw_metadata_json",
)


def read_production_census(engine):
    """One repeatable, read-only transaction; never read accounts/history/detections."""
    from sqlalchemy import text

    def serial(value):
        return value.isoformat() if isinstance(value, (datetime, date)) else value

    with engine.connect() as connection, connection.begin():
        connection.exec_driver_sql(
            "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY"
        )
        connection.exec_driver_sql("SET LOCAL statement_timeout='60s'")
        publications = [
            dict(row)
            for row in connection.execute(
                text(
                    "SELECT channel,generation_id,manifest_sha256 FROM corpus_publication "
                    "WHERE channel IN ('anemone-canonical','edna-canonical','edna') ORDER BY channel"
                )
            ).mappings()
        ]
        binding = {
            row["channel"]: {
                key: row[key] for key in ("generation_id", "manifest_sha256")
            }
            for row in publications
        }
        if (
            not binding.get("anemone-canonical")
            or not binding.get("edna")
            or binding["anemone-canonical"] != binding.get("edna-canonical")
        ):
            raise ValueError("Canonical publication is unavailable or out of sync")
        for row in binding.values():
            for value in row.values():
                validate_id(value)
        rows, used = [], 0
        result = (
            connection.execution_options(stream_results=True)
            .execute(
                text(
                    "SELECT " + ",".join(FIELDS) + " FROM edna_sample "
                    "WHERE provider='anemone' AND active IS TRUE ORDER BY sample_id LIMIT :limit"
                ),
                {"limit": MAX_OCCURRENCES + 1},
            )
            .mappings()
            .yield_per(500)
        )
        for row in result:
            value = {key: serial(item) for key, item in row.items()}
            used += len(canonical_bytes(value))
            if len(rows) >= MAX_OCCURRENCES or used > MAX_SNAPSHOT_BYTES:
                raise ValueError("Acquisition census snapshot limit exceeded")
            rows.append(value)
    return rows, {
        "basis": "production_repeatable_read",
        "publication": binding,
        "metadata_sha256": digest(rows),
        "metadata_bytes": used,
    }


def _reported_location(sample):
    lat, lon = sample.get("lat"), sample.get("lon")
    if isinstance(lat, bool) or isinstance(lon, bool) or lat is None or lon is None:
        return None
    try:
        lat, lon = float(lat), float(lon)
    except (TypeError, ValueError):
        return None
    if not (
        math.isfinite(lat)
        and math.isfinite(lon)
        and -90 <= lat <= 90
        and -180 <= lon <= 180
    ):
        return None
    return {
        "lat": lat,
        "lon": lon,
        "coordinate_basis": sample.get("coordinate_precision") or "unspecified",
    }


def build_inventory(samples, provenance, *, halo_degrees=0.02):
    """All reported locations x all sampling years, including full-month context.

    The 1-degree tiles and halo are acquisition envelopes only. Provider worldmesh
    is retained as a label and never decoded into physical sampling footprints.
    """
    if not 0 <= halo_degrees <= 0.1 or not math.isfinite(halo_degrees):
        raise ValueError("Acquisition halo must be finite and at most 0.1 degrees")
    if len(samples) > MAX_OCCURRENCES:
        raise ValueError("Acquisition census row limit exceeded")
    years, dates, seen, unresolved = Counter(), [], set(), []
    locations, tiles, kinds = {}, {}, Counter()
    reported_cells, missing_cells = set(), 0
    for sample in sorted(samples, key=lambda row: row["sample_id"]):
        sid = validate_id(sample["sample_id"])
        if sid in seen:
            raise ValueError("Duplicate acquisition census occurrence")
        seen.add(sid)
        if (
            sample.get("provider", "anemone") != "anemone"
            or sample.get("active", True) is not True
        ):
            continue
        kinds[sample.get("sample_kind") or "unknown"] += 1
        metadata = sample.get("raw_metadata_json") or {}
        metadata = json.loads(metadata) if isinstance(metadata, str) else metadata
        cell = str(metadata.get("worldmesh") or "")
        if cell:
            reported_cells.add(cell)
        else:
            missing_cells += 1
        reasons, local_date = [], None
        try:
            precision = sample.get("temporal_precision")
            if precision not in {"datetime", "date"}:
                raise ValueError("Unknown temporal precision")
            raw_date = str(sample.get("collection_date_utc"))
            if precision == "date":
                # A provider calendar date has no invented midnight/timezone.
                local_date = date.fromisoformat(raw_date)
            else:
                stamp = datetime.fromisoformat(raw_date.replace("Z", "+00:00"))
                if stamp.tzinfo is None:
                    raise ValueError("Unzoned timestamp")
                local_date = stamp.astimezone(ZoneInfo(CALENDAR)).date()
            if not 2002 <= local_date.year <= date.today().year:
                raise ValueError("Date outside supported historical interval")
            years[local_date.year] += 1
            dates.append(local_date.isoformat())
        except (ValueError, TypeError):
            reasons.append("date_unresolved")
        location = _reported_location(sample)
        if location is None:
            reasons.append("coordinate_unresolved")
        else:
            lid = digest(location)
            entry = locations.setdefault(
                lid,
                {
                    "location_id": lid,
                    **location,
                    "sample_ids": [],
                    "sampling_years": set(),
                    "reported_worldmesh": set(),
                },
            )
            entry["sample_ids"].append(sid)
            if cell:
                entry["reported_worldmesh"].add(cell)
            if local_date:
                entry["sampling_years"].add(local_date.year)
            lat, lon = location["lat"], location["lon"]
            south, west = math.floor(lat), math.floor(lon)
            footprint = dict(
                south=max(-89.9, south - halo_degrees),
                north=min(89.9, south + 1 + halo_degrees),
                west=max(-179.9, west - halo_degrees),
                east=min(179.9, west + 1 + halo_degrees),
            )
            if not (
                footprint["south"] <= lat <= footprint["north"]
                and footprint["west"] <= lon <= footprint["east"]
            ):
                reasons.append("outside_mur_tile_support")
            else:
                tid = digest(footprint)
                tile = tiles.setdefault(
                    tid, {"tile_id": tid, "footprint": footprint, "location_ids": set()}
                )
                tile["location_ids"].add(lid)
        if reasons:
            unresolved.append(
                {
                    "sample_id": sid,
                    "reasons": reasons,
                    "original_date": sample.get("collection_date_utc"),
                    "temporal_precision": sample.get("temporal_precision"),
                }
            )
    year_values = sorted(years)
    for tile in tiles.values():
        tile["location_ids"] = sorted(tile["location_ids"])
        tile["sampling_years"] = year_values
        tile["basis"] = "unreviewed_acquisition_envelope"
    for location in locations.values():
        for key in ("sampling_years", "reported_worldmesh"):
            location[key] = sorted(location[key])
    report = {
        "schema_version": 1,
        "kind": "historical_sst_acquisition_inventory",
        "source": provenance,
        "calendar": CALENDAR,
        "scope": "all_reported_locations_all_sampling_years",
        "halo_degrees": halo_degrees,
        "sampling_years": year_values,
        "counts": {
            "source_occurrences": sum(kinds.values()),
            "sample_kinds": dict(sorted(kinds.items())),
            "reported_coordinate_locations": len(locations),
            "acquisition_tiles": len(tiles),
            "reported_worldmesh_values": len(reported_cells),
            "occurrences_without_worldmesh": missing_cells,
            "unresolved_occurrences": len(unresolved),
        },
        "year_counts": [
            {"year": year, "occurrences": count}
            for year, count in sorted(years.items())
        ],
        "reported_date_extent": {
            "from": min(dates) if dates else None,
            "to": max(dates) if dates else None,
        },
        "locations": [locations[key] for key in sorted(locations)],
        "tiles": [tiles[key] for key in sorted(tiles)],
        "unresolved": unresolved,
        "limitations": [
            "Occurrences and reported coordinates are not reviewed physical samples or areas.",
            "Controls and unknown classifications are included in the acquisition census only.",
            "Tile halo is a download margin, not a scientific coordinate uncertainty estimate.",
            "Date-only records never acquire an invented sample-time match.",
        ],
    }
    report["inventory_id"] = digest(report)
    return report
