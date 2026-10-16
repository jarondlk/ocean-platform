"""Trusted C14 registration of an existing scientific index and its dependencies.

Registration never imports, promotes, approves or exposes a snapshot. An operator
supplies an explicit isolated C09 store and an already sealed index. References
protect the index and every exact child from cleanup; current withdrawals still
apply. This is deliberately absent from public routes and agent capabilities.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib

from pydantic import TypeAdapter

from ingestion.catalogue_snapshot import SnapshotAccessDenied
from ingestion.scientific_catalogue_inputs import load_registry
from schema.context_catalogue import Identifier, Sha256, canonical_json


@dataclass(frozen=True)
class ScientificCatalogueRegistration:
    snapshot_id: str
    child_snapshot_ids: tuple[str, ...]
    references: tuple[tuple[str, str], ...]
    registration_id: str

    def __post_init__(self):
        TypeAdapter(Identifier).validate_python(self.registration_id)
        for identity in (self.snapshot_id, *self.child_snapshot_ids):
            TypeAdapter(Sha256).validate_python(identity)
        if (
            not self.child_snapshot_ids
            or self.snapshot_id in self.child_snapshot_ids
            or tuple(sorted(set(self.child_snapshot_ids))) != self.child_snapshot_ids
            or self.references != _references(
                self.registration_id, self.snapshot_id, self.child_snapshot_ids
            )
        ):
            raise ValueError("Invalid scientific snapshot dependency registration")

    def require_current(self, store):
        """Reject missing retention bindings or withdrawals before serving work."""
        state = store.lifecycle()
        for reference, identity in self.references:
            entry = state["snapshots"].get(identity)
            if (
                state["references"].get(reference) != identity
                or entry is None
                or entry["retired"]
                or entry["revoked"]
            ):
                raise SnapshotAccessDenied("Catalogue registration unavailable")


def _references(registration_id, snapshot_id, children):
    return tuple(
        (
            "c14:dependency:"
            + hashlib.sha256(
                canonical_json([registration_id, snapshot_id, identity]).encode()
            ).hexdigest(),
            identity,
        )
        for identity in (snapshot_id, *children)
    )


def register_scientific_snapshot(*, store, snapshot_id, registration_id):
    """Pin one explicit index and its sealed children, idempotently.

If a later pin fails, earlier pins remain conservative retention references.
Retrying the same registration is safe. An operator reconciles any abandoned
partial registration; automatic rollback could release another in-flight retry's
protection. No public user can invoke registration or remove these references.
"""
    TypeAdapter(Identifier).validate_python(registration_id)
    TypeAdapter(Sha256).validate_python(snapshot_id)
    manifest, contents = store.read(snapshot_id)
    registry = load_registry(manifest, contents)
    children = tuple(sorted({item.snapshot_id for item in registry.metadata.datasets}))
    registration = ScientificCatalogueRegistration(
        snapshot_id=snapshot_id,
        child_snapshot_ids=children,
        references=_references(registration_id, snapshot_id, children),
        registration_id=registration_id,
    )
    # C09 verifies each exact manifest/content and current store access under its
    # reference transaction. A concurrently retired child cannot be resurrected.
    for reference, identity in registration.references:
        store.add_reference(identity, reference)
    registration.require_current(store)
    return registration
