"""Provisional demos never turn unknown source evidence into formal approval."""

from copy import deepcopy
from datetime import date, datetime, timedelta, timezone
from itertools import product

import pytest
from pydantic import ValidationError

import config
from api.auth import route_permission
from ingestion.edna_analysis_bundle import load_analysis, publish_analysis
from ingestion.immutable_bundle import digest
from ingestion.provisional_research_bundle import (
    DemoDecision,
    ProvisionalRecipe,
    ProvisionalSampling,
    build_demo,
    validate_inputs,
)
from orchestration.research_intents import QUESTIONS, ResearchIntent, render_research
from preprocessing.edna_analysis import runtime_versions
from preprocessing.edna_detection_frequency import registry_versions
from preprocessing.historical_sst_matching import preview_relative_temperature_bins
from preprocessing.research_recipe import DetectionFrequencyRecipe
from retrieval.source_scope import FAMILIES, legacy_scope
from tests.test_research_analysis_bundle import publication_fixture


def default_scope():
    return legacy_scope({})


def fixture():
    recipe, source, applied = publication_fixture()
    registry = applied["definition"]
    area = registry["areas"][0]
    area.update(
        geometry_type="reviewed_regional_context_rectangle",
        coordinate_uncertainty_km=None,
    )
    registry["areas"] = [area]
    source["publication"] = {
        "anemone-canonical": {
            "generation_id": recipe.canonical_generation,
            "manifest_sha256": digest("canonical-manifest"),
        }
    }
    for index, sample in enumerate(source["edna_sample"]):
        sample.update(
            sample_kind="unknown",
            is_control=None,
            provider_project_id="fixture",
            original_sample_label=f"sample-{index}",
        )
    for member in registry["memberships"]:
        member.update(
            area_id=area["area_id"],
            area_version=digest(area),
            representative_policy="provisional_singleton_assay",
            physical_sample_id=digest(
                {
                    "proposal": "one-source-collection-occurrence",
                    "sample_id": member["occurrences"][0]["sample_id"],
                }
            ),
        )
    registry = ProvisionalSampling.model_validate(registry)
    observations = []
    start, end = date(2020, 1, 1), date(2023, 12, 31)
    for i in range((end - start).days + 1):
        when = start + timedelta(days=i)
        row = {
            "area_id": area["area_id"],
            "area_version": digest("preview-area"),
            "product_definition_id": digest("product"),
            "granule_id": digest(str(when)),
            "raw_sha256": digest("raw" + str(when)),
            "time_utc": str(when) + "T09:00:00+00:00",
            "measurement_type": "satellite_in_situ_analysis",
            "temporal_statistic": "daily_foundation_analysis",
            "processing_generation": "final",
            "product_version": "04.1",
            "status": "valid",
            "sst_celsius": float(10 + (i % 90) / 10),
            "native_sample_area_evidence": False,
            "scientific_publication": False,
            "warnings": [],
        }
        observations.append({**row, "observation_id": digest(row)})
    period = {
        "status": "complete_unpublished_regional_context_preview",
        "area_id": area["area_id"],
        "definition": {
            "diagnostic_rectangle": {
                k: area[k] for k in ("west", "east", "south", "north")
            }
        },
        "period": {"first_year": 2020, "last_year": 2023},
        "observations": observations,
        "relative_temperature": preview_relative_temperature_bins(observations),
        "scientific_approval": False,
        "scientific_publication": False,
        "native_sample_area_evidence": False,
        "final_series_gaps": [],
    }
    period["period_preview_id"] = digest(period)
    sampling = registry.model_dump(mode="json")
    approval = DemoDecision(
        user_instruction="Proceed with a provisional demo",
        rationale="Synthetic explicit user decision, not independent researcher approval.",
        recorded_at_utc=datetime(2026, 10, 8, tzinfo=timezone.utc),
        source_sha256=digest(source),
        sampling_sha256=digest(sampling),
        period_preview_id=period["period_preview_id"],
    ).model_dump(mode="json")
    inputs = {
        "canonical": source,
        "provisional_sampling": sampling,
        "period_preview": period,
        "user_decision": approval,
        "runtime": runtime_versions(),
    }
    recipe = ProvisionalRecipe.model_validate(
        {
            **recipe.model_dump(mode="json"),
            **registry_versions(list(registry.areas), list(registry.memberships)),
            "analysis_unit": "provisional_singleton_occurrence",
            "control_policy": "known_controls_excluded_unknown_provisional",
            "date_only_policy": "assumed_Japan_midday",
            "sst_panel_id": period["period_preview_id"],
            "temperature_partition": {"kind": "regional_season_thirds"},
        }
    )
    return recipe, inputs


def test_unknown_sources_stay_unknown_and_controls_cannot_be_eligible():
    recipe, inputs = fixture()
    before = deepcopy(inputs)
    result = build_demo(recipe, inputs)
    assert inputs == before
    assert len(result["tables"]["membership"]) == 15
    assert all(
        m["physical_identity_confirmed"] is False
        and m["environmental_classification_confirmed"] is False
        for m in result["tables"]["membership"]
    )
    assert all(
        s["sample_kind"] == "unknown" for s in inputs["canonical"]["edna_sample"]
    )
    assert result["inputs"]["user_decision"]["independent_researcher_approval"] is False
    with pytest.raises(ValidationError):
        DetectionFrequencyRecipe.model_validate(result["recipe"])
    changed = deepcopy(inputs)
    changed["canonical"]["edna_sample"][0]["is_control"] = True
    changed["user_decision"]["source_sha256"] = digest(changed["canonical"])
    result = build_demo(recipe, changed)
    assert len(result["tables"]["membership"]) == 14
    assert any(
        "inactive_control_or_unknown" in row["reasons"]
        for row in result["tables"]["exclusions"]
    )


@pytest.mark.parametrize(
    "field", ["provider_endorsement", "independent_researcher_approval"]
)
def test_cannot_claim_independent_or_provider_approval(field):
    recipe, inputs = fixture()
    inputs["user_decision"][field] = True
    with pytest.raises(ValidationError):
        validate_inputs(recipe, inputs)


def test_stale_decision_and_interim_generation_are_rejected():
    recipe, inputs = fixture()
    inputs["canonical"]["edna_detection"][0]["read_count"] += 1
    with pytest.raises(ValueError, match="binding"):
        build_demo(recipe, inputs)
    recipe, inputs = fixture()
    period = inputs["period_preview"]
    row = period["observations"][0]
    row["processing_generation"] = "interim"
    row["observation_id"] = digest(
        {k: v for k, v in row.items() if k != "observation_id"}
    )
    period["period_preview_id"] = digest(
        {k: v for k, v in period.items() if k != "period_preview_id"}
    )
    inputs["user_decision"]["period_preview_id"] = period["period_preview_id"]
    recipe = recipe.model_copy(update={"sst_panel_id": period["period_preview_id"]})
    with pytest.raises(ValueError, match="final regional"):
        build_demo(recipe, inputs)


def test_relative_baseline_uses_daily_region_season_not_fish_sample_quantiles():
    recipe, inputs = fixture()
    result = build_demo(recipe, inputs)
    assert len(result["tables"]["relative_sst_thresholds"]) == 4
    assert (
        sum(p["supported_days"] for p in result["tables"]["relative_sst_thresholds"])
        == 1461
    )
    assert all(
        r["relative_bin"] in {"low", "middle", "high", "unpartitioned_ties"}
        for r in result["tables"]["sst_links"]
    )
    assert all(
        r["metric"] == "sequencing_read_sum_not_abundance"
        for r in result["tables"]["read_ranking"]
    )
    assert sum(
        r["read_count"]
        for r in result["tables"]["read_ranking"]
        if r["period_kind"] == "all"
    ) == sum(
        r["read_count"]
        for r in inputs["canonical"]["edna_detection"]
        if r["assignment_method"] == recipe.assignment_method
    )


def test_demo_roundtrip_scope_and_spatial_limits(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "EDNA_ARTIFACT_URI", "")
    monkeypatch.setattr(config, "ANALYSIS_DIR", tmp_path)
    recipe, inputs = fixture()
    result = build_demo(recipe, inputs)
    publish_analysis(result)
    bundle = load_analysis(result["analysis_id"])
    assert bundle["tables"] == result["tables"]
    assert bundle["manifest"]["schema_version"] == 3
    for enabled in product((False, True), repeat=4):
        scope = default_scope()
        for family, flag in zip(FAMILIES, enabled):
            scope["sources"][family]["enabled"] = flag
        answer = render_research(
            bundle,
            scope,
            QUESTIONS["temperature_comparison"][0],
            ResearchIntent(kind="temperature_comparison"),
        )
        # Multiple protocols still require explicit selection; no sources widened.
        if (
            not scope["sources"]["edna_metabarcoding"]["enabled"]
            or not scope["sources"]["remote_sensing"]["enabled"]
        ):
            assert answer.reason == "source_disabled"
    scope = default_scope()
    protocol = bundle["tables"]["membership"][0]["protocol_id"]
    answer = render_research(
        bundle,
        scope,
        QUESTIONS["fish_frequency"][0],
        ResearchIntent(kind="fish_frequency", protocol_id=protocol),
    )
    assert answer.reason is None
    assert (
        "singleton occurrence proxies" in answer.answer
        and "not fish abundance" in answer.answer
    )
    assert all(d["analysis_type"] == "provisional_demo" for d in answer.documents)
    assert "read_ranking" in {d["table"] for d in answer.documents}
    spatial = render_research(
        bundle,
        scope,
        QUESTIONS["distribution_change"][0],
        ResearchIntent(kind="distribution_change", protocol_id=protocol),
    )
    assert spatial.reason == "no_matching_evidence"
    assert (
        route_permission("POST", "/research-registry-reviews")
        == "classification:decide"
    )
    assert (
        route_permission("POST", "/research-registry-reviews/id/decision")
        == "classification:decide"
    )


def test_current_status_checks_full_detection_rows_and_uses_only_read_transactions(
    monkeypatch,
):
    from ingestion.provisional_research_bundle import demo_status

    recipe, inputs = fixture()
    observed = []
    stored = deepcopy(inputs["canonical"])

    class Result:
        def __init__(self, rows):
            self.rows = rows

        def mappings(self):
            return self

        def all(self):
            return self.rows

    class Connection:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            pass

        def begin(self):
            return self

        def exec_driver_sql(self, statement):
            observed.append(statement)

        def execute(self, statement, params=None):
            statement = str(statement)
            observed.append(statement)
            if "FROM corpus_publication" in statement:
                return Result(
                    [{"channel": k, **v} for k, v in stored["publication"].items()]
                )
            table = statement.split("FROM ")[1].split()[0]
            return Result(stored[table])

    class Engine:
        def connect(self):
            return Connection()

    monkeypatch.setattr(
        "ingestion.provisional_research_bundle.get_engine", lambda: Engine()
    )
    assert demo_status({"inputs": inputs}) == "current"
    assert observed[0].endswith("READ ONLY")
    assert all(s.startswith(("SET ", "SELECT ")) for s in observed)
    assert not any("app_user" in s or "chat_" in s for s in observed)
    stored["edna_detection"][0]["read_count"] += 1
    assert demo_status({"inputs": inputs}) == "historical"
    stored = deepcopy(inputs["canonical"])
    stored["publication"] = {}
    assert demo_status({"inputs": inputs}) == "historical"
    monkeypatch.setattr(
        "ingestion.provisional_research_bundle.get_engine",
        lambda: (_ for _ in ()).throw(RuntimeError("unavailable")),
    )
    assert demo_status({"inputs": inputs}) == "current_state_unavailable"


def test_results_cannot_be_rehashed_to_override_recomputed_statistics(
    tmp_path, monkeypatch
):
    import hashlib
    import json
    from ingestion.edna_analysis_bundle import _decode_analysis
    from ingestion.immutable_bundle import canonical_bytes

    monkeypatch.setattr(config, "EDNA_ARTIFACT_URI", "")
    monkeypatch.setattr(config, "ANALYSIS_DIR", tmp_path)
    recipe, inputs = fixture()
    result = build_demo(recipe, inputs)
    publish_analysis(result)
    bundle = load_analysis(result["analysis_id"])
    files = deepcopy(bundle["files"])
    manifest = deepcopy(bundle["manifest"])
    rows = json.loads(files["read_ranking.json"])
    rows[0]["read_count"] += 1000
    rows[0]["result_id"] = digest(
        [
            result["analysis_id"],
            "read_ranking",
            {k: v for k, v in rows[0].items() if k != "result_id"},
        ]
    )
    files["read_ranking.json"] = canonical_bytes(rows)
    manifest["files"]["read_ranking.json"] = hashlib.sha256(
        files["read_ranking.json"]
    ).hexdigest()
    files["manifest.json"] = canonical_bytes(manifest)
    with pytest.raises(ValueError, match="differ from complete"):
        _decode_analysis(result["analysis_id"], manifest, files)


def test_publication_requires_current_source_check_and_never_runs_by_default(
    monkeypatch,
):
    from scripts.run_provisional_research_demo import run

    recipe, inputs = fixture()
    called = []
    monkeypatch.setattr(
        "scripts.run_provisional_research_demo.publish_analysis",
        lambda result: called.append(result),
    )
    preflight = run(recipe.model_dump(mode="json"), inputs)
    assert preflight["published"] is False and called == []
    monkeypatch.setattr(
        "scripts.run_provisional_research_demo.demo_status", lambda _: "historical"
    )
    with pytest.raises(ValueError, match="current source verification"):
        run(recipe.model_dump(mode="json"), inputs, execute=True)
    assert called == []
