from contextlib import nullcontext
from datetime import datetime, timezone
from types import SimpleNamespace

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from api import overview_coverage as service
from api import auth
from api.auth import ROLE_PERMISSIONS, route_permission
from api.main import app


@pytest.fixture
def artifacts(tmp_path, monkeypatch):
    normalized, serving = tmp_path / "normalized", tmp_path / "serving"
    normalized.mkdir()
    serving.mkdir()
    monkeypatch.setattr(service.config, "NORMALIZED_DIR", normalized)
    monkeypatch.setattr(service.config, "SERVING_DIR", serving)
    pd.DataFrame({"sample_id": ["a", "a", "b"], "ctd_date": ["2025-12-01", "2025-12-01", "2026-02-01"]}).to_parquet(normalized / "ctd_summary.parquet")
    pd.DataFrame({"sample_id": ["a", "b", "ctd-only"], "sample_year_month": ["2025-12", "2026-02", "2024-01"],
                  "has_kraken": [True, False, False], "has_metaeuk": [True, True, False]}).to_parquet(serving / "sample_registry.parquet")
    pd.DataFrame({"date_jst": ["2026-02-13", "2026-02-20", "2026-02-20", "2026-02-21"],
                  "mean_sst": [12., 13., 13., float('nan')]}).to_parquet(normalized / "sst_daily_summary.parquet")
    return normalized, serving


def test_source_units_and_sst_holes_are_preserved(artifacts):
    ctd = service.artifact_source("ctd")
    meta = service.artifact_source("metagenome")
    sst = service.artifact_source("remote_sensing")
    assert ctd.total_count == 2
    assert [item.month for item in ctd.bins] == ["2025-12", "2026-02"]
    assert meta.total_count == 2  # Kraken and MetaEuk never double-count a sample.
    assert meta.observed_start == "2025-12"
    assert meta.temporal_precision == "month"
    assert sst.total_count == 2
    assert sst.excluded_count == 1
    assert sst.missing_day_count == 6
    assert sst.missing_dates_within_extent == [f"2026-02-{day}" for day in range(14, 20)]
    assert sst.bins[0].observed_days == 2
    assert sst.bins[0].expected_days == 8
    assert sst.bins[0].missing_days == 6


@pytest.mark.parametrize("value,precision,expected", [
    ("2023-12-31T15:30:00Z", "datetime", "2024-01-01"),
    ("2023-12-31", "date", "2023-12-31"),
    ("2023-12", "month", "2023-12"),
    ("2023-12-31T15:30:00", "datetime", None),
    ("2023-02-30", "date", None),
    ("2023-13", "month", None),
    (None, "date", None),
    ("2023-01-01", "unknown", None),
    (pd.Timestamp("2024-01-18"), "date", "2024-01-18"),
    (pd.Timestamp("2024-01-18T12:00:00"), "date", None),
    (pd.Timestamp("2024-01-18T00:00:00Z"), "date", None),
])
def test_date_precision_and_jst_month_boundaries(value, precision, expected):
    assert service.calendar_value(value, precision) == expected


def test_empty_undated_and_unavailable_are_distinct():
    empty = service.aggregate_source("ctd", [])
    undated = service.aggregate_source("ctd", [("sample", None)])
    unavailable = service.source_definition("ctd")
    assert empty.status == undated.status == "empty"
    assert empty.total_count == 0
    assert undated.total_count == undated.undated_count == 1
    assert unavailable.status == "unavailable"
    assert unavailable.total_count is None


def test_conflicting_duplicate_dates_fail():
    with pytest.raises(ValueError, match="Conflicting"):
        service.aggregate_source("ctd", [("sample", "2024-01-01"), ("sample", "2024-02-01")])


def test_refresh_observes_atomic_replacement(artifacts):
    normalized, _ = artifacts
    old = service.artifact_source("ctd")
    path = normalized / "replacement.parquet"
    pd.DataFrame({"sample_id": ["new"], "ctd_date": ["2026-03-02"]}).to_parquet(path)
    path.replace(normalized / "ctd_summary.parquet")
    new = service.artifact_source("ctd")
    assert new.observed_start == "2026-03-02"
    assert old.source_binding != new.source_binding


def test_ctd_parquet_timestamp_dates_are_lossless_calendar_dates(artifacts):
    normalized, _ = artifacts
    pd.DataFrame({"sample_id": ["a", "b"], "ctd_date": pd.to_datetime(["2024-01-18", "2024-02-15"])}).to_parquet(normalized / "ctd_summary.parquet")
    source = service.artifact_source("ctd")
    assert source.total_count == 2 and source.undated_count == 0
    assert source.observed_start == "2024-01-18"
    assert source.observed_end == "2024-02-15"


def test_changing_artifact_fails_after_bounded_retry(artifacts, monkeypatch):
    revisions = iter([(1, 1, value) for value in range(4)])
    monkeypatch.setattr(service, "_revision", lambda path: next(revisions))
    with pytest.raises(ValueError, match="changed"):
        service.artifact_source("ctd")


def test_api_isolates_dependency_failure_and_sanitizes_response(artifacts, monkeypatch):
    def unavailable():
        raise RuntimeError("private-bucket/path postgres://password SECRET")
    monkeypatch.setattr(service, "edna_source", unavailable)
    response = TestClient(app).get("/overview/coverage")
    assert response.status_code == 200
    payload = response.json()
    assert payload["calendar"] == "Asia/Tokyo"
    assert datetime.fromisoformat(payload["generated_at"]).tzinfo == timezone.utc
    rows = {row["id"]: row for row in payload["sources"]}
    assert rows["ctd"]["total_count"] == 2
    assert rows["edna_metabarcoding"]["status"] == "unavailable"
    assert rows["edna_metabarcoding"]["total_count"] is None
    assert "SECRET" not in response.text and "private-bucket" not in response.text
    assert "password" not in response.text


def test_edna_counts_occurrences_without_claiming_eligibility(monkeypatch):
    rows = [
        dict(sample_id="a", collection_date_utc="2023-12-31T15:30:00Z", temporal_precision="datetime", sample_kind="environmental", is_control=False),
        dict(sample_id="b", collection_date_utc="2023-12-31", temporal_precision="date", sample_kind="negative_control", is_control=True),
        dict(sample_id="c", collection_date_utc=None, temporal_precision=None, sample_kind="unknown", is_control=None),
    ]
    monkeypatch.setattr(service, "read_edna_snapshot", lambda: (rows, {"generation_id": "a" * 64}))
    source = service.edna_source()
    assert source.total_count == 3 and source.undated_count == 1
    assert source.categories == dict(environmental=1, controls=1, unknown_or_other=1)
    assert [item.month for item in source.bins] == ["2023-12", "2024-01"]
    assert source.count_unit == "occurrences"


@pytest.mark.parametrize("role", ["viewer", "researcher", "admin"])
def test_overview_aggregate_permission_is_available_to_existing_roles(role):
    assert route_permission("GET", "/overview/coverage") in ROLE_PERMISSIONS[role]
    if role == "viewer":
        assert route_permission("GET", "/data/edna/samples") not in ROLE_PERMISSIONS[role]


@pytest.mark.parametrize("role", ["viewer", "researcher", "admin"])
def test_authenticated_roles_can_read_aggregates_but_viewer_cannot_read_records(artifacts, monkeypatch, role):
    monkeypatch.setattr(auth, "authenticate_request", lambda request: SimpleNamespace(permissions=ROLE_PERMISSIONS[role]))
    monkeypatch.setattr(service, "read_edna_snapshot", lambda: ([], {}))
    client = TestClient(app)
    assert client.get("/overview/coverage").status_code == 200
    assert client.post("/overview/coverage").status_code == 403
    if role == "viewer":
        assert client.get("/data/edna/samples").status_code == 403


def test_sst_empty_month_keeps_completeness_and_invalid_values(artifacts):
    normalized, _ = artifacts
    pd.DataFrame({"date_jst": ["2026-01-31", "2026-03-01", "2026-02-04", "invalid"],
                  "mean_sst": pd.Series([1., 2., pd.NA, 3.], dtype="Float64")}).to_parquet(normalized / "sst_daily_summary.parquet")
    source = service.artifact_source("remote_sensing")
    middle = source.bins[1]
    assert middle.month == "2026-02" and middle.count == 0
    assert middle.expected_days == middle.missing_days == 28
    assert source.undated_count == 1 and source.excluded_count == 1


@pytest.mark.parametrize("method", ["POST", "PUT", "DELETE", "PATCH"])
def test_coverage_has_no_mutation_permission(method):
    assert route_permission(method, "/overview/coverage") is None


def test_anonymous_coverage_is_denied(monkeypatch):
    monkeypatch.setenv("AUTH_MODE", "required")
    monkeypatch.setenv("DEPLOYMENT_ENV", "test")
    response = TestClient(app).get("/overview/coverage")
    assert response.status_code == 401


class Result:
    def __init__(self, rows):
        self.rows = rows

    def mappings(self):
        return self.rows


class SnapshotConnection:
    def __init__(self, publications):
        self.publications = publications
        self.statements = []

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def begin(self):
        return nullcontext()

    def exec_driver_sql(self, statement):
        self.statements.append(statement)

    def execute(self, statement, params=None):
        self.statements.append(str(statement))
        return Result(self.publications if "corpus_publication" in str(statement) else [])


def test_edna_read_is_canonical_bound_and_read_only(monkeypatch):
    publications = [dict(channel=channel, generation_id="a" * 64, manifest_sha256="b" * 64)
                    for channel in ("anemone-canonical", "edna-canonical")]
    connection = SnapshotConnection(publications)
    class Engine:
        def connect(self):
            return connection
    monkeypatch.setattr(service, "get_engine", Engine)
    rows, binding = service.read_edna_snapshot()
    assert rows == [] and binding["generation_id"] == "a" * 64
    assert "READ ONLY" in connection.statements[0]
    assert "statement_timeout" in connection.statements[1]
    assert "edna_detection" not in " ".join(connection.statements)
    assert "raw_metadata" not in " ".join(connection.statements)
    publications[1]["generation_id"] = "c" * 64
    with pytest.raises(ValueError, match="Canonical publication"):
        service.read_edna_snapshot()


def test_gap_list_is_bounded_but_count_is_exact():
    source = service.aggregate_source("remote_sensing", [("a", "2020-01-01"), ("b", "2022-01-01")])
    assert source.missing_day_count == 730
    assert len(source.missing_dates_within_extent) == service.MAX_MISSING_DATES
    assert source.missing_dates_truncated
