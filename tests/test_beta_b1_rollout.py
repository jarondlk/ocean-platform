"""Preservation and phase-order tests for the fixed beta image rollout planner."""

from copy import deepcopy
import json

import pytest

from scripts import beta_b1_rollout as rollout


def make_material():
    def service(kind):
        name = "ocean-v1-beta-research-controller" if kind == "controller" else "ocean-v1-beta-serving"
        main = {"name": "controller" if kind == "controller" else "api", "image": rollout.OLD,
                "env": [{"name": "ENABLE_V1_RESEARCH_DISPATCH", "value": "false"},
                        {"name": "ENABLE_V1_SYNTHESIS", "value": "false"},
                        {"name": "DSN", "valueSource": {"secretKeyRef": {"secret": "fixed", "version": "1"}}}],
                "resources": {"limits": {"cpu": "1", "memory": "1Gi"}}, "dependsOn": ["sql-proxy"]}
        result = {"name": rollout.PREFIX + "/services/" + name, "uid": kind + "-fixed-uid", "etag": "fresh-etag",
                  "generation": "2", "observedGeneration": "2", "ingress": "INGRESS_TRAFFIC_INTERNAL_ONLY",
                  "template": {"serviceAccount": kind + "@example.com", "timeout": "60s",
                               "scaling": {"maxInstanceCount": 1}, "vpcAccess": {"egress": "PRIVATE_RANGES_ONLY"},
                               "containers": [main, {"name": "sql-proxy", "image": "fixed-proxy@sha256:fixed"}]},
                  "traffic": [{"type": "TRAFFIC_TARGET_ALLOCATION_TYPE_LATEST", "percent": 100}],
                  "terminalCondition": {"state": "CONDITION_SUCCEEDED"},
                  "latestReadyRevision": rollout.PREFIX + "/services/" + name + "/revisions/" + name + "-old",
                  "latestCreatedRevision": rollout.PREFIX + "/services/" + name + "/revisions/" + name + "-old"}
        if kind == "serving":
            result["template"]["containers"].insert(0, {"name": "frontend", "image": "fixed-frontend@sha256:fixed"})
        return result
    serving, controller = service("serving"), service("controller")
    contract = {"services": {}, "revisions": {"controller": "ocean-v1-beta-research-controller-b1-test",
                "stage": "ocean-v1-beta-serving-b1-stage-test", "live": "ocean-v1-beta-serving-b1-live-test",
                "drain": "ocean-v1-beta-serving-b1-drain-test"}}
    for kind, s in [("serving", serving), ("controller", controller)]:
        contract["services"][kind] = {"name": s["name"], "uid": s["uid"],
            "initial_revision": s["latestReadyRevision"].split("/")[-1],
            "baseline_configuration_sha256": rollout.sha(rollout.baseline_configuration(s, kind))}
    return serving, controller, contract


@pytest.fixture
def material():
    return make_material()


def completed(before, plan):
    result = {**deepcopy(before), **deepcopy(plan["expected_configuration"])}
    result["generation"] = result["observedGeneration"] = str(int(before["generation"]) + 1)
    result["etag"] = "new-etag"
    result["latestReadyRevision"] = result["latestCreatedRevision"] = before["name"] + "/revisions/" + plan["expected_ready_revision"]
    return result


def test_complete_ordered_phase_graph_preserves_configuration(material):
    serving, controller, contract = material
    plan = rollout.plan_transition(controller, "controller", contract)
    after = completed(controller, plan)
    assert rollout.verify_readback(controller, after, plan, contract)["all_other_configuration_preserved"]
    assert plan["update_mask"] == "template.containers,template.revision"
    for phase in ("stage", "promote", "admit-stage", "admit-promote", "drain"):
        plan = rollout.plan_transition(serving, phase, contract)
        after = completed(serving, plan)
        assert rollout.verify_readback(serving, after, plan, contract)["all_other_configuration_preserved"]
        assert plan["body"]["etag"] == serving["etag"]
        if phase in {"promote", "admit-promote"}:
            assert plan["update_mask"] == "traffic" and "template" not in plan["body"]
        assert rollout.main_container(after, "serving")["image"] == rollout.NEW
        assert next(c for c in after["template"]["containers"] if c["name"] == "frontend")["image"] == "fixed-frontend@sha256:fixed"
        serving = after
    assert not rollout.flag_state(serving)


@pytest.mark.parametrize("target", ["identity", "secret", "sidecar", "frontend", "scale", "network", "timeout", "ingress", "image", "extra", "project", "uid"])
def test_initial_configuration_drift_is_rejected(material, target):
    service, _, contract = material
    main = rollout.main_container(service, "serving")
    if target == "identity":
        service["template"]["serviceAccount"] = "other@example.com"
    elif target == "secret":
        main["env"][2]["valueSource"]["secretKeyRef"]["version"] = "latest"
    elif target in {"sidecar", "frontend"}:
        service["template"]["containers"][-1 if target == "sidecar" else 0]["image"] = "wrong"
    elif target == "scale":
        service["template"]["scaling"]["maxInstanceCount"] = 5
    elif target == "network":
        service["template"]["vpcAccess"]["egress"] = "ALL_TRAFFIC"
    elif target == "timeout":
        service["template"]["timeout"] = "600s"
    elif target == "ingress":
        service["ingress"] = "INGRESS_TRAFFIC_ALL"
    elif target == "image":
        main["image"] = "unreviewed:latest"
    elif target == "extra":
        service["customAudiences"] = ["unreviewed"]
    elif target == "project":
        service["name"] = service["name"].replace(rollout.PROJECT, "legacy-project")
    else:
        service["uid"] = "recreated-service"
    with pytest.raises(rollout.Rejected):
        rollout.plan_transition(service, "stage", contract)


@pytest.mark.parametrize("phase", ["promote", "admit-stage", "admit-promote", "drain"])
def test_phase_cannot_be_skipped(material, phase):
    with pytest.raises(rollout.Rejected):
        rollout.plan_transition(material[0], phase, material[2])


@pytest.mark.parametrize("target", ["stale_generation", "not_ready", "wrong_revision", "changed_env", "wrong_traffic"])
def test_provider_readback_must_match_entire_expected_configuration(material, target):
    service, _, contract = material
    plan = rollout.plan_transition(service, "stage", contract)
    after = completed(service, plan)
    if target == "stale_generation":
        after["observedGeneration"] = service["generation"]
    elif target == "not_ready":
        after["terminalCondition"]["state"] = "CONDITION_FAILED"
    elif target == "wrong_revision":
        after["latestReadyRevision"] = after["latestCreatedRevision"] = service["latestReadyRevision"]
    elif target == "changed_env":
        rollout.main_container(after, "serving")["env"].append({"name": "EXTRA", "value": "yes"})
    else:
        after["traffic"] = [{"type": "TRAFFIC_TARGET_ALLOCATION_TYPE_LATEST", "percent": 100}]
    with pytest.raises(rollout.Rejected):
        rollout.verify_readback(service, after, plan, contract)


def test_false_and_true_admission_cannot_mix(material):
    service, _, contract = material
    rollout.main_container(service, "serving")["env"][0]["value"] = "true"
    with pytest.raises(rollout.Rejected):
        rollout.plan_transition(service, "stage", contract)


def test_planning_does_not_mutate_input_and_never_grants_clearance(material):
    service, _, contract = material
    original = deepcopy(service)
    plan = rollout.plan_transition(service, "stage", contract)
    assert original == service and plan["rollout_cleared"] is False
    assert json.loads(json.dumps(plan))["endpoint"].startswith("https://run.googleapis.com/v2/" + rollout.PREFIX)


def build_fixture():
    config = json.loads((rollout.ROOT / "docs/plans/ocean-v1/beta/research-20261109/provider-amendment06/cloudbuild.json").read_text())
    build = deepcopy(config)
    build.update(id="ec6296cd-55ea-42ec-a50a-552364f2a62c", status="SUCCESS", projectId=rollout.PROJECT,
                 name="projects/534831104543/locations/asia-northeast1/builds/ec6296cd-55ea-42ec-a50a-552364f2a62c")
    build["options"].update(diskSizeGb="100", pool={}, workerRelease="legacy")
    for step in build["steps"]:
        step["status"] = "SUCCESS"
        if step["id"] == "immutable-source-label-proof":
            step["args"] = [a.replace("$$", "$") for a in step["args"]]
    build["results"] = {"images": [{"digest": rollout.NEW.split("@")[1]}]}
    source = {"bucket": rollout.PROJECT + "-build-source", "object": "source/fixed.tgz", "generation": "123"}
    build["source"] = {"storageSource": source}
    build["sourceProvenance"] = {"resolvedStorageSource": source}
    return build, config


def test_exact_four_build_proofs_with_only_documented_normalizations():
    build, config = build_fixture()
    assert rollout.verify_build(build, config)["all_four_exact_proofs_successful"]


@pytest.mark.parametrize("target", ["project", "identity", "source", "extra_secret", "root", "network", "step_status", "digest", "options"])
def test_build_changes_or_added_privileges_rejected(target):
    build, config = build_fixture()
    if target == "project":
        build["projectId"] = "legacy-project"
    elif target == "identity":
        build["serviceAccount"] = "unreviewed"
    elif target == "source":
        build["source"]["storageSource"] = {**build["source"]["storageSource"], "bucket": "unreviewed"}
    elif target == "extra_secret":
        build["availableSecrets"] = {}
    elif target in {"root", "network"}:
        build["steps"][1]["args"].append("--user=0" if target == "root" else "--network=host")
    elif target == "step_status":
        build["steps"][2]["status"] = "FAILURE"
    elif target == "digest":
        build["results"]["images"][0]["digest"] = "sha256:" + "0" * 64
    else:
        build["options"]["env"] = ["UNREVIEWED=1"]
    with pytest.raises(rollout.Rejected):
        rollout.verify_build(build, config)
