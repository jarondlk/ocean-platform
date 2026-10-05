from copy import deepcopy
import io
import json
import zipfile

from fastapi.testclient import TestClient
import pytest

import config
from api.main import app
from ingestion.edna_analysis_bundle import (
    TABLES,
    publish_analysis,
    load_analysis,
    analysis_status,
    regenerate_affected_analyses,
)
from ingestion.research_analysis_bundle import (
    RESEARCH_TABLES,
    build_research_analysis,
    classification_fingerprint,
)
from tests.research_fixtures import research_fixture
from tests.test_edna_analysis import fixture as legacy_fixture
from tests.test_research_sst_panel import applied
from preprocessing.research_recipe import DetectionFrequencyRecipe


def publication_fixture():
    recipe, source, areas, memberships, _, _ = research_fixture()
    _, legacy = legacy_fixture()
    source["edna_internal_standard"] = []
    source["external_source_file"] = legacy["external_source_file"]
    source["external_source_snapshot"] = legacy["external_source_snapshot"]
    for table in ("edna_sample", "edna_assay", "edna_detection"):
        prototype = legacy[table][0]
        for row in source[table]:
            row.update(
                {
                    k: prototype[k]
                    for k in ("source_file_id", "source_snapshot_id", "source_row_hash")
                }
            )
            row["source_row_number"] = 2
    generation = classification_fingerprint(source)
    source["generations"]["classification_generation"] = generation
    recipe = recipe.model_copy(
        update={"classification_generation": generation, "sst_panel_id": None}
    )
    registry = applied(
        {
            "schema_version": 1,
            "region_id": recipe.region_id,
            "areas": [a.model_dump(mode="json") for a in areas],
            "memberships": [m.model_dump(mode="json") for m in memberships],
        },
        "sampling",
        "sampling:" + recipe.region_id,
    )
    return recipe, source, registry


def setup_publication(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "EDNA_ARTIFACT_URI", "")
    monkeypatch.setattr(config, "ANALYSIS_DIR", tmp_path)
    recipe, source, registry = publication_fixture()
    monkeypatch.setattr(
        "ingestion.research_analysis_bundle.read_snapshot",
        lambda *_: (source, registry, None),
    )
    result = build_research_analysis(recipe, source, registry)
    publish_analysis(result)
    return result, source, registry


def test_v2_publication_preserves_v1_tables_and_reproducible_inputs(
    tmp_path, monkeypatch
):
    before = tuple(TABLES)
    result, source, registry = setup_publication(tmp_path, monkeypatch)
    assert tuple(TABLES) == before and "ranking" not in TABLES
    bundle = load_analysis(result["analysis_id"])
    assert bundle["manifest"]["schema_version"] == 2
    assert set(bundle["tables"]) == set(RESEARCH_TABLES)
    assert analysis_status(bundle) == "current"
    shuffled = {
        k: list(reversed(v)) if isinstance(v, list) else v for k, v in source.items()
    }
    assert (
        build_research_analysis(
            DetectionFrequencyRecipe.model_validate(result["recipe"]),
            shuffled,
            registry,
        )
        == result
    )
    legacy_recipe, legacy = legacy_fixture()
    from preprocessing.edna_analysis import build_analysis

    old = build_analysis(legacy_recipe, legacy)
    publish_analysis(old)
    assert "schema_version" not in load_analysis(old["analysis_id"])["manifest"]
    assert tuple(TABLES) == before
    source["edna_detection"][0]["read_count"] += 1
    assert analysis_status(bundle) == "historical"
    assert load_analysis(result["analysis_id"])["tables"] == bundle["tables"]


def test_v2_tables_exact_trace_csv_and_complete_export(tmp_path, monkeypatch):
    result, source, registry = setup_publication(tmp_path, monkeypatch)
    client = TestClient(app)
    run = "/data/edna/analysis/runs/" + result["analysis_id"]
    response = client.get(run)
    assert response.status_code == 200 and "ranking" in response.json()["tables"]
    page = client.get(run + "/tables/spatial?limit=1&offset=0").json()
    assert page["total"] == 3 and len(page["rows"]) == 1
    rid = page["rows"][0]["result_id"]
    trace = client.get(
        run + "/provenance", params={"table": "spatial", "result_id": rid}
    ).json()
    assert trace["inputs"]["sampling_registry"]["scientific_approval_sha256"]
    assert trace["result"]["result_id"] == rid
    assert client.get(run + "/tables/composition").status_code == 400
    csv = client.get(run + "/export?table=spatial")
    assert csv.status_code == 200 and "reviewed_physical_sample" in csv.text
    assert "fixture-region" in csv.text and "identity_version" in csv.text
    archive = client.get(run + "/export?format=bundle")
    with zipfile.ZipFile(io.BytesIO(archive.content)) as zipped:
        assert "area_month_sst.json" in zipped.namelist()
        assert json.loads(zipped.read("inputs.json"))["sampling_registry"] == registry
    regeneration = regenerate_affected_analyses(source["edna_sample"][0]["sample_id"])
    assert regeneration["affected"] == 1 and regeneration["analysis_ids"] == []
    assert (
        regeneration["pending"][0]["reason"]
        == "research_review_and_manual_publication_required"
    )


def test_unapproved_registry_and_tampered_output_are_rejected(tmp_path, monkeypatch):
    result, source, registry = setup_publication(tmp_path, monkeypatch)
    recipe = DetectionFrequencyRecipe.model_validate(result["recipe"])
    bad = deepcopy(registry)
    bad.pop("scientific_approval_sha256")
    with pytest.raises(ValueError, match="applied"):
        build_research_analysis(recipe, source, bad)
    path = tmp_path / "edna" / result["analysis_id"] / "ranking.json"
    rows = json.loads(path.read_bytes())
    rows[0]["eligible"] = 999
    path.write_text(json.dumps(rows))
    with pytest.raises(ValueError, match="integrity"):
        load_analysis(result["analysis_id"])


def test_known_earlier_algorithm_remains_readable_but_is_historical(
    tmp_path, monkeypatch
):
    from ingestion import research_analysis_bundle as research

    monkeypatch.setattr(config, "EDNA_ARTIFACT_URI", "")
    monkeypatch.setattr(config, "ANALYSIS_DIR", tmp_path)
    recipe, source, registry = publication_fixture()
    current = research.ALGORITHM_VERSION
    monkeypatch.setattr(
        research, "ALGORITHM_VERSION", "physical-detection-frequency-v1"
    )
    previous = build_research_analysis(recipe, source, registry)
    publish_analysis(previous)
    monkeypatch.setattr(research, "ALGORITHM_VERSION", current)
    monkeypatch.setattr(research, "read_snapshot", lambda *_: (source, registry, None))
    bundle = load_analysis(previous["analysis_id"])
    assert analysis_status(bundle) == "historical"
    assert bundle["tables"] == previous["tables"]
    assert (
        build_research_analysis(recipe, source, registry)["analysis_id"]
        != previous["analysis_id"]
    )
