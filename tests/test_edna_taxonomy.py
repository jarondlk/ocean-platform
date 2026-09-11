"""Offline regression reference; synthetic assay metadata is not sample evidence."""
from collections import Counter
from copy import deepcopy
import csv
import hashlib
import json
from pathlib import Path

import pandas as pd
import pytest

from ingestion.anemone import load_contract
from preprocessing.edna_analysis import build_analysis, method_comparison, taxon_key
from preprocessing.edna_taxonomy import (
    SOURCE_RANKS,
    deepest_resolved_assignment,
    detection_assignment,
    resolved_lineage,
    resolved_name,
)
from retrieval.edna_document_builder import build_edna_documents
from tests.test_edna_analysis import fixture as analysis_fixture


REFERENCE = Path(__file__).parent / "fixtures/anemone/community_qc3nn_target.tsv"
REFERENCE_SHA256 = "e9923f5b0251ec30d61c6b22347c0b0040d6aec4f444e83f0e67975a61defb16"


def reference_rows():
    with REFERENCE.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def reference_analysis_source():
    recipe, source = analysis_fixture()
    template = source["edna_detection"][0]
    source["edna_detection"] = [
        {
            **template, **row,
            "detection_id": hashlib.sha256(f"reference-{number}".encode()).hexdigest(),
            "sequence_sha256": hashlib.sha256(row["sequence"].encode()).hexdigest(),
            "assignment_method": "qcauto_95pct_3nn_target",
            "read_count": int(row["nreads"]),
            "copies_per_ml": float(row["ncopiesperml"]),
            "taxonomy_json": json.dumps({rank: row[rank] for rank in SOURCE_RANKS}),
            # Reproduce existing canonical records produced before this fix.
            "assigned_taxon_name": row["isolate"],
            "assigned_taxon_rank": "isolate",
            "source_row_number": number,
        }
        for number, row in enumerate(reference_rows(), start=2)
    ]
    return recipe.model_copy(update={"assignment_methods": ["qcauto_95pct_3nn_target"]}), source


def test_reference_identity_schema_and_assignment_resolution():
    assert hashlib.sha256(REFERENCE.read_bytes()).hexdigest() == REFERENCE_SHA256
    rows = reference_rows()
    assert list(rows[0]) == load_contract()["tables"]["community"]["columns"]
    assert list(SOURCE_RANKS) == list(rows[0])[1:-3]
    assert len(rows) == len({row["sequence"] for row in rows}) == 56
    assert sum(int(row["nreads"]) for row in rows) == 38260
    assert Counter(deepest_resolved_assignment(row)[1] for row in rows) == {
        "species": 37, "genus": 18, "family": 1,
    }
    assert deepest_resolved_assignment(rows[0]) == ("Tridentiger trigonocephalus", "species")
    assert deepest_resolved_assignment(rows[4]) == ("Acanthopagrus", "genus")
    assert deepest_resolved_assignment(rows[27]) == ("Stichaeidae", "family")


@pytest.mark.parametrize("value", [
    None, float("nan"), pd.NA, "", " NA ", "N/A", "NULL", "NaN", "unidentified",
    " unidentified Acanthopagrus ", "UNIDENTIFIED\tStichaeidae", "unknown fish",
    "unassigned", "Unclassified Metazoa",
])
def test_missing_and_placeholder_names_are_unresolved(value):
    assert resolved_name(value) is None


def test_placeholder_context_is_not_promoted_and_names_are_not_reclassified():
    assert deepest_resolved_assignment({"species": "unidentified Acanthopagrus"}) == (None, None)
    assert resolved_name("Unknownium example") == "Unknownium example"
    assert resolved_name("  Scomber japonicus  ") == "Scomber japonicus"
    # Real lower-rank labels remain available; populated cells alone are not proof.
    assert deepest_resolved_assignment({"species": "Fish example", "subspecies": "Fish example minor"}) == ("Fish example minor", "subspecies")
    assert deepest_resolved_assignment({"family": "Gobiidae", "subfamily": "Gobionellinae"}) == ("Gobionellinae", "subfamily")
    assert deepest_resolved_assignment({"genus": "Scomber", "species": "Scomber", "isolate": "Scomber"}) == ("Scomber", "genus")
    assert "species" not in resolved_lineage({"genus": "Scomber", "species": "Scomber"})


@pytest.mark.parametrize("rank,richness,retained,excluded,excluded_rows", [
    ("species", 26, 29166, 9094, 19),
    ("genus", 36, 38064, 196, 1),
])
def test_reference_analysis_excludes_unresolved_ranks_in_existing_rows(rank, richness, retained, excluded, excluded_rows):
    recipe, source = reference_analysis_source()
    before = deepcopy(source)
    result = build_analysis(recipe.model_copy(update={"rank": rank}), source)
    assert result["algorithm_version"] == "edna-descriptive-v2"
    diversity, = result["tables"]["diversity"]
    assert diversity["richness"] == richness
    assert diversity["retained_reads"] == retained
    assert diversity["excluded_reads"] == excluded
    assert diversity["source_reads"] == 38260
    exclusions = result["tables"]["exclusions"]
    assert len(exclusions) == excluded_rows
    assert {row["reason"] for row in exclusions} == {"unresolved_rank"}
    assert sum(row["read_count"] for row in result["tables"]["composition"]) == retained
    assert sum(row["read_proportion"] for row in result["tables"]["composition"]) == pytest.approx(1)
    assert source == before


def test_reference_does_not_override_unknown_sample_classification():
    recipe, source = reference_analysis_source()
    source["edna_sample"][0].update(sample_kind="unknown", is_control=None)
    result = build_analysis(recipe, source)
    assert result["tables"]["diversity"] == []
    assert len(result["tables"]["exclusions"]) == 56
    assert {row["reason"] for row in result["tables"]["exclusions"]} == {"control_or_unknown"}


def test_method_comparison_uses_resolved_lineage_and_retains_source_labels():
    _, source = reference_analysis_source()
    a = source["edna_detection"][4]
    b = {**a, "assignment_method": "qcauto_target", "detection_id": "b" * 64,
         "species": "Acanthopagrus schlegelii"}
    comparison, = method_comparison([a, b])
    assert comparison["status"] == "compatible_resolution"
    assert comparison["three_nn_taxonomy"]["species"] == "unidentified Acanthopagrus"
    b["genus"] = "Other genus"
    assert method_comparison([a, b])[0]["status"] == "conflicting_assignment"
    blank = {rank: "unidentified fish" for rank in SOURCE_RANKS}
    assert method_comparison([{**a, **blank}, {**b, **blank}])[0]["status"] == "unassigned"


def test_unresolved_ancestor_wording_does_not_split_a_resolved_taxon():
    a = {"family": "unknown", "genus": "Scomber", "species": "Scomber japonicus"}
    b = {**a, "family": "unidentified Scombridae"}
    assert taxon_key(a, "species") == taxon_key(b, "species")


def test_unresolved_species_do_not_generate_control_taxon_overlap():
    recipe, source = reference_analysis_source()
    environmental = source["edna_detection"][4]
    sample = {**source["edna_sample"][0], "sample_id": "6" * 64,
              "sample_kind": "negative_control", "is_control": True}
    assay = {**source["edna_assay"][0], "assay_id": "7" * 64, "sample_id": sample["sample_id"]}
    control = {**environmental, "detection_id": "8" * 64, "assay_id": assay["assay_id"],
               "sequence_sha256": "9" * 64}
    source["edna_sample"].append(sample)
    source["edna_assay"].append(assay)
    source["edna_detection"] = [environmental, control]
    result = build_analysis(recipe.model_copy(update={"rank": "species"}), source)
    assert result["tables"]["control_overlap"] == []
    control["sequence_sha256"] = environmental["sequence_sha256"]
    result = build_analysis(recipe.model_copy(update={"rank": "species"}), source)
    assert {row["match_basis"] for row in result["tables"]["control_overlap"]} == {"sequence"}


def test_rebuilt_retrieval_corrects_old_assignments_without_mutating_canonical_evidence():
    _, source = reference_analysis_source()
    before = deepcopy(source)
    documents = build_edna_documents(*(pd.DataFrame(source[name]) for name in ("edna_sample", "edna_assay", "edna_detection")))
    document, = documents
    assert "Tridentiger trigonocephalus (species), read count 4472" in document.text
    assert "Acanthopagrus (genus), read count 2737" in document.text
    assert "(isolate)" not in document.text
    assert document.metadata["detection_count"] == 56
    assert document.metadata["read_count_sum"] == 38260
    assert source == before


def test_retrieval_assignment_supports_sparse_rows_without_overriding_source():
    row = {"genus": "Scomber", "species": "unidentified Scomber",
           "assigned_taxon_name": "Scomber japonicus", "assigned_taxon_rank": "species"}
    assert detection_assignment(row) == ("Scomber", "genus")
    assert detection_assignment({"assigned_taxon_name": "Scomber japonicus", "assigned_taxon_rank": "species"}) == ("Scomber japonicus", "species")
    assert detection_assignment({**row, "taxonomy_json": '{"family": "Scombridae"}'}) == ("Scombridae", "family")
