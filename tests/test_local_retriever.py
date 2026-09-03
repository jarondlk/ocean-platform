from __future__ import annotations

import json

from retrieval.local_retriever import LocalRetriever
import retrieval.local_retriever as local_module
import db.vector_store as vector_store
import config


def test_load_normalizes_legacy_jsonl_aliases(tmp_path):
    path = tmp_path / "retrieval_documents.jsonl"
    path.write_text(
        json.dumps(
            {
                "id": "ctd_2024-01-O-s1",
                "date": "2024-01-18",
                "source_type": "ctd",
                "sample_id": "2024-01-O-s1",
                "title": "CTD cast",
                "text": "temperature salinity Onagawa",
            }
        )
        + "\n",
        encoding="utf-8",
    )

    retriever = LocalRetriever()
    retriever.load(path)

    doc = retriever.documents[0]
    assert doc["doc_id"] == "ctd_2024-01-O-s1"
    assert doc["time"] == "2024-01-18"
    assert doc["bay"] == "O"
    assert doc["station"] == "s1"


def test_search_filters_normalized_legacy_documents(tmp_path):
    path = tmp_path / "retrieval_documents.jsonl"
    docs = [
        {
            "id": "ctd_2024-01-O-s1",
            "date": "2024-01-18",
            "source_type": "ctd",
            "sample_id": "2024-01-O-s1",
            "title": "Onagawa CTD",
            "text": "Onagawa temperature profile",
        },
        {
            "id": "ctd_2024-01-I-s1",
            "date": "2024-01-18",
            "source_type": "ctd",
            "sample_id": "2024-01-I-s1",
            "title": "Ishinomaki CTD",
            "text": "Ishinomaki salinity profile",
        },
    ]
    path.write_text(
        "\n".join(json.dumps(doc) for doc in docs) + "\n",
        encoding="utf-8",
    )

    retriever = LocalRetriever()
    retriever.load(path)

    results = retriever.search("temperature", k=5, bay="O", time_from="2024-01-01")
    assert [r["doc_id"] for r in results] == ["ctd_2024-01-O-s1"]


def test_search_filters_edna_metadata_without_silent_control_exclusion(tmp_path):
    path = tmp_path / "retrieval_documents.jsonl"
    documents = [
        {
            "doc_id": "edna_environmental",
            "source_type": "edna_metabarcoding",
            "sample_id": "sample-1",
            "provider": "anemone",
            "provider_project_id": "project-1",
            "provider_run_id": "run-1",
            "assignment_method": "qcauto_target",
            "sample_kind": "environmental",
            "is_control": False,
            "lat": 38.4,
            "lon": 141.5,
            "time": "2026-01-01",
            "metadata": {"taxon_terms": ["Scomber", "Scomber japonicus"]},
            "title": "Environmental sample",
            "text": "Scomber detection",
        },
        {
            "doc_id": "edna_control",
            "source_type": "edna_metabarcoding",
            "sample_id": "sample-2",
            "provider": "anemone",
            "provider_project_id": "project-1",
            "provider_run_id": "run-1",
            "assignment_method": "qcauto_target",
            "sample_kind": "negative_control",
            "is_control": True,
            "title": "Control sample",
            "text": "control detection",
            "metadata": {"taxon_terms": ["Engraulis"]},
        },
    ]
    path.write_text(
        "\n".join(json.dumps(document) for document in documents) + "\n",
        encoding="utf-8",
    )
    retriever = LocalRetriever()
    retriever.load(path)

    assert len(retriever.search("detection", k=10, provider="anemone")) == 2
    assert [
        row["doc_id"]
        for row in retriever.search(
            "fish",
            k=10,
            taxon="scomber japonicus",
            is_control=False,
            lat_min=38,
            lon_max=142,
        )
    ] == ["edna_environmental"]


def test_local_embeddings_require_matching_document_content(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "SERVING_DIR", tmp_path)
    monkeypatch.setattr(config, "EMBEDDING_DIM", 2)
    calls = []

    def embed(texts):
        calls.append(texts)
        return [[0.1, 0.2] for _ in texts]

    monkeypatch.setattr(vector_store, "embed_batch", embed)
    for text in ("original", "corrected", "corrected"):
        retriever = LocalRetriever()
        retriever.documents = [{"doc_id": "edna-1", "text": text}]
        assert retriever.ensure_embeddings() is True
    assert calls == [["original"], ["corrected"]]


def test_local_singleton_reloads_changed_edna_artifacts(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "SERVING_DIR", tmp_path)
    monkeypatch.setattr(local_module, "_retriever", None)
    monkeypatch.setattr(local_module, "_corpus_signature", ())
    monkeypatch.setattr(LocalRetriever, "ensure_embeddings", lambda _self: False)
    path = tmp_path / "anemone_retrieval_documents.jsonl"
    path.write_text(json.dumps({"doc_id": "edna-1", "text": "MiFish", "active": True}) + "\n")
    assert len(local_module.get_local_retriever().documents) == 1
    path.write_text("")
    assert local_module.get_local_retriever().documents == []
