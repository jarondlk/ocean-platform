"""Local provisional matching; explicit assumptions never become observed facts."""

from collections import defaultdict
from datetime import date, datetime, time, timezone
from zoneinfo import ZoneInfo

import numpy as np

from ingestion.immutable_bundle import digest, validate_id
from preprocessing.edna_detection_frequency import season
from preprocessing.research_sst import MAX_OBSERVATIONS, link_sample_time
from preprocessing.sst_context_review import (
    ALGORITHM as CONTEXT_ALGORITHM,
    STATUS as CONTEXT_STATUS,
    ContextQualityProposal,
)

ALGORITHM = "provisional-historical-sst-matching-v1"
JAPAN = ZoneInfo("Asia/Tokyo")


def preview_context_observations(diagnostics, area_id):
    """Convert a verified-context diagnostic into explicitly unpublished rows.

    Hash binding detects changes; it is not a substitute for the upstream raw
    read-back verification or a reviewed area/product definition. The rectangle
    and proposed rules remain marked as provisional throughout this preview.
    """
    if not isinstance(area_id, str) or not area_id or len(area_id) > 128:
        raise ValueError("Invalid preview region label")
    if diagnostics.get("diagnostics_id") != digest(
        {k: v for k, v in diagnostics.items() if k != "diagnostics_id"}
    ):
        raise ValueError("Context diagnostic identity mismatch")
    if (
        diagnostics.get("algorithm") != CONTEXT_ALGORITHM
        or diagnostics.get("status") != CONTEXT_STATUS
    ):
        raise ValueError("Unsupported context diagnostic contract")
    for field in (
        "scientific_approval",
        "scientific_publication",
        "rectangle_is_reviewed_sampling_area",
        "coarse_context_is_native_sample_evidence",
    ):
        if diagnostics.get(field) is not False:
            raise ValueError("Context preview cannot assert scientific acceptance")
    if len(diagnostics["daily"]) > 31:
        raise ValueError("Context preview exceeds monthly bound")
    definition = {
        k: v for k, v in diagnostics["proposed_quality"].items() if k != "proposal_id"
    }
    proposal = ContextQualityProposal.model_validate(definition).model_dump(mode="json")
    if diagnostics["proposed_quality"]["proposal_id"] != digest(proposal):
        raise ValueError("Context quality proposal identity mismatch")
    area_version = digest(
        {
            "rectangle": diagnostics["diagnostic_rectangle"],
            "grid_step_degrees": diagnostics["grid_step_degrees"],
            "reviewed_sampling_area": False,
        }
    )
    product_definition_id = digest(
        {
            "source_plan_sha256": diagnostics["source_plan_sha256"],
            "proposal": proposal,
            "generation": "final_04.1",
            "evidence_role": "regional_context",
        }
    )
    observations, seen = [], set()
    for day in diagnostics["daily"]:
        if day["processing_generation"] != "final" or day["product_version"] != "04.1":
            raise ValueError("Interim context cannot enter final preview")
        when = datetime.fromisoformat(day["time_utc"])
        if (
            when.tzinfo is None
            or when.astimezone(timezone.utc).date().isoformat() != day["day"]
            or day["day"] in seen
        ):
            raise ValueError("Duplicate or inconsistent context date")
        seen.add(day["day"])
        quality = day["proposed_quality_preview"]
        if (
            quality.get("scientific_approval") is not False
            or quality.get("native_sample_area_evidence") is not False
        ):
            raise ValueError(
                "Context quality preview cannot assert scientific acceptance"
            )
        value = quality["sst_celsius"]
        if value is not None and (
            type(value) not in (int, float)
            or not np.isfinite(value)
            or not -3 <= value <= 45
        ):
            raise ValueError("Invalid context SST value")
        row = {
            "area_id": area_id,
            "area_version": area_version,
            "product_definition_id": product_definition_id,
            "granule_id": validate_id(day["granule_id"]),
            "raw_sha256": validate_id(day["raw_sha256"]),
            "source_diagnostics_id": diagnostics["diagnostics_id"],
            "source_manifest_sha256": validate_id(
                diagnostics["source_manifest_sha256"]
            ),
            "source_url": day["source_url"],
            "time_utc": when.isoformat(),
            "measurement_type": "satellite_in_situ_analysis",
            "temporal_statistic": "daily_foundation_analysis",
            "processing_generation": "final",
            "product_version": "04.1",
            "status": "valid"
            if quality["meets_proposed_support"] and value is not None
            else "insufficient_support",
            "sst_celsius": value,
            "warnings": quality["warnings"],
            "valid_fraction": quality["valid_fraction_of_open_ocean"],
            "valid_ocean_points": quality["valid_ocean_points"],
            "area_is_reviewed": False,
            "scientific_publication": False,
            "native_sample_area_evidence": False,
        }
        observations.append({**row, "observation_id": digest(row)})
    return observations


def _collection_time(member):
    """Use a reported local date when supplied; otherwise retain the reported day.

    Date-only records have no observed clock or reliable timezone conversion.
    The user explicitly chose Japan midday; this is recorded as an assumption.
    """
    raw = member.get("collection_time_utc")
    if member.get("temporal_precision") == "date":
        original = member.get("collection_date_local") or member.get("collection_date")
        if not original:
            original = raw
        if not original:
            raise ValueError("Collection date unavailable")
        day = date.fromisoformat(str(original)[:10])
        when = datetime.combine(day, time(12), JAPAN).astimezone(timezone.utc)
        return when, {
            "collection_time_basis": "assumed_midday_Asia_Tokyo",
            "collection_time_assumed": True,
            "original_reported_date": str(original),
        }
    if not raw:
        raise ValueError("Collection time unavailable")
    when = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    if when.tzinfo is None:
        raise ValueError("Collection time must be timezone qualified")
    return when.astimezone(timezone.utc), {
        "collection_time_basis": "reported_timestamp",
        "collection_time_assumed": False,
        "original_reported_timestamp": str(raw),
    }


def preview_historical_matching(members, observations, panel_id):
    """24h first; retry at 48h only when >20% of linkable members are unmatched.

    Missing area/time support is separate from temporal misses. Adjacent-day
    links keep actual source timestamps, so a final-series gap is never filled
    or relabelled as an observed temperature on that date.
    """
    validate_id(panel_id)
    if len(members) > 10000 or len(observations) > MAX_OBSERVATIONS:
        raise ValueError("Provisional matching resource limit exceeded")
    identities = [validate_id(m["physical_sample_id"]) for m in members]
    if len(set(identities)) != len(identities):
        raise ValueError("Duplicate provisional collection identity")
    # Run the existing strict observation validator even with no eligible members.
    link_sample_time([], observations, panel_id, max_time_hours=24)
    for row in observations:
        if row["status"] == "valid":
            value = row["sst_celsius"]
            if (
                type(value) not in (int, float)
                or not np.isfinite(value)
                or not -3 <= value <= 45
            ):
                raise ValueError("Invalid matching SST value")
    supported_areas = {
        (r["area_id"], r["area_version"])
        for r in observations
        if r["status"] == "valid"
    }
    eligible, unavailable, assumptions = [], [], {}
    for member in members:
        identity = member["physical_sample_id"]
        try:
            when, assumption = _collection_time(member)
        except (TypeError, ValueError):
            unavailable.append(
                {"physical_sample_id": identity, "status": "collection_time_unresolved"}
            )
            continue
        assumption = {
            **assumption,
            "sample_identity_status": member.get("identity_status", "unspecified"),
            "member_warnings": member.get("warnings", []),
        }
        assumptions[identity] = assumption
        if (member["area_id"], member["area_version"]) not in supported_areas:
            unavailable.append(
                {
                    "physical_sample_id": identity,
                    "status": "sst_area_support_unavailable",
                    **assumption,
                }
            )
            continue
        eligible.append({**member, "collection_time_utc": when.isoformat()})
    primary, pending = link_sample_time(
        eligible, observations, panel_id, max_time_hours=24
    )
    fraction = len(pending) / len(eligible) if eligible else None
    extended = fraction is not None and fraction > 0.2
    fallback = []
    if extended:
        waiting = {r["physical_sample_id"] for r in pending}
        fallback, pending = link_sample_time(
            [m for m in eligible if m["physical_sample_id"] in waiting],
            observations,
            panel_id,
            max_time_hours=48,
        )
    indexed = {r["observation_id"]: r for r in observations}
    links = []
    for rows, window in ((primary, 24), (fallback, 48)):
        for row in rows:
            identity = row["physical_sample_id"]
            source = indexed[row["observation_ids"][0]]
            links.append(
                {
                    **row,
                    **assumptions[identity],
                    "window_used_hours": window,
                    "extended_window": window == 48,
                    "source_warnings": source.get("warnings", []),
                    "source_time_utc": source["time_utc"],
                    "source_japan_date": datetime.fromisoformat(source["time_utc"])
                    .astimezone(JAPAN)
                    .date()
                    .isoformat(),
                }
            )
    result = {
        "schema_version": 1,
        "algorithm": ALGORITHM,
        "status": "provisional_local_preview",
        "source_panel_id": panel_id,
        "source_members_sha256": digest(members),
        "source_observation_ids": sorted(indexed),
        "links": sorted(links, key=lambda r: r["physical_sample_id"]),
        "unmatched": sorted(
            [
                *unavailable,
                *({**r, **assumptions[r["physical_sample_id"]]} for r in pending),
            ],
            key=lambda r: r["physical_sample_id"],
        ),
        "coverage": {
            "reported_collections": len(members),
            "otherwise_linkable_collections": len(eligible),
            "matched_within_24_hours": len(primary),
            "temporal_unmatched_fraction_at_24_hours": fraction,
            "extension_trigger_fraction": 0.2,
            "extension_applied": extended,
            "matched_within_extended_48_hours": len(fallback),
        },
        "classification_or_physical_identity_approved": False,
        "scientific_publication": False,
        "database_access": False,
        "cloud_writes": False,
    }
    return {**result, "preview_id": digest(result)}


def preview_relative_temperature_bins(observations):
    """Region/season thirds from supported daily SST, independent of fish samples."""
    if len(observations) > MAX_OBSERVATIONS:
        raise ValueError("Relative temperature baseline resource limit exceeded")
    groups, days, products = defaultdict(list), set(), set()
    versions = {}
    source_ids = set()
    for row in observations:
        identity = validate_id(row["observation_id"])
        if identity in source_ids or identity != digest(
            {k: v for k, v in row.items() if k != "observation_id"}
        ):
            raise ValueError("Relative SST observation identity conflict")
        source_ids.add(identity)
        products.add(row["product_definition_id"])
        area = row["area_id"]
        if versions.setdefault(area, row["area_version"]) != row["area_version"]:
            raise ValueError("Relative baseline mixes versions of one region")
        if row.get("temporal_statistic") != "daily_foundation_analysis":
            raise ValueError("Relative baseline requires daily foundation analysis")
        when = datetime.fromisoformat(row["time_utc"])
        if when.tzinfo is None:
            raise ValueError("Relative baseline time must be timezone qualified")
        local = when.astimezone(JAPAN).date()
        if (area, local) in days:
            raise ValueError("Duplicate regional SST day")
        days.add((area, local))
        if row["status"] != "valid":
            continue
        value = row["sst_celsius"]
        if (
            type(value) not in (int, float)
            or not np.isfinite(value)
            or not -3 <= value <= 45
        ):
            raise ValueError("Invalid relative SST value")
        _, label = season(local)
        groups[(area, label)].append((local, float(value), identity))
    if len(products) > 1:
        raise ValueError("Relative baseline mixes SST products")
    partitions = []
    for (area, label), rows in sorted(groups.items()):
        values = [r[1] for r in rows]
        low, high = map(float, np.quantile(values, [1 / 3, 2 / 3]))
        tied = low >= high
        partitions.append(
            {
                "area_id": area,
                "area_version": versions[area],
                "season": label,
                "baseline_from": min(r[0] for r in rows).isoformat(),
                "baseline_to": max(r[0] for r in rows).isoformat(),
                "supported_days": len(rows),
                "low_max_celsius": low,
                "high_min_celsius": high,
                "status": "unpartitioned_ties"
                if tied
                else "relative_study_period_thirds",
                "warnings": ["short_baseline"] if len(rows) < 30 else [],
                "daily_bins": [
                    {
                        "observation_id": identity,
                        "category": "unpartitioned_ties"
                        if tied
                        else "low"
                        if value <= low
                        else "high"
                        if value >= high
                        else "middle",
                    }
                    for _, value, identity in sorted(rows)
                ],
            }
        )
    result = {
        "schema_version": 1,
        "algorithm": "provisional-region-season-thirds-v1",
        "status": "provisional_local_preview",
        "calendar": "Asia/Tokyo",
        "source_observation_ids": sorted(source_ids),
        "partitions": partitions,
        "baseline_is_long_term_climatology": False,
        "scientific_publication": False,
    }
    return {**result, "preview_id": digest(result)}
