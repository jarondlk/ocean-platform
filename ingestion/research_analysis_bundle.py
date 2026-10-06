"""Version-two detection-frequency inputs and manual, reproducible calculation.

Request handlers only consume published bundles. Scientific generation and
review head checks never substitute for the recorded immutable source inputs.
"""

from datetime import datetime, date

from sqlalchemy import text
from sqlalchemy.orm import Session

from api.research_registry_service import read_registry
from db.app_models import ResearchRegistryHead
from db.connection import get_engine
from ingestion.immutable_bundle import canonical_bytes, digest, validate_id
from ingestion.research_sst_panel import applied_definition, decode_panel, load_panel
from preprocessing.edna_analysis import runtime_versions
from preprocessing.edna_detection_frequency import (
    ALGORITHM_VERSION,
    TABLES,
    MAX_RESULT_BYTES,
    build_detection_frequency,
    prepare_membership,
)
from preprocessing.research_recipe import DetectionFrequencyRecipe
from preprocessing.research_sst import link_sample_time, monthly_area_context

RESEARCH_TABLES = (*TABLES, "area_month_sst", "sst_exclusions")
RESEARCH_FILES = {name + ".json" for name in (*RESEARCH_TABLES, "recipe", "inputs")}
LIMITATIONS = [
    "Detection frequency describes reviewed eligible physical samples, not organism abundance or occupancy.",
    "Sampling effort, assay protocols and detectability can affect comparisons; no causal or significance inference is made.",
    "SST-linked sample counts differ from all eligible sample counts; unsampled groups have null frequency.",
    "MUR foundation analyses combine satellite and in-situ inputs; model assimilation is separately labelled.",
    "Full-month area SST context and temperatures matched to sampling times have different denominators.",
]


class ResearchHistoricalState(ValueError):
    pass


def classification_fingerprint(source):
    return digest(
        sorted(
            (
                s["sample_id"],
                s["scientific_content_sha256"],
                s.get("sample_kind"),
                s.get("is_control"),
                s.get("active"),
            )
            for s in source["edna_sample"]
        )
    )


def _json(value):
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return value


def read_snapshot(recipe, sampling_registry_id):
    """One bounded, consistent PostgreSQL read of applied decisions and source rows."""
    from ingestion.edna_analysis_bundle import validate_input_provenance

    validate_id(sampling_registry_id)
    panel = load_panel(recipe.sst_panel_id) if recipe.sst_panel_id else None
    with get_engine().connect() as connection, connection.begin():
        connection.exec_driver_sql(
            "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY"
        )
        with Session(bind=connection) as session:
            sampling_payload = read_registry(session, sampling_registry_id)
            sampling = applied_definition(sampling_payload, "sampling")
            head = session.get(ResearchRegistryHead, sampling_payload["registry_key"])
            if not head or head.registry_id != sampling_registry_id:
                raise ResearchHistoricalState("Sampling registry is historical")
            if panel:
                product_payload = panel["definition"]["product_registry"]
                product_id = digest(product_payload)
                if read_registry(session, product_id) != product_payload:
                    raise ValueError("SST product approval mismatch")
                product_head = session.get(
                    ResearchRegistryHead, product_payload["registry_key"]
                )
                if (
                    not product_head
                    or product_head.registry_id != product_id
                    or panel["definition"]["sampling_registry"] != sampling_payload
                ):
                    raise ResearchHistoricalState(
                        "SST panel uses historical product/area decisions"
                    )

            snapshot_bytes = 0

            def rows(sql, params, maximum):
                nonlocal snapshot_bytes
                result = (
                    connection.execution_options(stream_results=True)
                    .execute(
                        text(sql + " LIMIT :maximum"),
                        {**params, "maximum": maximum + 1},
                    )
                    .mappings()
                    .yield_per(1000)
                )
                output = []
                for row in result:
                    if len(output) >= maximum:
                        raise ValueError("Research snapshot row limit exceeded")
                    value = {k: _json(v) for k, v in row.items()}
                    snapshot_bytes += len(canonical_bytes(value))
                    if snapshot_bytes > MAX_RESULT_BYTES:
                        raise ValueError("Research snapshot byte limit exceeded")
                    output.append(value)
                return output

            publications = rows(
                "SELECT channel,generation_id,manifest_sha256 FROM corpus_publication WHERE channel IN ('anemone-canonical','edna-canonical','edna') ORDER BY channel",
                {},
                3,
            )
            publication = {
                p["channel"]: {k: p[k] for k in ("generation_id", "manifest_sha256")}
                for p in publications
            }
            canonical = publication.get("anemone-canonical")
            if (
                not canonical
                or canonical != publication.get("edna-canonical")
                or "edna" not in publication
            ):
                raise ValueError(
                    "Canonical/retrieval publication is unavailable or out of sync"
                )
            for p in publication.values():
                validate_id(p["generation_id"])
                validate_id(p["manifest_sha256"])
            sids = sorted(
                {o.sample_id for m in sampling.memberships for o in m.occurrences}
            )
            aids = sorted({m.representative_assay_id for m in sampling.memberships})
            samples = rows(
                "SELECT * FROM edna_sample WHERE sample_id = ANY(:ids) ORDER BY sample_id",
                {"ids": sids},
                10000,
            )
            assays = rows(
                "SELECT * FROM edna_assay WHERE assay_id = ANY(:ids) ORDER BY assay_id",
                {"ids": aids},
                10000,
            )
            detections = rows(
                "SELECT * FROM edna_detection WHERE active IS TRUE AND assay_id = ANY(:ids) AND assignment_method=:method ORDER BY detection_id",
                {"ids": aids, "method": recipe.assignment_method},
                1000000,
            )
            records = samples + assays + detections
            files = rows(
                "SELECT * FROM external_source_file WHERE source_file_id=ANY(:ids) ORDER BY source_file_id",
                {"ids": sorted({r["source_file_id"] for r in records})},
                20000,
            )
            snapshots = rows(
                "SELECT * FROM external_source_snapshot WHERE snapshot_id=ANY(:ids) ORDER BY snapshot_id",
                {"ids": sorted({r["source_snapshot_id"] for r in records})},
                2000,
            )
    source = {
        "edna_sample": samples,
        "edna_assay": assays,
        "edna_detection": detections,
        "edna_internal_standard": [],
        "external_source_file": files,
        "external_source_snapshot": snapshots,
        "publication": publication,
    }
    source["generations"] = {
        "canonical_generation": canonical["generation_id"],
        "classification_generation": classification_fingerprint(source),
    }
    validate_input_provenance(source)
    if len(canonical_bytes(source)) > MAX_RESULT_BYTES:
        raise ValueError("Research snapshot byte limit exceeded")
    return source, sampling_payload, panel


def validate_research_inputs(recipe, inputs):
    from ingestion.edna_analysis_bundle import validate_input_provenance

    if set(inputs) != {"canonical", "sampling_registry", "sst_panel", "runtime"}:
        raise ValueError("Incomplete research input contract")
    source = inputs["canonical"]
    validate_input_provenance(source)
    sampling = applied_definition(inputs["sampling_registry"], "sampling")
    if (
        sampling.region_id != recipe.region_id
        or classification_fingerprint(source) != recipe.classification_generation
    ):
        raise ValueError("Research region/classification mismatch")
    prepare_membership(recipe, source, list(sampling.areas), list(sampling.memberships))
    panel = inputs["sst_panel"]
    if bool(panel) != bool(recipe.sst_panel_id):
        raise ValueError("Research SST panel contract mismatch")
    if panel:
        collection = (
            panel["definition"].get("algorithm_version")
            == "reviewed-area-sst-collection-v1"
        )
        if (
            set(panel)
            != (
                {
                    "panel_id",
                    "manifest",
                    "manifest_sha256",
                    "definition",
                    "observations",
                }
                | ({"children"} if collection else set())
            )
            or digest(panel["definition"]) != recipe.sst_panel_id
            or panel["panel_id"] != recipe.sst_panel_id
            or panel["definition"]["sampling_registry"] != inputs["sampling_registry"]
        ):
            raise ValueError("Research SST panel identity mismatch")
        validate_id(panel["manifest_sha256"])
        if digest(panel["manifest"]) != panel["manifest_sha256"]:
            raise ValueError("Research SST manifest mismatch")
        files = {
            "manifest.json": canonical_bytes(panel["manifest"]),
            "definition.json": canonical_bytes(panel["definition"]),
            "observations.json": canonical_bytes(panel["observations"]),
        }
        if collection:
            from ingestion.research_sst_collection import decode_collection

            files["children.json"] = canonical_bytes(panel["children"])
            decode_collection(panel["panel_id"], panel["manifest"], files)
        else:
            decode_panel(
                panel["panel_id"], panel["manifest"], files, metadata_only=True
            )
    return sampling


def panel_reference(panel):
    return (
        {k: panel[k] for k in ("panel_id", "manifest", "definition", "observations")}
        | {"manifest_sha256": digest(panel["manifest"])}
        | ({"children": panel["children"]} if "children" in panel else {})
        if panel
        else None
    )


def build_research_analysis(recipe, source, sampling_registry, panel=None):
    # Stable input ordering makes acquisition/database row order immaterial.
    source = {
        k: sorted(v, key=digest) if isinstance(v, list) else v
        for k, v in source.items()
    }
    inputs = {
        "canonical": source,
        "sampling_registry": sampling_registry,
        "sst_panel": panel_reference(panel),
        "runtime": runtime_versions(),
    }
    sampling = validate_research_inputs(recipe, inputs)
    areas, memberships = list(sampling.areas), list(sampling.memberships)
    members, _ = prepare_membership(recipe, source, areas, memberships)
    observations = panel["observations"] if panel else []
    links, excluded = (
        link_sample_time(
            members,
            observations,
            recipe.sst_panel_id,
            max_time_hours=recipe.sst_max_time_hours,
        )
        if panel
        else ([], [])
    )
    tables = build_detection_frequency(recipe, source, areas, memberships, links)
    daily_context = bool(panel) and panel["definition"]["product_registry"][
        "definition"
    ]["temporal_statistic"] in {"daily_foundation_analysis", "daily_mean"}
    tables["area_month_sst"] = (
        monthly_area_context(
            observations,
            areas,
            recipe.spatial_year,
            min_day_fraction=recipe.sst_min_month_day_fraction,
        )
        if daily_context
        else []
    )
    if panel and not daily_context:
        excluded.append(
            {
                "panel_id": recipe.sst_panel_id,
                "status": "monthly_context_unavailable",
                "reason": "monthly_context_requires_reviewed_daily_product",
            }
        )
    tables["sst_exclusions"] = excluded
    serialized = recipe.model_dump(mode="json")
    input_sha256 = digest(inputs)
    identity = digest(
        {
            "algorithm": ALGORITHM_VERSION,
            "recipe": serialized,
            "input_sha256": input_sha256,
        }
    )
    for name, rows in tables.items():
        for row in rows:
            row["result_id"] = digest([identity, name, row])
    result = {
        "schema_version": 2,
        "analysis_kind": "detection_frequency",
        "analysis_id": identity,
        "algorithm_version": ALGORITHM_VERSION,
        "recipe": serialized,
        "input_sha256": input_sha256,
        "inputs": inputs,
        "tables": tables,
        "limitations": LIMITATIONS,
    }
    if len(canonical_bytes(result)) > MAX_RESULT_BYTES:
        raise ValueError("Research analysis byte limit exceeded")
    return result


def research_status(bundle):
    recipe = DetectionFrequencyRecipe.model_validate(bundle["recipe"])
    try:
        source, registry, panel = read_snapshot(
            recipe, digest(bundle["inputs"]["sampling_registry"])
        )
        source = {
            k: sorted(v, key=digest) if isinstance(v, list) else v
            for k, v in source.items()
        }
        current = {
            "canonical": source,
            "sampling_registry": registry,
            "sst_panel": panel_reference(panel),
            "runtime": runtime_versions(),
        }
        return (
            "current"
            if digest(current) == bundle["manifest"]["input_sha256"]
            and bundle["manifest"]["algorithm_version"] == ALGORITHM_VERSION
            else "historical"
        )
    except ResearchHistoricalState:
        # A changed review/publication is historical; unavailable infrastructure
        # is distinguished below and never advertised as current.
        return "historical"
    except Exception:
        return "current_state_unavailable"


def run_research_analysis(recipe, sampling_registry_id, *, execute=False):
    from ingestion.edna_analysis_bundle import publish_analysis

    source, registry, panel = read_snapshot(recipe, sampling_registry_id)
    result = build_research_analysis(recipe, source, registry, panel)
    if execute:
        publish_analysis(result)
    return {
        "execute": execute,
        "analysis_id": result["analysis_id"],
        "table_counts": {name: len(rows) for name, rows in result["tables"].items()},
    }
