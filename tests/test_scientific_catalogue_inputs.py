"""C13 frozen byte ownership, resource bounds and C02 eligibility acceptance."""

import copy
import hashlib
import time

import pytest

from ingestion import scientific_catalogue_inputs as inputs
from ingestion.catalogue_snapshot import LocalCatalogueSnapshotStore
from ingestion.catalogue_snapshot_capture import CaptureHeads
from ingestion.immutable_bundle import canonical_bytes, digest
from preprocessing import derived_artifacts
from schema.scientific_catalogue import ScientificRegistry
from schema.scientific_catalogue_fixtures import (
    scientific_fixture,
    seal_scientific_fixture,
)


def frozen(tmp_path, *, count=3, metadata=None, tables=None):
    if metadata is None:
        metadata, tables = scientific_fixture(count)
    store = LocalCatalogueSnapshotStore(
        root=tmp_path.resolve(), access_gate=lambda m: True
    )
    identity = seal_scientific_fixture(store, metadata, tables)
    manifest, contents = store.read(identity)
    return manifest, dict(contents)


@pytest.mark.parametrize(
    "alias",
    sorted(
        set(derived_artifacts.TYPE_METHODS)
        | set(derived_artifacts.FILE_METHODS)
        | set(derived_artifacts.ID_METHODS)
    ),
)
def test_known_legacy_method_aliases_keep_c02_unversioned_gate(tmp_path, alias):
    metadata, tables = scientific_fixture(1)
    metadata.analyses[0].method_id = alias
    manifest, contents = frozen(tmp_path, metadata=metadata, tables=tables)
    eligibility = inputs.load_registry(manifest, contents).eligibility[
        metadata.analyses[0].id
    ]
    assert not eligibility.eligible
    assert eligibility.status == "legacy_unversioned"
    assert not eligibility.scientific_approval


@pytest.mark.parametrize(
    "alias",
    [
        "cross_source_validation",
        "correlation",
        "analysis_taxa_env_correlations",
        "sst_ctd_validation.parquet",
    ],
)
def test_known_legacy_labels_can_retain_a_valid_canonical_receipt(tmp_path, alias):
    metadata, tables = scientific_fixture(1)
    analysis = metadata.analyses[0]
    method = (
        derived_artifacts.ID_METHODS.get(alias)
        or derived_artifacts.TYPE_METHODS.get(alias)
        or derived_artifacts.FILE_METHODS[alias]
    )
    version = derived_artifacts.CURRENT_METHODS[method]
    receipt = derived_artifacts.make_receipt(
        method,
        digest({table.name: tables[table.object_id] for table in analysis.tables}),
        {
            "inputs": {
                binding.dataset_id: binding.snapshot_id for binding in metadata.datasets
            },
            "method_version": version,
            "status": "computed",
        },
    )
    receipt.update(
        eligibility="eligible",
        review={
            "reviewer": "synthetic C13 fixture reviewer",
            "rationale": "Bound synthetic eligibility acceptance",
            "references": ["Synthetic fixture only"],
            "evidence_sha256": receipt["generation_sha256"],
        },
    )
    analysis.method_id, analysis.method_version, analysis.derived_receipt = (
        alias,
        version,
        receipt,
    )
    manifest, contents = frozen(tmp_path, metadata=metadata, tables=tables)
    eligibility = inputs.load_registry(manifest, contents).eligibility[analysis.id]
    assert eligibility.eligible and eligibility.status == "eligible"
    assert not eligibility.scientific_approval


def test_legacy_alias_is_history_and_cannot_join_global_published_findings(tmp_path):
    from tests.test_scientific_catalogue_adversarial import build, listing, ANALYSIS

    def configure(metadata, tables):
        metadata.analyses[0].method_id = "cross_source_validation"

    _, snapshot, adapter, _, _, _, _ = build(tmp_path, configure=configure)
    nodes = adapter.list(listing(snapshot)).items
    assert ANALYSIS not in {node.id for node in nodes}
    histories = [
        node
        for node in nodes
        if node.root == "metadata" and node.title.en == "Published synthetic finding"
    ]
    assert len(histories) == 1
    assert (
        adapter.inspect(histories[0].id, listing(snapshot))["eligibility"]["status"]
        == "legacy_unversioned"
    )


def test_roundtrip_retains_full_rows_and_transport_is_not_raw_measurement(tmp_path):
    manifest, contents = frozen(tmp_path, count=1205)
    data = inputs.load_registry(manifest, contents)
    analysis = data.metadata.analyses[0]
    rows = data.tables[analysis.tables[0].object_id]
    assert len(rows) == 1205
    assert rows[0]["value"] == 0.0
    assert rows[-1]["result_id"] == "result:0001204"
    assert rows[0]["missing"] is None
    assert "storage carrier only" in data.metadata.qualification
    assert data.eligibility[analysis.id].eligible
    assert not data.eligibility[analysis.id].scientific_approval


@pytest.mark.parametrize(
    "payload",
    [
        b'{"datasets":[],"datasets":[]}',
        b'{"x":NaN}',
        b'{"x":Infinity}',
        b"[]",
        b"{}",
        b"\xff",
    ],
)
def test_metadata_rejects_invalid_or_ambiguous_json(payload):
    with pytest.raises(ValueError):
        inputs.registry_metadata(payload)


@pytest.mark.parametrize(
    "payload", [b"[1]", b"{}", b'[{"a":1,"a":2}]', b'[{"value":NaN}]', b"[[[]]]"]
)
def test_table_rejects_wrong_columns_shapes_and_nonfinite(payload):
    registry, _ = scientific_fixture(1)
    with pytest.raises(ValueError):
        inputs.parse_table(registry.analyses[0].tables[0], payload)


@pytest.mark.parametrize(
    "mutation",
    [
        "missing",
        "extra",
        "bytes",
        "hash",
        "size",
        "role",
        "schema",
        "operation",
        "owner",
    ],
)
def test_loader_rejects_ownership_or_byte_substitution_before_rows(tmp_path, mutation):
    manifest, contents = frozen(tmp_path)
    table = manifest.objects[1]
    if mutation == "missing":
        contents.pop(table.object_id)
    elif mutation == "extra":
        contents["other"] = b"[]"
    elif mutation == "bytes":
        contents[table.object_id] += b" "
    elif mutation == "hash":
        table.sha256 = "f" * 64
        table.provenance.content_sha256 = "f" * 64
    elif mutation == "size":
        table.size_bytes += 1
    elif mutation == "role":
        table.role = "canonical_rows"
    elif mutation == "schema":
        table.schema_version = "other-v1"
    elif mutation == "operation":
        table.operation_id = "other:operation"
        manifest.operation_versions["other:operation"] = table.operation_version
    else:
        table.dataset_id = "other:dataset"
    with pytest.raises(ValueError):
        inputs.load_registry(manifest, contents)


@pytest.mark.parametrize(
    "change", ["duplicate_id", "missing_column", "extra_column", "wrong_count"]
)
def test_export_validates_complete_result_table_contract(change):
    registry, tables = scientific_fixture(3)
    rows = next(iter(tables.values()))
    if change == "duplicate_id":
        rows[1]["result_id"] = rows[0]["result_id"]
    elif change == "missing_column":
        rows[0].pop("missing")
    elif change == "extra_column":
        rows[0]["extra"] = False
    else:
        rows.pop()
    with pytest.raises(ValueError):
        inputs.registry_exports(registry, tables, generation="generation-1")


@pytest.mark.parametrize(
    "bound",
    [
        "MAX_ROWS",
        "MAX_TABLE_BYTES",
        "MAX_DECODED_BYTES",
        "MAX_MANIFEST_BYTES",
        "MAX_BYTES",
        "MAX_OBJECTS",
    ],
)
def test_export_resource_limits_fail_closed(monkeypatch, bound):
    registry, tables = scientific_fixture(3)
    monkeypatch.setattr(inputs, bound, 1)
    with pytest.raises(ValueError):
        inputs.registry_exports(registry, tables, generation="generation-1")


def derived_registry(*, reviewed=False):
    registry, tables = scientific_fixture(3)
    analysis = registry.analyses[0]
    analysis.method_id = "taxa_env_correlation"
    analysis.method_version = derived_artifacts.CURRENT_METHODS[analysis.method_id]
    operation = {
        "status": "computed",
        "inputs": {d.dataset_id: d.snapshot_id for d in registry.datasets},
        "parameters": {"regeneration_id": "synthetic-frozen-generation"},
    }
    analysis.derived_receipt = derived_artifacts.make_receipt(
        "taxa_env_correlation",
        digest({"results": next(iter(tables.values()))}),
        operation,
    )
    if reviewed:
        analysis.derived_receipt.update(
            eligibility="eligible",
            review={
                "reviewer": "Synthetic researcher",
                "rationale": "Synthetic fixture eligibility review",
                "references": ["Synthetic C13 receipt"],
                "evidence_sha256": analysis.derived_receipt["generation_sha256"],
            },
        )
    return registry, tables


@pytest.mark.parametrize(
    "reviewed,status,eligible",
    [(False, "review_required", False), (True, "eligible", True)],
)
def test_frozen_derived_eligibility_requires_bound_review_without_config_reads(
    tmp_path, monkeypatch, reviewed, status, eligible
):
    registry, tables = derived_registry(reviewed=reviewed)
    monkeypatch.setattr(
        derived_artifacts,
        "_superseded_generations",
        lambda: pytest.fail("Frozen validator read configured tombstones"),
    )
    manifest, contents = frozen(tmp_path, metadata=registry, tables=tables)
    result = inputs.load_registry(manifest, contents).eligibility[
        registry.analyses[0].id
    ]
    assert result.status == status
    assert result.eligible is eligible
    assert result.scientific_approval is False


@pytest.mark.parametrize(
    "mutation,status",
    [
        ("output", "hash_mismatch"),
        ("input", "stale_inputs"),
        ("review", "review_mismatch"),
        ("tombstone", "superseded"),
        ("invalidated", "invalidated"),
        ("superseded", "superseded"),
        ("method", "legacy_method"),
        ("missing", "legacy_unversioned"),
        ("receipt_method", "method_mismatch"),
        ("unavailable", "unavailable"),
    ],
)
def test_changed_or_historical_derived_evidence_never_becomes_current(
    tmp_path, mutation, status
):
    registry, tables = derived_registry(reviewed=True)
    receipt = registry.analyses[0].derived_receipt
    if mutation == "output":
        next(iter(tables.values()))[0]["value"] = 999.0
    elif mutation == "input":
        registry.datasets[0].snapshot_id = "f" * 64
    elif mutation == "review":
        receipt["review"]["evidence_sha256"] = "f" * 64
    elif mutation == "tombstone":
        registry.superseded_generations = [receipt["generation_sha256"]]
    elif mutation in {"invalidated", "superseded"}:
        receipt["eligibility"] = mutation
    elif mutation == "method":
        receipt["method_version"] = "legacy-v0"
        registry.analyses[0].method_version = "legacy-v0"
    elif mutation == "missing":
        registry.analyses[0].derived_receipt = None
    elif mutation == "receipt_method":
        receipt["method_id"] = "corroboration"
    else:
        receipt["operation_status"] = "unavailable"
        receipt["generation_sha256"] = derived_artifacts._generation(receipt)
    manifest, contents = frozen(tmp_path, metadata=registry, tables=tables)
    result = inputs.load_registry(manifest, contents).eligibility[
        registry.analyses[0].id
    ]
    assert not result.eligible
    assert result.status == status


@pytest.mark.parametrize(
    "method",
    [
        "gap_interpolation",
        "unknown_reliability",
        "unknown_analysis",
        "taxa_env_correlation",
        "sst_ctd_validation",
        "corroboration",
        "diversity_prediction",
    ],
)
def test_affected_unversioned_methods_stay_ineligible(tmp_path, method):
    registry, tables = scientific_fixture(3)
    registry.analyses[0].method_id = method
    manifest, contents = frozen(tmp_path, metadata=registry, tables=tables)
    assert (
        not inputs.load_registry(manifest, contents)
        .eligibility[registry.analyses[0].id]
        .eligible
    )


def test_derived_analysis_declared_version_must_match_reviewed_receipt(tmp_path):
    registry, tables = derived_registry(reviewed=True)
    registry.analyses[0].method_version = "misleading-version"
    manifest, contents = frozen(tmp_path, metadata=registry, tables=tables)
    result = inputs.load_registry(manifest, contents).eligibility[
        registry.analyses[0].id
    ]
    assert result.eligible is False
    assert result.status == "method_version_mismatch"


def test_registration_detaches_supplied_rows_metadata_and_returns_new_descriptors():
    registry, tables = scientific_fixture(3)
    requirement = inputs.frozen_registry_requirement(
        registry, tables, source_generation="generation-1"
    )
    original = copy.deepcopy(tables)
    registry.analyses[0].title.en = "Mutated later"
    next(iter(tables.values()))[0]["value"] = 999.0
    heads = CaptureHeads({"source:scientific:registry": "generation-1"})
    first = requirement.exporter(None, heads, time.monotonic() + 5)
    second = requirement.exporter(None, heads, time.monotonic() + 5)
    assert first.objects[0] is not second.objects[0]
    table_id = next(iter(original))
    assert first.contents[table_id] == canonical_bytes(original[table_id])
    assert b"Mutated later" not in first.contents["scientific:registry"]


@pytest.mark.parametrize("deadline", [float("nan"), float("inf"), 0.0, True, "later"])
def test_exporter_rejects_expired_or_invalid_deadlines(deadline):
    registry, tables = scientific_fixture(3)
    requirement = inputs.frozen_registry_requirement(
        registry, tables, source_generation="generation-1"
    )
    with pytest.raises(ValueError):
        requirement.exporter(
            None, CaptureHeads({"source:scientific:registry": "generation-1"}), deadline
        )


def test_exporter_rejects_generation_rollover():
    registry, tables = scientific_fixture(3)
    requirement = inputs.frozen_registry_requirement(
        registry, tables, source_generation="generation-1"
    )
    with pytest.raises(ValueError, match="generation"):
        requirement.exporter(
            None,
            CaptureHeads({"source:scientific:registry": "generation-2"}),
            time.monotonic() + 5,
        )


@pytest.mark.parametrize("tombstones", [None, ["bad"], {"x": "a" * 64}])
def test_invalid_injected_tombstones_fail_closed(tombstones):
    registry, _ = derived_registry(reviewed=True)
    receipt = registry.analyses[0].derived_receipt
    result = derived_artifacts.receipt_eligibility(
        receipt, receipt["output_sha256"], superseded_generations=tombstones
    )
    assert result.status == "invalid_registry"


def test_legacy_receipt_consumer_keeps_configured_invalidation_behavior(monkeypatch):
    registry, _ = derived_registry(reviewed=True)
    receipt = registry.analyses[0].derived_receipt
    monkeypatch.setattr(
        derived_artifacts,
        "_superseded_generations",
        lambda: {receipt["generation_sha256"]},
    )
    result = derived_artifacts.receipt_eligibility(receipt, receipt["output_sha256"])
    assert result.status == "superseded"


def test_unknown_tables_are_absent_instead_of_fake_empty(tmp_path):
    registry, _ = scientific_fixture(3)
    raw = registry.model_dump(mode="json")
    raw["analyses"][0]["tables"][0].update(
        object_id=None,
        row_count=None,
        availability={
            "status": "unknown",
            "reason": "Retained manifest lacks exact table",
        },
        completeness="unknown",
    )
    registry = ScientificRegistry.model_validate(raw)
    manifest, contents = frozen(tmp_path, metadata=registry, tables={})
    data = inputs.load_registry(manifest, contents)
    assert not data.tables
    assert data.metadata.analyses[0].tables[0].row_count is None


def test_load_revalidates_mutated_registry_descriptor(tmp_path):
    manifest, contents = frozen(tmp_path)
    item = manifest.objects[0]
    item.provenance.content_sha256 = hashlib.sha256(b"different").hexdigest()
    with pytest.raises(ValueError):
        inputs.load_registry(manifest, contents)
