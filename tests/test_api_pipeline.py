import json
import threading
import time

from fastapi import HTTPException
import pytest
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
        "backup_database",
        "load_db",
        "materialize_edna_retrieval",
        "embed_documents",
        "publish_provenance",
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


@pytest.mark.parametrize("unsafe_id", ["../escape", "/tmp/escape", "nested/escape", "..%2Fescape"])
def test_pipeline_artifact_paths_reject_unsafe_ids(unsafe_id):
    with pytest.raises(HTTPException) as exc_info:
        api_main._pipeline_status_path(unsafe_id)
    assert exc_info.value.status_code == 404


def test_pipeline_start_rejects_when_local_job_capacity_is_full(monkeypatch):
    slots = threading.BoundedSemaphore(1)
    assert slots.acquire(blocking=False)
    monkeypatch.setattr(api_main, "LOCAL_JOB_SLOTS", slots)

    try:
        response = client.post(
            "/pipeline/jobs",
            json={"stages": ["validate_raw"], "dry_run": True},
        )
    finally:
        slots.release()

    assert response.status_code == 429
    assert response.json()["detail"]["code"] == "local_job_capacity_reached"


def test_cloud_runtime_delegates_pipeline_execution(monkeypatch):
    monkeypatch.setattr(api_main.config, "JOB_EXECUTION_MODE", "external")

    response = client.post(
        "/pipeline/jobs",
        json={"stages": ["validate_raw"], "dry_run": True},
    )

    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "external_job_runner_required"


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


def test_pipeline_backup_command_requires_disposable_restore_test():
    response = client.post(
        "/pipeline/preflight",
        json={
            "stages": ["backup_database", "load_db"],
            "dry_run": True,
            "embed_after_load": False,
        },
    )

    assert response.status_code == 200
    backup = response.json()["command_plan"][0]
    assert backup["stage_id"] == "backup_database"
    assert "--restore-test" in backup["command"]


def test_pipeline_backup_preflight_skips_unused_model_probe(monkeypatch):
    def fail_if_called():
        raise AssertionError("backup-only preflight must not probe the model")

    monkeypatch.setattr(api_main, "_ollama_status", fail_if_called)

    response = client.post(
        "/pipeline/preflight",
        json={"stages": ["backup_database"], "dry_run": True},
    )

    assert response.status_code == 200
    model_status = response.json()["ollama"]
    assert model_status["skipped"] is True
    assert model_status["available"] is None


def test_pipeline_embedding_preflight_probes_configured_model(monkeypatch):
    monkeypatch.setattr(
        api_main,
        "_ollama_status",
        lambda: {"available": True, "provider": "vertex"},
    )

    response = client.post(
        "/pipeline/preflight",
        json={"stages": ["embed_documents"], "dry_run": True},
    )

    assert response.status_code == 200
    assert response.json()["ollama"] == {
        "available": True,
        "provider": "vertex",
    }


def test_provenance_publication_has_safe_dry_run_and_requires_execution_tag():
    dry_run = client.post(
        "/pipeline/preflight",
        json={"stages": ["publish_provenance"], "dry_run": True},
    )
    execute = client.post(
        "/pipeline/preflight",
        json={"stages": ["publish_provenance"], "dry_run": False},
    )

    assert dry_run.status_code == 200
    plan = dry_run.json()["command_plan"][0]
    assert plan["stage_id"] == "publish_provenance"
    assert "--publish" in plan["command"]
    assert "dry-run-placeholder" in plan["command"]
    dry_run_check = next(
        check
        for check in dry_run.json()["checks"]
        if check["id"] == "provenance_publication_id"
    )
    execute_check = next(
        check
        for check in execute.json()["checks"]
        if check["id"] == "provenance_publication_id"
    )
    assert dry_run_check["status"] == "pass"
    assert execute_check["status"] == "fail"


def test_provenance_publication_records_actual_pipeline_run_id():
    request = api_main.PipelineRunRequest(
        stages=["publish_provenance"],
        dry_run=False,
        tag="manifest-20260824",
    )

    command = api_main._pipeline_command(
        "publish_provenance",
        request,
        pipeline_run_id="pipeline-actual-20260824T120000",
    )

    assert command[command.index("--run-id") + 1] == "manifest-20260824"
    assert (
        command[command.index("--pipeline-run-id") + 1]
        == "pipeline-actual-20260824T120000"
    )


def test_pipeline_preflight_requires_backup_before_real_database_mutation():
    response = client.post(
        "/pipeline/preflight",
        json={"stages": ["load_db"], "dry_run": False, "reset_database": False},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is False
    assert any("backup_database before load_db" in blocker for blocker in payload["blockers"])


def test_pipeline_reset_requires_exact_server_side_confirmation():
    request = {
        "stages": ["backup_database", "load_db"],
        "dry_run": False,
        "reset_database": True,
        "embed_after_load": False,
    }

    missing = client.post("/pipeline/preflight", json=request)
    incorrect = client.post(
        "/pipeline/preflight",
        json={**request, "reset_confirmation": "reset database"},
    )
    accepted = client.post(
        "/pipeline/preflight",
        json={**request, "reset_confirmation": "RESET DATABASE"},
    )
    blocked_start = client.post("/pipeline/jobs", json=request)

    assert missing.status_code == 200
    assert incorrect.status_code == 200
    assert accepted.status_code == 200
    missing_check = next(
        check
        for check in missing.json()["checks"]
        if check["id"] == "database_reset_confirmation"
    )
    incorrect_check = next(
        check
        for check in incorrect.json()["checks"]
        if check["id"] == "database_reset_confirmation"
    )
    accepted_check = next(
        check
        for check in accepted.json()["checks"]
        if check["id"] == "database_reset_confirmation"
    )
    assert missing_check["status"] == "fail"
    assert incorrect_check["status"] == "fail"
    assert accepted_check["status"] == "pass"
    assert blocked_start.status_code == 400
    assert "RESET DATABASE" in blocked_start.text


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
    assert {row["kind"] for row in payload["artifact_freshness"]} <= {"raw", "derived"}
    assert {row["freshness_status"] for row in payload["artifact_freshness"]} <= {
        "recent",
        "aged",
        "archival",
        "missing",
        "unknown",
    }
    assert any(row["kind"] == "derived" for row in payload["artifact_freshness"])


def test_pipeline_database_load_requires_backup_for_real_run():
    response = client.post(
        "/pipeline/jobs",
        json={"stages": ["load_db"], "dry_run": False, "reset_database": False},
    )

    assert response.status_code == 400
    assert "backup_database before load_db" in response.text


def test_pipeline_dry_run_writes_manifest_and_history(tmp_path, monkeypatch):
    monkeypatch.setattr(api_main.config, "DATA_DIR", tmp_path)
    raw_ctd = tmp_path / "raw" / "ctd" / "CTD_Onagawa.tsv"
    raw_ctd.parent.mkdir(parents=True)
    raw_ctd.write_text("date\tdepth\ttemperature\n", encoding="utf-8")
    monkeypatch.setattr(api_main.config, "RAW_FILES", {"ctd": raw_ctd})

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
