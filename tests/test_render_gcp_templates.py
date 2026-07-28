from __future__ import annotations

from pathlib import Path

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
