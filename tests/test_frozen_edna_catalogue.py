"""Independent full-population C12 acceptance over explicit frozen fixtures."""

import hashlib

import pytest

from ingestion.catalogue_snapshot import (
    LocalCatalogueSnapshotStore,
    SnapshotAccessDenied,
)
from ingestion.edna_catalogue_inputs import EDNAUnavailable
from orchestration.frozen_edna_catalogue import (
    AdapterAccessDenied,
    EDNAAccess,
    FrozenEDNACatalogueAdapter,
)
from schema.context_catalogue import CatalogueFilters, ListingRequest, OperationRequest
from schema.edna_catalogue_fixtures import edna_fixture, edna_scope, seal_edna_fixture

PROJECT = "synthetic:edna:project-a"
METHOD = "qcauto_target"
PROTOCOL = {
    "target_gene": "12S",
    "primer_set": "Synthetic-MiFish",
    "sequencing_method": "synthetic-amplicon-sequencing",
}


def listing(snapshot, **changes):
    return ListingRequest.model_validate(
        {
            "snapshot_id": snapshot,
            "scope": edna_scope().model_dump(mode="json"),
            "access_binding": "user-a",
            "access_revision": "revision-1",
            **changes,
        }
    )


def operation(snapshot, identity=PROJECT, op="c12.table", *, scope=None, **parameters):
    return OperationRequest(
        snapshot_id=snapshot,
        scope=scope or edna_scope(),
        operation_id=op,
        operation_version="c12-v1",
        input_ids=[identity],
        parameters=parameters,
        access_binding="user-a",
        access_revision="revision-1",
    )


def local(tmp_path, datasets=None, *, allowed=None):
    store = LocalCatalogueSnapshotStore(
        root=tmp_path.resolve(), access_gate=lambda manifest: True
    )
    sid = seal_edna_fixture(
        store, datasets if datasets is not None else [edna_fixture(10)]
    )
    policy = {"denied": set(), "eligible": True}

    def eligible(snapshot, metadata):
        return policy["eligible"] and metadata.dataset_id not in policy["denied"]

    adapter = FrozenEDNACatalogueAdapter(
        store=store, access=EDNAAccess("user-a", "revision-1", allowed or eligible)
    )
    return store, sid, adapter, policy


@pytest.fixture(scope="module")
def large(tmp_path_factory):
    return local(tmp_path_factory.mktemp("c12-large"), [edna_fixture(1205)])


@pytest.mark.parametrize("limit", [1, 25, 100, 500])
def test_preview_never_limits_complete_raw_occurrence_population(large, limit):
    _, sid, adapter, _ = large
    value = adapter.query(operation(sid, population="raw", limit=limit))
    reference = adapter.query(operation(sid, population="raw", limit=500))
    assert len(value.result.rows) == limit
    assert value.result.receipt.total_rows.value == 1204
    assert (
        value.result.receipt.content_sha256 == reference.result.receipt.content_sha256
    )
    assert value.result.receipt.preview_truncated
    assert value.next_offset == limit


def test_raw_pages_reach_all_active_occurrences_once_and_retain_control_unknown(large):
    _, sid, adapter, _ = large
    rows, offset = [], 0
    while True:
        result = adapter.query(
            operation(sid, population="raw", offset=offset, limit=500)
        )
        rows.extend(result.result.rows)
        if result.next_offset is None:
            break
        offset = result.next_offset
    assert len(rows) == len({row["sample_id"] for row in rows}) == 1204
    assert {row["sample_kind"] for row in rows} == {
        "environmental",
        "negative_control",
        "unknown",
    }
    assert (
        sum(
            row["sample_kind"] == "unknown" and row["is_control"] is None
            for row in rows
        )
        == 1
    )
    assert all(row["physical_sample_id"] is None for row in rows)
    assert all(
        row["temporal_precision"] == "date" and "T" not in row["collection_date_utc"]
        for row in rows
    )


@pytest.mark.parametrize(
    "table,expected",
    [
        ("occurrences", 1203),
        ("assays", 1203),
        ("detections", 1202),
        ("classifications", 1203),
    ],
)
def test_correlated_raw_method_tables_keep_available_empty_entities(
    large, table, expected
):
    _, sid, adapter, _ = large
    result = adapter.query(
        operation(
            sid,
            population="raw",
            table=table,
            filters={"assignment_method": METHOD},
            limit=1,
        )
    ).result
    assert result.receipt.total_rows.value == expected
    assert result.receipt.authority == "descriptive"
    assert result.receipt.operation_version == "c12-v1"


@pytest.mark.parametrize(
    "table,expected",
    [
        ("occurrences", 1200),
        ("assays", 1200),
        ("detections", 1199),
        ("classifications", 1200),
    ],
)
def test_scientific_cohort_uses_actual_classification_protocol_and_availability(
    large, table, expected
):
    _, sid, adapter, _ = large
    result = adapter.query(
        operation(
            sid,
            population="eligible",
            table=table,
            filters={"assignment_method": METHOD},
            limit=1,
        )
    ).result
    assert result.receipt.total_rows.value == expected
    assert result.receipt.total_rows.denominator
    assert result.receipt.authority == "descriptive"


@pytest.mark.parametrize("method", ["qcauto_nontarget", "qcauto_95pct_3nn_nontarget"])
def test_nontarget_raw_inventory_remains_queryable_without_scientific_execution(
    tmp_path, method
):
    _, sid, adapter, _ = local(tmp_path)
    raw = adapter.query(
        operation(
            sid,
            population="raw",
            table="detections",
            filters={"assignment_method": method},
        )
    ).result
    assert raw.rows and {row["assignment_method"] for row in raw.rows} == {method}
    scientific = adapter.query(
        operation(
            sid,
            population="eligible",
            table="detections",
            filters={"assignment_method": method},
        )
    ).result
    assert scientific.rows == []
    assert scientific.receipt.availability.status == "unavailable"
    assert scientific.receipt.total_rows.value is None
    assert scientific.receipt.availability.reason


@pytest.mark.parametrize("action", ["store-revoke", "current-gate", "dataset-policy"])
@pytest.mark.parametrize(
    "op", ["c12.table", "c12.count", "c12.summary", "c12.coverage"]
)
def test_current_access_overrides_previously_successful_archived_reads(
    tmp_path, action, op
):
    store, sid, adapter, policy = local(tmp_path)
    adapter.query(operation(sid, op=op, population="raw"))
    if action == "store-revoke":
        store.revoke(sid)
    elif action == "current-gate":
        store.access_gate = lambda manifest: False
    else:
        policy["denied"].add(PROJECT)
    with pytest.raises(
        AdapterAccessDenied if action == "dataset-policy" else SnapshotAccessDenied
    ):
        adapter.query(operation(sid, op=op, population="raw"))


@pytest.mark.parametrize(
    "field,value", [("access_binding", "other-user"), ("access_revision", "revision-2")]
)
def test_access_context_is_current_and_exact(tmp_path, field, value):
    _, sid, adapter, _ = local(tmp_path)
    with pytest.raises(AdapterAccessDenied):
        adapter.query(operation(sid).model_copy(update={field: value}))


def test_old_classifications_reopen_identically_after_new_review_generation(tmp_path):
    store, original, adapter, _ = local(tmp_path)
    before = adapter.query(operation(original, filters={"assignment_method": METHOD}))
    metadata, frames = edna_fixture(10)
    frames["classifications"].loc[2, ["sample_kind", "is_control"]] = [
        "environmental",
        False,
    ]
    frames["classifications"].loc[2, "classification_basis"] = (
        "new synthetic provider correction; no scientific approval"
    )
    newer = seal_edna_fixture(
        store,
        [(metadata, frames)],
        publication="publication-2",
        classification="classification-2",
    )
    assert newer != original
    reopened = FrozenEDNACatalogueAdapter(
        store=LocalCatalogueSnapshotStore(
            root=tmp_path.resolve(), access_gate=lambda manifest: True
        ),
        access=adapter.access,
    )
    assert (
        reopened.query(operation(original, filters={"assignment_method": METHOD}))
        == before
    )
    changed = reopened.query(
        operation(newer, filters={"assignment_method": METHOD})
    ).result
    assert (
        changed.receipt.total_rows.value == before.result.receipt.total_rows.value + 1
    )
    manifest, contents = store.read(original)
    assert (
        next(
            capture
            for capture in manifest.source_captures
            if capture.source_family == "edna_metabarcoding"
        ).classification_generation
        == "classification-1"
    )
    assert all(
        hashlib.sha256(contents[item.object_id]).hexdigest() == item.content_sha256
        for item in before.result.receipt.inputs
    )
    assert store.latest() == (None, 0)


@pytest.mark.parametrize("state", ["unknown", "unavailable"])
def test_absent_source_tables_remain_visible_without_false_zero(tmp_path, state):
    metadata, frames = edna_fixture(0)
    for table in metadata.tables:
        table.object_id = table.row_count = None
        table.availability.status = table.completeness = state
        table.availability.reason = "Canonical input bytes deliberately not supplied"
    frames.clear()
    _, sid, adapter, _ = local(tmp_path, [(metadata, frames)])
    assert adapter.dataset_count(listing(sid)).value == 1
    for op in ("c12.table", "c12.count", "c12.summary", "c12.coverage"):
        result = adapter.query(operation(sid, op=op, population="raw")).result
        assert result.rows == []
        assert result.receipt.total_rows.state == "unknown"
        assert result.receipt.total_rows.value is None
        assert result.receipt.availability.status == "unavailable"


def test_available_empty_source_is_queryable_known_zero_and_retrieval_independent(
    tmp_path, monkeypatch
):
    _, sid, adapter, _ = local(tmp_path, [edna_fixture(0)])
    monkeypatch.setenv("DATABASE_URL", "postgresql://forbidden/never")
    monkeypatch.setenv("MODEL_PROVIDER", "forbidden")
    result = adapter.query(operation(sid, population="raw")).result
    assert result.rows == [] and result.receipt.total_rows.value == 0
    assert result.receipt.availability.status == "available"
    node = adapter.open(PROJECT, listing(sid))
    assert node.lifecycle.query_readiness == "ready"
    assert node.lifecycle.scientific_approval == "not_reviewed"
    assert node.lifecycle.embedding_readiness in {"not_ready", "unknown"}


def test_corruption_after_success_fails_instead_of_using_cached_rows(tmp_path):
    store, sid, adapter, _ = local(tmp_path)
    adapter.query(operation(sid))
    manifest, _ = store.read(sid)
    artifact = next(obj for obj in manifest.objects if obj.role == "classifications")
    (tmp_path / "v1/catalogue/objects" / artifact.sha256).write_bytes(b"corrupt")
    with pytest.raises(ValueError, match="integrity|bound|size"):
        adapter.query(operation(sid))


def test_scoped_capture_cannot_be_mistaken_for_complete_canonical_source(tmp_path):
    store, sid, adapter, _ = local(tmp_path)
    manifest, contents = store.read(sid)
    manifest.scope = edna_scope(provider_project_id="ProjectA")
    subset = store.seal(manifest, contents)
    with pytest.raises(EDNAUnavailable, match="whole-source"):
        adapter.query(operation(subset))


@pytest.mark.parametrize(
    "parameters",
    [
        {"unexpected": True},
        {"population": "all"},
        {"table": "physical_samples"},
        {"limit": 0},
        {"limit": 501},
        {"offset": -1},
        {"limit": "5"},
        {"offset": True},
        {"filters": {"raw_sql": "select forbidden"}},
        {"filters": {"assignment_method": "unknown"}},
        {"filters": {"is_control": "false"}},
    ],
)
def test_query_parameters_reject_ambiguous_unbounded_or_invented_semantics(
    tmp_path, parameters
):
    _, sid, adapter, _ = local(tmp_path)
    with pytest.raises(ValueError):
        adapter.query(operation(sid, **parameters))


@pytest.mark.parametrize(
    "op", ["c12.count", "c12.summary", "c12.coverage", "c12.frequency"]
)
def test_aggregate_offsets_cannot_hide_complete_result_population(tmp_path, op):
    _, sid, adapter, _ = local(tmp_path)
    with pytest.raises(ValueError):
        adapter.query(operation(sid, op=op, offset=1))


def test_all_dataset_sections_and_source_owned_raw_descriptor_are_explicit(large):
    _, sid, adapter, _ = large
    inspected = adapter.inspect(PROJECT, listing(sid))
    assert set(inspected) == {
        "node",
        "overview",
        "tables",
        "coverage",
        "methods",
        "provenance",
        "related",
    }
    node = inspected["node"]
    assert node.descriptor.population == "raw_inventory"
    assert node.descriptor.assignment_method == node.descriptor.sample_kind == "mixed"
    assert len(inspected["tables"]) == 4
    assert node.lifecycle.scientific_approval == "not_reviewed"
    assert node.source_family == "edna_metabarcoding"


def test_late_provider_project_inventory_uses_all_datasets_and_current_access(tmp_path):
    datasets = [
        edna_fixture(
            0,
            dataset_id=f"synthetic:edna:project-{number:03d}",
            provider_project_id=f"Project{number:03d}",
        )
        for number in range(32)
    ]
    _, sid, adapter, policy = local(tmp_path, datasets)
    request = listing(sid, filters=CatalogueFilters(kinds=["dataset"]), limit=25)
    first = adapter.list(request)
    second = adapter.list(request.model_copy(update={"cursor": first.next_cursor}))
    assert (
        first.total.value
        == second.total.value
        == adapter.dataset_count(request).value
        == 32
    )
    assert len(first.items) == 25 and len(second.items) == 7
    assert second.items[-1].id == "synthetic:edna:project-031"
    policy["denied"].add("synthetic:edna:project-031")
    assert adapter.dataset_count(request).value == 31


def test_exact_counts_separate_raw_occurrences_assays_classifications_and_methods(
    large,
):
    _, sid, adapter, _ = large
    result = adapter.query(
        operation(sid, op="c12.count", population="raw", limit=1)
    ).result
    row = result.rows[0]
    assert row["population"] == "raw"
    assert row["source_occurrence_count"] == 1204
    assert row["assay_count"] == 1203
    assert row["physical_sample_count"] is None
    assert row["controls"] == row["unknown_control_status"] == 1
    assert row["denominator"] and row["eligibility_definition"]
    assert result.receipt.total_rows.value == 1
    methods = row["methods"]
    assert {item["assignment_method"] for item in methods} == {
        METHOD,
        "qcauto_95pct_3nn_target",
        "qcauto_nontarget",
        "qcauto_95pct_3nn_nontarget",
    }
    assert sum(item["assignment_rows"] for item in methods) == 4807
    assert len(
        {
            (
                item["assignment_method"],
                item["target_gene"],
                item["primer_set"],
                item["sequencing_method"],
            )
            for item in methods
        }
    ) == len(methods)


def test_summary_is_method_and_protocol_separated_with_zero_missing_and_absent_concentration(
    tmp_path,
):
    _, sid, adapter, _ = local(tmp_path)
    result = adapter.query(
        operation(
            sid,
            op="c12.summary",
            population="raw",
            filters={"assignment_method": METHOD},
        )
    ).result
    assert len(result.rows) == 3
    assert sum(row["assignment_rows"] for row in result.rows) == 7
    assert sum(row["read_count_sum"] for row in result.rows) == 32
    assert sum(row["concentration_reported"] for row in result.rows) == 2
    assert sum(row["concentration_missing"] for row in result.rows) == 2
    assert sum(row["concentration_column_absent"] for row in result.rows) == 3
    assert sum(row["concentration_zero"] for row in result.rows) == 1
    assert sum(row["available_empty_assays"] for row in result.rows) == 1
    assert all(
        row["assignment_method"] == METHOD and row["entity"] == "detection_rows"
        for row in result.rows
    )
    assert all("not organism abundance" in row["denominator"] for row in result.rows)


def test_coverage_retains_actual_precision_without_inventing_expected_calendar(
    tmp_path,
):
    _, sid, adapter, _ = local(tmp_path)
    row = adapter.query(
        operation(sid, op="c12.coverage", population="raw")
    ).result.rows[0]
    assert row["observed_occurrences"] == row["dated_occurrences"] == 9
    assert row["unknown_date_occurrences"] == 0
    assert row["temporal_precisions"] == {"date": 9}
    assert row["earliest_retained_label"] == "2024-01-01"
    assert row["latest_retained_label"] == "2024-01-10"
    assert row["expected_dates"] is row["missing_dates"] is None
    assert row["coverage_state"] == "unknown"


@pytest.mark.parametrize("unit", ["source_occurrences", "assays"])
def test_frequency_keeps_eligible_empty_and_zero_read_units_in_denominator(
    tmp_path, unit
):
    _, sid, adapter, _ = local(tmp_path)
    row = adapter.query(
        operation(
            sid,
            op="c12.frequency",
            filters={"assignment_method": METHOD, "taxon": "Scomber"},
            frequency_unit=unit,
            **PROTOCOL,
        )
    ).result.rows[0]
    # Eligible 12S units are indices 0,6,7,9. Index6 is an available empty
    # source table, index0 reports zero reads, and indices7/9 are positives.
    assert row["entity"] == unit
    assert row["eligible_denominator"] == 4
    assert row["positive_units"] == 2
    assert row["frequency"] == 0.5
    assert "taxon predicate removed" in row["denominator"]
    assert "read_count > 0" in row["denominator"]


def test_zero_read_assignment_and_unknown_species_do_not_become_positive_species_detection(
    tmp_path,
):
    _, sid, adapter, _ = local(tmp_path)
    row = adapter.query(
        operation(
            sid,
            op="c12.frequency",
            filters={"assignment_method": METHOD, "taxon": "Scomber japonicus"},
            **PROTOCOL,
        )
    ).result.rows[0]
    # i0's source-backed species assignment reports zero reads; odd indices
    # retain an unresolved species label and only resolve to genus.
    assert row["eligible_denominator"] == 4 and row["positive_units"] == 0
    assert row["frequency"] == 0


@pytest.mark.parametrize(
    "changes",
    [
        {"population": "raw"},
        {"target_gene": None},
        {"primer_set": None},
        {"sequencing_method": None},
        {"filters": {"assignment_method": METHOD}},
        {"filters": {"taxon": "Scomber"}},
        {"filters": {"assignment_method": "qcauto_nontarget", "taxon": "Scomber"}},
    ],
)
def test_frequency_requires_supported_method_taxon_and_one_complete_protocol(
    tmp_path, changes
):
    _, sid, adapter, _ = local(tmp_path)
    parameters = {
        **PROTOCOL,
        "filters": {"assignment_method": METHOD, "taxon": "Scomber"},
        **changes,
    }
    result = adapter.query(operation(sid, op="c12.frequency", **parameters)).result
    assert result.rows == [] and result.receipt.total_rows.value is None
    assert result.receipt.availability.status == "unavailable"


def test_pinned_scope_cannot_be_silently_broadened_or_overridden(tmp_path):
    _, sid, adapter, _ = local(tmp_path)
    scope = edna_scope(provider_project_id="AnotherProject")
    result = adapter.query(
        operation(
            sid,
            op="c12.count",
            scope=scope,
            population="raw",
            filters={"provider_project_id": "ProjectA"},
        )
    ).result
    assert result.rows == [] and result.receipt.availability.status == "unavailable"
    assert result.receipt.total_rows.value is None


def test_provider_project_mismatch_produces_known_zero_without_classification_attribute_errors(
    tmp_path,
):
    _, sid, adapter, _ = local(tmp_path)
    result = adapter.query(
        operation(
            sid,
            op="c12.count",
            scope=edna_scope(provider_project_id="AnotherProject"),
            population="raw",
        )
    ).result
    assert result.rows[0]["source_occurrence_count"] == 0
    assert result.rows[0]["assay_count"] == 0
    assert result.receipt.availability.status == "available"


def test_partial_relational_inputs_cannot_claim_exact_aggregate_counts(tmp_path):
    metadata, frames = edna_fixture(10)
    next(
        table for table in metadata.tables if table.name == "detections"
    ).completeness = "partial"
    _, sid, adapter, _ = local(tmp_path, [(metadata, frames)])
    table = adapter.query(operation(sid, population="raw")).result
    assert table.rows and table.receipt.query_completion == "partial"
    assert table.receipt.total_rows.state == "unknown"
    for op in ("c12.count", "c12.summary"):
        result = adapter.query(operation(sid, op=op, population="raw")).result
        assert result.rows == [] and result.receipt.total_rows.value is None
        assert result.receipt.availability.status == "unavailable"


def test_empty_match_from_partial_input_cannot_hide_dataset_as_known_zero(tmp_path):
    metadata, frames = edna_fixture(10)
    next(
        table for table in metadata.tables if table.name == "occurrences"
    ).completeness = "partial"
    _, sid, adapter, _ = local(tmp_path, [(metadata, frames)])
    with pytest.raises(EDNAUnavailable):
        adapter.dataset_count(
            listing(sid, scope=edna_scope(provider_project_id="unseen-project"))
        )


def test_policy_callback_mutation_cannot_change_frozen_science_and_truthy_is_denied(
    tmp_path,
):
    def mutate(snapshot, metadata):
        metadata.tables.clear()
        return True

    _, sid, adapter, _ = local(tmp_path, allowed=mutate)
    assert (
        adapter.query(operation(sid, population="raw")).result.receipt.total_rows.value
        == 9
    )
    adapter.access = EDNAAccess("user-a", "revision-1", lambda snapshot, metadata: 1)
    assert adapter.dataset_count(listing(sid)).value == 0
    with pytest.raises(AdapterAccessDenied):
        adapter.query(operation(sid, population="raw"))


def test_statistics_metadata_and_related_links_do_not_duplicate_dataset_entities(
    tmp_path,
):
    first, frames = edna_fixture(10)
    other, other_frames = edna_fixture(
        10, dataset_id="synthetic:edna:project-b", provider_project_id="ProjectB"
    )
    first.related_ids = [other.dataset_id]
    _, sid, adapter, policy = local(tmp_path, [(first, frames), (other, other_frames)])
    references = adapter.list(
        listing(sid, filters=CatalogueFilters(kinds=["reference"]))
    )
    assert len(references.items) == 4
    assert {node.root for node in references.items} == {"statistics", "metadata"}
    assert adapter.dataset_count(listing(sid)).value == 2
    assert other.dataset_id in adapter.open(PROJECT, listing(sid)).related_ids
    policy["denied"].add(other.dataset_id)
    assert adapter.dataset_count(listing(sid)).value == 1
    assert other.dataset_id not in adapter.open(PROJECT, listing(sid)).related_ids


def test_explicit_c09_copy_is_independent_of_origin_and_rechecks_destination_access(
    tmp_path,
):
    from ingestion.catalogue_snapshot_transfer import build_transfer, import_quarantined

    source, sid, adapter, _ = local(tmp_path / "source")
    before = adapter.query(operation(sid, op="c12.count", population="raw")).result
    manifest, contents = source.read(sid)
    transfer = build_transfer(
        manifest,
        contents,
        destination_id="synthetic-c12-copy",
        authorization_ref="synthetic-c12-acceptance",
        origin_system="synthetic-source",
        qualifications={
            identity: (
                "Synthetic canonical descriptive inventory",
                "Current destination access and eligibility required",
            )
            for identity in contents
        },
        encodings={identity: "opaque-bytes-v1" for identity in contents},
    )
    destination = LocalCatalogueSnapshotStore(
        root=(tmp_path / "destination").resolve(), access_gate=lambda manifest: True
    )
    imported = import_quarantined(
        transfer,
        contents,
        destination_id="synthetic-c12-copy",
        store=destination,
        quarantine_root=(tmp_path / "quarantine").resolve(),
        authorize=lambda value: True,
        eligible=lambda obj, origin: True,
    )
    copied = FrozenEDNACatalogueAdapter(store=destination, access=adapter.access)
    source.revoke(sid)
    after = copied.query(
        operation(imported.snapshot_id, op="c12.count", population="raw")
    ).result
    assert (
        after.rows == before.rows
        and after.receipt.content_sha256 == before.receipt.content_sha256
    )
    assert imported.latest_promoted is False and imported.snapshot_id != sid
    assert all(
        record["origin"]["live_dependency"] is False
        for record in copied.inspect(PROJECT, listing(imported.snapshot_id))[
            "provenance"
        ]
    )
    destination.revoke(imported.snapshot_id)
    with pytest.raises(SnapshotAccessDenied):
        copied.query(operation(imported.snapshot_id, population="raw"))
