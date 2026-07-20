import json
import time

from fastapi.testclient import TestClient

import api.main as api_main
from api.main import app


client = TestClient(app)


def _wait_for_pipeline_job(job_id: str, timeout: float = 5.0) -> dict:
    deadline = time.time() + timeout
    payload = {}
    while time.time() < deadline:
        response = client.get(f"/pipeline/jobs/{job_id}")
        assert response.status_code == 200
        payload = response.json()
        if payload["status"] in {"complete", "failed", "cancelled"}:
            return payload
        time.sleep(0.05)
    raise AssertionError(f"Pipeline job did not finish in {timeout}s: {payload}")


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


def test_pipeline_preflight_returns_exact_command_plan():
    response = client.post(
        "/pipeline/preflight",
        json={
            "stages": ["load_db"],
            "dry_run": True,
            "reset_database": True,
            "embed_after_load": False,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["checks"]
    assert payload["command_plan"][0]["stage_id"] == "load_db"
    assert "--reset" in payload["command_plan"][0]["display_command"]
    assert "--embed" not in payload["command_plan"][0]["display_command"]


def test_pipeline_preflight_reports_real_db_reset_blocker():
    response = client.post(
        "/pipeline/preflight",
        json={"stages": ["load_db"], "dry_run": False, "reset_database": False},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is False
    assert any("reset_database=true" in blocker for blocker in payload["blockers"])


def test_pipeline_status_reports_active_jobs_and_artifact_freshness(tmp_path, monkeypatch):
    monkeypatch.setattr(api_main.config, "DATA_DIR", tmp_path)
    job_id = "pipeline_active_contract"
    run_dir = tmp_path / "pipeline_runs" / job_id
    run_dir.mkdir(parents=True)
    progress = {
        "job_id": job_id,
        "run_id": job_id,
        "status": "running",
        "current": 1,
        "total": 3,
        "percent": 33.33,
        "phase": "running_stage",
        "stage_id": "ingest",
        "message": "Running ingest",
        "updated_at": "2026-07-20T12:00:00+09:00",
        "output_dir": str(run_dir),
        "log_path": str(run_dir / "run.log"),
        "stages": ["validate_raw", "ingest", "build_retrieval_docs"],
    }
    (run_dir / "progress.json").write_text(json.dumps(progress), encoding="utf-8")

    response = client.get("/pipeline/status")

    assert response.status_code == 200
    payload = response.json()
    assert any(job["job_id"] == job_id for job in payload["active_jobs"])
    assert payload["artifact_freshness"]
    first_freshness = payload["artifact_freshness"][0]
    assert {"id", "kind", "freshness_status", "lineage_status", "age_days"}.issubset(first_freshness)


def test_pipeline_database_load_requires_reset_for_real_run():
    response = client.post(
        "/pipeline/jobs",
        json={"stages": ["load_db"], "dry_run": False, "reset_database": False},
    )

    assert response.status_code == 400
    assert "reset_database=true" in response.text


def test_pipeline_dry_run_writes_manifest_and_history(tmp_path, monkeypatch):
    monkeypatch.setattr(api_main.config, "DATA_DIR", tmp_path)

    response = client.post(
        "/pipeline/jobs",
        json={
            "stages": ["validate_raw"],
            "dry_run": True,
            "tag": "pytest-dry-run",
            "notes": "manifest contract test",
        },
    )

    assert response.status_code == 200
    started = response.json()
    status = _wait_for_pipeline_job(started["job_id"])
    assert status["status"] == "complete"

    detail_response = client.get(f"/pipeline/runs/{started['run_id']}")
    assert detail_response.status_code == 200
    detail = detail_response.json()
    manifest = detail["manifest"]
    assert detail["summary"]["run_id"] == started["run_id"]
    assert manifest["request"]["dry_run"] is True
    assert manifest["preflight"]["ok"] is True
    assert manifest["stage_results"][0]["status"] == "planned"
    assert "artifacts_before" in manifest
    assert "artifacts_after" in manifest
    assert "diffs" in manifest
    assert "DRY RUN" in detail["log_tail"]
    assert detail["stage_logs"][0]["stage_id"] == "validate_raw"
    assert detail["stage_logs"][0]["status"] == "planned"
    assert "DRY RUN" in detail["stage_logs"][0]["log"]

    log_response = client.get(f"/pipeline/jobs/{started['job_id']}/log")
    assert log_response.status_code == 200
    log_payload = log_response.json()
    assert log_payload["stage_logs"][0]["stage_id"] == "validate_raw"
    assert log_payload["stage_logs"][0]["line_count"] > 0

    runs_response = client.get("/pipeline/runs")
    assert runs_response.status_code == 200
    run_ids = {run["run_id"] for run in runs_response.json()["runs"]}
    assert started["run_id"] in run_ids


def test_pipeline_job_status_requires_known_job():
    response = client.get("/pipeline/jobs/missing-job")

    assert response.status_code == 404


def test_pipeline_job_log_requires_known_job():
    response = client.get("/pipeline/jobs/missing-job/log")

    assert response.status_code == 404
