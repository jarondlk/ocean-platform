"""Read-only cross-check of original Linux receipts against independent DB/key pins."""

from pathlib import Path
from datetime import datetime, timezone
import argparse
import hashlib
import json
import math
import sqlite3

from orchestration.experiment_sandbox.proofs import (
    PinnedTerminationIssuer,
    TerminationVerifierRegistry,
    verify_termination_packet,
)
from orchestration.experiment_sandbox import journal as journal_format
from schema.experiment_execution import ClosedExecutionBinding, TerminationIssuerScope
from schema.research_experiments import EnvironmentDescriptor, content_sha256

ROOT = Path(__file__).resolve().parents[6]
BASE = ROOT / "docs/plans/ocean-v1/evidence/C23/cloud-session-20261028-retained"
EXPORT = BASE / "actual-export01"
OUT = Path(__file__).resolve().parent
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument(
    "--verify-only",
    action="store_true",
    help="Check immutable receipts without creating or changing a receipt",
)
options = parser.parse_args()


def raw(path):
    return path.read_bytes()


def sha(data):
    return hashlib.sha256(data).hexdigest()


def doc(path):
    return json.loads(raw(path))


def canonical(value):
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False
    ).encode("ascii")


def one(rows):
    assert len(rows) == 1
    return rows[0]


def check(condition, name):
    if not condition:
        raise AssertionError(name)
    return True


pins = doc(BASE / "control-public-pins.json")
source = doc(EXPORT / "evidence/operator-source-20261027-08.json")
manifest = doc(EXPORT / "evidence/retained-export-20261028-01.json")
for name, pin in manifest["files"].items():
    check(
        sha(raw(EXPORT / name)) == pin["sha256"]
        and len(raw(EXPORT / name)) == pin["size_bytes"],
        "raw export member",
    )
for name, pin in source["source_files"].items():
    check(sha(raw(ROOT / name)) == pin, "source drift: " + name)
image = doc(EXPORT / "evidence/image-preparation-quota-v3.json")
runtime = doc(EXPORT / "evidence/runtime-preparation-quota-v3.json")
check(
    sha(raw(EXPORT / "evidence/image-preparation-quota-v3.json"))
    == pins["materials"]["image_receipt_sha256"],
    "image pin",
)
check(
    sha(raw(EXPORT / "evidence/runtime-preparation-quota-v3.json"))
    == pins["materials"]["runtime_manifest_sha256"],
    "runtime pin",
)
environment = EnvironmentDescriptor(
    kind="linux-gvisor",
    test_only=False,
    python_version=image["python_version"],
    image_digest=image["image_digest"],
    lockfile_sha256=image["lockfile_sha256"],
    packages=image["packages"],
    description="Pinned C23 retained synthetic acceptance image; scientific approval unverified",
)
profile_files = {
    n: source["source_files"][n]
    for n in (
        "orchestration/experiment_sandbox/profile.py",
        "orchestration/experiment_sandbox/profile_execution.py",
        "sandbox/experiment/trusted_init.py",
    )
}
fields = {
    "worker_id": pins["worker_id"],
    "worker_source_sha256": sha(
        canonical(
            {"version": "c23-worker-source-policy-v1", "files": source["source_files"]}
        )
    ),
    "environment_sha256": environment.identity_sha256,
    "image_digest": image["image_digest"],
    "runtime_sha256": content_sha256(runtime),
    "profile_policy_sha256": sha(
        canonical({"version": "c23-profile-source-policy-v1", "files": profile_files})
    ),
    "trusted_init_sha256": profile_files["sandbox/experiment/trusted_init.py"],
    "adapter_source_sha256": source["source_files"][
        "orchestration/experiment_sandbox/linux_runtime.py"
    ],
}
policy = {
    "version": "c23-physical-termination-source-policy-v1",
    "trust_scope": "retained-operator",
    **fields,
}
scope = TerminationIssuerScope(
    site_id="v1:c17-synthetic", source_policy_sha256=sha(canonical(policy)), **fields
)
results = {}
summaries = {}
for case, label in [
    ("scientific", "retained-scientific-20261028-01"),
    ("publication-revoked", "retained-owner-revoked-20261028-01"),
]:
    directory = EXPORT / "operator-acceptance" / label
    observation = doc(directory / "observations.json")
    report = observation["report"]
    database = doc(BASE / "database-exports" / (case + ".json"))
    tables = database["tables"]
    execution = one(tables["research_experiment_execution"])
    state = one(tables["research_experiment_execution_state"])
    proof = one(tables["research_experiment_termination_proof"])
    release = one(tables["research_experiment_release"])
    reservation = one(tables["research_experiment_reservation"])
    revision = one(tables["research_experiment_revision"])
    approval = one(tables["research_experiment_approval"])
    envelope = json.loads(execution["envelope_json"])
    job = directory / "worker" / execution["job_id"]
    profile = doc(directory / "profile.json")
    checks = {}
    checks["current_implementation_source"] = check(
        all(
            execution[n] == getattr(scope, n)
            for n in TerminationIssuerScope.model_fields
        ),
        "scope from independent public pins",
    )
    checks["approval_revision_envelope"] = check(
        execution["approval_id"] == approval["id"]
        and execution["proposal_revision_id"] == revision["id"]
        and approval["revision_id"] == revision["id"]
        and execution["reservation_id"] == reservation["id"]
        and reservation["envelope_sha256"] == execution["envelope_sha256"]
        and sha(execution["envelope_json"].encode()) == execution["envelope_sha256"]
        and sha(approval["request_json"].encode())
        == execution["approval_request_sha256"]
        and sha(execution["request_json"].encode())
        == execution["execution_request_sha256"],
        "approved envelope bindings",
    )
    proposal = json.loads(revision["proposal_json"])
    hashes = envelope["hashes"]
    checks["five_approved_hashes"] = check(
        all(
            hashes[n] == revision[n]
            for n in (
                "code_sha256",
                "proposal_sha256",
                "environment_sha256",
                "input_manifest_sha256",
                "resources_sha256",
            )
        )
        and sha(proposal["python_code"].encode()) == hashes["code_sha256"]
        and content_sha256(proposal) == hashes["proposal_sha256"]
        and content_sha256(proposal["resources"]) == hashes["resources_sha256"]
        and json.loads(revision["environment_json"])
        == environment.model_dump(mode="json")
        and raw(job / "inputs/analysis.py") == proposal["python_code"].encode(),
        "five approved hashes and staged code",
    )
    for item in envelope["manifest"]["files"]:
        data = raw(job / "inputs" / item["name"])
        check(
            sha(data) == item["sha256"] and len(data) == item["size_bytes"],
            "staged approved input",
        )
    checks["staged_input_files"] = True
    check(content_sha256(profile) == report["profile_sha256"], "profile hash")
    connection = sqlite3.connect(
        "file:"
        + str((directory / "journal/journal.sqlite3").resolve())
        + "?mode=ro&immutable=1",
        uri=True,
    )
    connection.row_factory = sqlite3.Row
    events = [
        dict(row)
        for row in connection.execute("SELECT * FROM events ORDER BY sequence")
    ]
    terminal = one([dict(row) for row in connection.execute("SELECT * FROM results")])
    connection.close()
    previous = "0" * 64
    clock = 0
    for number, event in enumerate(events, 1):
        check(
            event["sequence"] == number
            and event["previous_sha256"] == previous
            and event["epoch"] == 1
            and event["job_id"] == execution["job_id"]
            and event["envelope_sha256"] == execution["envelope_sha256"]
            and event["host_id"] == pins["worker_id"]
            and event["host_boot_id"] == pins["boot_id"]
            and event["monotonic_ns"] >= clock,
            "journal identity/order",
        )
        fields_to_hash = {n: v for n, v in event.items() if n != "sha256"}
        check(
            sha(journal_format._encode(fields_to_hash, 2 * 1024**2).encode())
            == event["sha256"],
            "journal canonical chain",
        )
        previous = event["sha256"]
        clock = event["monotonic_ns"]
        event["payload"] = json.loads(event["payload_json"])
    kinds = {
        kind: [e for e in events if e["kind"] == kind]
        for kind in (
            "create_intent",
            "enforcement_verified",
            "start_intent",
            "started",
            "cleanup_intent",
            "termination_verified",
            "finished",
        )
    }
    check(
        all(len(v) == 1 for v in kinds.values()),
        "exact one lifecycle event of each kind",
    )
    starts = [
        e
        for e in tables["research_experiment_execution_event"]
        if e["kind"] == "start_consumed"
    ]
    start = one(starts)
    start_intent = one(kinds["start_intent"])
    marker = doc(directory / "journal/identity.json")
    checks["single_fresh_start"] = check(
        start["id"]
        == start["start_id"]
        == start_intent["payload"]["start_id"]
        == start_intent["payload"]["start_event_id"]
        and start["preceding_journal_sha256"] == start_intent["previous_sha256"]
        and start["journal_id"] == marker["journal_id"]
        and start["journal_epoch"] == 1
        and start["host_boot_id"] == pins["boot_id"]
        and start["profile_sha256"] == report["profile_sha256"]
        and start["fence"] == 2
        and not tables["research_experiment_outbox"],
        "single native/retained start",
    )
    record = json.loads(terminal["document_json"])["record"]
    wrapper = json.loads(terminal["document_json"])
    finished = one(kinds["finished"])
    check(
        sha(terminal["document_json"].encode())
        == terminal["sha256"]
        == finished["payload"]["result_sha256"]
        == report["durable_terminal"]["terminal_result_sha256"],
        "full terminal wrapper hash",
    )
    checks["immutable_terminal_wrapper"] = check(
        terminal["event_sha256"]
        == finished["sha256"]
        == report["durable_terminal"]["terminal_head_sha256"]
        and terminal["event_sequence"] == finished["sequence"] == 11
        and record["reservation_released"] is False
        and record["scientific_approval"] == "not_independently_verified"
        and all(
            n not in wrapper
            for n in ("termination_proof_id", "release_id", "publication_reference")
        ),
        "finished identity/no authority cycles",
    )
    closed = one(
        [
            e
            for e in tables["research_experiment_execution_event"]
            if e["kind"] == "closed"
        ]
    )
    expected = ClosedExecutionBinding.model_validate(
        {
            **{
                n: execution[n]
                for n in ClosedExecutionBinding.model_fields
                if n in execution
            },
            "closed_fence": closed["fence"],
            "host_boot_id": closed["host_boot_id"],
            "journal_id": closed["journal_id"],
            "journal_epoch": closed["journal_epoch"],
            "profile_sha256": closed["profile_sha256"],
        }
    )
    check(
        closed["result_sha256"] == terminal["sha256"]
        and closed["terminal_sequence"] == finished["sequence"]
        and closed["terminal_head_sha256"] == finished["sha256"]
        and state["state"] == "closed"
        and state["fence"] == closed["fence"],
        "independent DB terminal close",
    )
    packet_path = (
        directory
        / "issuer"
        / (
            "c23-termination-"
            + execution["execution_id"]
            + "-"
            + str(closed["fence"])
            + ".json"
        )
    )
    packet = raw(packet_path)
    parsed = json.loads(packet)
    registry = TerminationVerifierRegistry(
        issuers=[
            PinnedTerminationIssuer(
                issuer_id=pins["cases"][case]["issuer_id"],
                key_id=pins["cases"][case]["key_id"],
                trust_scope="retained-operator",
                public_key=bytes.fromhex(pins["cases"][case]["issuer_public_key_hex"]),
                scope=scope,
            )
        ],
        trust_scope="retained-operator",
        enabled=True,
    )
    verified = verify_termination_packet(packet, expected=expected, registry=registry)
    stored_packet = (
        proof["packet_bytes"].encode()
        if proof["packet_bytes"].startswith("{")
        else bytes.fromhex(proof["packet_bytes"][2:])
    )
    checks["independent_signature_and_ledger"] = check(
        verified.packet_sha256 == proof["packet_sha256"]
        and packet == stored_packet
        and verified.verification_key_sha256 == proof["verification_key_sha256"]
        and verified.verification_policy_sha256
        == proof["verification_policy_sha256"]
        == observation["verifier_policy_sha256"]
        and verified.signature_sha256 == proof["signature_sha256"],
        "independent signature/DB exact packet",
    )
    intent = doc(
        directory
        / "issuer"
        / (
            "issuance-"
            + execution["execution_id"]
            + "-"
            + str(closed["fence"])
            + ".json"
        )
    )
    check(
        intent == {n: v for n, v in parsed.items() if n != "signature"},
        "create-once issuance intent",
    )
    native_path = one(list((job / "physical-termination").glob("*.json")))
    native = doc(native_path)
    claims = parsed["claims"]
    kernel = claims["kernel"]
    jw = claims["journal"]
    delete = native["delete"]
    check(
        sha(raw(native_path))
        == kernel["raw_observation_sha256"]
        == one(kinds["termination_verified"])["payload"]["native_observation_sha256"],
        "raw native bytes hash",
    )
    checks["original_cgroup_native_cleanup"] = check(
        one(kinds["create_intent"])["payload"]["cgroup_identity"]
        == [kernel["cgroup_device"], kernel["cgroup_inode"]]
        == [native["cgroup_device"], native["cgroup_inode"]]
        and native["populated"] == kernel["populated"] == 0
        and delete["exit_code"] == 0
        and delete["pipes_eof"] is True
        and sha(canonical(delete["command"])) == kernel["delete_command_sha256"]
        and sha(canonical(delete)) == kernel["delete_acknowledgement_sha256"]
        and native["host_boot_id"] == pins["boot_id"]
        and delete["command"]["argv"][-3:]
        == ["delete", "--force", execution["job_id"]],
        "original cgroup/delete/empty boot witness",
    )
    for kind, prefix in [
        ("create_intent", "create_intent"),
        ("cleanup_intent", "cleanup_intent"),
        ("termination_verified", "termination"),
    ]:
        event = one(kinds[kind])
        check(
            jw[prefix + "_sequence"] == event["sequence"]
            and jw[prefix + "_sha256"] == event["sha256"],
            "packet lifecycle journal witness",
        )
    check(
        kernel["cleanup_started_monotonic_ns"]
        <= kernel["delete_acknowledged_monotonic_ns"]
        <= kernel["populated_zero_monotonic_ns"]
        <= kernel["terminal_recorded_monotonic_ns"]
        == finished["monotonic_ns"]
        <= kernel["issued_monotonic_ns"],
        "ordered physical/terminal/issuance clock",
    )
    readback = one(kinds["enforcement_verified"])["payload"]["readback"]
    native_processes = readback["native_processes"]
    checks["prestart_enforcement"] = check(
        one(kinds["enforcement_verified"])["sequence"] < start_intent["sequence"]
        and native_processes["native_nofile_limit"] == 4096
        and native_processes["analysis_nofile_limit"] == 256
        and readback[execution["job_id"]]
        == {
            "cpu.max": "200000 100000",
            "memory.max": "4294967296",
            "memory.swap.max": "0",
            "pids.max": "128",
        },
        "measured native/guest/resource enforcement",
    )
    diagnostic_dirs = [p for p in (job / "diagnostics").iterdir() if p.is_dir()]
    check(
        len(
            [p for p in diagnostic_dirs if doc(p / "metadata.json")["stage"] == "start"]
        )
        == 1,
        "one actual native start diagnostic",
    )
    create = one(
        [p for p in diagnostic_dirs if doc(p / "metadata.json")["stage"] == "create"]
    )
    frame_capture = doc(create / "metadata.json")
    # Privacy deliberately retains the validated files, not a duplicate raw
    # control-frame body. Authenticate its captured digest/outcome and rely on
    # the frozen guarded decoder path; do not claim to reparse absent bytes.
    check(
        frame_capture["stdout"]["captured_sha256"] == record["frame_sha256"]
        and frame_capture["stdout"]["body_retained"] is False
        and frame_capture["stdout"]["captured_bytes"] > 0
        and frame_capture["pipes_eof"] is True
        and frame_capture["exit_status_observed"] == 0
        and record["analysis_exit_code"] == 0
        and record["simulation"] is False
        and record["state"] == "completed",
        "actual captured frame digest and guarded decode outcome",
    )
    retained = doc(job / "retained/manifest.json")
    retained_sha = sha(raw(job / "retained/manifest.json"))
    check(retained_sha == record["outputs_manifest_sha256"], "retained manifest hash")
    for item in retained["files"]:
        data = raw(job / "retained/files" / item["name"])
        check(
            sha(data) == item["sha256"] and len(data) == item["size_bytes"],
            "bounded output bytes",
        )
    for item in retained["logs"]:
        data = raw(job / "retained/logs" / item["name"])
        check(
            sha(data) == item["sha256"] and len(data) == item["size_bytes"],
            "retained log bytes",
        )
    summaries[case] = dict(doc(job / "retained/files/summary.json")["rows"])
    publications = [
        e
        for e in tables["research_experiment_execution_event"]
        if e["kind"] == "publication_retained"
    ]
    if case == "scientific":
        publication = one(publications)
        check(
            publication["result_sha256"] == retained_sha
            and report["publication_status"] == "acknowledged",
            "current publication",
        )
    else:
        revoke = observation["publication_revocation"]
        owner = one(
            [r for r in database["owners"] if r["id"] == execution["owner_user_id"]]
        )
        check(
            not publications
            and report["publication_status"] == "denied_or_uncertain"
            and report["publication_reference"] is None
            and owner["status"] == "suspended"
            and revoke["feature_flag_enabled"] is True
            and revoke["performed_after_durable_terminal"] is True
            and revoke["readback_status"] == "suspended"
            and revoke["terminal_journal_sha256"] == finished["sha256"]
            and revoke["observation"]["owner_user_id"] == execution["owner_user_id"],
            "actual owner suspension denies publication",
        )
    checks["publication_or_owner_denial"] = True
    checks["proof_backed_release"] = check(
        release["proof_id"] == proof["id"] == report["termination_proof_id"]
        and release["execution_id"] == execution["execution_id"]
        and release["reservation_id"] == reservation["id"]
        and release["closed_fence"] == closed["fence"]
        and release["id"] == report["release_id"]
        and reservation["state"] == "released"
        and report["capacity_release_status"] == "acknowledged",
        "correlated proof-backed release",
    )
    cleanup = observation["cleanup"]
    check(
        cleanup["cgroup_empty"] is True
        and cleanup["rootfs_unmounted"] is True
        and cleanup["mount_reconciliation"]["exit_code"] == 0
        and cleanup["mount_reconciliation"]["after"]["entry"] is None
        and "ro"
        in cleanup["mount_reconciliation"]["before"]["entry"]["options"].split(","),
        "final empty/unmounted kernel readback",
    )
    checks["cleanup_and_outputs"] = True
    results[case] = {
        "checks": checks,
        "passed": all(checks.values()),
        "execution_id": execution["execution_id"],
        "job_id": execution["job_id"],
        "closed_fence": closed["fence"],
        "packet_sha256": verified.packet_sha256,
        "proof_id": proof["id"],
        "release_id": release["id"],
        "journal_events": len(events),
        "analysis_state": record["state"],
        "publication_events": len(publications),
        "terminal_wrapper_sha256": terminal["sha256"],
        "scientific_approval": "not_independently_verified",
    }
check(
    summaries["scientific"]["exact_int64"]
    == summaries["publication-revoked"]["exact_int64"]
    == 9223372036854775807,
    "exact int64 numerical fixture",
)
for name, value in summaries["scientific"].items():
    check(
        math.isclose(
            value, summaries["publication-revoked"][name], rel_tol=1e-12, abs_tol=1e-12
        ),
        "repeated numerical value",
    )
check(
    math.isclose(
        summaries["scientific"]["ols_intercept"], 1, rel_tol=1e-12, abs_tol=1e-12
    )
    and math.isclose(
        summaries["scientific"]["ols_slope"], 2, rel_tol=1e-12, abs_tol=1e-12
    ),
    "known OLS values",
)
for name, pin in manifest["files"].items():
    check(sha(raw(EXPORT / name)) == pin["sha256"], "immutable raw after audit")
receipt = {
    "version": "c23-retained-independent-raw-audit-v1",
    "recorded_at": datetime.now(timezone.utc).isoformat(),
    "actual_run_source": "501c80b7e5ee07f0990539baea3d8243f71d184a",
    "all236_current_source_pins_match": True,
    "all167_export_members_verified": True,
    "results": results,
    "repeated_numerics": summaries,
    "absolute_and_relative_tolerance": 1e-12,
    "actual_retained_acceptance_passed": True,
    "C23_complete": False,
    "raw_frame_body_retained": False,
    "frame_validation_qualification": "Raw control-frame body is intentionally not retained. Independent audit verifies captured digest, EOF/outcome and validated files; guarded source performed frame grammar and writer-reaped checks. No independent reparse of unavailable body is claimed.",
    "remaining_gates": [
        "verified resource shutdown",
        "successful exact-source hosted CI",
        "delivery metadata/checkpoint",
    ],
    "qualification": "Read-only independent source/DB/canonical-chain/public-key/native/output cross-check; no signing, runtime, fabricated review or authority mutation. Prior containment/resource/science/recovery receipts remain separately qualified.",
}
if not options.verify_only:
    with (OUT / "final-receipt.json").open("x") as stream:
        json.dump(receipt, stream, indent=2, sort_keys=True)
        stream.write("\n")
print(
    json.dumps(
        {
            "actual_retained_acceptance_passed": True,
            "cases": {n: r["passed"] for n, r in results.items()},
            "checks_per_case": {n: len(r["checks"]) for n, r in results.items()},
            "C23_complete": False,
        }
    )
)
