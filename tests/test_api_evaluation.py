import json
import threading

import pandas as pd
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

import api.main as api_main
from api.main import app
from evaluation.benchmark import SYSTEM_VARIANTS
from evaluation.questions import BENCHMARK_QUESTIONS


client = TestClient(app)


@pytest.fixture(autouse=True)
def saved_ablation_artifact(tmp_path, monkeypatch):
    """Create the saved-run contract without relying on ignored project data."""
    evaluation_dir = tmp_path / "evaluation"
    run_dir = evaluation_dir / "ablation_qwen2.5:14b-instruct"
    run_dir.mkdir(parents=True)

    rows = []
    for question_index, question in enumerate(BENCHMARK_QUESTIONS):
        for variant_index, variant in enumerate(SYSTEM_VARIANTS):
            score = 0.2 + variant_index * 0.1 + question_index * 0.001
            rows.append(
                {
                    "question_id": question.id,
                    "category": question.category,
                    "question": question.question,
                    "mode": variant.name,
                    "n_retrieved": variant.source_coverage,
                    "retrieval_precision": min(score, 1.0),
                    "source_coverage": min(score + 0.02, 1.0),
                    "citation_count": variant_index,
                    "citation_accuracy": min(score + 0.04, 1.0),
                    "context_utilization": min(score + 0.06, 1.0),
                    "latency_seconds": 1.0 + variant_index * 0.2,
                    "response": f"Synthetic response for {question.id}",
                    "cited_ids": "[]",
                    "error": "",
                    "rouge_l": min(score + 0.01, 1.0),
                    "faithfulness": min(score + 0.03, 1.0),
                    "answer_completeness": min(score + 0.05, 1.0),
                    "semantic_similarity": min(score + 0.07, 1.0),
                }
            )

    pd.DataFrame(rows).to_csv(run_dir / "ablation_results.csv", index=False)
    (run_dir / "ablation_meta.json").write_text(
        json.dumps(
            {
                "model": "qwen2.5:14b-instruct",
                "n_questions": len(BENCHMARK_QUESTIONS),
                "n_variants": len(SYSTEM_VARIANTS),
                "n_evaluations": len(rows),
                "variants": [variant.name for variant in SYSTEM_VARIANTS],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(api_main.config, "EVALUATION_DIR", evaluation_dir)


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


def test_evaluation_analytics_returns_chart_ready_payload():
    response = client.get(
        "/evaluation/runs/ablation_qwen2.5:14b-instruct/analytics",
        params={"metric": "source_coverage", "baseline_mode": "Full framework"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["selected_metric"] == "source_coverage"
    assert payload["baseline_mode"] == "Full framework"
    assert payload["by_mode"]
    assert "delta_from_baseline" in payload["by_mode"][0]
    assert payload["mode_category_matrix"]["categories"]
    assert payload["mode_category_matrix"]["rows"]
    assert payload["lowest_scoring_questions"]
    assert payload["statistical_tests"]["status"] == "available"
    assert payload["statistical_tests"]["friedman"]
    assert "source_coverage" in payload["statistical_tests"]["significance_matrix"]


def test_evaluation_analytics_supports_category_filter():
    response = client.get(
        "/evaluation/runs/ablation_qwen2.5:14b-instruct/analytics",
        params={"metric": "retrieval_precision", "category": "Single-source (CTD)"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["filters"]["category"] == "Single-source (CTD)"
    assert {row["category"] for row in payload["by_category"]} == {"Single-source (CTD)"}


def test_evaluation_analytics_rejects_unknown_metric():
    response = client.get(
        "/evaluation/runs/ablation_qwen2.5:14b-instruct/analytics",
        params={"metric": "not_a_metric"},
    )

    assert response.status_code == 400
    assert "Unknown or unavailable evaluation metric" in response.text


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


def test_evaluation_job_status_rejects_unsafe_ids():
    with pytest.raises(HTTPException) as exc_info:
        api_main._job_status_path("../escape")
    assert exc_info.value.status_code == 404


def test_evaluation_start_rejects_when_local_job_capacity_is_full(monkeypatch):
    slots = threading.BoundedSemaphore(1)
    assert slots.acquire(blocking=False)
    monkeypatch.setattr(api_main, "LOCAL_JOB_SLOTS", slots)

    try:
        response = client.post(
            "/evaluation/runs/standard",
            json={"quick": True},
        )
    finally:
        slots.release()

    assert response.status_code == 429
    assert response.json()["detail"]["code"] == "local_job_capacity_reached"


def test_cloud_runtime_delegates_evaluation_execution(monkeypatch):
    monkeypatch.setattr(api_main.config, "JOB_EXECUTION_MODE", "external")

    response = client.post(
        "/evaluation/runs/standard",
        json={"quick": True},
    )

    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "external_job_runner_required"
