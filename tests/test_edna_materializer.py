import json

import pandas as pd

import config
from retrieval.edna_document_builder import build_edna_documents
from retrieval.edna_materializer import _document_frame, _write_artifacts
from retrieval.local_retriever import LocalRetriever
from retrieval.edna_publication import retrieval_path
from tests.test_edna_document_builder import _frames


def test_materialized_artifacts_round_trip_structured_filters(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "SERVING_DIR", tmp_path)
    documents = build_edna_documents(*_frames())
    _write_artifacts(documents, _document_frame(documents))
    retriever = LocalRetriever()
    retriever.load()
    results = retriever.search("MiFish", provider="anemone", taxon="engraulis", is_control=False)
    assert len(results) == 1
    assert results[0]["assignment_method"] == "qcauto_target"
    assert isinstance(results[0]["metadata"]["canonical_records"], list)
    parquet = pd.read_parquet(retrieval_path("parquet"))
    assert len(parquet) == 2
    assert json.loads(parquet.iloc[0]["metadata_json"])["edna_retrieval_document_version"] == 1


def test_empty_materialization_keeps_a_valid_empty_fallback(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "SERVING_DIR", tmp_path)
    _write_artifacts([], pd.DataFrame())
    retriever = LocalRetriever()
    retriever.load()
    assert retriever.search("MiFish") == []
    assert pd.read_parquet(retrieval_path("parquet")).empty
