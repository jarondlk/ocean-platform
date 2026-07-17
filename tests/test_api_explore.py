import pytest
from fastapi.testclient import TestClient

import config
from api.main import app


pytestmark = pytest.mark.skipif(
    not (config.NORMALIZED_DIR / "ctd_summary.parquet").exists(),
    reason="explore API tests require local parquet artifacts",
)


def test_explore_catalog_includes_ctd_summary():
    client = TestClient(app)

    response = client.get("/explore/catalog")

    assert response.status_code == 200
    ids = {item["id"] for item in response.json()}
    assert "ctd_summary" in ids


def test_explore_table_returns_paginated_rows():
    client = TestClient(app)

    response = client.get("/explore/table?dataset=ctd_summary&limit=2")

    assert response.status_code == 200
    payload = response.json()
    assert payload["dataset"] == "ctd_summary"
    assert payload["filtered"] >= 2
    assert len(payload["rows"]) == 2
    assert "mean_temperature" in payload["columns"]


def test_explore_timeseries_returns_points():
    client = TestClient(app)

    response = client.get(
        "/explore/timeseries?dataset=ctd_summary&y_column=mean_temperature"
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["x_column"] == "ctd_date"
    assert payload["y_column"] == "mean_temperature"
    assert payload["points"]


def test_explore_sample_detail_joins_sample_rows():
    client = TestClient(app)

    response = client.get("/explore/sample/2024-01-O-s1")

    assert response.status_code == 200
    payload = response.json()
    assert payload["sample_id"] == "2024-01-O-s1"
    assert payload["registry"]["sample_id"] == "2024-01-O-s1"
    assert payload["ctd"]


def test_debug_state_redacts_database_url():
    client = TestClient(app)

    response = client.get("/debug")

    assert response.status_code == 200
    payload = response.json()
    assert payload["config"]["database_url"]
    assert "://onagawa:***@" in payload["config"]["database_url"]
    assert "Raw process environment is intentionally omitted." in payload["notes"]


def test_data_catalog_exposes_data_page_inputs():
    client = TestClient(app)

    response = client.get("/data/catalog")

    assert response.status_code == 200
    payload = response.json()
    assert "2024-01-O-s1" in payload["ctd_samples"]
    assert "temperature" in payload["ctd_variables"]
    assert payload["sst_observations"] > 0


def test_data_ctd_profile_returns_depth_rows():
    client = TestClient(app)

    response = client.get("/data/ctd-profile/2024-01-O-s1")

    assert response.status_code == 200
    payload = response.json()
    assert payload["sample_id"] == "2024-01-O-s1"
    assert payload["summary"]["sample_id"] == "2024-01-O-s1"
    assert payload["rows"][0]["depth_m"] == 0
    assert "temperature" in payload["variables"]


def test_data_sst_returns_points_and_daily_range():
    client = TestClient(app)

    response = client.get("/data/sst?limit=5")

    assert response.status_code == 200
    payload = response.json()
    assert payload["observations"] == 5
    assert payload["days"] > 0
    assert payload["points"]
    assert payload["daily"]


def test_analysis_state_includes_reliability_and_cooccurrence():
    client = TestClient(app)

    response = client.get("/analysis?cooccurrence_pairs=5&table_limit=20")

    assert response.status_code == 200
    payload = response.json()
    assert payload["catalog"]["ctd_monthly_trends"]["exists"] is True
    assert payload["ctd_trends"]["rows"]
    assert payload["correlations"]["summary"]["total"] > 0
    assert len(payload["cooccurrence"]["top_pairs"]) == 5
    assert payload["reliability"]["sst_ctd"]["summary"]["paired"] > 0


def test_database_query_rejects_mutation_sql_before_execution():
    client = TestClient(app)

    response = client.post(
        "/database/query",
        json={"sql": "DELETE FROM retrieval_document", "limit": 10},
    )

    assert response.status_code == 400
    assert "Only SELECT/WITH queries are allowed" in response.text
