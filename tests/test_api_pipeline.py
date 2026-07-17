from fastapi.testclient import TestClient

from api.main import app


client = TestClient(app)


def test_pipeline_status_exposes_manual_stages_and_artifacts():
    response = client.get("/pipeline/status")

    assert response.status_code == 200
    payload = response.json()
    stage_ids = {stage["id"] for stage in payload["stages"]}
    assert {
        "validate_raw",
        "ingest",
        "build_retrieval_docs",
        "pre_analysis",
        "reliability",
        "load_db",
        "embed_documents",
    }.issubset(stage_ids)
    assert payload["readiness"]["manual_only"] is True
    assert payload["raw_sources"]
    assert payload["artifacts"]


def test_pipeline_start_rejects_unknown_stage():
    response = client.post(
        "/pipeline/jobs",
        json={"stages": ["missing_stage"], "dry_run": True},
    )

    assert response.status_code == 400
    assert "Unknown pipeline stage" in response.text


def test_pipeline_database_load_requires_reset_for_real_run():
    response = client.post(
        "/pipeline/jobs",
        json={"stages": ["load_db"], "dry_run": False, "reset_database": False},
    )

    assert response.status_code == 400
    assert "reset_database=true" in response.text


def test_pipeline_job_status_requires_known_job():
    response = client.get("/pipeline/jobs/missing-job")

    assert response.status_code == 404


def test_pipeline_job_log_requires_known_job():
    response = client.get("/pipeline/jobs/missing-job/log")

    assert response.status_code == 404
