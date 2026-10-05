import io
from urllib.request import Request

import pytest

from ingestion.immutable_bundle import digest
from scripts import prepare_research_sst as acquisition


def test_preflight_is_deterministic_bounded_and_declares_product():
    args = ["2020-05-15", "2023-05-15"]
    plan = acquisition.acquisition_plan(args, 38.58, 38.68, 141.37, 141.52)
    assert (
        acquisition.acquisition_plan(args[::-1] + args, 38.58, 38.68, 141.37, 141.52)
        == plan
    )
    assert plan["maximum_download_bytes"] == 2 * acquisition.MAX_FILE_BYTES
    assert plan["status"] == "unapproved_pilot" and plan["cloud_writes"] is False
    assert "analysis_error" in plan["requests"][0]["source_url"]
    assert plan["measurement_type"] == "satellite_in_situ_analysis"
    with pytest.raises(ValueError, match="bounded"):
        acquisition.acquisition_plan(args, 30, 40, 140, 141)
    with pytest.raises(ValueError, match="bounded"):
        acquisition.acquisition_plan(args, float("nan"), 39, 140, 141)
    with pytest.raises(ValueError, match="interval"):
        acquisition.acquisition_plan(["2000-01-01"], 38, 39, 140, 141)


def test_download_has_no_completed_manifest_for_bad_or_partial_response(
    tmp_path, monkeypatch
):
    plan = acquisition.acquisition_plan(["2020-05-15"], 38, 39, 140, 141)

    class Opener:
        def open(self, url, timeout):
            return io.BytesIO(b"<html>provider error</html>")

    monkeypatch.setattr(acquisition, "build_opener", lambda handler: Opener())
    destination = tmp_path / "pilot"
    with pytest.raises(ValueError, match="not NetCDF"):
        acquisition.download_pilot(plan, destination)
    assert not (destination / "pilot.json").exists()
    with pytest.raises(FileExistsError):
        acquisition.download_pilot(plan, destination)
    changed = {
        **plan,
        "requests": [
            {**plan["requests"][0], "source_url": "https://elsewhere.example"}
        ],
    }
    changed["plan_sha256"] = digest(
        {k: v for k, v in changed.items() if k != "plan_sha256"}
    )
    with pytest.raises(ValueError, match="provider contract"):
        acquisition.download_pilot(changed, tmp_path / "changed")


def test_redirect_cannot_leave_https_provider():
    handler = acquisition.SameProviderRedirect()
    req = Request(acquisition.ENDPOINT)
    for destination in (
        "http://coastwatch.pfeg.noaa.gov/file",
        "https://elsewhere.example/file",
        "https://user:secret@coastwatch.pfeg.noaa.gov/file",
    ):
        with pytest.raises(ValueError, match="outside"):
            handler.redirect_request(req, None, 302, "", {}, destination)
