"""Apply one fixed B1 plan after fresh provider, authority and observer checks.

No IAM, secret-value, database, catalogue, queue or Scheduler write is supported.
PATCH is never retried. Inspect the retained outcome before repeating a command.
"""

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

if not __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts import beta_b0_preflight as observer
from scripts import beta_b1_rollout as rollout


PROJECT = rollout.PROJECT
REGION = rollout.REGION
JOB = "ocean-v1-beta-provider-preflight-20261111"
ACCOUNT = "dilokkalayakul.jaronchai.p8@dc.tohoku.ac.jp"
ACTIVATION = "4843e61b95c0c0af27079e669d9c661556a362fef3a4c17ce6a30ebe959a7694"
API_HOSTS = {"run.googleapis.com", "cloudtasks.googleapis.com", "cloudscheduler.googleapis.com",
             "secretmanager.googleapis.com", "storage.googleapis.com", "logging.googleapis.com",
             "asia-northeast1-run.googleapis.com"}


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        return None


def token(personal=False):
    env = dict(os.environ)
    for key in ("CLOUDSDK_CONFIG", "CLOUDSDK_ACTIVE_CONFIG_NAME", "CLOUDSDK_AUTH_ACCESS_TOKEN",
                "CLOUDSDK_AUTH_ACCESS_TOKEN_FILE", "CLOUDSDK_AUTH_CREDENTIAL_FILE_OVERRIDE",
                "CLOUDSDK_AUTH_IMPERSONATE_SERVICE_ACCOUNT", "GOOGLE_APPLICATION_CREDENTIALS"):
        env.pop(key, None)
    env["CLOUDSDK_CORE_DISABLE_PROMPTS"] = "1"
    command = (["gcloud", "--configuration=default", "--account=" + ACCOUNT, "--project=" + PROJECT,
                "auth", "print-access-token"] if personal else
               [str(rollout.ROOT / "scripts/gcloud_beta.sh"), "auth", "print-access-token", "--project=" + PROJECT])
    result = subprocess.run(command, env=env, capture_output=True, text=True, check=False)
    observer.require(result.returncode == 0 and bool(result.stdout.strip()))
    return result.stdout.strip()


class Cloud:
    def __init__(self):
        self.read_token = token()
        self.operator_token = token(personal=True)
        self.opener = urllib.request.build_opener(NoRedirect)

    def request(self, url, *, personal=False, method="GET", body=None):
        parsed = urllib.parse.urlsplit(url)
        observer.require(parsed.scheme == "https" and parsed.netloc in API_HOSTS and not parsed.fragment)
        raw = None if body is None else json.dumps(body).encode()
        request = urllib.request.Request(url, data=raw, method=method,
            headers={"Authorization": "Bearer " + (self.operator_token if personal else self.read_token),
                     "Content-Type": "application/json"})
        with self.opener.open(request, timeout=30) as response:
            observer.require(response.status == 200)
            return observer.document(response.read())


def observer_report(cloud, execution_name, execution):
    """Read every bounded log page, including empty continuation pages."""
    start = observer.timestamp(execution["metadata"]["creationTimestamp"]).isoformat()
    end = observer.timestamp(execution["status"]["completionTime"]).isoformat()
    query = {"resourceNames": ["projects/" + PROJECT], "filter":
        f'resource.type="cloud_run_job" AND resource.labels.job_name="{JOB}" '
        f'AND resource.labels.location="{REGION}" '
        f'AND labels."run.googleapis.com/execution_name"="{execution_name}" '
        f'AND timestamp>="{start}" AND timestamp<="{end}" '
        'AND (jsonPayload.version="ocean-beta-runtime-rollout-preflight-v1" '
        'OR textPayload:"ocean-beta-runtime-rollout-preflight-v1")',
        "pageSize": 100, "orderBy": "timestamp desc"}
    reports, seen = [], set()
    for _ in range(10):
        logs = cloud.request("https://logging.googleapis.com/v2/entries:list", method="POST", body=query)
        for entry in logs.get("entries", []):
            report = entry.get("jsonPayload")
            if report is None and entry.get("textPayload"):
                report = observer.document(entry["textPayload"].encode())
            if report and report.get("version") == "ocean-beta-runtime-rollout-preflight-v1":
                reports.append(report)
        next_page = logs.get("nextPageToken")
        if not next_page:
            observer.require(len(reports) == 1)
            return reports[0]
        observer.require(type(next_page) is str and next_page not in seen)
        seen.add(next_page)
        query["pageToken"] = next_page
    raise observer.Rejected("Observer log pagination incomplete")


def fresh_entry(cloud, directory, execution_name, not_before, phase):
    """Read actual provider state, not local acceptance booleans."""
    queue = f"https://cloudtasks.googleapis.com/v2/projects/{PROJECT}/locations/{REGION}/queues/ocean-v1-beta-research"
    q = cloud.request(queue, personal=True)
    tasks = cloud.request(queue + "/tasks?pageSize=1000", personal=True)
    schedules = cloud.request(f"https://cloudscheduler.googleapis.com/v1/projects/{PROJECT}/locations/{REGION}/jobs?pageSize=500", personal=True)
    observer.require(q["state"] == "PAUSED" and not tasks.get("tasks") and not tasks.get("nextPageToken")
                     and not schedules.get("jobs") and not schedules.get("nextPageToken"))
    iam = cloud.request(f"https://run.googleapis.com/v1/projects/{PROJECT}/locations/{REGION}/services/ocean-v1-beta-research-controller:getIamPolicy")
    observer.require(iam["bindings"] == [{"role": "roles/run.invoker", "members": [
        f"serviceAccount:ocean-v1-beta-task-invoker@{PROJECT}.iam.gserviceaccount.com"]}])
    metadata = cloud.request(f"https://secretmanager.googleapis.com/v1/projects/{PROJECT}/secrets/ocean-v1-beta-controller-database/versions/1", personal=True)
    observer.require(metadata["state"] == "ENABLED")
    # This checks only control/activation metadata, not scientific table payloads.
    bucket = PROJECT + "-snapshots"
    def object_read(key):
        url = f"https://storage.googleapis.com/storage/v1/b/{bucket}/o/" + urllib.parse.quote(key, safe="")
        before = cloud.request(url, personal=True)
        raw = cloud.request(url + "?alt=media&generation=" + before["generation"], personal=True)
        after = cloud.request(url, personal=True)
        observer.require(before["generation"] == after["generation"])
        return raw, before
    # Fetch exact bytes separately because the activation intentionally has two
    # accepted canonical encodings; a parsed-and-reserialized hash is insufficient.
    def raw_object(key, generation):
        url = f"https://storage.googleapis.com/storage/v1/b/{bucket}/o/" + urllib.parse.quote(key, safe="")
        request = urllib.request.Request(url + "?alt=media&generation=" + generation,
            headers={"Authorization": "Bearer " + cloud.operator_token})
        with cloud.opener.open(request, timeout=30) as response:
            return response.read()
    from ingestion.gcs_catalogue_snapshot import validated_lifecycle
    from api.v1_catalogue_host import _activation
    control, control_meta = object_read("v1/catalogue/control.json")
    control_raw = raw_object("v1/catalogue/control.json", control_meta["generation"])
    observer.require(observer.document(control_raw) == control)
    state = validated_lifecycle(control_raw)
    _, activation_meta = object_read("v1/catalogue/activations/" + ACTIVATION + ".json")
    activation_raw = raw_object("v1/catalogue/activations/" + ACTIVATION + ".json", activation_meta["generation"])
    observer.require(hashlib.sha256(activation_raw).hexdigest() == ACTIVATION
                     and activation_meta["generation"] == "1794232040589985")
    _, _, registrations, _ = _activation(activation_raw, research_enabled=True)
    selected = {s for r in registrations.values() for s in (r.snapshot_id, *r.child_snapshot_ids)}
    observer.require(all(s in state["snapshots"] and not state["snapshots"][s]["revoked"]
                         and not state["snapshots"][s]["retired"] for s in selected))
    observer.require(execution_name.startswith(JOB + "-") and "/" not in execution_name)
    prefix = f"https://{REGION}-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/{PROJECT}"
    job = cloud.request(prefix + "/jobs/" + JOB)
    execution = cloud.request(prefix + "/executions/" + execution_name)
    contract = observer.document(observer.CONTRACT.read_bytes())
    observer.verify_job(job, contract)
    report = observer_report(cloud, execution_name, execution)
    now = datetime.now(timezone.utc)
    proof = observer.verify_execution(execution, contract, name=execution_name,
        not_before=observer.timestamp(not_before), now=now,
        index_raw=(observer.PROOF / "proxy-index.json").read_bytes(),
        child_raw=(observer.PROOF / "proxy-linux-amd64.json").read_bytes())
    quiescence = observer.verify_report(report, proof, now=now)
    result = {"captured_utc": now.isoformat(), "phase": phase, "observer": proof,
              "quiescence": quiescence, "control_generation": control_meta["generation"],
              "control_revision": state["revision"], "queue": "PAUSED", "tasks": 0, "scheduler_jobs": 0}
    (directory / (phase + "-entry.json")).write_text(json.dumps(result, indent=2) + "\n")
    return result


def execute(cloud, directory, phase, *, validate_only, execution_name=None, not_before=None):
    contract = observer.document(rollout.CONTRACT_PATH.read_bytes())
    qualification = rollout.verify_candidate(directory)
    kind = "controller" if phase == "controller" else "serving"
    endpoint = "https://run.googleapis.com/v2/" + contract["services"][kind]["name"]
    before = cloud.request(endpoint)
    plan = rollout.plan_transition(before, phase, contract)
    plan["candidate_qualification"] = qualification
    target = directory / (phase + ("-validate" if validate_only else "-apply"))
    observer.require(not target.exists())
    target.mkdir(mode=0o700)
    (target / "before.json").write_text(json.dumps(before, indent=2) + "\n")
    (target / "plan.json").write_text(json.dumps(plan, indent=2) + "\n")
    if not validate_only and phase != "drain":
        observer.require(bool(execution_name) and bool(not_before))
        fresh_entry(cloud, target, execution_name, not_before, phase)
        if kind == "serving":
            controller = cloud.request("https://run.googleapis.com/v2/" + contract["services"]["controller"]["name"])
            rollout.verify_baseline(controller, "controller", contract)
            observer.require(rollout.main_container(controller, "controller")["image"] == rollout.NEW
                             and controller["latestReadyRevision"].split("/")[-1] == contract["revisions"]["controller"])
    # No receipt can waive the provider's fresh etag check. PATCH is sent once.
    fresh = cloud.request(endpoint)
    observer.require(fresh["etag"] == before["etag"] and rollout.configuration(fresh) == rollout.configuration(before))
    params = {"updateMask": plan["update_mask"]}
    if validate_only:
        params["validateOnly"] = "true"
    operation = cloud.request(endpoint + "?" + urllib.parse.urlencode(params),
        personal=kind == "controller", method="PATCH", body=plan["body"])
    (target / "operation.json").write_text(json.dumps(operation, indent=2) + "\n")
    if validate_only:
        after = cloud.request(endpoint)
        observer.require(rollout.same_document(before, after))
        return {"phase": phase, "validated_only": True, "service_exactly_unchanged": True}
    deadline = time.monotonic() + 150
    while time.monotonic() < deadline:
        after = cloud.request(endpoint)
        if (str(after["generation"]) == str(after["observedGeneration"])
                and after.get("terminalCondition", {}).get("state") in {"CONDITION_SUCCEEDED", "CONDITION_FAILED"}):
            (target / "after.json").write_text(json.dumps(after, indent=2) + "\n")
            result = rollout.verify_readback(before, after, plan, contract)
            (target / "result.json").write_text(json.dumps(result, indent=2) + "\n")
            return result
        time.sleep(3)
    raise observer.Rejected("Deployment outcome requires inspection; do not retry PATCH")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--phase", choices=rollout.PHASES, required=True)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--validate-only", action="store_true")
    mode.add_argument("--apply", action="store_true")
    parser.add_argument("--observer")
    parser.add_argument("--not-before")
    args = parser.parse_args()
    try:
        directory = args.directory.resolve()
        observer.require(rollout.ROOT not in directory.parents and directory.is_dir()
                         and directory.stat().st_uid == os.geteuid() and not directory.stat().st_mode & 0o077)
        os.umask(0o077)
        print(json.dumps(execute(Cloud(), directory, args.phase, validate_only=args.validate_only,
                                execution_name=args.observer, not_before=args.not_before), sort_keys=True))
        return 0
    except (observer.Rejected, KeyError, OSError, ValueError, urllib.error.HTTPError):
        print('{"state":"b1_stopped_inspect_private_phase_directory_before_retry"}')
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
