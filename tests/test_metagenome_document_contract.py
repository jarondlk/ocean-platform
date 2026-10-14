"""Synthetic producer, compatibility and document-generation acceptance for C05."""
from __future__ import annotations

import importlib
import json

import pandas as pd
import pytest

from preprocessing.metagenome import build_sample_multisource_context, top_n_taxa_as_json
from retrieval.document_builder import build_metagenome_docs, documents_to_dataframe


SAMPLE = "2024-04-O-s1"
KRAKEN = "top_kraken_genera_json"
METAEUK = "top_metaeuk_genera_json"
UPPER = "top_kraken_upper_groups_json"


def _taxa(genus, abundance=12.0):
    return json.dumps([{"genus": genus, "abundance_value": abundance}])


def _context(**changes):
    row = {"sample_id": SAMPLE, "has_kraken": True, "has_metaeuk": True,
           "has_ctd": False, KRAKEN: _taxa("KrakenOnlyGenus"),
           METAEUK: _taxa("MetaEukOnlyGenus"), UPPER: "[]"}
    row.update(changes)
    return pd.DataFrame([row])


def _legacy():
    return _context().rename(columns={KRAKEN: "top_genus_10_json_x",
                                      METAEUK: "top_genus_10_json_y",
                                      UPPER: "top_upper_group_10_json"})


def _adapter(frame):
    contract = importlib.import_module("preprocessing.metagenome_contract")
    return contract.adapt_legacy_metagenome_context(frame)


def _producer():
    registry = pd.DataFrame([{"sample_id": SAMPLE, "has_kraken": True,
                              "has_metaeuk": True, "has_ctd": False}])
    kraken = pd.DataFrame([{"sample_id": SAMPLE, "top_genus_10_json": _taxa("KrakenOnlyGenus")}])
    metaeuk = pd.DataFrame([{"sample_id": SAMPLE, "top_genus_10_json": _taxa("MetaEukOnlyGenus")}])
    upper = pd.DataFrame([{"sample_id": SAMPLE, "top_upper_group_10_json": "[]"}])
    return build_sample_multisource_context(registry, pd.DataFrame(columns=["sample_id"]),
                                           kraken, metaeuk, upper)


def test_producer_names_method_fields_and_document_keeps_both_labels_once():
    produced = _producer()
    assert {KRAKEN, METAEUK, UPPER}.issubset(produced.columns)
    assert not {"top_genus_10_json_x", "top_genus_10_json_y"}.intersection(produced.columns)
    document = build_metagenome_docs(produced)[0]
    assert document.text.count("KrakenOnlyGenus") == 1
    assert document.text.count("MetaEukOnlyGenus") == 1
    assert "Top Kraken genera: KrakenOnlyGenus" in document.text
    assert "Top MetaEuk genera: MetaEukOnlyGenus" in document.text
    assert len(document.metadata["source_version"]) == 64
    assert document.metadata["field_mapping_version"] == produced.iloc[0]["metagenome_mapping_version"]


def test_legacy_merged_adapter_uses_verified_left_kraken_right_metaeuk_mapping():
    adapted = _adapter(_legacy())
    assert json.loads(adapted.iloc[0][KRAKEN])[0]["genus"] == "KrakenOnlyGenus"
    assert json.loads(adapted.iloc[0][METAEUK])[0]["genus"] == "MetaEukOnlyGenus"
    document = build_metagenome_docs(_legacy())[0]
    assert "Top Kraken genera: KrakenOnlyGenus" in document.text
    assert "Top MetaEuk genera: MetaEukOnlyGenus" in document.text


@pytest.mark.parametrize("method,column", [("kraken", KRAKEN), ("metaeuk", METAEUK)])
def test_unsuffixed_legacy_requires_explicit_single_method_coverage(method, column):
    frame = pd.DataFrame([{"sample_id": SAMPLE, "has_kraken": method == "kraken",
                           "has_metaeuk": method == "metaeuk", "top_genus_10_json": _taxa("SingleMethod")}])
    adapted = _adapter(frame)
    assert json.loads(adapted.iloc[0][column])[0]["genus"] == "SingleMethod"
    other = METAEUK if column == KRAKEN else KRAKEN
    assert adapted.iloc[0][other] is None
    document = build_metagenome_docs(frame)[0]
    assert document.text.count("SingleMethod") == 1
    assert ("Top Kraken" in document.text) is (method == "kraken")
    assert ("Top MetaEuk" in document.text) is (method == "metaeuk")


@pytest.mark.parametrize("flags", [{"has_kraken": True, "has_metaeuk": True},
                                    {"has_kraken": False, "has_metaeuk": False}, {}])
def test_ambiguous_unsuffixed_layout_is_rejected(flags):
    frame = pd.DataFrame([{"sample_id": SAMPLE, "top_genus_10_json": _taxa("UnknownMethod"), **flags}])
    with pytest.raises(ValueError, match="ambiguous.*unsuffixed"):
        _adapter(frame)


@pytest.mark.parametrize("missing", ["top_genus_10_json_x", "top_genus_10_json_y"])
def test_incomplete_legacy_merge_pair_is_rejected(missing):
    with pytest.raises(ValueError, match="incomplete.*legacy"):
        _adapter(_legacy().drop(columns=missing))


def test_mixed_canonical_and_legacy_fields_are_rejected():
    frame = _context().assign(top_genus_10_json_x=_taxa("WrongKraken"),
                              top_genus_10_json_y=_taxa("WrongMetaEuk"))
    with pytest.raises(ValueError, match="mixed.*canonical.*legacy"):
        _adapter(frame)


@pytest.mark.parametrize("method", ["kraken", "metaeuk"])
@pytest.mark.parametrize("coverage", [False, pd.NA])
def test_nonempty_summary_cannot_contradict_method_coverage(method, coverage):
    with pytest.raises(ValueError, match="summary contradicts false or unknown"):
        build_metagenome_docs(_context(**{f"has_{method}": coverage}))


def test_missing_taxa_summary_does_not_exchange_methods_or_fabricate_coverage():
    frame = _context(has_metaeuk=pd.NA).drop(columns=[KRAKEN, METAEUK])
    adapted = _adapter(frame)
    assert not adapted.iloc[0]["has_metaeuk"]
    document = build_metagenome_docs(frame)[0]
    assert "Top Kraken" not in document.text
    assert "Top MetaEuk" not in document.text
    assert len(document.metadata["source_version"]) == 64


def test_top_taxa_ties_and_empty_single_source_builds_are_deterministic():
    abundance = pd.DataFrame([{"sample_id": SAMPLE, "genus": "Zeta", "abundance_value": 5.0},
                              {"sample_id": SAMPLE, "genus": "Alpha", "abundance_value": 5.0}])
    first = top_n_taxa_as_json(abundance, "genus", "abundance_value")
    second = top_n_taxa_as_json(abundance.iloc[::-1], "genus", "abundance_value")
    assert first.equals(second)
    empty = top_n_taxa_as_json(abundance.iloc[:0], "genus", "abundance_value")
    assert empty.columns.tolist() == ["sample_id", "top_genus_10_json"]
    registry = pd.DataFrame([{"sample_id": SAMPLE, "has_kraken": True, "has_metaeuk": False}])
    context = build_sample_multisource_context(registry, pd.DataFrame(columns=["sample_id"]),
        first, empty, pd.DataFrame(columns=["sample_id", "top_upper_group_10_json"]))
    document = build_metagenome_docs(context)[0]
    assert "Top Kraken genera: Alpha" in document.text
    assert "Top MetaEuk" not in document.text


def test_repeat_and_legacy_normalization_keep_source_content_generation_hashes():
    first = build_metagenome_docs(_context())[0]
    second = build_metagenome_docs(_context())[0]
    legacy = build_metagenome_docs(_legacy())[0]
    assert first == second
    for key in ["source_version", "content_hash", "generation_hash"]:
        assert first.metadata[key] == legacy.metadata[key]
        assert len(first.metadata[key]) == 64
    assert first.doc_id == legacy.doc_id
    assert first.doc_id != f"meta_{SAMPLE}"


def test_json_whitespace_and_key_order_do_not_change_generation():
    first = build_metagenome_docs(_context())[0]
    formatted = _context(**{KRAKEN: '[ { "abundance_value": 12.0, "genus": "KrakenOnlyGenus" } ]'})
    changed = build_metagenome_docs(formatted)[0]
    assert first == changed


@pytest.mark.parametrize("taxa", [[{"genus": "MissingAbundance"}],
    [{"abundance_value": 2.0}], [{"genus": "NullAbundance", "abundance_value": None}],
    [{"genus": "StringAbundance", "abundance_value": "5"}],
    [{"genus": "Nonfinite", "abundance_value": float("inf")}], {}])
def test_malformed_compatibility_taxa_fail_visibly_instead_of_dropping_one_method(taxa):
    with pytest.raises(ValueError, match="taxa JSON|finite numeric abundance"):
        build_metagenome_docs(_context(**{KRAKEN: json.dumps(taxa)}))


def test_generated_source_version_cannot_hide_modified_context():
    produced = _producer()
    produced[KRAKEN] = _taxa("ChangedAfterVersioning")
    with pytest.raises(ValueError, match="source version does not match"):
        build_metagenome_docs(produced)


def test_changed_rendered_source_gets_new_content_and_generation():
    first = build_metagenome_docs(_context())[0]
    changed = build_metagenome_docs(_context(**{KRAKEN: _taxa("NewKrakenGenus")}))[0]
    assert first.doc_id != changed.doc_id
    for key in ["source_version", "content_hash", "generation_hash"]:
        assert first.metadata[key] != changed.metadata[key]


def test_changed_unrendered_source_gets_new_generation_even_if_text_matches():
    first = build_metagenome_docs(_context(sum_bases_gt1kb=100))[0]
    changed = build_metagenome_docs(_context(sum_bases_gt1kb=101))[0]
    assert first.text == changed.text
    assert first.metadata["content_hash"] == changed.metadata["content_hash"]
    assert first.metadata["source_version"] != changed.metadata["source_version"]
    assert first.metadata["generation_hash"] != changed.metadata["generation_hash"]
    assert first.doc_id != changed.doc_id


def test_document_builder_version_is_bound_to_document_generation(monkeypatch):
    import retrieval.document_builder as builder
    first = build_metagenome_docs(_context())[0]
    monkeypatch.setattr(builder, "METAGENOME_DOCUMENT_VERSION", "metagenome-document-test-v3")
    changed = build_metagenome_docs(_context())[0]
    assert first.metadata["source_version"] == changed.metadata["source_version"]
    assert first.metadata["content_hash"] == changed.metadata["content_hash"]
    assert first.metadata["generation_hash"] != changed.metadata["generation_hash"]
    assert first.doc_id != changed.doc_id


def test_field_mapping_version_is_bound_to_document_generation(monkeypatch):
    contract = importlib.import_module("preprocessing.metagenome_contract")
    first = build_metagenome_docs(_context())[0]
    monkeypatch.setattr(contract, "METAGENOME_FIELD_MAPPING_VERSION", "metagenome-fields-test-v3")
    changed = build_metagenome_docs(_context())[0]
    assert first.metadata["source_version"] == changed.metadata["source_version"]
    assert first.metadata["content_hash"] == changed.metadata["content_hash"]
    assert first.metadata["field_mapping_version"] != changed.metadata["field_mapping_version"]
    assert first.metadata["generation_hash"] != changed.metadata["generation_hash"]
    assert first.doc_id != changed.doc_id


@pytest.mark.parametrize("layout", ["canonical", "legacy"])
def test_loader_and_lineage_database_rows_keep_method_assignment(tmp_path, monkeypatch, layout):
    loader = importlib.import_module("scripts.load_db")
    lineage = importlib.import_module("ingestion.lineage")
    frame = _context() if layout == "canonical" else _legacy()
    frame.to_parquet(tmp_path / "sample_multisource_context.parquet", index=False)
    monkeypatch.setattr(loader.config, "SERVING_DIR", tmp_path)
    loaded = loader.metagenome_samples_dataframe()
    traced, _, _ = lineage._incoming_dataframe_for_table("metagenome_sample")
    for rows in [loaded, traced]:
        assert json.loads(rows.iloc[0][KRAKEN])[0]["genus"] == "KrakenOnlyGenus"
        assert json.loads(rows.iloc[0][METAEUK])[0]["genus"] == "MetaEukOnlyGenus"
    pd.testing.assert_frame_equal(loaded, traced)


@pytest.mark.parametrize("layout", ["canonical", "legacy"])
def test_api_taxa_response_keeps_method_labels(monkeypatch, layout):
    main = importlib.import_module("api.main")
    monkeypatch.setattr(main, "_sample_context_df", lambda: _context() if layout == "canonical" else _legacy())
    response = main.data_taxa(SAMPLE)
    assert response.kraken_top[0].label == "KrakenOnlyGenus"
    assert response.metaeuk_top[0].label == "MetaEukOnlyGenus"


def test_lineage_trace_retains_generated_hashes_and_source_keys(monkeypatch):
    lineage = importlib.import_module("ingestion.lineage")
    document = build_metagenome_docs(_context())[0]
    monkeypatch.setattr(lineage, "_read_retrieval_documents", lambda: documents_to_dataframe([document]))
    trace = lineage.build_document_traces()[0]
    assert trace.content_hash == document.metadata["content_hash"]
    assert f"source_version:{document.metadata['source_version']}" in trace.source_record_keys
    assert f"generation_hash:{document.metadata['generation_hash']}" in trace.source_record_keys
    assert trace.metadata == document.metadata


def test_generated_document_identity_fits_existing_database_length():
    document = build_metagenome_docs(_context(sample_id="s" * 64))[0]
    assert len(document.doc_id) <= 128
    assert len(document.metadata["generation_hash"]) == 64


def test_loader_retires_only_older_active_metagenome_documents_for_rebuilt_samples():
    loader = importlib.import_module("scripts.load_db")
    document = build_metagenome_docs(_context())[0]
    calls = []

    class Connection:
        def execute(self, sql, params):
            calls.append((str(sql), params))
            return type("Result", (), {"rowcount": 2})()

    count = loader._inactivate_superseded_metagenome_documents(Connection(), documents_to_dataframe([document]))
    assert count == 2
    sql, params = calls[0]
    assert "SET active = FALSE" in sql
    assert "source_type = 'metagenome'" in sql
    assert "active IS TRUE" in sql
    assert "sample_id = ANY(:sample_ids)" in sql
    assert "NOT (doc_id = ANY(:replacement_doc_ids))" in sql
    assert "DELETE" not in sql
    assert params == {"sample_ids": [SAMPLE], "replacement_doc_ids": [document.doc_id]}


def test_legacy_documents_do_not_implicitly_authorize_retirement():
    loader = importlib.import_module("scripts.load_db")

    class NoMutation:
        def execute(self, *args):
            pytest.fail("legacy incoming documents cannot authorize retirement")

    frame = pd.DataFrame([{"doc_id": f"meta_{SAMPLE}", "source_type": "metagenome",
                           "sample_id": SAMPLE, "metadata_json": "{}"}])
    assert loader._inactivate_superseded_metagenome_documents(NoMutation(), frame) == 0


def test_replacement_hash_validation_prevents_rewriting_retained_generation_identity():
    contract = importlib.import_module("preprocessing.metagenome_contract")
    frame = documents_to_dataframe(build_metagenome_docs(_context()))
    frame["text"] = "Altered under a retained document ID"
    with pytest.raises(ValueError, match="content or mapping hash evidence"):
        contract.metagenome_replacement_scope(frame)


@pytest.mark.parametrize("field,value", [("method_coverage", {"kraken": False, "metaeuk": True}),
    ("source_fields", {"kraken": METAEUK}), ("legacy_doc_id", "meta_unrelated"),
    ("additional_evidence", "changed")])
def test_retained_generation_identity_binds_all_metadata_evidence(field, value):
    contract = importlib.import_module("preprocessing.metagenome_contract")
    document = build_metagenome_docs(_context())[0]
    document.metadata[field] = value
    with pytest.raises(ValueError, match="generation identity is invalid"):
        contract.metagenome_replacement_scope(documents_to_dataframe([document]))


@pytest.mark.parametrize("field,value", [("lat", 1.23), ("event_id", "unrelated-event"),
                                         ("source_snapshot_id", "unrelated-snapshot")])
def test_retained_generation_identity_binds_scientific_document_fields(field, value):
    contract = importlib.import_module("preprocessing.metagenome_contract")
    frame = documents_to_dataframe(build_metagenome_docs(_context()))
    frame[field] = value
    with pytest.raises(ValueError, match="generation identity is invalid"):
        contract.metagenome_replacement_scope(frame)


@pytest.mark.parametrize("metadata", [None, "{}", "[]", '{"document_version":"old-version"}'])
def test_retained_versioned_identity_cannot_strip_or_downgrade_generation_metadata(metadata):
    contract = importlib.import_module("preprocessing.metagenome_contract")
    frame = documents_to_dataframe(build_metagenome_docs(_context()))
    frame["metadata_json"] = metadata
    with pytest.raises(ValueError, match="identity requires v2 generation metadata"):
        contract.metagenome_replacement_scope(frame)


def test_retained_versioned_identity_cannot_change_source_family_to_bypass_validation():
    contract = importlib.import_module("preprocessing.metagenome_contract")
    frame = documents_to_dataframe(build_metagenome_docs(_context()))
    frame["source_type"] = "ctd"
    with pytest.raises(ValueError, match="identity requires metagenome source_type"):
        contract.metagenome_replacement_scope(frame)


def test_multiple_active_generations_for_same_sample_cannot_authorize_retirement():
    contract = importlib.import_module("preprocessing.metagenome_contract")
    first = build_metagenome_docs(_context())[0]
    second = build_metagenome_docs(_context(**{KRAKEN: _taxa("ReplacementGenus")}))[0]
    with pytest.raises(ValueError, match="multiple active metagenome replacements"):
        contract.metagenome_replacement_scope(documents_to_dataframe([first, second]))


def test_dry_run_reports_scoped_retirement_while_preserving_unrelated_docs(monkeypatch):
    lineage = importlib.import_module("ingestion.lineage")
    document = build_metagenome_docs(_context())[0]
    incoming = documents_to_dataframe([document])
    existing = [
        {"doc_id": f"meta_{SAMPLE}", "source_type": "metagenome", "sample_id": SAMPLE, "active": True},
        {"doc_id": "inactive-generation", "source_type": "metagenome", "sample_id": SAMPLE, "active": False},
        {"doc_id": "ctd-doc", "source_type": "ctd", "sample_id": SAMPLE, "active": True},
        {"doc_id": "other-sample", "source_type": "metagenome", "sample_id": "other", "active": True},
    ]
    monkeypatch.setattr(lineage, "build_provenance_manifest", lambda **_: {"summary": {}})
    monkeypatch.setattr(lineage, "_incoming_dataframe_for_table", lambda name:
        (incoming, "serving:retrieval_parquet", ["doc_id"]) if name == "retrieval_document"
        else (pd.DataFrame(), None, []))
    monkeypatch.setattr(lineage, "_database_rows", lambda name, columns:
        (True, None, existing if name == "retrieval_document" else []))
    loader = importlib.import_module("scripts.load_db")
    monkeypatch.setattr(loader, "_load_anemone_bundle_frames", lambda *args, **kwargs: None)
    plan = lineage.build_upsert_dry_run_plan()
    table = next(item for item in plan["table_plans"] if item["table"] == "retrieval_document")
    assert table["planned_inserts"] == 1
    assert table["planned_inactivations"] == 1
    assert table["embedding_refresh_candidates"] == 1
    assert table["stale_existing"] == 4
