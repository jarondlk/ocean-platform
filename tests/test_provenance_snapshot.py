import json
import sys

import pytest

from ingestion.provenance_snapshot import (
    GcsSnapshotStore,
    LATEST_POINTER_NAME,
    LocalSnapshotStore,
    SnapshotConflict,
    SnapshotError,
    SnapshotPointer,
    StoredObject,
    canonical_json_bytes,
    prepare_snapshot,
    publish_snapshot,
    sha256_bytes,
    snapshot_store_from_uri,
)


def _manifest():
    return {
        "schema_version": 1,
        "generated_at": "2026-08-24T00:00:00+00:00",
        "project_root": "/repo",
        "summary": {
            "documents": 1,
            "embedding_model": "gemini-embedding-001",
            "embedding_dim": 768,
        },
        "source_files": [{"id": "raw:ctd", "sha256": "a" * 64}],
        "artifacts": [
            {
                "id": "serving:retrieval_parquet",
                "sha256": "b" * 64,
                "schema_hash": "c" * 64,
            }
        ],
        "documents": [
            {
                "doc_id": "ctd_doc_1",
                "content_hash": "d" * 64,
                "metadata_hash": "e" * 64,
            }
        ],
        "embeddings": [
            {
                "doc_id": "ctd_doc_1",
                "embedding_status": "embedded",
                "embedding_model": "gemini-embedding-001",
                "embedding_dim": 768,
            }
        ],
        "limitations": ["test fixture"],
    }


def test_prepare_snapshot_is_deterministic_for_fixed_publication_time():
    first = prepare_snapshot(
        _manifest(),
        manifest_id="phase7-test",
        pipeline_run_id="pipeline-1",
        published_at="2026-08-24T00:01:00+00:00",
    )
    second = prepare_snapshot(
        _manifest(),
        manifest_id="phase7-test",
        pipeline_run_id="pipeline-1",
        published_at="2026-08-24T00:01:00+00:00",
    )

    assert first.schema_version == 2
    assert first.corpus_fingerprint == second.corpus_fingerprint
    assert canonical_json_bytes(first.model_dump()) == canonical_json_bytes(second.model_dump())


def test_prepare_snapshot_rejects_missing_and_duplicate_document_ids():
    missing = _manifest()
    del missing["artifacts"]
    with pytest.raises(SnapshotError, match="missing required fields: artifacts"):
        prepare_snapshot(missing, manifest_id="missing")

    duplicate = _manifest()
    duplicate["documents"].append(dict(duplicate["documents"][0]))
    with pytest.raises(SnapshotError, match="doc_id values must be unique"):
        prepare_snapshot(duplicate, manifest_id="duplicate")


def test_prepare_snapshot_rejects_unsafe_manifest_id():
    with pytest.raises(SnapshotError, match="manifest_id"):
        prepare_snapshot(_manifest(), manifest_id="../escape")


def test_edna_publication_requires_complete_source_and_row_provenance():
    manifest = _manifest()
    snapshot_id, file_id = "a" * 64, "b" * 64
    manifest["source_files"] = [{
        "id": f"raw:anemone:{file_id}", "sha256": "c" * 64,
        "source_snapshot_id": snapshot_id,
        "source_url": "https://db.anemone.bio/dist/fixture/file.tsv.xz",
    }]
    manifest["artifacts"] = [{
        "id": "normalized:anemone:fixture", "sha256": "d" * 64,
        "source_snapshot_id": snapshot_id, "exists": True,
    }]
    manifest["documents"] = [{
        "doc_id": "edna_fixture", "source_type": "edna_metabarcoding",
        "content_hash": "e" * 64, "metadata_hash": "f" * 64,
        "source_file_ids": [f"raw:anemone:{file_id}"],
        "source_artifact_ids": ["normalized:anemone:fixture"],
        "metadata": {
            "edna_retrieval_document_version": 1,
            "source_snapshot_ids": [snapshot_id],
            "detection_set_sha256": "0" * 64,
            "canonical_records": [{
                "entity_type": kind, "entity_id": kind,
                "source_file_id": file_id, "source_snapshot_id": snapshot_id,
                "source_row_locator": [2], "source_row_hash": "1" * 64,
            } for kind in ("sample", "assay", "detection")],
        },
    }]
    assert prepare_snapshot(manifest, manifest_id="edna-complete").documents[0]["metadata"]
    for path in ("file", "hash", "artifact", "locator"):
        changed = json.loads(json.dumps(manifest))
        if path == "file":
            changed["source_files"] = []
        elif path == "hash":
            changed["source_files"][0]["sha256"] = None
        elif path == "artifact":
            changed["artifacts"] = []
        else:
            changed["documents"][0]["metadata"]["canonical_records"][0]["source_row_locator"] = []
        with pytest.raises(SnapshotError, match="incomplete eDNA provenance"):
            prepare_snapshot(changed, manifest_id="edna-incomplete")


def test_publication_requires_known_embedding_treatment_for_every_document():
    missing = _manifest()
    missing["embeddings"] = []
    with pytest.raises(SnapshotError, match="exactly one embedding treatment"):
        prepare_snapshot(
            missing,
            manifest_id="missing-embeddings",
            require_embedding_capture=True,
        )

    unknown = _manifest()
    unknown["embeddings"][0]["embedding_status"] = "unknown"
    with pytest.raises(SnapshotError, match="unknown embedding treatment"):
        prepare_snapshot(
            unknown,
            manifest_id="unknown-embeddings",
            require_embedding_capture=True,
        )


def test_local_publish_writes_verified_immutable_object_then_pointer(tmp_path):
    store = LocalSnapshotStore(tmp_path)
    snapshot = prepare_snapshot(
        _manifest(),
        manifest_id="phase7-local",
        pipeline_run_id="pipeline-1",
        published_at="2026-08-24T00:01:00+00:00",
    )

    result = publish_snapshot(snapshot, store=store)

    stored_manifest = store.read(result.pointer.object_path)
    stored_pointer = store.read(LATEST_POINTER_NAME)
    pointer = SnapshotPointer.model_validate_json(stored_pointer.data)
    assert pointer.manifest_id == "phase7-local"
    assert pointer.document_count == 1
    assert pointer.embedded_document_count == 1
    assert pointer.sha256 == sha256_bytes(stored_manifest.data)
    assert pointer.size_bytes == len(stored_manifest.data)

    with pytest.raises(SnapshotConflict, match="already exists"):
        publish_snapshot(snapshot, store=store)


def test_local_pointer_compare_and_swap_rejects_stale_generation(tmp_path):
    store = LocalSnapshotStore(tmp_path)
    first_generation = store.replace(LATEST_POINTER_NAME, b"first", expected_generation=0)
    store.replace(LATEST_POINTER_NAME, b"second", expected_generation=first_generation)

    with pytest.raises(SnapshotConflict, match="generation changed"):
        store.replace(LATEST_POINTER_NAME, b"stale", expected_generation=first_generation)

    assert store.read(LATEST_POINTER_NAME).data == b"second"


def test_publisher_does_not_advance_pointer_when_verification_fails():
    class CorruptingStore:
        def __init__(self):
            self.values = {}

        def create(self, key, data):
            self.values[key] = StoredObject(data=data + b"corrupt", generation=1)
            return 1

        def read(self, key):
            try:
                return self.values[key]
            except KeyError as exc:
                from ingestion.provenance_snapshot import SnapshotNotFound

                raise SnapshotNotFound(key) from exc

        def replace(self, key, data, *, expected_generation):
            raise AssertionError("pointer must not advance after failed verification")

    snapshot = prepare_snapshot(_manifest(), manifest_id="corrupt-test")
    with pytest.raises(SnapshotError, match="stored snapshot bytes differ"):
        publish_snapshot(snapshot, store=CorruptingStore())


def test_snapshot_store_uri_rejects_unsupported_scheme(tmp_path):
    store = snapshot_store_from_uri(f"file://{tmp_path}")
    assert isinstance(store, LocalSnapshotStore)

    with pytest.raises(SnapshotError, match="unsupported"):
        snapshot_store_from_uri("https://example.com/provenance")


def test_gcs_store_uses_prefix_and_generation_preconditions():
    class FakeBlob:
        def __init__(self, name):
            self.name = name
            self.data = None
            self.generation = None
            self.upload_preconditions = []

        def upload_from_string(self, data, *, content_type, if_generation_match):
            assert content_type == "application/json"
            self.upload_preconditions.append(if_generation_match)
            self.data = data
            self.generation = int(self.generation or 0) + 1

        def download_as_bytes(self, *, if_generation_match):
            assert if_generation_match == self.generation
            return self.data

        def reload(self):
            return None

    class FakeBucket:
        def __init__(self):
            self.blobs = {}

        def blob(self, name):
            return self.blobs.setdefault(name, FakeBlob(name))

    class FakeClient:
        def __init__(self):
            self.selected_bucket = None
            self.value = FakeBucket()

        def bucket(self, name):
            self.selected_bucket = name
            return self.value

    client = FakeClient()
    store = GcsSnapshotStore(bucket="test-bucket", prefix="provenance", client=client)

    assert store.create("manifests/one.json", b"one") == 1
    assert store.replace("latest.json", b"pointer", expected_generation=0) == 1
    assert store.read("manifests/one.json") == StoredObject(data=b"one", generation=1)
    assert client.selected_bucket == "test-bucket"
    assert sorted(client.value.blobs) == [
        "provenance/latest.json",
        "provenance/manifests/one.json",
    ]
    assert client.value.blobs["provenance/manifests/one.json"].upload_preconditions == [0]
    assert client.value.blobs["provenance/latest.json"].upload_preconditions == [0]


def test_pointer_payload_is_canonical_json(tmp_path):
    store = LocalSnapshotStore(tmp_path)
    snapshot = prepare_snapshot(
        _manifest(),
        manifest_id="canonical-test",
        published_at="2026-08-24T00:01:00+00:00",
    )
    result = publish_snapshot(snapshot, store=store)
    pointer_data = store.read(LATEST_POINTER_NAME).data

    assert pointer_data == canonical_json_bytes(json.loads(pointer_data))
    assert result.pointer_generation > 0


def test_snapshot_cli_builds_all_documents_for_validation(monkeypatch, capsys):
    import scripts.build_provenance_manifest as cli

    captured = {}

    def fake_manifest(*, limit_documents, include_embeddings):
        captured["limit_documents"] = limit_documents
        captured["include_embeddings"] = include_embeddings
        return _manifest()

    monkeypatch.setattr(cli, "build_provenance_manifest", fake_manifest)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "build_provenance_manifest.py",
            "--validate-only",
            "--run-id",
            "cli-validation",
        ],
    )

    assert cli.main() == 0
    payload = json.loads(capsys.readouterr().out)
    assert captured == {"limit_documents": None, "include_embeddings": True}
    assert payload["mode"] == "validate"
    assert payload["documents"] == 1


def test_snapshot_cli_publishes_to_explicit_local_store(tmp_path, monkeypatch, capsys):
    import scripts.build_provenance_manifest as cli

    monkeypatch.setattr(cli, "build_provenance_manifest", lambda **_: _manifest())
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "build_provenance_manifest.py",
            "--publish",
            "--run-id",
            "cli-publication",
            "--pipeline-run-id",
            "pipeline-1",
            "--snapshot-uri",
            f"file://{tmp_path}",
        ],
    )

    assert cli.main() == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["mode"] == "publish"
    assert payload["object_path"] == "manifests/cli-publication.json"
    assert (tmp_path / "latest.json").exists()
