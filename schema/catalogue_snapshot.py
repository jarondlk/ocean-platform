"""Sealed catalogue snapshot v1: exact bytes and reproducible source generations.

A snapshot ID is the SHA-256 of ``manifest_bytes``; it is deliberately not a
mutable publication ID or a filesystem generation. Embeddings are not inputs.
"""

from __future__ import annotations

import hashlib
from typing import Literal

from pydantic import Field, field_validator, model_validator

from ingestion.immutable_bundle import canonical_bytes
from retrieval.source_scope import EvidenceScope
from schema.context_catalogue import (
    ContractModel,
    Identifier,
    Provenance,
    Sha256,
    SourceFamily,
    TextValue,
    _strict_scope,
)

SCHEMA_VERSION = "catalogue-snapshot-v1"
# Artifact/shard bound, never an inventory row/dataset ceiling; reject, do not truncate.
MAX_OBJECTS = 4000
MAX_BYTES = 512 * 1024 * 1024
MAX_MANIFEST_BYTES = 4 * 1024 * 1024


class SourceCapture(ContractModel):
    source_id: Identifier
    source_family: SourceFamily
    source_generation: TextValue
    publication_generation: TextValue
    classification_generation: TextValue
    relationship_generation: TextValue
    operation_generation: TextValue
    capture_method: TextValue
    qualifiers: list[TextValue]


class SnapshotObject(ContractModel):
    object_id: Identifier
    dataset_id: Identifier
    source_id: Identifier
    source_family: SourceFamily
    role: Identifier
    sha256: Sha256
    size_bytes: int = Field(strict=True, ge=0, le=MAX_BYTES)
    schema_version: TextValue
    operation_id: Identifier
    operation_version: TextValue
    provenance: Provenance

    @model_validator(mode="after")
    def byte_provenance(self):
        if self.provenance.content_sha256 != self.sha256:
            raise ValueError("Object hash must match retained provenance")
        if (
            self.provenance.origin is not None
            and self.provenance.origin.content_sha256 != self.sha256
        ):
            raise ValueError("Exact copied origin hash must match snapshot bytes")
        return self


class SnapshotManifest(ContractModel):
    schema_version: Literal["catalogue-snapshot-v1"] = SCHEMA_VERSION
    scope: EvidenceScope
    source_captures: list[SourceCapture] = Field(min_length=1, max_length=MAX_OBJECTS)
    objects: list[SnapshotObject] = Field(min_length=1, max_length=MAX_OBJECTS)
    operation_versions: dict[Identifier, TextValue] = Field(min_length=1)

    @field_validator("scope", mode="before")
    @classmethod
    def strict_scope(cls, value):
        return _strict_scope(value)

    @model_validator(mode="after")
    def source_bindings(self):
        sources = {source.source_id: source for source in self.source_captures}
        if len(sources) != len(self.source_captures):
            raise ValueError("Duplicate source capture")
        for registry in (
            "classification_generation",
            "relationship_generation",
            "operation_generation",
        ):
            if len({getattr(source, registry) for source in self.source_captures}) != 1:
                raise ValueError("Snapshot contains mixed global registry generations")
        identities = [obj.object_id for obj in self.objects]
        if len(set(identities)) != len(identities):
            raise ValueError("Duplicate canonical object identity")
        if sum(obj.size_bytes for obj in self.objects) > MAX_BYTES:
            raise ValueError("Snapshot byte limit exceeded")
        used_sources = set()
        dataset_sources = {}
        for obj in self.objects:
            source = sources.get(obj.source_id)
            if source is None or source.source_family != obj.source_family:
                raise ValueError("Object source capture mismatch")
            if obj.provenance.source_generation != source.source_generation:
                raise ValueError("Object source generation mismatch")
            if self.operation_versions.get(obj.operation_id) != obj.operation_version:
                raise ValueError("Object operation version is not bound by manifest")
            if not getattr(self.scope.sources, obj.source_family).enabled:
                raise ValueError("Object family is disabled in snapshot scope")
            ownership = (obj.source_id, obj.source_family)
            if dataset_sources.setdefault(obj.dataset_id, ownership) != ownership:
                raise ValueError(
                    "Canonical dataset identity has conflicting source ownership"
                )
            used_sources.add(obj.source_id)
        if used_sources != set(sources):
            raise ValueError("A source capture must have an export object")
        for source in self.source_captures:
            if source.source_family != "edna_metabarcoding":
                continue
            datasets = {
                obj.dataset_id
                for obj in self.objects
                if obj.source_id == source.source_id
            }
            for dataset_id in datasets:
                roles = {
                    obj.role
                    for obj in self.objects
                    if obj.source_id == source.source_id
                    and obj.dataset_id == dataset_id
                }
                if not {"canonical_rows", "classifications"}.issubset(roles):
                    raise ValueError(
                        "Each eDNA export dataset requires canonical rows and classifications"
                    )
        return self


def validated_manifest(value: SnapshotManifest | dict) -> SnapshotManifest:
    """Copy and revalidate even previously validated but subsequently mutated models."""
    if isinstance(value, SnapshotManifest):
        value = value.model_dump(mode="json")
    return SnapshotManifest.model_validate(value)


def manifest_bytes(value: SnapshotManifest | dict) -> bytes:
    payload = validated_manifest(value).model_dump(mode="json")
    payload["objects"].sort(key=lambda item: item["object_id"])
    payload["source_captures"].sort(key=lambda item: item["source_id"])
    data = canonical_bytes(payload)
    if len(data) > MAX_MANIFEST_BYTES:
        raise ValueError("Snapshot manifest byte limit exceeded")
    return data


def manifest_id(value: SnapshotManifest | dict) -> str:
    return hashlib.sha256(manifest_bytes(value)).hexdigest()


def compare_snapshots(
    old: SnapshotManifest | dict, new: SnapshotManifest | dict
) -> dict:
    """Canonical export identities removed/replaced on explicit refresh.

    Export artifacts may contain many dataset rows. Adapters remain responsible
    for their row-level membership changes inside these immutable exports.
    """
    previous = {
        obj.object_id: obj.model_dump(mode="json")
        for obj in validated_manifest(old).objects
    }
    current = {
        obj.object_id: obj.model_dump(mode="json")
        for obj in validated_manifest(new).objects
    }
    return {
        "removed_object_ids": sorted(previous.keys() - current.keys()),
        "added_object_ids": sorted(current.keys() - previous.keys()),
        "replaced_object_ids": sorted(
            key
            for key in previous.keys() & current.keys()
            if previous[key] != current[key]
        ),
    }
