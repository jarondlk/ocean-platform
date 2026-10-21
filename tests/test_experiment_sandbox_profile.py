"""Pure C23 profile fixtures: no image, binary, runtime or code is executed."""

from copy import deepcopy
from dataclasses import FrozenInstanceError
import hashlib
import importlib.util
import json
import os
from pathlib import Path

import pytest

from orchestration.experiment_sandbox.contracts import (
    SandboxError,
    verify_execution_envelope,
)
from orchestration.experiment_sandbox.profile import (
    render_oci_profile,
    rootfs_inventory_sha256,
)
from schema.research_experiments import EnvironmentDescriptor, content_sha256
from tests.test_experiment_sandbox_contracts import (
    approved_envelope as _retained_fixture,
)

approved_envelope = _retained_fixture


def _sha(value):
    return hashlib.sha256(value.encode()).hexdigest()


def _structural_envelope(approved, *, resources=None):
    """Resign a *test-only* shape; this is no retained real approval/admission."""
    raw, _, _, _, _ = approved
    metadata = deepcopy(raw["metadata"])
    descriptor = EnvironmentDescriptor(
        kind="linux-gvisor",
        test_only=False,
        python_version="3.12.0",
        image_digest="sha256:" + _sha("synthetic image; not built"),
        lockfile_sha256=_sha("synthetic lock; not installable"),
        packages={
            name: "1.0.0"
            for name in (
                "numpy",
                "pandas",
                "pyarrow",
                "scipy",
                "statsmodels",
                "matplotlib",
                "packaging",
            )
        },
        description="Synthetic structural descriptor only; no installed image or actual approval",
    )
    metadata["environment"] = descriptor.model_dump(mode="json")
    metadata["proposal"]["environment_id"] = descriptor.identity_sha256
    if resources:
        metadata["proposal"]["resources"].update(resources)
    proposal = metadata["proposal"]
    metadata["manifest"]["proposal_sha256"] = content_sha256(proposal)
    metadata["hashes"] = {
        "proposal_sha256": content_sha256(proposal),
        "code_sha256": hashlib.sha256(proposal["python_code"].encode()).hexdigest(),
        "input_manifest_sha256": content_sha256(metadata["manifest"]),
        "environment_sha256": descriptor.identity_sha256,
        "resources_sha256": content_sha256(proposal["resources"]),
    }
    return verify_execution_envelope(
        {"metadata": metadata, "files": raw["files"]},
        expected_envelope_sha256=content_sha256(metadata),
        environments={descriptor.identity_sha256: descriptor.model_dump(mode="json")},
    )


def _layout(tmp_path, envelope):
    job = (tmp_path / envelope.job_id).resolve()
    job.mkdir(mode=0o700)
    inputs = job / "inputs"
    inputs.mkdir(mode=0o700)
    for name, value in {
        **envelope.files,
        "analysis.py": envelope.code,
        "manifest.json": envelope.manifest_bytes,
    }.items():
        p = inputs / name
        p.write_bytes(value)
        p.chmod(0o400)
    inputs.chmod(0o500)
    rootfs = job / "rootfs"
    rootfs.mkdir(mode=0o700)
    # Intentionally not an executable image. Hash/config tests cannot run it.
    (rootfs / "synthetic-image.txt").write_text(
        "Synthetic configuration fixture, not an image or runtime"
    )
    image = {
        "version": "c23-image-preparation-v1",
        "evidence_class": "configuration-only",
        "image_digest": envelope.environment["image_digest"],
        "base_image_digest": "sha256:" + _sha("synthetic base"),
        "architecture": "arm64",
        "python_version": envelope.environment["python_version"],
        "lockfile_sha256": envelope.environment["lockfile_sha256"],
        "packages": envelope.environment["packages"],
        "oci_manifest_sha256": envelope.environment["image_digest"][7:],
        "oci_config_sha256": _sha("synthetic config"),
        "layer_sha256": [_sha("synthetic layer")],
        "rootfs_inventory_sha256": rootfs_inventory_sha256(rootfs),
    }
    owner = (inputs / "analysis.py").stat()
    assert owner.st_uid != 0 and owner.st_gid != 0, "Use a non-root local/CI test owner"
    runtime = {
        "version": "c23-runtime-preparation-v1",
        "evidence_class": "configuration-only",
        "release": "release-20000101.0",
        "architecture": "arm64",
        "files": {
            "runsc": _sha("synthetic runsc"),
            "containerd-shim-runsc-v1": _sha("synthetic shim"),
            "gvisor-bin/synthetic-sidecar": _sha("synthetic sidecar"),
        },
        "input_host_uid": owner.st_uid,
        "input_host_gid": owner.st_gid,
    }
    return envelope, job, image, runtime


@pytest.fixture
def prepared(tmp_path, approved_envelope):
    return _layout(tmp_path, _structural_envelope(approved_envelope))


def render(prepared, **changes):
    envelope, job, image, runtime = prepared
    return render_oci_profile(
        envelope,
        job_root=changes.get("job_root", job),
        image_receipt=changes.get("image", image),
        runtime_manifest=changes.get("runtime", runtime),
    )


def test_fixed_profile_is_deterministic_and_never_eligible(prepared):
    a, b = render(prepared), render(prepared)
    assert a.profile_sha256 == b.profile_sha256 and a.document == b.document
    assert a.dispatch_eligible is False and a.document["dispatch_eligible"] is False
    assert a.document["evidence_class"] == "configuration-only"
    assert a.requirements["actual_linux_gvisor_verified"] is False
    assert a.requirements["production_dispatch_built"] is False
    assert len(a.requirements["unverified"]) == 8
    assert a.document["declared_seeds"] == prepared[0].proposal["seeds"]
    assert a.document["proposal_hashes"] == prepared[0].metadata["hashes"]
    assert not any("PYTHONHASHSEED=" in value for value in a.config["process"]["env"])


def test_read_only_root_minimal_namespace_process_and_guest_storage(prepared):
    profile = render(prepared)
    config = profile.config
    assert config["root"] == {"path": "rootfs", "readonly": True}
    process = config["process"]
    assert process["user"] == {"uid": 65532, "gid": 65532, "additionalGids": []}
    assert process["noNewPrivileges"] and not process["terminal"]
    assert process["args"] == [
        "/usr/local/bin/python3",
        "-I",
        "-B",
        "/inputs/analysis.py",
    ]
    assert all(value == [] for value in process["capabilities"].values())
    assert {tuple(value.items()) for value in config["linux"]["namespaces"]} == {
        (("type", name),)
        for name in ("pid", "mount", "ipc", "uts", "network", "user", "cgroup")
    }
    assert not {"hooks", "annotations", "devices"} & config.keys()
    assert "devices" not in config["linux"]
    inputs = config["mounts"][0]
    assert inputs["destination"] == "/inputs" and inputs["source"] == str(
        prepared[1] / "inputs"
    )
    assert "ro" in inputs["options"] and "rw" not in inputs["options"]
    writable = [m for m in config["mounts"] if "rw" in m["options"]]
    assert {m["destination"] for m in writable} == {"/outputs", "/scratch"}
    assert all(m["type"] == "tmpfs" and m["source"] == "tmpfs" for m in writable)
    assert all({"noexec", "nosuid", "nodev"} <= set(m["options"]) for m in writable)
    for forbidden in ("DOCKER_HOST=", "HTTP_PROXY=", "GOOGLE_", "AWS_", "PYTHONPATH="):
        assert not any(value.startswith(forbidden) for value in process["env"])


def test_flags_have_no_network_overlay_rootless_override_or_host_ipc(prepared):
    flags = render(prepared).runtime_args
    assert {
        "--network=none",
        "--directfs=false",
        "--overlay2=none",
        "--rootless=false",
        "--host-uds=none",
        "--host-fifo=none",
        "--ignore-cgroups=false",
        "--allow-flag-override=false",
        "--gofer-network-namespace=new",
        "--sidecar-release-enforcement-policy=ALWAYS",
    } <= set(flags)
    assert not any(value in {"run", "start", "create", "exec"} for value in flags)
    assert all("network-proxy" not in value for value in flags)


def test_budget_and_kernel_readback_plan_remain_within_approval(prepared):
    profile = render(prepared)
    resources = prepared[0].resources
    limits, expected = profile.config["linux"]["resources"], profile.requirements
    assert limits["cpu"] == {"period": 100000, "quota": resources["cpus"] * 100000}
    assert limits["memory"] == {
        "limit": resources["memory_bytes"],
        "swap": resources["memory_bytes"],
    }
    assert limits["pids"] == {"limit": 128}
    assert expected["readback_before_start"]["memory.swap.max"] == 0
    assert expected["external_wall_watchdog_seconds"] == resources["wall_seconds"]
    total = sum(
        expected[key]
        for key in (
            "output_file_budget_bytes",
            "stdout_max_bytes",
            "stderr_max_bytes",
            "output_manifest_max_bytes",
        )
    )
    assert total <= resources["max_output_bytes"]
    assert (
        expected["output_file_budget_bytes"] % 4096
        == expected["scratch_max_bytes"] % 4096
        == 0
    )


def test_narrow_resources_shrink_without_rounding_up(tmp_path, approved_envelope):
    envelope = _structural_envelope(
        approved_envelope,
        resources={
            "cpus": 1,
            "wall_seconds": 3,
            "memory_bytes": 64 * 1024**2,
            "max_output_bytes": 10001,
        },
    )
    profile = render(_layout(tmp_path, envelope))
    assert profile.requirements["output_file_budget_bytes"] == 4096
    assert profile.config["linux"]["resources"]["cpu"]["quota"] == 100000
    assert profile.requirements["external_wall_watchdog_seconds"] == 3


@pytest.mark.parametrize(
    "resources", [{"memory_bytes": 64 * 1024**2 + 1}, {"max_output_bytes": 8191}]
)
def test_unsupported_allocation_units_fail_closed(
    tmp_path, approved_envelope, resources
):
    with pytest.raises(SandboxError, match="sandbox_profile_unavailable"):
        render(
            _layout(
                tmp_path, _structural_envelope(approved_envelope, resources=resources)
            )
        )


def test_no_fake_environment_upgrade(prepared, approved_envelope):
    raw, expected, registry, _, _ = approved_envelope
    fake = verify_execution_envelope(
        raw, expected_envelope_sha256=expected, environments=registry
    )
    with pytest.raises(SandboxError):
        render_oci_profile(
            fake,
            job_root=prepared[1],
            image_receipt=prepared[2],
            runtime_manifest=prepared[3],
        )


@pytest.mark.parametrize(
    "key,value",
    [
        ("image_digest", "sha256:" + "f" * 64),
        ("lockfile_sha256", "f" * 64),
        ("python_version", "3.12.1"),
        ("architecture", "amd64"),
        ("oci_manifest_sha256", "f" * 64),
        ("rootfs_inventory_sha256", "f" * 64),
        ("rootfs_path", "/Users/private"),
        ("hooks", {"prestart": ["sh"]}),
        ("dispatch_eligible", True),
    ],
)
def test_image_mismatch_and_hostile_fields(prepared, key, value):
    image = deepcopy(prepared[2])
    image[key] = value
    with pytest.raises(SandboxError):
        render(prepared, image=image)


@pytest.mark.parametrize(
    "package",
    [
        "pip",
        "setuptools",
        "sqlalchemy",
        "google-cloud-storage",
        "azure-identity",
        "openai",
    ],
)
def test_application_installer_and_cloud_packages_rejected(prepared, package):
    image = deepcopy(prepared[2])
    image["packages"][package] = "1.0.0"
    with pytest.raises(SandboxError):
        render(prepared, image=image)


@pytest.mark.parametrize(
    "key,value",
    [
        ("release", "latest"),
        ("rootless", True),
        ("flags", ["--network=host"]),
        ("input_host_uid", 0),
        ("input_host_gid", 0),
        ("input_host_uid", True),
        ("ready", True),
    ],
)
def test_runtime_shortcuts_and_supplied_flags_fail(prepared, key, value):
    runtime = deepcopy(prepared[3])
    runtime[key] = value
    with pytest.raises(SandboxError):
        render(prepared, runtime=runtime)


@pytest.mark.parametrize(
    "change", ["runsc", "shim", "sidecar", "alias", "escape", "wrong_hash"]
)
def test_complete_runtime_release_manifest_is_required(prepared, change):
    runtime = deepcopy(prepared[3])
    files = runtime["files"]
    if change == "runsc":
        del files["runsc"]
    elif change == "shim":
        del files["containerd-shim-runsc-v1"]
    elif change == "sidecar":
        del files["gvisor-bin/synthetic-sidecar"]
    elif change == "alias":
        files["gvisor-bin//synthetic-sidecar"] = files.pop(
            "gvisor-bin/synthetic-sidecar"
        )
    elif change == "escape":
        files["gvisor-bin/../../host"] = _sha("host")
    else:
        files["runsc"] = "mutable-binary"
    with pytest.raises(SandboxError):
        render(prepared, runtime=runtime)


@pytest.mark.parametrize(
    "change", ["tamper", "writable", "symlink", "hardlink", "extra", "missing"]
)
def test_actual_staged_files_are_rechecked(prepared, change):
    inputs = prepared[1] / "inputs"
    inputs.chmod(0o700)
    code = inputs / "analysis.py"
    if change == "tamper":
        code.chmod(0o600)
        code.write_bytes(code.read_bytes() + b"# tampered")
        code.chmod(0o400)
    elif change == "writable":
        code.chmod(0o600)
    elif change == "symlink":
        code.unlink()
        code.symlink_to("manifest.json")
    elif change == "hardlink":
        os.link(code, prepared[1] / "outside-code")
    elif change == "extra":
        (inputs / "credential.json").write_text("{}")
    else:
        code.unlink()
    with pytest.raises(SandboxError):
        render(prepared)


def test_paths_cannot_alias_or_escape_private_root(prepared, tmp_path):
    alias = tmp_path / "alias"
    alias.symlink_to(prepared[1], target_is_directory=True)
    with pytest.raises(SandboxError):
        render(prepared, job_root=alias)
    prepared[1].chmod(0o755)
    with pytest.raises(SandboxError):
        render(prepared)


def test_rootfs_and_state_roots_cannot_be_symlinked(prepared, tmp_path):
    rootfs = prepared[1] / "rootfs"
    saved = tmp_path / "rootfs-saved"
    rootfs.rename(saved)
    rootfs.symlink_to(saved, target_is_directory=True)
    with pytest.raises(SandboxError):
        render(prepared)
    rootfs.unlink()
    saved.rename(rootfs)
    state = prepared[1].parent / ("runsc-state-" + prepared[0].job_id)
    state.symlink_to(rootfs, target_is_directory=True)
    with pytest.raises(SandboxError):
        render(prepared)


def test_rootfs_byte_tamper_rejects_old_materialization(prepared):
    (prepared[1] / "rootfs/synthetic-image.txt").write_text("changed image tree")
    with pytest.raises(SandboxError):
        render(prepared)


@pytest.mark.parametrize("change", ["escape_link", "fifo", "hardlink"])
def test_rootfs_special_and_escaping_objects_are_never_opened(prepared, change):
    rootfs = prepared[1] / "rootfs"
    if change == "escape_link":
        (rootfs / "link").symlink_to("../../host-private")
    elif change == "fifo":
        os.mkfifo(rootfs / "fifo")
    else:
        os.link(rootfs / "synthetic-image.txt", prepared[1] / "external-linked-copy")
    with pytest.raises(SandboxError, match="sandbox_rootfs_integrity"):
        rootfs_inventory_sha256(rootfs)


def test_rootfs_guest_absolute_symlink_is_hashed_without_following(tmp_path):
    root = tmp_path / "image"
    root.mkdir()
    (root / "guest-link").symlink_to("/not-an-existing-host-path/c23")
    assert len(rootfs_inventory_sha256(root)) == 64


def test_rootfs_inventory_limits_and_streams_files(prepared, monkeypatch):
    import orchestration.experiment_sandbox.profile as module

    rootfs = prepared[1] / "rootfs"
    file = rootfs / "large-scientific-library"
    file.write_bytes(b"x" * (2 * 1024**2 + 1))
    calls, actual = [], module.os.read

    def bounded(fd, count):
        calls.append(count)
        assert count <= 1024**2
        return actual(fd, count)

    monkeypatch.setattr(module.os, "read", bounded)
    rootfs_inventory_sha256(rootfs)
    assert calls
    monkeypatch.setattr(module, "MAX_ROOTFS_BYTES", 10)
    with pytest.raises(SandboxError):
        rootfs_inventory_sha256(rootfs)


def test_directory_discovery_stops_before_materializing_unbounded_names(
    tmp_path, monkeypatch
):
    import orchestration.experiment_sandbox.profile as module

    root = tmp_path / "image"
    root.mkdir()
    calls = []

    class Entry:
        def __init__(self, name):
            self.name = name

    class Many:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

        def __iter__(self):
            for i in range(1000000):
                calls.append(i)
                yield Entry(str(i))

    monkeypatch.setattr(module.os, "scandir", lambda _: Many())
    monkeypatch.setattr(module, "MAX_ROOTFS_ENTRIES", 3)
    with pytest.raises(SandboxError):
        rootfs_inventory_sha256(root)
    assert calls == [0, 1, 2, 3]


def test_pending_siblings_consume_global_discovery_budget(tmp_path, monkeypatch):
    import orchestration.experiment_sandbox.profile as module

    root = tmp_path / "image"
    root.mkdir()
    (root / "a").mkdir()
    (root / "b").write_text("deferred sibling")
    for name in ("c", "d"):
        (root / "a" / name).write_text("child")
    seen, original = [], module.os.stat

    def observed(name, *args, **kwargs):
        if name in {"c", "d"}:
            seen.append(name)
        return original(name, *args, **kwargs)

    monkeypatch.setattr(module.os, "stat", observed)
    monkeypatch.setattr(module, "MAX_ROOTFS_ENTRIES", 3)
    with pytest.raises(SandboxError):
        rootfs_inventory_sha256(root)
    assert not seen  # a,b plus c exhaust discovery; d refuses before child reads.


def test_prepared_document_is_defensively_detached(prepared):
    profile = render(prepared)
    profile.config["process"]["args"][0] = "/bin/sh"
    profile.document["runtime_preparation"]["files"].clear()
    profile.requirements["actual_linux_gvisor_verified"] = True
    assert profile.config["process"]["args"][0] == "/usr/local/bin/python3"
    assert profile.document["runtime_preparation"]["files"]
    assert profile.requirements["actual_linux_gvisor_verified"] is False
    with pytest.raises(FrozenInstanceError):
        profile.profile_sha256 = "0" * 64
    with pytest.raises(TypeError):
        render_oci_profile(
            prepared[0],
            job_root=prepared[1],
            image_receipt=prepared[2],
            runtime_manifest=prepared[3],
            environment={"HTTP_PROXY": "http://host"},
        )


@pytest.fixture(scope="module")
def image_helper():
    path = Path(__file__).resolve().parents[1] / "sandbox/experiment/verify_image.py"
    spec = importlib.util.spec_from_file_location("c23_image_material_helper", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def materials():
    # These strings are synthetic syntax fixtures, never accepted wheel pins.
    packages = {
        name: "1.0.0"
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
    lock = "".join(
        f"{name}=={version} --hash=sha256:{'a' * 64}\n"
        for name, version in packages.items()
    ).encode()
    base = "python:3.12.0-slim@sha256:" + "b" * 64
    document = {
        "version": "c23-scientific-build-v1",
        "base_reference": base,
        "python_version": "3.12.0",
        "lockfile_sha256": hashlib.sha256(lock).hexdigest(),
        "packages": packages,
    }
    return document, lock, base


def test_dedicated_complete_hash_lock_and_base_are_bound(image_helper, materials):
    document, lock, base = materials
    actual = image_helper.validate_materials(document, lock, base_reference=base)
    actual["packages"].clear()
    assert document["packages"]
    with pytest.raises(image_helper.MaterialError):
        image_helper.validate_materials(document, lock, base_reference="python:latest")
    with pytest.raises(image_helper.MaterialError):
        image_helper.validate_materials(
            document, lock, base_reference="another@sha256:" + "c" * 64
        )
    with pytest.raises(image_helper.MaterialError):
        image_helper.validate_materials(
            document, lock + b"# modified\n", base_reference=base
        )


@pytest.mark.parametrize(
    "line",
    [
        "numpy>=1 --hash=sha256:" + "a" * 64,
        "numpy==1.0.0",
        "numpy==1.0.0 --hash=sha512:" + "a" * 64,
        "numpy==1.0.0 --hash=sha256:" + "z" * 64,
        "numpy[extra]==1.0.0 --hash=sha256:" + "a" * 64,
        'numpy==1.0.0; python_version>="3.9" --hash=sha256:' + "a" * 64,
        "numpy @ https://host/private.whl --hash=sha256:" + "a" * 64,
        "--index-url https://untrusted.example",
        "-r other.lock",
        "-e ./source",
        "numpy==1.0.0 \\",
        "# no real pins",
    ],
)
def test_lock_cannot_hide_sources_options_markers_or_unpinned_values(
    image_helper, materials, line
):
    document, lock, base = materials
    changed = line.encode() + b"\n" + b"\n".join(lock.splitlines()[1:])
    document["lockfile_sha256"] = hashlib.sha256(changed).hexdigest()
    with pytest.raises(image_helper.MaterialError):
        image_helper.validate_materials(document, changed, base_reference=base)


@pytest.mark.parametrize(
    "change",
    [
        "missing_science",
        "unlocked",
        "duplicate_alias",
        "pip",
        "database",
        "cloud",
        "unknown",
        "python_patch",
    ],
)
def test_build_manifest_cannot_reuse_serving_dependencies(
    image_helper, materials, change
):
    document, lock, base = materials
    if change == "missing_science":
        del document["packages"]["statsmodels"]
    elif change == "unlocked":
        document["packages"]["numpy"] = "latest"
    elif change == "duplicate_alias":
        document["packages"]["NumPy"] = "1.0.0"
    elif change == "pip":
        document["packages"]["pip"] = "1.0.0"
    elif change == "database":
        document["packages"]["sqlalchemy"] = "1.0.0"
    elif change == "cloud":
        document["packages"]["google-cloud-storage"] = "1.0.0"
    elif change == "unknown":
        document["ready"] = True
    else:
        document["python_version"] = "3.12"
    with pytest.raises(image_helper.MaterialError):
        image_helper.validate_materials(document, lock, base_reference=base)


def test_installer_cleanup_is_unavailable_on_normal_host(image_helper, monkeypatch):
    monkeypatch.delenv("OCEAN_C23_IMAGE_BUILD", raising=False)
    with pytest.raises(
        image_helper.MaterialError, match="explicit scientific image build"
    ):
        image_helper.strip_installers()


def test_no_installable_materials_or_ready_image_are_invented(image_helper):
    folder = Path(__file__).resolve().parents[1] / "sandbox/experiment"
    assert not (folder / "build-materials.json").exists()
    assert not (folder / "requirements.lock").exists()
    readiness = json.loads((folder / "image-readiness.json").read_text())
    assert readiness["ready"] is readiness["dispatch_eligible"] is False
    assert readiness["built_image_digest"] is None
    template = json.loads((folder / "build-materials.template.json").read_text())
    with pytest.raises(image_helper.MaterialError):
        image_helper.validate_materials(
            template,
            (folder / "requirements.lock.template").read_bytes(),
            base_reference=None,
        )
    recipe = (folder / "Containerfile").read_text()
    assert "ARG SCIENTIFIC_BASE" in recipe and "FROM ${SCIENTIFIC_BASE}" in recipe
    assert (
        "--no-index" in recipe
        and "--require-hashes" in recipe
        and "--only-binary=:all:" in recipe
    )
    assert "--strip-installers" in recipe and "--verify-installed" in recipe
    assert "COPY . " not in recipe and "Containerfile.api" not in recipe
    assert "api/" not in recipe and "GOOGLE_" not in recipe and "AWS_" not in recipe
