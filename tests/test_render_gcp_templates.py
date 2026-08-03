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
        "OIDC_PROVIDER_ID": "google",
        "OIDC_PROVIDER_NAME": "Google",
        "OIDC_ISSUER": "https://accounts.google.com",
        "OIDC_CLIENT_ID": "client.apps.googleusercontent.com",
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
