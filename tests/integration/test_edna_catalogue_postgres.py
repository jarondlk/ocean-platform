"""Actual canonical PostgreSQL predicates versus frozen C12 row populations.

Only an explicitly selected disposable database is used. Each case owns its
schema, imports synthetic provider bytes and leaves retrieval unpublished.
"""
import json

import pandas as pd
import pytest
from sqlalchemy import text

import api.edna_service as service
from ingestion.anemone_catalogue import prepare_catalogue
from preprocessing.edna_catalogue_query import QueryUnavailable, select_rows
from schema.edna_catalogue import TABLE_COLUMNS
from scripts import import_anemone_catalogue as importer
from tests.integration.test_anemone_catalogue_postgres import database, pytestmark  # noqa: F401
from tests.test_anemone_catalogue import make_archive, rewrite


@pytest.fixture
def canonical(database, tmp_path):  # noqa: F811
    def four_methods(payloads):
        for suffix in ("", "3nn"):
            source = next(key for key in payloads if key.endswith(f"community_qc{suffix}_target.tsv.xz"))
            payloads[source.replace("_target.tsv.xz", "_nontarget.tsv.xz")] = payloads[source]

    work = tmp_path / "canonical"
    prepare_catalogue(make_archive(tmp_path / "archive", four_methods), work)
    importer.import_candidate(database, work, execute=True, publish_retrieval=False)
    with database.connect() as connection:
        assert connection.execute(text("SELECT count(*) FROM retrieval_document")).scalar_one() == 0
        assert connection.execute(text("SELECT count(*) FROM corpus_publication WHERE channel='edna'")).scalar_one() == 0
    database._c12_snapshot_root = tmp_path / "snapshots"
    return database


def frozen_tables(engine):
    tables = {}
    with engine.connect() as connection:
        for role, table in (("occurrences", "edna_sample"), ("classifications", "edna_sample"),
                            ("assays", "edna_assay"), ("detections", "edna_detection")):
            # Canonical table/column names are source constants, never user input.
            columns = ",".join('"' + column + '"' for column in TABLE_COLUMNS[role])
            rows = connection.execute(text(f"SELECT {columns} FROM {table}")).mappings().all()
            tables[role] = pd.DataFrame(rows, columns=TABLE_COLUMNS[role], dtype=object)
    return tables


def assert_canonical_parity(engine, filters):
    tables = frozen_tables(engine)
    selected = select_rows(tables, filters)
    with engine.connect() as connection:
        summary = service.edna_summary(filters, connection=connection)
        for entity, key, wrapper, joins, alias in (
            ("occurrences", "sample_id", service._sample_conditions, "edna_sample s", "s"),
            ("assays", "assay_id", service._aggregate_assay_conditions, "edna_assay a JOIN edna_sample s ON s.sample_id=a.sample_id", "a"),
            ("detections", "detection_id", service._detection_conditions, "edna_detection d JOIN edna_assay a ON a.assay_id=d.assay_id JOIN edna_sample s ON s.sample_id=a.sample_id", "d"),
        ):
            conditions, params = wrapper(filters)
            actual = connection.execute(text(f"SELECT {alias}.{key} FROM {joins} WHERE " + " AND ".join(conditions)), params).scalars().all()
            assert sorted(actual) == sorted(selected[entity][key].tolist())
    assert len(selected["occurrences"]) == summary["source_occurrences"]
    assert len(selected["assays"]) == summary["assays"]
    assert int(selected["occurrences"]["is_control"].eq(True).sum()) == summary["controls"]  # noqa: E712
    assert int(selected["occurrences"]["is_control"].isna().sum()) == summary["unknown_control_status"]
    for method in summary["methods"]:
        rows = selected["detections"].loc[
            (selected["detections"].assignment_method == method["assignment_method"])
            & (selected["detections"].target_status == method["target_status"])
        ]
        assert len(rows) == method["assignment_rows"]
        assert int(rows.read_count.sum()) == method["read_count_sum"]
        assert rows.assay_id.nunique() == method["assays_with_detections"]
    assert len(selected["detections"]) == sum(method["assignment_rows"] for method in summary["methods"])
    assert_sealed_adapter_parity(engine._c12_snapshot_root, tables, filters, summary, selected)
    return summary, selected


def assert_sealed_adapter_parity(root, tables, filters, summary, selected):
    """Exercise exact retained SQL rows through real C09 seal/read boundaries."""
    from ingestion.catalogue_snapshot import LocalCatalogueSnapshotStore
    from orchestration.frozen_edna_catalogue import EDNAAccess, FrozenEDNACatalogueAdapter
    from schema.context_catalogue import OperationRequest
    from schema.edna_catalogue import EDNADataset
    from schema.edna_catalogue_fixtures import edna_fixture, edna_scope, seal_edna_fixture

    metadata, _ = edna_fixture(0, dataset_id="synthetic:edna:canonical-postgres")
    payload = metadata.model_dump(mode="json")
    occurrence = tables["occurrences"].iloc[0]
    for field in ("provider", "provider_locus", "provider_team", "provider_project_id"):
        payload[field] = occurrence[field]
    for item in payload["tables"]:
        item["row_count"] = len(tables[item["name"]])
    metadata = EDNADataset.model_validate(payload)
    store = LocalCatalogueSnapshotStore(root=root.resolve(), access_gate=lambda manifest: True)
    sid = seal_edna_fixture(store, [(metadata, tables)])
    adapter = FrozenEDNACatalogueAdapter(store=store, access=EDNAAccess("user-a", "revision-1", lambda *args: True))

    def request(op, **parameters):
        return OperationRequest(snapshot_id=sid, scope=edna_scope(), operation_id=op,
                                operation_version="c12-v1", input_ids=[metadata.dataset_id],
                                parameters={"population": "raw", "filters": filters, **parameters},
                                access_binding="user-a", access_revision="revision-1")

    result = adapter.query(request("c12.count")).result
    assert result.receipt.source_completeness == "complete"
    count = result.rows[0]
    assert count["source_occurrence_count"] == summary["source_occurrences"]
    assert count["assay_count"] == summary["assays"]
    assert count["controls"] == summary["controls"]
    assert count["unknown_control_status"] == summary["unknown_control_status"]
    assert count["physical_sample_count"] is None
    actual_methods = {item["assignment_method"]: item for item in count["methods"]}
    for method in summary["methods"]:
        retained = actual_methods[method["assignment_method"]]
        assert retained["assignment_rows"] == method["assignment_rows"]
        assert retained["read_count_sum"] == method["read_count_sum"]
    for method in summary["community_availability"]:
        retained = actual_methods[method["assignment_method"]]
        assert retained["available_assays"] == method["available_tables"]
        assert retained["available_empty_assays"] == method["empty_tables"]
    assert sum(item["assignment_rows"] for item in count["methods"]) == len(selected["detections"])
    for role, key in (("occurrences", "sample_id"), ("assays", "assay_id"), ("detections", "detection_id")):
        page = adapter.query(request("c12.table", table=role, limit=500)).result
        assert sorted(row[key] for row in page.rows) == sorted(selected[role][key].tolist())
        assert page.receipt.total_rows.value == len(selected[role])


@pytest.mark.parametrize("filters", [
    {}, {"provider": "anemone"}, {"provider_locus": "MiFish"}, {"provider_team": "ANEMONE"},
    {"provider_project_id": "ProjectA"}, {"provider_run_id": "Run01"},
    {"provider_locus": "absent"}, {"sample_kind": "environmental"}, {"is_control": False}, {"is_control": True},
    {"taxon": "FIXTURE FISH"}, {"taxon": "absent"},
    {"lat_min": 38.4, "lat_max": 38.4, "lon_min": 141.5, "lon_max": 141.5}, {"lat_min": 39},
    {"time_from": "2024-01-01", "time_to": "2024-01-01"}, {"time_from": "2024-01-02"},
    {"time_from": "2024-01-01T18:00:00Z", "time_to": "2024-01-01T19:00:00Z"},
    {"time_from": "2024-01-02T08:00:00+09:00"},
    {"target_status": "target"}, {"target_status": "nontarget"},
    {"assignment_method": "qcauto_target"}, {"assignment_method": "qcauto_95pct_3nn_target"},
    {"assignment_method": "qcauto_nontarget"}, {"assignment_method": "qcauto_95pct_3nn_nontarget"},
    {"assignment_method": "qcauto_nontarget", "target_status": "target"},
    {"assignment_method": "qcauto_nontarget", "taxon": "FIXTURE FISH", "target_status": "nontarget"},
])
def test_unpublished_canonical_four_method_exact_sql_parity(canonical, filters):
    summary, selected = assert_canonical_parity(canonical, filters)
    if not filters:
        assert summary["source_occurrences"] == summary["assays"] == 1
        assert len(selected["detections"]) == 4
        assert len(summary["methods"]) == 4
        assert [method["read_count_sum"] for method in summary["methods"]] == [17, 17, 17, 17]


@pytest.mark.parametrize("method", ["qcauto_target", "qcauto_95pct_3nn_target", "qcauto_nontarget", "qcauto_95pct_3nn_nontarget"])
def test_available_empty_tables_select_occurrence_assay_but_no_detection(database, tmp_path, method):  # noqa: F811
    def empty(payloads):
        for suffix in ("", "3nn"):
            source = next(key for key in payloads if key.endswith(f"community_qc{suffix}_target.tsv.xz"))
            payloads[source.replace("_target.tsv.xz", "_nontarget.tsv.xz")] = payloads[source]
        for name in ("community_qc_target.tsv.xz", "community_qc3nn_target.tsv.xz", "community_qc_nontarget.tsv.xz", "community_qc3nn_nontarget.tsv.xz"):
            rewrite(payloads, name, lambda lines: lines[:1])

    work = tmp_path / "empty-canonical"
    prepare_catalogue(make_archive(tmp_path / "archive", empty), work)
    importer.import_candidate(database, work, execute=True)
    database._c12_snapshot_root = tmp_path / "snapshots"
    summary, selected = assert_canonical_parity(database, {"assignment_method": method})
    assert summary["source_occurrences"] == summary["assays"] == 1
    assert selected["detections"].empty and summary["methods"] == []
    assert summary["community_availability"] == [{"assignment_method": method, "available_tables": 1, "empty_tables": 1}]


@pytest.mark.parametrize(("kind", "control"), [("negative_control", True), ("unknown", None), ("environmental", False)])
def test_control_and_unknown_classifications_remain_raw_not_autoapproved(canonical, kind, control):
    with canonical.begin() as connection:
        connection.execute(text("UPDATE edna_sample SET sample_kind=:kind,is_control=:control"), {"kind": kind, "control": control})
    summary, selected = assert_canonical_parity(canonical, {"sample_kind": kind})
    assert summary["source_occurrences"] == 1 and len(selected["detections"]) == 4
    assert summary["controls"] == int(control is True)
    assert summary["unknown_control_status"] == int(control is None)


@pytest.mark.parametrize("criterion", [{"assignment_method": "qcauto_target"}, {"target_status": "target"}, {"taxon": "Fixture fish"}])
def test_same_assay_correlation_prevents_sibling_evidence_leakage(canonical, criterion):
    sibling = "c" * 64
    with canonical.begin() as connection:
        columns = connection.execute(text("SELECT column_name FROM information_schema.columns WHERE table_schema=current_schema() AND table_name='edna_assay' ORDER BY ordinal_position")).scalars().all()
        select = [":id" if column == "assay_id" else "'{}'" if column == "community_availability_json" else '"' + column + '"' for column in columns]
        connection.execute(text("INSERT INTO edna_assay(" + ",".join('"' + column + '"' for column in columns) + ") SELECT " + ",".join(select) + " FROM edna_assay LIMIT 1"), {"id": sibling})
    summary, _ = assert_canonical_parity(canonical, {"assay_id": sibling, **criterion})
    assert summary["source_occurrences"] == summary["assays"] == 0 and summary["methods"] == []


def test_source_unknown_rank_labels_match_sql_without_species_promotion(canonical):
    with canonical.begin() as connection:
        connection.execute(text("UPDATE edna_detection SET genus='Fixture',species='unknown fish',assigned_taxon_name='Fixture',assigned_taxon_rank='genus',taxonomy_json=:taxonomy"), {"taxonomy": json.dumps({"genus": "Fixture", "species": "unknown fish"})})
    summary, _ = assert_canonical_parity(canonical, {"taxon": "UNKNOWN FISH"})
    assert len(summary["methods"]) == 4


def test_utc_datetime_offsets_match_actual_database(canonical):
    with canonical.begin() as connection:
        connection.execute(text("UPDATE edna_sample SET collection_date_utc='2024-01-01T00:00:00+00:00',temporal_precision='datetime'"))
    summary, _ = assert_canonical_parity(canonical, {"time_from": "2024-01-01T09:00:00+09:00", "time_to": "2024-01-01T00:00:00Z"})
    assert summary["source_occurrences"] == 1


@pytest.mark.parametrize("availability", [None, "{}"])
def test_retained_legacy_detections_can_prove_method_without_inventing_empty_table(canonical, availability):
    with canonical.begin() as connection:
        connection.execute(text("UPDATE edna_assay SET community_availability_json=:availability"), {"availability": availability})
    summary, selected = assert_canonical_parity(canonical, {"assignment_method": "qcauto_nontarget"})
    assert summary["source_occurrences"] == summary["assays"] == 1
    assert len(selected["detections"]) == 1
    assert summary["community_availability"] == []


@pytest.mark.parametrize(("precision", "label"), [("month", "2024-01"), ("year", "2024"), (None, None)])
def test_coarse_dates_preserved_and_exact_frozen_time_filter_unavailable(canonical, precision, label):
    with canonical.begin() as connection:
        connection.execute(text("UPDATE edna_sample SET collection_date_utc=:label,temporal_precision=:precision"), {"label": label, "precision": precision})
    tables = frozen_tables(canonical)
    assert len(select_rows(tables, {})["occurrences"]) == 1
    with pytest.raises(QueryUnavailable, match="coarse or unresolved"):
        select_rows(tables, {"time_from": "2024-01-01"})
