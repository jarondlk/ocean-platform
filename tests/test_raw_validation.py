"""Tests for strict raw-source contracts and scientific input validation."""
from __future__ import annotations

import json
from pathlib import Path

from ingestion import raw_validation


SAMPLE_ID = "2024-01-O-s1"
SAMPLE_REPLICATE = f"{SAMPLE_ID}.1"


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _configure_minimal_sources(tmp_path: Path, monkeypatch):
    raw_dir = tmp_path / "raw"
    sources = {
        "ctd": _write(
            raw_dir / "ctd.tsv",
            "date\tlabel\tdepth\ttemperature\n"
            f"2024-01-18\t{SAMPLE_ID}\t0\t12.3\n",
        ),
        "runid": _write(
            raw_dir / "runid.tsv",
            f"r0001\t{SAMPLE_REPLICATE}\t2024-01-18\n",
        ),
        "read_summary": _write(
            raw_dir / "reads.tsv",
            f"{SAMPLE_REPLICATE}\t10\t100\t2\t20\n",
        ),
        "coverage_log": _write(
            raw_dir / "coverage.tsv",
            f"{SAMPLE_REPLICATE}.txt\t0.1\t10\t100\n",
        ),
        "kraken_genus_sample_tsv": _write(
            raw_dir / "kraken.tsv",
            f"{SAMPLE_ID}\nGenusA\t1.0\n",
        ),
        "kraken_genus_sample_txt": _write(
            raw_dir / "kraken.txt",
            f"{SAMPLE_ID}\nGenusA\t1.0\n",
        ),
        "kraken_upper_group_sample": _write(
            raw_dir / "upper.txt",
            f"\t{SAMPLE_ID}\nGroupA\tDomain:Group A\t1.0\n",
        ),
        "kraken_genus_group": _write(
            raw_dir / "kraken-group.tsv",
            "genus_txid\tgenus_name\tupper_txid\tupper_name\n",
        ),
        "metaeuk_genus_sample": _write(
            raw_dir / "metaeuk.tsv",
            f"{SAMPLE_ID}\nGenusA\t1.0\n",
        ),
        "genus_group": _write(
            raw_dir / "genus-group.tsv",
            "1\tGenusA\t2\tGroupA\n",
        ),
        "gn_consistency": _write(
            raw_dir / "gn.tsv",
            "1\t3\tGenusA\n",
        ),
        "km_consistency": _write(
            raw_dir / "km.tsv",
            "contig\tm\t3\t\t\t1\t\t\t\t\t\n",
        ),
    }
    sst_dir = tmp_path / "sst"
    _write(sst_dir / "JCPT_DA_JPN03_SST_20240118_1200.nc", "fixture")
    contract = {
        "schema_version": 1,
        "allowed_date_start": "2000-01-01",
        "allowed_future_days": 366,
        "maximum_row_drop_ratio": 0.2,
        "sources": {
            name: {
                "minimum_rows": 1,
                **(
                    {"columns": 4}
                    if name == "ctd"
                    else {"columns": 3}
                    if name in {"runid", "gn_consistency"}
                    else {"columns": 5}
                    if name == "read_summary"
                    else {"columns": 4}
                    if name
                    in {
                        "coverage_log",
                        "kraken_genus_group",
                        "genus_group",
                    }
                    else {"columns": 11}
                    if name == "km_consistency"
                    else {"minimum_sample_columns": 1}
                ),
            }
            for name in sources
        },
        "sst": {"minimum_files": 1},
    }
    contract_path = tmp_path / "contract.json"
    contract_path.write_text(json.dumps(contract), encoding="utf-8")
    monkeypatch.setattr(raw_validation.config, "RAW_FILES", sources)
    monkeypatch.setattr(raw_validation.config, "SST_NETCDF_DIR", sst_dir)
    return sources, contract_path


def test_strict_raw_validation_accepts_contract_compliant_sources(
    tmp_path,
    monkeypatch,
):
    _, contract_path = _configure_minimal_sources(tmp_path, monkeypatch)
    report_path = tmp_path / "validation.json"

    report = raw_validation.validate_raw_sources(
        contract_path=contract_path,
        report_path=report_path,
    )

    assert report.ok is True
    assert report.errors == 0
    assert report.sst_files == 1
    assert len(report.sst_collection_hash or "") == 64
    assert report_path.exists()
    assert all(len(source.sha256 or "") == 64 for source in report.sources)


def test_strict_raw_validation_rejects_duplicate_ctd_keys(
    tmp_path,
    monkeypatch,
):
    sources, contract_path = _configure_minimal_sources(tmp_path, monkeypatch)
    with sources["ctd"].open("a", encoding="utf-8") as handle:
        handle.write(f"2024-01-18\t{SAMPLE_ID}\t0\t12.4\n")

    report = raw_validation.validate_raw_sources(
        contract_path=contract_path,
        report_path=tmp_path / "validation.json",
    )

    assert report.ok is False
    assert any(
        issue.code == "duplicate_profile_keys"
        for issue in report.issues
    )


def test_validation_detects_large_row_count_regression(
    tmp_path,
    monkeypatch,
):
    _, contract_path = _configure_minimal_sources(tmp_path, monkeypatch)
    report_path = tmp_path / "validation.json"
    first = raw_validation.validate_raw_sources(
        contract_path=contract_path,
        report_path=report_path,
    )
    payload = first.to_dict()
    payload["sources"][0]["rows"] = 100
    report_path.write_text(json.dumps(payload), encoding="utf-8")

    second = raw_validation.validate_raw_sources(
        contract_path=contract_path,
        report_path=report_path,
        write_report=False,
    )

    assert any(
        issue.code == "unexpected_row_count_drop"
        for issue in second.issues
    )
