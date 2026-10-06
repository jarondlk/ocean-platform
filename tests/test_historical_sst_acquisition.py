from copy import deepcopy
import io
import json
from urllib.error import HTTPError

import pytest

from ingestion.immutable_bundle import digest
from ingestion.sst_acquisition import (
    acquisition_plan,
    build_history_plan,
    download_batch,
    mur_time_axis,
    mur_source_gap_inventory,
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
