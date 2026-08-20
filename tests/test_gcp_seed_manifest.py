from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from scripts.build_gcp_seed_manifest import build_seed_manifest


def _write(path: Path, value: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(value)


def test_seed_manifest_is_bounded_and_content_addressed(tmp_path: Path):
    raw_dir = tmp_path / "data" / "raw"
    sst_dir = tmp_path / "sst"
    _write(raw_dir / "ctd" / "CTD.tsv", b"ctd")
    _write(raw_dir / "meta" / "sample.tsv", b"meta")
    _write(raw_dir / ".DS_Store", b"ignored")
    _write(sst_dir / "202601" / "one.nc", b"one")
    _write(sst_dir / "202601" / "two.nc", b"two")
    _write(sst_dir / "202601" / ".DS_Store", b"ignored")

    manifest = build_seed_manifest(
        raw_dir=raw_dir,
        sst_dir=sst_dir,
        required_raw_relative=["ctd/CTD.tsv", "meta/sample.tsv"],
        minimum_sst_files=2,
        generated_at="2026-08-20T00:00:00+00:00",
    )

    assert manifest["total_objects"] == 4
    assert manifest["total_bytes"] == len(b"ctdmetaonetwo")
    assert manifest["groups"]["ctd_metagenome"]["objects"] == 2
    assert manifest["groups"]["sst_netcdf"]["objects"] == 2
    destinations = [item["destination"] for item in manifest["objects"]]
    assert destinations == [
        "raw/ctd/CTD.tsv",
        "raw/meta/sample.tsv",
        "raw/sst-netcdf/202601/one.nc",
        "raw/sst-netcdf/202601/two.nc",
    ]
    first = manifest["objects"][0]
    assert first["sha256"] == hashlib.sha256(b"ctd").hexdigest()
    assert len(manifest["collection_sha256"]) == 64


def test_seed_manifest_rejects_unexpected_raw_file(tmp_path: Path):
    raw_dir = tmp_path / "raw"
    sst_dir = tmp_path / "sst"
    _write(raw_dir / "expected.tsv", b"expected")
    _write(raw_dir / "generated.parquet", b"must not upload")
    _write(sst_dir / "one.nc", b"one")

    with pytest.raises(ValueError, match="unexpected raw files"):
        build_seed_manifest(
            raw_dir=raw_dir,
            sst_dir=sst_dir,
            required_raw_relative=["expected.tsv"],
            minimum_sst_files=1,
        )


def test_seed_manifest_enforces_sst_contract(tmp_path: Path):
    raw_dir = tmp_path / "raw"
    sst_dir = tmp_path / "sst"
    _write(raw_dir / "expected.tsv", b"expected")
    _write(sst_dir / "one.nc", b"one")

    with pytest.raises(ValueError, match="at least 2 SST files"):
        build_seed_manifest(
            raw_dir=raw_dir,
            sst_dir=sst_dir,
            required_raw_relative=["expected.tsv"],
            minimum_sst_files=2,
        )
