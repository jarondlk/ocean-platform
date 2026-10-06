from copy import deepcopy
import io
import json
import socket
import ssl
from urllib.error import HTTPError

import pytest

from ingestion.immutable_bundle import digest
from ingestion.sst_acquisition import (
    acquisition_plan,
    build_history_plan,
    download_batch,
    mur_time_axis,
    mur_source_gap_inventory,
    _provider_ipv4_connection,
    ProviderIPv4HTTPSConnection,
    provider_opener,
    inspect_mur_source_original,
)
from ingestion.sst_inventory import build_inventory


def sample(label="one", **changes):
    return {
        "sample_id": digest(label),
        "provider": "anemone",
        "active": True,
        "collection_date_utc": "2020-12-31T16:00:00Z",
        "temporal_precision": "datetime",
        "lat": 38.62,
        "lon": 141.44,
        "sample_kind": "unknown",
        "raw_metadata_json": {"worldmesh": "reported-cell"},
        **changes,
    }


class Opener:
    def __init__(self, *responses):
        self.responses = iter(responses)
        self.calls = 0

    def open(self, url, timeout):
        self.calls += 1
        result = next(self.responses)
        if isinstance(result, BaseException):
            raise result
        return io.BytesIO(result)


def test_inventory_dates_locations_and_unknowns_do_not_infer_review():
    rows = [
        sample(),
        sample("date", collection_date_utc="2017-12-18", temporal_precision="date"),
        sample("missing", lat=None, raw_metadata_json={}, collection_date_utc=None),
        sample("bad-zone", collection_date_utc="2020-01-01T01:00:00"),
    ]
    report = build_inventory(rows, {"basis": "fixture"})
    assert report == build_inventory(rows[::-1], {"basis": "fixture"})
    assert report["sampling_years"] == [2017, 2021]
    assert report["counts"]["source_occurrences"] == 4
    assert report["counts"]["unresolved_occurrences"] == 2
    assert report["counts"]["reported_coordinate_locations"] == 1
    assert report["tiles"][0]["sampling_years"] == [2017, 2021]
    assert report["tiles"][0]["basis"] == "unreviewed_acquisition_envelope"
    assert "date_unresolved" not in str(report["locations"][0])
    with pytest.raises(ValueError, match="Duplicate"):
        build_inventory(rows + [rows[0]], {})


def test_history_full_calendar_partition_budget_and_tampering():
    inventory = build_inventory(
        [sample(collection_date_utc="2020-05-15T00:00:00Z")], {}
    )
    plan = build_history_plan(inventory)
    assert plan["request_count"] == 366
    assert plan["batch_count"] == 36
    assert plan["scientific_publication"] is False
    assert all(len(b["days"]) <= 12 for b in plan["batches"])
    assert plan == build_history_plan(deepcopy(inventory))
    inventory["tiles"][0]["footprint"]["north"] = 50
    with pytest.raises(ValueError, match="checksum"):
        build_history_plan(inventory)


def test_resume_rechecks_bytes_and_preserves_provider_revisions(tmp_path):
    plan = acquisition_plan(["2020-05-15", "2020-05-16"], 38, 39, 140, 141)
    first = Opener(b"CDF\x01first", HTTPError("url", 503, "", {}, None))
    result = download_batch(plan, tmp_path, attempts=1, opener=first)
    assert result["status"].startswith("incomplete")
    assert not (tmp_path / "acquisition.json").exists()
    assert result["outcomes"] == {"acquired": 1, "retryable": 1}
    resumed = Opener(b"CDF\x01second")
    complete = download_batch(plan, tmp_path, opener=resumed)
    assert complete["status"].startswith("complete") and resumed.calls == 1
    original = complete["files"][0]["filename"]
    changed = download_batch(
        plan, tmp_path, opener=Opener(b"CDF\x01revised", b"CDF\x01second"), recheck=True
    )
    assert changed["files"][0]["filename"] != original
    assert (tmp_path / original).exists()
    states = json.loads((tmp_path / "journal.json").read_text())["requests"].values()
    assert sorted(len(s["generations"]) for s in states) == [1, 2]
    (tmp_path / changed["files"][0]["filename"]).write_bytes(b"CDF\x01tampered")
    failed = download_batch(plan, tmp_path, opener=Opener())
    assert failed["outcomes"]["local_integrity_failure"] == 1
    assert not (tmp_path / "acquisition.json").exists()


def test_failures_retries_and_redirect_contract(tmp_path, monkeypatch):
    plan = acquisition_plan(["2020-05-15"], 38, 39, 140, 141)
    delays = []
    retry = HTTPError("url", 429, "", {"Retry-After": "1"}, None)
    result = download_batch(
        plan,
        tmp_path / "retry",
        opener=Opener(retry, b"CDF\x01complete"),
        sleep=delays.append,
    )
    assert result["status"].startswith("complete") and delays == [1]
    for label, response, expected in [
        ("missing", HTTPError("url", 404, "", {}, None), "provider_missing"),
        ("denied", HTTPError("url", 403, "", {}, None), "access_denied"),
        ("html", b"<html>error</html>", "invalid_response"),
    ]:
        out = tmp_path / label
        result = download_batch(plan, out, opener=Opener(response))
        assert result["outcomes"] == {expected: 1}
        assert not (out / "acquisition.json").exists()
        assert not list(out.glob(".download-*"))
    deferred = Opener(HTTPError("url", 429, "", {"Retry-After": "120"}, None))
    assert download_batch(plan, tmp_path / "defer", opener=deferred)["outcomes"] == {
        "retryable": 1
    }
    assert deferred.calls == 1
    monkeypatch.setattr("ingestion.sst_acquisition.MAX_FILE_BYTES", 8)
    small_plan = acquisition_plan(["2020-05-15"], 38, 39, 140, 141)
    assert download_batch(
        small_plan, tmp_path / "oversize", opener=Opener(b"CDF\x01toolong")
    )["outcomes"] == {"oversized": 1}


def test_journal_plan_conflicts_locks_and_symlinks_fail_closed(tmp_path):
    plan = acquisition_plan(["2020-05-15"], 38, 39, 140, 141)
    directory = tmp_path / "data"
    download_batch(plan, directory, opener=Opener(b"CDF\x01original"))
    different = acquisition_plan(["2020-05-16"], 38, 39, 140, 141)
    with pytest.raises(ValueError, match="different plan"):
        download_batch(different, directory)
    (directory / ".acquisition.lock").write_text("another process")
    with pytest.raises(FileExistsError):
        download_batch(plan, directory)
    link = tmp_path / "alias"
    link.symlink_to(directory, target_is_directory=True)
    with pytest.raises(ValueError, match="symlink"):
        download_batch(plan, link)
    modified = deepcopy(plan)
    modified["requests"][0]["source_url"] = "https://untrusted.example"
    modified["plan_sha256"] = digest(
        {k: v for k, v in modified.items() if k != "plan_sha256"}
    )
    with pytest.raises(ValueError, match="provider contract"):
        download_batch(modified, tmp_path / "tampered")


def test_time_axis_exposes_mirror_gaps_and_rejects_wrong_times():
    report, _ = mur_time_axis(
        "2021-02-19",
        "2021-02-22",
        opener=Opener(b"time\nUTC\n2021-02-19T09:00:00Z\n2021-02-22T09:00:00Z\n"),
    )
    assert report["missing_mirror_dates"] == ["2021-02-20", "2021-02-21"]
    assert report["absence_basis"] == "mirror_only_source_archive_not_checked"
    with pytest.raises(ValueError, match="analysis time"):
        mur_time_axis(
            "2020-05-15",
            "2020-05-16",
            opener=Opener(b"time\nUTC\n2020-05-15T00:00:00Z\n"),
        )


def test_source_catalogue_gap_check_never_claims_binary_coverage():
    title = "20210220090000-JPL-L4_GHRSST-SSTfnd-MUR-GLOB-v02.0-fv04.1"
    payload = {
        "feed": {
            "entry": [
                {
                    "id": "G-fixture",
                    "title": title,
                    "links": [
                        {
                            "href": "https://archive.podaac.earthdata.nasa.gov/product/"
                            + title
                            + ".nc"
                        },
                        {"href": "https://untrusted.example/" + title + ".nc"},
                    ],
                }
            ]
        }
    }

    def response(url, timeout):
        stream = io.BytesIO(json.dumps(payload).encode())
        stream.headers = {"CMR-Hits": "1"}
        return stream

    report, _ = mur_source_gap_inventory(
        ["2021-02-20", "2021-02-21"], open_url=response
    )
    assert report["dates_without_catalogue_match"] == ["2021-02-21"]
    assert report["granules"][0]["binary_verified"] is False
    assert len(report["granules"][0]["binary_urls"]) == 1
    assert report["basis"] == "source_archive_metadata_only_binary_not_downloaded"
    payload["feed"]["entry"] = []
    with pytest.raises(ValueError, match="incomplete"):
        mur_source_gap_inventory(["2021-02-20"], open_url=response)


def test_ipv4_provider_connection_is_scoped_and_preserves_tls(monkeypatch):
    from ingestion import sst_acquisition as module

    calls, sockets = [], []
    original_resolver = socket.getaddrinfo

    def addresses(host, port, family, kind):
        calls.append((host, port, family, kind))
        return [
            (family, kind, 6, "", ("192.0.2.1", port)),
            (family, kind, 6, "", ("192.0.2.2", port)),
        ]

    class Connection:
        def __init__(self, *args):
            self.closed = False
            sockets.append(self)

        def settimeout(self, timeout):
            self.timeout = timeout

        def connect(self, target):
            if target[0] == "192.0.2.1":
                raise TimeoutError("unreachable")
            self.target = target

        def close(self):
            self.closed = True

    monkeypatch.setattr(module.socket, "getaddrinfo", addresses)
    monkeypatch.setattr(module.socket, "socket", Connection)
    for address in (("untrusted.example", 443), (module.HOST, 80)):
        with pytest.raises(ValueError, match="approved provider"):
            _provider_ipv4_connection(address)
    connection = _provider_ipv4_connection((module.HOST, 443), 7)
    assert sockets[0].closed and connection.target == ("192.0.2.2", 443)
    assert connection.timeout == 7
    assert calls == [(module.HOST, 443, socket.AF_INET, socket.SOCK_STREAM)]
    tls = ProviderIPv4HTTPSConnection(module.HOST)
    assert tls._context.check_hostname
    assert tls._context.verify_mode == ssl.CERT_REQUIRED
    assert tls._create_connection is _provider_ipv4_connection
    provider_opener(ipv4_only=True)
    # Construction never installs a process-wide resolver override.
    assert module.socket.getaddrinfo is addresses
    monkeypatch.setattr(module.socket, "getaddrinfo", original_resolver)


def test_ipv4_connection_closes_failed_socket_and_rejects_absent_dns(monkeypatch):
    from ingestion import sst_acquisition as module

    monkeypatch.setattr(module.socket, "getaddrinfo", lambda *args: [])
    with pytest.raises(OSError, match="no IPv4"):
        _provider_ipv4_connection((module.HOST, 443))


def mur_original_fixture(
    path, *, version="04.1nrt", title=None, stamp="2021-02-20T09:00:00"
):
    import numpy as np
    import xarray as xr

    ds = xr.Dataset(
        {
            name: (("time", "lat", "lon"), np.ones((1, 2, 2)))
            for name in ("analysed_sst", "analysis_error", "mask", "sea_ice_fraction")
        },
        coords={
            "time": [np.datetime64(stamp)],
            "lat": [38.6, 38.61],
            "lon": [141.4, 141.41],
        },
        attrs={
            "id": "MUR-JPL-L4-GLOB-v04.1",
            "product_version": version,
            "title": title or "Daily MUR SST, Interim near-real-time (nrt) product",
        },
    )
    ds.analysed_sst.attrs["units"] = "kelvin"
    ds.to_netcdf(path)


def test_original_nrt_is_verified_without_resolving_final_series_gap(tmp_path):
    path = tmp_path / "original.nc"
    mur_original_fixture(path)
    result = inspect_mur_source_original(path, "2021-02-20")
    assert result["processing_generation"] == "interim_near_real_time"
    assert result["product_metadata"]["product_version"] == "04.1nrt"
    assert result["final_series_gap_resolved"] is False
    assert result["scientific_approval"] is False
    assert result["receipt_id"] == digest(
        {k: v for k, v in result.items() if k != "receipt_id"}
    )
    mur_original_fixture(path, version="04.1", title="Daily MUR SST, Final product")
    final = inspect_mur_source_original(path, "2021-02-20")
    assert (
        final["processing_generation"] == "final" and not final["scientific_approval"]
    )
    assert final["raw_sha256"] != result["raw_sha256"]


def test_original_date_version_generation_conflicts_and_symlinks_fail(tmp_path):
    path = tmp_path / "original.nc"
    for changes, message in [
        ({"version": "04.2"}, "product/version"),
        ({"stamp": "2021-02-21T09:00:00"}, "time mismatch"),
        ({"version": "04.1"}, "labels disagree"),
    ]:
        mur_original_fixture(path, **changes)
        with pytest.raises(ValueError, match=message):
            inspect_mur_source_original(path, "2021-02-20")
    link = tmp_path / "alias.nc"
    link.symlink_to(path)
    with pytest.raises(ValueError, match="regular file"):
        inspect_mur_source_original(link, "2021-02-20")
