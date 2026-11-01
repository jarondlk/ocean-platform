"""Disposable C27 flag rollback/drain rehearsal; never a live deployment tool.

Uses actual C17/C20/C21/C22/C25 services and public worker response helpers.
Synthetic queues/execution observations are explicit. The bounded subprocess
checks use existing retained-runner software simulations, not Linux execution.
"""
from __future__ import annotations

import argparse
import base64
from datetime import date, datetime
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import uuid
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[6]
sys.path.insert(0, str(ROOT))
FLAGS = (
    "CATALOGUE", "CATALOGUE_BROWSER", "SHELL", "INVESTIGATIONS",
    "RESEARCH_CONTROLLER", "RESEARCH_RUNS", "RESEARCH_DISPATCH", "EVIDENCE",
    "SYNTHESIS", "EXPERIMENTS", "EXPERIMENT_DISPATCH", "EXPERIMENT_WORKSPACE",
)
DRAIN_OFF = {"RESEARCH_CONTROLLER", "RESEARCH_DISPATCH", "SYNTHESIS", "EXPERIMENT_DISPATCH"}
ACCEPTED_SOURCE = "afe9cb2d1a6d2c28a834daab1a342de4563dc3a3"
CHECKS = (
    "tests/test_chat_issue59.py::test_api_history_and_audit_share_the_bounded_evidence",
    "tests/test_research_run_http.py::test_dispatch_disabled_keeps_actual_cancel_history_and_events",
    "tests/test_research_runs.py::test_crash_boundary_charges_uncertain_or_replays_commit[True]",
    "tests/test_experiment_sandbox_retained_runner.py::test_cancel_before_effect_does_not_invent_start_or_release",
    "tests/test_experiment_sandbox_retained_runner.py::test_independent_postfinish_failure_keeps_terminal_history_and_capacity_uncertain",
    "tests/test_experiment_sandbox_retained_runner.py::test_missing_original_create_identity_retains_capacity_without_runtime_commands",
    "tests/test_experiment_sandbox_retained_runner.py::test_changed_boot_retains_capacity_and_never_reconstructs_start_or_cleanup",
    "tests/test_experiment_sandbox_retained_runner.py::test_release_ack_loss_is_reported_unknown_instead_of_false_or_reexecuted",
    "tests/test_experiment_sandbox_retained_runner.py::test_nonterminal_reconciliation_never_restarts_and_only_bound_start_can_close[False]",
)


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest(value):
    return hashlib.sha256(value if isinstance(value, bytes) else canonical(value).encode()).hexdigest()


def encode(value):
    if isinstance(value, (uuid.UUID, date, datetime)):
        return str(value)
    if isinstance(value, bytes):
        return {"sha256": digest(value), "bytes": len(value)}
    if isinstance(value, (tuple, list)):
        return [encode(item) for item in value]
    if isinstance(value, dict):
        return {str(key): encode(item) for key, item in value.items()}
    return value


def profiles(name):
    return {"ENABLE_V1_" + flag: str(name == "enabled" or (name == "drain" and flag not in DRAIN_OFF)).lower()
        for flag in FLAGS}


def apply_profile(name):
    values = profiles(name)
    os.environ.update(values)
    return values


def response(value, status=200):
    assert value.status_code == status, (value.status_code, value.body.decode())
    return json.loads(value.body)


def denied(callback, status=503):
    try:
        callback()
    except Exception as error:
        assert getattr(error, "status_code", None) == status, repr(error)
        return {"status_code": status, "code": error.code}
    raise AssertionError("Expected current service denial")


def snapshots(engine, port_path):
    from db.app_models import AppBase
    values = {}
    with engine.connect() as connection:
        for name, table in sorted(AppBase.metadata.tables.items()):
            rows = [encode(dict(row._mapping)) for row in connection.execute(table.select())]
            rows.sort(key=canonical)
            values[name] = {"rows": len(rows), "sha256": digest(rows)}
    with sqlite3.connect(port_path) as connection:
        for (name,) in connection.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"):
            assert name.replace("_", "").isalnum()
            columns = [column[1] for column in connection.execute(f'PRAGMA table_info("{name}")')]
            rows = [encode(dict(zip(columns, row))) for row in connection.execute(f'SELECT * FROM "{name}"')]
            rows.sort(key=canonical)
            values["synthetic_port." + name] = {"rows": len(rows), "sha256": digest(rows)}
    return values


def run_shared(directory):
    import config
    from sqlalchemy import create_engine, event, select
    from api.research_run_routes import research_run_response
    from api.research_evidence_routes import research_evidence_response
    from api.research_experiment_routes import research_experiment_response
    from api.experiment_workspace_routes import experiment_workspace_response
    from api.v1_runtime_routes import runtime_response, V1RuntimeConfiguration
    from db.app_models import AppBase, ResearchExperimentOutbox, ResearchExperimentReservation, ResearchRunStep
    from orchestration.research_runs import RunJournal
    from orchestration.research_experiments import FakeExperimentExecutor
    from tests.system_acceptance_support import make_system_acceptance_fixture, seed_integrated_browser

    apply_profile("enabled")
    engine = create_engine("sqlite+pysqlite:///" + str(directory / "v1.sqlite"))
    @event.listens_for(engine, "connect")
    def foreign_keys(connection, _):
        connection.execute("PRAGMA foreign_keys=ON")
    AppBase.metadata.create_all(engine)
    fixture = make_system_acceptance_fixture(engine, directory)
    fixture.runs.service.enabled = config.v1_research_runs_enabled
    fixture.runs.service.dispatch_enabled = config.v1_research_dispatch_enabled
    fixture.evidence.enabled = config.v1_evidence_enabled
    fixture.answers.enabled = config.v1_evidence_enabled
    fixture.answers.synthesis_enabled = config.v1_synthesis_enabled
    fixture.experiments.service.enabled = config.v1_experiments_enabled
    fixture.experiments.service.dispatch_enabled = config.v1_experiment_dispatch_enabled
    fixture.workspace.enabled = config.v1_experiment_workspace_enabled
    try:
        seed = seed_integrated_browser(fixture)
        runs, investigations, actor = fixture.runs.service, fixture.retained.service, fixture.user
        done, answer, receipt = seed["run"], seed["answer_job"], seed["receipts"][0]
        context = fixture.context()
        queued = runs.invoke("submit", fixture.run_request(context), actor)["run"]
        running = runs.invoke("submit", fixture.run_request(context), actor)["run"]
        lease = runs.claim(**fixture.runs.delivery(running))
        assert lease is not None
        running = runs.invoke("status", fixture.runs.address(running), actor)["run"]
        assert running["status"] == "running"
        port_path = directory / "c26-synthetic-executions.sqlite"
        before = snapshots(engine, port_path)
        flags_drain = apply_profile("drain")
        after_flags = snapshots(engine, port_path)
        assert before == after_flags

        # Actual API worker DTO guards and services retain history when only
        # execution/synthesis dispatch is disabled. No production wiring exists.
        address = fixture.runs.address(done)
        assert response(research_run_response(actor, runs, investigations, "status", address))["run"] == done
        events = response(research_run_response(actor, runs, investigations, "events", {**address, "after_cursor": 0}))
        assert events["events"][-1]["kind"] == "completed"
        saved_receipt = response(research_evidence_response(actor, fixture.evidence, fixture.answers, investigations,
            "evidence", "open", {"receipt_id": receipt["id"], "expected_sha256": receipt["sha256"]}))["receipt"]
        assert saved_receipt == receipt
        saved_answer = response(research_evidence_response(actor, fixture.evidence, fixture.answers, investigations,
            "answers", "status", {**address, "job_id": answer["id"]}))["job"]
        assert saved_answer == answer
        experiment = response(research_experiment_response(actor, fixture.experiments.service, investigations,
            "get", {"experiment_id": seed["experiment"]["id"]}))["experiment"]
        assert experiment["proposal"] == seed["experiment"]["proposal"]
        artifact = seed["execution"]["artifacts"][0]
        artifact_request = {**seed["execution_request"], "execution_id": seed["execution"]["id"],
            "artifact_id": artifact["id"], "expected_sha256": artifact["sha256"]}
        saved_artifact = response(experiment_workspace_response(actor, fixture.workspace, fixture.experiments.service,
            "artifact", artifact_request))
        assert digest(base64.b64decode(saved_artifact["content_base64"])) == artifact["sha256"]
        assert saved_artifact["artifact"]["authority"] == "experimental"
        denied_delivery = denied(lambda: runs.execute_delivery(**fixture.runs.delivery(queued)))
        denied_outbox = denied(runs.dispatch_outbox)
        response(research_run_response(actor, runs, investigations, "submit", fixture.run_request(context)), 503)
        new_answer = fixture.answers.invoke("list", address, actor)
        response(research_evidence_response(actor, fixture.evidence, fixture.answers, investigations,
            "answers", "submit", {**address, "input_version": new_answer["input_version"], "locale": "ja",
                "idempotency_key": str(uuid.uuid4())}), 503)
        denied(lambda: fixture.experiments.service.invoke("dispatch", fixture.experiments.decision(seed["experiment"]), actor))
        read_snapshot = snapshots(engine, port_path)
        assert before == read_snapshot
        cancelled = []
        for row in (queued, running):
            value = response(research_run_response(actor, runs, investigations, "cancel",
                {**fixture.runs.address(row), "idempotency_key": str(uuid.uuid4())}))["run"]
            assert value["status"] == "cancelled"
            cancelled.append(value)
        fenced = denied(lambda: RunJournal(runs, lease).bind({}), status=409)
        assert runs.execute_delivery(**fixture.runs.delivery(running))["run"] == cancelled[1]
        assert runs.execute_delivery(**fixture.runs.delivery(queued))["run"] == cancelled[0]

        drained = snapshots(engine, port_path)
        flags_off = apply_profile("off")
        assert snapshots(engine, port_path) == drained
        response(research_run_response(actor, runs, investigations, "status", address), 503)
        response(research_evidence_response(actor, fixture.evidence, fixture.answers, investigations,
            "evidence", "open", {"receipt_id": receipt["id"], "expected_sha256": receipt["sha256"]}), 503)
        response(experiment_workspace_response(actor, fixture.workspace, fixture.experiments.service,
            "artifact", artifact_request), 503)
        configuration = V1RuntimeConfiguration(site_id=investigations.site_id, revision="c27-flags-off")
        response(runtime_response(actor, configuration), 503)
        assert snapshots(engine, port_path) == drained
        # Same accepted code, additive schema retained; this is not proof that
        # a previous binary can read the current database.
        apply_profile("drain")
        assert response(research_run_response(actor, runs, investigations, "status", address))["run"] == done
        assert response(research_evidence_response(actor, fixture.evidence, fixture.answers, investigations,
            "answers", "status", {**address, "job_id": answer["id"]}))["job"] == answer
        assert snapshots(engine, port_path) == drained

        # Queue ACK loss uses exactly one durable step/effect on redelivery.
        apply_profile("enabled")
        retry_context = fixture.context()
        retry_run = runs.invoke("submit", fixture.run_request(retry_context), actor)["run"]
        fixture.runs.queue.accept_then_fail = True
        try:
            runs.dispatch_outbox()
        except RuntimeError:
            pass
        else:
            raise AssertionError("Expected synthetic queue acceptance/ACK loss")
        fixture.runs.queue.accept_then_fail = False
        runs.dispatch_outbox()
        target_deliveries = [x for x in fixture.runs.queue.deliveries if x["run_id"] == retry_run["id"]]
        assert len(target_deliveries) == 2 and target_deliveries[0] == target_deliveries[1]
        first = runs.execute_delivery(**target_deliveries[0])
        calls = fixture.state["factory_calls"]
        second = runs.execute_delivery(**target_deliveries[1])
        assert first == second and first["run"]["status"] == "completed"
        assert fixture.state["factory_calls"] == calls
        with fixture.retained.factory() as session:
            steps = session.scalars(select(ResearchRunStep).where(ResearchRunStep.run_id == uuid.UUID(retry_run["id"]))).all()
            assert len(steps) == 1 and steps[0].state == "committed"

        # C22 delivery uncertainty retains its reservation and delivery identity;
        # flag rollback must not release capacity to make the queue look empty.
        experiments = fixture.experiments
        proposal = experiments.create(user=experiments.other)
        proposal = experiments.service.invoke("approve", experiments.decision(proposal), experiments.other)["experiment"]
        dispatch_request = experiments.decision(proposal)
        reserved = experiments.service.invoke("dispatch", dispatch_request, experiments.other)["experiment"]
        reservation_id = reserved["dispatch"]["reservation_id"]
        class LostAck(FakeExperimentExecutor):
            def enqueue(self, **kwargs):
                super().enqueue(**kwargs)
                raise OSError("Explicit synthetic accepted dispatch with lost acknowledgement")
        experiments.service.executor = LostAck()
        assert experiments.service.dispatch_outbox()["sent"] == 0
        with fixture.retained.factory() as session:
            reservation = session.get(ResearchExperimentReservation, uuid.UUID(reservation_id))
            outbox = session.scalar(select(ResearchExperimentOutbox).where(ResearchExperimentOutbox.reservation_id == reservation.id))
            assert reservation.state == outbox.state == "uncertain"
            stable_delivery_id = str(outbox.delivery_id)
        held_before = snapshots(engine, port_path)
        apply_profile("drain")
        held_denial = denied(experiments.service.dispatch_outbox)
        assert snapshots(engine, port_path) == held_before
        with fixture.retained.factory() as session:
            assert session.get(ResearchExperimentReservation, uuid.UUID(reservation_id)).state == "uncertain"
        apply_profile("enabled")
        experiments.service.executor = FakeExperimentExecutor()
        assert experiments.service.dispatch_outbox(retry_uncertain=True)["sent"] == 1
        with fixture.retained.factory() as session:
            reservation = session.get(ResearchExperimentReservation, uuid.UUID(reservation_id))
            outbox = session.scalar(select(ResearchExperimentOutbox).where(ResearchExperimentOutbox.reservation_id == reservation.id))
            assert reservation.state == "accepted" and outbox.state == "sent"
            assert str(outbox.delivery_id) == stable_delivery_id
            assert reservation.state != "released"
        envelope = experiments.service.load_execution_envelope(reservation_id, user=experiments.other)
        assert envelope["metadata"]["execution_performed"] is False
        apply_profile("drain")
        return {"status": "passed", "profiles": {"enabled_synthetic_only": profiles("enabled"),
            "drain_preserve_history": flags_drain, "emergency_unavailable": flags_off},
            "same_candidate_restore_only": True, "previous_binary_compatibility": "not_established",
            "snapshots": {"before_dispatch_disable": before, "after_dispatch_disable_and_reads": read_snapshot,
                "after_explicit_cancellations": drained, "uncertain_experiment_before_disable": held_before},
            "history_evidence": {"run_id": done["id"], "context_sha256": done["context"]["binding"]["payload_sha256"],
                "receipt_sha256": receipt["sha256"], "answer_sha256": digest(answer),
                "proposal_hashes": seed["experiment"]["hashes"], "artifact_sha256": artifact["sha256"]},
            "drain": {"cancelled_states": [row["status"] for row in cancelled], "late_lease": fenced,
                "delivery_disabled": denied_delivery, "outbox_disabled": denied_outbox,
                "terminal_redelivery_unchanged": True},
            "research_ack_loss": {"delivery_count": len(target_deliveries), "identical_delivery_identity": True,
                "committed_steps": 1, "terminal_redelivery_invoked_no_controller": True},
            "experiment_ack_loss": {"reservation_id": reservation_id, "delivery_id": stable_delivery_id,
                "state_while_disabled": "uncertain", "dispatch_disabled": held_denial,
                "reconciled_with_same_delivery": True, "reservation_released": False, "execution_performed": False}}
    finally:
        engine.dispose()


def source_files():
    names = {str(Path(__file__).resolve().relative_to(ROOT))}
    for module in tuple(sys.modules.values()):
        path = getattr(module, "__file__", None)
        if not path:
            continue
        path = Path(path).resolve()
        if path.is_relative_to(ROOT) and path.suffix == ".py" and ".venv" not in path.parts:
            names.add(str(path.relative_to(ROOT)))
    names.update(node.split("::")[0] for node in CHECKS)
    return {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in sorted(names)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    os.environ.update(DEPLOYMENT_ENV="test", AUTH_MODE="disabled", ENABLE_MOCK_LOGIN="false", PERSIST_LOCAL_CHAT="false")
    apply_profile("off")
    result = {"version": "c27-local-rollback-rehearsal-v1", "status": "failed",
        "accepted_runtime_source": ACCEPTED_SOURCE, "checkout": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "scope": "Disposable synthetic local stores; actual service/DTO semantics; no provider, cloud, Linux execution or production deployment",
        "release_accepted": False}
    try:
        with tempfile.TemporaryDirectory(prefix="ocean-c27-rollback-") as temp:
            result["shared_stack"] = run_shared(Path(temp))
        # All v1 flags are off in this subprocess by default. The legacy /chat
        # test uses the real route with explicit synthetic retrieval/runtime and
        # actual retained ChatInteraction. No provider/model operation occurs.
        apply_profile("off")
        command = [sys.executable, "-m", "pytest", *CHECKS, "-q", "--tb=short",
            "--junitxml=" + str(args.output.resolve() / "regressions.xml")]
        child = subprocess.run(command, cwd=ROOT, env=dict(os.environ), capture_output=True, text=True, timeout=180)
        (args.output / "regressions.log").write_text(child.stdout + child.stderr)
        assert child.returncode == 0, "Bounded actual regression subprocess failed; retain raw output"
        suites = ET.parse(args.output / "regressions.xml").getroot()
        cases = list(suites.iter("testcase"))
        assert len(cases) == 11 and not any(list(case) for case in cases)
        result["regressions"] = {"command": command, "returncode": child.returncode,
            "passed": len(cases), "failed": 0, "skipped": 0, "all_v1_flags_initially_off": profiles("off"),
            "qualification": "C23 retained-runner cases mock Linux/DB/physical observations and prove software uncertainty handling only; legacy /chat test uses synthetic retrieval/model."}
        result["source_files"] = source_files()
        for name, identity in result["source_files"].items():
            if name != str(Path(__file__).resolve().relative_to(ROOT)):
                accepted = subprocess.check_output(["git", "show", ACCEPTED_SOURCE + ":" + name], cwd=ROOT)
                assert hashlib.sha256(accepted).hexdigest() == identity, name
        result["source_revision"] = "sha256:" + digest(result["source_files"])
        result["disposable_stores_removed"] = not Path(temp).exists()
        assert result["disposable_stores_removed"]
        result["artifacts_sha256"] = {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(args.output.iterdir()) if p.is_file()}
        result["status"] = "passed"
    finally:
        (args.output / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"status": result["status"], "regressions": result["regressions"]["passed"],
        "source_revision": result["source_revision"], "release_accepted": False}, indent=2))


if __name__ == "__main__":
    main()
