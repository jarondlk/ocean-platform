"""Explicit user-approved demo artifacts, separate from scientific registries.

Canonical classifications, physical identities and researcher approvals are never
changed or invented. Operators publish these immutable, reproducible results only
after recording the user's exact decision and the retained source bindings.
"""

from collections import Counter
from datetime import date, datetime
from typing import Literal

from pydantic import Field
from sqlalchemy import text

from db.connection import get_engine
from ingestion.immutable_bundle import canonical_bytes, digest
from preprocessing.edna_analysis import runtime_versions, taxon_key
from preprocessing.edna_detection_frequency import (
    TABLES as FREQUENCY_TABLES,
    build_detection_frequency,
    prepare_membership,
)
from preprocessing.historical_sst_matching import (
    preview_historical_matching,
    preview_relative_temperature_bins,
)
from preprocessing.research_recipe import (
    DetectionFrequencyRecipe,
    Hash,
    ResearchModel,
    SamplingRegistry,
    PhysicalMembership,
)
from preprocessing.research_sst import monthly_area_context

ALGORITHM = "user-approved-provisional-regional-demo-v1"
TABLES = (
    *FREQUENCY_TABLES,
    "area_month_sst",
    "sst_exclusions",
    "relative_sst_thresholds",
    "read_ranking",
)
FILES = {name + ".json" for name in (*TABLES, "recipe", "inputs")}
LIMITATIONS = [
    "User-approved provisional demo; no independent researcher or ANEMONE provider endorsement.",
    "Singleton occurrence proxies are not confirmed physical water collections; unknown classifications remain unchanged.",
    "Known controls and unresolved repeat groups are excluded. Empty or faulty tables are not zero detections.",
    "Read counts are sequencing signals, not fish abundance; methods and protocols remain separate.",
    "SST is 0.05-degree subsampled regional foundation analysis, not native coastal or sample-point temperature.",
    "Relative SST uses the available study-period region/season baseline, not a long-term climatology; no causal weather inference.",
    "One regional rectangle cannot establish within-region spatial redistribution.",
]


class DemoPartition(ResearchModel):
    kind: Literal["regional_season_thirds"] = "regional_season_thirds"
    low_max: None = None
    high_min: None = None


class ProvisionalRecipe(DetectionFrequencyRecipe):
    analysis_unit: Literal["provisional_singleton_occurrence"] = (
        "provisional_singleton_occurrence"
    )
    control_policy: Literal["known_controls_excluded_unknown_provisional"] = (
        "known_controls_excluded_unknown_provisional"
    )
    date_only_policy: Literal["assumed_Japan_midday"] = "assumed_Japan_midday"
    temperature_partition: DemoPartition


class ProvisionalMembership(PhysicalMembership):
    representative_policy: Literal["provisional_singleton_assay"] = (
        "provisional_singleton_assay"
    )


class ProvisionalSampling(SamplingRegistry):
    memberships: tuple[ProvisionalMembership, ...] = Field(
        min_length=1, max_length=10000
    )


class DemoDecision(ResearchModel):
    decision_origin: Literal["user"] = "user"
    approval_basis: Literal["explicit_user_approved_provisional_demo"] = (
        "explicit_user_approved_provisional_demo"
    )
    reviewer_display_label: Literal["ANEMONE"] = "ANEMONE"
    provider_endorsement: Literal[False] = False
    independent_researcher_approval: Literal[False] = False
    user_instruction: str = Field(min_length=1, max_length=4000)
    rationale: str = Field(min_length=1, max_length=4000)
    recorded_at_utc: datetime
    source_sha256: Hash
    sampling_sha256: Hash
    period_preview_id: Hash


def validate_inputs(recipe, inputs):
    from ingestion.edna_analysis_bundle import validate_input_provenance

    if set(inputs) != {
        "canonical",
        "provisional_sampling",
        "period_preview",
        "user_decision",
        "runtime",
    }:
        raise ValueError("Incomplete provisional demo input contract")
    decision = DemoDecision.model_validate(inputs["user_decision"])
    if decision.recorded_at_utc.tzinfo is None:
        raise ValueError("Decision recording time requires a timezone")
    source, period = inputs["canonical"], inputs["period_preview"]
    validate_input_provenance(source)
    registry = ProvisionalSampling.model_validate(inputs["provisional_sampling"])
    if (
        decision.source_sha256 != digest(source)
        or decision.sampling_sha256 != digest(inputs["provisional_sampling"])
        or decision.period_preview_id != period.get("period_preview_id")
        or period.get("period_preview_id")
        != digest({k: v for k, v in period.items() if k != "period_preview_id"})
        or recipe.sst_panel_id != period["period_preview_id"]
        or registry.region_id != recipe.region_id
        or period["area_id"] not in {a.area_id for a in registry.areas}
        or period.get("status") != "complete_unpublished_regional_context_preview"
        or period.get("scientific_approval") is not False
        or period.get("scientific_publication") is not False
        or period.get("native_sample_area_evidence") is not False
    ):
        raise ValueError("Provisional decision/source/period binding mismatch")
    if len(registry.areas) != 1:
        raise ValueError("This demo supports one explicit regional rectangle")
    area = registry.areas[0]
    bounds = period["definition"]["diagnostic_rectangle"]
    if any(getattr(area, k) != bounds[k] for k in ("west", "east", "south", "north")):
        raise ValueError("Demo rectangle differs from retained SST processing")
    if area.geometry_type != "reviewed_regional_context_rectangle":
        raise ValueError("A demo rectangle cannot assert a provider footprint")
    if (
        period["period"]
        != {"first_year": recipe.time_from.year, "last_year": recipe.time_to.year}
        or recipe.time_from.isoformat() != f"{recipe.time_from.year}-01-01"
        or recipe.time_to.isoformat() != f"{recipe.time_to.year}-12-31"
    ):
        raise ValueError("Demo interval requires the exact processed calendar years")
    observations = period["observations"]
    seen = set()
    for row in observations:
        if (
            row["observation_id"]
            != digest({k: v for k, v in row.items() if k != "observation_id"})
            or row["observation_id"] in seen
            or row["processing_generation"] != "final"
            or row["product_version"] != "04.1"
            or row["area_id"] != area.area_id
            or row["native_sample_area_evidence"] is not False
        ):
            raise ValueError("Invalid final regional observation")
        seen.add(row["observation_id"])
    if (
        preview_relative_temperature_bins(observations)
        != period["relative_temperature"]
    ):
        raise ValueError("Relative seasonal baseline differs from full daily inputs")
    # These are proposals, never persisted physical membership or classification.
    samples = {s["sample_id"]: s for s in source["edna_sample"]}
    groups = Counter(
        (
            s.get("provider_project_id"),
            s.get("original_sample_label"),
            s.get("collection_date_utc"),
        )
        for s in samples.values()
    )
    for member in registry.memberships:
        if len(member.occurrences) != 1:
            raise ValueError("Repeated collection identities require later review")
        sample = samples.get(member.occurrences[0].sample_id)
        if (
            not sample
            or groups[
                (
                    sample.get("provider_project_id"),
                    sample.get("original_sample_label"),
                    sample.get("collection_date_utc"),
                )
            ]
            != 1
        ):
            raise ValueError("Provisional membership is not a singleton occurrence")
        if member.physical_sample_id != digest(
            {
                "proposal": "one-source-collection-occurrence",
                "sample_id": sample["sample_id"],
            }
        ):
            raise ValueError(
                "Demo identity must be an explicit singleton occurrence proxy"
            )
    prepare_membership(recipe, source, list(registry.areas), list(registry.memberships))
    return registry


def build_demo(recipe, inputs):
    registry = validate_inputs(recipe, inputs)
    source, period = inputs["canonical"], inputs["period_preview"]
    areas, memberships = list(registry.areas), list(registry.memberships)
    members, _ = prepare_membership(recipe, source, areas, memberships)
    # Bind derived observations to this user-approved rectangle, retaining the
    # exact upstream preview identity; no scientific approval flag is changed.
    versions = {a.area_id: digest(a.model_dump(mode="json")) for a in areas}
    observations = []
    for original in period["observations"]:
        row = {k: v for k, v in original.items() if k != "observation_id"}
        row.update(
            source_observation_id=original["observation_id"],
            area_version=versions[row["area_id"]],
        )
        observations.append({**row, "observation_id": digest(row)})
    matching = preview_historical_matching(
        [{**m, "identity_status": "provisional_singleton_occurrence"} for m in members],
        observations,
        recipe.sst_panel_id,
    )
    partitions = {
        (p["area_id"], p["season"]): p
        for p in period["relative_temperature"]["partitions"]
    }
    indexed = {m["physical_sample_id"]: m for m in members}
    links = []
    for link in matching["links"]:
        member = indexed[link["physical_sample_id"]]
        part = partitions[(member["area_id"], member["season"])]
        value = link["sst_celsius"]
        label = (
            "unpartitioned_ties"
            if part["status"] == "unpartitioned_ties"
            else "low"
            if value <= part["low_max_celsius"]
            else "high"
            if value >= part["high_min_celsius"]
            else "middle"
        )
        links.append(
            {
                **link,
                "relative_bin": label,
                "baseline_from": part["baseline_from"],
                "baseline_to": part["baseline_to"],
            }
        )
    tables = build_detection_frequency(recipe, source, areas, memberships, links)
    # The first demo has one regional rectangle and unresolved species-specific
    # sardine evidence. Do not export zero maps or spatial-change rankings that
    # could be mistaken for absence or distribution evidence.
    for name in (
        "spatial",
        "spatial_temperature_bins",
        "matched_panel",
        "change_ranking",
        "changes",
        "follow_through",
    ):
        tables[name] = []
    tables["area_month_sst"] = monthly_area_context(
        observations,
        areas,
        recipe.spatial_year,
        min_day_fraction=recipe.sst_min_month_day_fraction,
    )
    tables["sst_exclusions"] = [
        *matching["unmatched"],
        *({"status": "final_series_gap", **g} for g in period["final_series_gaps"]),
    ]
    tables["relative_sst_thresholds"] = [
        {k: v for k, v in p.items() if k != "daily_bins"}
        for p in period["relative_temperature"]["partitions"]
    ]
    reads = Counter()
    lookup = {m["assay_id"]: m for m in members}
    taxa = {}
    for row in source["edna_detection"]:
        if (
            row.get("active", True) is not True
            or row["assignment_method"] != recipe.assignment_method
            or row["assay_id"] not in lookup
            or row.get("class") not in recipe.fish_classes
        ):
            continue
        lineage = taxon_key(row, "species")
        if not lineage:
            continue
        key = digest(lineage)
        taxa[key] = row["species"]
        m = lookup[row["assay_id"]]
        reads[(m["protocol_id"], key, "all", "all")] += row["read_count"]
        reads[(m["protocol_id"], key, "year", str(m["year"]))] += row["read_count"]
        reads[
            (m["protocol_id"], key, "season", f"{m['season_year']}-{m['season']}")
        ] += row["read_count"]
    tables["read_ranking"] = [
        {
            "protocol_id": p,
            "taxon_key": key,
            "species": taxa[key],
            "period_kind": kind,
            "period": period_name,
            "read_count": count,
            "metric": "sequencing_read_sum_not_abundance",
        }
        for (p, key, kind, period_name), count in sorted(
            reads.items(),
            key=lambda pair: (pair[0][0], pair[0][2], pair[0][3], -pair[1], pair[0][1]),
        )
    ]
    serialized = recipe.model_dump(mode="json")
    identity = digest(
        {"algorithm": ALGORITHM, "recipe": serialized, "input_sha256": digest(inputs)}
    )
    for name, rows in tables.items():
        for row in rows:
            row["result_id"] = digest([identity, name, row])
    result = {
        "schema_version": 3,
        "analysis_kind": "provisional_demo",
        "analysis_id": identity,
        "algorithm_version": ALGORITHM,
        "recipe": serialized,
        "inputs": inputs,
        "input_sha256": digest(inputs),
        "tables": tables,
        "limitations": LIMITATIONS,
    }
    if len(canonical_bytes(result)) > 128 * 1024**2:
        raise ValueError("Provisional demo byte limit exceeded")
    return result


def demo_status(bundle):
    """Fail closed when canonical bindings change; no scientific review is implied."""
    source = bundle["inputs"]["canonical"]
    try:
        with get_engine().connect() as connection, connection.begin():
            connection.exec_driver_sql(
                "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY"
            )
            connection.exec_driver_sql("SET LOCAL statement_timeout='30s'")
            for table, key, ids in (
                (
                    "edna_sample",
                    "sample_id",
                    [r["sample_id"] for r in source["edna_sample"]],
                ),
                (
                    "edna_assay",
                    "sample_id",
                    [r["sample_id"] for r in source["edna_sample"]],
                ),
                (
                    "edna_detection",
                    "assay_id",
                    [r["assay_id"] for r in source["edna_assay"]],
                ),
                (
                    "external_source_file",
                    "source_file_id",
                    [r["source_file_id"] for r in source["external_source_file"]],
                ),
                (
                    "external_source_snapshot",
                    "snapshot_id",
                    [r["snapshot_id"] for r in source["external_source_snapshot"]],
                ),
            ):
                rows = (
                    connection.execute(
                        text(
                            f"SELECT * FROM {table} WHERE {key}=ANY(:ids) LIMIT :limit"
                        ),
                        {"ids": ids, "limit": len(source[table]) + 1},
                    )
                    .mappings()
                    .all()
                )
                current_rows = [
                    {
                        k: v.isoformat() if isinstance(v, (datetime, date)) else v
                        for k, v in row.items()
                    }
                    for row in rows
                ]
                if sorted(current_rows, key=digest) != sorted(
                    source[table], key=digest
                ):
                    return "historical"
            pubs = (
                connection.execute(
                    text(
                        "SELECT channel,generation_id,manifest_sha256 FROM corpus_publication WHERE channel IN ('anemone-canonical','edna-canonical','edna')"
                    )
                )
                .mappings()
                .all()
            )
            current = {
                r["channel"]: {k: r[k] for k in ("generation_id", "manifest_sha256")}
                for r in pubs
            }
            if current != source["publication"]:
                return "historical"
        return (
            "current"
            if bundle["inputs"]["runtime"] == runtime_versions()
            else "historical"
        )
    except Exception:
        return "current_state_unavailable"
