"""Host-safe normalization/OCI binding checks; no image or analysis execution."""

from copy import deepcopy
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from orchestration.experiment_sandbox.profile import rootfs_inventory_sha256
from orchestration.experiment_sandbox.contracts import SandboxError
from sandbox.experiment.gcp import prepare_image_receipts as materializer
from sandbox.experiment.gcp import run_operator_acceptance as operator


@pytest.fixture
def prepared(monkeypatch, tmp_path):
    from sandbox.experiment.gcp import normalize_rootfs

    monkeypatch.setattr(operator, "FIXED_ROOT", tmp_path)
    monkeypatch.setattr(materializer, "FIXED_ROOT", tmp_path)
    source = tmp_path / "scientific-bundle-quota-v3/rootfs"
    destination = tmp_path / "scientific-normalized-quota-v3/rootfs"
    for root in (source, destination):
        (root / "opt/c23").mkdir(parents=True)
        (root / "opt/c23/trusted_init.py").write_bytes(
            b"# synthetic bytes, never executed\n"
        )
    evidence = tmp_path / "evidence"
    evidence.mkdir()
    receipt_path = evidence / "rootfs-normalization-quota-v3.json"
    provenance = {
        "version": "unit-test-mocked-normalizer-validation-only",
        "source_rootfs": str(source),
        "destination_rootfs": str(destination),
        "destination_rootfs_inventory_sha256": rootfs_inventory_sha256(destination),
    }
    raw = operator._canonical(provenance)
    operator._create(receipt_path, raw)
    calls = []

    def verified(document, *, source, destination):
        calls.append((deepcopy(document), Path(source), Path(destination)))
        assert document == provenance
        return deepcopy(document)

    real_validator = normalize_rootfs.verify_normalization_receipt
    monkeypatch.setattr(normalize_rootfs, "verify_normalization_receipt", verified)
    oci = tmp_path / "scientific-oci-quota-v3"
    (oci / "blobs/sha256").mkdir(parents=True)

    def blob(raw):
        digest = operator._sha(raw)
        operator._create(oci / "blobs/sha256" / digest, raw)
        return {"digest": "sha256:" + digest, "size": len(raw)}

    config = blob(operator._canonical({"architecture": "amd64", "os": "linux"}))
    layer = blob(b"synthetic opaque layer bytes; never extracted")
    manifest = {"schemaVersion": 2, "config": config, "layers": [layer]}
    descriptor = blob(operator._canonical(manifest))
    operator._create(
        oci / "oci-layout", operator._canonical({"imageLayoutVersion": "1.0.0"})
    )
    operator._create(
        oci / "index.json",
        operator._canonical({"schemaVersion": 2, "manifests": [descriptor]}),
    )
    packages = {
        name: "1.0"
        for name in (
            "numpy",
            "pandas",
            "pyarrow",
            "scipy",
            "statsmodels",
            "matplotlib",
            "packaging",
        )
    }
    image = {
        "version": "c23-image-preparation-v1",
        "evidence_class": "configuration-only",
        "image_digest": descriptor["digest"],
        "base_image_digest": "sha256:" + "b" * 64,
        "architecture": "amd64",
        "python_version": "3.12.15",
        "lockfile_sha256": "c" * 64,
        "packages": packages,
        "oci_manifest_sha256": descriptor["digest"][7:],
        "oci_config_sha256": config["digest"][7:],
        "layer_sha256": [layer["digest"][7:]],
        "rootfs_inventory_sha256": provenance["destination_rootfs_inventory_sha256"],
    }
    runtime_bytes = {
        "runsc": b"runsc-not-executed",
        "containerd-shim-runsc-v1": b"shim-not-executed",
        "gvisor-bin/platform": b"sidecar-not-executed",
    }
    runtime = {
        "version": "c23-runtime-preparation-v1",
        "evidence_class": "configuration-only",
        "release": "release-20261019.0",
        "architecture": "amd64",
        "files": {name: operator._sha(raw) for name, raw in runtime_bytes.items()},
        "input_host_uid": operator.APP_UID,
        "input_host_gid": operator.APP_GID,
    }
    return SimpleNamespace(
        source=source,
        destination=destination,
        receipt=receipt_path,
        receipt_sha256=operator._sha(raw),
        provenance=provenance,
        calls=calls,
        image=image,
        runtime=runtime,
        runtime_bytes=runtime_bytes,
        oci=oci,
        root=tmp_path,
        evidence=evidence,
        real_validator=real_validator,
    )


def verify(prepared):
    return operator.verify_materials(
        prepared.destination,
        prepared.oci,
        prepared.image,
        prepared.runtime,
        normalization_receipt=prepared.receipt,
        normalization_sha256=prepared.receipt_sha256,
    )


def test_materials_bind_original_oci_and_separate_normalization_provenance(prepared):
    result = verify(prepared)
    assert result["image_preparation"]["image_digest"] == prepared.image["image_digest"]
    assert result["rootfs_normalization"] == {
        "receipt_sha256": prepared.receipt_sha256,
        "provenance": prepared.provenance,
        "source_oci_manifest_digest": prepared.image["image_digest"],
    }
    assert prepared.calls == [
        (prepared.provenance, prepared.source, prepared.destination)
    ]
    assert "copied topology differs" in result["materialization_qualification"]


def test_actual_normalization_verifier_binds_temp_copy_without_relaxing_old_nlink_guard(
    prepared, monkeypatch
):
    from sandbox.experiment.gcp import normalize_rootfs

    # Only synthetic inert bytes on local temporary trees; no cp/image/analysis
    # program is launched. The read-only production verifier runs for real.
    original = prepared.source / "opt/c23/trusted_init.py"
    os.link(original, prepared.source / "alias")
    (prepared.destination / "alias").write_bytes(original.read_bytes())
    assert original.stat().st_nlink == 2
    with pytest.raises(SandboxError, match="sandbox_rootfs_integrity"):
        rootfs_inventory_sha256(prepared.source)
    before = normalize_rootfs.scan_tree(prepared.source)
    copied = normalize_rootfs.scan_tree(prepared.destination, require_single_links=True)
    destination_hash = rootfs_inventory_sha256(prepared.destination)
    document = {
        "version": normalize_rootfs.VERSION,
        "label": "quota-v3",
        "recorded_at": "2026-10-25T09:00:00+00:00",
        "target": {
            "project": operator.PROJECT,
            "instance": operator.INSTANCE,
            "linux_root_guard": True,
        },
        "helper_sha256": operator._sha(Path(normalize_rootfs.__file__).read_bytes()),
        "command": [
            "/usr/bin/cp",
            "-a",
            "--no-preserve=links",
            "--reflink=auto",
            "--",
            str(prepared.source),
            str(prepared.destination),
        ],
        "cp_exit_status": 0,
        "cp_version_sha256": "c" * 64,
        "source_rootfs": str(prepared.source),
        "destination_rootfs": str(prepared.destination),
        "source_semantic_sha256": before["semantic_sha256"],
        "destination_semantic_sha256": copied["semantic_sha256"],
        "source_snapshot_before_sha256": before["snapshot_sha256"],
        "source_snapshot_after_sha256": before["snapshot_sha256"],
        "source_hardlink_topology_sha256": before["hardlink_topology_sha256"],
        "source_counts": before["counts"],
        "destination_counts": copied["counts"],
        "destination_rootfs_inventory_sha256": destination_hash,
        "source_unchanged": True,
        "semantic_equivalence": True,
        "all_regular_nlink_one": True,
        "source_inode_confinement_verified": True,
        "C23_complete": False,
        "dispatch_eligible": False,
    }
    prepared.receipt.unlink()
    raw = operator._canonical(document)
    operator._create(prepared.receipt, raw)
    prepared.receipt_sha256 = operator._sha(raw)
    prepared.image["rootfs_inventory_sha256"] = destination_hash
    monkeypatch.setattr(
        normalize_rootfs, "verify_normalization_receipt", prepared.real_validator
    )
    result = verify(prepared)
    assert result["rootfs_normalization"]["provenance"] == document
    assert result["image_preparation"]["rootfs_inventory_sha256"] == destination_hash
    assert (
        result["rootfs_normalization"]["provenance"]["source_counts"]["hardlink_groups"]
        == 1
    )


@pytest.mark.parametrize(
    "change", ["missing", "wrong_hash", "writable", "different_path", "original_rootfs"]
)
def test_normalization_omission_or_misbinding_refuses_before_validator(
    prepared, change
):
    path, digest, rootfs = (
        prepared.receipt,
        prepared.receipt_sha256,
        prepared.destination,
    )
    if change == "missing":
        path.unlink()
    elif change == "wrong_hash":
        digest = "f" * 64
    elif change == "writable":
        path.chmod(0o600)
    elif change == "different_path":
        other = path.with_name("different.json")
        operator._create(other, path.read_bytes())
        path = other
    else:
        rootfs = prepared.source
    with pytest.raises((operator.OperatorError, OSError)):
        operator.verify_rootfs_normalization(rootfs, path, digest)
    assert prepared.calls == []


def test_normalization_verified_inventory_must_match_strict_image_inventory(prepared):
    prepared.provenance["destination_rootfs_inventory_sha256"] = "d" * 64
    prepared.receipt.unlink()
    raw = operator._canonical(prepared.provenance)
    operator._create(prepared.receipt, raw)
    prepared.receipt_sha256 = operator._sha(raw)
    with pytest.raises(operator.OperatorError, match="normalization_inventory_binding"):
        verify(prepared)


def test_normalized_tree_tamper_is_caught_by_unchanged_strict_inventory(prepared):
    (prepared.destination / "unexpected").write_bytes(b"changed")
    with pytest.raises(operator.OperatorError, match="materialized_rootfs_hash"):
        verify(prepared)
    assert prepared.calls == []


def test_oci_blob_bytes_are_still_checked_after_normalization(prepared):
    path = prepared.oci / "blobs/sha256" / prepared.image["layer_sha256"][0]
    path.chmod(0o600)
    path.write_bytes(b"substituted layer")
    with pytest.raises(operator.OperatorError, match="oci_blob_checksum"):
        verify(prepared)


def test_materialization_guard_precedes_normalization_reads(monkeypatch, tmp_path):
    def denied():
        raise operator.OperatorError("dedicated_linux_root_worker_required")

    monkeypatch.setattr(materializer, "require_worker", denied)
    with pytest.raises(
        operator.OperatorError, match="dedicated_linux_root_worker_required"
    ):
        materializer.record(
            "quota-v3",
            "a" * 64,
            normalization_receipt=tmp_path / "not-read",
            normalization_sha256="b" * 64,
        )


def test_materialization_v2_create_only_records_verified_normalized_copy(
    prepared, monkeypatch
):
    context = prepared.root / "build-context-quota-v3"
    context.mkdir()
    wrapper = (prepared.destination / "opt/c23/trusted_init.py").read_bytes()
    materials = {
        "base_reference": "synthetic@" + prepared.image["base_image_digest"],
        "python_version": prepared.image["python_version"],
        "packages": prepared.image["packages"],
    }
    lock = b"synthetic lock bytes, never installed\n"
    for name, raw in (
        ("trusted_init.py", wrapper),
        ("build-materials.json", operator._canonical(materials)),
        ("requirements.lock", lock),
    ):
        operator._create(context / name, raw)
    operator._create(
        prepared.evidence / "installed-runtime.json",
        operator._canonical(prepared.runtime),
    )
    observation = {
        "python_version": materials["python_version"],
        "packages": materials["packages"],
        "dependency_graph": "verified",
    }
    operator._create(
        prepared.evidence / "image-build-quota-v3.stdout.txt",
        operator._canonical(observation) + b"\n",
    )
    monkeypatch.setattr(materializer, "require_worker", lambda: None)
    monkeypatch.setattr(
        materializer, "validate_materials", lambda *args, **kwargs: None
    )
    actual_read = materializer._read

    def read(path, maximum):
        prefix = "/opt/ocean-c23-runtime/release-20261019.0/"
        if str(path).startswith(prefix):
            return prepared.runtime_bytes[str(path)[len(prefix) :]]
        return actual_read(path, maximum)

    monkeypatch.setattr(materializer, "_read", read)
    result = materializer.record(
        "quota-v3",
        operator._sha(wrapper),
        normalization_receipt=prepared.receipt,
        normalization_sha256=prepared.receipt_sha256,
    )
    assert result["version"] == "c23-worker-materialization-v2"
    assert result["rootfs_normalization"]["receipt_sha256"] == prepared.receipt_sha256
    assert result["rootfs_normalization"]["provenance"] == prepared.provenance
    assert (
        result["rootfs_normalization"]["source_oci_manifest_digest"]
        == prepared.image["image_digest"]
    )
    assert result["image"]["rootfs_inventory_sha256"] == rootfs_inventory_sha256(
        prepared.destination
    )
    assert result["containment_verified"] is result["dispatch_eligible"] is False
    before = (prepared.evidence / "materialization-quota-v3.json").read_bytes()
    assert json.loads(before) == result
    with pytest.raises(FileExistsError):
        materializer.record(
            "quota-v3",
            operator._sha(wrapper),
            normalization_receipt=prepared.receipt,
            normalization_sha256=prepared.receipt_sha256,
        )
    assert (prepared.evidence / "materialization-quota-v3.json").read_bytes() == before
