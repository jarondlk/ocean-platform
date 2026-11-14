"""Read-only verification of the fixed beta observer and exact OCI platform pin.

This tool cannot execute jobs or update services. Cloud observations are inputs,
not authority to ignore admission, source, IAM, catalogue or budget gates.
"""

import argparse
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "deploy/gcp/beta/b0/observer-contract.json"
PROOF = ROOT / "docs/plans/ocean-v1/beta/main-mac-return-20261114"
PROXY_REPOSITORY = "gcr.io/cloud-sql-connectors/cloud-sql-proxy"
INDEX_DIGEST = "sha256:f333a9c59890c3c67b8505166c5dbdcc0b29fca9173a2e09ca0446ab6997a736"
CHILD_DIGEST = "sha256:1d2285ce2ae05129166c2cf2eb9d481570ffd43b4755dab5384ad17ffa1194bb"
OCI_INDEX = "application/vnd.oci.image.index.v1+json"
OCI_MANIFEST = "application/vnd.oci.image.manifest.v1+json"
MAX_AGE = timedelta(seconds=180)


class Rejected(ValueError):
    """A bounded failure that never includes supplied data or credential values."""


def require(condition):
    if not condition:
        raise Rejected("B0 proof rejected")


def _pairs(items):
    result = {}
    for key, value in items:
        require(key not in result)
        result[key] = value
    return result


def document(raw):
    require(isinstance(raw, bytes) and len(raw) <= 1_000_000)
    try:
        value = json.loads(raw, object_pairs_hook=_pairs,
                           parse_constant=lambda _: require(False))
    except (ValueError, UnicodeError, RecursionError):
        raise Rejected("B0 JSON rejected") from None
    require(type(value) is dict)
    return value


def digest(raw):
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def same_document(left, right):
    # JSON distinguishes booleans and integers even though Python equality does not.
    return json.dumps(left, sort_keys=True, allow_nan=False) == json.dumps(right, sort_keys=True, allow_nan=False)


def verify_proxy(reviewed, observed, index_raw, child_raw):
    """Permit only this reviewed index's exact Linux/amd64 child substitution."""
    require(reviewed == f"{PROXY_REPOSITORY}@{INDEX_DIGEST}")
    require(observed == f"{PROXY_REPOSITORY}@{CHILD_DIGEST}")
    require(digest(index_raw) == INDEX_DIGEST and digest(child_raw) == CHILD_DIGEST)
    index, child = document(index_raw), document(child_raw)
    require(type(index.get("schemaVersion")) is int and index["schemaVersion"] == 2)
    require(index.get("mediaType") == OCI_INDEX)
    require(type(index.get("manifests")) is list)
    members = [x for x in index["manifests"] if type(x) is dict and x.get("digest") == CHILD_DIGEST]
    require(len(members) == 1)
    require(members[0] == {
        "mediaType": OCI_MANIFEST, "digest": CHILD_DIGEST, "size": len(child_raw),
        "platform": {"architecture": "amd64", "os": "linux"},
    })
    require(type(child.get("schemaVersion")) is int and child["schemaVersion"] == 2)
    require(child.get("mediaType") == OCI_MANIFEST)
    return {"index": INDEX_DIGEST, "executed_manifest": CHILD_DIGEST, "platform": "linux/amd64"}


def normalized_spec(spec):
    result = deepcopy(spec)
    try:
        containers = result["template"]["spec"]["containers"]
        require(len(containers) == 2 and containers[0]["name"] == "diagnostics")
        args = containers[0]["args"]
        require(type(args) is list and len(args) == 2 and all(type(x) is str for x in args))
        containers[0]["args"] = [
            {"sha256": hashlib.sha256(x.encode()).hexdigest(), "bytes": len(x.encode())} for x in args
        ]
    except (KeyError, TypeError, IndexError):
        raise Rejected("B0 observer configuration rejected") from None
    return result


def verify_job(job, contract):
    try:
        require(job["apiVersion"] == contract["job_api_version"] and job["kind"] == "Job")
        metadata = job["metadata"]
        for key, expected in (("name", "job_name"), ("namespace", "project_number"),
                              ("uid", "job_uid"), ("generation", "job_generation")):
            require(type(metadata[key]) is type(contract[expected]) and metadata[key] == contract[expected])
        template = job["spec"]["template"]
        require(same_document(template["metadata"]["annotations"], contract["annotations"]))
        require(same_document(normalized_spec(template["spec"]), contract["execution_spec"]))
        source = ROOT / "deploy/gcp/beta/b0/observer.source"
        require(hashlib.sha256(source.read_bytes()).hexdigest() == contract["observer_source_sha256"])
    except (KeyError, TypeError, IndexError):
        raise Rejected("B0 observer job rejected") from None
    return {"job": contract["job_name"], "generation": metadata["generation"],
            "observer_source_sha256": contract["observer_source_sha256"]}


def timestamp(value):
    try:
        require(type(value) is str)
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
        require(result.utcoffset() == timedelta(0))
        return result
    except (ValueError, TypeError):
        raise Rejected("B0 timestamp rejected") from None


def verify_execution(execution, contract, *, name, not_before, now, index_raw, child_raw):
    try:
        metadata, status = execution["metadata"], execution["status"]
        require(execution["kind"] == "Execution" and execution["apiVersion"] == contract["job_api_version"])
        require(name.startswith(contract["job_name"] + "-") and metadata["name"] == name)
        require(metadata["namespace"] == contract["project_number"])
        owners = metadata["ownerReferences"]
        require(len(owners) == 1 and owners[0]["name"] == contract["job_name"]
                and owners[0]["uid"] == contract["job_uid"] and owners[0]["kind"] == "Job")
        for key, value in contract["annotations"].items():
            require(metadata["annotations"].get(key) == value)
        spec = normalized_spec(execution["spec"])
        proxy = spec["template"]["spec"]["containers"][1]
        expected = contract["execution_spec"]["template"]["spec"]["containers"][1]
        require(proxy["name"] == expected["name"] == "sql-proxy")
        proof = verify_proxy(expected["image"], proxy["image"], index_raw, child_raw)
        proxy["image"] = expected["image"]
        require(same_document(spec, contract["execution_spec"]))
        require(any(x.get("type") == "Completed" and x.get("status") == "True"
                    for x in status["conditions"]))
        require(type(status.get("succeededCount")) is int and status["succeededCount"] == 1)
        require(all(status.get(key, 0) == 0 for key in ("failedCount", "cancelledCount", "runningCount", "retriedCount")))
        created = timestamp(metadata["creationTimestamp"])
        start, end = timestamp(status["startTime"]), timestamp(status["completionTime"])
        require(not_before <= created <= start <= end <= now and now - end <= MAX_AGE)
        require(end - start <= timedelta(seconds=180))
    except (KeyError, TypeError, IndexError, AttributeError):
        raise Rejected("B0 observer execution rejected") from None
    return {"execution": name, "start_utc": start.isoformat(), "completion_utc": end.isoformat(),
            "proxy_proof": proof}


HEAD_FIELDS = {
    "runs": {"total", "queued", "running", "awaiting_clarification", "awaiting_approval", "nonterminal",
             "open_lease_fields", "unexpired_leases", "unknown_status"},
    "answer_jobs": {"total", "queued", "running", "nonterminal", "open_lease_fields", "unexpired_leases", "unknown_status"},
}
OUTBOX_FIELDS = {"total", "pending", "pending_dispatchable", "pending_terminal", "pending_stale_input", "orphaned", "unknown_state"}
FIELDS = {**HEAD_FIELDS, **{x: OUTBOX_FIELDS for x in ("run_outbox", "answer_outbox")},
          **{x: {"prepared_model_steps", "unknown_kind", "unknown_state"} for x in ("run_steps", "answer_steps")},
          **{x: {"matches", "terminal", "lease_closed"} for x in ("q3_run", "q3_answer_job")}}
TRUE_FLAGS = {"fixed_question_three_terminal_and_leases_closed", "runtime_identity_change_clear_at_snapshot",
              "transaction_read_only_verified", "counts_and_booleans_only", "proxy_shutdown_verified",
              "snapshot_is_not_a_new_submission_or_queue_admission_fence",
              "terminal_pending_outbox_is_not_dispatchable_and_is_not_modified"}


def verify_report(report, execution_proof, *, now):
    require(set(report) == TRUE_FLAGS | {"version", "state", "project", "counts", "captured_utc",
                                       "user_records_prompts_payloads_credentials_selected_or_emitted"})
    require(all(report[x] is True for x in TRUE_FLAGS))
    require(report["user_records_prompts_payloads_credentials_selected_or_emitted"] is False)
    require(report["version"] == "ocean-beta-runtime-rollout-preflight-v1"
            and report["state"] == "read_only_rollout_preflight_verified"
            and report["project"] == "ocean-v1-beta-20261101")
    groups = report["counts"]
    require(type(groups) is dict and set(groups) == set(FIELDS))
    for name, fields in FIELDS.items():
        values = groups[name]
        require(type(values) is dict and set(values) == fields)
        require(all(type(v) is int and 0 <= v <= 9007199254740991 for v in values.values()))
        if name.startswith("q3_"):
            require(values == {"matches": 1, "terminal": 1, "lease_closed": 1})
        elif name in HEAD_FIELDS:
            require(all(v == 0 for k, v in values.items() if k != "total"))
        elif name.endswith("_steps"):
            require(all(v == 0 for v in values.values()))
        else:
            require(values["pending"] <= values["total"])
            require(all(values[k] <= values["pending"] for k in ("pending_dispatchable", "pending_terminal", "pending_stale_input")))
            require(all(values[k] == 0 for k in ("pending_dispatchable", "orphaned", "unknown_state")))
    require(groups["runs"]["total"] >= 1 and groups["answer_jobs"]["total"] >= 1)
    captured = timestamp(report["captured_utc"])
    require(timestamp(execution_proof["start_utc"]) <= captured <= timestamp(execution_proof["completion_utc"]) <= now)
    require(now - captured <= MAX_AGE)
    return {"captured_utc": captured.isoformat(), "aggregate_only_quiescence_verified": True,
            "snapshot_is_not_an_admission_fence": True}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--job", type=Path, required=True)
    parser.add_argument("--execution", type=Path)
    parser.add_argument("--execution-name")
    parser.add_argument("--report", type=Path)
    parser.add_argument("--not-before")
    args = parser.parse_args()
    try:
        contract = document(CONTRACT.read_bytes())
        result = {"version": "ocean-beta-b0-observer-proof-v1",
                  "job": verify_job(document(args.job.read_bytes()), contract),
                  "cloud_mutations": False, "rollout_cleared": False}
        options = (args.execution, args.execution_name, args.report, args.not_before)
        require(all(options) or not any(options))
        if args.execution:
            now = datetime.now(timezone.utc)
            proof = verify_execution(document(args.execution.read_bytes()), contract,
                name=args.execution_name, not_before=timestamp(args.not_before), now=now,
                index_raw=(PROOF / "proxy-index.json").read_bytes(),
                child_raw=(PROOF / "proxy-linux-amd64.json").read_bytes())
            result["execution"] = proof
            result["quiescence"] = verify_report(document(args.report.read_bytes()), proof, now=now)
        print(json.dumps(result, sort_keys=True))
        return 0
    except (Rejected, OSError, ValueError):
        print('{"state":"b0_preflight_rejected","rollout_cleared":false}')
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
