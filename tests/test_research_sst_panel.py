from copy import deepcopy
import json

import pytest

import config
from ingestion.immutable_bundle import digest, canonical_bytes
from ingestion.research_sst_panel import (
    build_panel,
    decode_panel,
    load_panel,
    publish_panel,
)
from preprocessing.research_sst import monthly_area_context, normalize_granule
from tests.research_fixtures import h, research_fixture
from tests.test_research_sst import sst_fixture


def applied(payload, kind, key):
    # Synthetic ledger-shaped records; real batch entrypoints read the DB ledger.
    return {
        "schema_version": 1,
        "kind": kind,
        "registry_key": key,
        "definition": payload,
        "review_id": "00000000-0000-0000-0000-000000000001",
        "scientific_approval_sha256": h("fixture approval"),
    }


def panel_fixture(tmp_path):
    path, ds, product, granule, areas = sst_fixture(tmp_path)
    recipe, source, all_areas, memberships, _, _ = research_fixture()
    sampling = applied(
        {
            "schema_version": 1,
            "region_id": recipe.region_id,
            "areas": [a.model_dump(mode="json") for a in all_areas],
            "memberships": [m.model_dump(mode="json") for m in memberships],
        },
        "sampling",
        "sampling:" + recipe.region_id,
    )
    product_registry = applied(
        product.model_dump(mode="json"),
        "sst_product",
        "sst_product:" + product.product_id,
    )
    return product_registry, sampling, [(path, granule)]


def test_panel_publishes_replays_and_retains_exact_raw_files(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "EDNA_ARTIFACT_URI", "")
    monkeypatch.setattr(config, "ANALYSIS_DIR", tmp_path / "artifacts")
    product, sampling, granules = panel_fixture(tmp_path)
    identity = publish_panel(product, sampling, granules)
    assert publish_panel(product, sampling, granules) == identity
    bundle = load_panel(identity)
    assert len(bundle["observations"]) == 3
    assert (
        bundle["files"]["raw-" + granules[0][1].granule_id + ".nc"]
        == granules[0][0].read_bytes()
    )
    assert bundle["definition"]["product_registry"] == product
    path = tmp_path / "artifacts" / "research-sst" / identity / "observations.json"
    rows = json.loads(path.read_bytes())
    rows[0]["sst_celsius"] = 99
    path.write_text(json.dumps(rows))
    with pytest.raises(ValueError, match="integrity"):
        load_panel(identity)


def test_panel_approval_shape_duplicate_granules_and_output_contract(tmp_path):
    product, sampling, granules = panel_fixture(tmp_path)
    invalid = deepcopy(product)
    invalid.pop("scientific_approval_sha256")
    with pytest.raises(ValueError, match="applied"):
        build_panel(invalid, sampling, granules)
    with pytest.raises(ValueError, match="Duplicate"):
        build_panel(product, sampling, granules * 2)
    identity, definition, rows, files = build_panel(product, sampling, granules)
    # A manifest that omits raw bytes cannot masquerade as a complete panel.
    manifest = {"id": identity, "files": {"definition.json": h("fake")}}
    with pytest.raises(ValueError, match="file contract"):
        decode_panel(identity, manifest, files)


def test_monthly_context_requires_daily_coverage_and_keeps_unobserved_months(tmp_path):
    path, ds, product, granule, areas = sst_fixture(tmp_path)
    rows = normalize_granule(path, granule, product, areas)
    output = monthly_area_context(rows, areas, 2020)
    may = output[4]
    assert may["valid_days"] == 1 and may["missing_days"] == 30
    assert may["sst_celsius"] is None
    assert output[0]["valid_days"] == 0 and output[0]["sst_celsius"] is None
    assert len(output) == 12
    supported = monthly_area_context(rows, areas, 2020, min_day_fraction=1 / 31)[4]
    assert (
        supported["status"] == "supported"
        and supported["sst_celsius"] == rows[0]["sst_celsius"]
    )
    assert supported["temperature_basis"] == "full_month_daily_area_context"
    with pytest.raises(ValueError, match="Multiple daily"):
        monthly_area_context(rows * 2, areas, 2020)
    changed = deepcopy(rows)
    changed[0]["temporal_statistic"] = "model_instant"
    changed[0]["observation_id"] = digest(
        {k: v for k, v in changed[0].items() if k != "observation_id"}
    )
    with pytest.raises(ValueError, match="daily SST"):
        monthly_area_context(changed, areas, 2020)


def test_embedded_panel_metadata_requires_exact_manifest_and_raw_references(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(config, "EDNA_ARTIFACT_URI", "")
    monkeypatch.setattr(config, "ANALYSIS_DIR", tmp_path / "artifacts")
    product, sampling, granules = panel_fixture(tmp_path)
    identity = publish_panel(product, sampling, granules)
    panel = load_panel(identity)
    metadata = {k: v for k, v in panel["files"].items() if not k.startswith("raw-")}
    assert (
        decode_panel(identity, panel["manifest"], metadata, metadata_only=True)[
            "observations"
        ]
        == panel["observations"]
    )
    with pytest.raises(ValueError, match="file contract"):
        decode_panel(identity, panel["manifest"], metadata)
    rows = deepcopy(panel["observations"])
    rows[0]["source_url"] = "fixture://different-provider-granule"
    rows[0]["observation_id"] = digest(
        {k: v for k, v in rows[0].items() if k != "observation_id"}
    )
    metadata["observations.json"] = canonical_bytes(rows)
    manifest = deepcopy(panel["manifest"])
    import hashlib

    manifest["files"]["observations.json"] = hashlib.sha256(
        metadata["observations.json"]
    ).hexdigest()
    metadata["manifest.json"] = canonical_bytes(manifest)
    with pytest.raises(ValueError, match="observation provenance"):
        decode_panel(identity, manifest, metadata, metadata_only=True)
