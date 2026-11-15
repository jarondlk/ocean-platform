"""Fixed-image admission transitions preserve the complete deployed boundary."""
from copy import deepcopy

import pytest

from scripts import beta_b1_rollout as original
from scripts import beta_b1_shared_owner as shared
from scripts.beta_b0_preflight import Rejected
from tests.test_beta_b1_rollout import completed, make_material


@pytest.fixture
def live():
    service, _, contract = make_material()
    contract.update(version=shared.repair.READY_VERSION, image=shared.IMAGE)
    original.main_container(service, "serving")["image"] = shared.IMAGE
    for e in original.main_container(service, "serving")["env"]:
        if e["name"] in original.FLAGS:
            e["value"] = "true"
    service["latestReadyRevision"] = service["latestCreatedRevision"] = service["name"] + "/revisions/" + shared.INITIAL
    service["traffic"] = original.fixed_traffic(shared.INITIAL)
    return service, contract


def test_drain_restore_preserves_exact_images_and_other_settings(live):
    service, contract = live
    for phase in shared.PHASES:
        proposal = shared.plan(service, phase, contract)
        after = completed(service, proposal)
        assert shared.readback(service, after, proposal, contract)["all_other_configuration_preserved"]
        assert [c["image"] for c in after["template"]["containers"]] == [c["image"] for c in service["template"]["containers"]]
        if phase == "restore-promote":
            assert proposal["update_mask"] == "traffic" and "template" not in proposal["body"]
        service = after
    assert original.flag_state(service) and service["traffic"] == original.fixed_traffic(shared.LIVE)


@pytest.mark.parametrize("change", ["image", "identity", "proxy", "secret", "network", "timeout", "ingress", "scaling", "uid", "traffic", "predecessor", "flags", "etag", "not_ready"])
def test_drift_cannot_enter_drain(live, change):
    service, contract = live
    main = original.main_container(service, "serving")
    if change == "image":
        main["image"] = original.NEW
    elif change == "identity":
        service["template"]["serviceAccount"] = "other@example.invalid"
    elif change == "proxy":
        service["template"]["containers"][-1]["image"] = "mutable:latest"
    elif change == "secret":
        main["env"][-1]["valueSource"]["secretKeyRef"]["version"] = "latest"
    elif change == "network":
        service["template"]["vpcAccess"]["egress"] = "ALL_TRAFFIC"
    elif change == "timeout":
        service["template"]["timeout"] = "120s"
    elif change == "ingress":
        service["ingress"] = "INGRESS_TRAFFIC_ALL"
    elif change == "scaling":
        service["template"]["scaling"]["maxInstanceCount"] = 20
    elif change == "uid":
        service["uid"] = "different"
    elif change == "traffic":
        service["traffic"] = []
    elif change == "predecessor":
        service["latestReadyRevision"] += "-stale"
    elif change == "flags":
        main["env"][0]["value"] = "false"
    elif change == "etag":
        service["etag"] = ""
    else:
        service["observedGeneration"] = "0"
    with pytest.raises(Rejected):
        shared.plan(service, "drain", contract)


@pytest.mark.parametrize("phase", ["restore-stage", "restore-promote"])
def test_restore_cannot_skip_drain(live, phase):
    with pytest.raises(Rejected):
        shared.plan(live[0], phase, live[1])


def test_idle_restore_requires_exact_immutable_revision(live):
    service, contract = live
    service = completed(service, shared.plan(service, "drain", contract))
    proposal = shared.plan(service, "restore-stage", contract)
    after = completed(service, proposal)
    after["latestReadyRevision"] = service["latestReadyRevision"]
    revision = {**deepcopy(after["template"]), "name": after["latestCreatedRevision"],
        "service": after["name"].split("/")[-1], "uid": "fixed-revision", "generation": "1", "observedGeneration": "1",
        "conditions": [{"type": "Ready", "state": "CONDITION_SUCCEEDED", "revisionReason": "RETIRED"},
            {"type": "ContainerReady", "state": "CONDITION_SUCCEEDED"}]}
    with pytest.raises(Rejected):
        shared.readback(service, after, proposal, contract)
    assert shared.readback(service, after, proposal, contract, revision)["runtime_startup_verified"] is False
    revision["serviceAccount"] = "foreign@example.invalid"
    with pytest.raises(Rejected):
        shared.readback(service, after, proposal, contract, revision)
