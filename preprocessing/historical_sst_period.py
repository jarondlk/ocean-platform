"""Reconcile bounded monthly previews into a complete, unpublished period.

This does not approve a sampling footprint or write scientific publications.
Raw verification remains the upstream monthly processor's responsibility.
"""

from collections import Counter
from datetime import date, timedelta

from ingestion.immutable_bundle import digest
from ingestion.sst_context_integration import build_context_integration_plan
from preprocessing.historical_sst_matching import (
    preview_context_observations,
    preview_relative_temperature_bins,
)


def period_batches(plan, report, first_year, last_year):
    if (
        type(first_year) is not int
        or type(last_year) is not int
        or not 2002 <= first_year <= last_year <= 2100
        or last_year - first_year > 9
    ):
        raise ValueError("Period requires at most ten ordered calendar years")
    integration = build_context_integration_plan(plan, report)
    batches = [
        b
        for b in integration["batches"]
        if first_year <= int(b["month"][:4]) <= last_year
    ]
    start, end = date(first_year, 1, 1), date(last_year, 12, 31)
    days = {
        (start + timedelta(days=i)).isoformat() for i in range((end - start).days + 1)
    }
    final = {day for b in batches for day in b["days"]}
    gaps = [g for g in integration["unsupported_final_dates"] if g["day"] in days]
    if final & {g["day"] for g in gaps} or final | {g["day"] for g in gaps} != days:
        raise ValueError("Archive does not reconcile the requested full period")
    return integration, batches, gaps


def build_period_preview(plan, report, diagnostics, area_id, first_year, last_year):
    integration, batches, gaps = period_batches(plan, report, first_year, last_year)
    expected = {b["batch_id"]: b for b in batches}
    if not isinstance(diagnostics, list) or len(diagnostics) != len(expected):
        raise ValueError("All exact monthly batches are required for period completion")
    seen, observations, bindings, common = set(), [], [], None
    for diagnostic in diagnostics:
        identity = diagnostic["batch_id"]
        if identity not in expected or identity in seen:
            raise ValueError("Duplicate or out-of-period diagnostic batch")
        seen.add(identity)
        batch = expected[identity]
        if (
            diagnostic["source_plan_sha256"] != plan["plan_sha256"]
            or diagnostic["source_report_id"] != report["report_id"]
            or diagnostic["integration_plan_id"] != integration["integration_plan_id"]
            or [d["day"] for d in diagnostic["daily"]] != batch["days"]
            or [d["request_sha256"] for d in diagnostic["daily"]]
            != batch["request_sha256s"]
            or diagnostic["archive_unsupported_final_dates"]
            != integration["unsupported_final_dates"]
        ):
            raise ValueError("Monthly diagnostic source/calendar binding mismatch")
        rules = {
            key: diagnostic[key]
            for key in (
                "diagnostic_rectangle",
                "proposed_quality",
                "source_archive_uri",
                "grid_step_degrees",
            )
        }
        if common is not None and rules != common:
            raise ValueError("Period cannot combine different regions or quality rules")
        common = rules
        observations.extend(preview_context_observations(diagnostic, area_id))
        bindings.append(
            {
                "batch_id": identity,
                "diagnostics_id": diagnostic["diagnostics_id"],
                "source_manifest_sha256": diagnostic["source_manifest_sha256"],
            }
        )
    observations.sort(key=lambda row: row["time_utc"])
    years = {}
    for year in range(first_year, last_year + 1):
        rows = [r for r in observations if int(r["time_utc"][:4]) == year]
        years[str(year)] = {
            "final_days": len(rows),
            "supported_days": sum(r["status"] == "valid" for r in rows),
            "insufficient_support_days": sum(r["status"] != "valid" for r in rows),
            "final_series_gaps": [g for g in gaps if int(g["day"][:4]) == year],
            "warning_counts": dict(
                sorted(Counter(w for r in rows for w in r["warnings"]).items())
            ),
        }
    result = {
        "schema_version": 1,
        "algorithm": "historical-regional-context-period-preview-v1",
        "status": "complete_unpublished_regional_context_preview",
        "source_plan_sha256": plan["plan_sha256"],
        "source_report_id": report["report_id"],
        "integration_plan_id": integration["integration_plan_id"],
        "period": {"first_year": first_year, "last_year": last_year},
        "area_id": area_id,
        "definition": common,
        "batches": sorted(bindings, key=lambda b: b["batch_id"]),
        "observations": observations,
        "year_coverage": years,
        "final_series_gaps": gaps,
        "relative_temperature": preview_relative_temperature_bins(observations),
        "scientific_approval": False,
        "scientific_publication": False,
        "native_sample_area_evidence": False,
        "limitations": [
            "0.05-degree subsampled regional context, not native coastal/sample-area SST.",
            "The explicit rectangle is a provisional demo region, not a confirmed sampling footprint.",
            "Interim generations remain excluded; gaps are not filled.",
            "Completion is processing evidence, not permission to serve unapproved scientific results.",
        ],
    }
    return {**result, "period_preview_id": digest(result)}
