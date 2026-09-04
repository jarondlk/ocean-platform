"""Non-target files are inventoried, never downloaded or analyzed by this MVP."""

from copy import deepcopy
import hashlib
import json

import pandas as pd
import pytest

import config
import ingestion.anemone as acquisition
from preprocessing.anemone import (
    AnemoneNormalizationError,
    build_anemone_bundle,
    snapshot_contract,
    stable_sha256,
)
from preprocessing.anemone_classification import review_template
from tests.test_anemone_ingestion import (
    PROJECT,
    RUN,
    SAMPLE,
    _credentials,
    _fixture_server,
    _local_contract,
    _scope,
)


NON_TARGET_FILES = ("community_qc_nontarget.tsv.xz", "community_qc3nn_nontarget.tsv.xz")
LEGACY_PATH = config.PROJECT_ROOT / "data_contracts/history/anemone_mifish_v1.json"


def add_non_targets(payloads, names=NON_TARGET_FILES):
    prefix = f"/dist/MiFish/ANEMONE/{PROJECT}/{RUN}/{SAMPLE}/"
    for name in names:
        payloads[prefix] = payloads[prefix].replace(
            b"</body>", f'<a href="{name}">{name}</a></body>'.encode()
        )
        # Invalid XZ is intentional: metadata-only files must not be downloaded
        # or passed to the target-community TSV validator/parser.
        payloads[prefix + name] = b"unexamined non-target payload" * 1000


@pytest.mark.parametrize("level", ["sample", "run"])
@pytest.mark.parametrize(
    "names", [NON_TARGET_FILES[:1], NON_TARGET_FILES[1:], NON_TARGET_FILES]
)
def test_nontargets_are_optional_bounded_metadata_only(tmp_path, level, names):
    contract = acquisition.load_contract()
    with _fixture_server(contract) as (base, payloads, server):
        local = _local_contract(base)
        base_result = acquisition.sync_anemone(
            _scope(base, level=level),
            credentials=_credentials(),
            execute=True,
            output_root=tmp_path / "raw",
            contract=local,
            allow_insecure_http=True,
        )
        original = build_anemone_bundle(
            base_result["snapshot_id"], raw_root=tmp_path / "raw", contract=local
        )
        add_non_targets(payloads, names)
        server.requests.clear()
        result = acquisition.sync_anemone(
            _scope(base, level=level),
            credentials=_credentials(),
            execute=True,
            output_root=tmp_path / "raw",
            contract=local,
            allow_insecure_http=True,
            max_files=13 + len(names),
            max_bytes=base_result["downloaded_bytes"],
        )
        non_targets = [
            item for item in result["files"] if item["role"].endswith("_nontarget")
        ]
        assert len(non_targets) == len(names)
        assert all(item["selection_status"] == "metadata_only" for item in non_targets)
        assert all(
            item["validation_status"] == "not_downloaded" for item in non_targets
        )
        assert all(
            item["sha256"] is None and item["row_count"] is None for item in non_targets
        )
        assert result["selected_file_count"] == 5
        assert result["contract_version"] == 2
        assert result["downloaded_bytes"] == base_result["downloaded_bytes"]
        source_gets = [
            path
            for method, path, _ in server.requests
            if method == "GET" and not path.endswith("/")
        ]
        assert len(source_gets) == 5
        assert not any("nontarget" in path for path in source_gets)
        limited = acquisition.inventory_anemone(
            _scope(base, level=level),
            credentials=_credentials(),
            contract=local,
            allow_insecure_http=True,
            max_files=13,
        )
        assert not limited.ok
        assert "file_limit_exceeded" in {issue.code for issue in limited.issues}

    bundle = build_anemone_bundle(
        result["snapshot_id"], raw_root=tmp_path / "raw", contract=local
    )
    files = bundle.frames["external_source_file"]
    assert len(files) == 13 + len(names)
    assert len(files[files["role"].str.endswith("_nontarget")]) == len(names)
    assert len(bundle.frames["edna_detection"]) == 2
    assert set(bundle.frames["edna_detection"]["assignment_method"]) == {
        "qcauto_target",
        "qcauto_95pct_3nn_target",
    }
    for table, identity in (
        ("edna_sample", "sample_id"),
        ("edna_assay", "assay_id"),
        ("edna_detection", "detection_id"),
    ):
        columns = [identity, "scientific_content_sha256"]
        pd.testing.assert_frame_equal(
            original.frames[table][columns], bundle.frames[table][columns]
        )
    raw_files = list(
        (tmp_path / "raw" / "snapshots" / result["snapshot_id"]).rglob("*nontarget*")
    )
    assert raw_files == []


def test_nontargets_cannot_replace_required_target_files(tmp_path):
    contract = acquisition.load_contract()
    with _fixture_server(contract) as (base, payloads, _):
        add_non_targets(payloads)
        prefix = f"/dist/MiFish/ANEMONE/{PROJECT}/{RUN}/{SAMPLE}/"
        # Keep the valid filename visible but outside its exact contract name.
        payloads[prefix] = payloads[prefix].replace(
            b"community_qc_target.tsv.xz", b"community_qc_target_extra.tsv.xz"
        )
        payloads[prefix + "community_qc_target_extra.tsv.xz"] = b"unsupported"
        result = acquisition.inventory_anemone(
            _scope(base),
            credentials=_credentials(),
            contract=_local_contract(base),
            allow_insecure_http=True,
        )
    codes = {issue.code for issue in result.issues}
    assert {"required_file_missing", "unknown_source_file"} <= codes


def test_contract_history_is_hash_pinned_and_unknown_contracts_fail():
    legacy = acquisition.load_contract(LEGACY_PATH)
    assert (
        stable_sha256(legacy)
        == "958c8df592571219dd4dbc2c5b454c03501ffc86b855f84fe8ae2c8d100356da"
    )
    current = acquisition.load_contract()
    for contract in (legacy, current):
        assert acquisition.load_contract_by_hash(stable_sha256(contract)) == contract
    assert stable_sha256(legacy) != stable_sha256(current)
    with pytest.raises(acquisition.AnemoneError, match="approved source contract"):
        acquisition.load_contract_by_hash("0" * 64)


def test_old_snapshot_uses_original_contract_without_rewriting_source(
    tmp_path, monkeypatch
):
    legacy = acquisition.load_contract(LEGACY_PATH)
    current = acquisition.load_contract()
    with _fixture_server(legacy) as (base, _, _):
        local_legacy = {**legacy, "base_url": base}
        result = acquisition.sync_anemone(
            _scope(base),
            credentials=_credentials(),
            execute=True,
            output_root=tmp_path,
            contract=local_legacy,
            allow_insecure_http=True,
        )
    sid = result["snapshot_id"]
    root = tmp_path / "snapshots" / sid
    before = {
        p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in root.iterdir()
    }
    expected = build_anemone_bundle(sid, raw_root=tmp_path, contract=local_legacy)

    # The fixture's HTTP origin differs from production; retain that origin in
    # both repository-contract candidates for the automatic resolver test.
    def loader(path=config.ANEMONE_CONTRACT_PATH):
        selected = legacy if path == LEGACY_PATH else current
        return {**deepcopy(selected), "base_url": local_legacy["base_url"]}

    monkeypatch.setattr(acquisition, "load_contract", loader)
    assert snapshot_contract(sid, raw_root=tmp_path) == local_legacy
    actual = build_anemone_bundle(sid, raw_root=tmp_path)
    assert actual.normalization_id == expected.normalization_id
    assert actual.contract_sha256 == stable_sha256(local_legacy)
    assert review_template(sid, raw_root=tmp_path)["status"] == "draft"
    assert before == {
        p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in root.iterdir()
    }
    path = root / "manifest.json"
    manifest = json.loads(path.read_text())
    manifest["contract_sha256"] = "0" * 64
    path.write_text(json.dumps(manifest))
    with pytest.raises(AnemoneNormalizationError) as failure:
        build_anemone_bundle(sid, raw_root=tmp_path)
    assert failure.value.code == "snapshot_contract_unknown"
