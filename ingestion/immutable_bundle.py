"""Content-addressed local bundles with a single verified publication pointer."""
from pathlib import Path
import hashlib
import json
import os
import re
import tempfile


def canonical_bytes(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                      allow_nan=False).encode()


def digest(value):
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def atomic_json(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=".pointer-", dir=path.parent)
    with os.fdopen(fd, "wb") as handle:
        handle.write(canonical_bytes(value))
        handle.flush()
        os.fsync(handle.fileno())
    Path(name).replace(path)


def validate_id(value):
    if not isinstance(value, str) or not re.fullmatch(r"[a-f0-9]{64}", value):
        raise ValueError("Invalid bundle identifier")
    return value


def seal_bundle(staging: Path, root: Path, identity: str, metadata: dict):
    validate_id(identity)
    files = {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
             for p in sorted(staging.iterdir()) if p.is_file()}
    manifest = {**metadata, "id": identity, "files": files}
    (staging / "manifest.json").write_bytes(canonical_bytes(manifest))
    destination = root / identity
    if not destination.exists():
        try:
            staging.rename(destination)
            return manifest
        except OSError:
            if not destination.exists():
                raise
    if destination.exists():
        existing = verify_bundle(root, identity)
        if existing != manifest:
            raise ValueError("Immutable bundle content conflict")
        # Only discard the duplicate staging files created by this publication.
        for name in [*files, 'manifest.json']:
            (staging / name).unlink()
        staging.rmdir()
    return manifest


def read_bundle(root: Path, identity: str, *, expected_digest=None, required_files=None,
                max_bytes=128 * 1024 * 1024):
    """Verify and return the same bytes consumers will use (no second file read)."""
    # Reuse the bounded local reader's realpath containment and symlink guards.
    # Keep every untrusted bundle component behind that filesystem boundary.
    from ingestion.artifact_store import BoundedLocalStore
    from ingestion.provenance_snapshot import SnapshotNotFound

    validate_id(identity)
    if root.is_symlink():
        raise ValueError("Invalid manifest path")
    store = BoundedLocalStore(root)
    try:
        manifest_bytes = store.read(identity + "/manifest.json",
                                    max_bytes=min(max_bytes, 1024 * 1024)).data
    except SnapshotNotFound as exc:
        raise ValueError("Unknown bundle") from exc
    except ValueError as exc:
        if str(exc) == "Artifact byte limit exceeded":
            raise ValueError("Bundle manifest limit exceeded") from exc
        raise ValueError("Invalid manifest path") from exc
    manifest = json.loads(manifest_bytes)
    if manifest.get("id") != identity or not isinstance(manifest.get("files"), dict):
        raise ValueError("Invalid bundle manifest")
    if expected_digest is not None and digest(manifest) != expected_digest:
        raise ValueError("Bundle manifest integrity check failed")
    if required_files is not None and set(manifest['files']) != set(required_files):
        raise ValueError("Incomplete bundle file contract")
    contents = {'manifest.json': manifest_bytes}
    total = len(manifest_bytes)
    for name, expected in manifest["files"].items():
        if not name or Path(name).name != name or "\\" in name or name in {".", "..", "manifest.json"}:
            raise ValueError("Invalid bundle path")
        try:
            data = store.read(identity + "/" + name, max_bytes=max_bytes - total).data
        except (SnapshotNotFound, ValueError) as exc:
            if str(exc) == "Artifact byte limit exceeded":
                raise ValueError("Bundle byte resource limit exceeded") from exc
            raise ValueError("Bundle integrity check failed") from exc
        total += len(data)
        if total > max_bytes:
            raise ValueError('Bundle byte resource limit exceeded')
        if hashlib.sha256(data).hexdigest() != expected:
            raise ValueError("Bundle integrity check failed")
        contents[name] = data
    return manifest, contents


def verify_bundle(root: Path, identity: str):
    return read_bundle(root, identity)[0]
