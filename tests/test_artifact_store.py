from concurrent.futures import ThreadPoolExecutor
import json

import pytest

import config
from ingestion.artifact_store import ArtifactStore, BoundedLocalStore, tree_files
from ingestion.provenance_snapshot import SnapshotConflict, SnapshotNotFound
from ingestion.edna_analysis_bundle import (
    publish_analysis,
    load_analysis,
    provenance_descriptors,
)
from preprocessing.edna_analysis import build_analysis
from tests.test_edna_analysis import fixture


def test_store_replay_conflict_and_changed_generation(tmp_path):
    store = ArtifactStore(store=BoundedLocalStore(tmp_path))
    identity = "a" * 64
    first = store.publish("raw", identity, {"sample/file.tsv": b"one"})
    assert store.publish("raw", identity, {"sample/file.tsv": b"one"}) == first
    assert store.read("raw", identity)[1] == {"sample/file.tsv": b"one"}
    with pytest.raises(ValueError, match="conflict|limit"):
        store.publish("raw", identity, {"sample/file.tsv": b"other"})
    key = "raw/objects/" + identity + "/sample/file.tsv"
    existing = store.store.read(key)
    store.store.replace(key, b"one", expected_generation=existing.generation)
    with pytest.raises(ValueError, match="integrity"):
        store.read("raw", identity)


def test_interrupted_upload_is_not_registered_and_can_resume(tmp_path, monkeypatch):
    store = ArtifactStore(store=BoundedLocalStore(tmp_path))
    original = store.store.create

    def fail(key, data):
        if key.endswith("b.json"):
            raise OSError("interrupted")
        return original(key, data)

    monkeypatch.setattr(store.store, "create", fail)
    with pytest.raises(OSError):
        store.publish("raw", "a" * 64, {"a.json": b"1", "b.json": b"2"})
    with pytest.raises(SnapshotNotFound):
        store.read("raw", "a" * 64)
    monkeypatch.setattr(store.store, "create", original)
    store.publish("raw", "a" * 64, {"a.json": b"1", "b.json": b"2"})
    assert len(store.read("raw", "a" * 64)[1]) == 2


def test_concurrent_index_updates_and_stale_pointer(tmp_path):
    store = ArtifactStore(store=BoundedLocalStore(tmp_path))
    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = [
            executor.submit(store.publish, "analysis", c * 64, {"a.json": c.encode()})
            for c in "ab"
        ]
        for outcome in outcomes:
            outcome.result()
    assert len(store.entries("analysis")) == 2
    generation = store.replace_pointer(
        "retrieval/current.json", {"status": "pending"}, 0
    )
    with pytest.raises(SnapshotConflict):
        store.replace_pointer("retrieval/current.json", {"status": "ready"}, 0)
    assert store.pointer("retrieval/current.json")[1] == generation


def test_limits_keys_and_tampered_registration(tmp_path):
    store = ArtifactStore(store=BoundedLocalStore(tmp_path / "objects"))
    for key in ("../escape", "/absolute", "a//b", "a/./b"):
        with pytest.raises(ValueError):
            store.publish("raw", "a" * 64, {key: b"bad"})
    store.publish("analysis", "a" * 64, {"one.json": b"123"})
    with pytest.raises(ValueError, match="limit"):
        store.read("analysis", "a" * 64, max_bytes=1)
    receipt_path = tmp_path / "objects" / "analysis" / "registry" / ("a" * 64 + ".json")
    receipt = json.loads(receipt_path.read_bytes())
    receipt["files"] = {}
    receipt_path.write_text(json.dumps(receipt))
    with pytest.raises(ValueError, match="integrity"):
        store.read("analysis", "a" * 64)
    (tmp_path / "link").symlink_to(receipt_path)
    with pytest.raises(ValueError, match="Symlink"):
        tree_files(tmp_path)


def test_analysis_object_store_read_without_staging_directory(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "EDNA_ARTIFACT_URI", (tmp_path / "objects").as_uri())
    monkeypatch.setattr(config, "EDNA_CACHE_DIR", tmp_path / "writer")
    recipe, source = fixture()
    first = build_analysis(recipe, source)
    publish_analysis(first)
    source["edna_detection"][0]["read_count"] += 1
    publish_analysis(build_analysis(recipe, source))
    monkeypatch.setattr(config, "EDNA_CACHE_DIR", tmp_path / "fresh-reader")
    assert load_analysis(first["analysis_id"])["tables"] == first["tables"]
    assert len(provenance_descriptors()) == 2
    assert not (tmp_path / "fresh-reader").exists()


def test_remote_retrieval_pending_ready_and_fresh_reader(tmp_path, monkeypatch):
    from retrieval.edna_materializer import _write_artifacts, _document_frame
    from retrieval.edna_document_builder import build_edna_documents
    from tests.test_edna_document_builder import _frames
    from retrieval.edna_publication import (
        set_pending,
        set_ready,
        current_manifest,
        retrieval_path,
    )

    monkeypatch.setattr(config, "EDNA_ARTIFACT_URI", (tmp_path / "objects").as_uri())
    monkeypatch.setattr(config, "EDNA_CACHE_DIR", tmp_path / "writer")
    docs = build_edna_documents(*_frames())
    set_pending()
    artifacts = _write_artifacts(docs, _document_frame(docs), publish=False)
    with pytest.raises(ValueError, match="incomplete"):
        current_manifest()
    set_ready(artifacts["manifest"])
    monkeypatch.setattr(config, "EDNA_CACHE_DIR", tmp_path / "reader")
    assert retrieval_path("jsonl").is_file()
    set_pending()
    with pytest.raises(ValueError, match="incomplete"):
        retrieval_path("jsonl")
    set_ready(artifacts["manifest"])


def test_gcs_transport_uses_preconditions_and_bounded_downloads():
    from google.api_core.exceptions import NotFound, PreconditionFailed
    from ingestion.artifact_store import BoundedGcsStore

    class Blob:
        def __init__(self):
            self.data, self.generation, self.size = None, 0, None
            self.reads = 0
            self.preconditions = []

        def reload(self):
            if self.data is None:
                raise NotFound("missing")

        def upload_from_string(self, data, *, content_type, if_generation_match):
            self.preconditions.append(if_generation_match)
            if self.generation != if_generation_match:
                raise PreconditionFailed("conflict")
            self.data, self.size = data, len(data)
            self.generation += 1

        def download_as_bytes(self, *, if_generation_match):
            assert if_generation_match == self.generation
            self.reads += 1
            return self.data

    class Bucket:
        def __init__(self):
            self.blobs = {}

        def blob(self, name):
            return self.blobs.setdefault(name, Blob())

    class Client:
        def __init__(self):
            self.value = Bucket()

        def bucket(self, _):
            return self.value

    client = Client()
    store = ArtifactStore(
        store=BoundedGcsStore(bucket="test", prefix="edna", client=client)
    )
    receipt = store.publish("raw", "a" * 64, {"sample.tsv": b"fixture"})
    assert store.publish("raw", "a" * 64, {"sample.tsv": b"fixture"}) == receipt
    assert store.read("raw", "a" * 64)[1] == {"sample.tsv": b"fixture"}
    obj = client.value.blobs["edna/raw/objects/" + "a" * 64 + "/sample.tsv"]
    assert obj.preconditions == [0, 0]
    count = obj.reads
    obj.size = 999999
    with pytest.raises(ValueError, match="limit"):
        store.read("raw", "a" * 64)
    assert obj.reads == count


def test_retrieval_cache_limit_is_explicit(tmp_path, monkeypatch):
    import retrieval.edna_publication as publication
    from retrieval.edna_materializer import _write_artifacts, _document_frame
    from retrieval.edna_document_builder import build_edna_documents
    from tests.test_edna_document_builder import _frames
    monkeypatch.setattr(config, 'EDNA_ARTIFACT_URI', (tmp_path/'objects').as_uri())
    monkeypatch.setattr(config, 'EDNA_CACHE_DIR', tmp_path/'writer')
    docs = build_edna_documents(*_frames())
    _write_artifacts(docs, _document_frame(docs))
    monkeypatch.setattr(config, 'EDNA_CACHE_DIR', tmp_path/'reader')
    monkeypatch.setattr(publication, 'MAX_CACHE_BYTES', 1)
    with pytest.raises(ValueError, match='cache limit'):
        publication.current_manifest()
