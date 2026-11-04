"""Additive C17 retention in the existing beta C09 lifecycle authority.

The serving identity needs generation-conditional replacement of the *single*
``v1/catalogue/control.json`` object. It still cannot write scientific contents,
manifest or activation objects. Every reference is visible to ordinary C09
readers/operator cleanup; there is no separate database retention authority.

Only ``c17:dependency:<sha256>`` additions are supported. They never release
protection, restore access, seal/promote/revoke snapshots or perform cleanup.
Prepared/uncertain C17 operations retain conservative references across process
restarts. No local filesystem or in-memory production fallback exists.
"""
from __future__ import annotations

import re

from ingestion.catalogue_snapshot import MAX_CONTROL_BYTES, SnapshotCommitUncertain
from ingestion.gcs_catalogue_snapshot import GcsCatalogueSnapshotStore, validated_lifecycle
from ingestion.immutable_bundle import canonical_bytes, validate_id
from ingestion.provenance_snapshot import SnapshotConflict

MAX_REFERENCE_ATTEMPTS = 8
REFERENCE_PATTERN = re.compile(r"c17:dependency:[a-f0-9]{64}")


class BetaCatalogueRetentionStore(GcsCatalogueSnapshotStore):
    """Canonical, current-access-checked C09 CAS with reference additions only."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        if not callable(getattr(self._store, "replace", None)):
            raise ValueError("Explicit generation-conditional beta control transport required")

    @staticmethod
    def _reference(reference):
        if type(reference) is not str or REFERENCE_PATTERN.fullmatch(reference) is None:
            raise ValueError("Only explicit C17 dependency retention references are supported")
        return reference

    @staticmethod
    def _uncertain(identity, reference, state):
        return SnapshotCommitUncertain(action="reference", details={
            "snapshot_id": identity, "reference": reference},
            proposed_revision=state["revision"],
            proposed_latest_generation=state["latest_generation"])

    def _observed_reference(self, identity, reference, manifest):
        """Reconcile the durable binding; every successful reply closes access."""
        state, _ = self._state()
        self._access(state, identity, manifest)
        existing = state["references"].get(reference)
        if existing is not None and existing != identity:
            raise SnapshotConflict("Reference already binds another snapshot")
        return state["revision"] if existing == identity else None

    def add_reference(self, identity, reference):
        if self._active_read_scope() is not None:
            raise ValueError("Retention writes cannot share a catalogue read scope")
        validate_id(identity)
        self._reference(reference)
        for _ in range(MAX_REFERENCE_ATTEMPTS):
            # Read verifies canonical manifest, all exact object bytes and current
            # source/activation authority, fenced by fresh lifecycle generations.
            manifest, _contents = self.read(identity)
            state, before = self._state()
            self._access(state, identity, manifest)
            existing = state["references"].get(reference)
            if existing is not None:
                if existing != identity:
                    raise SnapshotConflict("Reference already binds another snapshot")
                return state["revision"]
            state["revision"] += 1
            state["references"][reference] = identity
            state["audits"].append({"revision": state["revision"], "action": "reference",
                "snapshot_id": identity, "reference": reference})
            data = canonical_bytes(state)
            if len(data) > MAX_CONTROL_BYTES:
                raise ValueError("Catalogue control bound exceeded; no retention write attempted")
            validated_lifecycle(data)
            try:
                generation = self._store.replace(self._key("control.json"), data,
                    expected_generation=before.generation)
            except SnapshotConflict:
                # A definitive precondition rejection cannot have committed this
                # replacement. Reopen all authority; never reuse an old state.
                continue
            except Exception:
                # A timeout/error might occur after durable GCS publication. An
                # unchanged read does not prove an in-flight request cannot still
                # commit; only a current matching binding establishes success.
                try:
                    revision = self._observed_reference(identity, reference, manifest)
                except Exception:
                    raise self._uncertain(identity, reference, state) from None
                if revision is not None:
                    return revision
                raise self._uncertain(identity, reference, state) from None
            if type(generation) is not int or generation <= 0 or generation == before.generation:
                raise self._uncertain(identity, reference, state) from None
            try:
                revision = self._observed_reference(identity, reference, manifest)
            except Exception:
                raise self._uncertain(identity, reference, state) from None
            if revision is None:
                raise self._uncertain(identity, reference, state) from None
            return revision
        raise SnapshotConflict("Catalogue retention control is busy; retry under current authority")
