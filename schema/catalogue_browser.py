"""C16 snapshot discovery wire contracts; authorization is server-owned."""
from __future__ import annotations

from typing import Literal

from pydantic import Field, field_validator, model_validator

from retrieval.source_scope import EvidenceScope
from schema.context_catalogue import (
    ContractModel, Identifier, LocalizedText, NonnegativeInt, PageLimit, Sha256,
    _strict_scope,
)


class CatalogueSnapshotDescriptor(ContractModel):
    snapshot_id: Sha256
    label: LocalizedText


class CatalogueSnapshotsRequest(ContractModel):
    schema_version: Literal["context-catalogue-v1"] = "context-catalogue-v1"
    scope: EvidenceScope
    limit: PageLimit = 100
    cursor: str | None = Field(default=None, min_length=1, max_length=2048)

    @field_validator("scope", mode="before")
    @classmethod
    def strict_scope(cls, value):
        return _strict_scope(value)


class CatalogueSnapshotsResponse(ContractModel):
    version: Literal["catalogue-browser-v1"] = "catalogue-browser-v1"
    scope: EvidenceScope
    snapshots: list[CatalogueSnapshotDescriptor] = Field(max_length=500)
    latest_snapshot_id: Sha256 | None
    total: NonnegativeInt
    next_cursor: str | None = Field(default=None, min_length=1, max_length=2048)
    access_revision: Identifier

    @model_validator(mode="after")
    def coherent_inventory(self):
        identities = [item.snapshot_id for item in self.snapshots]
        if len(identities) != len(set(identities)) or len(identities) > self.total:
            raise ValueError("Snapshot pages require distinct permitted identities")
        if (self.latest_snapshot_id is None) != (self.total == 0):
            raise ValueError("Latest snapshot requires a nonempty eligible inventory")
        if self.next_cursor is not None and not self.snapshots:
            raise ValueError("An empty snapshot page cannot continue")
        return self
