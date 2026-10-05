from copy import deepcopy
from dataclasses import replace
from itertools import product
from datetime import datetime, timezone
import uuid

from fastapi.testclient import TestClient
import numpy as np
import pytest
import xarray as xr

import config
from api.main import app
from api.auth import route_permission
from ingestion.anemone_catalogue import file_sha256
from ingestion.edna_analysis_bundle import publish_analysis, load_analysis
from ingestion.research_analysis_bundle import build_research_analysis
from ingestion.research_sst_panel import publish_panel, load_panel
from orchestration.research_intents import (
    QUESTIONS,
    SST_INTENTS,
    ResearchIntent,
    parse_intent,
    render_research,
)
from preprocessing.research_sst import GranuleInput
from retrieval.source_scope import FAMILIES
from tests.research_fixtures import h
from tests.test_research_analysis_bundle import publication_fixture
from tests.test_research_sst_panel import applied
from tests.test_research_sst import sst_fixture


def research_chat_fixture(tmp_path, monkeypatch, *, product_semantics=None):
    monkeypatch.setattr(config, "EDNA_ARTIFACT_URI", "")
    monkeypatch.setattr(config, "ANALYSIS_DIR", tmp_path / "artifacts")
    recipe, source, registry = publication_fixture()
    _, _, product_definition, _, _ = sst_fixture(tmp_path)
    if product_semantics:
        product_definition = type(product_definition).model_validate(
            {**product_definition.model_dump(mode="json"), **product_semantics}
        )
    granules = []
    for year, value in ((2020, 10), (2023, 20)):
        path = tmp_path / f"{year}.nc"
        ds = xr.Dataset(
            {
                "analysed_sst": (
                    ("time", "lat", "lon"),
                    np.full((1, 2, 4), value + 273.15),
                    {"units": "K"},
                ),
                "mask": (("lat", "lon"), np.ones((2, 4))),
                "quality": (("lat", "lon"), np.full((2, 4), 5)),
            },
            coords={
                "time": [np.datetime64(f"{year}-05-15T01:00:00")],
                "lat": [38.25, 38.75],
                "lon": [140.25, 140.75, 141.25, 141.75],
            },
            attrs={"title": product_definition.expected_title},
        )
        ds.to_netcdf(path)
        granules.append(
            (
                path,
                GranuleInput(
                    granule_id=h(str(year)),
                    raw_sha256=file_sha256(path),
                    source_url=f"fixture://sst/{year}",
                    expected_time_utc=datetime(year, 5, 15, 1, tzinfo=timezone.utc),
                ),
            )
        )
    product_record = applied(
        product_definition.model_dump(mode="json"),
        "sst_product",
        "sst_product:" + product_definition.product_id,
    )
    panel_id = publish_panel(product_record, registry, granules)
    panel = load_panel(panel_id)
    recipe = recipe.model_copy(update={"sst_panel_id": panel_id})
    monkeypatch.setattr(
        "ingestion.research_analysis_bundle.read_snapshot",
        lambda *_: (source, registry, panel),
    )
    result = build_research_analysis(recipe, source, registry, panel)
    publish_analysis(result)
    return load_analysis(result["analysis_id"]), source


def scope_for(identity, flags=(True, True, True, True)):
    return {
        "version": 1,
        "sources": {
            family: {
                "enabled": flag,
                "filters": {},
                **({"analysis_id": identity} if family == "edna_metabarcoding" else {}),
            }
            for family, flag in zip(FAMILIES, flags)
        },
    }


def test_six_intents_have_exact_rows_and_verified_two_source_citations(
    tmp_path, monkeypatch
):
    bundle, source = research_chat_fixture(tmp_path, monkeypatch)
    identity = bundle["manifest"]["id"]
    client = TestClient(app)
    monkeypatch.setattr(
        "api.main.retrieve_with_expansion",
        lambda *a, **k: pytest.fail("research must not use top-k retrieval"),
    )
    monkeypatch.setattr(
        "api.main.get_model_runtime",
        lambda *a, **k: pytest.fail("research must not invoke a model"),
    )
    for kind, query in (
        (kind, query) for kind, aliases in QUESTIONS.items() for query in aliases
    ):
        response = client.post(
            "/chat",
            json={
                "query": query,
                "evidence_scope": scope_for(identity),
                "research_intent": {"kind": kind},
            },
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["outcome"] == "answered" and body["model_invoked"] is False
        audit = body["answer_audit"]
        assert audit["claim_verification"] == "published_result_rows_verified"
        assert audit["invalid_citation_count"] == 0
        assert audit["missing_expected_citations"] == []
        assert set(audit["citation_requirements"]["satisfied_source_types"]) == (
            {"edna_metabarcoding", "remote_sensing"}
            if kind in SST_INTENTS
            else {"edna_metabarcoding"}
        )
        for document in body["analysis_context"]:
            lookup = {r["result_id"]: r for r in bundle["tables"][document["table"]]}
            for row in document["result_rows"]:
                assert row == {k: lookup[row["result_id"]][k] for k in row}
    assert len(bundle["tables"]["temperature_series"]) > 0
    assert all(row["sst_celsius"] is None for row in bundle["tables"]["area_month_sst"])


def test_all_16_source_combinations_preserve_source_choices(tmp_path, monkeypatch):
    bundle, _ = research_chat_fixture(tmp_path, monkeypatch)
    identity = bundle["manifest"]["id"]
    client = TestClient(app)
    for flags in product((False, True), repeat=4):
        scope = scope_for(identity, flags)
        for kind in QUESTIONS:
            response = client.post(
                "/chat",
                json={
                    "query": QUESTIONS[kind][0],
                    "evidence_scope": scope,
                    "research_intent": {"kind": kind},
                },
            )
            assert response.status_code == 200, response.text
            body = response.json()
            enabled = dict(zip(FAMILIES, flags))
            answerable = enabled["edna_metabarcoding"] and (
                kind not in SST_INTENTS or enabled["remote_sensing"]
            )
            assert (body["outcome"] == "answered") == answerable
            assert body["options"]["evidence_scope"] == scope
            if not answerable:
                assert body["model_invoked"] is False and body["analysis_context"] == []


@pytest.mark.parametrize(
    "semantics",
    [
        {
            "product_id": "himawari_geophysical_sst",
            "measurement_type": "satellite_retrieval",
            "temporal_statistic": "instant_retrieval",
        },
        {
            "product_id": "jcope_model_sst",
            "measurement_type": "model_assimilation",
            "temporal_statistic": "model_instant",
        },
    ],
)
def test_instant_products_support_sample_links_without_inventing_monthly_means(
    tmp_path, monkeypatch, semantics
):
    bundle, _ = research_chat_fixture(
        tmp_path, monkeypatch, product_semantics=semantics
    )
    assert bundle["tables"]["sst_links"]
    assert bundle["tables"]["area_month_sst"] == []
    assert any(
        row.get("reason") == "monthly_context_requires_reviewed_daily_product"
        for row in bundle["tables"]["sst_exclusions"]
    )
    answer = TestClient(app).post(
        "/chat",
        json={
            "query": QUESTIONS["spatial_temperature"][0],
            "research_intent": {"kind": "spatial_temperature"},
            "evidence_scope": scope_for(bundle["manifest"]["id"]),
        },
    )
    assert answer.status_code == 200 and answer.json()["outcome"] == "answered"
    assert semantics["measurement_type"] in answer.json()["answer"]


def test_saved_viewer_answer_retains_exact_rows_and_scopes_after_sources_change(
    tmp_path, monkeypatch
):
    from sqlalchemy import select
    import api.auth as auth
    from api.auth import ROLE_PERMISSIONS
    from db.app_models import AppUser, ChatInteraction
    from tests.test_chat_feedback import _database, _add_user, _install_database

    bundle, source = research_chat_fixture(tmp_path, monkeypatch)
    factory = _database()
    actor = _add_user(factory, "research-viewer@test.invalid")
    with factory.begin() as session:
        session.get(AppUser, actor.id).role = "viewer"
    actor = replace(actor, role="viewer", permissions=ROLE_PERMISSIONS["viewer"])
    _install_database(monkeypatch, factory)
    monkeypatch.setattr(auth, "authenticate_request", lambda _: actor)
    client = TestClient(app)
    scope = scope_for(bundle["manifest"]["id"])
    response = client.post(
        "/chat",
        json={
            "query": QUESTIONS["temperature_comparison"][0],
            "evidence_scope": scope,
            "research_intent": {"kind": "temperature_comparison"},
        },
    )
    assert response.status_code == 200 and response.json()["outcome"] == "answered"
    body = response.json()
    source["edna_detection"][0]["read_count"] += 1
    with factory() as session:
        saved = session.scalar(
            select(ChatInteraction).where(
                ChatInteraction.id == uuid.UUID(body["interaction_id"])
            )
        )
        assert saved.request_options["evidence_scope"] == scope
        assert saved.answer == body["answer"]
        assert saved.evidence_snapshot["analysis_context"] == body["analysis_context"]
        assert (
            saved.answer_audit_snapshot["claim_verification"]
            == "published_result_rows_verified"
        )
        assert saved.outcome == "answered"
    assert (
        client.get("/data/edna/analysis/runs/" + bundle["manifest"]["id"]).status_code
        == 403
    )
    second = client.post(
        "/chat",
        json={
            "query": QUESTIONS["fish_frequency"][0],
            "evidence_scope": scope,
            "research_intent": {"kind": "fish_frequency"},
        },
    )
    assert second.json()["abstention_reason"] == "aggregate_unavailable"


def test_conflicts_unsupported_questions_and_historical_analysis_abstain(
    tmp_path, monkeypatch
):
    bundle, source = research_chat_fixture(tmp_path, monkeypatch)
    identity = bundle["manifest"]["id"]
    scope = scope_for(identity)
    scope["sources"]["edna_metabarcoding"]["filters"]["provider_run_id"] = (
        "unrelated-run"
    )
    result = render_research(bundle, scope, QUESTIONS["fish_frequency"][0])
    assert result.reason == "aggregate_scope_required" and not result.documents
    for query in (
        "Show top fish detection frequencies in a different region",
        "Show top 20 fish detection frequencies",
        "Show top fish detection frequencies in 2019",
    ):
        assert parse_intent(query, bundle["recipe"]) is None
    assert (
        parse_intent(QUESTIONS["fish_frequency"][1] + "?", bundle["recipe"])
        == "fish_frequency"
    )
    assert (
        render_research(
            bundle,
            scope_for(identity),
            QUESTIONS["fish_frequency"][0],
            ResearchIntent(kind="monthly_spatial"),
        ).reason
        == "aggregate_scope_required"
    )
    changed = deepcopy(bundle)
    changed["tables"]["matched_panel"] = []
    assert (
        render_research(
            changed, scope_for(identity), QUESTIONS["distribution_change"][0]
        ).reason
        == "no_matching_evidence"
    )
    source["edna_detection"][0]["read_count"] += 1
    response = TestClient(app).post(
        "/chat",
        json={
            "query": QUESTIONS["fish_frequency"][0],
            "evidence_scope": scope_for(identity),
        },
    )
    assert response.json()["abstention_reason"] == "aggregate_unavailable"
    assert response.json()["model_invoked"] is False


def test_published_options_are_bounded_metadata_with_chat_permission(
    tmp_path, monkeypatch
):
    bundle, _ = research_chat_fixture(tmp_path, monkeypatch)
    response = TestClient(app).get("/chat/analysis-options")
    assert response.status_code == 200
    option = response.json()["options"][0]
    assert (
        option["analysis_id"] == bundle["manifest"]["id"]
        and len(option["workflows"]) == 6
    )
    assert "canonical" not in option and "sampling_registry" not in option
    assert route_permission("GET", "/chat/analysis-options") == "chat:use"
