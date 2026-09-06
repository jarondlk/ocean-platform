import json
from contextlib import contextmanager
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


def test_controlled_application_default_is_offline_without_review_id(
    monkeypatch, capsys
):
    monkeypatch.setattr(sys, "argv", ["job", "--stage", "apply-classification"])
    monkeypatch.setattr(job, "execute_stage", lambda _: pytest.fail("must not execute"))
    assert job.main() == 0
    plan = json.loads(capsys.readouterr().out)
    assert plan["stage"] == "apply-classification"
    assert plan["execute"] is False


def test_controlled_application_runs_the_fixed_order_and_finalizes(monkeypatch):
    import api.classification_application_service as lifecycle
    import db.connection as connection_module

    calls = []
    application = SimpleNamespace(id="application-id")

    @contextmanager
    def session():
        yield object()

    class Connection:
        dialect = SimpleNamespace(name="sqlite")

        def close(self):
            calls.append("lock_closed")

    monkeypatch.setattr(connection_module, "get_session", session)
    monkeypatch.setattr(
        connection_module,
        "get_engine",
        lambda: SimpleNamespace(connect=lambda: Connection()),
    )
    monkeypatch.setattr(lifecycle, "workload_actor", lambda _session: "actor")
    monkeypatch.setattr(
        lifecycle,
        "begin_application",
        lambda *_args, **_kwargs: application,
    )
    monkeypatch.setattr(
        lifecycle,
        "start_stage",
        lambda _session, _application_id, stage: (
            application,
            calls.append(f"start:{stage}") is None,
        ),
    )
    monkeypatch.setattr(
        lifecycle,
        "complete_stage",
        lambda _session, _application_id, stage, _result: calls.append(
            f"complete:{stage}"
        ),
    )
    monkeypatch.setattr(
        lifecycle,
        "finalize_application",
        lambda *_args: calls.append("finalize"),
    )
    monkeypatch.setattr(lifecycle, "_load_application", lambda *_args: application)
    monkeypatch.setattr(lifecycle, "application_summary", lambda _application: {"status": "applied"})
    monkeypatch.setattr(
        job,
        "_execute_application_stage",
        lambda stage, _application_id: calls.append(f"execute:{stage}") or {},
    )
    result = job.run_controlled_application(
        SimpleNamespace(
            classification_review_id="00000000-0000-4000-8000-000000000001",
            rollback_of=None,
            operation_id="ordered-run",
        )
    )
    assert result == {"status": "applied"}
    expected = []
    for stage in lifecycle.APPLICATION_STAGES:
        expected.append(f"start:{stage}")
        if stage == "finalize":
            expected.append("finalize")
        else:
            expected.extend((f"execute:{stage}", f"complete:{stage}"))
    assert calls == [*expected, "lock_closed"]


@pytest.mark.parametrize(
    "options",
    [
        ["--execute", "--stage", "acquire"],
        ["--execute", "--stage", "import"],
        ["--execute", "--stage", "analyze"],
        ["--max-files", "2001"],
        ["--max-bytes", "536870913"],
        ["--stage", "acquire", "--validate-only"],
        ["--stage", "classification-review", "--execute"],
        ["--stage", "import", "--classification-review", "review.json"],
        ["--stage", "acquire", "--classification-review-artifact-id", "a" * 64],
        ["--stage", "normalize", "--classification-review", "review.json", "--classification-review-artifact-id", "a" * 64],
        ["--stage", "apply-classification", "--execute"],
        ["--stage", "apply-classification", "--execute", "--classification-review-id", "not-a-uuid"],
        ["--stage", "acquire", "--rollback-of", "00000000-0000-0000-0000-000000000000"],
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
            environment = {
                item["name"]: item.get("value")
                for item in task["containers"][0]["env"]
            }
            assert environment["SST_NETCDF_DIR"] == "/mnt/ocean-data/raw/sst-netcdf"
            assert environment["HIMAWARI_RAW_DIR"] == "/mnt/ocean-data/raw/himawari"
            assert environment["DEPLOYMENT_ENV"] == "production"
            assert environment["CLASSIFICATION_APPLICATION_ACTOR_SUBJECT"] == (
                "ocean-jobs@example-project.iam.gserviceaccount.com"
            )
            assert task["containers"][0]["args"] == [
                "scripts/run_anemone_job.py",
                "--stage",
                "apply-classification",
            ]
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


def test_review_can_be_delivered_as_registered_cloud_configuration(tmp_path, monkeypatch):
    from tests.test_anemone_classification import minimal_review
    import preprocessing.anemone as normalizer

    monkeypatch.setattr(config, "EDNA_ARTIFACT_URI", (tmp_path / "objects").as_uri())
    monkeypatch.setattr(config, "RAW_ANEMONE_DIR", tmp_path / "raw")
    monkeypatch.setattr(config, "ANEMONE_NORMALIZED_DIR", tmp_path / "normalized")
    review = minimal_review()
    path = tmp_path / "review.json"
    path.write_text(json.dumps(review))
    args = SimpleNamespace(stage="classification-review", classification_review=path)
    published = job.execute_stage(args)
    assert job.execute_stage(args) == published
    store = ArtifactStore(config.EDNA_ARTIFACT_URI)
    store.publish("raw", "b" * 64, {"manifest.json": b"{}"}, metadata={"snapshot_id": "a" * 64})
    output = tmp_path / "synthetic-normalized"
    output.mkdir()
    (output / "normalization_manifest.json").write_text("{}")

    def normalize(identity, **kwargs):
        assert identity == "a" * 64
        assert kwargs["classification_review"] == review
        return {"normalization_id": "c" * 64, "bundle_path": str(output)}

    monkeypatch.setattr(normalizer, "normalize_anemone_snapshot", normalize)
    result = job.execute_stage(SimpleNamespace(stage="normalize", artifact_id="b" * 64,
        classification_review_artifact_id=published["artifact_id"]))
    _, receipt = job.restore_normalized(store, result["artifact_id"])
    assert receipt["classification_review_sha256"] == published["artifact_id"]
    # Published decisions cannot be replaced by editing the operator's file.
    review["decisions"][0]["reviewer"] = "Changed locally"
    path.write_text(json.dumps(review))
    assert json.loads(store.read("classification-reviews", published["artifact_id"])[1]["review.json"])["decisions"][0]["reviewer"] == "Fixture reviewer"
