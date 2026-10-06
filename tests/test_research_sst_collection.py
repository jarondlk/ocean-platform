from copy import deepcopy
import hashlib
import json

import pytest

import config
from ingestion.immutable_bundle import canonical_bytes, digest
from ingestion.research_sst_collection import (
    build_collection,
    load_collection,
    publish_collection,
)
from ingestion.research_sst_panel import decode_panel, load_panel, publish_panel
from tests.test_research_sst_panel import panel_fixture


def children(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "EDNA_ARTIFACT_URI", "")
    monkeypatch.setattr(config, "ANALYSIS_DIR", tmp_path / "artifacts")
    product, sampling, granules = panel_fixture(tmp_path)
    identity = publish_panel(product, sampling, granules)
    first = load_panel(identity)
    path, granule = granules[0]
    import xarray as xr

    with xr.open_dataset(path) as dataset:
        revised = dataset.load().copy(deep=True)
    revised["analysed_sst"] = revised["analysed_sst"] + 1
    next_path = tmp_path / "revision.nc"
    revised.to_netcdf(next_path)
    changed = granule.model_copy(
        update={
            "raw_sha256": hashlib.sha256(next_path.read_bytes()).hexdigest(),
            "granule_id": digest("revised granule"),
        }
    )
    second = load_panel(publish_panel(product, sampling, [(next_path, changed)]))
    return first, second


def test_collection_explicit_tile_ownership_full_provenance_and_serving(
    tmp_path, monkeypatch
):
    first, second = children(tmp_path, monkeypatch)
    selections = [(first, ["A"]), (second, ["B", "C"])]
    identity = publish_collection(iter(selections))
    assert publish_collection(iter(selections[::-1])) == identity
    collection = load_panel(identity)
    assert collection == load_collection(identity)
    assert len(collection["observations"]) == 3
    assert set(collection["files"]) == {
        "definition.json",
        "children.json",
        "observations.json",
        "manifest.json",
    }
    assert all("raw_sha256" in row for row in collection["observations"])
    assert (
        collection["definition"]["integrity_basis"]
        == "operator_verified_raw_children_serving_verified_metadata"
    )
    path = (
        tmp_path
        / "artifacts"
        / "research-sst-collections"
        / identity
        / "observations.json"
    )
    rows = json.loads(path.read_bytes())
    rows[0]["sst_celsius"] = 99
    path.write_bytes(canonical_bytes(rows))
    with pytest.raises(ValueError, match="integrity"):
        load_collection(identity)


def test_collection_conflicts_review_generations_and_raw_verification(
    tmp_path, monkeypatch
):
    first, second = children(tmp_path, monkeypatch)
    with pytest.raises(ValueError, match="Conflicting"):
        build_collection([(first, ["A"]), (second, ["A"])])
    with pytest.raises(ValueError, match="identity"):
        build_collection([(first, ["A"]), (first, ["B"])])
    with pytest.raises(ValueError, match="unique reviewed"):
        build_collection([(first, ["unreviewed"])])
    with pytest.raises(ValueError, match="one applied"):
        changed = deepcopy(second)
        changed["definition"]["product_registry"]["scientific_approval_sha256"] = (
            digest("other approval")
        )
        build_collection([(first, ["A"]), (changed, ["B"])])
    partial = deepcopy(first)
    partial["files"] = {
        key: value
        for key, value in partial["files"].items()
        if not key.startswith("raw-")
    }
    with pytest.raises(ValueError, match="file contract"):
        build_collection([(partial, ["A"])])


def test_collection_analysis_replay_export_and_original_single_panel(
    tmp_path, monkeypatch
):
    from fastapi.testclient import TestClient
    from api.main import app
    from ingestion.edna_analysis_bundle import load_analysis, publish_analysis
    from ingestion.research_analysis_bundle import build_research_analysis
    from tests.test_research_analysis_bundle import publication_fixture

    first, second = children(tmp_path, monkeypatch)
    recipe, source, sampling = publication_fixture()
    # Both fixtures describe the same reviewed cohort; pin its exact applied record.
    assert first["definition"]["sampling_registry"] == sampling
    collection_id = publish_collection([(first, ["A"]), (second, ["B", "C"])])
    collection = load_panel(collection_id)
    recipe = recipe.model_copy(update={"sst_panel_id": collection_id})
    result = build_research_analysis(recipe, source, sampling, collection)
    assert publish_analysis(result)
    loaded = load_analysis(result["analysis_id"])
    assert loaded["inputs"]["sst_panel"]["children"] == collection["children"]
    client = TestClient(app)
    response = client.get(
        "/data/edna/analysis/runs/" + result["analysis_id"] + "/export?format=bundle"
    )
    assert response.status_code == 200
    old_recipe = recipe.model_copy(update={"sst_panel_id": first["panel_id"]})
    old = build_research_analysis(old_recipe, source, sampling, first)
    publish_analysis(old)
    assert "children" not in load_analysis(old["analysis_id"])["inputs"]["sst_panel"]
    decode_panel(first["panel_id"], first["manifest"], first["files"])


def test_collection_rejects_aggregate_and_metadata_budget_overflow(
    tmp_path, monkeypatch
):
    first, second = children(tmp_path, monkeypatch)
    monkeypatch.setattr("ingestion.research_sst_collection.MAX_OBSERVATIONS", 1)
    with pytest.raises(ValueError, match="observation limit"):
        build_collection([(first, ["A", "B"])])
    monkeypatch.setattr("ingestion.research_sst_collection.MAX_OBSERVATIONS", 200000)
    monkeypatch.setattr("ingestion.research_sst_collection.MAX_COLLECTION_BYTES", 32)
    with pytest.raises(ValueError, match="byte limit"):
        build_collection([(first, ["A"])])
