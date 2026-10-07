from copy import deepcopy
import hashlib
import io
import json
from urllib.error import HTTPError
from urllib.request import Request

import numpy as np
import pytest
import xarray as xr

from ingestion.immutable_bundle import digest
from ingestion.sst_nasa_subset import (
    _NoRedirect,
    download_nasa_pilot,
    nasa_opener,
    nasa_subset_plan,
    validate_nasa_pilot,
)


def plan():
    return nasa_subset_plan(
        [
            {
                "day": "2019-01-01",
                "role": "native_patch",
                "footprint": {
                    "south": 38.37,
                    "north": 38.48,
                    "west": 141.42,
                    "east": 141.53,
                },
            }
        ]
    )


def fixture(tmp_path, request, **attrs):
    ds = xr.Dataset(
        {
            v: (("time", "lat", "lon"), np.ones((1, 12, 12)))
            for v in ("analysed_sst", "analysis_error", "mask", "sea_ice_fraction")
        },
        coords={
            "time": [np.datetime64("2019-01-01T09:00:00")],
            "lat": np.arange(3837, 3849) / 100,
            "lon": np.arange(14142, 14154) / 100,
        },
        attrs={
            "title": "Daily MUR SST, Final product",
            "product_version": "04.1",
            **attrs,
        },
    )
    ds.analysed_sst.attrs["units"] = "kelvin"
    ds.analysis_error.attrs["units"] = "kelvin"
    path = tmp_path / "fixture.nc"
    ds.to_netcdf(path, engine="netcdf4")
    data = path.read_bytes()
    sha = hashlib.sha256(data).hexdigest()
    entry = {
        **request,
        "bytes": len(data),
        "filename": request["day"] + "-" + sha + ".nc",
        "raw_sha256": sha,
        "granule_id": digest({"source_url": request["source_url"], "raw_sha256": sha}),
    }
    return data, entry


def test_nasa_origin_credential_permissions_redirect_and_no_receipt_secret(tmp_path):
    credential = tmp_path / "token"
    secret = "a" * 110 + ".bbb.ccc"
    credential.write_text(secret)
    credential.chmod(0o600)
    calls = []
    data, _ = fixture(tmp_path, plan()["requests"][0])

    class Transport:
        def open(self, request, *, timeout):
            calls.append(request)
            return io.BytesIO(data)

    opener = nasa_opener(credential, transport=Transport())
    with pytest.raises(ValueError, match="destination"):
        opener.open("https://example.com/test", timeout=30)
    assert calls == []
    with pytest.raises(ValueError, match="redirect"):
        _NoRedirect().redirect_request(
            Request(plan()["requests"][0]["source_url"]),
            None,
            302,
            "redirect",
            {},
            "https://example.com/",
        )
    manifest = download_nasa_pilot(
        plan(), tmp_path / "raw", credential, transport=Transport()
    )
    assert calls[0].get_header("Authorization") == "Bearer " + secret
    assert manifest["status"] == "complete_unapproved_acquisition"
    assert secret not in json.dumps(manifest)
    assert secret not in (tmp_path / "raw" / "journal.json").read_text()

    class Never:
        def open(self, *args, **kwargs):
            raise AssertionError("retained bytes must be reused")

    resumed = download_nasa_pilot(
        plan(), tmp_path / "raw", credential, transport=Never()
    )
    assert resumed["files"] == manifest["files"]
    credential.chmod(0o644)
    with pytest.raises(ValueError, match="private"):
        nasa_opener(credential)
    credential.chmod(0o600)
    link = tmp_path / "link"
    link.symlink_to(credential)
    with pytest.raises(ValueError, match="symlink"):
        nasa_opener(link)


def test_nasa_final_container_coordinates_units_and_byte_tampering(tmp_path):
    p = plan()
    data, entry = fixture(tmp_path, p["requests"][0])
    manifest = {
        "status": "complete_unapproved_acquisition",
        "plan": p,
        "files": [entry],
    }
    result = validate_nasa_pilot(manifest, {entry["filename"]: data}, p)
    assert result["scientific_approval"] is False
    assert result["requests"][0]["finite_ocean_pixels"] == 144
    with pytest.raises(ValueError, match="byte/identity"):
        validate_nasa_pilot(manifest, {entry["filename"]: data + b"x"}, p)
    nrt, nrt_entry = fixture(tmp_path, p["requests"][0], product_version="04.1nrt")
    manifest["files"] = [nrt_entry]
    with pytest.raises(ValueError, match="final MUR"):
        validate_nasa_pilot(manifest, {nrt_entry["filename"]: nrt}, p)


def test_nasa_single_day_contract_does_not_hide_full_archive_request_cost():
    descriptor = {k: plan()["requests"][0][k] for k in ("day", "role", "footprint")}
    excluded = deepcopy(descriptor)
    excluded["day"] = "2021-02-20"
    with pytest.raises(ValueError, match="final-generation"):
        nasa_subset_plan([excluded])
    with pytest.raises(ValueError, match="1–16"):
        nasa_subset_plan([descriptor] * 17)
    with pytest.raises(ValueError, match="Duplicate"):
        nasa_subset_plan([descriptor] * 2)
    invalid = deepcopy(descriptor)
    invalid["footprint"]["south"] = 38.371
    with pytest.raises(ValueError, match="envelope"):
        nasa_subset_plan([invalid])
    context = deepcopy(descriptor)
    context["role"] = "context"
    assert nasa_subset_plan([context])["plan_sha256"] != plan()["plan_sha256"]


def test_nasa_denied_access_has_sanitized_persistent_journal(tmp_path):
    credential = tmp_path / "token"
    credential.write_text("a" * 110 + ".bbb.ccc")
    credential.chmod(0o600)

    class Denied:
        def open(self, request, *, timeout):
            raise HTTPError(
                request.full_url, 401, "private provider text", {}, io.BytesIO()
            )

    manifest = download_nasa_pilot(
        plan(), tmp_path / "raw", credential, transport=Denied()
    )
    assert manifest["status"] == "incomplete_unapproved_acquisition"
    assert manifest["outcomes"] == {"access_denied": 1}
    journal = (tmp_path / "raw" / "journal.json").read_text()
    assert "private provider text" not in journal
    assert (
        json.loads(journal)["requests"][next(iter(json.loads(journal)["requests"]))][
            "http_status"
        ]
        == 401
    )
