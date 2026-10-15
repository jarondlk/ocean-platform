"""Frozen registration and fail-closed source export coordination."""
from __future__ import annotations

import hashlib
import time
from dataclasses import replace

import pytest
from sqlalchemy import Column, MetaData, String, Table

from ingestion.catalogue_snapshot_capture import (
    CaptureBudget, CaptureError, CaptureHeads, CapturedSource,
    SourceExportRegistry, SourceExportRequirement, TableHeadCoordinator,
    _export, capture_snapshot,
)
from retrieval.source_scope import EvidenceScope
from schema.catalogue_snapshot import SnapshotObject
from schema.context_catalogue import Provenance


FAMILIES = ("ctd", "metagenome", "remote_sensing", "edna_metabarcoding")


def scope():
    return EvidenceScope.model_validate({"version": 1, "sources": {
        family: {"enabled": True, "filters": {}} for family in FAMILIES
    }})


def heads():
    return CaptureHeads({
        "publication": "p1", "classification": "c1", "relationship": "r1", "operation": "o1",
        **{f"source:{family}": "s1" for family in FAMILIES},
    })


def captured(family, captured_heads):
    roles = ("canonical_rows", "classifications") if family == "edna_metabarcoding" else ("rows",)
    objects, contents = [], {}
    for role in roles:
        payload = f'{family}:{role}:{captured_heads.source_generation(family)}'.encode()
        digest = hashlib.sha256(payload).hexdigest()
        identity = f"{family}:{role}"
        objects.append(SnapshotObject(
            object_id=identity, dataset_id=f"{family}:dataset", source_id=family,
            source_family=family, role=role, sha256=digest, size_bytes=len(payload),
            schema_version="rows-v1", operation_id=f"{family}:{role}", operation_version="export-v1",
            provenance=Provenance(content_sha256=digest, source_generation=captured_heads.source_generation(family)),
        ))
        contents[identity] = payload
    return CapturedSource(tuple(objects), contents)


def registry(exporter=None):
    registrations = []
    for family in FAMILIES:
        roles = ("canonical_rows", "classifications") if family == "edna_metabarcoding" else ("rows",)
        registrations.append(SourceExportRequirement(
            source_id=family, source_family=family,
            schema_versions={role: "rows-v1" for role in roles},
            operation_versions={role: "export-v1" for role in roles},
            exporter=exporter or (lambda connection, captured_heads, deadline, family=family: captured(family, captured_heads)),
        ))
    return SourceExportRegistry(tuple(registrations))


class Connection:
    def execute(self, *args, **kwargs):
        pass


def test_registration_freezes_caller_owned_maps_and_canonicalizes_source_order():
    schemas, operations = {"rows": "v1"}, {"rows": "op1"}
    requirement = SourceExportRequirement("ctd", "ctd", schemas, operations, lambda *args: None)
    schemas["rows"] = "changed"
    operations.clear()
    assert requirement.schema_versions == {"rows": "v1"}
    assert requirement.operation_versions == {"rows": "op1"}
    with pytest.raises(TypeError):
        requirement.schema_versions["rows"] = "changed"
    assert [item.source_id for item in registry().requirements] == sorted(FAMILIES)


@pytest.mark.parametrize("roles", [{"canonical_rows": "v1"}, {"classifications": "v1"}, {"rows": "v1"}])
def test_edna_requires_both_canonical_rows_and_classifications(roles):
    with pytest.raises(CaptureError, match="canonical_rows and classifications"):
        SourceExportRequirement("edna", "edna_metabarcoding", roles, roles, lambda *args: None)


def test_registry_requires_all_families_and_unique_sources():
    complete = registry().requirements
    with pytest.raises(CaptureError, match="all four"):
        SourceExportRegistry(complete[:-1])
    with pytest.raises(CaptureError, match="unique"):
        SourceExportRegistry(complete + (complete[0],))


def test_conflicting_shared_operation_identity_is_rejected():
    registrations = list(registry().requirements)
    registrations[0] = replace(registrations[0], operation_ids={"rows": "shared"})
    registrations[1] = replace(registrations[1], operation_ids={
        role: "shared" for role in registrations[1].schema_versions
    }, operation_versions={role: "conflicting" for role in registrations[1].schema_versions})
    with pytest.raises(CaptureError, match="Conflicting"):
        SourceExportRegistry(tuple(registrations))


@pytest.mark.parametrize("changes", [
    {"source_family": "unknown"}, {"schema_versions": {}}, {"operation_versions": {}},
    {"exporter": None}, {"qualifiers": ("",)}, {"source_id": "../../unsafe"},
])
def test_invalid_source_registrations_fail(changes):
    with pytest.raises(ValueError):
        replace(registry().requirements[0], **changes)


@pytest.mark.parametrize("changes", [
    {"max_seconds": 0}, {"max_seconds": 301}, {"max_seconds": float("inf")},
    {"max_bytes": 0}, {"max_objects": -1}, {"max_attempts": 11}, {"max_attempts": True},
])
def test_invalid_capture_budget_fails(changes):
    with pytest.raises(CaptureError):
        CaptureBudget(**changes)


def test_heads_are_copied_and_never_mutable():
    values = dict(heads().values)
    frozen = CaptureHeads(values)
    values["publication"] = "new"
    assert frozen.values["publication"] == "p1"
    with pytest.raises(TypeError):
        frozen.values["publication"] = "new"


def test_complete_exports_bind_every_registered_role_and_generation_without_embeddings():
    manifest, payloads, size = _export(Connection(), registry(), heads(), scope(), time.monotonic() + 30, CaptureBudget())
    assert len(manifest.objects) == 5
    assert size == sum(map(len, payloads.values()))
    assert {source.operation_generation for source in manifest.source_captures} == {"o1"}
    assert {source.classification_generation for source in manifest.source_captures} == {"c1"}
    assert {item.source_family for item in manifest.objects} == set(FAMILIES)
    assert "embedding" not in manifest.model_dump_json()


def test_full_registration_can_capture_only_scope_enabled_families():
    selected = scope()
    selected.sources.ctd.enabled = False
    manifest, payloads, _ = _export(Connection(), registry(), heads(), selected, time.monotonic() + 30, CaptureBudget())
    assert len(manifest.objects) == 4
    assert "ctd" not in {source.source_family for source in manifest.source_captures}
    assert not any(key.startswith("ctd:") for key in payloads)


def test_later_exporter_cannot_mutate_previously_validated_descriptors():
    retained = {}
    registrations = []
    for item in registry().requirements:
        def export(connection, captured_heads, deadline, family=item.source_family):
            if "ctd" in retained:
                retained["ctd"].objects[0].schema_version = "mutated-after-validation"
            result = captured(family, captured_heads)
            if family == "ctd":
                retained["ctd"] = result
            return result
        registrations.append(replace(item, exporter=export))
    manifest, _, _ = _export(Connection(), SourceExportRegistry(tuple(registrations)), heads(), scope(), time.monotonic() + 30, CaptureBudget())
    assert next(item for item in manifest.objects if item.source_family == "ctd").schema_version == "rows-v1"


@pytest.mark.parametrize("mode", ["wrong_type", "missing_content", "duplicate_object", "wrong_source", "wrong_version", "missing_role", "mutable_bytes"])
def test_export_failures_stop_before_manifest_seal(mode):
    def bad_export(connection, captured_heads, deadline):
        value = captured("ctd", captured_heads)
        if mode == "wrong_type":
            return None
        if mode == "missing_content":
            return CapturedSource(value.objects, {})
        if mode == "duplicate_object":
            return CapturedSource(value.objects * 2, value.contents)
        if mode == "wrong_source":
            return captured("metagenome", captured_heads)
        if mode == "wrong_version":
            return CapturedSource((value.objects[0].model_copy(update={"schema_version": "different"}),), value.contents)
        if mode == "missing_role":
            return CapturedSource((), {})
        return CapturedSource(value.objects, {key: bytearray(data) for key, data in value.contents.items()})
    with pytest.raises(CaptureError):
        _export(Connection(), registry(bad_export), heads(), scope(), time.monotonic() + 30, CaptureBudget())


@pytest.mark.parametrize("budget", [CaptureBudget(max_bytes=1), CaptureBudget(max_objects=1)])
def test_output_budget_is_enforced(budget):
    with pytest.raises(CaptureError, match="budget"):
        _export(Connection(), registry(), heads(), scope(), time.monotonic() + 30, budget)


def test_expired_export_deadline_fails():
    with pytest.raises(CaptureError, match="time budget"):
        _export(Connection(), registry(), heads(), scope(), time.monotonic() - 1, CaptureBudget())


def test_head_coordinator_rejects_missing_generation_columns():
    with pytest.raises(CaptureError, match="columns"):
        TableHeadCoordinator(Table("bad", MetaData(), Column("name", String)))


@pytest.mark.parametrize("rows", [[("publication", "p1")], [("publication", "p1"), ("publication", "p2")]])
def test_head_coordinator_rejects_missing_or_duplicate_heads(rows):
    class Rows:
        def all(self):
            return rows
    class Reader:
        def execute(self, statement):
            return Rows()
    coordinator = TableHeadCoordinator(Table("heads", MetaData(), Column("name", String), Column("generation", String)))
    with pytest.raises(CaptureError, match="complete and unique"):
        coordinator.read(Reader(), registry().required_heads)


def test_no_application_database_fallback_and_nonpostgres_engine_rejected(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://must-never-be-used/production")
    class Engine:
        class dialect:
            name = "sqlite"
    with pytest.raises(CaptureError, match="explicit PostgreSQL"):
        capture_snapshot(engine=Engine(), registry=registry(), coordinator=None, store=None,
                         scope=scope(), expected_latest_generation=0)


@pytest.mark.parametrize("selection", ["filter", "analysis", "empty"])
def test_scoped_or_empty_capture_rejected_before_database_connection(selection):
    class Engine:
        class dialect:
            name = "postgresql"
        def connect(self):
            raise AssertionError("Rejected scope must not connect to a database")
    selected = scope()
    if selection == "filter":
        selected.sources.ctd.filters.station = "station-1"
    elif selection == "analysis":
        selected.sources.edna_metabarcoding.analysis_id = "a" * 64
    else:
        for family in FAMILIES:
            getattr(selected.sources, family).enabled = False
    with pytest.raises(CaptureError, match="scoped row filtering|at least one"):
        capture_snapshot(engine=Engine(), registry=registry(), coordinator=None, store=None,
                         scope=selected, expected_latest_generation=0)
