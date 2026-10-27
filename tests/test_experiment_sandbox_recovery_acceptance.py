"""Host-safe driver contracts; guest analysis/runtime/ACLs never run here."""

import ast
from copy import deepcopy
from pathlib import Path
import signal
import subprocess
import sys
from types import SimpleNamespace

import pytest

from sandbox.experiment.gcp import run_recovery_acceptance as recovery
from tests.test_experiment_sandbox_operator_acceptance import (
    blueprint as blueprint,
    image as image,
)


@pytest.mark.parametrize("episode", recovery.EPISODES)
def test_generated_recovery_fixture_is_bounded_pinned_synthetic_and_ast_only(
    blueprint, image, episode
):
    original = deepcopy(blueprint)
    wrapper = recovery.recovery_fixture(blueprint, image, episode, "a" * 32)
    envelope = recovery.op.verify_operator_fixture(wrapper)
    assert wrapper["purpose"] == recovery.op.PURPOSE
    assert (
        wrapper["retained_C22_real_approval"]
        is wrapper["real_C22_reservation_consumption_verified"]
        is False
    )
    assert (
        wrapper["operator_admission_only"] is True
        and wrapper["recovery_episode"] == episode
    )
    assert envelope.resources["wall_seconds"] == 90
    assert envelope.environment["image_digest"] == image["image_digest"]
    assert isinstance(ast.parse(envelope.code), ast.Module)
    assert ("time.monotonic()+75" in envelope.code.decode()) == (
        episode != "terminal-replay"
    )
    assert "operator_recovery_marker" in envelope.code.decode()
    assert blueprint == original


@pytest.mark.parametrize("entry", ["run", "controller"])
def test_privileged_driver_entries_refuse_before_reading_context_or_importing_runtime(
    monkeypatch, tmp_path, entry
):
    def denied():
        raise recovery.op.OperatorError("dedicated_linux_root_worker_required")

    monkeypatch.setattr(recovery.op, "require_worker", denied)
    with pytest.raises(
        recovery.op.OperatorError, match="dedicated_linux_root_worker_required"
    ):
        getattr(recovery, entry)(
            SimpleNamespace(
                attempt_dir=tmp_path / "never", context=tmp_path / "not-read"
            )
        )
    assert list(tmp_path.iterdir()) == []


class FakeBase:
    """Inert forwarding double: no interpreter, runtime or cgroup is started."""

    def __init__(self):
        self.calls = []
        self.status = 0

    def _spawn(self, argv, host, **kwargs):
        self.calls.append(("spawn", list(argv), host, kwargs))
        return SimpleNamespace(
            stdout=bytearray(b"captured"),
            stderr=bytearray(),
            process=SimpleNamespace(poll=lambda: 0),
        )

    def _wait(self, capture, **kwargs):
        self.calls.append(("wait", capture, kwargs))
        return self.status

    def _command(self, argv, host, **kwargs):
        self.calls.append(("command", list(argv), host, kwargs))
        return self.status, b"real-forwarded-shape", b""


@pytest.mark.parametrize(
    "episode,stage,method",
    [("lost-create-ack", "create", "wait"), ("lost-start-ack", "start", "command")],
)
@pytest.mark.parametrize(
    "phase,status,expected",
    [
        ("first", 0, True),
        ("first", 1, False),
        ("recover", 0, False),
        ("contender", 0, False),
    ],
)
def test_crash_barriers_are_only_after_real_forwarded_success_before_return(
    tmp_path, episode, stage, method, phase, status, expected
):
    observed = []
    implementation = recovery.forwarding_adapter(
        FakeBase, tmp_path, episode, phase, observed.append
    )
    adapter = implementation()
    adapter.status = status
    argv = ["inert-runsc", "--root=/inert", stage, "c23-" + "a" * 48]
    if method == "wait":
        capture = adapter._spawn(argv, Path("/inert-host"), deadline=1)
        answer = adapter._wait(capture, deadline=1, require_eof=False)
        assert answer == status and adapter.calls[-1][0] == "wait"
    else:
        answer = adapter._command(argv, Path("/inert-host"), deadline=1)
        assert answer[0] == status and adapter.calls[-1][0] == "command"
    assert bool(observed) is expected


def test_cut_capture_snapshots_are_create_only_and_never_overwritten(tmp_path):
    adapter = recovery.forwarding_adapter(
        FakeBase, tmp_path, "lost-create-ack", "recover", lambda *_: None
    )()
    capture = adapter._spawn(
        ["inert-runsc", "create", "c23-" + "a" * 48], Path("/inert")
    )
    adapter.retain_commands()
    capture.stdout.extend(b"later")
    adapter.retain_commands()
    assert (tmp_path / "capture-0-command-0.stdout.bin").read_bytes() == b"captured"
    assert (
        tmp_path / "capture-1-command-0.stdout.bin"
    ).read_bytes() == b"capturedlater"
    assert recovery._commands(tmp_path) == ["create"]


def completed_record():
    return {
        "replayed": False,
        "state": "completed",
        "reason": "completed",
        "job_id": "job",
        "profile_sha256": "profile",
        "dispatch_eligible": False,
        "reservation_released": False,
        "scientific_approval": "not_independently_verified",
        "termination_proof": {
            "whole_host_subtree_empty": True,
            "populated": 0,
            "runtime_delete_acknowledged": True,
        },
        "outputs_manifest_sha256": "a" * 64,
    }


def observations(episode):
    result = completed_record()
    barrier = {
        "job_id": "job",
        "profile_sha256": "profile",
        "point": {
            "lost-create-ack": "create_succeeded_before_ack_handling",
            "lost-start-ack": "start_succeeded_before_ack_handling",
            "terminal-replay": "terminal_committed_before_delivery",
        }[episode],
        "journal": {"terminal": episode == "terminal-replay", "epoch": 1, "events": []},
    }
    if episode == "terminal-replay":
        barrier["journal"]["result"] = {"record": deepcopy(result)}
        resumed = {
            "result": {**result, "replayed": True},
            "has_outputs": True,
            "journal": deepcopy(barrier["journal"]),
        }
        first_commands = ["create", "state", "start", "wait", "delete"]
        commands = []
    else:
        result.update(
            state="interrupted",
            reason="reconciled_without_reexecution",
            outputs_manifest_sha256=None,
        )
        resumed = {"result": result, "has_outputs": False, "journal": {"epoch": 2}}
        first_commands = ["create"] + (
            ["state", "start"] if episode == "lost-start-ack" else []
        )
        commands = ["delete"]
    return [
        episode,
        barrier,
        {"reason": "sandbox_worker_busy", "runtime_commands": []},
        resumed,
        first_commands,
        commands,
        {"populated": 1},
        {"populated": 0},
    ]


@pytest.mark.parametrize("episode", recovery.EPISODES)
def test_acceptance_never_promotes_operator_results_and_requires_all_checks(episode):
    answer = recovery.assess(*observations(episode))
    assert answer["episode_passed"] is True
    assert (
        answer["C23_complete"]
        is answer["retained_C22_real_approval"]
        is answer["reservation_released"]
        is False
    )
    assert "real retained C22 bridge/release" in answer["open_gates"]


@pytest.mark.parametrize(
    "change",
    [
        "unknown_delete",
        "populated",
        "profile",
        "job",
        "release",
        "contender_effect",
        "no_epoch",
        "rerun",
        "no_live_job",
    ],
)
@pytest.mark.parametrize("episode", ["lost-create-ack", "lost-start-ack"])
def test_crash_assessment_cannot_launder_uncertain_cleanup_or_reexecution(
    episode, change
):
    values = observations(episode)
    result = values[3]["result"]
    if change == "unknown_delete":
        result["termination_proof"]["runtime_delete_acknowledged"] = False
    elif change == "populated":
        values[7]["populated"] = 1
    elif change == "profile":
        result["profile_sha256"] = "different"
    elif change == "job":
        result["job_id"] = "different"
    elif change == "release":
        result["reservation_released"] = True
    elif change == "contender_effect":
        values[2]["runtime_commands"] = ["create"]
    elif change == "no_epoch":
        values[3]["journal"]["epoch"] = 1
    elif change == "no_live_job":
        values[6]["populated"] = 0
    else:
        values[5].append("start")
    assert recovery.assess(*values)["episode_passed"] is False


@pytest.mark.parametrize(
    "change",
    [
        "commands",
        "manifest",
        "journal",
        "epoch",
        "not_replayed",
        "missing_outputs",
        "original_replayed",
    ],
)
def test_terminal_replay_requires_immutable_record_and_zero_commands(change):
    values = observations("terminal-replay")
    if change == "commands":
        values[5].append("create")
    elif change == "manifest":
        values[3]["result"]["outputs_manifest_sha256"] = "changed"
    elif change == "journal":
        values[3]["journal"]["result"]["record"]["reason"] = "changed"
    elif change == "epoch":
        values[3]["journal"]["epoch"] = 2
    elif change == "not_replayed":
        values[3]["result"]["replayed"] = False
    elif change == "original_replayed":
        values[1]["journal"]["result"]["record"]["replayed"] = True
        values[3]["journal"] = deepcopy(values[1]["journal"])
    else:
        values[3]["has_outputs"] = False
    assert recovery.assess(*values)["episode_passed"] is False


def test_sigkill_targets_only_the_exact_fresh_trusted_helper_child():
    # This is a fixed, inert host test helper, never a fixture analysis program.
    child = subprocess.Popen(
        [sys.executable, "-I", "-S", "-c", "import time;time.sleep(30)"],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        recovery._kill_controller(child)
        assert child.returncode == -signal.SIGKILL
        with pytest.raises(recovery.RecoveryError, match="not_alive"):
            recovery._kill_controller(child)
    finally:
        if child.poll() is None:
            child.kill()
            child.wait(timeout=5)


@pytest.mark.parametrize("episode", recovery.EPISODES)
@pytest.mark.parametrize("phase", recovery.PHASES)
def test_coordinator_observation_budget_is_explicit_bounded_and_separate_from_runtime(
    episode, phase
):
    expected = (
        30
        if phase == "contender"
        else 150
        if (phase, episode) == ("first", "terminal-replay")
        else 90
    )
    assert recovery.observation_timeout(episode, phase) == expected
    assert 0 < expected <= 150
    # Pure selection test: no clocks/sleeps/controller/runtime are invoked.


@pytest.mark.parametrize(
    "episode,phase", [("unknown", "first"), ("terminal-replay", "unknown")]
)
def test_unknown_observation_phase_cannot_select_an_unbounded_wait(episode, phase):
    with pytest.raises(recovery.RecoveryError, match="observation_phase"):
        recovery.observation_timeout(episode, phase)
