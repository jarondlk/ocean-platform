"""Operator-only three-episode Linux/gVisor crash acceptance.

No generated analysis is ever evaluated by this host program. Controllers are
fresh Python processes, not forks after native imports. C22 approval, dispatch,
reservation release, VM-reboot and scientific acceptance remain unverified.
"""

from __future__ import annotations

import argparse
import ast
from copy import deepcopy
from dataclasses import asdict
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
import uuid

# The explicit script entrypoint must work under a fresh operator interpreter.
# This is a fixed source location, never a request-provided Python search path.
SOURCE_ROOT = Path(__file__).resolve().parents[3]
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))

from sandbox.experiment.gcp import run_operator_acceptance as op  # noqa: E402

VERSION = "c23-operator-recovery-acceptance-v1"
EPISODES = ("lost-create-ack", "lost-start-ack", "terminal-replay")
PHASES = ("first", "contender", "recover")
OPEN_GATES = [
    "VM reboot/power failure",
    "queued-launch cancellation",
    "synthetic admission revocation",
    "real retained C22 bridge/release",
]


class RecoveryError(ValueError):
    pass


def _write(path, document):
    op._create(path, op._canonical(document))


def _stage(argv):
    return next((value for value in argv[1:] if not value.startswith("--")), None)


def recovery_fixture(blueprint, image, episode, nonce):
    """Rehash only a plainly marked synthetic operator fixture, never real C22."""
    from schema.research_experiments import content_sha256

    if episode not in EPISODES:
        raise RecoveryError("recovery_episode")
    wrapper = op.make_operator_fixture(
        blueprint,
        image,
        "smoke",
        nonce,
        host_canary="/unused-operator-recovery-canary",
        host_socket="/unused-operator-recovery.sock",
    )
    wrapper = deepcopy(wrapper)
    proposal = wrapper["metadata"]["proposal"]
    prefix = proposal["python_code"].split("import os, json\n", 1)[0]
    # Retain the trusted fixture's input constants/write_summary helper, replacing
    # only its known smoke body. The resulting code is parsed, never executed here.
    marker = "import os, json\n"
    if marker not in proposal["python_code"] or "def write_summary" not in prefix:
        raise RecoveryError("recovery_fixture_template")
    program = "import os,time\nassert os.getuid()==65532 and os.getgid()==65532\n"
    if episode != "terminal-replay":
        program += "deadline=time.monotonic()+75\nwhile time.monotonic()<deadline: time.sleep(0.05)\n"
    program += "write_summary([['operator_recovery_marker'," + repr(nonce) + "]])\n"
    proposal["python_code"] = prefix + program
    ast.parse(proposal["python_code"])
    proposal["question"] = "Operator-owned synthetic recovery: " + episode
    proposal["resources"]["wall_seconds"] = 90
    metadata = wrapper["metadata"]
    metadata["manifest"].update(
        question=proposal["question"], proposal_sha256=content_sha256(proposal)
    )
    metadata["hashes"].update(
        proposal_sha256=content_sha256(proposal),
        code_sha256=hashlib.sha256(proposal["python_code"].encode()).hexdigest(),
        input_manifest_sha256=content_sha256(metadata["manifest"]),
        resources_sha256=content_sha256(proposal["resources"]),
    )
    wrapper["operator_envelope_sha256"] = content_sha256(metadata)
    wrapper["recovery_episode"] = episode
    wrapper["operator_admission_only"] = True
    op.verify_operator_fixture(wrapper)
    return wrapper


def snapshot_document(snapshot):
    if snapshot is None:
        return None
    return {
        "job_id": snapshot.job_id,
        "envelope_sha256": snapshot.envelope_sha256,
        "epoch": snapshot.epoch,
        "terminal": snapshot.terminal,
        "reconciliation_required": snapshot.reconciliation_required,
        "events": [
            {**asdict(event), "payload": event.payload} for event in snapshot.events
        ],
        "result": snapshot.result,
    }


def _network(context, target):
    controls = context["network"]
    return op.validate_network_controls(
        op._immutable_document(
            controls["host_controls"], controls["host_controls_sha256"]
        ),
        op._immutable_document(
            controls["network_isolation"], controls["network_isolation_sha256"]
        ),
        target,
        instance_id=op._metadata("instance/id"),
        boot_id=op._boot_id(),
        interfaces=op._metadata("instance/network-interfaces/"),
        access_configs=op._metadata("instance/network-interfaces/0/access-configs/"),
        external_ip=op._metadata(op.METADATA_EXTERNAL_IP),
        now_ns=time.monotonic_ns(),
    )


def _load_context(path, digest):
    path = Path(path)
    op.check_attempt_path(path.parent)
    op._private_directory(path.parent, allow_search=True)
    if path.name != "recovery-context.json":
        raise RecoveryError("recovery_context_path")
    context = op._immutable_document(path, digest)
    if (
        context.get("version") != VERSION
        or context.get("purpose") != op.PURPOSE
        or context.get("episode") not in EPISODES
        or context.get("retained_C22_real_approval") is not False
        or context.get("driver_sha256")
        != op._hash_file(Path(__file__).resolve(), 1024**2)
        or context.get("attempt") != str(path.parent)
    ):
        raise RecoveryError("recovery_context_identity")
    for name, checksum in context["pins"].items():
        if name not in {
            "operator-fixture.json",
            "profile.json",
            "image.json",
            "runtime.json",
        }:
            raise RecoveryError("recovery_context_pin")
        op._immutable_document(path.parent / name, checksum)
    if set(context["pins"]) != {
        "operator-fixture.json",
        "profile.json",
        "image.json",
        "runtime.json",
    }:
        raise RecoveryError("recovery_context_pins")
    return context


def _reopen(attempt, context):
    from orchestration.experiment_sandbox.profile_execution import (
        render_execution_profile,
    )

    fixture = op._immutable_document(
        attempt / "operator-fixture.json", context["pins"]["operator-fixture.json"]
    )
    envelope = op.verify_operator_fixture(fixture)
    image = op._immutable_document(
        attempt / "image.json", context["pins"]["image.json"]
    )
    runtime = op._immutable_document(
        attempt / "runtime.json", context["pins"]["runtime.json"]
    )
    if (
        envelope.job_id != context["job_id"]
        or envelope.envelope_sha256 != context["envelope_sha256"]
    ):
        raise RecoveryError("recovery_job_binding")
    profile = render_execution_profile(
        envelope,
        job_root=attempt / "worker" / envelope.job_id,
        image_receipt=image,
        runtime_manifest=runtime,
        control_host_uid=op.CONTROL_UID,
        control_host_gid=op.CONTROL_GID,
        trusted_init_sha256=context["trusted_init_sha256"],
    )
    if profile.profile_sha256 != context[
        "profile_sha256"
    ] or profile.document != op._immutable_document(
        attempt / "profile.json", context["pins"]["profile.json"]
    ):
        raise RecoveryError("recovery_profile_changed")
    return envelope, profile, runtime


def forwarding_adapter(base, directory, episode, phase, barrier):
    """Only forwards real effects; inserts observations after success, never ACKs."""

    class ObservedAdapter(base):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.observed = []
            self.retention_generation = 0

        def _spawn(self, argv, host, **kwargs):
            if len(self.observed) >= 64:
                raise RecoveryError("recovery_command_bound")
            index = len(self.observed)
            _write(
                directory / f"command-{index}.intent.json",
                {"argv": list(argv), "stage": _stage(argv)},
            )
            capture = super()._spawn(argv, host, **kwargs)
            self.observed.append((list(argv), capture))
            return capture

        def _wait(self, capture, **kwargs):
            code = super()._wait(capture, **kwargs)
            stage = next(
                (_stage(argv) for argv, value in self.observed if value is capture),
                None,
            )
            if (
                phase == "first"
                and episode == "lost-create-ack"
                and stage == "create"
                and code == 0
            ):
                barrier("create_succeeded_before_ack_handling")
            return code

        def _command(self, argv, host, **kwargs):
            result = super()._command(argv, host, **kwargs)
            if (
                phase == "first"
                and episode == "lost-start-ack"
                and _stage(argv) == "start"
                and result[0] == 0
            ):
                barrier("start_succeeded_before_ack_handling")
            return result

        def retain_commands(self):
            generation = self.retention_generation
            self.retention_generation += 1
            for index, (argv, capture) in enumerate(self.observed):
                raw_out, raw_err = bytes(capture.stdout), bytes(capture.stderr)
                if max(len(raw_out), len(raw_err)) > 64 * 1024**2:
                    raise RecoveryError("recovery_capture_bound")
                _write(
                    directory
                    / f"capture-{generation}-command-{index}.observation.json",
                    {
                        "argv": argv,
                        "exit_status": capture.process.poll(),
                        "stdout_sha256": op._sha(raw_out),
                        "stderr_sha256": op._sha(raw_err),
                    },
                )
                op._create(
                    directory / f"capture-{generation}-command-{index}.stdout.bin",
                    raw_out,
                )
                op._create(
                    directory / f"capture-{generation}-command-{index}.stderr.bin",
                    raw_err,
                )

    return ObservedAdapter


def controller(arguments):
    target = op.require_worker()
    context = _load_context(arguments.context, arguments.context_sha256)
    _network(context, target)
    attempt, phase = Path(context["attempt"]), arguments.phase
    directory = attempt / "episodes" / phase
    op._private_directory(directory)
    envelope, profile, runtime = _reopen(attempt, context)
    from orchestration.experiment_sandbox.journal import DurableExecutionJournal
    from orchestration.experiment_sandbox.linux_runtime import LinuxExecutionAdapter

    with DurableExecutionJournal(attempt / "journal") as journal:
        adapter = None

        def barrier(point):
            adapter.retain_commands()
            _write(
                directory / "barrier.json",
                {
                    "version": VERSION,
                    "point": point,
                    "controller_pid": os.getpid(),
                    "context_sha256": arguments.context_sha256,
                    "job_id": envelope.job_id,
                    "profile_sha256": profile.profile_sha256,
                    "journal": snapshot_document(
                        journal.read(envelope.job_id, envelope.envelope_sha256)
                    ),
                },
            )
            # Coordinator kills this exact child. Bounded failure leaves the real
            # adapter's own cleanup/watchdog path available, never a fake success.
            deadline = time.monotonic() + 45
            while time.monotonic() < deadline:
                time.sleep(0.05)
            raise RecoveryError("recovery_barrier_timeout")

        implementation = forwarding_adapter(
            LinuxExecutionAdapter, directory, context["episode"], phase, barrier
        )
        adapter = implementation(
            attempt / "worker", context["runtime_directory"], runtime, journal
        )
        try:
            result = adapter.run(
                envelope,
                profile,
                admission=lambda candidate: op._admission(
                    attempt / "operator-fixture.json",
                    context["pins"]["operator-fixture.json"],
                    candidate,
                ),
            )
            if phase == "first" and context["episode"] == "terminal-replay":
                _write(
                    directory / "terminal-before-delivery.json",
                    {
                        "result": result.document,
                        "has_outputs": result.outputs is not None,
                    },
                )
                barrier("terminal_committed_before_delivery")
            adapter.retain_commands()
            _write(
                directory / "result.json",
                {
                    "result": result.document,
                    "has_outputs": result.outputs is not None,
                    "output_files_sha256": {
                        name: op._sha(raw) for name, raw in result.outputs.files.items()
                    }
                    if result.outputs
                    else {},
                    "journal": snapshot_document(
                        journal.read(envelope.job_id, envelope.envelope_sha256)
                    ),
                },
            )
            return 0
        except Exception as error:
            failure = {
                "type": type(error).__name__,
                "reason": getattr(error, "reason", str(error))[:512],
                "dispatch_eligible": False,
                "reservation_released": False,
            }
            try:
                adapter.retain_commands()
            except Exception as retention_error:
                failure["raw_capture_retention_error"] = type(retention_error).__name__
            _write(directory / "error.json", failure)
            return 2


def _start_controller(context_path, digest, phase):
    directory = context_path.parent / "episodes" / phase
    op._private_directory(directory, create=True)
    stdout = (directory / "controller.stdout.txt").open("xb")
    stderr = (directory / "controller.stderr.txt").open("xb")
    try:
        process = subprocess.Popen(
            [
                sys.executable,
                "-B",
                str(Path(__file__).resolve()),
                "_controller",
                "--context",
                str(context_path),
                "--context-sha256",
                digest,
                "--phase",
                phase,
            ],
            stdin=subprocess.DEVNULL,
            stdout=stdout,
            stderr=stderr,
            cwd=SOURCE_ROOT,
            close_fds=True,
        )
    finally:
        stdout.close()
        stderr.close()
    return process


def observation_timeout(episode, phase):
    """Bound coordinator waits separately from the unchanged guest wall limit."""
    if episode not in EPISODES or phase not in PHASES:
        raise RecoveryError("recovery_observation_phase")
    if phase == "contender":
        # Leave time to kill the first controller before its45s barrier expires.
        return 30
    if phase == "first" and episode == "terminal-replay":
        return 90 + 60  # Runtime ceiling plus trusted preflight observation margin.
    return 60 + 30


def _wait_barrier(process, path, digest, *, timeout):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if path.exists():
            try:
                value = json.loads(op._read(path, op.MAX_FIXTURE))
                if (
                    value["controller_pid"] != process.pid
                    or value["context_sha256"] != digest
                ):
                    raise RecoveryError("recovery_barrier_identity")
                if process.poll() is not None:
                    raise RecoveryError("recovery_controller_died_before_cut")
                return value
            except (OSError, json.JSONDecodeError):
                pass
        if process.poll() is not None:
            raise RecoveryError("recovery_controller_exited_before_barrier")
        time.sleep(0.05)
    raise RecoveryError("recovery_barrier_unobserved")


def _population(attempt, envelope, journal):
    identity = op._cgroup_identity(journal, envelope)
    outer = Path("/sys/fs/cgroup/ocean-c23") / envelope.job_id
    if identity is None or not outer.exists():
        raise RecoveryError("recovery_owned_cgroup_missing")
    info = outer.lstat()
    if (info.st_dev, info.st_ino) != identity or outer != outer.resolve(strict=True):
        raise RecoveryError("recovery_owned_cgroup_changed")
    raw = op._kernel_read(outer / "cgroup.events")
    fields = op._parse_cgroup_counters(raw, "cgroup.events")
    return {
        "device": identity[0],
        "inode": identity[1],
        "populated": fields["populated"],
        "raw": raw.decode("ascii"),
    }


def _wait_watchdog_empty(attempt, envelope, journal):
    deadline = time.monotonic() + 8
    while True:
        observed = _population(attempt, envelope, journal)
        if observed["populated"] == 0:
            return observed
        if time.monotonic() >= deadline:
            raise RecoveryError("recovery_watchdog_not_empty")
        time.sleep(0.02)


def _kill_controller(process):
    if process.poll() is not None:
        raise RecoveryError("recovery_child_not_alive_at_kill")
    process.kill()
    process.wait(timeout=5)
    if process.returncode != -signal.SIGKILL:
        raise RecoveryError("recovery_child_not_sigkilled")


def assess(
    episode,
    barrier,
    contender,
    recovery,
    first_commands,
    recovery_commands,
    before_kill,
    after_kill,
):
    result = recovery.get("result", {})
    proof = result.get("termination_proof") or {}
    checks = {
        "expected_barrier": barrier.get("point")
        == {
            "lost-create-ack": "create_succeeded_before_ack_handling",
            "lost-start-ack": "start_succeeded_before_ack_handling",
            "terminal-replay": "terminal_committed_before_delivery",
        }[episode],
        "same_job": result.get("job_id") == barrier.get("job_id"),
        "same_profile": result.get("profile_sha256") == barrier.get("profile_sha256"),
        "no_dispatch_or_release": result.get("dispatch_eligible") is False
        and result.get("reservation_released") is False,
        "scientific_unverified": result.get("scientific_approval")
        == "not_independently_verified",
        "verified_cleanup": proof.get("whole_host_subtree_empty") is True
        and proof.get("populated") == 0
        and proof.get("runtime_delete_acknowledged") is True,
        "owned_empty_after_crash": after_kill.get("populated") == 0,
        "one_create": first_commands.count("create") == 1,
    }
    if episode == "terminal-replay":
        checks.update(
            replayed=result.get("replayed") is True,
            terminal_completed=result.get("state") == "completed",
            retained_outputs=recovery.get("has_outputs") is True,
            zero_runtime_commands=not recovery_commands,
            terminal_before_crash=barrier.get("journal", {}).get("terminal") is True,
        )
        original = barrier.get("journal") or {}
        checks["immutable_terminal_journal"] = recovery.get("journal", {}).get(
            "result"
        ) == original.get("result") and recovery.get("journal", {}).get(
            "epoch"
        ) == original.get("epoch")
        checks["same_terminal_record"] = {
            key: value for key, value in result.items() if key != "replayed"
        } == {
            key: value
            for key, value in original.get("result", {}).get("record", {}).items()
            if key != "replayed"
        }
        checks["original_was_first_execution"] = (
            original.get("result", {}).get("record", {}).get("replayed") is False
        )
    else:
        original = barrier.get("journal") or {}
        checks.update(
            contender_busy=contender.get("reason") == "sandbox_worker_busy",
            no_contender_commands=contender.get("runtime_commands") == [],
            original_nonterminal=original.get("terminal") is False,
            cleanup_only=result.get("state") == "interrupted"
            and result.get("reason") == "reconciled_without_reexecution",
            no_recovered_outputs=recovery.get("has_outputs") is False,
            no_reexecution=not any(
                stage in {"create", "start", "wait"} for stage in recovery_commands
            ),
            increased_epoch=recovery.get("journal", {}).get("epoch", 0)
            > original.get("epoch", 0),
        )
        checks["live_before_kill"] = before_kill.get("populated") == 1
        if episode == "lost-start-ack":
            checks["one_start"] = first_commands.count("start") == 1
            checks["start_ack_not_journaled"] = not any(
                event["kind"] == "started" for event in original.get("events", [])
            )
        else:
            checks["no_start"] = "start" not in first_commands
    return {
        "checks": checks,
        "episode_passed": all(checks.values()),
        "C23_complete": False,
        "retained_C22_real_approval": False,
        "reservation_released": False,
        "open_gates": OPEN_GATES,
    }


def _commands(directory):
    return [
        json.loads(op._read(path, 65536))["stage"]
        for path in sorted(directory.glob("command-*.intent.json"))
    ]


def run(arguments):
    target = op.require_worker()
    from orchestration.experiment_sandbox.files import stage_inputs
    from orchestration.experiment_sandbox.journal import DurableExecutionJournal
    from orchestration.experiment_sandbox.profile_execution import (
        render_execution_profile,
    )
    from sandbox.experiment import trusted_init

    attempt = op.check_attempt_path(arguments.attempt_dir)
    op._private_directory(op.FIXED_ROOT, allow_search=True)
    if not op.ATTEMPTS_ROOT.exists():
        op._private_directory(op.ATTEMPTS_ROOT, create=True, allow_search=True)
    op._private_directory(op.ATTEMPTS_ROOT, allow_search=True)
    op._private_directory(attempt, create=True)
    _write(
        attempt / "recovery-start.json",
        {
            "version": VERSION,
            "episode": arguments.episode,
            "purpose": op.PURPOSE,
            "target": target,
            "retained_C22_real_approval": False,
            "reservation_released": False,
            "C23_complete": False,
        },
    )
    processes, mount_intent = [], None
    report = {
        "version": VERSION,
        "purpose": op.PURPOSE,
        "episode": arguments.episode,
        "retained_C22_real_approval": False,
        "reservation_released": False,
        "C23_complete": False,
        "open_gates": OPEN_GATES,
        "cleanup_deferred": True,
    }
    try:
        if (
            op._sha(op._read(arguments.blueprint, op.MAX_FIXTURE))
            != arguments.blueprint_sha256
        ):
            raise RecoveryError("recovery_blueprint_hash")
        blueprint = op.load_blueprint(arguments.blueprint)
        image = json.loads(op._read(arguments.image_receipt, op.MAX_FIXTURE))
        runtime = json.loads(op._read(arguments.runtime_manifest, op.MAX_FIXTURE))
        materials = op.verify_materials(
            arguments.rootfs,
            arguments.oci_layout,
            image,
            runtime,
            normalization_receipt=arguments.normalization_receipt,
            normalization_sha256=arguments.normalization_sha256,
        )
        network = {
            name: str(getattr(arguments, name))
            for name in (
                "host_controls",
                "host_controls_sha256",
                "network_isolation",
                "network_isolation_sha256",
            )
        }
        _network({"network": network}, target)
        wrapper = recovery_fixture(
            blueprint, image, arguments.episode, uuid.uuid4().hex
        )
        envelope = op.verify_operator_fixture(wrapper)
        worker = op._private_directory(attempt / "worker", create=True)
        journal_root = op._private_directory(attempt / "journal", create=True)
        op._private_directory(attempt / "episodes", create=True)
        with DurableExecutionJournal(journal_root):
            pass
        stage_inputs(worker, envelope)
        inputs = worker / envelope.job_id / "inputs"
        for path in inputs.iterdir():
            os.chown(path, op.APP_UID, op.APP_GID, follow_symlinks=False)
        os.chown(inputs, op.APP_UID, op.APP_GID, follow_symlinks=False)
        inputs.chmod(0o500)
        rootfs = worker / envelope.job_id / "rootfs"
        rootfs.mkdir(mode=0o755)
        mount_intent = op.MountIntent(Path(arguments.rootfs), rootfs)
        op._perform_mount(mount_intent, attempt)
        op._grant_gofer_traversal(attempt, worker, worker / envelope.job_id)
        init_sha = op._hash_file(Path(trusted_init.__file__).resolve(), 65536)
        profile = render_execution_profile(
            envelope,
            job_root=worker / envelope.job_id,
            image_receipt=image,
            runtime_manifest=runtime,
            control_host_uid=op.CONTROL_UID,
            control_host_gid=op.CONTROL_GID,
            trusted_init_sha256=init_sha,
        )
        values = {
            "operator-fixture.json": wrapper,
            "profile.json": profile.document,
            "image.json": image,
            "runtime.json": runtime,
        }
        pins = {}
        for name, value in values.items():
            raw = op._canonical(value)
            op._create(attempt / name, raw)
            pins[name] = op._sha(raw)
        context = {
            "version": VERSION,
            "purpose": op.PURPOSE,
            "episode": arguments.episode,
            "attempt": str(attempt),
            "job_id": envelope.job_id,
            "envelope_sha256": envelope.envelope_sha256,
            "profile_sha256": profile.profile_sha256,
            "trusted_init_sha256": init_sha,
            "runtime_directory": str(arguments.runtime_directory),
            "pins": pins,
            "driver_sha256": op._hash_file(Path(__file__).resolve(), 1024**2),
            "network": network,
            "materials": materials,
            "retained_C22_real_approval": False,
        }
        context_path = attempt / "recovery-context.json"
        context_raw = op._canonical(context)
        op._create(context_path, context_raw)
        digest = op._sha(context_raw)
        report["context_sha256"] = digest
        first = _start_controller(context_path, digest, "first")
        processes.append(first)
        barrier = _wait_barrier(
            first,
            attempt / "episodes/first/barrier.json",
            digest,
            timeout=observation_timeout(arguments.episode, "first"),
        )
        _write(attempt / "coordinator-barrier-observed.json", barrier)
        contender = {}
        if arguments.episode != "terminal-replay":
            rival = _start_controller(context_path, digest, "contender")
            processes.append(rival)
            rival.wait(timeout=observation_timeout(arguments.episode, "contender"))
            contender = json.loads(
                op._read(attempt / "episodes/contender/error.json", 65536)
            )
            contender["runtime_commands"] = _commands(attempt / "episodes/contender")
            _write(attempt / "contender-observation.json", contender)
        with DurableExecutionJournal(journal_root) as journal:
            before = _population(attempt, envelope, journal)
            _write(attempt / "before-controller-kill.json", before)
            # Popen owns/reaps precisely this fresh child; no name/PID searching.
            _kill_controller(first)
            after = _wait_watchdog_empty(attempt, envelope, journal)
            _write(attempt / "after-controller-kill.json", after)
            _write(
                attempt / "journal-after-crash.json",
                snapshot_document(
                    journal.read(envelope.job_id, envelope.envelope_sha256)
                ),
            )
        resumed = _start_controller(context_path, digest, "recover")
        processes.append(resumed)
        resumed.wait(timeout=observation_timeout(arguments.episode, "recover"))
        recovered = json.loads(
            op._read(attempt / "episodes/recover/result.json", op.MAX_FIXTURE)
        )
        evaluation = assess(
            arguments.episode,
            barrier,
            contender,
            recovered,
            _commands(attempt / "episodes/first"),
            _commands(attempt / "episodes/recover"),
            before,
            after,
        )
        report["evaluation"] = evaluation
        report["recovered_result"] = recovered
        if evaluation["episode_passed"]:
            with DurableExecutionJournal(journal_root) as journal:
                report["cleanup"] = op._cleanup(journal, envelope, mount_intent)
            report["cleanup_deferred"] = False
    except Exception as error:
        report["error"] = {
            "type": type(error).__name__,
            "reason": getattr(error, "reason", str(error))[:512],
        }
    finally:
        for process in processes:
            if process.poll() is None:
                process.kill()
                process.wait(timeout=5)
        _write(attempt / "recovery-attempt.json", report)
    print(
        json.dumps(
            {
                "attempt": str(attempt),
                "episode_passed": report.get("evaluation", {}).get(
                    "episode_passed", False
                ),
                "cleanup_deferred": report["cleanup_deferred"],
                "C23_complete": False,
            },
            sort_keys=True,
        )
    )
    return (
        0
        if report.get("evaluation", {}).get("episode_passed")
        and not report["cleanup_deferred"]
        else 1
    )


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="action", required=True)
    child = commands.add_parser("_controller")
    child.add_argument("--context", type=Path, required=True)
    child.add_argument("--context-sha256", required=True)
    child.add_argument("--phase", choices=PHASES, required=True)
    execute = commands.add_parser("run")
    execute.add_argument("--episode", choices=EPISODES, required=True)
    execute.add_argument("--attempt-dir", type=Path, required=True)
    for name in (
        "blueprint",
        "host-controls",
        "network-isolation",
        "normalization-receipt",
    ):
        execute.add_argument("--" + name, type=Path, required=True)
    for name in (
        "blueprint-sha256",
        "host-controls-sha256",
        "network-isolation-sha256",
        "normalization-sha256",
    ):
        execute.add_argument("--" + name, required=True)
    for name, default in (
        ("rootfs", op.FIXED_ROOT / "scientific-normalized-quota-v3/rootfs"),
        ("oci-layout", op.FIXED_ROOT / "scientific-oci-quota-v3"),
        ("image-receipt", op.FIXED_ROOT / "evidence/image-preparation-quota-v3.json"),
        (
            "runtime-manifest",
            op.FIXED_ROOT / "evidence/runtime-preparation-quota-v3.json",
        ),
        ("runtime-directory", Path("/opt/ocean-c23-runtime/release-20261019.0")),
    ):
        execute.add_argument("--" + name, type=Path, default=default)
    arguments = parser.parse_args(argv)
    return (
        controller(arguments) if arguments.action == "_controller" else run(arguments)
    )


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, OSError) as error:
        print(
            json.dumps(
                {
                    "error": type(error).__name__,
                    "reason": str(error)[:512],
                    "C23_complete": False,
                }
            ),
            file=sys.stderr,
        )
        raise SystemExit(2)
