"""Explicit isolated LOCAL catalogue snapshots and transactional lifecycle state.

No configuration, cloud client, legacy fallback or model dependency is used.
Immutable blobs/manifests are written before registration. One bounded atomic
control document, serialized by a POSIX file lock and generation CAS, owns latest,
references, holds, revocations, logical retirements and their audits. A failure
before its commit leaves only unreachable bytes, never a readable partial seal.

Cleanup here means *logical retirement*: it revokes readability and rejects later
holds/references. It deliberately deletes zero physical files. Physical garbage
collection is a separate future operation; local state/files and a capture DB do
not claim a distributed transaction. Capture owners retain source-head locks
across final validation and promotion. A transaction/connection failure around
local promotion must be reconciled by its capture owner; local state is not
rolled back by a subsequent database failure.
"""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import stat
from contextlib import contextmanager
from pathlib import Path
from typing import Callable

from ingestion.artifact_store import BoundedLocalStore, safe_key
from ingestion.immutable_bundle import canonical_bytes, validate_id
from ingestion.provenance_snapshot import SnapshotConflict, SnapshotNotFound
from schema.catalogue_snapshot import (
    MAX_MANIFEST_BYTES,
    SnapshotManifest,
    compare_snapshots,
    manifest_bytes,
    validated_manifest,
)

MAX_CONTROL_BYTES = 4 * 1024 * 1024


class SnapshotAccessDenied(PermissionError):
    """A current trusted gate or persistent withdrawal denies this snapshot."""


class SnapshotCommitUncertain(RuntimeError):
    """A failed state write cannot yet be reconciled as committed or rolled back."""

    def __init__(
        self, *, action, details, proposed_revision, proposed_latest_generation
    ):
        self.action = action
        self.details = dict(details)
        self.proposed_revision = proposed_revision
        self.proposed_latest_generation = proposed_latest_generation
        super().__init__(
            "Catalogue state commit uncertain; reopen and reconcile before retry"
        )


class LocalCatalogueSnapshotStore:
    def __init__(
        self,
        *,
        root: Path,
        access_gate: Callable[[SnapshotManifest], bool],
        prefix: str = "v1/catalogue",
    ):
        root = Path(root)
        if not root.is_absolute() or not callable(access_gate):
            raise ValueError(
                "Explicit absolute local root and trusted access gate required"
            )
        safe_key(prefix)
        if prefix.split("/")[0] != "v1":
            raise ValueError("Catalogue snapshots require a separate v1 namespace")
        self.root = root
        self.prefix = prefix
        self.access_gate = access_gate
        self._guard(root)
        root.mkdir(parents=True, exist_ok=True)
        self.store = BoundedLocalStore(root)
        self._guard(root / prefix)
        (root / prefix).mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _guard(path: Path):
        for part in (path, *path.parents):
            try:
                mode = part.lstat().st_mode
            except FileNotFoundError:
                continue
            if stat.S_ISLNK(mode):
                raise ValueError("Symlink in catalogue store path")
            if part != path and not stat.S_ISDIR(mode):
                raise ValueError("Non-directory catalogue store ancestor")
        if path.exists() and not (path.is_file() or path.is_dir()):
            raise ValueError("Nonregular catalogue store path")

    def _key(self, suffix):
        key = safe_key(f"{self.prefix}/{safe_key(suffix)}")
        self._guard(self.root / key)
        return key

    @contextmanager
    def _locked(self):
        key = self._key("control.lock")
        flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0)
        fd = os.open(self.root / key, flags, 0o600)
        try:
            if not stat.S_ISREG(os.fstat(fd).st_mode):
                raise ValueError("Catalogue lock is not regular")
            fcntl.flock(fd, fcntl.LOCK_EX)
            yield
        finally:
            os.close(fd)

    @staticmethod
    def _empty_state():
        return {
            "schema_version": "catalogue-snapshot-control-v1",
            "revision": 0,
            "latest": None,
            "latest_generation": 0,
            "snapshots": {},
            "references": {},
            "audits": [],
        }

    def _state(self):
        try:
            obj = self.store.read(
                self._key("control.json"), max_bytes=MAX_CONTROL_BYTES
            )
        except SnapshotNotFound:
            return self._empty_state(), 0
        state = json.loads(obj.data)
        if (
            set(state) != set(self._empty_state())
            or state["schema_version"] != "catalogue-snapshot-control-v1"
            or type(state["revision"]) is not int
            or state["revision"] < 0
            or type(state["latest_generation"]) is not int
            or state["latest_generation"] < 0
            or not isinstance(state["snapshots"], dict)
            or not isinstance(state["references"], dict)
            or not isinstance(state["audits"], list)
        ):
            raise ValueError("Invalid catalogue control state")
        for identity, entry in state["snapshots"].items():
            validate_id(identity)
            if set(entry) != {"held", "revoked", "retired"} or any(
                type(value) is not bool for value in entry.values()
            ):
                raise ValueError("Invalid snapshot lifecycle state")
        if state["latest"] is not None:
            validate_id(state["latest"])
            if (
                state["latest"] not in state["snapshots"]
                or state["snapshots"][state["latest"]]["retired"]
            ):
                raise ValueError("Invalid latest snapshot registration")
        for reference, identity in state["references"].items():
            self._reference_id(reference)
            if (
                identity not in state["snapshots"]
                or state["snapshots"][identity]["retired"]
            ):
                raise ValueError("Invalid snapshot reference registration")
        return state, obj.generation

    def _commit(self, state, generation, *, action, details):
        state["revision"] += 1
        state["audits"].append(
            {"revision": state["revision"], "action": action, **details}
        )
        data = canonical_bytes(state)
        if len(data) > MAX_CONTROL_BYTES:
            raise ValueError(
                "Catalogue control state limit exceeded; no state committed"
            )
        # LocalSnapshotStore.replace also locks its CAS file; reject its lock path
        # before delegating because the primitive itself accepts ordinary paths.
        self._key("control.json.lock")
        key = self._key("control.json")
        try:
            self.store.replace(key, data, expected_generation=generation)
        except Exception as original_error:
            # A primitive error can occur after os.replace. Reconcile exact bytes
            # or unchanged generation; if observation fails, expose uncertainty
            # rather than implying that a state transition definitely rolled back.
            uncertain = SnapshotCommitUncertain(
                action=action,
                details=details,
                proposed_revision=state["revision"],
                proposed_latest_generation=state["latest_generation"],
            )
            try:
                observed = self.store.read(key, max_bytes=MAX_CONTROL_BYTES)
            except SnapshotNotFound:
                if generation == 0:
                    raise original_error
                raise uncertain from original_error
            except Exception:
                raise uncertain from original_error
            if observed.data != data:
                if observed.generation == generation:
                    raise original_error
                raise uncertain from original_error
        return state["revision"]

    def _create(self, suffix, data):
        key = self._key(suffix)
        try:
            self.store.create(key, data)
        except SnapshotConflict:
            pass
        observed = self.store.read(self._key(suffix), max_bytes=len(data))
        if observed.data != data:
            raise ValueError("Immutable catalogue object conflict")

    @staticmethod
    def _registered(state, identity):
        validate_id(identity)
        entry = state["snapshots"].get(identity)
        if entry is None or entry["retired"]:
            raise SnapshotNotFound("Snapshot is not registered or was retired")
        return entry

    def _verified(self, identity):
        validate_id(identity)
        raw = self.store.read(
            self._key(f"manifests/{identity}.json"), max_bytes=MAX_MANIFEST_BYTES
        ).data
        if hashlib.sha256(raw).hexdigest() != identity:
            raise ValueError("Snapshot manifest integrity failure")
        manifest = validated_manifest(json.loads(raw))
        if manifest_bytes(manifest) != raw:
            raise ValueError("Snapshot manifest is not canonical")
        contents = {}
        for obj in manifest.objects:
            data = self.store.read(
                self._key(f"objects/{obj.sha256}"), max_bytes=obj.size_bytes
            ).data
            if (
                len(data) != obj.size_bytes
                or hashlib.sha256(data).hexdigest() != obj.sha256
            ):
                raise ValueError("Snapshot object integrity failure")
            contents[obj.object_id] = data
        return manifest, contents

    def _access(self, state, identity, manifest):
        entry = self._registered(state, identity)
        # Gate receives an isolated copy, so it cannot change verified manifest.
        if (
            entry["revoked"]
            or self.access_gate(validated_manifest(manifest)) is not True
        ):
            raise SnapshotAccessDenied("Current snapshot access denied")

    def seal(
        self, manifest: SnapshotManifest | dict, contents: dict[str, bytes]
    ) -> str:
        raw = manifest_bytes(manifest)
        manifest = validated_manifest(json.loads(raw))
        identity = hashlib.sha256(raw).hexdigest()
        if not isinstance(contents, dict) or set(contents) != {
            obj.object_id for obj in manifest.objects
        }:
            raise ValueError("Exact snapshot object membership required")
        contents = dict(contents)
        for obj in manifest.objects:
            data = contents[obj.object_id]
            if (
                type(data) is not bytes
                or len(data) != obj.size_bytes
                or hashlib.sha256(data).hexdigest() != obj.sha256
            ):
                raise ValueError("Snapshot supplied object integrity failure")
        with self._locked():
            state, generation = self._state()
            existing = state["snapshots"].get(identity)
            if existing is not None:
                self._registered(state, identity)
                self._verified(identity)
                return identity
            for obj in manifest.objects:
                self._create(f"objects/{obj.sha256}", contents[obj.object_id])
            self._create(f"manifests/{identity}.json", raw)
            self._verified(identity)
            state["snapshots"][identity] = {
                "held": False,
                "revoked": False,
                "retired": False,
            }
            self._commit(
                state, generation, action="seal", details={"snapshot_id": identity}
            )
            return identity

    def promote(
        self,
        identity: str,
        *,
        expected_generation: int,
        validate_capture: Callable[[], None] | None = None,
    ) -> int:
        with self._locked():
            state, generation = self._state()
            manifest, _ = self._verified(identity)
            self._access(state, identity, manifest)
            if (
                type(expected_generation) is not int
                or state["latest_generation"] != expected_generation
            ):
                raise SnapshotConflict("Catalogue latest pointer generation changed")
            if validate_capture is not None:
                if validate_capture() is False:
                    raise SnapshotConflict("Capture validator rejected promotion")
            if state["latest"] == identity:
                return state["latest_generation"]
            state["latest"] = identity
            state["latest_generation"] += 1
            self._commit(
                state, generation, action="promote", details={"snapshot_id": identity}
            )
            return state["latest_generation"]

    def latest(self) -> tuple[str | None, int]:
        with self._locked():
            state, _ = self._state()
            if state["latest"] is not None:
                manifest, _ = self._verified(state["latest"])
                self._access(state, state["latest"], manifest)
            return state["latest"], state["latest_generation"]

    def read(self, identity: str) -> tuple[SnapshotManifest, dict[str, bytes]]:
        with self._locked():
            state, _ = self._state()
            self._registered(state, identity)
            manifest, contents = self._verified(identity)
            self._access(state, identity, manifest)
            return manifest, contents

    @staticmethod
    def _reference_id(reference):
        from pydantic import TypeAdapter
        from schema.context_catalogue import Identifier

        return TypeAdapter(Identifier).validate_python(reference, strict=True)

    def add_reference(self, identity: str, reference: str) -> int:
        self._reference_id(reference)
        with self._locked():
            state, generation = self._state()
            manifest, _ = self._verified(identity)
            self._access(state, identity, manifest)
            existing = state["references"].get(reference)
            if existing is not None:
                if existing != identity:
                    raise SnapshotConflict("Reference already binds another snapshot")
                return state["revision"]
            state["references"][reference] = identity
            return self._commit(
                state,
                generation,
                action="reference",
                details={"reference": reference, "snapshot_id": identity},
            )

    def remove_reference(self, identity: str, reference: str) -> int:
        validate_id(identity)
        self._reference_id(reference)
        with self._locked():
            state, generation = self._state()
            existing = state["references"].get(reference)
            if existing is None:
                return state["revision"]
            if existing != identity:
                raise SnapshotConflict("Reference binds another snapshot")
            del state["references"][reference]
            return self._commit(
                state,
                generation,
                action="unreference",
                details={"reference": reference, "snapshot_id": identity},
            )

    def set_hold(self, identity: str, held: bool) -> int:
        if type(held) is not bool:
            raise ValueError("Hold must be boolean")
        with self._locked():
            state, generation = self._state()
            entry = self._registered(state, identity)
            if entry["held"] == held:
                return state["revision"]
            entry["held"] = held
            return self._commit(
                state,
                generation,
                action="hold",
                details={"snapshot_id": identity, "held": held},
            )

    def revoke(self, identity: str) -> int:
        """Persist withdrawal. Only a separately reviewed policy may restore it."""
        with self._locked():
            state, generation = self._state()
            entry = self._registered(state, identity)
            if entry["revoked"]:
                return state["revision"]
            entry["revoked"] = True
            return self._commit(
                state, generation, action="revoke", details={"snapshot_id": identity}
            )

    def cleanup(self, candidates: list[str], *, dry_run: bool = False) -> dict:
        if type(dry_run) is not bool:
            raise ValueError("Dry run must be boolean")
        identities = sorted(set(validate_id(identity) for identity in candidates))
        with self._locked():
            state, generation = self._state()
            referenced = set(state["references"].values())
            eligible = [
                identity
                for identity in identities
                if identity in state["snapshots"]
                and not state["snapshots"][identity]["retired"]
                and not state["snapshots"][identity]["held"]
                and identity != state["latest"]
                and identity not in referenced
            ]
            report = {
                "eligible_ids": eligible,
                "retired_ids": [] if dry_run else eligible,
                "retired_count": 0 if dry_run else len(eligible),
                "physical_deleted_count": 0,
                "dry_run": dry_run,
            }
            if eligible and not dry_run:
                for identity in eligible:
                    state["snapshots"][identity]["retired"] = True
                self._commit(
                    state,
                    generation,
                    action="retire",
                    details={
                        "snapshot_ids": eligible,
                        "retired_count": len(eligible),
                        "physical_deleted_count": 0,
                    },
                )
            return report

    def lifecycle(self) -> dict:
        """Trusted operator state for retention audits, never a public data listing."""
        with self._locked():
            state, _ = self._state()
            return state

    def changes(self, old_identity: str, new_identity: str) -> dict:
        old, _ = self.read(old_identity)
        new, _ = self.read(new_identity)
        return compare_snapshots(old, new)
