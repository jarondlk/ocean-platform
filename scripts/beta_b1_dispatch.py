"""Deliver exactly one canonical beta Research task; never resume the queue.

Only an undispatched task for the supplied public run/job UUID is accepted.
An intent file is retained before the sole tasks.run request. Uncertain outcomes
must be inspected; this command never retries or creates a replacement task.
"""

import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import sys
import urllib.parse

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
B2_RECEIPT = rollout.ROOT / 'docs/plans/ocean-v1/beta/b2-20261116/discovery-live-20261122.json'
B2_RECEIPT_SHA256 = 'd8e8fcf2874431bbc0d3772172827c7f1daca686ca310c51a4e2fa2597104556'
B2_RESTORATION_RECEIPT = rollout.ROOT / 'docs/plans/ocean-v1/beta/b4-20261124/research-trial-live.json'
B2_RESTORATION_RECEIPT_SHA256 = '2ff012cca762a03e7501b03381a29900c7dc8bfe328485d1f0671c170db997a9'
B2_SWEEP_RESTORATION_RECEIPT = rollout.ROOT / 'docs/plans/ocean-v1/beta/b4-20261124/research-sweep-live.json'
B2_SWEEP_RESTORATION_RECEIPT_SHA256 = '23a3ac6a6a4e875fd3e198a3f4eaa7f2839aed1e2ef9ae73f6eeb6e2feafe887'
B2_SWEEP_RESTORATION_GENERATION = '73'
B2_LAYOUT_RECEIPT = rollout.ROOT / 'docs/plans/ocean-v1/beta/b4-20261124/frontend-layout-live.json'
B2_LAYOUT_RECEIPT_SHA256 = 'b0c6d241e3d1db4b5977c7ac0183149b00756d7468b7a92535bacf941f5d6f27'
B2_LAYOUT_GENERATION = '74'
B2_PLEX_RECEIPT = rollout.ROOT / 'docs/plans/ocean-v1/beta/ui-20261126/frontend-plex-live.json'
B2_PLEX_RECEIPT_SHA256 = '9905548daf8bb9e24d675543ef4fbf56220f7ec76ab427f269839f10bad5b1d4'
B2_PLEX_GENERATION = '75'
B2_READABLE_RECEIPT = rollout.ROOT / 'docs/plans/ocean-v1/beta/ui-20261127/frontend-readable-live.json'
B2_READABLE_RECEIPT_SHA256 = 'e269d8df601c435f8321d87fe4d74aeafcd24919b214e22c0d43f1c51ad58458'
B2_READABLE_GENERATION = '76'
B2_WAIT_RECEIPT = rollout.ROOT / 'docs/plans/ocean-v1/beta/ui-20261127/frontend-wait-live.json'
B2_WAIT_RECEIPT_SHA256 = '42cbf674a7c395b1094194337839b8828cf50ef222f969d3752d53fe577eb9e0'
B2_WAIT_GENERATION = '77'
B2_SUPPORT_RECEIPT = rollout.ROOT / 'docs/plans/ocean-v1/beta/ui-20261127/frontend-support-live.json'
B2_SUPPORT_RECEIPT_SHA256 = '8092c303e0f183a135e0b4cf68aea02f38e8205795ba4fb0d154d39e8e111e2c'
B2_SUPPORT_GENERATION = '78'
# Readable-answer API image on both services (controller generation 11, serving 79).
ANSWERS_RECEIPT = rollout.ROOT / 'docs/plans/ocean-v1/beta/answers-20261127/answers-live.json'
ANSWERS_RECEIPT_SHA256 = 'e14e795fa62143114d77bfa71874e9d6c7740cdbfa7e4171eac016e77b0f25c5'
ANSWERS_CONTROLLER_GENERATION = '11'


def answers_deployment(cloud):
    """The answers receipt when the live controller is at its generation, else None."""
    controller = cloud.request(f'https://run.googleapis.com/v2/{rollout.PREFIX}/services/ocean-v1-beta-research-controller')
    if str(controller['generation']) != ANSWERS_CONTROLLER_GENERATION:
        return None
    raw = ANSWERS_RECEIPT.read_bytes()
    guard.require(hashlib.sha256(raw).hexdigest() == ANSWERS_RECEIPT_SHA256)
    receipt = guard.document(raw)
    guard.require(receipt['version'] == 'ocean-beta-answers-live-v1'
                  and receipt['project'] == rollout.PROJECT and receipt['region'] == rollout.REGION
                  and receipt['baseline_receipt_sha256'] == B2_RECEIPT_SHA256
                  and str(receipt['research_controller']['generation']) == ANSWERS_CONTROLLER_GENERATION
                  and receipt['research_controller']['new_image'] == receipt['serving']['new_image'] == receipt['image'])
    return receipt


def qualified_b2_serving(service, original):
    generation = str(service['generation'])
    frontend_only = generation in (B2_LAYOUT_GENERATION, B2_PLEX_GENERATION, B2_READABLE_GENERATION, B2_WAIT_GENERATION,
                                  B2_SUPPORT_GENERATION)
    if generation == B2_SUPPORT_GENERATION:
        path, digest = B2_SUPPORT_RECEIPT, B2_SUPPORT_RECEIPT_SHA256
        version = 'ocean-beta-frontend-support-live-v1'
    elif generation == B2_WAIT_GENERATION:
        path, digest = B2_WAIT_RECEIPT, B2_WAIT_RECEIPT_SHA256
        version = 'ocean-beta-frontend-wait-live-v1'
    elif generation == B2_READABLE_GENERATION:
        path, digest = B2_READABLE_RECEIPT, B2_READABLE_RECEIPT_SHA256
        version = 'ocean-beta-frontend-readable-live-v1'
    elif generation == B2_PLEX_GENERATION:
        path, digest = B2_PLEX_RECEIPT, B2_PLEX_RECEIPT_SHA256
        version = 'ocean-beta-frontend-plex-live-v1'
    elif generation == B2_LAYOUT_GENERATION:
        path, digest = B2_LAYOUT_RECEIPT, B2_LAYOUT_RECEIPT_SHA256
        version = 'ocean-beta-frontend-layout-live-v1'
    elif generation == B2_SWEEP_RESTORATION_GENERATION:
        path, digest = B2_SWEEP_RESTORATION_RECEIPT, B2_SWEEP_RESTORATION_RECEIPT_SHA256
        version = 'ocean-beta-b4-research-sweep-live-v1'
    else:
        path, digest = B2_RESTORATION_RECEIPT, B2_RESTORATION_RECEIPT_SHA256
        version = 'ocean-beta-b4-research-trial-live-v1'
    raw = path.read_bytes()
    guard.require(hashlib.sha256(raw).hexdigest() == digest)
    receipt = guard.document(raw)
    guard.require(receipt['version'] == version
                  and receipt['project'] == rollout.PROJECT and receipt['region'] == rollout.REGION
                  and receipt['baseline_receipt_sha256'] == B2_RECEIPT_SHA256)
    selection = receipt['deployment' if frontend_only else 'restoration']
    template = {**service['template'], 'revision': original['revision']}
    if frontend_only:
        frontend, = (item for item in template['containers'] if item.get('name') == 'frontend')
        guard.require(selection['only_frontend_image_and_revision_changed'] is True
                      and frontend['image'] == selection['frontend_after'])
        baseline_field = ('baseline_frontend_image' if generation in (B2_PLEX_GENERATION, B2_READABLE_GENERATION, B2_WAIT_GENERATION,
                                                             B2_SUPPORT_GENERATION)
                          else 'frontend_before')
        baseline_frontend = selection[baseline_field]
        template['containers'] = [
            {**item, 'image': baseline_frontend} if item is frontend else item
            for item in template['containers']
        ]
    else:
        guard.require(selection['normalized_previous_configuration_matches'] is True)
    guard.require(selection['baseline_configuration_sha256'] == original['configuration_sha256']
                  and rollout.sha({'template': template, 'traffic': service['traffic']})
                  == original['configuration_sha256'])
    return {'revision': selection['revision' if frontend_only else 'restored_revision'],
            'generation': selection['generation'],
            'configuration_sha256': selection['configuration_sha256'], 'new_image': selection['image']}


def verify_b2_deployment(cloud):
    raw = B2_RECEIPT.read_bytes()
    guard.require(hashlib.sha256(raw).hexdigest() == B2_RECEIPT_SHA256)
    receipt = guard.document(raw)
    image = receipt['image_proof']['image']
    guard.require(receipt['image_proof']['build_status'] == 'SUCCESS'
                  and receipt['image_proof']['offline_proof'] == 'success'
                  and receipt['initial_cold_discovery_delivery_passed'] is True)
    answers = answers_deployment(cloud)
    if answers is not None:
        # Both services must match the answers receipt exactly; no other serving
        # generation is qualified on the new image.
        receipt, image = answers, answers['image']
    for kind, slug, key in (('serving', 'ocean-v1-beta-serving', 'serving'),
                            ('controller', 'ocean-v1-beta-research-controller', 'research_controller')):
        name = f'{rollout.PREFIX}/services/{slug}'
        selection = receipt[key]
        service = cloud.request('https://run.googleapis.com/v2/' + name)
        if answers is None and kind == 'serving' and str(service['generation']) != str(selection['generation']):
            selection = qualified_b2_serving(service, selection)
        revision = selection['revision']
        active, = service['trafficStatuses']
        guard.require(service['name'] == name
                      and str(service['generation']) == str(service['observedGeneration']) == str(selection['generation'])
                      and service['terminalCondition']['state'] == 'CONDITION_SUCCEEDED'
                      and service['latestCreatedRevision'] == service['latestReadyRevision']
                      and service['latestReadyRevision'].split('/')[-1] == revision
                      and active['revision'] == revision and active['percent'] == 100
                      and selection['new_image'] == rollout.main_container(service, kind)['image'] == image
                      and rollout.sha({'template': service['template'], 'traffic': service['traffic']})
                      == selection['configuration_sha256'])
        if kind == 'serving':
            guard.require(rollout.flag_state(service))
    return f'{rollout.PREFIX}/services/ocean-v1-beta-research-controller'


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


def one_queued_task(cloud, queue):
    """Require one task across complete bounded pages, not one first page."""
    tasks, seen = [], set()
    query = {"pageSize": 1000, "responseView": "FULL"}
    for _ in range(10):
        page = cloud.request(queue + "/tasks?" + urllib.parse.urlencode(query), personal=True)
        tasks.extend(page.get("tasks", []))
        guard.require(len(tasks) <= 1)
        token = page.get("nextPageToken")
        if not token:
            guard.require(len(tasks) == 1)
            return tasks[0]
        guard.require(type(token) is str and token not in seen)
        seen.add(token)
        query["pageToken"] = token
    raise guard.Rejected("Task listing incomplete")


def execute(cloud, directory, kind, identity, *, repair_candidate=False, list_candidate=False, b2_candidate=False):
    guard.require(sum((repair_candidate, list_candidate, b2_candidate)) <= 1)
    if b2_candidate:
        return dispatch(cloud, directory, kind, identity, verify_b2_deployment(cloud))
    if repair_candidate or list_candidate:
        from scripts import beta_b1_repair_rollout as repair
        contract = guard.document((repair.LIST_CONTRACT if list_candidate else repair.CONTRACT).read_bytes())
        repair.qualify(directory, contract)
        verify_baseline, image = repair.baseline, contract['image']
    else:
        contract = guard.document(rollout.CONTRACT_PATH.read_bytes())
        verify_baseline, image = rollout.verify_baseline, rollout.NEW
    for name in ("controller", "serving"):
        service = cloud.request("https://run.googleapis.com/v2/" + contract["services"][name]["name"])
        verify_baseline(service, name, contract)
        guard.require(rollout.main_container(service, name)["image"] == image)
        revision = contract["revisions"]["controller" if name == "controller" else "live"]
        guard.require(service["latestCreatedRevision"] == service["latestReadyRevision"]
                      and service["latestReadyRevision"].split("/")[-1] == revision)
        if name == "serving":
            guard.require(rollout.flag_state(service)
                          and guard.same_document(service["traffic"], rollout.fixed_traffic(revision)))
    return dispatch(cloud, directory, kind, identity, contract['services']['controller']['name'])


def dispatch(cloud, directory, kind, identity, controller):
    iam = cloud.request("https://run.googleapis.com/v1/" + controller + ":getIamPolicy")
    guard.require(iam["bindings"] == [{"role": "roles/run.invoker", "members": [
        "serviceAccount:" + SETTINGS.task_invoker_email]}])
    queue = "https://cloudtasks.googleapis.com/v2/" + SETTINGS.queue_path
    guard.require(cloud.request(queue, personal=True)["state"] == "PAUSED")
    intent = validate_task(one_queued_task(cloud, queue), kind, identity)
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
    candidate = parser.add_mutually_exclusive_group()
    candidate.add_argument('--repair-candidate', action='store_true', help='Require the separately qualified exact B1 repair image/CI contract')
    candidate.add_argument('--list-candidate', action='store_true', help='Require the separately qualified exact list-read image/CI contract')
    candidate.add_argument('--b2-candidate', action='store_true', help='Require the accepted B2 discovery images and service configurations')
    args = parser.parse_args()
    try:
        directory = args.directory.resolve()
        guard.require(rollout.ROOT not in directory.parents and directory.is_dir()
                      and directory.stat().st_uid == os.geteuid() and not directory.stat().st_mode & 0o077)
        os.umask(0o077)
        print(json.dumps(execute(Cloud(), directory, args.kind, args.identity,
            repair_candidate=args.repair_candidate, list_candidate=args.list_candidate, b2_candidate=args.b2_candidate), sort_keys=True))
        return 0
    except (guard.Rejected, KeyError, OSError, ValueError):
        print('{"state":"manual_delivery_stopped_inspect_intent_before_retry"}')
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
