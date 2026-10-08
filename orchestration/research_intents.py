"""Six conservative research intents over exact, published result rows.

No model, SQL generation, inference from retrieval snippets or scope widening.
Unrecognized qualifiers require clarification instead of approximate matching.
"""

from dataclasses import dataclass
import json
import re
from typing import Literal

from ingestion.immutable_bundle import canonical_bytes
from preprocessing.research_recipe import Hash, ResearchModel


class ResearchIntent(ResearchModel):
    kind: Literal[
        "fish_frequency",
        "temperature_comparison",
        "monthly_spatial",
        "spatial_temperature",
        "distribution_change",
        "follow_through",
    ]
    protocol_id: Hash | None = None


QUESTIONS = {
    "fish_frequency": (
        "Show the top 10 fish by detection frequency, with yearly and seasonal changes",
        "Which fish are detected most frequently by year and season",
        "Show top fish detection frequencies",
    ),
    "temperature_comparison": (
        "Compare fish detection frequency in high and low SST conditions and show a representative series",
        "Which fish have contrasting detection frequencies in high and low SST",
        "Show fish temperature comparisons",
    ),
    "monthly_spatial": (
        "Show the best-covered month and sardine detections by area",
        "Which month has the most sampled areas and what are the sardine counts",
        "Show monthly sardine coverage",
    ),
    "spatial_temperature": (
        "Show temperature conditions for sampled areas with and without sardine detections",
        "Compare SST conditions in sardine-positive and sampled-negative areas",
        "Show spatial sardine temperature bins",
    ),
    "distribution_change": (
        "Show the three fish with the largest endpoint distribution changes",
        "Which three fish have the biggest distribution changes",
        "Compare endpoint fish distributions",
    ),
    "follow_through": (
        "Follow the same three fish through the intermediate years with SST",
        "Show intermediate-year changes and SST for the endpoint fish panel",
        "Show the fixed fish panel with SST",
    ),
}
SST_INTENTS = {"temperature_comparison", "spatial_temperature", "follow_through"}
TABLES_BY_INTENT = {
    "fish_frequency": ("ranking", "series"),
    "temperature_comparison": (
        "temperature_contrasts",
        "temperature_bins",
        "temperature_series",
    ),
    "monthly_spatial": ("month_coverage", "spatial"),
    "spatial_temperature": ("spatial_temperature_bins", "area_month_sst"),
    "distribution_change": ("change_ranking", "matched_panel", "changes"),
    "follow_through": ("change_ranking", "matched_panel", "follow_through"),
}
MAX_CARD_ROWS = 500
MAX_RESPONSE_BYTES = 2 * 1024 * 1024


def normalized(query):
    return re.sub(r"\s+", " ", query.casefold().strip()).rstrip(".?!")


def parse_intent(query, recipe=None):
    query = normalized(query)
    if recipe:
        suffix = normalized(
            f" in {recipe['region_id']} from {str(recipe['time_from'])[:4]} to {str(recipe['time_to'])[:4]}"
        )
        if query.endswith(suffix):
            query = query[: -len(suffix)].strip()
    return next(
        (
            kind
            for kind, aliases in QUESTIONS.items()
            if query in {normalized(a) for a in aliases}
        ),
        None,
    )


@dataclass
class ResearchAnswer:
    answer: str
    documents: list[dict]
    reason: str | None
    diagnostics: dict


def abstain(reason, message):
    return ResearchAnswer(
        message,
        [],
        reason,
        {"failure": reason, "model_invoked": False, "research": True},
    )


def check_scope(bundle, scope, kind):
    recipe = bundle["recipe"]
    selections = scope["sources"]
    if not selections["edna_metabarcoding"]["enabled"]:
        return abstain(
            "source_disabled",
            "ANEMONE eDNA is unchecked. Enable it to use this published frequency analysis.",
        )
    if kind in SST_INTENTS and not selections["remote_sensing"]["enabled"]:
        return abstain(
            "source_disabled",
            "SST is unchecked. Enable remote sensing to request this temperature workflow. Source selections were retained.",
        )
    samples = bundle["inputs"]["canonical"]["edna_sample"]
    permitted = {
        "assignment_method": recipe["assignment_method"],
        "sample_kind": "environmental",
        "is_control": False,
        "time_from": recipe["time_from"],
        "time_to": recipe["time_to"],
    }
    if bundle["manifest"].get("schema_version") == 3:
        permitted.pop("sample_kind")
        permitted.pop("is_control")
    for key in ("provider", "provider_project_id", "provider_run_id"):
        values = {sample.get(key) for sample in samples}
        if len(values) == 1:
            permitted[key] = next(iter(values))
    edna = selections["edna_metabarcoding"]["filters"]
    for key, value in edna.items():
        if value is not None and (key not in permitted or value != permitted[key]):
            return abstain(
                "aggregate_scope_required",
                f"The {key} filter differs from the published cohort. Select a matching analysis or explicitly clear the conflicting filter; no cohort was broadened.",
            )
    if kind in SST_INTENTS:
        for key, value in selections["remote_sensing"]["filters"].items():
            if value is not None and (
                (key == "dataset_id" and (bundle["manifest"].get("schema_version") != 3 or value != "mur-miyagi-2020-2023"))
                or (key != "dataset_id" and (key not in {"time_from", "time_to"} or value != recipe[key]))
            ):
                return abstain(
                    "aggregate_scope_required",
                    f"The SST {key} filter differs from the immutable panel. Select a matching panel or explicitly clear the filter.",
                )
        if not recipe.get("sst_panel_id"):
            return abstain(
                "aggregate_unavailable",
                "This analysis has no reviewed historical SST panel. Temperature results are unavailable; no temperatures were inferred.",
            )
    return None


def _escape(value):
    return (
        re.sub(r"([\\`*{}\[\]()<>#|])", r"\\\1", str(value))
        .replace("\n", " ")
        .replace("\r", " ")
    )


def _value(value):
    if value is None:
        return "unavailable"
    if isinstance(value, float):
        return f"{value:.6g}"
    if isinstance(value, bool):
        return "yes" if value else "no"
    return _escape(value)


def result_rows(bundle, kind, protocol_id):
    output = {}
    tables = TABLES_BY_INTENT[kind]
    if bundle["manifest"].get("schema_version") == 3:
        tables += (
            ("read_ranking",)
            if kind == "fish_frequency"
            else ("relative_sst_thresholds",)
            if kind in SST_INTENTS
            else ()
        )
    for table in tables:
        rows = bundle["tables"][table]
        rows = [r for r in rows if r.get("protocol_id", protocol_id) == protocol_id]
        if kind == "fish_frequency" and table == "series":
            rows = [r for r in rows if r["period_kind"] in {"year", "season"}]
        if table == "read_ranking":
            # Highest sequencing-read sums, separately ranked for each period.
            counts = {}
            selected = []
            for row in rows:
                group = (row["period_kind"], row["period"])
                counts[group] = counts.get(group, 0) + 1
                if counts[group] <= 10:
                    selected.append(row)
            rows = selected
        if kind == "spatial_temperature" and table == "area_month_sst":
            selected = next(
                (
                    r["month"]
                    for r in bundle["tables"]["month_coverage"]
                    if r["protocol_id"] == protocol_id and r["selected"]
                ),
                None,
            )
            rows = [r for r in rows if r["month"] == selected]
        output[table] = rows
    return output


def render_research(bundle, scope, query, intent=None):
    recipe = bundle["recipe"]
    provisional = bundle["manifest"].get("schema_version") == 3
    from ingestion.regional_publication import analysis_publication
    accepted = analysis_publication(bundle) if provisional else None
    recognized = parse_intent(query, recipe)
    if not recognized or (intent and recognized != intent.kind):
        return abstain(
            "aggregate_scope_required",
            "Choose one of the six published research workflows. This question contains an unsupported or conflicting qualifier, so no statistics were inferred.",
        )
    kind = intent.kind if intent else recognized
    if kind in {"monthly_spatial", "spatial_temperature"} and "sardine" in normalized(
        query
    ):
        from ingestion.immutable_bundle import digest
        from preprocessing.edna_analysis import taxon_key

        matches = [
            r
            for r in bundle["inputs"]["canonical"]["edna_detection"]
            if r.get("species") == "Sardinops melanostictus"
            and digest(taxon_key(r, "species")) == recipe["spatial_taxon_key"]
        ]
        if not matches:
            return abstain(
                "aggregate_scope_required",
                "This cohort has no species-resolved Sardinops melanostictus evidence. Unidentified Sardinops records cannot establish Japanese-sardine detections or absence. A genus-level analysis needs a separately labelled recipe; no taxon was substituted."
                if provisional
                else "This analysis does not establish Sardinops melanostictus as its spatial taxon. Select the reviewed sardine analysis; no taxon was substituted.",
            )
    failure = check_scope(bundle, scope, kind)
    if failure:
        return failure
    if provisional and kind in {"distribution_change", "follow_through"}:
        return abstain(
            "no_matching_evidence",
            "This provisional demo uses one Miyagi regional rectangle. It cannot establish changes in spatial distribution; reviewed comparable sampling areas are still needed. The regional time series remains available.",
        )
    protocols = sorted({row["protocol_id"] for row in bundle["tables"]["membership"]})
    if not protocols:
        return abstain(
            "empty_analysis_cohort",
            "No reviewed physical samples are eligible in this published analysis. Review exclusions before interpreting detection frequency.",
        )
    protocol = intent.protocol_id if intent else None
    if protocol is None and len(protocols) != 1:
        return abstain(
            "aggregate_scope_required",
            "This analysis has multiple assay protocols. Select one published protocol; their denominators will remain separate.",
        )
    protocol = protocol or protocols[0]
    if protocol not in protocols:
        return abstain(
            "aggregate_scope_required",
            "The selected protocol is not present in this published analysis.",
        )
    rows_by_table = result_rows(bundle, kind, protocol)
    if (
        kind in {"distribution_change", "follow_through"}
        and not rows_by_table["matched_panel"]
    ):
        return abstain(
            "no_matching_evidence",
            "No area-season strata meet the fixed endpoint support rule. Distribution-change rankings and follow-through are unavailable; unobserved groups were not treated as zero.",
        )
    if (
        kind == "temperature_comparison"
        and not any(r["representative"] for r in rows_by_table["temperature_contrasts"])
        and not provisional
    ):
        return abstain(
            "no_matching_evidence",
            "The matched SST data do not support a representative high/low comparison under this recipe. No species was selected from unsupported contrasts.",
        )
    identity = bundle["manifest"]["id"]
    documents, sections = [], []
    covered = (
        ["edna_metabarcoding", "remote_sensing"]
        if kind in SST_INTENTS
        else ["edna_metabarcoding"]
    )
    from preprocessing.edna_analysis import taxon_key
    from ingestion.immutable_bundle import digest

    requested_keys = {
        r.get("taxon_key")
        for rows in rows_by_table.values()
        for r in rows[:MAX_CARD_ROWS]
    }
    taxa, seen_lineages = {}, set()
    for detection in bundle["inputs"]["canonical"]["edna_detection"]:
        lineage = taxon_key(detection, "species")
        signature = lineage
        if signature not in seen_lineages:
            seen_lineages.add(signature)
            key = digest(lineage)
            if key in requested_keys:
                taxa[key] = detection["species"]
    for table, rows in rows_by_table.items():
        # Exact published fields; source lineage arrays remain in the full bundle.
        hidden = {
            "member_ids",
            "detected_member_ids",
            "lineage",
            "observation_ids",
            "source_granule_ids",
        }
        if kind not in SST_INTENTS:
            hidden |= {"sst_matched", "sample_time_sst_mean_celsius", "sst_unavailable"}
        featured = [
            {k: v for k, v in row.items() if k not in hidden}
            for row in rows[:MAX_CARD_ROWS]
        ]
        # Only reviewed cell geometry and names are projected to chat. Source
        # occurrences, contact metadata and sampling identity decisions stay
        # behind the researcher provenance permission.
        plot_areas = (
            [
                {
                    key: area[key]
                    for key in (
                        "area_id",
                        "label",
                        "west",
                        "east",
                        "south",
                        "north",
                        "coordinate_uncertainty_km",
                    )
                }
                for area in (
                    bundle["inputs"]["provisional_sampling"]["areas"]
                    if provisional
                    else bundle["inputs"]["sampling_registry"]["definition"]["areas"]
                )
            ]
            if table in {"spatial", "spatial_temperature_bins", "area_month_sst"}
            else []
        )
        keys = {r.get("taxon_key") for r in featured}
        plot_taxa = {key: value for key, value in taxa.items() if key in keys}
        doc_id = f"analysis_edna_{identity}_{table}"
        documents.append(
            {
                "id": doc_id,
                "title": ("Miyagi regional analysis: " if accepted else "Provisional demo: " if provisional else "") + table.replace("_", " ").capitalize(),
                "analysis_id": identity,
                "table": table,
                "analysis_type": "regional_frequency" if accepted else "provisional_demo"
                if provisional
                else "detection_frequency",
                "source_family": "edna_metabarcoding",
                "covered_source_types": covered,
                "result_ids": [r["result_id"] for r in featured],
                "result_rows": featured,
                "plot_areas": plot_areas,
                "analysis_recipe": recipe,
                "plot_taxa": [
                    {"taxon_key": key, "species": value}
                    for key, value in sorted(plot_taxa.items())
                ],
                "total_rows": len(rows),
                "rows_truncated": len(rows) > MAX_CARD_ROWS,
                "text": json.dumps(featured, sort_keys=True, ensure_ascii=False),
            }
        )
        columns = [
            key
            for key in (
                "species",
                "taxon_key",
                "position",
                "area_id",
                "season",
                "year",
                "month",
                "period",
                "bin",
                "detected",
                "eligible",
                "frequency",
                "read_count",
                "low_max_celsius",
                "high_min_celsius",
                "baseline_from",
                "baseline_to",
                "supported_days",
                "low_detected",
                "low_eligible",
                "high_detected",
                "high_eligible",
                "all_edna_eligible",
                "sst_unavailable",
                "representative",
                "difference_percentage_points",
                "standardized_difference_percentage_points",
                "mean_absolute_change_percentage_points",
                "sst_matched",
                "sample_time_sst_mean_celsius",
                "sst_celsius",
                "valid_days",
                "missing_days",
                "supported",
                "sampling_status",
            )
            if any(key in r for r in featured)
        ]
        if featured and columns:
            summary = [
                "| " + " | ".join(columns) + " |",
                "| " + " | ".join("---" for _ in columns) + " |",
            ]
            summary += [
                "| "
                + " | ".join(
                    _value(
                        taxa.get(row.get(key), row.get(key))
                        if key == "taxon_key"
                        else row.get(key)
                    )
                    for key in columns
                )
                + " |"
                for row in featured[:10]
            ]
            sections.append(
                f"{table.replace('_', ' ').capitalize()} ({len(rows)} published rows; first {min(10, len(rows))} shown):\n\n"
                + "\n".join(summary)
                + f"\n\n[{doc_id}]"
            )
        elif not featured:
            sections.append(
                f"{table.replace('_', ' ').capitalize()}: no matching published rows. [{doc_id}]"
            )
    title = f"Published detection-frequency analysis for {_escape(recipe['region_id'])}, {recipe['time_from']}–{recipe['time_to']} ({recipe['calendar']}); one assay protocol."
    explanation = "Frequency = detected / eligible physical samples. An unsampled group has no rate. Low-support and partial periods retain their flags. These descriptive differences do not establish abundance, occupancy or causation."
    if provisional:
        title = f"{'Published Miyagi regional analysis' if accepted else 'User-approved provisional Miyagi demo'}, {recipe['time_from']}–{recipe['time_to']} ({recipe['calendar']}); one assignment method and assay protocol."
        explanation = "Frequency = detected / eligible singleton occurrence proxies, not confirmed physical water collections. Canonical unknown classifications and identities are unchanged; known controls, empty tables and unresolved repeats are excluded. Read-ranking tables show sequencing read sums, not fish abundance. ANEMONE is the user-selected reviewer display label; this is not independent researcher approval or provider endorsement. Sparse groups retain warnings. A regional rectangle cannot establish within-region spatial distribution."
        if kind in SST_INTENTS:
            explanation += " SST uses final MUR 04.1 only: 0.05-degree subsampled regional foundation analysis with cosine-latitude grid-point weighting, not native coastal/sample-point temperatures. Low/high thresholds use each region/season's supported daily SST over the displayed study years, not a long-term climatology. Sampling-time links use 24 hours, extended to 48 hours only if over 20% are unmatched; matched and all-eDNA denominators differ. Missing or interim dates remain explicit final-series gaps; nearby-date links retain their actual timestamps. These comparisons show association, not weather causing abundance changes."
            explanation += f" Final-series gaps: {', '.join(g['day'] for g in bundle['inputs']['period_preview']['final_series_gaps']) or 'none'}."
    elif kind in SST_INTENTS:
        product = bundle["inputs"]["sst_panel"]["definition"]["product_registry"][
            "definition"
        ]
        explanation += f" SST product: {_escape(product['provider'])}, {_escape(product['product_id'])}, {_escape(product['version'])}; {_escape(product['measurement_type'])}. All-eDNA and SST-matched denominators remain separate. Full-month context uses available daily area values under the recorded coverage rule."
        if product.get("regional_context"):
            explanation += " Historical SST uses 0.05-degree subsampled regional context with cosine-latitude grid-point weighting. It is not native coastal or point-sample temperature evidence. Missing ice fractions may use the open-sea mask with recorded warnings; interim generations and unsupported dates remain gaps."
        if product["temporal_statistic"] not in {
            "daily_mean",
            "daily_foundation_analysis",
        }:
            explanation += " This product has no reviewed daily aggregation, so full-month SST context is unavailable; only sampling-time matches are shown."
        cuts = next(
            (
                row
                for row in bundle["tables"]["temperature_bins"]
                if row["protocol_id"] == protocol
            ),
            None,
        )
        if cuts:
            explanation += f" Low SST ≤{_value(cuts['low_max'])}°C; high SST ≥{_value(cuts['high_min'])}°C ({_escape(recipe['temperature_partition']['kind'])}). The comparison retains the fixed Q1 top-ten fish list. Representative selection uses equally weighted supported area-season contrasts."
    answer = title + "\n\n" + explanation + "\n\n" + "\n\n".join(sections)
    if (
        len(canonical_bytes({"answer": answer, "documents": documents}))
        > MAX_RESPONSE_BYTES
    ):
        return abstain(
            "aggregate_scope_required",
            "This research response exceeds the bounded display limit. Use the paginated Data tables for the full published analysis.",
        )
    diagnostics = {
        "research": True,
        "backend": "immutable_research_bundle",
        "model_invoked": False,
        "top_k_applied": False,
        "analysis_id": identity,
        "research_intent": {"kind": kind, "protocol_id": protocol},
        "expected_source_types": covered,
        "retrieved_source_types": covered,
        "missing_source_types": [],
        "result_rows_verified": True,
        "operational_publication": accepted,
        "display_row_limit_per_table": MAX_CARD_ROWS,
    }
    return ResearchAnswer(answer, documents, None, diagnostics)
