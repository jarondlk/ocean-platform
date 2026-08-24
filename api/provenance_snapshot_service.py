"""Fast, verified reads of precomputed provenance snapshots."""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import lru_cache
from typing import Any, Callable, Dict, Optional

from pydantic import ValidationError

import config
from ingestion.provenance_snapshot import (
    LATEST_POINTER_NAME,
    ProvenanceSnapshot,
    SnapshotError,
    SnapshotPointer,
    SnapshotStore,
    sha256_bytes,
    snapshot_store_from_uri,
)


@dataclass(frozen=True)
class LoadedSnapshot:
    snapshot: ProvenanceSnapshot
    pointer: SnapshotPointer
    loaded_at: float
    documents_by_id: Dict[str, Dict[str, Any]]
    embeddings_by_id: Dict[str, Dict[str, Any]]
    artifacts_by_id: Dict[str, Dict[str, Any]]
    source_files_by_id: Dict[str, Dict[str, Any]]


def _indexed_rows(rows: list[Dict[str, Any]], key: str) -> Dict[str, Dict[str, Any]]:
    index: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        value = str(row.get(key) or "")
        if not value:
            raise SnapshotError(f"snapshot row is missing {key}")
        if value in index:
            raise SnapshotError(f"snapshot contains duplicate {key}: {value}")
        index[value] = row
    return index


def _age_seconds(value: str) -> int:
    try:
        generated = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if generated.tzinfo is None:
            generated = generated.replace(tzinfo=timezone.utc)
        return max(0, int((datetime.now(timezone.utc) - generated).total_seconds()))
    except (TypeError, ValueError):
        return 0


class ProvenanceSnapshotService:
    """Load once per TTL and share one verified snapshot across request threads."""

    def __init__(
        self,
        *,
        store: SnapshotStore,
        ttl_seconds: int = 60,
        clock: Callable[[], float] = time.monotonic,
    ):
        if ttl_seconds < 1:
            raise ValueError("ttl_seconds must be positive")
        self.store = store
        self.ttl_seconds = ttl_seconds
        self.clock = clock
        self._lock = threading.Lock()
        self._cached: Optional[LoadedSnapshot] = None

    def load(self) -> LoadedSnapshot:
        now = self.clock()
        cached = self._cached
        if cached is not None and now - cached.loaded_at < self.ttl_seconds:
            return cached

        with self._lock:
            now = self.clock()
            cached = self._cached
            if cached is not None and now - cached.loaded_at < self.ttl_seconds:
                return cached
            loaded = self._load_verified(now)
            self._cached = loaded
            return loaded

    def _load_verified(self, loaded_at: float) -> LoadedSnapshot:
        pointer_object = self.store.read(LATEST_POINTER_NAME)
        try:
            pointer = SnapshotPointer.model_validate_json(pointer_object.data)
        except ValidationError as exc:
            raise SnapshotError(f"invalid latest provenance pointer: {exc}") from exc
        expected_path = f"manifests/{pointer.manifest_id}.json"
        if pointer.object_path != expected_path:
            raise SnapshotError("latest provenance pointer has an unexpected object path")

        manifest_object = self.store.read(pointer.object_path)
        if len(manifest_object.data) != pointer.size_bytes:
            raise SnapshotError("provenance snapshot size does not match latest pointer")
        if sha256_bytes(manifest_object.data) != pointer.sha256:
            raise SnapshotError("provenance snapshot digest does not match latest pointer")
        try:
            snapshot = ProvenanceSnapshot.model_validate_json(manifest_object.data)
        except ValidationError as exc:
            raise SnapshotError(f"invalid provenance snapshot: {exc}") from exc

        if snapshot.manifest_id != pointer.manifest_id:
            raise SnapshotError("snapshot manifest_id does not match latest pointer")
        if snapshot.generated_at != pointer.generated_at:
            raise SnapshotError("snapshot generation time does not match latest pointer")
        if snapshot.published_at != pointer.published_at:
            raise SnapshotError("snapshot publication time does not match latest pointer")
        if snapshot.pipeline_run_id != pointer.pipeline_run_id:
            raise SnapshotError("snapshot pipeline run does not match latest pointer")
        if snapshot.corpus_fingerprint != pointer.corpus_fingerprint:
            raise SnapshotError("snapshot corpus fingerprint does not match latest pointer")
        if len(snapshot.documents) != pointer.document_count:
            raise SnapshotError("snapshot document count does not match latest pointer")

        documents = _indexed_rows(snapshot.documents, "doc_id")
        embeddings = _indexed_rows(snapshot.embeddings, "doc_id")
        artifacts = _indexed_rows(snapshot.artifacts, "id")
        source_files = _indexed_rows(snapshot.source_files, "id")
        embedded_count = sum(
            1 for row in snapshot.embeddings if row.get("embedding_status") == "embedded"
        )
        if embedded_count != pointer.embedded_document_count:
            raise SnapshotError("snapshot embedding count does not match latest pointer")
        summary_model = snapshot.summary.get("embedding_model")
        normalized_model = str(summary_model) if summary_model else None
        if normalized_model != pointer.embedding_model:
            raise SnapshotError("snapshot embedding model does not match latest pointer")
        summary_dim = snapshot.summary.get("embedding_dim")
        try:
            normalized_dim = int(summary_dim) if summary_dim is not None else None
        except (TypeError, ValueError) as exc:
            raise SnapshotError("snapshot embedding dimension is invalid") from exc
        if normalized_dim != pointer.embedding_dim:
            raise SnapshotError("snapshot embedding dimension does not match latest pointer")

        return LoadedSnapshot(
            snapshot=snapshot,
            pointer=pointer,
            loaded_at=loaded_at,
            documents_by_id=documents,
            embeddings_by_id=embeddings,
            artifacts_by_id=artifacts,
            source_files_by_id=source_files,
        )

    @staticmethod
    def _metadata(loaded: LoadedSnapshot) -> Dict[str, Any]:
        pointer = loaded.pointer
        return {
            "manifest_id": pointer.manifest_id,
            "pipeline_run_id": pointer.pipeline_run_id,
            "generated_at": pointer.generated_at,
            "published_at": pointer.published_at,
            "age_seconds": _age_seconds(pointer.generated_at),
            "sha256": pointer.sha256,
            "size_bytes": pointer.size_bytes,
            "document_count": pointer.document_count,
            "embedded_document_count": pointer.embedded_document_count,
            "embedding_model": pointer.embedding_model,
            "embedding_dim": pointer.embedding_dim,
        }

    def manifest_payload(
        self,
        *,
        limit_documents: int,
        include_embeddings: bool,
    ) -> Dict[str, Any]:
        loaded = self.load()
        snapshot = loaded.snapshot
        documents = snapshot.documents[:limit_documents]
        document_ids = {str(row["doc_id"]) for row in documents}
        embeddings = (
            [
                row
                for row in snapshot.embeddings
                if str(row.get("doc_id") or "") in document_ids
            ]
            if include_embeddings
            else []
        )
        summary = dict(snapshot.summary)
        summary.update(
            {
                "documents": len(documents),
                "document_limit": limit_documents,
                "total_documents": len(snapshot.documents),
                "embedded_documents_in_manifest": sum(
                    1 for row in embeddings if row.get("embedding_status") == "embedded"
                ),
            }
        )
        return {
            "schema_version": snapshot.schema_version,
            "generated_at": snapshot.generated_at,
            "project_root": snapshot.project_root,
            "snapshot": self._metadata(loaded),
            "summary": summary,
            "source_files": snapshot.source_files,
            "artifacts": snapshot.artifacts,
            "documents": documents,
            "embeddings": embeddings,
            "limitations": snapshot.limitations,
        }

    def trace_payload(self, doc_id: str) -> Dict[str, Any]:
        loaded = self.load()
        document = loaded.documents_by_id.get(doc_id)
        if document is None:
            return {
                "doc_id": doc_id,
                "found": False,
                "snapshot": self._metadata(loaded),
                "trace": {},
            }
        artifact_ids = set(document.get("source_artifact_ids") or [])
        source_file_ids = set(document.get("source_file_ids") or [])
        embedding = loaded.embeddings_by_id.get(doc_id)
        artifacts = [
            loaded.artifacts_by_id[value]
            for value in sorted(artifact_ids)
            if value in loaded.artifacts_by_id
        ]
        source_files = [
            loaded.source_files_by_id[value]
            for value in sorted(source_file_ids)
            if value in loaded.source_files_by_id
        ]
        return {
            "doc_id": doc_id,
            "found": True,
            "snapshot": self._metadata(loaded),
            "trace": {
                "document": document,
                "embedding": embedding,
                "artifacts": artifacts,
                "source_files": source_files,
                "trace_path": [
                    {"level": "citation", "key": doc_id},
                    {"level": "retrieval_document", "key": document.get("content_hash")},
                    {"level": "derived_artifacts", "keys": sorted(artifact_ids)},
                    {"level": "source_files", "keys": sorted(source_file_ids)},
                    {
                        "level": "embedding_treatment",
                        "key": embedding.get("embedding_model") if embedding else None,
                    },
                ],
            },
        }


@lru_cache(maxsize=1)
def get_provenance_snapshot_service() -> ProvenanceSnapshotService:
    return ProvenanceSnapshotService(
        store=snapshot_store_from_uri(),
        ttl_seconds=config.PROVENANCE_CACHE_TTL_SECONDS,
    )
