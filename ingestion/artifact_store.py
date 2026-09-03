"""Bounded immutable research objects with generation-conditional publication.

No directory operations are performed on GCS. Local staging/cache paths must
be POSIX storage. The index retains every registration; latest is separate.
"""

from pathlib import Path, PurePosixPath
from urllib.parse import urlparse
import hashlib
import json
import tempfile

from ingestion.immutable_bundle import canonical_bytes, digest, validate_id
from ingestion.provenance_snapshot import (
    GcsSnapshotStore,
    LocalSnapshotStore,
    SnapshotConflict,
    SnapshotNotFound,
    StoredObject,
)

MAX_BYTES = 512 * 1024 * 1024
MAX_FILES = 4000
MAX_INDEX_BYTES = 4 * 1024 * 1024
NAMESPACES = {
    "raw",
    "normalized",
    "retrieval",
    "analysis",
    "recipes",
    "evaluation",
    "operations",
}


def safe_key(value):
    if not isinstance(value, str) or not value or "\\" in value:
        raise ValueError("Invalid artifact key")
    path = PurePosixPath(value)
    if path.is_absolute() or any(p in {"", ".", ".."} for p in value.split("/")):
        raise ValueError("Invalid artifact key")
    return value


class BoundedLocalStore(LocalSnapshotStore):
    def read(self, key, *, max_bytes=MAX_BYTES):
        safe_key(key)
        path = self.root / key
        if any(p.is_symlink() for p in (path, *path.parents)):
            raise ValueError("Symlink in artifact path")
        try:
            with path.open("rb") as handle:
                data = handle.read(max_bytes + 1)
                import os

                generation = os.fstat(handle.fileno()).st_mtime_ns
        except FileNotFoundError as exc:
            raise SnapshotNotFound("Artifact not found") from exc
        if len(data) > max_bytes:
            raise ValueError("Artifact byte limit exceeded")
        return StoredObject(data, generation)


class BoundedGcsStore(GcsSnapshotStore):
    def read(self, key, *, max_bytes=MAX_BYTES):
        safe_key(key)
        blob = self.bucket.blob(self._name(key))
        try:
            blob.reload()
            if blob.size is None or int(blob.size) > max_bytes:
                raise ValueError("Artifact byte limit exceeded")
            generation = int(blob.generation)
            data = blob.download_as_bytes(if_generation_match=generation)
        except ValueError:
            raise
        except Exception as exc:
            raise self._translate_error(exc, key=key) from exc
        if len(data) > max_bytes:
            raise ValueError("Artifact byte limit exceeded")
        return StoredObject(data, generation)


class ArtifactStore:
    def __init__(self, uri=None, *, store=None):
        if store is not None:
            self.store = store
            return
        parsed = urlparse(uri or "")
        if parsed.query or parsed.fragment or parsed.username or parsed.password:
            raise ValueError("Invalid artifact-store URI")
        if parsed.scheme == "gs" and parsed.netloc:
            if parsed.path.strip("/"):
                safe_key(parsed.path.strip("/"))
            self.store = BoundedGcsStore(
                bucket=parsed.netloc, prefix=parsed.path.strip("/")
            )
        elif (
            parsed.scheme == "file"
            and not parsed.netloc
            and Path(parsed.path).is_absolute()
        ):
            self.store = BoundedLocalStore(Path(parsed.path))
        else:
            raise ValueError(
                "Artifact store requires gs://bucket/prefix or absolute file:// URI"
            )

    def _read(self, key, maximum=MAX_BYTES):
        return self.store.read(safe_key(key), max_bytes=maximum)

    def pointer(self, key):
        try:
            value = self._read(key, MAX_INDEX_BYTES)
            return json.loads(value.data), value.generation
        except SnapshotNotFound:
            return None, 0

    def replace_pointer(self, key, payload, generation):
        data = canonical_bytes(payload)
        if len(data) > MAX_INDEX_BYTES:
            raise ValueError("Artifact index limit exceeded")
        return self.store.replace(safe_key(key), data, expected_generation=generation)

    @staticmethod
    def _namespace(namespace):
        if namespace not in NAMESPACES:
            raise ValueError("Invalid artifact namespace")
        return namespace

    def entries(self, namespace):
        self._namespace(namespace)
        index, _ = self.pointer(namespace + "/index.json")
        if index is None:
            return {}
        if index.get("schema_version") != 1 or not isinstance(
            index.get("entries"), dict
        ):
            raise ValueError("Invalid artifact index")
        for identity, entry in index["entries"].items():
            validate_id(identity)
            validate_id(entry["receipt_sha256"])
        return index["entries"]

    def _create(self, key, data):
        try:
            self.store.create(key, data)
        except SnapshotConflict:
            pass
        observed = self._read(key, len(data))
        if observed.data != data:
            raise ValueError("Immutable artifact conflict")
        return observed.generation

    def publish(self, namespace, identity, files, *, metadata=None):
        self._namespace(namespace)
        validate_id(identity)
        if (
            not files
            or len(files) > MAX_FILES
            or sum(len(v) for v in files.values()) > MAX_BYTES
        ):
            raise ValueError("Artifact file/byte limit exceeded")
        objects = {}
        for name, data in sorted(files.items()):
            safe_key(name)
            key = f"{namespace}/objects/{identity}/{name}"
            generation = self._create(key, data)
            objects[name] = {
                "sha256": hashlib.sha256(data).hexdigest(),
                "size": len(data),
                "generation": generation,
            }
        receipt = {
            "schema_version": 1,
            "id": identity,
            "namespace": namespace,
            "files": objects,
            "metadata": metadata or {},
        }
        data = canonical_bytes(receipt)
        if len(data) > MAX_INDEX_BYTES:
            raise ValueError("Artifact receipt limit exceeded")
        self._create(f"{namespace}/registry/{identity}.json", data)
        entry = {"receipt_sha256": digest(receipt), "metadata": metadata or {}}
        # Re-read and merge on conflict: never lose a concurrently registered run.
        for _ in range(8):
            index, generation = self.pointer(namespace + "/index.json")
            if index is not None and (
                index.get("schema_version") != 1
                or not isinstance(index.get("entries"), dict)
            ):
                raise ValueError("Invalid artifact index")
            entries = index["entries"] if index is not None else {}
            if identity in entries and entries[identity] != entry:
                raise ValueError("Artifact registration conflict")
            entries[identity] = entry
            try:
                self.replace_pointer(
                    namespace + "/index.json",
                    {"schema_version": 1, "entries": entries},
                    generation,
                )
                return receipt
            except SnapshotConflict:
                continue
        raise SnapshotConflict("Artifact index is busy; retry publication")

    def read(self, namespace, identity, *, max_bytes=MAX_BYTES):
        validate_id(identity)
        entry = self.entries(namespace).get(identity)
        if entry is None:
            raise SnapshotNotFound("Unregistered artifact")
        receipt = json.loads(
            self._read(f"{namespace}/registry/{identity}.json", MAX_INDEX_BYTES).data
        )
        if (
            digest(receipt) != entry["receipt_sha256"]
            or receipt.get("id") != identity
            or receipt.get("namespace") != namespace
        ):
            raise ValueError("Artifact receipt integrity failure")
        if (
            not isinstance(receipt.get("files"), dict)
            or not 0 < len(receipt["files"]) <= MAX_FILES
        ):
            raise ValueError("Invalid artifact file contract")
        total, contents = 0, {}
        for name, info in receipt["files"].items():
            safe_key(name)
            size = info["size"]
            if not isinstance(size, int) or size < 0:
                raise ValueError("Invalid artifact size")
            total += size
            if total > max_bytes:
                raise ValueError("Artifact byte limit exceeded")
            obj = self._read(f"{namespace}/objects/{identity}/{name}", size)
            if (
                obj.generation != info["generation"]
                or len(obj.data) != size
                or hashlib.sha256(obj.data).hexdigest() != info["sha256"]
            ):
                raise ValueError("Artifact object integrity failure")
            contents[name] = obj.data
        return receipt, contents

    def restore(self, namespace, identity, destination):
        """Restore a verified bundle to a caller-selected local cache directory."""
        receipt, files = self.read(namespace, identity)
        if destination.exists():
            if tree_files(destination) != files:
                raise ValueError("Existing local artifact differs from registration")
            return receipt
        if any(p.is_symlink() for p in (destination, *destination.parents)):
            raise ValueError("Symlink in cache destination")
        destination.parent.mkdir(parents=True, exist_ok=True)
        staging = Path(tempfile.mkdtemp(prefix=".restore-", dir=destination.parent))
        for name, data in files.items():
            path = staging / safe_key(name)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        staging.rename(destination)
        return receipt

    def publish_tree(self, namespace, directory, *, metadata=None):
        files = tree_files(directory)
        identity = digest(
            {name: hashlib.sha256(data).hexdigest() for name, data in files.items()}
        )
        return self.publish(namespace, identity, files, metadata=metadata)


def tree_files(directory):
    """Read only a bounded explicitly selected staging bundle, never a data root."""
    if directory.is_symlink() or not directory.is_dir():
        raise ValueError("Invalid staging directory")
    files, total = {}, 0
    for path in sorted(directory.rglob("*")):
        if path.is_symlink():
            raise ValueError("Symlink in staging bundle")
        if not path.is_file():
            continue
        with path.open("rb") as handle:
            data = handle.read(MAX_BYTES - total + 1)
        total += len(data)
        if total > MAX_BYTES or len(files) >= MAX_FILES:
            raise ValueError("Artifact file/byte limit exceeded")
        files[path.relative_to(directory).as_posix()] = data
    return files
