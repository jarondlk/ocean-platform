from __future__ import annotations

import json

import pandas as pd

from retrieval.document_builder import documents_to_dataframe
from retrieval.edna_document_builder import (
    EDNA_SOURCE_TYPE,
    build_edna_documents,
    document_source_row_hash,
)


def _frames() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    samples = pd.DataFrame(
        [
            {
                "sample_id": "s" * 64,
                "provider": "anemone",
                "provider_sample_id": "sample-1",
                "provider_project_id": "project-1",
                "provider_run_id": "run-1",
                "sample_kind": "environmental",
                "is_control": False,
                "collection_date_utc": "2026-09-01",
                "lat": 38.4,
                "lon": 141.5,
                "anchor_event_id": "event-1",
                "source_snapshot_id": "1" * 64,
                "source_file_id": "2" * 64,
                "active": True,
            },
            {
                "sample_id": "x" * 64,
                "provider": "anemone",
                "provider_sample_id": "inactive-sample",
                "sample_kind": "unknown",
                "is_control": None,
                "active": False,
            },
        ]
    )
    assays = pd.DataFrame(
        [
            {
                "assay_id": "a" * 64,
                "sample_id": "s" * 64,
                "target_gene": "12S",
                "primer_set": "MiFish-U/E",
                "sequencing_method": "Illumina MiSeq",
                "source_snapshot_id": "1" * 64,
                "source_file_id": "3" * 64,
                "active": True,
            }
        ]
    )
    detections = pd.DataFrame(
        [
            {
                "detection_id": "d" * 64,
                "assay_id": "a" * 64,
                "assignment_method": "qcauto_target",
                "read_count": 4,
                "copies_per_ml": None,
                "genus": "Engraulis",
                "species": "Engraulis japonicus",
                "assigned_taxon_name": "Engraulis japonicus",
                "assigned_taxon_rank": "species",
                "source_snapshot_id": "1" * 64,
                "source_file_id": "4" * 64,
                "active": True,
            },
            {
                "detection_id": "c" * 64,
                "assay_id": "a" * 64,
                "assignment_method": "qcauto_target",
                "read_count": 9,
                "copies_per_ml": 2.5,
                "genus": "Scomber",
                "assigned_taxon_name": "Scomber",
                "assigned_taxon_rank": "genus",
                "source_snapshot_id": "1" * 64,
                "source_file_id": "4" * 64,
                "active": True,
            },
            {
                "detection_id": "b" * 64,
                "assay_id": "a" * 64,
                "assignment_method": "qcauto_95pct_3nn_target",
                "read_count": 7,
                "copies_per_ml": None,
                "genus": "Scomber",
                "assigned_taxon_name": "Scomber japonicus",
                "assigned_taxon_rank": "species",
                "source_snapshot_id": "1" * 64,
                "source_file_id": "5" * 64,
                "active": True,
            },
        ]
    )
    return samples, assays, detections


def test_builds_one_bounded_document_per_assignment_method():
    samples, assays, detections = _frames()

    documents = build_edna_documents(samples, assays, detections)

    assert len(documents) == 2
    assert {document.assignment_method for document in documents} == {
        "qcauto_target",
        "qcauto_95pct_3nn_target",
    }
    qcauto = next(
        document
        for document in documents
        if document.assignment_method == "qcauto_target"
    )
    assert qcauto.source_type == EDNA_SOURCE_TYPE
    assert qcauto.sample_id == "s" * 64
    assert qcauto.assay_id == "a" * 64
    assert qcauto.is_control is False
    assert qcauto.metadata["detection_count"] == 2
    assert qcauto.metadata["read_count_sum"] == 13
    assert qcauto.metadata["copies_per_ml_record_count"] == 1
    assert qcauto.metadata["featured_detection_ids"] == ["c" * 64, "d" * 64]
    assert "Scomber (genus), read count 9" in qcauto.text
    assert qcauto.text.index("Scomber (genus)") < qcauto.text.index(
        "Engraulis japonicus (species)"
    )
    assert "not abundance" in qcauto.text
    assert "biological absence" in qcauto.text
    assert "richness" not in qcauto.text.lower()


def test_document_build_is_deterministic_and_persists_metadata():
    samples, assays, detections = _frames()
    first = build_edna_documents(samples, assays, detections)
    second = build_edna_documents(
        samples.sample(frac=1, random_state=1),
        assays.sample(frac=1, random_state=2),
        detections.sample(frac=1, random_state=3),
    )

    assert [document.doc_id for document in first] == [
        document.doc_id for document in second
    ]
    assert [document.text for document in first] == [
        document.text for document in second
    ]
    assert [document_source_row_hash(document) for document in first] == [
        document_source_row_hash(document) for document in second
    ]

    frame = documents_to_dataframe(first)
    metadata = json.loads(frame.iloc[0]["metadata_json"])
    assert metadata["edna_retrieval_document_version"] == 1
    assert "Scomber" in metadata["taxon_terms"]
    assert frame.iloc[0]["provider"] == "anemone"
    assert bool(frame.iloc[0]["active"]) is True


def test_inactive_rows_and_unknown_assignment_methods_are_not_documented():
    samples, assays, detections = _frames()
    detections.loc[:, "active"] = False
    extra = detections.head(1).copy()
    extra.loc[:, "active"] = True
    extra.loc[:, "assignment_method"] = "unsupported"

    assert build_edna_documents(samples, assays, pd.concat([detections, extra])) == []


def test_control_and_unknown_status_are_explicit():
    samples, assays, detections = _frames()
    samples.loc[0, "sample_kind"] = "negative_control"
    samples.loc[0, "is_control"] = True
    control = build_edna_documents(samples, assays, detections)[0]
    assert "control (negative_control)" in control.text

    samples.loc[0, "sample_kind"] = "unknown"
    samples.loc[0, "is_control"] = None
    unknown = build_edna_documents(samples, assays, detections)[0]
    assert "unknown; control status unknown" in unknown.text
