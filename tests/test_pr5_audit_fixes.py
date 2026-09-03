from copy import deepcopy
import json
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

import config
from api.main import app
from ingestion.edna_analysis_bundle import (
    publish_analysis,
    load_analysis,
    provenance_descriptors,
    analysis_trace,
    context_documents,
)
from ingestion.immutable_bundle import digest, canonical_bytes
from preprocessing.edna_analysis import build_analysis
from tests.test_edna_analysis import fixture
from retrieval.local_retriever import LocalRetriever

client = TestClient(app)


@pytest.mark.parametrize(
    "change", ["omitted", "rehash", "unregistered", "symlink", "count", "result_id"]
)
def test_analysis_direct_reads_fail_closed(tmp_path, monkeypatch, change):
    recipe, source = fixture()
    monkeypatch.setattr(config, "ANALYSIS_DIR", tmp_path)
    monkeypatch.setattr(
        "ingestion.edna_analysis_bundle.read_canonical", lambda _: source
    )
    result = build_analysis(recipe, source)
    identity = result["analysis_id"]
    publish_analysis(result)
    root = tmp_path / "edna" / identity
    manifest_path = root / "manifest.json"
    manifest = json.loads(manifest_path.read_bytes())
    registration = tmp_path / "edna" / "registry" / (identity + ".json")
    if change == "omitted":
        del manifest["files"]["diversity.json"]
        (root / "diversity.json").write_text("[]")
    elif change == "rehash":
        (root / "diversity.json").write_text("[]")
        import hashlib

        manifest["files"]["diversity.json"] = hashlib.sha256(b"[]").hexdigest()
    elif change == "unregistered":
        registration.unlink()
    elif change == "symlink":
        target = tmp_path / "copied.json"
        target.write_bytes((root / "diversity.json").read_bytes())
        (root / "diversity.json").unlink()
        (root / "diversity.json").symlink_to(target)
    elif change == "count":
        manifest["table_counts"]["diversity"] = 999
        registration.write_bytes(
            canonical_bytes(
                {"analysis_id": identity, "manifest_sha256": digest(manifest)}
            )
        )
    else:
        rows = json.loads((root / "diversity.json").read_bytes())
        rows[0]["result_id"] = "0" * 64
        data = canonical_bytes(rows)
        (root / "diversity.json").write_bytes(data)
        import hashlib

        manifest["files"]["diversity.json"] = hashlib.sha256(data).hexdigest()
        registration.write_bytes(
            canonical_bytes(
                {"analysis_id": identity, "manifest_sha256": digest(manifest)}
            )
        )
    manifest_path.write_bytes(canonical_bytes(manifest))
    base = "/data/edna/analysis/runs/" + identity
    for suffix in ("", "/tables/diversity", "/export", "/export?format=bundle"):
        assert client.get(base + suffix).status_code == 409
    assert context_documents({"analysis_id": identity}) == []


def test_historical_citation_survives_new_recipe_run(tmp_path, monkeypatch):
    recipe, source = fixture()
    monkeypatch.setattr(config, "ANALYSIS_DIR", tmp_path)
    first = build_analysis(recipe, source)
    publish_analysis(first)
    updated = deepcopy(source)
    updated["edna_detection"][0]["read_count"] = 7
    publish_analysis(build_analysis(recipe, updated))
    monkeypatch.setattr(
        "ingestion.edna_analysis_bundle.read_canonical", lambda _: updated
    )
    identity = first["analysis_id"]
    assert len(provenance_descriptors()) == 2
    assert analysis_trace(
        f"analysis_edna_{identity}_diversity", provenance_descriptors()
    )["found"]
    assert (
        client.get("/data/edna/analysis/runs/" + identity).json()["status"]
        == "historical"
    )
    assert (
        client.get(
            "/data/edna/analysis/runs/" + identity + "/export?format=bundle"
        ).status_code
        == 200
    )
    assert (
        load_analysis(identity)["tables"]["diversity"] == first["tables"]["diversity"]
    )
    assert context_documents({"analysis_id": identity}) == []


def test_sample_list_and_method_applied_before_local_ranking(tmp_path, monkeypatch):
    recipe, source = fixture()
    member = source["edna_sample"][0]["sample_id"]
    recipe = recipe.model_copy(
        update={
            "cohort": recipe.cohort.model_copy(update={"sample_ids": [member]}),
            "assignment_methods": ["qcauto_target"],
        }
    )
    monkeypatch.setattr(config, "ANALYSIS_DIR", tmp_path)
    monkeypatch.setattr(
        "ingestion.edna_analysis_bundle.read_canonical", lambda _: source
    )
    result = build_analysis(recipe, source)
    publish_analysis(result)
    retriever = LocalRetriever()
    retriever.documents = [
        dict(
            doc_id=str(i),
            sample_id="0" * 64,
            assignment_method="qcauto_target",
            text="diversity " * 20,
            source_type="edna_metabarcoding",
            provider="anemone",
            provider_project_id="project-science",
            sample_kind="environmental",
            is_control=False,
        )
        for i in range(20)
    ]
    included = dict(
        retriever.documents[0], doc_id="included", sample_id=member, text="diversity"
    )
    retriever.documents += [
        dict(
            included, doc_id="other-method", assignment_method="qcauto_95pct_3nn_target"
        ),
        included,
    ]
    retriever.bm25.fit([r["text"] for r in retriever.documents])
    with (
        patch("orchestration.unified._pg_available", return_value=False),
        patch("retrieval.local_retriever.get_local_retriever", return_value=retriever),
    ):
        response = client.post(
            "/retrieve",
            json={"query": "diversity", "analysis_id": result["analysis_id"], "k": 1},
        )
    assert response.status_code == 200, response.text
    assert [r["doc_id"] for r in response.json()["sources"]] == ["included"]
    assert response.json()["diagnostics"]["source_type_counts"]["primary"] == {
        "edna_metabarcoding": 1
    }
    assert retriever.search("diversity", sample_ids=[]) == []
    assert (
        retriever.search("diversity", sample_ids=[member], assignment_methods=[]) == []
    )
