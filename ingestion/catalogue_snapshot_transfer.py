"""Synthetic/local approved-copy contracts and quarantine verification for C09.

All source bytes, destination identity, authorization and eligibility callbacks
are explicit. Origin metadata never opens a URL/path or grants access. This
module creates no source export, network client, legacy connection or latest
publication. Accepted imports seal a new independent manifest after validation.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import tempfile
from typing import Callable, Literal

from pydantic import Field, model_validator

from ingestion.artifact_store import BoundedLocalStore
from ingestion.catalogue_snapshot import LocalCatalogueSnapshotStore
from ingestion.immutable_bundle import canonical_bytes
from schema.catalogue_snapshot import (
    MAX_BYTES,
    MAX_OBJECTS,
    SnapshotManifest,
    SnapshotObject,
    manifest_id,
    manifest_bytes,
    validated_manifest,
)
from schema.context_catalogue import (
    ContractModel,
    Identifier,
    NonnegativeInt,
    Sha256,
    TextValue,
    TransferOrigin,
    _finite_json,
)

TRANSFER_VERSION = "catalogue-transfer-v1"
MAX_TRANSFER_MANIFEST_BYTES = 8 * 1024 * 1024


class TransferRejected(ValueError):
    """Copy did not pass the current destination/authorization/byte boundary."""


class TransferObject(ContractModel):
    object_id: Identifier
    encoding: Literal["json-rows-v1", "opaque-bytes-v1"]
    row_count: NonnegativeInt | None
    origin: TransferOrigin

    @model_validator(mode="after")
    def count_semantics(self):
        if (self.encoding == "json-rows-v1") != (self.row_count is not None):
            raise ValueError(
                "JSON rows require an exact count; opaque bytes have no invented row count"
            )
        return self


class TransferManifest(ContractModel):
    schema_version: Literal["catalogue-transfer-v1"] = TRANSFER_VERSION
    destination_id: Identifier
    authorization_ref: TextValue
    source_snapshot_id: Sha256
    snapshot: SnapshotManifest
    objects: list[TransferObject] = Field(min_length=1, max_length=MAX_OBJECTS)

    @model_validator(mode="after")
    def exact_bindings(self):
        if manifest_id(self.snapshot) != self.source_snapshot_id:
            raise ValueError("Transfer source manifest identity mismatch")
        if any(obj.provenance.origin is not None for obj in self.snapshot.objects):
            raise ValueError(
                "Chained copies require a future typed lineage contract; original origins cannot be overwritten"
            )
        source = {obj.object_id: obj for obj in self.snapshot.objects}
        if len({obj.object_id for obj in self.objects}) != len(self.objects) or {
            obj.object_id for obj in self.objects
        } != set(source):
            raise ValueError("Transfer objects must match the exact source manifest")
        for entry in self.objects:
            obj = source[entry.object_id]
            origin = entry.origin
            if (
                origin.origin_object_id != obj.object_id
                or origin.source_snapshot_id != self.source_snapshot_id
                or origin.source_generation != obj.provenance.source_generation
                or origin.content_sha256 != obj.sha256
                or origin.schema_version != obj.schema_version
                or origin.operation_version != obj.operation_version
                or origin.transfer_authorization_ref != self.authorization_ref
            ):
                raise ValueError(
                    "Transfer origin must retain exact object/hash/generation/schema/operation/authorization bindings"
                )
        return self


def transfer_manifest(value: TransferManifest | dict) -> TransferManifest:
    if isinstance(value, TransferManifest):
        value = value.model_dump(mode="json")
    result = TransferManifest.model_validate(value)
    if (
        len(canonical_bytes(result.model_dump(mode="json")))
        > MAX_TRANSFER_MANIFEST_BYTES
    ):
        raise TransferRejected("Transfer manifest byte limit exceeded")
    return result


def transfer_id(value: TransferManifest | dict) -> str:
    payload = transfer_manifest(value).model_dump(mode="json")
    payload["objects"].sort(key=lambda entry: entry["object_id"])
    payload["snapshot"] = json.loads(manifest_bytes(transfer_manifest(value).snapshot))
    return hashlib.sha256(canonical_bytes(payload)).hexdigest()


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise TransferRejected("Duplicate JSON key in exported rows")
        result[key] = value
    return result


def _rows(data: bytes) -> list[dict]:
    def reject_constant(value):
        raise TransferRejected("Nonfinite JSON constant in exported rows")

    try:
        value = json.loads(
            data.decode("utf-8"),
            object_pairs_hook=_unique_object,
            parse_constant=reject_constant,
        )
        if not isinstance(value, list) or any(
            not isinstance(row, dict) for row in value
        ):
            raise TransferRejected("Exported JSON rows must be an array of objects")
        _finite_json(value)
        return value
    except (UnicodeError, ValueError, RecursionError) as exc:
        raise TransferRejected("Invalid or ambiguous exported JSON rows") from exc


def _contents(
    snapshot: SnapshotManifest, supplied: dict[str, bytes]
) -> dict[str, bytes]:
    if not isinstance(supplied, dict) or set(supplied) != {
        obj.object_id for obj in snapshot.objects
    }:
        raise TransferRejected("Exact source object membership is required")
    total = 0
    result = {}
    for obj in snapshot.objects:
        data = supplied[obj.object_id]
        if (
            type(data) is not bytes
            or len(data) != obj.size_bytes
            or hashlib.sha256(data).hexdigest() != obj.sha256
        ):
            raise TransferRejected("Source object size/hash mismatch")
        total += len(data)
        if total > MAX_BYTES:
            raise TransferRejected("Transfer byte budget exceeded")
        result[obj.object_id] = data
    return result


def build_transfer(
    snapshot: SnapshotManifest | dict,
    supplied: dict[str, bytes],
    *,
    destination_id: str,
    authorization_ref: str,
    origin_system: str,
    qualifications: dict[str, tuple[str, str]],
    encodings: dict[str, Literal["json-rows-v1", "opaque-bytes-v1"]],
) -> TransferManifest:
    """Build a descriptive copy manifest; string references are not permissions."""
    snapshot = validated_manifest(snapshot)
    contents = _contents(snapshot, supplied)
    if set(qualifications) != set(contents) or set(encodings) != set(contents):
        raise TransferRejected(
            "Every object requires explicit scientific/access/encoding qualifications"
        )
    source_id = manifest_id(snapshot)
    objects = []
    for obj in snapshot.objects:
        scientific, conditions = qualifications[obj.object_id]
        encoding = encodings[obj.object_id]
        row_count = (
            len(_rows(contents[obj.object_id])) if encoding == "json-rows-v1" else None
        )
        objects.append(
            TransferObject(
                object_id=obj.object_id,
                encoding=encoding,
                row_count=row_count,
                origin=TransferOrigin(
                    origin_system=origin_system,
                    origin_object_id=obj.object_id,
                    source_snapshot_id=source_id,
                    source_generation=obj.provenance.source_generation,
                    schema_version=obj.schema_version,
                    operation_version=obj.operation_version,
                    content_sha256=obj.sha256,
                    scientific_qualification=scientific,
                    access_conditions=conditions,
                    transfer_authorization_ref=authorization_ref,
                    live_dependency=False,
                ),
            )
        )
    return transfer_manifest(TransferManifest(
        destination_id=destination_id,
        authorization_ref=authorization_ref,
        source_snapshot_id=source_id,
        snapshot=snapshot,
        objects=objects,
    ))


@dataclass(frozen=True)
class ImportedSnapshot:
    snapshot_id: str
    source_snapshot_id: str
    transfer_id: str
    object_count: int
    row_counts: tuple[tuple[str, int | None], ...]
    latest_promoted: bool = False


def import_quarantined(
    value: TransferManifest | dict,
    supplied: dict[str, bytes],
    *,
    destination_id: str,
    store: LocalCatalogueSnapshotStore,
    quarantine_root: Path,
    authorize: Callable[[TransferManifest], bool],
    eligible: Callable[[SnapshotObject, TransferOrigin], bool],
) -> ImportedSnapshot:
    """Validate/stage/recheck then seal; never publish or consult an origin store.

    Rejection cleans the temporary quarantine. A late local seal/read failure
    may leave verified immutable bytes/registration, but never advances latest.
    Trusted current callbacks, not authorization-reference text, decide access.
    """
    manifest = transfer_manifest(value)
    if not callable(authorize) or not callable(eligible):
        raise TransferRejected(
            "Trusted current authorization and eligibility gates are required"
        )
    if manifest.destination_id != destination_id:
        raise TransferRejected("Explicit independent destination mismatch")
    contents = _contents(manifest.snapshot, supplied)
    descriptors = {obj.object_id: obj for obj in manifest.snapshot.objects}
    entries = {entry.object_id: entry for entry in manifest.objects}

    def gates():
        if authorize(transfer_manifest(manifest)) is not True:
            raise TransferRejected("Current transfer authorization denied")
        for obj in manifest.snapshot.objects:
            # Defensive copies prevent a trusted adapter accidentally mutating
            # the frozen wire bindings between the check and sealed copy.
            if (
                eligible(
                    SnapshotObject.model_validate(obj.model_dump(mode="json")),
                    TransferOrigin.model_validate(
                        entries[obj.object_id].origin.model_dump(mode="json")
                    ),
                )
                is not True
            ):
                raise TransferRejected("Current object eligibility denied")

    gates()
    for key, entry in entries.items():
        if (
            entry.encoding == "json-rows-v1"
            and len(_rows(contents[key])) != entry.row_count
        ):
            raise TransferRejected("Transfer row count mismatch")
    quarantine_root = Path(quarantine_root)
    if not quarantine_root.is_absolute():
        raise TransferRejected("An explicit absolute local quarantine root is required")
    LocalCatalogueSnapshotStore._guard(quarantine_root)
    quarantine_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix="c09-copy-", dir=quarantine_root
    ) as temporary:
        directory = Path(temporary)
        local = BoundedLocalStore(directory)
        written = set()
        for obj in manifest.snapshot.objects:
            if obj.sha256 not in written:
                local.create(obj.sha256, contents[obj.object_id])
                written.add(obj.sha256)
        staged = {
            key: local.read(obj.sha256, max_bytes=obj.size_bytes).data
            for key, obj in descriptors.items()
        }
        _contents(manifest.snapshot, staged)
        imported = manifest.snapshot.model_dump(mode="json")
        for obj in imported["objects"]:
            obj["provenance"]["origin"] = entries[obj["object_id"]].origin.model_dump(
                mode="json"
            )
        imported = validated_manifest(imported)
        gates()
        if store.access_gate(validated_manifest(imported)) is not True:
            raise TransferRejected("Current destination access denied")
        identity = store.seal(imported, staged)
        store.read(identity)
    return ImportedSnapshot(
        identity,
        manifest.source_snapshot_id,
        transfer_id(manifest),
        len(manifest.objects),
        tuple(sorted((key, entry.row_count) for key, entry in entries.items())),
    )
