"""Read-only, generation-bound C09 snapshots in the isolated beta GCS store.

The trusted caller supplies the current access decision and exact beta target.
No listing, discovery, empty-state fallback, mutation, reference installation or
promotion occurs. Immutable objects are verified against their canonical C09
manifest, and current lifecycle/authority is checked again before bytes return.
"""
from __future__ import annotations

import hashlib
import json
import os
from contextlib import contextmanager
from contextvars import ContextVar
from copy import deepcopy
from threading import get_ident

from ingestion.artifact_store import BoundedGcsStore, safe_key
from ingestion.catalogue_snapshot import (
    LocalCatalogueSnapshotStore, MAX_CONTROL_BYTES, SnapshotAccessDenied,
)
from ingestion.immutable_bundle import canonical_bytes, validate_id
from ingestion.provenance_snapshot import SnapshotConflict, SnapshotNotFound, StoredObject
from schema.catalogue_snapshot import (
    MAX_MANIFEST_BYTES, compare_snapshots, manifest_bytes, validated_manifest,
)

BUCKET = "ocean-v1-beta-20261101-snapshots"
PREFIX = "v1/catalogue"
MAX_READ_SCOPE_SNAPSHOTS = 256


def _unique(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("Duplicate catalogue control key")
        value[key] = item
    return value


def _json(data):
    return json.loads(data.decode("utf-8"), object_pairs_hook=_unique,
        parse_constant=lambda _: (_ for _ in ()).throw(ValueError("Nonfinite catalogue JSON")))


def validated_lifecycle(data):
    """Validate canonical C09 control and replay its complete Local audit chain.

    This is a pure check of the existing LocalCatalogueSnapshotStore contract;
    it never repairs state or treats missing control as an empty registry.
    """
    try:
        if type(data) is not bytes or not 0 < len(data) <= MAX_CONTROL_BYTES:
            raise ValueError()
        state = _json(data)
        expected = LocalCatalogueSnapshotStore._empty_state()
        if (type(state) is not dict or set(state) != set(expected)
                or state["schema_version"] != expected["schema_version"]
                or type(state["revision"]) is not int or state["revision"] < 0
                or type(state["latest_generation"]) is not int or state["latest_generation"] < 0
                or type(state["snapshots"]) is not dict or type(state["references"]) is not dict
                or type(state["audits"]) is not list or len(state["audits"]) != state["revision"]
                or canonical_bytes(state) != data):
            raise ValueError()
        for identity, entry in state["snapshots"].items():
            validate_id(identity)
            if (type(entry) is not dict or set(entry) != {"held", "revoked", "retired"}
                    or any(type(value) is not bool for value in entry.values())):
                raise ValueError()
        if state["latest"] is not None:
            validate_id(state["latest"])
        for reference, identity in state["references"].items():
            LocalCatalogueSnapshotStore._reference_id(reference)
            validate_id(identity)
        for revision, audit in enumerate(state["audits"], 1):
            if (type(audit) is not dict or type(audit.get("revision")) is not int
                    or audit["revision"] != revision):
                raise ValueError()
            action = audit.get("action")
            if action == "retire":
                if set(audit) != {"revision", "action", "snapshot_ids", "retired_count", "physical_deleted_count"}:
                    raise ValueError()
                identities = audit["snapshot_ids"]
                if (type(identities) is not list or not identities
                        or identities != sorted(set(identities))
                        or type(audit["retired_count"]) is not int or audit["retired_count"] != len(identities)
                        or type(audit["physical_deleted_count"]) is not int or audit["physical_deleted_count"] != 0):
                    raise ValueError()
                for identity in identities:
                    validate_id(identity)
                    entry = expected["snapshots"][identity]
                    if (entry["retired"] or entry["held"] or identity == expected["latest"]
                            or identity in expected["references"].values()):
                        raise ValueError()
                    entry["retired"] = True
            else:
                extra = {"reference"} if action in {"reference", "unreference"} else {"held"} if action == "hold" else set()
                if set(audit) != {"revision", "action", "snapshot_id", *extra}:
                    raise ValueError()
                identity = validate_id(audit["snapshot_id"])
                if action == "seal":
                    if identity in expected["snapshots"]:
                        raise ValueError()
                    expected["snapshots"][identity] = {"held": False, "revoked": False, "retired": False}
                elif action == "unreference":
                    reference = LocalCatalogueSnapshotStore._reference_id(audit["reference"])
                    if expected["references"].pop(reference) != identity:
                        raise ValueError()
                else:
                    entry = expected["snapshots"][identity]
                    if entry["retired"]:
                        raise ValueError()
                    if action == "promote":
                        if entry["revoked"] or expected["latest"] == identity:
                            raise ValueError()
                        expected["latest"], expected["latest_generation"] = identity, expected["latest_generation"] + 1
                    elif action == "reference":
                        reference = LocalCatalogueSnapshotStore._reference_id(audit["reference"])
                        if entry["revoked"] or reference in expected["references"]:
                            raise ValueError()
                        expected["references"][reference] = identity
                    elif action == "hold":
                        if type(audit["held"]) is not bool or audit["held"] == entry["held"]:
                            raise ValueError()
                        entry["held"] = audit["held"]
                    elif action == "revoke":
                        if entry["revoked"]:
                            raise ValueError()
                        entry["revoked"] = True
                    else:
                        raise ValueError()
            expected["revision"] = revision
            expected["audits"].append(audit)
        if expected != state:
            raise ValueError()
        return state
    except Exception:
        raise ValueError("Invalid canonical catalogue lifecycle or audit chain") from None


class GcsCatalogueSnapshotStore:
    def __init__(self, *, bucket=BUCKET, prefix=PREFIX, access_gate, client=None, _test_store=None):
        if bucket != BUCKET or prefix != PREFIX or not callable(access_gate):
            raise ValueError("Explicit isolated beta catalogue target and current access gate required")
        if _test_store is not None:
            if (os.environ.get("DEPLOYMENT_ENV") != "test" or client is not None
                    or not callable(getattr(_test_store, "read", None))):
                raise ValueError("Synthetic transport injection requires explicit test environment")
            self._store = _test_store
        else:
            self._store = BoundedGcsStore(bucket=bucket, prefix="", client=client)
        self.bucket_name, self.prefix, self.access_gate = bucket, prefix, access_gate
        self._control_scope = ContextVar("catalogue_control_scope", default=None)

    def _key(self, suffix):
        return safe_key(self.prefix + "/" + safe_key(suffix))

    def _read(self, suffix, maximum):
        result = self._store.read(self._key(suffix), max_bytes=maximum)
        if (not isinstance(result, StoredObject) or type(result.data) is not bytes
                or len(result.data) > maximum or type(result.generation) is not int or result.generation <= 0):
            raise ValueError("Bounded generation-identified catalogue object required")
        return result

    def _fresh_state(self):
        try:
            obj = self._read("control.json", MAX_CONTROL_BYTES)
        except SnapshotNotFound:
            raise ValueError("Current catalogue control is unavailable") from None
        return validated_lifecycle(obj.data), obj

    def _active_read_scope(self):
        scope = self._control_scope.get()
        return scope if scope and scope["active"] and scope["thread"] == get_ident() else None

    def _state(self):
        scope = self._active_read_scope()
        if scope is None:
            return self._fresh_state()
        # Consumers receive detached state; no caller can mutate the shared fence.
        return deepcopy(scope["state"]), StoredObject(scope["object"].data, scope["object"].generation)

    @contextmanager
    def read_scope(self):
        """One current control observation, fenced again before returning work.

        Immutable manifest/payload reads and hashes remain fresh. No state is
        retained across operations, threads or the lifetime of an exited scope.
        Nested read operations share the same generation-consistent observation.
        """
        if self._active_read_scope() is not None:
            yield
            return
        state, before = self._fresh_state()
        scope = {"active": True, "thread": get_ident(), "state": state, "object": before, "manifests": {}}
        token = self._control_scope.set(scope)
        try:
            yield
            current, after = self._fresh_state()
            self._same_control(before, after)
            for identity, manifest in tuple(scope["manifests"].items()):
                self._access(current, identity, manifest)
        finally:
            scope["active"] = False
            self._control_scope.reset(token)

    @staticmethod
    def _registered(state, identity):
        entry = state["snapshots"].get(validate_id(identity))
        if entry is None or entry["retired"]:
            raise SnapshotNotFound("Snapshot is not registered or was retired")
        if entry["revoked"]:
            raise SnapshotAccessDenied("Current snapshot access denied")
        return entry

    def _access(self, state, identity, manifest):
        self._registered(state, identity)
        checked = validated_manifest(manifest)
        if self.access_gate(checked) is not True:
            raise SnapshotAccessDenied("Current snapshot access denied")
        scope = self._active_read_scope()
        if scope is not None and identity not in scope["manifests"]:
            if len(scope["manifests"]) >= MAX_READ_SCOPE_SNAPSHOTS:
                raise ValueError("Catalogue read scope snapshot bound exceeded")
            scope["manifests"][identity] = checked.model_copy(deep=True)

    @staticmethod
    def _same_control(before, after):
        if before.generation != after.generation or before.data != after.data:
            raise SnapshotConflict("Catalogue control changed during read; retry under current authority")

    def read(self, identity):
        validate_id(identity)
        state, before = self._state()
        self._registered(state, identity)
        try:
            raw = self._read(f"manifests/{identity}.json", MAX_MANIFEST_BYTES).data
            if hashlib.sha256(raw).hexdigest() != identity:
                raise ValueError("Snapshot manifest integrity failure")
            manifest = validated_manifest(_json(raw))
            if manifest_bytes(manifest) != raw:
                raise ValueError("Snapshot manifest is not canonical")
            self._access(state, identity, manifest)
            contents = {}
            for obj in manifest.objects:
                data = self._read(f"objects/{obj.sha256}", obj.size_bytes).data
                if len(data) != obj.size_bytes or hashlib.sha256(data).hexdigest() != obj.sha256:
                    raise ValueError("Snapshot object integrity failure")
                contents[obj.object_id] = data
        except SnapshotNotFound:
            raise ValueError("Registered snapshot immutable bytes are unavailable") from None
        current, after = self._state()
        self._same_control(before, after)
        self._access(current, identity, manifest)
        return manifest, contents

    def lifecycle(self):
        """A detached, freshly fetched trusted control state; never a data listing."""
        return self._state()[0]

    def latest(self):
        state, before = self._state()
        if state["latest"] is not None:
            self.read(state["latest"])
        current, after = self._state()
        self._same_control(before, after)
        return current["latest"], current["latest_generation"]

    def changes(self, old_identity, new_identity):
        return compare_snapshots(self.read(old_identity)[0], self.read(new_identity)[0])

    @staticmethod
    def _unsupported(*args, **kwargs):
        raise NotImplementedError("Serving catalogue store is read-only; operator mutation is not supported")

    seal = promote = add_reference = remove_reference = set_hold = revoke = cleanup = _unsupported
