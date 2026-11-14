"""Construct and verify narrow beta-only Cloud Run updates; never fetch credentials.

The operator supplies fresh provider readbacks. A plan is not clearance to apply:
current authority, source/build/CI, budget and post-drain quiescence are separate
required checks. Plans and raw service metadata stay in private operator storage.
"""

import argparse
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import re
import sys

if not __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.beta_b0_preflight import Rejected, document, require, same_document


ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = ROOT / "deploy/gcp/beta/b1/rollout-contract.json"
PROJECT = "ocean-v1-beta-20261101"
REGION = "asia-northeast1"
PREFIX = f"projects/{PROJECT}/locations/{REGION}"
OLD = "asia-northeast1-docker.pkg.dev/ocean-v1-beta-20261101/ocean-v1-beta/snapshot-api@sha256:4b24ca90a47c22f14c05987b958121780418c28b4f0563e8c88d0b8bb3e4999a"
NEW = "asia-northeast1-docker.pkg.dev/ocean-v1-beta-20261101/ocean-v1-beta/snapshot-api@sha256:7889ef206cb34008e5a5806ab8bd0ebff486501e53160862e94bfd12b8d875f8"
FLAGS = {"ENABLE_V1_RESEARCH_DISPATCH", "ENABLE_V1_SYNTHESIS"}
OUTPUT_FIELDS = {"uid", "generation", "createTime", "updateTime", "deleteTime", "expireTime", "creator",
                 "lastModifier", "observedGeneration", "terminalCondition", "conditions", "latestReadyRevision",
                 "latestCreatedRevision", "trafficStatuses", "uri", "urls", "etag", "reconciling", "satisfiesPzs"}
PHASES = ("controller", "stage", "promote", "admit-stage", "admit-promote", "drain")


def sha(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def configuration(service):
    result = {k: deepcopy(v) for k, v in service.items() if k not in OUTPUT_FIELDS}
    result["template"].pop("revision", None)
    return result


def main_container(service, kind):
    name = "controller" if kind == "controller" else "api"
    matches = [c for c in service["template"]["containers"] if c.get("name") == name]
    require(len(matches) == 1)
    return matches[0]


def flag_state(service):
    entries = [e for e in main_container(service, "serving")["env"] if e.get("name") in FLAGS]
    require(len(entries) == 2 and {e["name"] for e in entries} == FLAGS)
    require(all(set(e) == {"name", "value"} and e["value"] in {"true", "false"} for e in entries))
    values = {e["value"] for e in entries}
    require(len(values) == 1)
    return values.pop() == "true"


def fixed_traffic(revision):
    return [{"type": "TRAFFIC_TARGET_ALLOCATION_TYPE_REVISION", "revision": revision, "percent": 100}]


def baseline_configuration(service, kind):
    result = configuration(service)
    main = main_container(result, kind)
    require(main["image"] in {OLD, NEW})
    main["image"] = OLD
    result["traffic"] = [{"type": "TRAFFIC_TARGET_ALLOCATION_TYPE_LATEST", "percent": 100}]
    if kind == "serving":
        flag_state(result)
        for entry in main["env"]:
            if entry["name"] in FLAGS:
                entry["value"] = "false"
    return result


def verify_baseline(service, kind, contract):
    entry = contract["services"][kind]
    require(service["name"] == entry["name"] and service["uid"] == entry["uid"])
    require(sha(baseline_configuration(service, kind)) == entry["baseline_configuration_sha256"])
    require(type(service.get("etag")) is str and bool(service["etag"]))
    require(service.get("terminalCondition", {}).get("state") == "CONDITION_SUCCEEDED")
    require(str(service["generation"]) == str(service["observedGeneration"]))
    return entry


def revision_name(contract, phase):
    return contract["revisions"]["controller" if phase == "controller" else "live" if phase.startswith("admit") or phase == "drain" else "stage"]


def plan_transition(service, phase, contract):
    require(phase in PHASES)
    kind = "controller" if phase == "controller" else "serving"
    entry = verify_baseline(service, kind, contract)
    before = configuration(service)
    expected = deepcopy(before)
    image = main_container(service, kind)["image"]
    ready = service["latestReadyRevision"].split("/")[-1]
    require(service["latestCreatedRevision"] == service["latestReadyRevision"])
    revision = revision_name(contract, phase)
    require(re.fullmatch(re.escape(entry["name"].split("/")[-1]) + r"-[a-z0-9-]+[a-z0-9]", revision)
            and len(revision) <= 63)
    body = {"name": service["name"], "etag": service["etag"]}
    mask = []
    if phase == "controller":
        require(image == OLD and ready == entry["initial_revision"])
        require(same_document(service["traffic"], [{"type": "TRAFFIC_TARGET_ALLOCATION_TYPE_LATEST", "percent": 100}]))
        main_container(expected, kind)["image"] = NEW
    else:
        enabled = flag_state(service)
        if phase == "stage":
            require(image == OLD and not enabled and ready == entry["initial_revision"])
            require(same_document(service["traffic"], [{"type": "TRAFFIC_TARGET_ALLOCATION_TYPE_LATEST", "percent": 100}]))
            main_container(expected, kind)["image"] = NEW
            expected["traffic"] = fixed_traffic(ready)
        elif phase == "promote":
            require(image == NEW and not enabled and ready == contract["revisions"]["stage"])
            require(same_document(service["traffic"], fixed_traffic(entry["initial_revision"])))
            expected["traffic"] = fixed_traffic(ready)
        elif phase == "admit-stage":
            require(image == NEW and not enabled and ready == contract["revisions"]["stage"])
            require(same_document(service["traffic"], fixed_traffic(ready)))
            for e in main_container(expected, kind)["env"]:
                if e["name"] in FLAGS:
                    e["value"] = "true"
        elif phase == "admit-promote":
            require(image == NEW and enabled and ready == contract["revisions"]["live"])
            require(same_document(service["traffic"], fixed_traffic(contract["revisions"]["stage"])))
            expected["traffic"] = fixed_traffic(ready)
        else:
            require(image == NEW and enabled)
            revision = contract["revisions"]["drain"]
            for e in main_container(expected, kind)["env"]:
                if e["name"] in FLAGS:
                    e["value"] = "false"
            expected["traffic"] = [{"type": "TRAFFIC_TARGET_ALLOCATION_TYPE_LATEST", "percent": 100}]
    new_revision = phase in {"controller", "stage", "admit-stage", "drain"}
    if new_revision:
        body["template"] = {"containers": deepcopy(expected["template"]["containers"]), "revision": revision}
        mask += ["template.containers", "template.revision"]
    if not same_document(before["traffic"], expected["traffic"]):
        body["traffic"] = expected["traffic"]
        mask.append("traffic")
    require(bool(mask))
    return {"version": "ocean-beta-b1-narrow-plan-v1", "phase": phase, "method": "PATCH",
            "endpoint": "https://run.googleapis.com/v2/" + service["name"],
            "update_mask": ",".join(mask), "body": body, "before_generation": service["generation"],
            "before_configuration_sha256": sha(before), "expected_configuration": expected,
            "expected_ready_revision": revision if new_revision else ready,
            "creates_revision": new_revision, "rollout_cleared": False}


def verify_readback(before, after, plan, contract):
    kind = "controller" if plan["phase"] == "controller" else "serving"
    verify_baseline(after, kind, contract)
    require(sha(configuration(before)) == plan["before_configuration_sha256"])
    require(same_document(configuration(after), plan["expected_configuration"]))
    require(int(after["generation"]) > int(before["generation"]))
    require(after["latestReadyRevision"].split("/")[-1] == plan["expected_ready_revision"])
    require(after["latestCreatedRevision"] == after["latestReadyRevision"])
    return {"phase": plan["phase"], "generation": after["generation"],
            "ready_revision": plan["expected_ready_revision"], "all_other_configuration_preserved": True}


def verify_build(build, expected):
    require(build["id"] == "ec6296cd-55ea-42ec-a50a-552364f2a62c" and build["status"] == "SUCCESS")
    require(build["projectId"] == PROJECT and build["name"] in {
        f"projects/{p}/locations/{REGION}/builds/{build['id']}" for p in (PROJECT, "534831104543")})
    require(build["serviceAccount"] == expected["serviceAccount"])
    require(build["images"] == expected["images"] and build["timeout"] == expected["timeout"])
    require(build["tags"] == expected["tags"])
    require(not any(key in build for key in ("secrets", "availableSecrets", "substitutions", "buildTriggerId")))
    options = deepcopy(build["options"])
    require(options.pop("pool", {}) == {} and options.pop("workerRelease", "legacy") == "legacy")
    require(str(options["diskSizeGb"]) == "100")
    options["diskSizeGb"] = 100
    require(same_document(options, expected["options"]))
    require(len(build["steps"]) == len(expected["steps"]) == 4)
    for actual, wanted in zip(build["steps"], expected["steps"]):
        require(actual["status"] == "SUCCESS")
        value = {k: v for k, v in actual.items() if k not in {"status", "timing", "pullTiming"}}
        target = deepcopy(wanted)
        if target["id"] == "immutable-source-label-proof":
            target["args"] = [x.replace("$$", "$") for x in target["args"]]
        require(same_document(value, target))
    require(len(build["results"]["images"]) == 1
            and build["results"]["images"][0]["digest"] == NEW.split("@")[1])
    source = build["sourceProvenance"]["resolvedStorageSource"]
    require(source["bucket"] == PROJECT + "-build-source" and source["object"].startswith("source/")
            and str(source["generation"]).isdecimal())
    require(build["source"] == {"storageSource": source})
    return {"build": build["id"], "image": NEW, "all_four_exact_proofs_successful": True}


def verify_candidate(directory):
    """Accept only the previously reviewed exact source/build/composed-CI proof."""
    base = ROOT / "docs/plans/ocean-v1/beta/research-20261109/provider-amendment06"
    ci = document((base / "ci.json").read_bytes())
    require(ci["source_revision"] == "0f15bbcae3ad73ed76ddb32dd57b3a03dbedb49f")
    source = document((base / "production-source-manifest.json").read_bytes())["sources"]
    require(len(source) == 180 and all(hashlib.sha256((ROOT / p).read_bytes()).hexdigest() == h for p, h in source.items()))
    hashes = {"normal-workflow.yml": "60848d40908c66aa3832c31943376350a465a7f5958b5c562e18eaa4ce402cb0",
              "diagnostic-workflow.yml": "55bb71a44a87ce68701aff39b66cb70c65b4246c4cfaa63e54b32141e8fed84c",
              "postgres.log": "d4133a90458730ad45cb0a6d35105e86e515decb7e1753b36d024d152b676b21"}
    for name, expected in hashes.items():
        require(hashlib.sha256((directory / name).read_bytes()).hexdigest() == expected)
    for filename, records, run_id in (
        ("normal_jobs.json", ci["original_normal_workflow"]["reused_successful_jobs"], 42941802734),
        ("diagnostic_jobs.json", ci["postgres_workflow_only_supersession"]["jobs"], 43020625782),
    ):
        jobs = document((directory / filename).read_bytes())["jobs"]
        by_id = {j["id"]: j for j in jobs}
        require(len(by_id) == len(jobs))
        for expected in records:
            j = by_id[expected["id"]]
            require(j["run_id"] == run_id and j["name"] == expected["name"]
                    and j["status"] == "completed" and j["conclusion"] == "success")
            require(bool(j["steps"]) and all(s["status"] == "completed" and s["conclusion"] == "success" for s in j["steps"]))
    proof = verify_build(document((directory / "build.json").read_bytes()), document((base / "cloudbuild.json").read_bytes()))
    return {**proof, "runtime_commit": ci["source_revision"], "source_paths": len(source),
            "composed_CI_accepted": True, "normal_workflow_still_failed": True,
            "interpreter_crash_cause_proven": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--before", type=Path, required=True)
    parser.add_argument("--phase", choices=PHASES, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--qualification", type=Path, required=True)
    args = parser.parse_args()
    try:
        output = args.output.absolute()
        require(ROOT not in output.parents and not output.exists() and not output.is_symlink())
        require(output.parent.is_dir() and not output.parent.is_symlink()
                and output.parent.stat().st_uid == os.geteuid() and not output.parent.stat().st_mode & 0o077)
        qualification = verify_candidate(args.qualification)
        plan = plan_transition(document(args.before.read_bytes()), args.phase, document(CONTRACT_PATH.read_bytes()))
        plan["candidate_qualification"] = qualification
        fd = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, "w") as f:
            json.dump(plan, f, indent=2, sort_keys=True)
            f.write("\n")
        print(json.dumps({"phase": args.phase, "plan_sha256": sha(plan), "cloud_mutations": False,
                          "update_mask": plan["update_mask"], "rollout_cleared": False}))
        return 0
    except (Rejected, KeyError, ValueError, OSError):
        print('{"state":"b1_plan_rejected","cloud_mutations":false}')
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
