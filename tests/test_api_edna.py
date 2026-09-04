from __future__ import annotations

from fastapi.testclient import TestClient

import api.main as api_main
from api.main import app


client = TestClient(app)


def test_edna_catalog_and_sample_routes(monkeypatch):
    monkeypatch.setattr(
        api_main,
        "edna_catalog",
        lambda: {
            "samples": 2,
            "assays": 2,
            "detections": 4,
            "controls": 1,
            "unknown_control_status": 0,
            "providers": ["anemone"],
            "projects": ["project-1"],
            "runs": ["run-1"],
            "assignment_methods": [
                "qcauto_95pct_3nn_target",
                "qcauto_target",
            ],
            "sample_kinds": ["environmental", "negative_control"],
            "time_extent": {"min": "2026-01-01", "max": "2026-01-02"},
            "coordinate_extent": {
                "lat_min": 38.0,
                "lat_max": 39.0,
                "lon_min": 141.0,
                "lon_max": 142.0,
            },
        },
    )
    captured = {}

    def fake_samples(filters, **kwargs):
        captured.update({"filters": filters, **kwargs})
        return {
            "total": 1,
            "limit": kwargs["limit"],
            "offset": kwargs["offset"],
            "rows": [{"sample_id": "s" * 64, "is_control": False}],
        }

    monkeypatch.setattr(api_main, "edna_samples", fake_samples)

    catalog = client.get("/data/edna/catalog")
    samples = client.get(
        "/data/edna/samples?provider=anemone&assignment_method=qcauto_target"
        "&taxon=Scomber&is_control=false&limit=20"
    )

    assert catalog.status_code == 200
    assert catalog.json()["assignment_methods"] == [
        "qcauto_95pct_3nn_target",
        "qcauto_target",
    ]
    assert samples.status_code == 200
    assert samples.json()["rows"][0]["is_control"] is False
    assert captured["filters"] == {
        "provider": "anemone",
        "assignment_method": "qcauto_target",
        "taxon": "Scomber",
        "is_control": False,
    }
    assert captured["limit"] == 20


def test_edna_detail_routes_reject_invalid_and_missing_ids(monkeypatch):
    assert client.get("/data/edna/samples/not-a-hash").status_code == 400
    monkeypatch.setattr(api_main, "edna_sample_detail", lambda _value: None)
    assert client.get(f"/data/edna/samples/{'a' * 64}").status_code == 404


def test_edna_detection_route_preserves_method_and_sequence_choice(monkeypatch):
    captured = {}

    def fake_detections(filters, **kwargs):
        captured.update({"filters": filters, **kwargs})
        return {
            "total": 1,
            "limit": kwargs["limit"],
            "offset": kwargs["offset"],
            "rows": [
                {
                    "detection_id": "d" * 64,
                    "assignment_method": "qcauto_95pct_3nn_target",
                    "read_count": 10,
                }
            ],
        }

    monkeypatch.setattr(api_main, "edna_detections", fake_detections)
    response = client.get(
        "/data/edna/detections?assignment_method=qcauto_95pct_3nn_target"
        "&include_sequence=true"
    )

    assert response.status_code == 200
    assert captured["filters"]["assignment_method"] == "qcauto_95pct_3nn_target"
    assert captured["include_sequence"] is True
    assert response.json()["rows"][0]["read_count"] == 10


def test_edna_filters_fail_closed():
    assert (
        client.get("/data/edna/samples?assignment_method=unsupported").status_code
        == 400
    )
    assert client.get("/data/edna/samples?lat_min=40&lat_max=30").status_code == 400
    assert client.get("/data/edna/samples?sample_kind=field").status_code == 400
    assert client.get("/data/edna/samples?time_from=2026-02-30").status_code == 400
    assert client.get("/data/edna/samples?time_from=2026-03-01&time_to=2026-01-01").status_code == 400
    assert client.get("/data/edna/detections?sample_id=not-a-hash").status_code == 400
    assert (
        client.get(
            "/documents?source_type=metagenome&taxon=Scomber"
        ).status_code
        == 400
    )
    response = client.post(
        "/retrieve",
        json={
            "query": "fish",
            "source_type": "metagenome",
            "assignment_method": "qcauto_target",
        },
    )
    assert response.status_code == 422


def test_edna_export_contains_provenance_and_no_credentials(monkeypatch):
    def fake_detections(_filters, **kwargs):
        assert _filters["lat_min"] == 0
        assert _filters["is_control"] is False
        assert kwargs["limit"] == 25_001
        return {
            "total": 1,
            "limit": 25_001,
            "offset": 0,
            "rows": [
                {
                    "detection_id": "d" * 64,
                    "assignment_method": "qcauto_target",
                    "provider_sample_id": "=HYPERLINK(\"https://example.invalid\")",
                    "read_count": 10,
                    "source_snapshot_id": "s" * 64,
                    "source_file_id": "f" * 64,
                    "source_url": "https://db.anemone.bio/dist/sample/file.tsv.xz",
                    "source_sha256": "h" * 64,
                    "source_row_number": 2,
                }
            ],
        }

    monkeypatch.setattr(api_main, "edna_detections", fake_detections)
    response = client.get("/data/edna/export?assignment_method=qcauto_target&lat_min=0&is_control=false")

    assert response.status_code == 200
    assert response.headers["x-export-truncated"] == "false"
    body = response.text
    assert "assignment_method" in body
    assert "source_url" in body
    assert "source_sha256" in body
    assert "collection_date_utc" in body
    assert "target_gene" in body
    assert "'=HYPERLINK" in body
    assert "password" not in body.lower()
    assert "authorization" not in body.lower()
