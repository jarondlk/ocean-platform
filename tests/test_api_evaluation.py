from fastapi.testclient import TestClient

from api.main import app


client = TestClient(app)


def test_evaluation_catalog_exposes_questions_modes_and_variants():
    response = client.get("/evaluation/catalog")

    assert response.status_code == 200
    payload = response.json()
    assert len(payload["questions"]) == 15
    assert {mode["name"] for mode in payload["modes"]} == {
        "Baseline",
        "+Analysis",
        "+Reliability",
        "Full",
    }
    assert len(payload["variants"]) == 7
    assert payload["questions"][0]["reference_answer"]


def test_evaluation_runs_include_saved_ablation_artifact():
    response = client.get("/evaluation/runs")

    assert response.status_code == 200
    runs = response.json()["runs"]
    run_ids = {run["run_id"] for run in runs}
    assert "ablation_qwen2.5:14b-instruct" in run_ids
    ablation = next(run for run in runs if run["run_id"] == "ablation_qwen2.5:14b-instruct")
    assert ablation["run_type"] == "ablation"
    assert ablation["n_evaluations"] == 105
    assert ablation["has_quality_metrics"] is True


def test_evaluation_run_detail_returns_rows_and_summary():
    response = client.get("/evaluation/runs/ablation_qwen2.5:14b-instruct?limit=3")

    assert response.status_code == 200
    payload = response.json()
    assert payload["row_count"] == 105
    assert len(payload["rows"]) == 3
    assert "by_mode" in payload["summary"]
    assert payload["summary"]["by_mode"]


def test_evaluation_report_can_be_generated_from_legacy_csv():
    response = client.get("/evaluation/runs/ablation_qwen2.5:14b-instruct/report")

    assert response.status_code == 200
    payload = response.json()
    assert payload["run_id"] == "ablation_qwen2.5:14b-instruct"
    assert "Evaluation Report" in payload["markdown"]


def test_evaluation_compare_requires_known_runs():
    response = client.post(
        "/evaluation/compare",
        json={"run_ids": ["ablation_qwen2.5:14b-instruct", "missing"]},
    )

    assert response.status_code == 404


def test_evaluation_standard_start_rejects_unknown_mode():
    response = client.post(
        "/evaluation/runs/standard",
        json={"quick": True, "modes": ["Not a mode"]},
    )

    assert response.status_code == 400
    assert "Unknown evaluation mode" in response.text


def test_evaluation_ablation_start_rejects_unknown_variant():
    response = client.post(
        "/evaluation/runs/ablation",
        json={"quick": True, "variants": ["Not a variant"]},
    )

    assert response.status_code == 400
    assert "Unknown ablation variant" in response.text


def test_evaluation_job_status_requires_known_job():
    response = client.get("/evaluation/jobs/missing-job")

    assert response.status_code == 404
