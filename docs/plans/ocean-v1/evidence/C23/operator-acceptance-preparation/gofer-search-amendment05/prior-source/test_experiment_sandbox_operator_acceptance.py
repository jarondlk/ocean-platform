"""Pure operator fixture/guard tests; no guest analysis, mount or cgroup runs."""

import ast
import base64
from copy import deepcopy
import hashlib
import os
from pathlib import Path
import subprocess
import textwrap
from types import SimpleNamespace
import urllib.error

import pytest

from sandbox.experiment.gcp import run_operator_acceptance as operator
from orchestration.experiment_sandbox.contracts import SandboxError


@pytest.fixture(scope="module")
def blueprint(tmp_path_factory):
    path = tmp_path_factory.mktemp("operator-blueprint") / "blueprint.json"
    metadata = operator.prepare_blueprint(path)
    assert metadata["analysis_executed"] is False
    assert metadata["sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()
    return operator.load_blueprint(path)


@pytest.fixture
def image():
    # Non-executable, configuration-only identities. Actual CLI verifies real
    # OCI blobs/rootfs before any adapter call; these are pure fixture tests.
    return {
        "version": "c23-image-preparation-v1",
        "evidence_class": "configuration-only",
        "image_digest": "sha256:" + "a" * 64,
        "base_image_digest": "sha256:" + "b" * 64,
        "architecture": "amd64",
        "python_version": "3.12.15",
        "lockfile_sha256": "c" * 64,
        "packages": {
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
        },
        "oci_manifest_sha256": "a" * 64,
        "oci_config_sha256": "d" * 64,
        "layer_sha256": ["e" * 64],
        "rootfs_inventory_sha256": "f" * 64,
    }


def fixture(blueprint, image, name="smoke", nonce="1" * 32):
    return operator.make_operator_fixture(
        blueprint,
        image,
        name,
        nonce,
        host_canary="/operator-synthetic/host-canary",
        host_socket="/operator-synthetic/host.sock",
    )


def test_actual_fake_service_blueprint_is_explicitly_not_real_c22_approval(blueprint):
    assert blueprint["purpose"] == "operator-owned synthetic acceptance"
    assert blueprint["retained_C22_real_approval"] is False
    assert blueprint["real_C22_reservation_consumption_verified"] is False
    assert blueprint["metadata"]["environment"]["kind"] == "c22-fake"
    assert blueprint["metadata"]["execution_performed"] is False
    assert len(blueprint["files_base64"]) == 3


def test_case_programs_are_ast_only_distinct_and_bound_to_image_and_exact_int64(
    blueprint, image
):
    identifiers, hashes, codes = set(), set(), set()
    original = deepcopy(blueprint)
    for name in operator.cases():
        wrapper = fixture(blueprint, image, name)
        envelope = operator.verify_operator_fixture(wrapper)
        assert (
            wrapper["purpose"] == operator.PURPOSE
            and wrapper["retained_C22_real_approval"] is False
        )
        assert wrapper["real_C22_reservation_consumption_verified"] is False
        assert envelope.environment["image_digest"] == image["image_digest"]
        assert envelope.environment["lockfile_sha256"] == image["lockfile_sha256"]
        assert envelope.metadata["scientific_approval"] == "not_independently_verified"
        assert len(envelope.code) <= 32768
        assert isinstance(ast.parse(envelope.code), ast.Module)
        assert b"9223372036854775807" in b"".join(envelope.files.values())
        assert envelope.job_id not in identifiers
        assert envelope.envelope_sha256 not in hashes
        assert envelope.metadata["hashes"]["code_sha256"] not in codes
        identifiers.add(envelope.job_id)
        hashes.add(envelope.envelope_sha256)
        codes.add(envelope.metadata["hashes"]["code_sha256"])
    assert len(identifiers) == 21
    assert blueprint == original


def test_attempt_nonce_changes_job_without_changing_retained_fake_blueprint(
    blueprint, image
):
    first = operator.verify_operator_fixture(fixture(blueprint, image, nonce="1" * 32))
    second = operator.verify_operator_fixture(fixture(blueprint, image, nonce="2" * 32))
    assert (
        first.job_id != second.job_id
        and first.envelope_sha256 != second.envelope_sha256
    )
    assert first.metadata["reservation_id"] != second.metadata["reservation_id"]
    assert first.files == second.files


@pytest.mark.parametrize(
    "field", ["retained_C22_real_approval", "real_C22_reservation_consumption_verified"]
)
@pytest.mark.parametrize("value", [True, 0, None, "false"])
def test_operator_wrapper_cannot_claim_real_c22_authority(
    blueprint, image, field, value
):
    wrapper = fixture(blueprint, image)
    wrapper[field] = value
    with pytest.raises(operator.OperatorError, match="authority"):
        operator.verify_operator_fixture(wrapper)


def test_retained_operator_fixture_admission_rereads_exact_immutable_bytes(
    blueprint, image, tmp_path
):
    wrapper = fixture(blueprint, image)
    envelope = operator.verify_operator_fixture(wrapper)
    path = tmp_path / "operator.json"
    raw = operator._canonical(wrapper)
    operator._create(path, raw)
    assert (
        operator._admission(path, operator._sha(raw), envelope)
        == envelope.envelope_sha256
    )
    path.chmod(0o600)
    with pytest.raises(operator.OperatorError, match="not_immutable"):
        operator._admission(path, operator._sha(raw), envelope)
    path.write_bytes(raw + b" ")
    path.chmod(0o400)
    with pytest.raises(operator.OperatorError, match="changed"):
        operator._admission(path, operator._sha(raw), envelope)


def test_operator_fixture_rejects_resigned_mismatched_inner_code(blueprint, image):
    wrapper = fixture(blueprint, image)
    wrapper["metadata"]["proposal"]["python_code"] = 'print("changed")\n'
    wrapper["operator_envelope_sha256"] = hashlib.sha256(
        operator._canonical(wrapper["metadata"])
    ).hexdigest()
    with pytest.raises(SandboxError):
        operator.verify_operator_fixture(wrapper)


def test_cli_run_refuses_on_mac_before_imports_or_privileged_effects(
    monkeypatch, tmp_path
):
    called = []
    monkeypatch.setattr(operator.sys, "platform", "darwin")
    monkeypatch.setattr(operator.subprocess, "run", lambda *a, **k: called.append(a))
    with pytest.raises(
        operator.OperatorError, match="dedicated_linux_root_worker_required"
    ):
        operator.main(
            [
                "run",
                "--case",
                "smoke",
                "--attempt-dir",
                str(tmp_path / "never-created"),
                "--blueprint",
                str(tmp_path / "not-read"),
                "--blueprint-sha256",
                "a" * 64,
                "--host-controls",
                str(tmp_path / "host-controls"),
                "--host-controls-sha256",
                "b" * 64,
                "--network-isolation",
                str(tmp_path / "isolation"),
                "--network-isolation-sha256",
                "c" * 64,
                "--normalization-receipt",
                str(tmp_path / "normalization"),
                "--normalization-sha256",
                "d" * 64,
            ]
        )
    assert called == [] and not (tmp_path / "never-created").exists()


@pytest.mark.parametrize(
    "failure", ["uid", "euid", "arch", "hostname", "project", "instance"]
)
def test_worker_target_guard_refuses_wrong_identity(monkeypatch, failure):
    monkeypatch.setattr(operator.sys, "platform", "linux")
    monkeypatch.setattr(operator.os, "getuid", lambda: 501 if failure == "uid" else 0)
    monkeypatch.setattr(operator.os, "geteuid", lambda: 501 if failure == "euid" else 0)
    monkeypatch.setattr(
        operator.os,
        "uname",
        lambda: SimpleNamespace(machine="arm64" if failure == "arch" else "x86_64"),
    )
    monkeypatch.setattr(
        operator.socket,
        "gethostname",
        lambda: "wrong" if failure == "hostname" else operator.INSTANCE,
    )
    reads = []

    def metadata(name):
        reads.append(name)
        if name == "project/project-id":
            return "legacy-project" if failure == "project" else operator.PROJECT
        return "wrong-instance" if failure == "instance" else operator.INSTANCE

    with pytest.raises(operator.OperatorError):
        operator.require_worker(metadata)
    if failure in {"uid", "euid", "arch", "hostname"}:
        assert reads == []


def test_worker_guard_checks_both_fixed_metadata_values(monkeypatch):
    monkeypatch.setattr(operator.sys, "platform", "linux")
    monkeypatch.setattr(operator.os, "getuid", lambda: 0)
    monkeypatch.setattr(operator.os, "geteuid", lambda: 0)
    monkeypatch.setattr(operator.os, "uname", lambda: SimpleNamespace(machine="x86_64"))
    monkeypatch.setattr(operator.socket, "gethostname", lambda: operator.INSTANCE)
    reads = []

    def metadata(name):
        reads.append(name)
        return operator.PROJECT if name == "project/project-id" else operator.INSTANCE

    assert operator.require_worker(metadata)["linux_root_guard"] is True
    assert reads == ["project/project-id", "instance/name"]


@pytest.mark.parametrize(
    "path",
    [
        "relative",
        "/tmp/test",
        "/var/lib/ocean-c23/operator-acceptance/../escape",
        "/var/lib/ocean-c23/operator-acceptance/nested/attempt",
        "/var/lib/ocean-c23/operator-acceptance/UPPER",
    ],
)
def test_attempt_paths_cannot_escape_fixed_operator_root(path):
    with pytest.raises(operator.OperatorError, match="attempt_path"):
        operator.check_attempt_path(path)


def test_attempt_path_is_exact_single_child():
    value = operator.ATTEMPTS_ROOT / "smoke-unique123"
    assert operator.check_attempt_path(value) == value


def test_blueprint_and_receipt_writes_are_create_only_and_nofollow(tmp_path):
    target = tmp_path / "retained.json"
    operator._create(target, b"original")
    with pytest.raises(FileExistsError):
        operator._create(target, b"replacement")
    assert target.read_bytes() == b"original" and target.stat().st_mode & 0o777 == 0o400
    alias = tmp_path / "alias"
    alias.symlink_to(target)
    with pytest.raises(operator.OperatorError):
        operator._read(alias, 1024)
    os.link(target, tmp_path / "hardlink")
    with pytest.raises(operator.OperatorError):
        operator._read(target, 1024)


def actual_like_document(state="completed", reason="completed"):
    return {
        "state": state,
        "reason": reason,
        "dispatch_eligible": False,
        "reservation_released": False,
        "scientific_approval": "not_independently_verified",
        "execution_started": True,
        "termination_proof": {
            "whole_host_subtree_empty": True,
            "populated": 0,
            "runtime_delete_acknowledged": True,
        },
        "outputs_manifest_sha256": "a" * 64 if state == "completed" else None,
    }


def test_evaluation_never_turns_unknown_termination_into_acceptance():
    document = actual_like_document()
    clean = {"rootfs_unmounted": True}
    assert operator.evaluate_case("smoke", document, {}, clean, elapsed=1)[
        "case_assertions_passed"
    ]
    document["termination_proof"] = None
    assert not operator.evaluate_case("smoke", document, {}, clean, elapsed=1)[
        "case_assertions_passed"
    ]
    document = actual_like_document()
    document["reservation_released"] = True
    assert not operator.evaluate_case("smoke", document, {}, clean, elapsed=1)[
        "case_assertions_passed"
    ]


def test_memory_case_needs_actual_cgroup_limit_event_and_cleanup():
    document = actual_like_document("uncertain", "sandbox_runtime_uncertain")
    clean = {"rootfs_unmounted": True}
    assert not operator.evaluate_case(
        "memory", document, {"available": True, "memory.events": {}}, clean, elapsed=1
    )["case_assertions_passed"]
    result = operator.evaluate_case(
        "memory",
        document,
        {"available": True, "memory.events": {"oom_kill": 1}},
        clean,
        elapsed=1,
    )
    assert result["case_assertions_passed"] and result["C23_complete"] is False
    assert not operator.evaluate_case(
        "memory",
        document,
        {"available": True, "memory.events": {"oom_kill": 1}},
        {"rootfs_unmounted": False},
        elapsed=1,
    )["case_assertions_passed"]


def test_cpu_case_requires_observed_throttling():
    document = actual_like_document()
    clean = {"rootfs_unmounted": True}
    assert not operator.evaluate_case("cpu", document, {}, clean, elapsed=1)[
        "case_assertions_passed"
    ]
    assert operator.evaluate_case(
        "cpu",
        document,
        {"cpu.stat": {"nr_throttled": 2, "throttled_usec": 50}},
        clean,
        elapsed=1,
    )["case_assertions_passed"]


def test_wall_cancel_logs_and_unsafe_cases_have_specific_failure_expectations():
    clean = {"rootfs_unmounted": True}
    for name, state, reason in [
        ("wall", "timed_out", "wall_limit"),
        ("cancel", "cancelled", "cancelled"),
        ("logs", "failed", "log_limit"),
        ("unsafe-fifo", "failed", "adapter_failure"),
    ]:
        result = operator.evaluate_case(
            name, actual_like_document(state, reason), {}, clean, elapsed=12
        )
        assert result["case_assertions_passed"] and result["C23_complete"] is False
    assert not operator.evaluate_case(
        "wall", actual_like_document("timed_out", "wall_limit"), {}, clean, elapsed=25
    )["case_assertions_passed"]


def numerical_attempt(name):
    return {
        "purpose": operator.PURPOSE,
        "retained_C22_real_approval": False,
        "case": name,
        "evaluation": {"case_assertions_passed": True},
        "adapter_result": {
            "state": "completed",
            "declared_seeds": {"numpy": 20261024},
            "image_digest": "sha256:" + "a" * 64,
            "approved_hashes": {"environment_sha256": "b" * 64},
            "runtime_sha256": "c" * 64,
            "trusted_init_sha256": "d" * 64,
            "adapter_source_sha256": "e" * 64,
        },
        "comparison_configuration": {
            "resources": {"wall_seconds": 30, "memory_bytes": 512 * 1024**2},
            "rootfs_materialization": {
                "rootfs_inventory_sha256": "f" * 64,
                "normalization_receipt_sha256": "1" * 64,
            },
            "normalized_init_policy": {
                "version": "test-only",
                "max_output_bytes": 65536,
            },
        },
        "summary_table": {
            "columns": ["probe", "value"],
            "rows": [
                ["mean", 0.1],
                ["t_statistic", 0.5],
                ["p_value", 0.6],
                ["ols_intercept", 1.0],
                ["ols_slope", 2.0],
                ["exact_int64", 2**63 - 1],
            ],
        },
    }


def test_repeat_numerics_require_same_image_explicit_seed_exact_int64_and_tolerance():
    first, second = numerical_attempt("numerics-a"), numerical_attempt("numerics-b")
    result = operator.compare_numerics(first, second)
    assert (
        result["repeated_numerics_within_tolerance"] and result["exact_int64_preserved"]
    )
    assert (
        result["scientific_approval"] == "not_independently_verified"
        and result["C23_complete"] is False
    )
    second["summary_table"]["rows"][0][1] = 0.1001
    assert not operator.compare_numerics(first, second)[
        "repeated_numerics_within_tolerance"
    ]
    second = numerical_attempt("numerics-b")
    second["summary_table"]["rows"][-1][1] = float(2**63 - 1)
    with pytest.raises(operator.OperatorError, match="summary_identity"):
        operator.compare_numerics(first, second)


@pytest.mark.parametrize(
    "change", ["image", "seed", "approval", "not_completed", "nonfinite"]
)
def test_numerics_cannot_hide_changed_environment_or_unaccepted_attempt(change):
    first, second = numerical_attempt("numerics-a"), numerical_attempt("numerics-b")
    if change == "image":
        second["adapter_result"]["image_digest"] = "sha256:" + "c" * 64
    elif change == "seed":
        second["adapter_result"]["declared_seeds"] = {"numpy": 7}
    elif change == "approval":
        second["retained_C22_real_approval"] = True
    elif change == "not_completed":
        second["adapter_result"]["state"] = "uncertain"
    else:
        second["summary_table"]["rows"][0][1] = float("nan")
    with pytest.raises(operator.OperatorError):
        operator.compare_numerics(first, second)


def test_raster_case_uses_canvas_and_pillow_not_metadata_png_defaults():
    body = operator.cases()["raster"].body
    assert "FigureCanvasAgg" in body and "Image.fromarray" in body
    assert "format='PNG'" in body and "savefig" not in body
    assert "pnginfo" not in body


def test_numerics_body_declares_all_scientific_packages_and_explicit_seed():
    for name in ("numerics-a", "numerics-b"):
        case = operator.cases()[name]
        assert case.seeds == {"numpy": 20261024}
        for value in (
            "numpy",
            "pandas",
            "pyarrow",
            "scipy",
            "statsmodels",
            "default_rng(20261024)",
        ):
            assert value in case.body


def test_containment_case_includes_all_non_output_write_mounts_and_canaries():
    body = operator.cases()["containment"].body
    for value in (
        "/tmp/c23-write",
        "/dev/shm/c23-write",
        "/run/c23-write",
        "/var/tmp/c23-write",
        "HOST_CANARY",
        "HOST_SOCKET",
        "169.254.169.254",
        "1.1.1.1",
        "/proc/1/fd/1",
        "socket.if_nameindex()",
        "interface_names == {'lo'}",
        "/proc/net/route",
    ):
        assert value in body


def test_blueprint_decoding_cannot_replace_frozen_machine_bytes(blueprint, tmp_path):
    changed = deepcopy(blueprint)
    name = next(iter(changed["files_base64"]))
    changed["files_base64"][name] = base64.b64encode(b"changed").decode()
    path = tmp_path / "changed.json"
    operator._create(path, operator._canonical(changed))
    with pytest.raises(SandboxError):
        operator.load_blueprint(path)


def network_receipts():
    target = {
        "project": operator.PROJECT,
        "instance": operator.INSTANCE,
        "linux_root_guard": True,
    }
    boot = "11111111-1111-4111-8111-111111111111"
    host = {
        "version": "c23-host-positive-controls-v1",
        "purpose": operator.PURPOSE,
        "target": {**target, "host_boot_id": boot, "instance_id": "12345"},
        "monotonic_ns": 1000,
        "host_external_tcp_connect": True,
        "metadata_read_positive": True,
        "untrusted_execution_performed": False,
        "external_endpoint": {"address": "1.1.1.1", "port": 443},
    }
    isolated = {
        "version": "c23-host-network-isolation-v1",
        "project": operator.PROJECT,
        "instance": operator.INSTANCE,
        "host_boot_id": boot,
        "complete_router_inventory": True,
        "observed_monotonic_ns": 2000,
        "instance_resource": {
            "name": operator.INSTANCE,
            "id": "12345",
            "status": "RUNNING",
            "zone": operator.GCP_API
            + "projects/"
            + operator.PROJECT
            + "/zones/asia-northeast1-a",
            "networkInterfaces": [
                {"network": operator.NETWORK, "subnetwork": operator.SUBNET}
            ],
        },
        "routers": [],
        "network_resource": {
            "selfLink": operator.NETWORK,
            "name": "c23-private",
            "peerings": [],
            "autoCreateSubnetworks": False,
        },
        "subnetwork_resource": {
            "selfLink": operator.SUBNET,
            "name": "c23-tokyo",
            "network": operator.NETWORK,
            "region": operator.GCP_API
            + "projects/"
            + operator.PROJECT
            + "/regions/asia-northeast1",
        },
    }
    observation = {
        "instance_id": "12345",
        "boot_id": boot,
        "interfaces": "0/",
        "access_configs": "",
        "external_ip": "",
        "now_ns": 3000,
    }
    return host, isolated, target, observation


def test_two_phase_network_controls_bind_positive_to_current_no_egress_target():
    host, isolated, target, observation = network_receipts()
    result = operator.validate_network_controls(host, isolated, target, **observation)
    assert result["host_external_tcp_positive_before_egress_removal"] is True
    assert result["current_metadata_external_ip_absent"] is True
    assert result["retained_router_inventory_no_nat"] is True
    assert "snapshot" in result["qualification"]


@pytest.mark.parametrize(
    "change",
    [
        "missing_positive",
        "different_boot",
        "different_instance",
        "stale_positive",
        "future_positive",
        "incomplete_routers",
        "nat",
        "peering",
        "other_subnet",
        "other_network",
        "external_ip",
        "external_ipv6",
        "extra_nic",
        "live_access_config",
        "live_extra_nic",
        "stale_isolation",
    ],
)
def test_network_gate_does_not_confuse_absent_host_egress_with_sandbox_containment(
    change,
):
    host, isolated, target, observation = network_receipts()
    if change == "missing_positive":
        host["host_external_tcp_connect"] = False
    elif change == "different_boot":
        host["target"]["host_boot_id"] = "22222222-2222-4222-8222-222222222222"
    elif change == "different_instance":
        host["target"]["instance_id"] = "99999"
    elif change == "stale_positive":
        observation["now_ns"] = host["monotonic_ns"] + 7201 * 10**9
    elif change == "future_positive":
        host["monotonic_ns"] = 9999
    elif change == "incomplete_routers":
        isolated["complete_router_inventory"] = False
    elif change == "nat":
        isolated["routers"] = [
            {"network": operator.NETWORK, "nats": [{"name": "forbidden"}]}
        ]
    elif change == "peering":
        isolated["network_resource"]["peerings"] = [{"name": "unexpected"}]
    elif change == "other_subnet":
        isolated["instance_resource"]["networkInterfaces"][0]["subnetwork"] = "other"
    elif change == "other_network":
        isolated["instance_resource"]["networkInterfaces"][0]["network"] = "other"
    elif change == "external_ip":
        isolated["instance_resource"]["networkInterfaces"][0]["accessConfigs"] = [
            {"natIP": "203.0.113.1"}
        ]
    elif change == "external_ipv6":
        isolated["instance_resource"]["networkInterfaces"][0]["ipv6AccessConfigs"] = [
            {"externalIpv6": "2001:db8::1"}
        ]
    elif change == "extra_nic":
        isolated["instance_resource"]["networkInterfaces"].append(
            deepcopy(isolated["instance_resource"]["networkInterfaces"][0])
        )
    elif change == "live_access_config":
        observation["access_configs"] = "0/\n1/"
    elif change == "live_extra_nic":
        observation["interfaces"] = "0/\n1/"
    else:
        observation["now_ns"] = isolated["observed_monotonic_ns"] + 1801 * 10**9
    with pytest.raises(operator.OperatorError):
        operator.validate_network_controls(host, isolated, target, **observation)


def test_complete_router_inventory_allows_only_other_network_nat():
    host, isolated, target, observation = network_receipts()
    isolated["routers"] = [
        {"network": operator.NETWORK + "-different", "nats": [{"name": "unrelated"}]}
    ]
    assert operator.validate_network_controls(host, isolated, target, **observation)[
        "retained_router_inventory_no_nat"
    ]


@pytest.mark.parametrize("action", ["prepare-host-controls", "seal-network-isolation"])
def test_privileged_setup_cli_is_also_guarded_before_filesystem_or_network_effects(
    action, monkeypatch, tmp_path
):
    def denied():
        raise operator.OperatorError("dedicated_linux_root_worker_required")

    monkeypatch.setattr(operator, "require_worker", denied)
    with pytest.raises(
        operator.OperatorError, match="dedicated_linux_root_worker_required"
    ):
        if action == "prepare-host-controls":
            operator.prepare_host_controls(tmp_path / "never.json")
        else:
            operator.seal_network_isolation(
                SimpleNamespace(output=tmp_path / "never.json")
            )
    assert not (tmp_path / "never.json").exists()


def test_immutable_network_receipt_hash_and_mode_are_required(tmp_path):
    path = tmp_path / "host.json"
    raw = operator._canonical({"operator": "synthetic"})
    operator._create(path, raw)
    assert operator._immutable_document(path, operator._sha(raw)) == {
        "operator": "synthetic"
    }
    with pytest.raises(operator.OperatorError, match="changed"):
        operator._immutable_document(path, "a" * 64)
    path.chmod(0o600)
    with pytest.raises(operator.OperatorError, match="not_immutable"):
        operator._immutable_document(path, operator._sha(raw))


@pytest.mark.parametrize(
    "change",
    [
        "host_list",
        "isolated_list",
        "target_list",
        "target_bool_number",
        "resource_list",
        "nic_not_list",
        "nic_entry_list",
        "nic_configs_dict",
        "nic_configs_null",
        "nic_ipv6_dict",
        "network_list",
        "subnet_list",
        "peerings_dict",
        "routers_dict",
        "router_list",
        "nats_dict",
    ],
)
def test_network_receipts_reject_malformed_falsy_shapes(change):
    host, isolated, target, observation = network_receipts()
    if change == "host_list":
        host = []
    elif change == "isolated_list":
        isolated = []
    elif change == "target_list":
        target = []
    elif change == "target_bool_number":
        host["target"]["linux_root_guard"] = 1
    elif change == "resource_list":
        isolated["instance_resource"] = []
    elif change == "nic_not_list":
        isolated["instance_resource"]["networkInterfaces"] = {}
    elif change == "nic_entry_list":
        isolated["instance_resource"]["networkInterfaces"] = [[]]
    elif change == "nic_configs_dict":
        isolated["instance_resource"]["networkInterfaces"][0]["accessConfigs"] = {}
    elif change == "nic_configs_null":
        isolated["instance_resource"]["networkInterfaces"][0]["accessConfigs"] = None
    elif change == "nic_ipv6_dict":
        isolated["instance_resource"]["networkInterfaces"][0]["ipv6AccessConfigs"] = {}
    elif change == "network_list":
        isolated["network_resource"] = []
    elif change == "subnet_list":
        isolated["subnetwork_resource"] = []
    elif change == "peerings_dict":
        isolated["network_resource"]["peerings"] = {}
    elif change == "routers_dict":
        isolated["routers"] = {}
    elif change == "router_list":
        isolated["routers"] = [[]]
    else:
        isolated["routers"] = [{"network": operator.NETWORK, "nats": {}}]
    with pytest.raises(operator.OperatorError):
        operator.validate_network_controls(host, isolated, target, **observation)


@pytest.mark.parametrize(
    "field", ["runtime_sha256", "trusted_init_sha256", "adapter_source_sha256"]
)
@pytest.mark.parametrize("change", ["different", "missing", "malformed"])
def test_numerical_repetition_requires_identical_valid_runtime_pins(field, change):
    first, second = numerical_attempt("numerics-a"), numerical_attempt("numerics-b")
    if change == "missing":
        first["adapter_result"].pop(field)
        second["adapter_result"].pop(field)
    elif change == "malformed":
        first["adapter_result"][field] = second["adapter_result"][field] = "invalid"
    else:
        second["adapter_result"][field] = "f" * 64
    with pytest.raises(operator.OperatorError, match="numerical_runtime_changed"):
        operator.compare_numerics(first, second)


@pytest.mark.parametrize(
    "change", ["resources", "policy", "rootfs", "normalization", "missing", "empty"]
)
def test_numerical_repetition_requires_same_normalized_resources_policy(change):
    first, second = numerical_attempt("numerics-a"), numerical_attempt("numerics-b")
    if change == "resources":
        second["comparison_configuration"]["resources"]["wall_seconds"] += 1
    elif change == "policy":
        second["comparison_configuration"]["normalized_init_policy"][
            "max_output_bytes"
        ] += 1
    elif change == "rootfs":
        second["comparison_configuration"]["rootfs_materialization"][
            "rootfs_inventory_sha256"
        ] = "2" * 64
    elif change == "normalization":
        second["comparison_configuration"]["rootfs_materialization"][
            "normalization_receipt_sha256"
        ] = "3" * 64
    elif change == "empty":
        first["comparison_configuration"] = second["comparison_configuration"] = {}
    else:
        first.pop("comparison_configuration")
        second.pop("comparison_configuration")
    with pytest.raises(operator.OperatorError, match="numerical_configuration_changed"):
        operator.compare_numerics(first, second)


class CheckedLease:
    def __init__(self):
        self.checks = 0

    def require_current(self):
        self.checks += 1


def mount_model(monkeypatch, tmp_path):
    """Physical mount state model only: no host mount/umount is invoked."""
    source, target = tmp_path / "source", tmp_path / "target"
    source.mkdir()
    target.mkdir()
    intent = operator.MountIntent(source, target)
    original = operator._directory_identity(target)
    source_id = operator._directory_identity(source)
    state = {"mounted": False, "commands": []}

    def observed(candidate):
        assert candidate is intent
        return {
            "entry": {"mount_id": "42", "options": "ro"} if state["mounted"] else None,
            "target_identity": list(source_id if state["mounted"] else original),
            "source_identity": list(source_id),
        }

    monkeypatch.setattr(operator, "_mount_observation", observed)
    return intent, state, observed


@pytest.mark.parametrize(
    "failure", ["lost_ack", "stdout_retention", "stderr_retention"]
)
def test_bind_effect_survives_lost_ack_and_log_failure_then_is_reconciled(
    failure, monkeypatch, tmp_path
):
    intent, state, _ = mount_model(monkeypatch, tmp_path)
    attempt = tmp_path / "attempt"
    attempt.mkdir()
    actual_create = operator._create

    def create(path, raw):
        if Path(path).name == f"mount-0.{failure.split('_')[0]}.bin":
            raise OSError("retention failed after physical bind")
        actual_create(path, raw)

    def run(command, **kwargs):
        state["commands"].append(command)
        assert intent.attempted and intent.prechecked_absent
        if command[0] == "/usr/bin/mount":
            state["mounted"] = True
            if failure == "lost_ack":
                raise subprocess.TimeoutExpired(command, 10)
        else:
            assert command == [
                "/usr/bin/umount",
                "--internal-only",
                "--",
                str(intent.target),
            ]
            state["mounted"] = False
        return subprocess.CompletedProcess(command, 0, b"", b"")

    monkeypatch.setattr(operator, "_create", create)
    monkeypatch.setattr(operator.subprocess, "run", run)
    with pytest.raises((OSError, subprocess.TimeoutExpired)):
        operator._perform_mount(intent, attempt)
    assert state["mounted"] and len(state["commands"]) == 1
    lease = CheckedLease()
    reconciled = operator._unmount_reconciled(intent, lease)
    assert reconciled["rootfs_unmounted"] is True and not state["mounted"]
    assert lease.checks >= 3


def prepared_mount_intent(monkeypatch, tmp_path):
    intent, state, observed = mount_model(monkeypatch, tmp_path)
    before = observed(intent)
    intent.source_identity = tuple(before["source_identity"])
    intent.target_identity_before = tuple(before["target_identity"])
    intent.prechecked_absent = intent.attempted = True
    state["mounted"] = True
    return intent, state


def test_unmount_lost_ack_requires_observed_absence_not_command_status(
    monkeypatch, tmp_path
):
    intent, state = prepared_mount_intent(monkeypatch, tmp_path)

    def lost_ack(command, **kwargs):
        state["mounted"] = False
        raise subprocess.TimeoutExpired(command, 10)

    monkeypatch.setattr(operator.subprocess, "run", lost_ack)
    record = operator._unmount_reconciled(intent, CheckedLease())
    assert record["rootfs_unmounted"] is True
    assert record["command_ack_error"] == "TimeoutExpired"
    assert record["after"]["entry"] is None


def test_successful_unmount_ack_with_mount_remaining_is_not_cleanup(
    monkeypatch, tmp_path
):
    intent, _ = prepared_mount_intent(monkeypatch, tmp_path)
    monkeypatch.setattr(
        operator.subprocess,
        "run",
        lambda command, **kwargs: subprocess.CompletedProcess(command, 0, b"", b""),
    )
    with pytest.raises(operator.OperatorError, match="unmount_unverified"):
        operator._unmount_reconciled(intent, CheckedLease())


@pytest.mark.parametrize(
    "change", ["preexisting", "no_attempt", "source_replaced", "target_replaced"]
)
def test_unmount_refuses_unowned_or_changed_mount(monkeypatch, tmp_path, change):
    intent, _ = prepared_mount_intent(monkeypatch, tmp_path)
    if change == "preexisting":
        intent.prechecked_absent = False
    elif change == "no_attempt":
        intent.attempted = False
    elif change == "source_replaced":
        intent.source_identity = (0, 0)
    else:
        real = operator._mount_observation

        def replaced(candidate):
            result = real(candidate)
            result["target_identity"] = [0, 0]
            return result

        monkeypatch.setattr(operator, "_mount_observation", replaced)

    def never_run(*args, **kwargs):
        raise AssertionError("unowned mount must not be unmounted")

    monkeypatch.setattr(operator.subprocess, "run", never_run)
    with pytest.raises(operator.OperatorError, match="identity_unverified"):
        operator._unmount_reconciled(intent, CheckedLease())


def test_mountinfo_read_failure_never_becomes_unmounted_true(monkeypatch, tmp_path):
    intent, _ = prepared_mount_intent(monkeypatch, tmp_path)

    def failed(_):
        raise OSError("mountinfo unavailable")

    monkeypatch.setattr(operator, "_mount_observation", failed)
    with pytest.raises(OSError, match="mountinfo unavailable"):
        operator._unmount_reconciled(intent, CheckedLease())


def test_mountinfo_decodes_target_and_rejects_stacked_mounts(monkeypatch):
    raw = b"42 1 8:1 / /operator\\040target ro - ext4 /dev/root ro\n"
    monkeypatch.setattr(operator, "_kernel_read", lambda *args: raw)
    assert operator._mount_entry(Path("/operator target"))["mount_id"] == "42"
    assert operator._mount_entry(Path("/different")) is None
    monkeypatch.setattr(operator, "_kernel_read", lambda *args: raw + raw)
    with pytest.raises(operator.OperatorError, match="stacked"):
        operator._mount_entry(Path("/operator target"))


def test_kernel_virtual_file_reads_until_eof_and_enforces_bound(monkeypatch, tmp_path):
    path = tmp_path / "virtual-file"
    path.touch()
    chunks = iter([b"ab", b"cd", b""])
    monkeypatch.setattr(operator.os, "read", lambda *args: next(chunks))
    assert operator._kernel_read(path, 4) == b"abcd"
    chunks = iter([b"abc", b"de"])
    with pytest.raises(operator.OperatorError, match="limit"):
        operator._kernel_read(path, 4)


@pytest.mark.parametrize("folder", ["", "0/"])
def test_known_metadata_config_folder_still_requires_empty_terminal_ip(folder):
    host, isolated, target, observed = network_receipts()
    observed["access_configs"] = folder
    result = operator.validate_network_controls(host, isolated, target, **observed)
    assert result["current_metadata_external_ip_absent"] is True
    assert result["current_metadata_access_configs"] == folder
    assert result["current_metadata_terminal_external_ip"] == ""


@pytest.mark.parametrize(
    "terminal", ["203.0.113.1", "2001:db8::1", " ", "\n", None, False, [], {}]
)
@pytest.mark.parametrize("folder", ["", "0/"])
def test_any_terminal_ip_or_unverified_shape_denies_even_known_folder(folder, terminal):
    host, isolated, target, observed = network_receipts()
    observed.update(access_configs=folder, external_ip=terminal)
    with pytest.raises(operator.OperatorError, match="host_external_ip_not_absent"):
        operator.validate_network_controls(host, isolated, target, **observed)


@pytest.mark.parametrize(
    "folder", ["/", "0", "1/", "0/\n1/", "00/", "0/\n", None, [], {}]
)
def test_unknown_metadata_folder_never_passes_with_empty_terminal(folder):
    host, isolated, target, observed = network_receipts()
    observed["access_configs"] = folder
    with pytest.raises(operator.OperatorError, match="host_external_ip_not_absent"):
        operator.validate_network_controls(host, isolated, target, **observed)


@pytest.mark.parametrize("change", ["api_external_ip", "api_extra_nic", "nat", "stale"])
def test_empty_terminal_does_not_override_api_or_snapshot_contradiction(change):
    host, isolated, target, observed = network_receipts()
    observed["access_configs"] = "0/"
    if change == "api_external_ip":
        isolated["instance_resource"]["networkInterfaces"][0]["accessConfigs"] = [
            {"natIP": "203.0.113.1"}
        ]
    elif change == "api_extra_nic":
        isolated["instance_resource"]["networkInterfaces"].append(
            deepcopy(isolated["instance_resource"]["networkInterfaces"][0])
        )
    elif change == "nat":
        isolated["routers"] = [
            {"network": operator.NETWORK, "nats": [{"name": "forbidden"}]}
        ]
    else:
        observed["now_ns"] = isolated["observed_monotonic_ns"] + 1801 * 10**9
    with pytest.raises(operator.OperatorError):
        operator.validate_network_controls(host, isolated, target, **observed)


class MetadataResponse:
    def __init__(
        self, raw=b"", status=200, flavor="Google", suffix=operator.METADATA_EXTERNAL_IP
    ):
        self.raw = raw
        self.status = status
        self.headers = {"Metadata-Flavor": flavor} if flavor is not None else {}
        self.url = "http://169.254.169.254/computeMetadata/v1/" + suffix

    def geturl(self):
        return self.url

    def read(self, limit):
        return self.raw[:limit]

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def metadata_response(monkeypatch, response):
    requests = []

    def open_request(request, timeout):
        requests.append((request, timeout))
        if isinstance(response, Exception):
            raise response
        return response

    monkeypatch.setattr(
        operator.urllib.request,
        "build_opener",
        lambda *args: SimpleNamespace(open=open_request),
    )
    return requests


def test_terminal_metadata_uses_exact_allowlisted_authenticated_empty_http200(
    monkeypatch,
):
    requests = metadata_response(monkeypatch, MetadataResponse())
    assert operator._metadata(operator.METADATA_EXTERNAL_IP) == ""
    request, timeout = requests[0]
    assert request.full_url.endswith("/" + operator.METADATA_EXTERNAL_IP)
    assert request.get_header("Metadata-flavor") == "Google" and timeout == 3
    with pytest.raises(operator.OperatorError, match="metadata_path"):
        operator._metadata("instance/network-interfaces/1/access-configs/0/external-ip")
    assert len(requests) == 1


@pytest.mark.parametrize(
    "change",
    [
        "status",
        "flavor",
        "missing_flavor",
        "url",
        "oversized",
        "malformed",
        "whitespace",
        "not_found",
    ],
)
def test_terminal_metadata_refuses_unverified_empty_or_malformed_response(
    monkeypatch, change
):
    response = MetadataResponse()
    if change == "status":
        response.status = 201
    elif change == "flavor":
        response.headers["Metadata-Flavor"] = "Other"
    elif change == "missing_flavor":
        response.headers = {}
    elif change == "url":
        response.url += "/different"
    elif change == "oversized":
        response.raw = b"x" * 257
    elif change == "malformed":
        response.raw = b"\xff"
    elif change == "whitespace":
        response.raw = b"\n"
    else:
        response = urllib.error.HTTPError(
            response.url, 404, "Not Found", response.headers, None
        )
    metadata_response(monkeypatch, response)
    if change == "whitespace":
        # Whitespace is preserved so the exact-empty gate cannot treat it as absent.
        assert operator._metadata(operator.METADATA_EXTERNAL_IP) == "\n"
    else:
        with pytest.raises(
            (operator.OperatorError, UnicodeError, urllib.error.HTTPError)
        ):
            operator._metadata(operator.METADATA_EXTERNAL_IP)


CPU_KERNEL7_FIXTURE = b"""usage_usec 31368660
user_usec 17848319
system_usec 13520341
nice_usec 32891
core_sched.force_idle_usec 0
nr_periods 0
nr_throttled 0
throttled_usec 0
nr_bursts 0
burst_usec 0
"""


def test_actual_kernel7_dotted_cpu_counter_is_retained_without_losing_required_fields():
    # Exact readback from the dedicated worker's retained host-diagnostic-02.
    parsed = operator._parse_cgroup_counters(CPU_KERNEL7_FIXTURE, "cpu.stat")
    assert parsed["core_sched.force_idle_usec"] == 0
    assert parsed["usage_usec"] == 31368660 and len(parsed) == 10


@pytest.mark.parametrize(
    "row",
    [
        b"usage_usec 1",
        b"bad..key 0",
        b"bad. 0",
        b".bad 0",
        b"x -1",
        b"x NaN",
        b"x 18446744073709551616",
        b"x 1 extra",
        b"x",
        b"\xff 1",
    ],
)
def test_cgroup_counter_parser_rejects_duplicate_malformed_or_overflow_rows(row):
    with pytest.raises((operator.OperatorError, UnicodeError)):
        operator._parse_cgroup_counters(CPU_KERNEL7_FIXTURE + row + b"\n", "cpu.stat")


@pytest.mark.parametrize(
    "name,raw",
    [
        ("cpu.stat", b"usage_usec 0\n"),
        ("memory.events", b"max 0\n"),
        ("pids.events", b"other 0\n"),
        ("cgroup.events", b"populated 0\n"),
    ],
)
def test_cgroup_counter_files_cannot_omit_known_required_fields(name, raw):
    with pytest.raises(operator.OperatorError, match="missing_required"):
        operator._parse_cgroup_counters(raw, name)


@pytest.mark.parametrize("malformed", [False, True])
def test_metrics_retain_raw_owned_cgroup_readback_before_interpretation(
    monkeypatch, tmp_path, malformed
):
    actual_path = Path
    root = tmp_path / "groups"
    outer = root / "job"
    outer.mkdir(parents=True)
    observation = tmp_path / "observations"
    observation.mkdir()
    raw_cpu = CPU_KERNEL7_FIXTURE + (b"broken row extra\n" if malformed else b"")
    values = {
        "cpu.stat": raw_cpu,
        "memory.events": b"low 0\nhigh 0\nmax 0\noom 0\noom_kill 0\n",
        "pids.events": b"max 0\n",
        "cgroup.events": b"populated 0\nfrozen 0\n",
        "memory.peak": b"1024\n",
    }
    for name, raw in values.items():
        (outer / name).write_bytes(raw)
    info = outer.stat()
    event = SimpleNamespace(
        kind="create_intent", payload={"cgroup_identity": [info.st_dev, info.st_ino]}
    )
    journal = SimpleNamespace(read=lambda *args: SimpleNamespace(events=[event]))
    envelope = SimpleNamespace(job_id="job", envelope_sha256="a" * 64)
    monkeypatch.setattr(
        operator,
        "Path",
        lambda value: (
            root if str(value) == "/sys/fs/cgroup/ocean-c23" else actual_path(value)
        ),
    )
    if malformed:
        with pytest.raises(operator.OperatorError, match="operator_cgroup_measurement"):
            operator._collect_metrics(journal, envelope, observation_dir=observation)
    else:
        measured = operator._collect_metrics(
            journal, envelope, observation_dir=observation
        )
        assert measured["cpu.stat"]["core_sched.force_idle_usec"] == 0
        assert measured["raw_cgroup_files"]["cpu.stat"] == raw_cpu.decode("ascii")
        assert measured["memory.peak"] == 1024
    assert (observation / "cgroup-cpu.stat.raw.txt").read_bytes() == raw_cpu


def test_namespace_probe_matches_profile_bits_and_architecture_without_executing_program():
    from orchestration.experiment_sandbox.profile_execution import CLONE_NAMESPACE_BITS

    body = operator.cases()["namespaces"].body
    tree = ast.parse(textwrap.dedent(body))
    bits = next(
        item.value
        for item in tree.body
        if isinstance(item, ast.Assign)
        and any(
            isinstance(target, ast.Name) and target.id == "namespace_bits"
            for target in item.targets
        )
    )
    assert tuple(ast.literal_eval(bits)) == CLONE_NAMESPACE_BITS
    syscall_numbers = {
        call.args[1].value
        for call in ast.walk(tree)
        if isinstance(call, ast.Call)
        and isinstance(call.func, ast.Name)
        and call.func.id == "denied"
        and isinstance(call.args[1], ast.Constant)
    }
    assert syscall_numbers == {56, 165, 166, 272, 308, 435}
    assert "os.uname().machine == 'x86_64'" in body
    assert "ordinary-child-ok" in body and "ordinary-thread-ok" in body
    assert "clone3_invalid_pointer" in body and "clone3_zero_size" in body
    assert "ctypes.c_uint64*11" in body
    # Analyze stored AST only. No syscall/ctypes/guest code is executed locally.


def test_unexpected_namespace_clone_child_has_only_immediate_exit_before_other_actions():
    tree = ast.parse(textwrap.dedent(operator.cases()["namespaces"].body))
    helper = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "denied"
    )
    child = next(
        node
        for node in helper.body
        if isinstance(node, ast.If)
        and ast.unparse(node.test) == "clone_child and result == 0"
    )
    assert len(child.body) == 1 and isinstance(child.body[0], ast.Expr)
    assert ast.unparse(child.body[0]) == "os._exit(0)"
    assert helper.body.index(child) < next(
        index for index, node in enumerate(helper.body) if isinstance(node, ast.Assert)
    )
