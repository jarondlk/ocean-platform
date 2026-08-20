from __future__ import annotations

import json
from pathlib import Path

import yaml

import scripts.render_gcp_templates as renderer


def test_gcp_templates_render_without_secret_values(tmp_path: Path):
    values = {
        "PROJECT_ID": "example-project",
        "PROJECT_NUMBER": "123456789",
        "REGION": "asia-northeast1",
        "ARTIFACT_REPOSITORY": "example-repository",
        "IMAGE_TAG": "build-123",
        "CLOUD_SQL_INSTANCE": "example-postgres",
        "PUBLIC_APP_URL": "https://example.run.app",
        "OIDC_PROVIDER_ID_VALUE": "google",
        "OIDC_PROVIDER_NAME_VALUE": "Google",
        "OIDC_ISSUER_VALUE": "https://accounts.google.com",
        "OIDC_CLIENT_ID_VALUE": "client.apps.googleusercontent.com",
        "OLLAMA_PRIVATE_URL": "https://model.internal",
        "DATA_BUCKET": "example-data",
    }

    paths = renderer.render_templates(values, tmp_path)

    assert len(paths) == len(renderer.TEMPLATES)
    assert all(path.exists() for path in paths)
    combined = "\n".join(path.read_text() for path in paths)
    assert renderer.TOKEN_PATTERN.search(combined) is None
    assert "secret-value-that-must-not-appear" not in combined

    documents = {
        path.name: yaml.safe_load(path.read_text(encoding="utf-8"))
        for path in paths
    }
    service = documents["service.rendered.yaml"]
    assert service["metadata"]["labels"]["cost_component"] == "serving"
    assert service["metadata"]["annotations"]["run.googleapis.com/maxScale"] == "1"
    assert (
        service["spec"]["template"]["metadata"]["annotations"]
        ["autoscaling.knative.dev/maxScale"]
        == "1"
    )
    assert (
        service["spec"]["template"]["metadata"]["annotations"]
        ["autoscaling.knative.dev/minScale"]
        == "0"
    )
    frontend = service["spec"]["template"]["spec"]["containers"][0]
    frontend_env = {
        setting["name"]: setting.get("value")
        for setting in frontend["env"]
    }
    assert frontend_env["AUTH_TRUST_HOST"] == "true"
    assert frontend_env["OIDC_PROVIDER_NAME"] == "Google"
    assert frontend_env["OIDC_PROVIDER_ID"] == "google"
    assert frontend_env["OIDC_ISSUER"] == "https://accounts.google.com"
    assert (
        frontend_env["OIDC_CLIENT_ID"]
        == "client.apps.googleusercontent.com"
    )
    api = service["spec"]["template"]["spec"]["containers"][1]
    api_env = {
        setting["name"]: setting.get("value")
        for setting in api["env"]
    }
    assert api_env["AUTH_ALLOWED_PROVIDERS"] == "google"
    assert api_env["DATA_DIR"] == "/mnt/onagawa-data"
    assert api_env["SST_NETCDF_DIR"] == "/mnt/onagawa-data/raw/sst-netcdf"
    assert api_env["HIMAWARI_RAW_DIR"] == "/mnt/onagawa-data/raw/himawari"
    assert api_env["MODEL_PROVIDER"] == "vertex"
    assert api_env["GOOGLE_CLOUD_PROJECT"] == "example-project"
    assert api_env["GOOGLE_CLOUD_LOCATION"] == "global"
    assert api_env["CHAT_MODEL"] == "gemini-3.6-flash"
    assert api_env["EMBEDDING_MODEL"] == "gemini-embedding-001"
    assert api_env["CHAT_MAX_OUTPUT_TOKENS"] == "1600"
    assert api_env["VERTEX_THINKING_BUDGET"] == "0"
    assert "OLLAMA_BASE_URL" not in api_env

    expected_job_labels = {
        "job-migrate.rendered.yaml": "migration",
        "job-pipeline.rendered.yaml": "pipeline",
        "job-embedding.rendered.yaml": "embedding",
        "job-evaluation.rendered.yaml": "evaluation",
    }
    for filename, component in expected_job_labels.items():
        job = documents[filename]
        assert job["metadata"]["labels"]["cost_component"] == component
        assert (
            job["spec"]["template"]["spec"]["template"]["spec"]["maxRetries"]
            == 0
        )

    pipeline = documents["job-pipeline.rendered.yaml"]
    pipeline_task = pipeline["spec"]["template"]["spec"]["template"]["spec"]
    assert pipeline_task["timeoutSeconds"] == "1800"
    assert pipeline_task["containers"][0]["args"] == [
        "scripts/run_pipeline.py",
        "--dry-run",
        "--no-embed",
        "--json",
    ]

    embedding = documents["job-embedding.rendered.yaml"]
    embedding_task = embedding["spec"]["template"]["spec"]["template"]["spec"]
    embedding_container = embedding_task["containers"][0]
    embedding_env = {
        setting["name"]: setting.get("value")
        for setting in embedding_container["env"]
    }
    assert embedding_task["timeoutSeconds"] == "1800"
    assert embedding_container["args"] == [
        "scripts/update_embeddings.py",
        "--batch-size",
        "32",
        "--dry-run",
        "--limit",
        "16",
    ]
    assert embedding_env["MODEL_PROVIDER"] == "vertex"
    assert embedding_env["GOOGLE_CLOUD_PROJECT"] == "example-project"
    assert embedding_env["GOOGLE_CLOUD_LOCATION"] == "global"
    assert embedding_env["EMBEDDING_MODEL"] == "gemini-embedding-001"
    assert embedding_env["EMBEDDING_DIM"] == "768"
    assert embedding_env["MODEL_REQUEST_TIMEOUT_SECONDS"] == "120"

    evaluation = documents["job-evaluation.rendered.yaml"]
    evaluation_task = evaluation["spec"]["template"]["spec"]["template"]["spec"]
    evaluation_container = evaluation_task["containers"][0]
    evaluation_env = {
        setting["name"]: setting.get("value")
        for setting in evaluation_container["env"]
    }
    assert evaluation_container["args"] == [
        "scripts/run_evaluation.py",
        "--questions",
        "ctd_01",
        "--modes",
        "Full",
    ]
    assert evaluation_env["MODEL_PROVIDER"] == "vertex"
    assert evaluation_env["CHAT_MODEL"] == "gemini-3.6-flash"
    assert evaluation_env["CHAT_MAX_OUTPUT_TOKENS"] == "1600"
    assert evaluation_env["VERTEX_THINKING_BUDGET"] == "0"
    assert evaluation_env["MODEL_REQUEST_TIMEOUT_SECONDS"] == "120"


def test_gcp_upload_script_is_raw_only_and_non_deleting():
    script = (renderer.TEMPLATE_DIR / "upload-data.sh").read_text(
        encoding="utf-8"
    )

    assert 'UPLOAD_MODE="${UPLOAD_MODE:-dry-run}"' in script
    assert 'RAW_DIR="$PROJECT_ROOT/data/raw"' in script
    assert 'SST_DIR="$PROJECT_ROOT/onagawa_sst_subset"' in script
    assert 'gcloud storage rsync data ' not in script
    assert "--delete-unmatched-destination-objects" not in script
    assert script.count("--exclude='.*\\.DS_Store$'") == 4
    assert "build_gcp_seed_manifest.py" in script
    assert "manifests/$SEED_TAG.json" in script


def test_gcp_retention_policies_are_bounded():
    storage = json.loads(
        (renderer.TEMPLATE_DIR / "storage-lifecycle.json").read_text(
            encoding="utf-8"
        )
    )
    rules = storage["lifecycle"]["rule"]
    version_rule = next(
        rule for rule in rules if "daysSinceNoncurrentTime" in rule["condition"]
    )
    assert version_rule["condition"] == {"daysSinceNoncurrentTime": 30}
    count_rule = next(
        rule for rule in rules if "numNewerVersions" in rule["condition"]
    )
    assert count_rule["condition"] == {
        "numNewerVersions": 3,
        "isLive": False,
    }

    cleanup = json.loads(
        (renderer.TEMPLATE_DIR / "artifact-cleanup-policy.json").read_text(
            encoding="utf-8"
        )
    )
    delete = next(
        policy for policy in cleanup if policy["action"]["type"] == "Delete"
    )
    assert delete["condition"] == {"tagState": "any", "olderThan": "30d"}
    keep = next(policy for policy in cleanup if policy["action"]["type"] == "Keep")
    assert keep["mostRecentVersions"]["keepCount"] == 5
