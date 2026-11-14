"""Deliver exactly one canonical beta Research task; never resume the queue.

Only an undispatched task for the supplied public run/job UUID is accepted.
An intent file is retained before the sole tasks.run request. Uncertain outcomes
must be inspected; this command never retries or creates a replacement task.
"""

import argparse
import base64
import json
import os
from pathlib import Path
import sys

if not __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from orchestration.cloud_research_dispatch import CloudResearchQueue, CloudResearchSettings, delivery_body
from scripts import beta_b0_preflight as guard
from scripts import beta_b1_rollout as rollout
from scripts.beta_b1_apply import Cloud


SETTINGS = CloudResearchSettings(version="ocean-v1-beta-research-cloud-v1",
    project_id=rollout.PROJECT, region=rollout.REGION, queue_id="ocean-v1-beta-research",
    controller_origin="https://ocean-v1-beta-research-controller-534831104543.asia-northeast1.run.app",
    task_invoker_email="ocean-v1-beta-task-invoker@ocean-v1-beta-20261101.iam.gserviceaccount.com",
    task_invoker_subject="105490365082123397320")


def validate_task(task, kind, identity):
    request = task["httpRequest"]
    body = guard.document(base64.b64decode(request["body"], validate=True))
    expected_body = delivery_body(kind, identity, body["delivery_id"])
    guard.require(guard.same_document(body, expected_body))
    expected = CloudResearchQueue(settings=SETTINGS, kind=kind).task(
        delivery_id=body["delivery_id"], **{"run_id" if kind == "run" else "job_id": identity})
    guard.require(task["name"] == expected["name"] and task["dispatchDeadline"] == expected["dispatchDeadline"])
    guard.require(all(request.get(k) == expected["httpRequest"][k]
                      for k in ("url", "httpMethod", "body", "oidcToken")))
    headers = {k.lower(): v for k, v in request.get("headers", {}).items()}
    guard.require(headers.get("content-type") == "application/json"
                  and set(headers) <= {"content-type", "user-agent"})
    guard.require(not task.get("dispatchCount", 0) and not task.get("responseCount", 0))
    return {"version": "ocean-beta-b1-single-task-intent-v1", "kind": kind,
            "identity": identity, "delivery_id": body["delivery_id"], "task": task["name"],
            "canonical_target_identity_and_body_verified": True,
            "prior_dispatches": 0, "queue_must_remain_paused": True,
            "automatic_retry_permitted": False, "successful_answer_claimed": False}


def execute(cloud, directory, kind, identity):
    contract = guard.document(rollout.CONTRACT_PATH.read_bytes())
    for name in ("controller", "serving"):
        service = cloud.request("https://run.googleapis.com/v2/" + contract["services"][name]["name"])
        rollout.verify_baseline(service, name, contract)
        guard.require(rollout.main_container(service, name)["image"] == rollout.NEW)
        revision = contract["revisions"]["controller" if name == "controller" else "live"]
        guard.require(service["latestCreatedRevision"] == service["latestReadyRevision"]
                      and service["latestReadyRevision"].split("/")[-1] == revision)
        if name == "serving":
            guard.require(rollout.flag_state(service)
                          and guard.same_document(service["traffic"], rollout.fixed_traffic(revision)))
    iam = cloud.request("https://run.googleapis.com/v1/" + contract["services"]["controller"]["name"] + ":getIamPolicy")
    guard.require(iam["bindings"] == [{"role": "roles/run.invoker", "members": [
        "serviceAccount:" + SETTINGS.task_invoker_email]}])
    queue = "https://cloudtasks.googleapis.com/v2/" + SETTINGS.queue_path
    guard.require(cloud.request(queue, personal=True)["state"] == "PAUSED")
    tasks = cloud.request(queue + "/tasks?pageSize=1000&responseView=FULL", personal=True)
    guard.require(not tasks.get("nextPageToken") and len(tasks.get("tasks", [])) == 1)
    intent = validate_task(tasks["tasks"][0], kind, identity)
    target = directory / ("manual-" + kind + "-" + identity)
    guard.require(not target.exists())
    target.mkdir(mode=0o700)
    (target / "intent.json").write_text(json.dumps(intent, indent=2) + "\n")
    # Exactly one write. The default BASIC response excludes the task body.
    result = cloud.request("https://cloudtasks.googleapis.com/v2/" + intent["task"] + ":run",
                           personal=True, method="POST", body={"responseView": "BASIC"})
    (target / "acknowledgement.json").write_text(json.dumps(result, indent=2) + "\n")
    guard.require(result["name"] == intent["task"])
    return {"task_dispatch_requested": True, "kind": kind, "identity": identity,
            "successful_answer_claimed": False, "queue_resumed": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--kind", choices=("run", "answer"), required=True)
    parser.add_argument("--identity", required=True)
    args = parser.parse_args()
    try:
        directory = args.directory.resolve()
        guard.require(rollout.ROOT not in directory.parents and directory.is_dir()
                      and directory.stat().st_uid == os.geteuid() and not directory.stat().st_mode & 0o077)
        os.umask(0o077)
        print(json.dumps(execute(Cloud(), directory, args.kind, args.identity), sort_keys=True))
        return 0
    except (guard.Rejected, KeyError, OSError, ValueError):
        print('{"state":"manual_delivery_stopped_inspect_intent_before_retry"}')
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
