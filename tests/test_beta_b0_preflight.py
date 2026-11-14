"""Adversarial tests for the reconstructed read-only B0 verification boundary."""

from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
import json

import pytest

from scripts import beta_b0_preflight as guard


NOW = datetime(2026, 11, 14, 7, 30, tzinfo=timezone.utc)
BEFORE = NOW - timedelta(seconds=60)
NAME = "ocean-v1-beta-provider-preflight-20261111-test001"


@pytest.fixture
def material():
    contract = guard.document(guard.CONTRACT.read_bytes())
    spec = deepcopy(contract["execution_spec"])
    spec["template"]["spec"]["containers"][0]["args"] = [
        (guard.ROOT / "deploy/gcp/beta/b0" / name).read_text()
        for name in ("observer-entry.source", "observer.source")
    ]
    job = {"apiVersion": contract["job_api_version"], "kind": "Job", "metadata": {
        "name": contract["job_name"], "uid": contract["job_uid"],
        "namespace": contract["project_number"], "generation": contract["job_generation"],
    }, "spec": {"template": {"metadata": {"annotations": deepcopy(contract["annotations"])}, "spec": spec}}}
    execution = {"apiVersion": contract["job_api_version"], "kind": "Execution", "metadata": {
        "name": NAME, "namespace": contract["project_number"],
        "creationTimestamp": (NOW - timedelta(seconds=40)).isoformat(),
        "annotations": deepcopy(contract["annotations"]),
        "ownerReferences": [{"kind": "Job", "uid": contract["job_uid"], "name": contract["job_name"]}],
    }, "spec": deepcopy(spec), "status": {
        "conditions": [{"type": "Completed", "status": "True"}], "succeededCount": 1,
        "startTime": (NOW - timedelta(seconds=35)).isoformat(),
        "completionTime": (NOW - timedelta(seconds=5)).isoformat(),
    }}
    execution["spec"]["template"]["spec"]["containers"][1]["image"] = f"{guard.PROXY_REPOSITORY}@{guard.CHILD_DIGEST}"
    groups = {name: dict.fromkeys(fields, 0) for name, fields in guard.FIELDS.items()}
    groups["runs"]["total"] = 3
    groups["answer_jobs"]["total"] = 2
    for name in ("q3_run", "q3_answer_job"):
        groups[name] = {"matches": 1, "terminal": 1, "lease_closed": 1}
    report = {**dict.fromkeys(guard.TRUE_FLAGS, True), "version": "ocean-beta-runtime-rollout-preflight-v1",
              "state": "read_only_rollout_preflight_verified", "project": "ocean-v1-beta-20261101",
              "counts": groups, "captured_utc": (NOW - timedelta(seconds=10)).isoformat(),
              "user_records_prompts_payloads_credentials_selected_or_emitted": False}
    return contract, job, execution, report


def execution_proof(material, *, now=NOW, before=BEFORE):
    contract, _, execution, _ = material
    return guard.verify_execution(execution, contract, name=NAME, not_before=before, now=now,
        index_raw=(guard.PROOF / "proxy-index.json").read_bytes(),
        child_raw=(guard.PROOF / "proxy-linux-amd64.json").read_bytes())


def test_exact_source_job_and_platform_execution(material):
    contract, job, _, report = material
    assert guard.verify_job(job, contract)["observer_source_sha256"] == contract["observer_source_sha256"]
    proof = execution_proof(material)
    assert proof["proxy_proof"]["platform"] == "linux/amd64"
    assert guard.verify_report(report, proof, now=NOW)["aggregate_only_quiescence_verified"]
    assert hashlib.sha256((guard.ROOT / "deploy/gcp/beta/b0/observer.source").read_bytes()).hexdigest() == "a094ff42319fb4428fd0955ab8abfaf6ea94dd5b9d976198ef50f85af20a9e33"


@pytest.mark.parametrize("target", ["source", "wrapper", "secret", "network", "identity", "timeout", "extra_env", "image", "bool_count"])
def test_changed_job_authority_is_rejected(material, target):
    contract, job, _, _ = material
    template = job["spec"]["template"]
    task = template["spec"]["template"]["spec"]
    main = task["containers"][0]
    if target == "source":
        main["args"][1] += "\n# changed\n"
    elif target == "wrapper":
        main["args"][0] += "\n# changed\n"
    elif target == "secret":
        next(x for x in main["env"] if x["name"] == "OCEAN_V1_DATABASE_URL")["valueFrom"]["secretKeyRef"]["key"] = "latest"
    elif target == "network":
        template["metadata"]["annotations"]["run.googleapis.com/vpc-access-egress"] = "all-traffic"
    elif target == "identity":
        task["serviceAccountName"] = "other@example.com"
    elif target == "timeout":
        task["timeoutSeconds"] = "600"
    elif target == "extra_env":
        main["env"].append({"name": "DATABASE_URL", "value": "untrusted"})
    elif target == "image":
        main["image"] = main["image"].split("@")[0] + ":latest"
    else:
        template["spec"]["taskCount"] = True
    with pytest.raises(guard.Rejected):
        guard.verify_job(job, contract)


@pytest.mark.parametrize("target", ["proxy_repo", "proxy_tag", "other_digest", "main_image", "args", "owner", "project", "failed", "retried", "bool_count", "future", "pre_drain"])
def test_execution_cannot_weaken_fixed_configuration(material, target):
    _, _, execution, _ = material
    main, proxy = execution["spec"]["template"]["spec"]["containers"]
    if target == "proxy_repo":
        proxy["image"] = "attacker.example/proxy@" + guard.CHILD_DIGEST
    elif target == "proxy_tag":
        proxy["image"] = guard.PROXY_REPOSITORY + ":latest"
    elif target == "other_digest":
        proxy["image"] = guard.PROXY_REPOSITORY + "@sha256:" + "0" * 64
    elif target == "main_image":
        main["image"] = "wrong:latest"
    elif target == "args":
        proxy["args"].append("--public-ip")
    elif target == "owner":
        execution["metadata"]["ownerReferences"][0]["uid"] = "wrong"
    elif target == "project":
        execution["metadata"]["namespace"] = "legacy"
    elif target == "failed":
        execution["status"]["failedCount"] = 1
    elif target == "retried":
        execution["status"]["retriedCount"] = 1
    elif target == "bool_count":
        execution["status"]["succeededCount"] = True
    elif target == "future":
        execution["status"]["completionTime"] = (NOW + timedelta(seconds=1)).isoformat()
    else:
        execution["metadata"]["creationTimestamp"] = (BEFORE - timedelta(seconds=1)).isoformat()
    with pytest.raises(guard.Rejected):
        execution_proof(material)


def test_expired_execution_rejected(material):
    with pytest.raises(guard.Rejected):
        execution_proof(material, now=NOW + timedelta(seconds=180))


@pytest.mark.parametrize("which", ["index", "child"])
def test_tampered_manifest_bytes_rejected(which):
    index = (guard.PROOF / "proxy-index.json").read_bytes()
    child = (guard.PROOF / "proxy-linux-amd64.json").read_bytes()
    if which == "index":
        index += b" "
    else:
        child += b" "
    with pytest.raises(guard.Rejected):
        guard.verify_proxy(f"{guard.PROXY_REPOSITORY}@{guard.INDEX_DIGEST}",
                           f"{guard.PROXY_REPOSITORY}@{guard.CHILD_DIGEST}", index, child)


@pytest.mark.parametrize("target", ["lease", "prepared", "dispatchable", "orphan", "unknown", "fixed", "bool_count", "false_flag", "extra_payload", "missing_group", "impossible_counts", "future", "outside_execution"])
def test_report_booleans_do_not_replace_aggregate_proof(material, target):
    report = material[3]
    proof = execution_proof(material)
    groups = report["counts"]
    if target == "lease":
        groups["runs"]["open_lease_fields"] = 1
    elif target == "prepared":
        groups["answer_steps"]["prepared_model_steps"] = 1
    elif target == "dispatchable":
        groups["run_outbox"].update(total=1, pending=1, pending_dispatchable=1)
    elif target == "orphan":
        groups["answer_outbox"]["orphaned"] = 1
    elif target == "unknown":
        groups["run_steps"]["unknown_state"] = 1
    elif target == "fixed":
        groups["q3_run"]["matches"] = 0
    elif target == "bool_count":
        groups["runs"]["total"] = True
    elif target == "false_flag":
        report["proxy_shutdown_verified"] = False
    elif target == "extra_payload":
        report["user_payload"] = "must never be accepted or emitted"
    elif target == "missing_group":
        del groups["run_steps"]
    elif target == "impossible_counts":
        groups["runs"]["total"] = 0
    elif target == "future":
        report["captured_utc"] = (NOW + timedelta(seconds=1)).isoformat()
    else:
        report["captured_utc"] = (NOW - timedelta(seconds=40)).isoformat()
    with pytest.raises(guard.Rejected):
        guard.verify_report(report, proof, now=NOW)


def test_terminal_pending_outbox_is_preserved_not_released(material):
    material[3]["counts"]["run_outbox"].update(total=1, pending=1, pending_terminal=1)
    assert guard.verify_report(material[3], execution_proof(material), now=NOW)["snapshot_is_not_an_admission_fence"]


@pytest.mark.parametrize("raw", [b'{"x":1,"x":2}', b'{"x":NaN}', b'[]', b'null', b'\xff'])
def test_noncanonical_ambiguous_or_nonfinite_input_rejected(raw):
    with pytest.raises(guard.Rejected):
        guard.document(raw)


def test_naive_timestamp_rejected():
    with pytest.raises(guard.Rejected):
        guard.timestamp("2026-11-14T07:30:00")


def test_normalization_does_not_mutate_original(material):
    original = deepcopy(material[1])
    guard.verify_job(material[1], material[0])
    assert material[1] == original


def test_json_boolean_is_not_integer():
    assert not guard.same_document({"taskCount": True}, {"taskCount": 1})
    assert json.loads(json.dumps({"taskCount": 1}))["taskCount"] == 1
