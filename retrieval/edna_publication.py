"""Resolve only a complete eDNA retrieval generation; never mix artifact files."""
import json
import tempfile
from contextvars import ContextVar
import uuid
import fcntl
from pathlib import Path

import config
from ingestion.immutable_bundle import atomic_json, digest, verify_bundle, read_bundle, validate_id
from ingestion.artifact_store import ArtifactStore

_pending = ContextVar('edna_pending_publication', default=None)
MAX_CACHE_BYTES = 512 * 1024 * 1024


def publication_root():
    return (config.EDNA_CACHE_DIR / 'retrieval') if config.EDNA_ARTIFACT_URI else config.SERVING_DIR / "edna_generations"


def set_pending():
    if config.EDNA_ARTIFACT_URI:
        store = ArtifactStore(config.EDNA_ARTIFACT_URI)
        _, generation = store.pointer('retrieval/current.json')
        updated = store.replace_pointer('retrieval/current.json',
            {'status': 'pending', 'operation_id': uuid.uuid4().hex}, generation)
        _pending.set((config.EDNA_ARTIFACT_URI, updated))
        return
    atomic_json(config.SERVING_DIR / "edna_current.json", {"status": "pending"})


def set_ready(manifest):
    if config.EDNA_ARTIFACT_URI:
        store = ArtifactStore(config.EDNA_ARTIFACT_URI)
        receipt, files = store.read('retrieval', manifest['id'])
        if receipt['metadata']['manifest_sha256'] != digest(manifest) or json.loads(files['manifest.json']) != manifest:
            raise ValueError('Retrieval registration mismatch')
        token = _pending.get()
        if token is not None:
            if token[0] != config.EDNA_ARTIFACT_URI:
                raise ValueError('Publication store changed')
            generation = token[1]
        else:
            _, generation = store.pointer('retrieval/current.json')
        store.replace_pointer('retrieval/current.json',
            {'status': 'ready', 'generation_id': manifest['id'], 'manifest_sha256': digest(manifest)}, generation)
        _pending.set(None)
        return
    atomic_json(config.SERVING_DIR / "edna_current.json", {
        "status": "ready", "generation_id": manifest["id"], "manifest_sha256": digest(manifest),
    })


def current_manifest():
    if config.EDNA_ARTIFACT_URI:
        store = ArtifactStore(config.EDNA_ARTIFACT_URI)
        payload, _ = store.pointer('retrieval/current.json')
        if payload is None:
            return None
        if payload.get('status') != 'ready':
            raise ValueError('eDNA retrieval publication is incomplete')
        identity = validate_id(payload['generation_id'])
        expected = validate_id(payload['manifest_sha256'])
        root = publication_root()
        root.mkdir(parents=True, exist_ok=True)
        target = root / identity
        # Only local POSIX cache locking; never a lock on the bucket mount.
        with (root / '.cache.lock').open('a+b') as lock:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
            if not target.exists():
                _, files = store.read('retrieval', identity, max_bytes=128*1024*1024)
                manifest = json.loads(files['manifest.json'])
                if digest(manifest) != expected or manifest['id'] != identity:
                    raise ValueError('eDNA retrieval pointer integrity check failed')
                used = sum(p.stat().st_size for p in root.rglob('*') if p.is_file())
                if used + sum(len(data) for data in files.values()) > MAX_CACHE_BYTES:
                    raise ValueError('Retrieval cache limit exceeded; replace disposable cache')
                staging = Path(tempfile.mkdtemp(prefix='.cache-', dir=root))
                for name, data in files.items():
                    if Path(name).name != name:
                        raise ValueError('Invalid retrieval file path')
                    (staging / name).write_bytes(data)
                staging.rename(target)
            manifest, _ = read_bundle(root, identity, expected_digest=expected,
                required_files={'anemone_retrieval_documents.jsonl', 'anemone_retrieval_documents.parquet'})
        return manifest
    pointer = config.SERVING_DIR / "edna_current.json"
    if not pointer.exists():
        return None
    payload = json.loads(pointer.read_bytes())
    if payload.get("status") != "ready":
        raise ValueError("eDNA retrieval publication is incomplete")
    manifest = verify_bundle(publication_root(), payload.get("generation_id"))
    if digest(manifest) != payload.get("manifest_sha256"):
        raise ValueError("eDNA retrieval pointer integrity check failed")
    return manifest


def retrieval_path(suffix: str) -> Path:
    if suffix not in {"parquet", "jsonl"}:
        raise ValueError("Invalid retrieval artifact type")
    manifest = current_manifest()
    name = f"anemone_retrieval_documents.{suffix}"
    # Compatibility for pre-generation PR3 artifacts only, never on pending/error.
    if manifest:
        return publication_root() / manifest["id"] / name
    return (publication_root() / 'unpublished' / name) if config.EDNA_ARTIFACT_URI else config.SERVING_DIR / name
