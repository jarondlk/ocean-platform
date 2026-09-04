"""Validated, immutable publication of precomputed provenance snapshots.

Expensive lineage construction belongs in an operator-run pipeline. This
module takes the completed manifest, validates its durable envelope, writes an
immutable object, verifies the stored bytes, and only then advances a small
``latest.json`` pointer. Serving code can consequently read one known object
without scanning the scientific corpus.
"""
from __future__ import annotations

import fcntl
import hashlib
import json
import os
import re
import tempfile
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Literal, Optional, Protocol
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field, ValidationError

import config


SNAPSHOT_SCHEMA_VERSION = 2
LATEST_POINTER_NAME = "latest.json"
MANIFEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")


class SnapshotError(RuntimeError):
    """Base exception for snapshot validation and storage failures."""


class SnapshotConflict(SnapshotError):
    """Raised when an immutable object or pointer generation changed."""


class SnapshotNotFound(SnapshotError):
    """Raised when a requested snapshot object does not exist."""


class ProvenanceSnapshot(BaseModel):
    """Durable schema for a complete, precomputed provenance manifest."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[2]
    manifest_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
    pipeline_run_id: Optional[str] = None
    generated_at: str
    published_at: str
    project_root: str
    corpus_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    summary: Dict[str, Any] = Field(default_factory=dict)
    source_files: list[Dict[str, Any]] = Field(default_factory=list)
    artifacts: list[Dict[str, Any]] = Field(default_factory=list)
    documents: list[Dict[str, Any]] = Field(default_factory=list)
    embeddings: list[Dict[str, Any]] = Field(default_factory=list)
    edna_analyses: list[Dict[str, Any]] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)


class SnapshotPointer(BaseModel):
    """Small mutable pointer to one immutable manifest object."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[2]
    manifest_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
    object_path: str
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    size_bytes: int = Field(gt=0)
    generated_at: str
    published_at: str
    pipeline_run_id: Optional[str] = None
    corpus_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    document_count: int = Field(ge=0)
    embedded_document_count: int = Field(ge=0)
    embedding_model: Optional[str] = None
    embedding_dim: Optional[int] = Field(default=None, gt=0)


@dataclass(frozen=True)
class StoredObject:
    data: bytes
    generation: int


@dataclass(frozen=True)
class PublishedSnapshot:
    pointer: SnapshotPointer
    pointer_generation: int


class SnapshotStore(Protocol):
    def read(self, key: str) -> StoredObject:
        """Read an object and its concurrency generation."""

    def create(self, key: str, data: bytes) -> int:
        """Create an immutable object and fail if it already exists."""

    def replace(self, key: str, data: bytes, *, expected_generation: int) -> int:
        """Replace an object only when its generation matches."""


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def canonical_json_bytes(value: Any) -> bytes:
    """Return deterministic UTF-8 JSON suitable for integrity hashing."""
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _optional_positive_int(name: str, value: Any) -> Optional[int]:
    if value is None:
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise SnapshotError(f"{name} must be a positive integer") from exc
    if parsed < 1:
        raise SnapshotError(f"{name} must be a positive integer")
    return parsed


def _validated_manifest_id(value: str) -> str:
    value = value.strip()
    if not MANIFEST_ID_PATTERN.fullmatch(value):
        raise SnapshotError(
            "manifest_id must be 1-128 characters using letters, numbers, '.', '_', or '-'"
        )
    return value


def _validated_timestamp(name: str, value: Any) -> str:
    text_value = str(value)
    try:
        parsed = datetime.fromisoformat(text_value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise SnapshotError(f"{name} must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None:
        raise SnapshotError(f"{name} must include a timezone")
    return text_value


def _corpus_fingerprint(manifest: Dict[str, Any]) -> str:
    """Fingerprint stable lineage identities without hashing response metadata."""
    document_rows = [
        {
            "doc_id": row.get("doc_id"),
            "content_hash": row.get("content_hash"),
            "metadata_hash": row.get("metadata_hash"),
        }
        for row in manifest.get("documents", [])
        if isinstance(row, dict)
    ]
    artifact_rows = [
        {
            "id": row.get("id"),
            "sha256": row.get("sha256"),
            "schema_hash": row.get("schema_hash"),
        }
        for row in manifest.get("artifacts", [])
        if isinstance(row, dict)
    ]
    artifact_rows.extend({'id': 'edna_analysis:'+row['analysis_id'], 'sha256': row['manifest_sha256'], 'schema_hash': None}
                         for row in manifest.get('edna_analyses', []))
    return sha256_bytes(
        canonical_json_bytes(
            {
                "documents": sorted(document_rows, key=lambda row: str(row.get("doc_id") or "")),
                "artifacts": sorted(artifact_rows, key=lambda row: str(row.get("id") or "")),
            }
        )
    )


def _validate_edna_provenance(snapshot: ProvenanceSnapshot) -> None:
    from ingestion.immutable_bundle import digest, validate_id
    for descriptor in snapshot.edna_analyses:
        try:
            identity = validate_id(descriptor['analysis_id'])
            manifest = descriptor['manifest']
            if manifest['id'] != identity or digest(manifest) != descriptor['manifest_sha256'] or digest(descriptor['recipe']) != manifest['recipe_sha256']:
                raise ValueError('Analysis manifest mismatch')
            if digest({'algorithm':manifest['algorithm_version'], 'recipe':descriptor['recipe'], 'input_sha256':manifest['input_sha256']}) != identity:
                raise ValueError('Analysis identity mismatch')
            from ingestion.edna_analysis_bundle import TABLES
            if not {'recipe.json', 'inputs.json', *(name+'.json' for name in TABLES)}.issubset(manifest['files']):
                raise ValueError('Analysis input/result artifacts missing')
            for sha in manifest['files'].values():
                validate_id(sha)
            if descriptor['bundle_route'] != f'/data/edna/analysis/runs/{identity}/export?format=bundle':
                raise ValueError('Invalid analysis bundle route')
        except (KeyError, ValueError, TypeError) as exc:
            raise SnapshotError('Incomplete eDNA analysis provenance') from exc
    files = {row.get("id"): row for row in snapshot.source_files}
    artifacts = {row.get("id"): row for row in snapshot.artifacts}
    sha256 = re.compile(r"^[a-f0-9]{64}$")
    for document in snapshot.documents:
        if document.get("source_type") != "edna_metabarcoding":
            continue
        prefix = f"incomplete eDNA provenance for {document['doc_id']}: "
        metadata = document.get("metadata") or {}
        snapshot_ids = set(metadata.get("source_snapshot_ids") or [])
        file_ids = document.get("source_file_ids") or []
        records = metadata.get("canonical_records") or []
        if metadata.get("edna_retrieval_document_version") != 1 or not snapshot_ids or not file_ids or len(records) < 3:
            raise SnapshotError(prefix + "missing document version, snapshots, files, or canonical records")
        if not sha256.fullmatch(str(metadata.get("detection_set_sha256") or "")):
            raise SnapshotError(prefix + "missing detection-set hash")
        for file_id in file_ids:
            source = files.get(file_id, {})
            if not sha256.fullmatch(str(source.get("sha256") or "")) or source.get("source_snapshot_id") not in snapshot_ids or not source.get("source_url"):
                raise SnapshotError(prefix + "missing source file, snapshot, URL, or SHA-256")
        for record in records:
            locator = record.get("source_row_locator")
            locators = locator if isinstance(locator, list) else [locator]
            if (
                not record.get("entity_id")
                or record.get("source_snapshot_id") not in snapshot_ids
                or f"raw:anemone:{record.get('source_file_id')}" not in file_ids
                or not sha256.fullmatch(str(record.get("source_row_hash") or ""))
                or not locators
                or any(not isinstance(value, int) or isinstance(value, bool) or value < 1 for value in locators)
            ):
                raise SnapshotError(prefix + "invalid canonical record or source-row locator")
        normalized_snapshots: set[str] = set()
        for artifact_id in document.get("source_artifact_ids") or []:
            artifact = artifacts.get(artifact_id, {})
            if not artifact.get("exists") or not sha256.fullmatch(str(artifact.get("sha256") or "")):
                raise SnapshotError(prefix + "missing normalized or retrieval artifact")
            if artifact.get("source_snapshot_id"):
                normalized_snapshots.add(artifact["source_snapshot_id"])
        if not snapshot_ids.issubset(normalized_snapshots):
            raise SnapshotError(prefix + "missing normalized snapshot artifacts")


def prepare_snapshot(
    manifest: Dict[str, Any],
    *,
    manifest_id: str,
    pipeline_run_id: Optional[str] = None,
    published_at: Optional[str] = None,
    require_embedding_capture: bool = False,
) -> ProvenanceSnapshot:
    """Upgrade and validate a generated schema-v1 manifest for publication."""
    validated_id = _validated_manifest_id(manifest_id)
    if manifest.get("schema_version") != 1:
        raise SnapshotError(
            f"generated manifest schema_version must be 1, got {manifest.get('schema_version')!r}"
        )
    required = {
        "generated_at",
        "project_root",
        "summary",
        "source_files",
        "artifacts",
        "documents",
        "embeddings",
        "limitations",
    }
    missing = sorted(required - set(manifest))
    if missing:
        raise SnapshotError(f"manifest is missing required fields: {', '.join(missing)}")

    publication_time = published_at or _utc_now_iso()
    payload = {
        "schema_version": SNAPSHOT_SCHEMA_VERSION,
        "manifest_id": validated_id,
        "pipeline_run_id": pipeline_run_id.strip() if pipeline_run_id else None,
        "generated_at": _validated_timestamp("generated_at", manifest["generated_at"]),
        "published_at": _validated_timestamp("published_at", publication_time),
        "project_root": str(manifest["project_root"]),
        "corpus_fingerprint": _corpus_fingerprint(manifest),
        "summary": manifest["summary"],
        "source_files": manifest["source_files"],
        "artifacts": manifest["artifacts"],
        "documents": manifest["documents"],
        "embeddings": manifest["embeddings"],
        "edna_analyses": manifest.get("edna_analyses", []),
        "limitations": manifest["limitations"],
    }
    try:
        snapshot = ProvenanceSnapshot.model_validate(payload)
    except ValidationError as exc:
        raise SnapshotError(f"invalid provenance snapshot: {exc}") from exc

    document_ids = [str(row.get("doc_id") or "") for row in snapshot.documents]
    if any(not doc_id for doc_id in document_ids):
        raise SnapshotError("every snapshot document must have a non-empty doc_id")
    if len(document_ids) != len(set(document_ids)):
        raise SnapshotError("snapshot document doc_id values must be unique")
    _validate_edna_provenance(snapshot)
    if require_embedding_capture:
        embedding_ids = [str(row.get("doc_id") or "") for row in snapshot.embeddings]
        if set(embedding_ids) != set(document_ids) or len(embedding_ids) != len(document_ids):
            raise SnapshotError(
                "published snapshot requires exactly one embedding treatment for every document"
            )
        unknown = [
            doc_id
            for doc_id, row in zip(embedding_ids, snapshot.embeddings)
            if row.get("embedding_status") not in {"embedded", "missing"}
        ]
        if unknown:
            raise SnapshotError(
                f"published snapshot has unknown embedding treatment for {len(unknown)} documents"
            )
    return snapshot


def build_pointer(snapshot: ProvenanceSnapshot, *, object_path: str, data: bytes) -> SnapshotPointer:
    summary = snapshot.summary
    return SnapshotPointer(
        schema_version=SNAPSHOT_SCHEMA_VERSION,
        manifest_id=snapshot.manifest_id,
        object_path=object_path,
        sha256=sha256_bytes(data),
        size_bytes=len(data),
        generated_at=snapshot.generated_at,
        published_at=snapshot.published_at,
        pipeline_run_id=snapshot.pipeline_run_id,
        corpus_fingerprint=snapshot.corpus_fingerprint,
        document_count=len(snapshot.documents),
        embedded_document_count=sum(
            1 for row in snapshot.embeddings if row.get("embedding_status") == "embedded"
        ),
        embedding_model=(str(summary.get("embedding_model")) if summary.get("embedding_model") else None),
        embedding_dim=_optional_positive_int(
            "summary.embedding_dim",
            summary.get("embedding_dim"),
        ),
    )


class LocalSnapshotStore:
    """Filesystem store used for local development and deterministic tests."""

    def __init__(self, root: Path):
        self.root = root.resolve()

    def _path(self, key: str) -> Path:
        candidate = (self.root / key).resolve()
        try:
            candidate.relative_to(self.root)
        except ValueError as exc:
            raise SnapshotError(f"snapshot key escapes store root: {key}") from exc
        return candidate

    @staticmethod
    def _advance_generation(path: Path, previous_generation: int) -> int:
        """Return a generation distinct from the replaced file's generation.

        Some container filesystems assign the same mtime to temporary files
        created in a tight loop. Explicitly advance the replacement mtime so
        compare-and-swap remains deterministic across local and CI runtimes.
        """
        candidate = max(time.time_ns(), previous_generation + 1_000_000)
        for attempt in range(4):
            requested = candidate + (attempt * 1_000_000_000)
            os.utime(path, ns=(requested, requested))
            generation = path.stat().st_mtime_ns
            if generation != previous_generation:
                return generation
        raise SnapshotError(f"could not advance local snapshot generation: {path}")

    def read(self, key: str) -> StoredObject:
        path = self._path(key)
        try:
            data = path.read_bytes()
            generation = path.stat().st_mtime_ns
        except FileNotFoundError as exc:
            raise SnapshotNotFound(f"snapshot object does not exist: {key}") from exc
        return StoredObject(data=data, generation=generation)

    def create(self, key: str, data: bytes) -> int:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path: Optional[Path] = None
        try:
            with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as handle:
                temporary_path = Path(handle.name)
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            try:
                os.link(temporary_path, path)
            except FileExistsError as exc:
                raise SnapshotConflict(f"immutable snapshot already exists: {key}") from exc
        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)
        return path.stat().st_mtime_ns

    def replace(self, key: str, data: bytes, *, expected_generation: int) -> int:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        lock_path = path.with_suffix(f"{path.suffix}.lock")
        with lock_path.open("a+b") as lock_handle:
            fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX)
            current_generation = path.stat().st_mtime_ns if path.exists() else 0
            if current_generation != expected_generation:
                raise SnapshotConflict(
                    f"pointer generation changed for {key}: expected {expected_generation}, got {current_generation}"
                )
            temporary_path: Optional[Path] = None
            try:
                with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as handle:
                    temporary_path = Path(handle.name)
                    handle.write(data)
                    handle.flush()
                    os.fsync(handle.fileno())
                os.replace(temporary_path, path)
                temporary_path = None
            finally:
                if temporary_path is not None:
                    temporary_path.unlink(missing_ok=True)
            return self._advance_generation(path, current_generation)


class GcsSnapshotStore:
    """Cloud Storage store using ADC and generation preconditions."""

    def __init__(self, *, bucket: str, prefix: str = "", client: Any = None):
        try:
            from google.cloud import storage
        except ImportError as exc:
            raise SnapshotError(
                "google-cloud-storage is required for gs:// provenance snapshots"
            ) from exc
        self.bucket = (client or storage.Client()).bucket(bucket)
        self.prefix = prefix.strip("/")

    def _name(self, key: str) -> str:
        clean_key = key.strip("/")
        if not clean_key or ".." in Path(clean_key).parts:
            raise SnapshotError(f"invalid snapshot key: {key}")
        return f"{self.prefix}/{clean_key}" if self.prefix else clean_key

    @staticmethod
    def _translate_error(exc: Exception, *, key: str) -> SnapshotError:
        try:
            from google.api_core.exceptions import NotFound, PreconditionFailed
        except ImportError:
            return SnapshotError(f"Cloud Storage operation failed for {key}: {exc}")
        if isinstance(exc, NotFound):
            return SnapshotNotFound(f"snapshot object does not exist: {key}")
        if isinstance(exc, PreconditionFailed):
            return SnapshotConflict(f"snapshot generation conflict: {key}")
        return SnapshotError(f"Cloud Storage operation failed for {key}: {exc}")

    def read(self, key: str) -> StoredObject:
        blob = self.bucket.blob(self._name(key))
        try:
            blob.reload()
            generation = int(blob.generation or 0)
            data = blob.download_as_bytes(if_generation_match=generation)
        except Exception as exc:
            raise self._translate_error(exc, key=key) from exc
        return StoredObject(data=data, generation=generation)

    def create(self, key: str, data: bytes) -> int:
        blob = self.bucket.blob(self._name(key))
        try:
            blob.upload_from_string(
                data,
                content_type="application/json",
                if_generation_match=0,
            )
        except Exception as exc:
            raise self._translate_error(exc, key=key) from exc
        return int(blob.generation or 0)

    def replace(self, key: str, data: bytes, *, expected_generation: int) -> int:
        blob = self.bucket.blob(self._name(key))
        try:
            blob.upload_from_string(
                data,
                content_type="application/json",
                if_generation_match=expected_generation,
            )
        except Exception as exc:
            raise self._translate_error(exc, key=key) from exc
        return int(blob.generation or 0)


def snapshot_store_from_uri(uri: Optional[str] = None, *, client: Any = None) -> SnapshotStore:
    selected = (uri or config.PROVENANCE_SNAPSHOT_URI).strip()
    parsed = urlparse(selected)
    if parsed.scheme == "gs":
        if not parsed.netloc:
            raise SnapshotError("gs:// snapshot URI requires a bucket name")
        return GcsSnapshotStore(
            bucket=parsed.netloc,
            prefix=parsed.path.strip("/"),
            client=client,
        )
    if parsed.scheme == "file":
        return LocalSnapshotStore(Path(parsed.path))
    if not parsed.scheme:
        return LocalSnapshotStore(Path(selected))
    raise SnapshotError(f"unsupported provenance snapshot URI scheme: {parsed.scheme}")


def publish_snapshot(
    snapshot: ProvenanceSnapshot,
    *,
    store: Optional[SnapshotStore] = None,
) -> PublishedSnapshot:
    """Publish verified immutable bytes, then advance the latest pointer."""
    selected_store = store or snapshot_store_from_uri()
    snapshot_data = canonical_json_bytes(snapshot.model_dump(mode="json"))
    object_path = f"manifests/{snapshot.manifest_id}.json"
    selected_store.create(object_path, snapshot_data)

    stored = selected_store.read(object_path)
    if stored.data != snapshot_data:
        raise SnapshotError("stored snapshot bytes differ from the validated publication payload")

    pointer = build_pointer(snapshot, object_path=object_path, data=snapshot_data)
    pointer_data = canonical_json_bytes(pointer.model_dump(mode="json"))
    try:
        current = selected_store.read(LATEST_POINTER_NAME)
        expected_generation = current.generation
    except SnapshotNotFound:
        expected_generation = 0
    pointer_generation = selected_store.replace(
        LATEST_POINTER_NAME,
        pointer_data,
        expected_generation=expected_generation,
    )
    return PublishedSnapshot(pointer=pointer, pointer_generation=pointer_generation)
