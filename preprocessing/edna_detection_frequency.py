"""Sparse, deterministic descriptive frequencies over reviewed physical samples.

No provider acquisition, SQL, model calls, identity inference or publication here.
All denominator memberships are fixed before taxon presence is reduced.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from fractions import Fraction
from datetime import date, datetime
import json
import math
from zoneinfo import ZoneInfo

from ingestion.immutable_bundle import canonical_bytes, digest
from ingestion.research_readiness import method_status
from preprocessing.edna_analysis import protocol, taxon_key
from preprocessing.edna_eligibility import PROTOCOL_FIELDS
from preprocessing.research_recipe import (
    DetectionFrequencyRecipe,
    PhysicalMembership,
    ReviewedArea,
)

ALGORITHM_VERSION = "physical-detection-frequency-v3"
READABLE_ALGORITHM_VERSIONS = {
    "physical-detection-frequency-v1",
    "physical-detection-frequency-v2",
    ALGORITHM_VERSION,
}
MAX_SAMPLES = 10_000
MAX_DETECTIONS = 1_000_000
MAX_TAXA = 5_000
MAX_RESULT_ROWS = 200_000
MAX_RESULT_BYTES = 128 * 1024 * 1024
TABLES = (
    "membership",
    "exclusions",
    "coverage",
    "ranking",
    "series",
    "month_coverage",
    "spatial",
    "temperature_bins",
    "temperature_contrasts",
    "temperature_strata",
    "temperature_series",
    "spatial_temperature_bins",
    "stratum_coverage",
    "matched_panel",
    "change_ranking",
    "changes",
    "follow_through",
    "sst_links",
    "methods",
)


def _index(rows, key, maximum):
    if len(rows) > maximum:
        raise ValueError(f"{key} row limit exceeded")
    indexed = {r[key]: r for r in rows}
    if len(indexed) != len(rows):
        raise ValueError(f"Duplicate {key}")
    return indexed


def registry_versions(areas, memberships):
    return {
        "region_version": digest(
            sorted(
                (a.model_dump(mode="json") for a in areas), key=lambda a: a["area_id"]
            )
        ),
        "identity_version": digest(
            sorted(
                (m.model_dump(mode="json") for m in memberships),
                key=lambda m: m["physical_sample_id"],
            )
        ),
    }


def season(when: date) -> tuple[int, str]:
    if when.month in (12, 1, 2):
        return when.year + (when.month == 12), "DJF"
    return when.year, {3: "MAM", 4: "MAM", 5: "MAM", 6: "JJA", 7: "JJA", 8: "JJA"}.get(
        when.month, "SON"
    )


def _season_interval(year, label):
    if label == "DJF":
        return date(year - 1, 12, 1), date(year, 3, 1)
    month = {"MAM": 3, "JJA": 6, "SON": 9}[label]
    return date(year, month, 1), date(year, month + 3, 1)


def prepare_membership(recipe, source, areas, memberships):
    """Validate evidence bindings; stale decisions exclude units, never broaden scope."""
    provisional = recipe.analysis_unit == "provisional_singleton_occurrence"
    versions = registry_versions(areas, memberships)
    if versions != {
        "region_version": recipe.region_version,
        "identity_version": recipe.identity_version,
    }:
        raise ValueError("Reviewed registry generation mismatch")
    for key in ("canonical_generation", "classification_generation"):
        if source.get("generations", {}).get(key) != getattr(recipe, key):
            raise ValueError(f"{key} mismatch")
    area_index = _index([a.model_dump(mode="json") for a in areas], "area_id", 1000)
    sample_index = _index(source["edna_sample"], "sample_id", MAX_SAMPLES)
    assay_index = _index(source["edna_assay"], "assay_id", MAX_SAMPLES)
    if len(memberships) > MAX_SAMPLES:
        raise ValueError("Physical membership limit exceeded")
    seen_occurrences, seen_physical, selected, excluded = set(), set(), [], []
    for decision in sorted(memberships, key=lambda m: m.physical_sample_id):
        pid = decision.physical_sample_id
        if pid in seen_physical:
            raise ValueError("Duplicate physical sample")
        seen_physical.add(pid)
        ids = {o.sample_id for o in decision.occurrences}
        if ids & seen_occurrences:
            raise ValueError("Occurrence assigned to multiple physical samples")
        seen_occurrences.update(ids)
        area = area_index.get(decision.area_id)
        assay = assay_index.get(decision.representative_assay_id)
        reasons = []
        if not area or digest(area) != decision.area_version:
            reasons.append("stale_area_decision")
        elif area["region_id"] != recipe.region_id:
            reasons.append("outside_selected_region")
        rows = [sample_index.get(o.sample_id) for o in decision.occurrences]
        if any(
            not r or r.get("scientific_content_sha256") != o.scientific_content_sha256
            for o, r in zip(decision.occurrences, rows)
        ):
            reasons.append("stale_identity_evidence")
        if any(
            not r
            or r.get("active", True) is not True
            or r.get("sample_kind")
            not in ({"environmental", "unknown"} if provisional else {"environmental"})
            or (
                r.get("is_control") is True
                if provisional
                else r.get("is_control") is not False
            )
            for r in rows
        ):
            reasons.append("inactive_control_or_unknown")
        if provisional and len(ids) != 1:
            reasons.append("provisional_repeated_identity_unresolved")
        if (
            not assay
            or assay.get("active", True) is not True
            or assay["sample_id"] not in ids
            or assay.get("scientific_content_sha256")
            != decision.representative_assay_sha256
        ):
            reasons.append("stale_representative_assay")
        sample = sample_index.get(assay["sample_id"]) if assay else None
        local = None
        if sample and sample.get("temporal_precision") == "datetime":
            try:
                when = datetime.fromisoformat(
                    str(sample["collection_date_utc"]).replace("Z", "+00:00")
                )
                if when.tzinfo is None:
                    raise ValueError("Unqualified source time")
                local = when.astimezone(ZoneInfo(recipe.calendar)).date()
            except (KeyError, TypeError, ValueError):
                pass
        if provisional and sample and sample.get("temporal_precision") == "date":
            try:
                from datetime import time

                local = date.fromisoformat(str(sample["collection_date_utc"])[:10])
                when = datetime.combine(local, time(12), ZoneInfo(recipe.calendar))
            except (KeyError, TypeError, ValueError):
                pass
        if local is None:
            reasons.append("collection_calendar_unresolved")
        elif not recipe.time_from <= local <= recipe.time_to:
            reasons.append("outside_selected_period")
        if assay:
            if not all(
                assay.get(k) is not None and str(assay[k]).strip()
                for k in PROTOCOL_FIELDS
            ):
                reasons.append("protocol_incomplete")
            status = method_status(assay, recipe.assignment_method)
            if status != "available_nonempty":
                reasons.append(
                    "empty_method_requires_qc_review"
                    if status == "valid_empty_requires_qc_review"
                    else "method_unavailable"
                )
        common = {
            "physical_sample_id": pid,
            "occurrence_ids": sorted(ids),
            "decision_id": digest(decision.model_dump(mode="json")),
            "area_id": decision.area_id,
        }
        if provisional:
            common.update(
                analysis_unit="provisional_singleton_occurrence",
                physical_identity_confirmed=False,
                environmental_classification_confirmed=all(
                    r
                    and r.get("sample_kind") == "environmental"
                    and r.get("is_control") is False
                    for r in rows
                ),
                collection_time_assumed=bool(
                    sample and sample.get("temporal_precision") == "date"
                ),
            )
        if reasons:
            excluded.append({**common, "reasons": sorted(set(reasons))})
        else:
            sy, sl = season(local)
            selected.append(
                {
                    **common,
                    "assay_id": assay["assay_id"],
                    "protocol_id": digest(protocol(assay)),
                    "collection_date": local.isoformat(),
                    "collection_time_utc": when.isoformat(),
                    "year": local.year,
                    "month": local.strftime("%Y-%m"),
                    "season_year": sy,
                    "season": sl,
                    "area_version": decision.area_version,
                }
            )
    # Every unreviewed occurrence stays visible, even if classification is environmental.
    for sid in sorted(sample_index.keys() - seen_occurrences):
        excluded.append(
            {
                "physical_sample_id": None,
                "occurrence_ids": [sid],
                "decision_id": None,
                "area_id": None,
                "reasons": ["unreviewed_physical_identity"],
            }
        )
    return selected, excluded


def _presence(recipe, source, members):
    detections = source.get("edna_detection", [])
    _index(detections, "detection_id", MAX_DETECTIONS)
    selected_assays = {m["assay_id"]: m["physical_sample_id"] for m in members}
    reads, taxa, method_counts = Counter(), {}, Counter()
    for row in detections:
        if (
            row.get("active", True) is not True
            or row.get("assignment_method") != recipe.assignment_method
        ):
            continue
        aid = row["assay_id"]
        if aid not in selected_assays:
            continue
        method_counts[aid] += 1
        count = row.get("read_count")
        if isinstance(count, bool) or not isinstance(count, int) or count < 0:
            raise ValueError("Invalid detection read count")
        if row.get("class") not in recipe.fish_classes:
            continue
        lineage = taxon_key(row, "species")
        if lineage is None:
            continue
        key = digest(lineage)
        taxa[key] = dict(taxon_key=key, species=row["species"], lineage=dict(lineage))
        if len(taxa) > MAX_TAXA:
            raise ValueError("Taxon limit exceeded")
        reads[(selected_assays[aid], key)] += count
    assay_index = {a["assay_id"]: a for a in source["edna_assay"]}
    for aid in selected_assays:
        raw = assay_index[aid]["community_availability_json"]
        availability = json.loads(raw) if isinstance(raw, str) else raw
        if method_counts[aid] != availability[recipe.assignment_method]["row_count"]:
            raise ValueError(
                "Complete method table does not reconcile with assay availability"
            )
    presence = defaultdict(set)
    for (pid, key), count in reads.items():
        if count >= recipe.min_read_count:
            presence[key].add(pid)
    return dict(presence), taxa


def build_detection_frequency(
    recipe: DetectionFrequencyRecipe,
    source: dict,
    areas: list[ReviewedArea],
    memberships: list[PhysicalMembership],
    sst_links=None,
):
    members, exclusions = prepare_membership(recipe, source, areas, memberships)
    presence, taxa = _presence(recipe, source, members)
    tables = {name: [] for name in TABLES}
    tables["membership"], tables["exclusions"] = members, exclusions
    by_protocol = defaultdict(list)
    for member in members:
        by_protocol[member["protocol_id"]].append(member)
    # Reject a fragmented protocol/taxon cohort before constructing result grids.
    years = recipe.time_to.year - recipe.time_from.year + 2
    upper_rows = 0
    for cohort in by_protocol.values():
        ids = {m["physical_sample_id"] for m in cohort}
        ntaxa = sum(bool(ids & values) for values in presence.values())
        nstrata = len({(m["area_id"], m["season"]) for m in cohort})
        upper_rows += (
            min(ntaxa, 10) * 17 * years
            + 17 * years
            + ntaxa * (10 + nstrata)
            + len(cohort)
            + 12
            + 5 * len(areas)
            + min(ntaxa, 3) * nstrata * (years + 1)
        )
    if upper_rows > MAX_RESULT_ROWS:
        raise ValueError("Research result row budget exceeded before allocation")
    links = _index(sst_links or [], "physical_sample_id", MAX_SAMPLES)
    if links and recipe.sst_panel_id is None:
        raise ValueError("SST links require a pinned panel")
    member_ids = {m["physical_sample_id"] for m in members}
    if links.keys() - member_ids:
        raise ValueError("SST link outside eligible membership")
    for link in links.values():
        value = link.get("sst_celsius")
        if (
            link.get("panel_id") != recipe.sst_panel_id
            or link.get("status") != "matched"
            or isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
            or not -3 <= value <= 45
            or not link.get("source_granule_ids")
            or not link.get("observation_ids")
        ):
            raise ValueError("Invalid or untraceable SST link")
    tables["sst_links"] = sorted(links.values(), key=lambda r: r["physical_sample_id"])

    def rate(key, cohort):
        ids = {m["physical_sample_id"] for m in cohort}
        detected = sorted(ids & presence.get(key, set()))
        return {
            "detected": len(detected),
            "eligible": len(ids),
            "frequency": len(detected) / len(ids) if ids else None,
            "low_support": len(ids) < recipe.min_stratum_samples,
            "member_ids": sorted(ids),
            "detected_member_ids": detected,
            "sampling_status": "unsampled"
            if not ids
            else "sampled_detected"
            if detected
            else "sampled_not_detected",
        }

    for proto, cohort in sorted(by_protocol.items()):
        common = {"protocol_id": proto, "assignment_method": recipe.assignment_method}
        keys = sorted(
            (
                k
                for k in presence
                if presence[k] & {m["physical_sample_id"] for m in cohort}
            ),
            key=lambda k: (-rate(k, cohort)["detected"], k),
        )
        top = keys[:10]
        for position, key in enumerate(top, 1):
            tables["ranking"].append(
                {**common, **taxa[key], "position": position, **rate(key, cohort)}
            )
        groups = defaultdict(list)
        for member in cohort:
            groups[(member["area_id"], member["month"])].append(member)
        for (area, month), group in sorted(groups.items()):
            tables["coverage"].append(
                {
                    **common,
                    "area_id": area,
                    "month": month,
                    "eligible": len(group),
                    "member_ids": sorted(m["physical_sample_id"] for m in group),
                    "sst_matched": sum(m["physical_sample_id"] in links for m in group),
                }
            )
        last_season_year = season(recipe.time_to)[0]
        all_periods = []
        for year in range(
            recipe.time_from.year, max(recipe.time_to.year, last_season_year) + 1
        ):
            periods = []
            if year <= recipe.time_to.year:
                periods.append(
                    (
                        "year",
                        str(year),
                        [m for m in cohort if m["year"] == year],
                        date(year, 1, 1) < recipe.time_from
                        or date(year, 12, 31) > recipe.time_to,
                    )
                )
            for label in ("DJF", "MAM", "JJA", "SON"):
                start, end = _season_interval(year, label)
                if start > recipe.time_to or end <= recipe.time_from:
                    continue
                partial = (
                    start < recipe.time_from
                    or end.toordinal() - 1 > recipe.time_to.toordinal()
                )
                periods.append(
                    (
                        "season",
                        f"{year}-{label}",
                        [
                            m
                            for m in cohort
                            if (m["season_year"], m["season"]) == (year, label)
                        ],
                        partial,
                    )
                )
            for month in range(1, 13):
                start = date(year, month, 1)
                end = date(year + (month == 12), month % 12 + 1, 1)
                if start > recipe.time_to or end <= recipe.time_from:
                    continue
                label = f"{year}-{month:02d}"
                periods.append(
                    (
                        "month",
                        label,
                        [m for m in cohort if m["month"] == label],
                        start < recipe.time_from
                        or end.toordinal() - 1 > recipe.time_to.toordinal(),
                    )
                )
            for kind, label, group, partial in periods:
                all_periods.append((kind, label, group, partial))
                matched = [m for m in group if m["physical_sample_id"] in links]
                sst = [links[m["physical_sample_id"]]["sst_celsius"] for m in matched]
                for key in top:
                    tables["series"].append(
                        {
                            **common,
                            "taxon_key": key,
                            "period_kind": kind,
                            "period": label,
                            "partial_period": partial,
                            **rate(key, group),
                            "sst_matched": len(matched),
                            "sample_time_sst_mean_celsius": sum(sst) / len(sst)
                            if sst
                            else None,
                        }
                    )

        # The winning month depends only on eligible area coverage and effort.
        months = []
        for month in range(1, 13):
            label = f"{recipe.spatial_year}-{month:02d}"
            group = [m for m in cohort if m["month"] == label]
            areas_in_month = Counter(m["area_id"] for m in group)
            months.append(
                {
                    **common,
                    "month": label,
                    "sampled_areas": len(areas_in_month),
                    "eligible": len(group),
                    "supported_areas": sum(
                        n >= recipe.min_stratum_samples for n in areas_in_month.values()
                    ),
                }
            )
        winner = min(
            months, key=lambda r: (-r["sampled_areas"], -r["eligible"], r["month"])
        )
        tables["month_coverage"].extend(
            {**row, "selected": row["month"] == winner["month"] and row["eligible"] > 0}
            for row in months
        )
        spatial_group = (
            [m for m in cohort if m["month"] == winner["month"]]
            if winner["eligible"]
            else []
        )
        for area in sorted(a.area_id for a in areas if a.region_id == recipe.region_id):
            group = [m for m in spatial_group if m["area_id"] == area]
            tables["spatial"].append(
                {
                    **common,
                    "month": winner["month"] if winner["eligible"] else None,
                    "area_id": area,
                    "taxon_key": recipe.spatial_taxon_key,
                    **rate(recipe.spatial_taxon_key, group),
                }
            )

        matched = [m for m in cohort if m["physical_sample_id"] in links]
        values = sorted(links[m["physical_sample_id"]]["sst_celsius"] for m in matched)
        partition = recipe.temperature_partition
        low, high = partition.low_max, partition.high_min
        if partition.kind == "cohort_thirds" and values:
            low, high = (
                values[(len(values) - 1) // 3],
                values[(2 * (len(values) - 1)) // 3],
            )
        bins = defaultdict(list)
        if low is not None and high is not None and low < high:
            for m in matched:
                value = links[m["physical_sample_id"]]["sst_celsius"]
                bins[
                    "low" if value <= low else "high" if value >= high else "middle"
                ].append(m)
        elif partition.kind == "regional_season_thirds":
            for member in matched:
                label = links[member["physical_sample_id"]].get("relative_bin")
                if label not in {"low", "middle", "high", "unpartitioned_ties"}:
                    raise ValueError(
                        "Regional relative bins require a verified daily baseline"
                    )
                bins[label].append(member)
        else:
            bins["unpartitioned_ties"].extend(matched)
        contrasts = []
        temperature_strata = defaultdict(lambda: defaultdict(list))
        for label, group in bins.items():
            for member in group:
                temperature_strata[(member["area_id"], member["season"])][label].append(
                    member
                )
        # Q2 asks about the fixed top-ten list from Q1, not a new SST-selected list.
        for key in top:
            for label in ("low", "middle", "high", "unpartitioned_ties"):
                tables["temperature_bins"].append(
                    {
                        **common,
                        "taxon_key": key,
                        "bin": label,
                        "low_max": low,
                        "high_min": high,
                        "all_edna_eligible": len(cohort),
                        "sst_unavailable": len(cohort) - len(matched),
                        **rate(key, bins[label]),
                    }
                )
            lr, hr = rate(key, bins["low"]), rate(key, bins["high"])
            supported = (
                min(lr["eligible"], hr["eligible"]) >= recipe.min_stratum_samples
            )
            delta = (
                float(
                    (
                        Fraction(hr["detected"], hr["eligible"])
                        - Fraction(lr["detected"], lr["eligible"])
                    )
                    * 100
                )
                if lr["frequency"] is not None and hr["frequency"] is not None
                else None
            )
            contrasts.append(
                {
                    **common,
                    "taxon_key": key,
                    "low_detected": lr["detected"],
                    "low_eligible": lr["eligible"],
                    "high_detected": hr["detected"],
                    "high_eligible": hr["eligible"],
                    "supported": supported,
                    "difference_percentage_points": delta,
                    "representative": False,
                }
            )
            supported_deltas = []
            for (area, label), stratum_bins in sorted(temperature_strata.items()):
                left, right = (
                    rate(key, stratum_bins["low"]),
                    rate(key, stratum_bins["high"]),
                )
                supported_stratum = (
                    min(left["eligible"], right["eligible"])
                    >= recipe.min_stratum_samples
                )
                delta_stratum = (
                    (
                        Fraction(right["detected"], right["eligible"])
                        - Fraction(left["detected"], left["eligible"])
                    )
                    * 100
                    if left["frequency"] is not None and right["frequency"] is not None
                    else None
                )
                tables["temperature_strata"].append(
                    {
                        **common,
                        "taxon_key": key,
                        "area_id": area,
                        "season": label,
                        "low_detected": left["detected"],
                        "low_eligible": left["eligible"],
                        "high_detected": right["detected"],
                        "high_eligible": right["eligible"],
                        "supported": supported_stratum,
                        "difference_percentage_points": float(delta_stratum)
                        if delta_stratum is not None
                        else None,
                    }
                )
                if supported_stratum:
                    supported_deltas.append(delta_stratum)
            contrasts[-1]["supported_strata"] = len(supported_deltas)
            contrasts[-1]["standardized_difference_percentage_points"] = (
                float(sum(supported_deltas) / len(supported_deltas))
                if supported_deltas
                else None
            )
            contrasts[-1]["supported"] = supported and bool(supported_deltas)
        for area in sorted(a.area_id for a in areas if a.region_id == recipe.region_id):
            all_area_samples = [m for m in spatial_group if m["area_id"] == area]
            for label in ("low", "middle", "high", "unpartitioned_ties"):
                group = [m for m in bins[label] if m in all_area_samples]
                temperatures = [
                    links[m["physical_sample_id"]]["sst_celsius"] for m in group
                ]
                tables["spatial_temperature_bins"].append(
                    {
                        **common,
                        "area_id": area,
                        "taxon_key": recipe.spatial_taxon_key,
                        "bin": label,
                        "month": winner["month"] if winner["eligible"] else None,
                        "temperature_basis": "sample_time",
                        "low_max": low,
                        "high_min": high,
                        "all_edna_eligible": len(all_area_samples),
                        "sst_unavailable": sum(
                            m["physical_sample_id"] not in links
                            for m in all_area_samples
                        ),
                        "sst_matched": len(group),
                        "sample_time_sst_mean_celsius": sum(temperatures)
                        / len(temperatures)
                        if temperatures
                        else None,
                        **rate(recipe.spatial_taxon_key, group),
                    }
                )
        supported = [r for r in contrasts if r["supported"]]
        if supported:
            min(
                supported,
                key=lambda r: (
                    -abs(r["standardized_difference_percentage_points"]),
                    r["taxon_key"],
                ),
            )["representative"] = True
        tables["temperature_contrasts"].extend(contrasts)
        representative = next((r for r in contrasts if r["representative"]), None)
        if representative:
            for kind, label, group, partial in all_periods:
                sst = [
                    links[m["physical_sample_id"]]["sst_celsius"]
                    for m in group
                    if m["physical_sample_id"] in links
                ]
                tables["temperature_series"].append(
                    {
                        **common,
                        "taxon_key": representative["taxon_key"],
                        "period_kind": kind,
                        "period": label,
                        "partial_period": partial,
                        **rate(representative["taxon_key"], group),
                        "sst_matched": len(sst),
                        "sample_time_sst_mean_celsius": sum(sst) / len(sst)
                        if sst
                        else None,
                    }
                )

        strata = defaultdict(lambda: defaultdict(list))
        for m in cohort:
            strata[(m["area_id"], m["season"])][m["season_year"]].append(m)
        for (area, label), groups_by_year in sorted(strata.items()):
            for year in range(recipe.endpoint_from, recipe.endpoint_to + 1):
                start, end = _season_interval(year, label)
                group = groups_by_year[year]
                tables["stratum_coverage"].append(
                    {
                        **common,
                        "area_id": area,
                        "season": label,
                        "year": year,
                        "eligible": len(group),
                        "supported": len(group) >= recipe.min_stratum_samples,
                        "partial_period": start < recipe.time_from
                        or end.toordinal() - 1 > recipe.time_to.toordinal(),
                        "member_ids": sorted(m["physical_sample_id"] for m in group),
                    }
                )
        panel = [
            (s, g)
            for s, g in sorted(strata.items())
            if all(
                len(g[y]) >= recipe.min_stratum_samples
                and _season_interval(y, s[1])[0] >= recipe.time_from
                and _season_interval(y, s[1])[1].toordinal() - 1
                <= recipe.time_to.toordinal()
                for y in (recipe.endpoint_from, recipe.endpoint_to)
            )
        ]
        for (area, label), groups_by_year in panel:
            tables["matched_panel"].append(
                {
                    **common,
                    "area_id": area,
                    "season": label,
                    "endpoint_from_eligible": len(groups_by_year[recipe.endpoint_from]),
                    "endpoint_to_eligible": len(groups_by_year[recipe.endpoint_to]),
                    "weight": 1 / len(panel),
                }
            )
        change_scores, changes = [], defaultdict(list)
        for key in keys:
            for (area, label), groups_by_year in panel:
                left, right = (
                    rate(key, groups_by_year[y])
                    for y in (recipe.endpoint_from, recipe.endpoint_to)
                )
                delta = float(
                    (
                        Fraction(right["detected"], right["eligible"])
                        - Fraction(left["detected"], left["eligible"])
                    )
                    * 100
                )
                changes[key].append(
                    {
                        **common,
                        "taxon_key": key,
                        "area_id": area,
                        "season": label,
                        "from_year": recipe.endpoint_from,
                        "to_year": recipe.endpoint_to,
                        "from_detected": left["detected"],
                        "from_eligible": left["eligible"],
                        "to_detected": right["detected"],
                        "to_eligible": right["eligible"],
                        "difference_percentage_points": delta,
                    }
                )
            if changes[key] and any(
                r["from_detected"] or r["to_detected"] for r in changes[key]
            ):
                change_scores.append(
                    {
                        **common,
                        **taxa[key],
                        "mean_absolute_change_percentage_points": sum(
                            abs(r["difference_percentage_points"]) for r in changes[key]
                        )
                        / len(panel),
                        "matched_strata": len(panel),
                    }
                )
        change_scores.sort(
            key=lambda r: (-r["mean_absolute_change_percentage_points"], r["taxon_key"])
        )
        for position, row in enumerate(change_scores[:3], 1):
            key = row["taxon_key"]
            tables["change_ranking"].append({**row, "position": position})
            tables["changes"].extend(changes[key])
            for (area, label), groups_by_year in panel:
                for year in range(recipe.endpoint_from, recipe.endpoint_to + 1):
                    group = groups_by_year[year]
                    sst = [
                        links[m["physical_sample_id"]]["sst_celsius"]
                        for m in group
                        if m["physical_sample_id"] in links
                    ]
                    tables["follow_through"].append(
                        {
                            **common,
                            "taxon_key": key,
                            "area_id": area,
                            "season": label,
                            "year": year,
                            **rate(key, group),
                            "sst_matched": len(sst),
                            "sample_time_sst_mean_celsius": sum(sst) / len(sst)
                            if sst
                            else None,
                        }
                    )
    tables["methods"] = [
        {
            "algorithm_version": ALGORITHM_VERSION,
            "analysis_unit": recipe.analysis_unit,
            "threshold_level": recipe.threshold_level,
            "calendar": recipe.calendar,
            "description": "Descriptive detection frequencies; no abundance, occupancy, causal or significance inference.",
            "temperature_weighting": "eligible_sample_time",
            "representative_temperature_metric": recipe.representative_temperature_metric,
            "change_weighting": "equal_endpoint_matched_area_season_protocol_strata",
        }
    ]
    if (
        sum(len(rows) for rows in tables.values()) > MAX_RESULT_ROWS
        or len(canonical_bytes(tables)) > MAX_RESULT_BYTES
    ):
        raise ValueError("Research result resource limit exceeded")
    return tables
