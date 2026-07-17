from __future__ import annotations

import json

from retrieval.local_retriever import LocalRetriever


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
