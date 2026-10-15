"""Injected, bounded PostgreSQL capture for the independent v1 snapshot store.

Exporters execute in a read-only REPEATABLE READ transaction. After it closes,
the coordinator locks its dedicated generation table in SHARE mode, rechecks the
complete head set in READ COMMITTED, and retains that lock through local sealing
and pointer publication. Every source writer must update these heads in the same
transaction as its data. The lock blocks insertion/deletion as well as updates.
This is a protected publication interval, not a database/filesystem transaction.
"""
from __future__ import annotations

import math
import time
from dataclasses import dataclass
from types import MappingProxyType
from typing import Callable, Mapping

from sqlalchemy import Table, select, text

from ingestion.catalogue_snapshot import SnapshotCommitUncertain
from retrieval.source_scope import EvidenceScope
from schema.catalogue_snapshot import MAX_BYTES, MAX_OBJECTS, SnapshotManifest, SnapshotObject, SourceCapture
from schema.context_catalogue import Identifier, SourceFamily, TextValue
from pydantic import TypeAdapter


SOURCE_FAMILIES = frozenset({"ctd", "metagenome", "remote_sensing", "edna_metabarcoding"})
REGISTRY_HEADS = frozenset({"publication", "classification", "relationship", "operation"})
_identifier = TypeAdapter(Identifier)
_text = TypeAdapter(TextValue)


class CaptureError(ValueError):
    """Capture failed before a confirmed local publication."""


class CaptureRollover(CaptureError):
    """The source or registry changed between export and publication."""


class CapturePublicationUncertain(RuntimeError):
    """Local CAS or the subsequent DB release has an unconfirmed outcome.

    Publication may already have succeeded. Callers must inspect this proposed
    snapshot/pointer before retrying. We do not attempt compensating pointer writes.
    """

    def __init__(self, snapshot_id: str, pointer_generation: int):
        self.snapshot_id = snapshot_id
        self.pointer_generation = pointer_generation
        super().__init__("Local publication outcome is uncertain; inspect the proposed snapshot/pointer before retrying")


@dataclass(frozen=True)
class CaptureHeads:
    values: Mapping[str, str]

    def __post_init__(self):
        frozen = dict(self.values)
        for name, generation in frozen.items():
            _identifier.validate_python(name)
            _text.validate_python(generation)
        object.__setattr__(self, "values", MappingProxyType(frozen))

    def source_generation(self, source_id: str) -> str:
        return self.values[f"source:{source_id}"]


@dataclass(frozen=True)
class CaptureBudget:
    max_seconds: float = 30.0
    max_bytes: int = 64 * 1024 * 1024
    max_objects: int = MAX_OBJECTS
    max_attempts: int = 2

    def __post_init__(self):
        if type(self.max_seconds) not in (int, float) or not math.isfinite(self.max_seconds) or not 0 < self.max_seconds <= 300:
            raise CaptureError("Capture duration must be positive and at most 300 seconds")
        if any(type(value) is not int or value <= 0 for value in (
            self.max_bytes, self.max_objects, self.max_attempts,
        )) or self.max_attempts > 10 or self.max_objects > MAX_OBJECTS or self.max_bytes > MAX_BYTES:
            raise CaptureError("Capture limits must be positive integers; attempts at most ten")


@dataclass(frozen=True)
class CapturedSource:
    objects: tuple[SnapshotObject, ...]
    contents: Mapping[str, bytes]

    def __post_init__(self):
        object.__setattr__(self, "objects", tuple(
            SnapshotObject.model_validate(item.model_dump(mode="json")) for item in self.objects
        ))
        object.__setattr__(self, "contents", MappingProxyType(dict(self.contents)))


@dataclass(frozen=True)
class SourceExportRequirement:
    """Source-owned frozen registration; no application/config DB discovery.

    A role maps to its schema and operation versions. All registered roles must
    occur in the output, including canonical_rows and classifications for eDNA.
    Exporters must honor the supplied monotonic deadline for non-SQL work; SQL
    statements are independently bounded by the transaction timeout.
    """

    source_id: str
    source_family: SourceFamily
    schema_versions: Mapping[str, str]
    operation_versions: Mapping[str, str]
    exporter: Callable[[object, CaptureHeads, float], CapturedSource]
    capture_method: str = "postgresql-repeatable-read-v1"
    qualifiers: tuple[str, ...] = ()
    operation_ids: Mapping[str, str] | None = None

    def __post_init__(self):
        _identifier.validate_python(self.source_id)
        if self.source_family not in SOURCE_FAMILIES:
            raise CaptureError("Unknown source family")
        schemas, operations = dict(self.schema_versions), dict(self.operation_versions)
        operation_ids = dict(self.operation_ids) if self.operation_ids is not None else {
            role: f"{self.source_id}:{role}" for role in schemas
        }
        if not schemas or schemas.keys() != operations.keys():
            raise CaptureError("Each export role requires schema and operation versions")
        if operation_ids.keys() != schemas.keys():
            raise CaptureError("Each export role requires an operation identity")
        for role, version in schemas.items():
            _identifier.validate_python(role)
            _text.validate_python(version)
            _text.validate_python(operations[role])
            _identifier.validate_python(operation_ids[role])
        if self.source_family == "edna_metabarcoding" and not {
            "canonical_rows", "classifications",
        } <= schemas.keys():
            raise CaptureError("eDNA requires canonical_rows and classifications exports")
        if not callable(self.exporter):
            raise CaptureError("A source-owned exporter callback is required")
        _text.validate_python(self.capture_method)
        for qualifier in self.qualifiers:
            _text.validate_python(qualifier)
        object.__setattr__(self, "schema_versions", MappingProxyType(schemas))
        object.__setattr__(self, "operation_versions", MappingProxyType(operations))
        object.__setattr__(self, "operation_ids", MappingProxyType(operation_ids))
        object.__setattr__(self, "qualifiers", tuple(self.qualifiers))


@dataclass(frozen=True)
class SourceExportRegistry:
    requirements: tuple[SourceExportRequirement, ...]

    def __post_init__(self):
        registrations = tuple(sorted(self.requirements, key=lambda item: item.source_id))
        if len({item.source_id for item in registrations}) != len(registrations):
            raise CaptureError("Source registrations must have unique identities")
        if {item.source_family for item in registrations} != SOURCE_FAMILIES:
            raise CaptureError("Capture registration must cover all four source families")
        versions = {}
        for requirement in registrations:
            for role, identity in requirement.operation_ids.items():
                if identity in versions and versions[identity] != requirement.operation_versions[role]:
                    raise CaptureError("Conflicting registered operation versions")
                versions[identity] = requirement.operation_versions[role]
        object.__setattr__(self, "requirements", registrations)

    @property
    def required_heads(self) -> frozenset[str]:
        return REGISTRY_HEADS | frozenset(
            f"source:{item.source_id}" for item in self.requirements
        )


class TableHeadCoordinator:
    """Use a caller-injected dedicated v1 table; never look up DATABASE_URL.

    Table rows must name generations in ``name`` and ``generation`` columns.
    Capture compares the complete set, so new rows cannot escape reconciliation.
    Source publishers update this table in their data-changing transaction.
    """

    def __init__(self, table: Table):
        if not {"name", "generation"} <= set(table.c.keys()):
            raise CaptureError("Generation table requires name and generation columns")
        self.table = table

    def read(self, connection, required_heads: frozenset[str]) -> CaptureHeads:
        rows = connection.execute(select(self.table.c.name, self.table.c.generation)).all()
        values = dict(rows)
        if len(values) != len(rows) or not required_heads <= values.keys():
            raise CaptureError("Generation rows must be complete and unique")
        return CaptureHeads(values)

    def lock(self, connection, required_heads: frozenset[str]) -> CaptureHeads:
        qualified = connection.dialect.identifier_preparer.format_table(self.table)
        connection.execute(text(f"LOCK TABLE {qualified} IN SHARE MODE"))
        return self.read(connection, required_heads)


@dataclass(frozen=True)
class CaptureResult:
    snapshot_id: str
    pointer_generation: int
    attempts: int
    exported_bytes: int
    heads: CaptureHeads


def _remaining_ms(deadline: float) -> int:
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise CaptureError("Capture time budget exhausted")
    return max(1, int(remaining * 1000))


def _bound_transaction(connection, deadline: float):
    milliseconds = str(_remaining_ms(deadline))
    for setting in ("statement_timeout", "lock_timeout", "idle_in_transaction_session_timeout"):
        connection.execute(text("SELECT set_config(:setting, :milliseconds, true)"), {
            "setting": setting, "milliseconds": milliseconds,
        })


def _export(connection, registry, heads, scope, deadline, budget):
    objects, contents, sources, operation_versions = [], {}, [], {}
    byte_count = 0
    for requirement in registry.requirements:
        if not getattr(scope.sources, requirement.source_family).enabled:
            continue
        _bound_transaction(connection, deadline)
        exported = requirement.exporter(connection, heads, deadline)
        _remaining_ms(deadline)
        if not isinstance(exported, CapturedSource):
            raise CaptureError("Exporter must return CapturedSource")
        object_ids = [item.object_id for item in exported.objects]
        if len(set(object_ids)) != len(object_ids) or set(object_ids) != exported.contents.keys():
            raise CaptureError("Export descriptors and content keys must match exactly")
        if set(contents) & set(exported.contents):
            raise CaptureError("Object identities must be unique across sources")
        roles = set()
        for item in exported.objects:
            if (item.source_id, item.source_family) != (
                requirement.source_id, requirement.source_family,
            ):
                raise CaptureError("Export object does not match its source registration")
            if item.role not in requirement.schema_versions or (
                item.schema_version != requirement.schema_versions[item.role]
                or item.operation_version != requirement.operation_versions[item.role]
                or item.operation_id != requirement.operation_ids[item.role]
            ):
                raise CaptureError("Export role/schema/operation differs from frozen registration")
            payload = exported.contents[item.object_id]
            if not isinstance(payload, bytes):
                raise CaptureError("Export contents must be frozen bytes")
            roles.add(item.role)
            byte_count += len(payload)
        if roles != requirement.schema_versions.keys():
            raise CaptureError("Required source export roles are incomplete")
        # A callback may retain its CapturedSource. Detach validated descriptors
        # before invoking the next source, just as immutable bytes are detached
        # from any source-owned row buffers.
        objects.extend(
            SnapshotObject.model_validate(item.model_dump(mode="json"))
            for item in exported.objects
        )
        contents.update(exported.contents)
        if byte_count > budget.max_bytes or len(objects) > budget.max_objects:
            raise CaptureError("Capture byte/object budget exhausted")
        sources.append(SourceCapture(
            source_id=requirement.source_id, source_family=requirement.source_family,
            source_generation=heads.source_generation(requirement.source_id),
            publication_generation=heads.values["publication"],
            classification_generation=heads.values["classification"],
            relationship_generation=heads.values["relationship"],
            operation_generation=heads.values["operation"],
            capture_method=requirement.capture_method, qualifiers=list(requirement.qualifiers),
        ))
        operation_versions.update({
            requirement.operation_ids[role]: version
            for role, version in requirement.operation_versions.items()
        })
    manifest = SnapshotManifest(
        scope=scope, source_captures=sources, objects=objects,
        operation_versions=operation_versions,
    )
    return manifest, contents, byte_count


def capture_snapshot(*, engine, registry: SourceExportRegistry, coordinator: TableHeadCoordinator,
                     store, scope: EvidenceScope, expected_latest_generation: int,
                     budget: CaptureBudget = CaptureBudget()) -> CaptureResult:
    """Capture and conditionally publish without model/embedding dependencies.

    Engine, registry, generation table, store and expected pointer are explicit.
    A competing pointer publication fails its CAS instead of being overwritten.
    Only head rollover is retried; failed exports never reach seal or promote.
    """
    if engine.dialect.name != "postgresql":
        raise CaptureError("Consistent source capture requires explicit PostgreSQL engine")
    if type(expected_latest_generation) is not int or expected_latest_generation < 0:
        raise CaptureError("Expected latest generation must be a nonnegative integer")
    scope = EvidenceScope.model_validate(scope.model_dump(mode="json"))
    if any(
        getattr(scope.sources, family).filters.model_dump(exclude_none=True)
        or getattr(getattr(scope.sources, family), "analysis_id", None) is not None
        for family in SOURCE_FAMILIES
    ):
        raise CaptureError("C09 captures whole registered sources; scoped row filtering belongs to adapters")
    if not any(getattr(scope.sources, family).enabled for family in SOURCE_FAMILIES):
        raise CaptureError("Capture requires at least one enabled source family")
    deadline = time.monotonic() + budget.max_seconds
    for attempt in range(1, budget.max_attempts + 1):
        _remaining_ms(deadline)
        with engine.connect().execution_options(isolation_level="REPEATABLE READ") as connection:
            with connection.begin():
                connection.execute(text("SET TRANSACTION READ ONLY"))
                _bound_transaction(connection, deadline)
                heads = coordinator.read(connection, registry.required_heads)
                manifest, contents, byte_count = _export(
                    connection, registry, heads, scope, deadline, budget,
                )
        published = None
        try:
            with engine.connect().execution_options(isolation_level="READ COMMITTED") as connection:
                with connection.begin():
                    _bound_transaction(connection, deadline)
                    current = coordinator.lock(connection, registry.required_heads)
                    if current != heads:
                        raise CaptureRollover("Source/registry heads changed during capture")
                    _remaining_ms(deadline)
                    snapshot_id = store.seal(manifest, contents)

                    def validate_capture():
                        _remaining_ms(deadline)
                        if coordinator.read(connection, registry.required_heads) != heads:
                            raise CaptureRollover("Source/registry heads changed before publication")

                    generation = store.promote(
                        snapshot_id, expected_generation=expected_latest_generation,
                        validate_capture=validate_capture,
                    )
                    published = (snapshot_id, generation)
            return CaptureResult(snapshot_id, generation, attempt, byte_count, heads)
        except CaptureRollover:
            if attempt == budget.max_attempts:
                raise
        except SnapshotCommitUncertain as exc:
            if exc.action == "promote":
                raise CapturePublicationUncertain(
                    exc.details["snapshot_id"], exc.proposed_latest_generation,
                ) from exc
            # Uncertain sealing can leave a registered immutable bundle but
            # cannot itself change latest. Preserve its typed reconciliation
            # details instead of claiming a clean filesystem rollback.
            raise
        except Exception as exc:
            if published is not None:
                raise CapturePublicationUncertain(*published) from exc
            raise
    raise AssertionError("Unreachable capture retry state")
