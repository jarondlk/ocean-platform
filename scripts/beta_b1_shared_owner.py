"""Fixed-image B1 admission drain/restore for the qualified owner-lock amendment.

No SQL, job, queue, IAM or secret mutation. Each PATCH is attempted once, with
an exclusive local intent and fresh provider etag. SQL amendment qualification
and current quiescence are separate gates, not implied by a generated plan.
"""
import argparse
from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import time
import urllib.parse

if not __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts import beta_b0_preflight as guard
from scripts import beta_b1_apply as cloud_api
from scripts import beta_b1_repair_rollout as repair
from scripts import beta_b1_rollout as original

IMAGE = "asia-northeast1-docker.pkg.dev/ocean-v1-beta-20261101/ocean-v1-beta/snapshot-api@sha256:5aedf3ba006901cd129e237632eab36aa06195d936ab1fd80c196863767f9ea7"
INITIAL = "ocean-v1-beta-serving-b1-ready-live-1115"
DRAIN = "ocean-v1-beta-serving-b1-share-drain-1116"
LIVE = "ocean-v1-beta-serving-b1-share-live-1116"
PHASES = ("drain", "restore-stage", "restore-promote")


def baseline(service, contract):
    guard.require(contract["version"] == repair.READY_VERSION and contract["image"] == IMAGE)
    guard.require(original.main_container(service, "serving")["image"] == IMAGE)
    normalized = deepcopy(service)
    original.main_container(normalized, "serving")["image"] = original.NEW
    original.verify_baseline(normalized, "serving", contract)


def plan(service, phase, contract):
    guard.require(phase in PHASES)
    baseline(service, contract)
    expected = original.configuration(service)
    ready, created = (service[k].split("/")[-1] for k in ("latestReadyRevision", "latestCreatedRevision"))
    enabled = original.flag_state(service)
    latest = [{"type": "TRAFFIC_TARGET_ALLOCATION_TYPE_LATEST", "percent": 100}]
    if phase == "drain":
        guard.require(ready == created == INITIAL and enabled and service["traffic"] == original.fixed_traffic(INITIAL))
        revision, enabled, traffic = DRAIN, False, latest
    elif phase == "restore-stage":
        guard.require(ready == created == DRAIN and not enabled and service["traffic"] == latest)
        revision, enabled, traffic = LIVE, True, original.fixed_traffic(DRAIN)
    else:
        guard.require(created == LIVE and ready in {DRAIN, LIVE} and enabled and service["traffic"] == original.fixed_traffic(DRAIN))
        revision, traffic = LIVE, original.fixed_traffic(LIVE)
    for item in original.main_container(expected, "serving")["env"]:
        if item["name"] in original.FLAGS:
            item["value"] = str(enabled).lower()
    expected["traffic"] = traffic
    body = {"name": service["name"], "etag": service["etag"], "traffic": traffic}
    mask = "traffic"
    if phase != "restore-promote":
        body["template"] = {"containers": deepcopy(expected["template"]["containers"]), "revision": revision}
        mask = "template.containers,template.revision,traffic"
    return {"phase": phase, "body": body, "update_mask": mask, "expected_configuration": expected,
        "before_configuration_sha256": original.sha(original.configuration(service)), "expected_ready_revision": revision}


def readback(before, after, proposal, contract, staged=None):
    baseline(after, contract)
    guard.require(original.sha(original.configuration(before)) == proposal["before_configuration_sha256"]
        and original.configuration(after) == proposal["expected_configuration"]
        and int(after["generation"]) > int(before["generation"])
        and after["latestCreatedRevision"].split("/")[-1] == proposal["expected_ready_revision"])
    idle = proposal["phase"] == "restore-stage"
    if idle and after["latestReadyRevision"] != after["latestCreatedRevision"]:
        guard.require(after["latestReadyRevision"] == before["latestReadyRevision"] and staged is not None)
        guard.require(original.verify_revision(after, staged, LIVE)["retired"])
    else:
        guard.require(after["latestReadyRevision"].split("/")[-1] == proposal["expected_ready_revision"])
    return {"phase": proposal["phase"], "generation": after["generation"],
        "ready_revision": after["latestReadyRevision"].split("/")[-1], "image": IMAGE,
        "all_other_configuration_preserved": True, "runtime_startup_verified": not idle}


def execute(cloud, directory, phase, *, validate_only, execution_name=None, not_before=None):
    contract = guard.document(repair.READY_CONTRACT.read_bytes())
    endpoint = "https://run.googleapis.com/v2/" + contract["services"]["serving"]["name"]
    before = cloud.request(endpoint)
    proposal = plan(before, phase, contract)
    target = directory / (phase + ("-validate" if validate_only else "-apply"))
    target.mkdir(mode=0o700)  # Refuse to replay any existing attempt.
    def save(name, value):
        (target / name).write_text(json.dumps(value, indent=2) + "\n")
    save("before.json", before)
    save("plan.json", proposal)
    if not validate_only and phase != "drain":
        guard.require(execution_name and not_before)
        cloud_api.fresh_entry(cloud, target, execution_name, not_before, phase)
        if phase == "restore-stage":
            guard.require((datetime.now(timezone.utc) - guard.timestamp(before["updateTime"])).total_seconds() > 60)
        else:
            staged = cloud.request(endpoint + "/revisions/" + LIVE)
            original.verify_revision(before, staged, LIVE)
            save("staged-before.json", staged)
    current = cloud.request(endpoint)
    guard.require(current["etag"] == before["etag"] and original.configuration(current) == original.configuration(before))
    params = {"updateMask": proposal["update_mask"]}
    if validate_only:
        params["validateOnly"] = "true"
    save("intent.json", {"utc": datetime.now(timezone.utc).isoformat(), "validate_only": validate_only,
        "single_patch_no_automatic_retry": True})
    operation = cloud.request(endpoint + "?" + urllib.parse.urlencode(params), method="PATCH", body=proposal["body"])
    save("operation.json", operation)
    if validate_only:
        guard.require(cloud.request(endpoint) == before)
        return {"phase": phase, "validated_only": True, "service_unchanged": True}
    deadline = time.monotonic() + 150
    while time.monotonic() < deadline:
        after = cloud.request(endpoint)
        if (str(after["generation"]) == str(after["observedGeneration"])
                and after.get("terminalCondition", {}).get("state") == "CONDITION_SUCCEEDED"):
            if phase != "restore-stage" and after["latestReadyRevision"].split("/")[-1] != proposal["expected_ready_revision"]:
                time.sleep(3)
                continue
            staged = cloud.request(endpoint + "/revisions/" + LIVE) if phase == "restore-stage" else None
            save("after.json", after)
            result = readback(before, after, proposal, contract, staged)
            save("result.json", result)
            return result
        time.sleep(3)
    raise guard.Rejected("Inspect uncertain PATCH; never replay automatically")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--phase", choices=PHASES, required=True)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--validate-only", action="store_true")
    mode.add_argument("--apply", action="store_true")
    parser.add_argument("--observer")
    parser.add_argument("--not-before")
    args = parser.parse_args()
    import os
    os.umask(0o077)
    directory = args.directory.resolve()
    guard.require(original.ROOT not in directory.parents and directory.is_dir()
        and directory.stat().st_uid == os.geteuid() and not directory.stat().st_mode & 0o077)
    try:
        print(json.dumps(execute(cloud_api.Cloud(), directory, args.phase, validate_only=args.validate_only,
            execution_name=args.observer, not_before=args.not_before)))
        return 0
    except Exception:
        print('{"state":"stopped_inspect_private_phase_before_retry"}')
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
