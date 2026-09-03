import json
from types import SimpleNamespace
import sys

import pytest
import yaml

import config
from scripts import run_anemone_job as job
from ingestion.artifact_store import ArtifactStore


def test_job_default_is_offline_plan(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["job", "--stage", "acquire"])
    monkeypatch.setattr(job, "execute_stage", lambda _: pytest.fail("must not execute"))
    assert job.main() == 0
    assert json.loads(capsys.readouterr().out)["execute"] is False


@pytest.mark.parametrize(
    "options",
    [
        ["--execute", "--stage", "acquire"],
        ["--execute", "--stage", "import"],
        ["--execute", "--stage", "analyze"],
        ["--max-files", "2001"],
        ["--max-bytes", "536870913"],
        ["--stage", "acquire", "--validate-only"],
    ],
)
def test_job_rejects_missing_scope_and_excess_limits(tmp_path, monkeypatch, options):
    monkeypatch.setattr(config, "EDNA_ARTIFACT_URI", tmp_path.as_uri())
    monkeypatch.setattr(sys, "argv", ["job", *options])
    with pytest.raises(SystemExit):
        job.main()


def test_job_failure_report_never_serializes_exception_details(
    tmp_path, monkeypatch, capsys
):
    monkeypatch.setattr(config, "EDNA_ARTIFACT_URI", (tmp_path / "objects").as_uri())
    monkeypatch.setattr(config, "EDNA_CACHE_DIR", tmp_path / "cache")
    monkeypatch.setattr(sys, "argv", ["job", "--stage", "materialize", "--execute"])

    def fail(_):
        raise ValueError("secret-value-that-must-not-appear")

    monkeypatch.setattr(job, "execute_stage", fail)
    assert job.main() == 2
    output = capsys.readouterr().out
    assert "secret-value" not in output
    assert json.loads(output)["error_type"] == "ValueError"
    assert len(ArtifactStore(config.EDNA_ARTIFACT_URI).entries("operations")) == 1


def test_normalize_job_uses_verified_remote_raw_snapshot(tmp_path, monkeypatch):
    import preprocessing.anemone as normalizer

    monkeypatch.setattr(config, "EDNA_ARTIFACT_URI", (tmp_path / "objects").as_uri())
    monkeypatch.setattr(config, "RAW_ANEMONE_DIR", tmp_path / "cache" / "raw")
    monkeypatch.setattr(
        config, "ANEMONE_NORMALIZED_DIR", tmp_path / "cache" / "normalized"
    )
    store = ArtifactStore(config.EDNA_ARTIFACT_URI)
    store.publish(
        "raw", "a" * 64, {"manifest.json": b"{}"}, metadata={"snapshot_id": "b" * 64}
    )
    normalized_path = tmp_path / "synthetic-normalized"
    normalized_path.mkdir()
    (normalized_path / "normalization_manifest.json").write_text("{}")

    def normalize(identity, **kwargs):
        assert identity == "b" * 64
        assert (
            kwargs["raw_root"] / "snapshots" / identity / "manifest.json"
        ).read_bytes() == b"{}"
        assert kwargs["activate"] is False
        return {"normalization_id": "c" * 64, "bundle_path": str(normalized_path)}

    monkeypatch.setattr(normalizer, "normalize_anemone_snapshot", normalize)
    result = job.execute_stage(SimpleNamespace(stage="normalize", artifact_id="a" * 64))
    assert result["normalization_id"] == "c" * 64
    restored, metadata = job.restore_normalized(store, result["artifact_id"])
    assert restored == "c" * 64 and metadata["raw_artifact_id"] == "a" * 64


def test_anemone_job_templates_are_bounded_and_secret_files_pinned(tmp_path):
    from scripts.render_gcp_templates import (
        render_templates,
        ANEMONE_TEMPLATES,
        TOKEN_PATTERN,
    )

    values = {
        "PROJECT_ID": "example-project",
        "PROJECT_NUMBER": "123456789",
        "REGION": "asia-northeast1",
        "ARTIFACT_REPOSITORY": "ocean",
        "IMAGE_TAG": "test",
        "CLOUD_SQL_INSTANCE": "test-sql",
        "PUBLIC_APP_URL": "https://example.run.app",
        "OIDC_PROVIDER_ID_VALUE": "google",
        "OIDC_PROVIDER_NAME_VALUE": "Google",
        "OIDC_ISSUER_VALUE": "https://accounts.google.com",
        "OIDC_CLIENT_ID_VALUE": "test.apps.googleusercontent.com",
        "DATA_BUCKET": "test-data",
        "ANEMONE_IMAGE_DIGEST": "sha256:" + "a" * 64,
        "ANEMONE_USERNAME_VERSION": "1",
        "ANEMONE_PASSWORD_VERSION": "2",
    }
    render_templates(values, tmp_path, include_anemone=True)
    for filename in ANEMONE_TEMPLATES:
        path = tmp_path / filename.replace(".template.", ".rendered.")
        assert TOKEN_PATTERN.search(path.read_text()) is None
        spec = yaml.safe_load(path.read_text())["spec"]["template"]["spec"]
        assert spec["taskCount"] == spec["parallelism"] == 1
        task = spec["template"]["spec"]
        assert task["maxRetries"] == 0 and int(task["timeoutSeconds"]) == 1800
        assert "--execute" not in task["containers"][0]["args"]
        assert "@sha256:" in task["containers"][0]["image"]
        if "sync" in filename:
            assert "DATABASE_URL" not in path.read_text()
            assert all(
                v["secret"]["items"][0]["key"] in ("1", "2") for v in task["volumes"]
            )
        else:
            assert task["volumes"][0]["csi"]["readOnly"] is True
    with pytest.raises(ValueError, match="pinned"):
        render_templates(
            {**values, "ANEMONE_PASSWORD_VERSION": "latest"},
            tmp_path,
            include_anemone=True,
        )


def test_recipe_can_be_delivered_as_registered_cloud_configuration(
    tmp_path, monkeypatch
):
    from tests.test_edna_analysis import fixture
    import ingestion.edna_analysis_bundle as analyses

    monkeypatch.setattr(config, "EDNA_ARTIFACT_URI", (tmp_path / "objects").as_uri())
    recipe, _ = fixture()
    path = tmp_path / "reviewed.json"
    path.write_text(recipe.model_dump_json())
    args = SimpleNamespace(
        stage="recipe", recipe=path, environment=None, artifact_id=None
    )
    published = job.execute_stage(args)

    def run(selected, **kwargs):
        assert selected == recipe
        assert kwargs == {"execute": False, "environment": []}
        return {"validated": True}

    monkeypatch.setattr(analyses, "run_analysis", run)
    remote = SimpleNamespace(
        stage="analyze",
        recipe=None,
        environment=None,
        artifact_id=published["artifact_id"],
        validate_only=True,
    )
    assert job.execute_stage(remote) == {"validated": True}
