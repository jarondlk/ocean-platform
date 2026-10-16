"""Independent adversarial C12 scientific-selection and current-access checks."""

import hashlib
import json

import pandas as pd
import pytest

from ingestion.catalogue_snapshot import LocalCatalogueSnapshotStore
from ingestion.edna_catalogue_inputs import load_dataset
from orchestration import frozen_edna_catalogue as adapter_module
from orchestration.frozen_edna_catalogue import (
    AdapterAccessDenied, EDNAAccess, FrozenEDNACatalogueAdapter,
)
from schema.context_catalogue import OperationRequest
from schema.edna_catalogue import RAW_METHODS
from schema.edna_catalogue_fixtures import edna_fixture, edna_scope, seal_edna_fixture

DATASET = "synthetic:edna:project-a"
METHOD = "qcauto_target"
PROTOCOL = {
    "target_gene": "12S", "primer_set": "Synthetic-MiFish",
    "sequencing_method": "synthetic-amplicon-sequencing",
}


def frozen(tmp_path, sources=None, *, callback=None):
    store = LocalCatalogueSnapshotStore(root=tmp_path.resolve(), access_gate=lambda manifest: True)
    snapshot = seal_edna_fixture(store, sources or [edna_fixture(1)])
    adapter = FrozenEDNACatalogueAdapter(store=store, access=EDNAAccess(
        "independent-user", "current-policy-1", callback or (lambda snapshot, metadata: True),
    ))
    return store, snapshot, adapter


def operation(snapshot, *, op="c12.count", **parameters):
    return OperationRequest(snapshot_id=snapshot, scope=edna_scope(), operation_id=op,
                            operation_version="c12-v1", input_ids=[DATASET], parameters=parameters,
                            access_binding="independent-user", access_revision="current-policy-1")


def fixture():
    metadata, frames = edna_fixture(1)
    return metadata, {role: frame.astype(object) for role, frame in frames.items()}


def row_count(metadata, role, count):
    next(item for item in metadata.tables if item.name == role).row_count = count


def second_assay(metadata, frames, *, target_gene="18S", primer_set="OtherPrimer", methods=RAW_METHODS):
    original = frames["assays"].iloc[0].to_dict()
    assay_id = hashlib.sha256(b"independent-second-assay").hexdigest()
    original.update(assay_id=assay_id, target_gene=target_gene, primer_set=primer_set)
    availability = json.loads(original["community_availability_json"])
    original["community_availability_json"] = json.dumps({key: value for key, value in availability.items() if key in methods})
    frames["assays"] = pd.concat([frames["assays"], pd.DataFrame([original])], ignore_index=True)
    added = []
    for row in frames["detections"].to_dict("records"):
        if row["assignment_method"] in methods:
            row.update(assay_id=assay_id, detection_id=hashlib.sha256((assay_id + row["assignment_method"]).encode()).hexdigest())
            added.append(row)
    frames["detections"] = pd.concat([frames["detections"], pd.DataFrame(added)], ignore_index=True)
    row_count(metadata, "assays", len(frames["assays"]))
    row_count(metadata, "detections", len(frames["detections"]))


@pytest.mark.parametrize("method", [None, "qcauto_target", "qcauto_95pct_3nn_target"])
def test_nontarget_only_taxonomy_cannot_qualify_a_scientific_target_population(tmp_path, method):
    metadata, frames = fixture()
    detections = frames["detections"]
    non = detections.assignment_method.str.endswith("_nontarget")
    for index in detections.index[non]:
        detections.at[index, "taxonomy_json"] = '{"species":"Independent nontarget species"}'
        detections.at[index, "assigned_taxon_name"] = "Independent nontarget species"
        detections.at[index, "assigned_taxon_rank"] = "species"
    _, snapshot, adapter = frozen(tmp_path, [(metadata, frames)])
    filters = {"taxon": "Independent nontarget species"}
    if method:
        filters["assignment_method"] = method
    eligible = adapter.query(operation(snapshot, population="eligible", filters=filters)).result
    assert eligible.receipt.availability.status == "available"
    assert eligible.rows[0]["source_occurrence_count"] == 0
    if method is None:
        raw = adapter.query(operation(snapshot, population="raw", filters=filters)).result
        assert raw.rows[0]["source_occurrence_count"] == 1


def test_default_scientific_population_and_summary_exclude_nontarget_siblings(tmp_path):
    _, snapshot, adapter = frozen(tmp_path)
    table = adapter.query(operation(snapshot, op="c12.table", table="detections")).result
    summary = adapter.query(operation(snapshot, op="c12.summary")).result
    assert {row["assignment_method"] for row in table.rows} == {"qcauto_target", "qcauto_95pct_3nn_target"}
    assert {row["assignment_method"] for row in summary.rows} == {"qcauto_target", "qcauto_95pct_3nn_target"}
    assert sum(row["assignment_rows"] for row in summary.rows) == 2


@pytest.mark.parametrize("legacy", [None, "{}"])
@pytest.mark.parametrize("method", ["qcauto_target", "qcauto_95pct_3nn_target"])
def test_actual_legacy_detections_establish_scientific_method_availability(tmp_path, legacy, method):
    metadata, frames = fixture()
    frames["assays"].at[0, "community_availability_json"] = legacy
    _, snapshot, adapter = frozen(tmp_path, [(metadata, frames)])
    count = adapter.query(operation(snapshot, filters={"assignment_method": method})).result.rows[0]
    assert count["source_occurrence_count"] == count["assay_count"] == 1
    assert count["methods"][0]["available_assays"] == count["methods"][0]["eligible_assays"] == 1
    assert count["methods"][0]["available_empty_assays"] == 0
    frequency = adapter.query(operation(snapshot, op="c12.frequency", filters={"assignment_method": method, "taxon": "Scomber"}, **PROTOCOL)).result.rows[0]
    assert frequency["eligible_denominator"] == 1
    assert frequency["positive_units"] == 0
    assert frequency["frequency"] == 0


def test_protocol_fields_cannot_be_satisfied_by_two_different_assays(tmp_path):
    metadata, frames = fixture()
    second_assay(metadata, frames)
    _, snapshot, adapter = frozen(tmp_path, [(metadata, frames)])
    response = adapter.query(operation(snapshot, target_gene="12S", primer_set="OtherPrimer", sequencing_method=PROTOCOL["sequencing_method"])).result
    assert response.rows[0]["source_occurrence_count"] == response.rows[0]["assay_count"] == 0
    frequency = adapter.query(operation(snapshot, op="c12.frequency", filters={"assignment_method": METHOD, "taxon": "Scomber"}, target_gene="12S", primer_set="OtherPrimer", sequencing_method=PROTOCOL["sequencing_method"])).result.rows[0]
    assert frequency["eligible_denominator"] == 0
    assert frequency["positive_units"] == 0
    assert frequency["frequency"] is None


def test_a_complete_protocol_sibling_cannot_lend_eligibility_to_an_incomplete_method_assay(tmp_path):
    metadata, frames = fixture()
    second_assay(metadata, frames, target_gene="12S", primer_set=None, methods=(METHOD,))
    # Original complete assay retains only a raw nontarget method; the target
    # assay has an incomplete protocol despite sharing the same occurrence.
    original_id = frames["assays"].at[0, "assay_id"]
    value = json.loads(frames["assays"].at[0, "community_availability_json"])
    frames["assays"].at[0, "community_availability_json"] = json.dumps({"qcauto_nontarget": value["qcauto_nontarget"]})
    frames["detections"] = frames["detections"].loc[~frames["detections"].assay_id.eq(original_id) | frames["detections"].assignment_method.eq("qcauto_nontarget")].reset_index(drop=True)
    row_count(metadata, "detections", len(frames["detections"]))
    _, snapshot, adapter = frozen(tmp_path, [(metadata, frames)])
    response = adapter.query(operation(snapshot, filters={"assignment_method": METHOD})).result
    assert response.rows[0]["source_occurrence_count"] == response.rows[0]["assay_count"] == 0


@pytest.mark.parametrize("outcome", [False, None, 0, 1, "true"])
def test_current_access_requires_literal_true_for_all_operation_types(tmp_path, outcome):
    _, snapshot, adapter = frozen(tmp_path, callback=lambda snapshot, metadata: outcome)
    for op in adapter_module.OPERATIONS:
        with pytest.raises(AdapterAccessDenied):
            adapter.query(operation(snapshot, op=op))


def test_callback_metadata_mutation_cannot_reclassify_or_relabel_frozen_inputs(tmp_path):
    def mutate(snapshot, metadata):
        metadata.dataset_id = "rewritten-dataset"
        metadata.descriptor.assignment_method = "qcauto_nontarget"
        metadata.qualification = "injected callback prose"
        metadata.tables.clear()
        return True
    _, snapshot, adapter = frozen(tmp_path, callback=mutate)
    response = adapter.query(operation(snapshot)).result
    assert response.rows[0]["source_occurrence_count"] == 1
    assert {item["assignment_method"] for item in response.rows[0]["methods"]} == {"qcauto_target", "qcauto_95pct_3nn_target"}
    assert all("injected callback prose" not in value for value in response.receipt.provenance.references)


def test_callback_rechecks_after_a_prior_success_for_frequency_as_well_as_inventory(tmp_path):
    policy = {"allowed": True}
    _, snapshot, adapter = frozen(tmp_path, callback=lambda snapshot, metadata: policy["allowed"])
    request = operation(snapshot, op="c12.frequency", filters={"assignment_method": METHOD, "taxon": "Scomber"}, **PROTOCOL)
    assert adapter.query(request).result.rows[0]["eligible_denominator"] == 1
    policy["allowed"] = False
    with pytest.raises(AdapterAccessDenied):
        adapter.query(request)


def test_snapshot_footer_budget_is_checked_before_any_access_callback_or_decode(tmp_path, monkeypatch):
    calls = []
    _, snapshot, adapter = frozen(tmp_path, callback=lambda snapshot, metadata: calls.append(metadata.dataset_id) or True)
    monkeypatch.setattr(adapter_module, "MAX_ROWS", 1)
    def unexpected(*args, **kwargs):
        pytest.fail("Snapshot footer bounds must fail before dataset decode")
    monkeypatch.setattr(adapter_module, "load_dataset", unexpected)
    with pytest.raises(ValueError, match="budget"):
        adapter.query(operation(snapshot))
    assert calls == []


def test_every_dataset_actual_decode_budget_is_validated_before_any_access_callback(tmp_path, monkeypatch):
    calls = []
    sources = [edna_fixture(1), edna_fixture(1, dataset_id="synthetic:edna:second-project")]
    _, snapshot, adapter = frozen(tmp_path, sources, callback=lambda snapshot, metadata: calls.append(metadata.dataset_id) or True)
    original = adapter_module.load_dataset
    budget = adapter_module.MAX_DECODED_BYTES
    def expanded(*args, **kwargs):
        value = original(*args, **kwargs)
        # Simulate actual Arrow buffers exceeding the footer accounting, which
        # can occur when nullable values expand on decode. Resource numbers are
        # synthetic; no large allocation or external process is involved.
        for frame in value.tables.values():
            frame.attrs["decoded_bytes"] = budget // 6
        return value
    monkeypatch.setattr(adapter_module, "load_dataset", expanded)
    with pytest.raises(ValueError, match="budget"):
        adapter.query(operation(snapshot))
    assert calls == []


def test_remaining_actual_snapshot_budget_is_passed_to_each_dataset_decoder(tmp_path, monkeypatch):
    sources = [edna_fixture(1), edna_fixture(1, dataset_id="synthetic:edna:second-project")]
    _, snapshot, adapter = frozen(tmp_path, sources)
    original = adapter_module.load_dataset
    budgets = []
    def observe(*args, **kwargs):
        budgets.append(kwargs["decoded_budget"])
        return original(*args, **kwargs)
    monkeypatch.setattr(adapter_module, "load_dataset", observe)
    adapter.query(operation(snapshot))
    assert len(budgets) == 2
    assert budgets[0] == adapter_module.MAX_DECODED_BYTES
    assert budgets[1] < budgets[0]


@pytest.mark.parametrize("value", [2**53, 2**63 - 1])
@pytest.mark.parametrize("op", ["c12.table", "c12.count", "c12.summary"])
def test_exact_canonical_int64_reads_are_retained_but_unsafe_browser_outputs_are_unavailable(tmp_path, value, op):
    metadata, frames = fixture()
    frames["detections"].at[0, "read_count"] = value
    store, snapshot, adapter = frozen(tmp_path, [(metadata, frames)])
    manifest, contents = store.read(snapshot)
    metadata_object = next(item for item in manifest.objects if item.role == "canonical_rows")
    retained = load_dataset(manifest, contents, metadata_object)
    assert value in retained.tables["detections"].read_count.tolist()
    assert all(type(item) is int for item in retained.tables["detections"].read_count)
    response = adapter.query(operation(snapshot, op=op, table="detections", filters={"assignment_method": METHOD})).result
    assert response.rows == []
    assert response.receipt.availability.status == "unavailable"
    assert "browser numeric contract" in response.receipt.availability.reason
    assert response.receipt.total_rows.value is None


def test_scientific_output_columns_declare_read_concentration_and_frequency_units(tmp_path):
    _, snapshot, adapter = frozen(tmp_path)
    table = adapter.query(operation(snapshot, op="c12.table", table="detections")).result
    units = {column.key: column.unit for column in table.columns}
    assert units["read_count"] == "reads"
    assert units["copies_per_ml"] == "copies/mL"
    summary = adapter.query(operation(snapshot, op="c12.summary")).result
    units = {column.key: column.unit for column in summary.columns}
    assert units["read_count_sum"] == "reads"
    assert units["copies_per_ml_mean"] == "copies/mL"
    frequency = adapter.query(operation(snapshot, op="c12.frequency", filters={"assignment_method": METHOD, "taxon": "Scomber"}, **PROTOCOL)).result
    assert {column.key: column.unit for column in frequency.columns}["frequency"] == "proportion"


def test_retained_occurrence_bytes_do_not_advertise_queries_without_relational_inputs(tmp_path):
    from schema.context_catalogue import Availability, ListingRequest

    metadata, frames = fixture()
    for spec in metadata.tables:
        if spec.name in {"assays", "detections"}:
            spec.object_id = spec.row_count = None
            spec.availability = Availability(status="unavailable", reason="Not retained")
            spec.completeness = "unavailable"
            del frames[spec.name]
    _, snapshot, adapter = frozen(tmp_path, [(metadata, frames)])
    request = ListingRequest(snapshot_id=snapshot, scope=edna_scope(),
                             access_binding="independent-user", access_revision="current-policy-1")
    table_id = next(spec.object_id for spec in metadata.tables if spec.name == "occurrences")
    node = adapter.open(table_id, request)
    assert node.availability.status == "available"
    assert node.lifecycle.query_readiness == "not_ready"
    assert all(item.availability.status == "unavailable" for item in node.operations)
    assert adapter.query(operation(snapshot, op="c12.table", population="raw")).result.receipt.availability.status == "unavailable"
