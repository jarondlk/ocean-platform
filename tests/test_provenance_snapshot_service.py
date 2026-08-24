import json
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest

from api.provenance_snapshot_service import ProvenanceSnapshotService
from ingestion.provenance_snapshot import (
    LATEST_POINTER_NAME,
    LocalSnapshotStore,
    SnapshotError,
    prepare_snapshot,
    publish_snapshot,
)


def _manifest():
    return {
        "schema_version": 1,
        "generated_at": "2026-08-24T00:00:00+00:00",
        "project_root": "/repo",
        "summary": {
            "documents": 2,
            "artifacts": 1,
            "source_files": 1,
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
                "doc_id": f"ctd_doc_{index}",
                "content_hash": str(index) * 64,
                "metadata_hash": str(index + 2) * 64,
                "source_file_ids": ["raw:ctd"],
                "source_artifact_ids": ["serving:retrieval_parquet"],
            }
            for index in (1, 2)
        ],
        "embeddings": [
            {
                "doc_id": f"ctd_doc_{index}",
                "embedding_status": "embedded",
                "embedding_model": "gemini-embedding-001",
                "embedding_dim": 768,
            }
            for index in (1, 2)
        ],
        "limitations": ["test fixture"],
    }


def _published_store(tmp_path):
    store = LocalSnapshotStore(tmp_path)
    snapshot = prepare_snapshot(
        _manifest(),
        manifest_id="service-test",
        pipeline_run_id="pipeline-1",
        published_at="2026-08-24T00:01:00+00:00",
    )
    publish_snapshot(snapshot, store=store)
    return store


def test_manifest_payload_is_bounded_without_rebuilding(tmp_path):
    service = ProvenanceSnapshotService(
        store=_published_store(tmp_path),
        ttl_seconds=60,
    )

    payload = service.manifest_payload(
        limit_documents=1,
        include_embeddings=False,
    )

    assert payload["schema_version"] == 2
    assert payload["snapshot"]["manifest_id"] == "service-test"
    assert payload["summary"]["documents"] == 1
    assert payload["summary"]["total_documents"] == 2
    assert [row["doc_id"] for row in payload["documents"]] == ["ctd_doc_1"]
    assert payload["embeddings"] == []


def test_trace_payload_uses_prebuilt_indexes(tmp_path):
    service = ProvenanceSnapshotService(
        store=_published_store(tmp_path),
        ttl_seconds=60,
    )

    found = service.trace_payload("ctd_doc_2")
    missing = service.trace_payload("missing")

    assert found["found"] is True
    assert found["trace"]["document"]["doc_id"] == "ctd_doc_2"
    assert found["trace"]["artifacts"][0]["id"] == "serving:retrieval_parquet"
    assert found["trace"]["source_files"][0]["id"] == "raw:ctd"
    assert found["trace"]["embedding"]["embedding_status"] == "embedded"
    assert missing["found"] is False
    assert missing["snapshot"]["manifest_id"] == "service-test"


def test_concurrent_cache_miss_reads_pointer_and_manifest_once(tmp_path):
    delegate = _published_store(tmp_path)

    class CountingStore:
        def __init__(self):
            self.read_count = 0
            self.lock = threading.Lock()

        def read(self, key):
            with self.lock:
                self.read_count += 1
            return delegate.read(key)

    store = CountingStore()
    service = ProvenanceSnapshotService(store=store, ttl_seconds=60)

    with ThreadPoolExecutor(max_workers=12) as executor:
        results = list(executor.map(lambda _: service.trace_payload("ctd_doc_1"), range(12)))

    assert all(result["found"] for result in results)
    assert store.read_count == 2


def test_cache_reloads_after_ttl(tmp_path):
    delegate = _published_store(tmp_path)

    class CountingStore:
        def __init__(self):
            self.read_count = 0

        def read(self, key):
            self.read_count += 1
            return delegate.read(key)

    times = iter([0.0, 0.0, 1.0, 61.0, 61.0])
    store = CountingStore()
    service = ProvenanceSnapshotService(
        store=store,
        ttl_seconds=60,
        clock=lambda: next(times),
    )

    service.load()
    service.load()
    service.load()

    assert store.read_count == 4


def test_loader_rejects_snapshot_digest_mismatch(tmp_path):
    store = _published_store(tmp_path)
    pointer_path = tmp_path / LATEST_POINTER_NAME
    pointer = json.loads(pointer_path.read_text())
    pointer["sha256"] = "0" * 64
    current_generation = store.read(LATEST_POINTER_NAME).generation
    store.replace(
        LATEST_POINTER_NAME,
        json.dumps(pointer).encode(),
        expected_generation=current_generation,
    )
    service = ProvenanceSnapshotService(store=store, ttl_seconds=60)

    with pytest.raises(SnapshotError, match="digest"):
        service.load()
