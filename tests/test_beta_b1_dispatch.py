"""Canonical task refusal tests use synthetic UUIDs without credentials/network."""
from copy import deepcopy

import pytest

from orchestration.cloud_research_dispatch import CloudResearchQueue
from scripts import beta_b1_dispatch as delivery
from tests.test_beta_b1_rollout import completed, make_material

IDENTITY = "11111111-1111-4111-8111-111111111111"
DELIVERY = "22222222-2222-4222-8222-222222222222"


def task(kind="run"):
    return CloudResearchQueue(settings=delivery.SETTINGS, kind=kind).task(
        delivery_id=DELIVERY, **{"run_id" if kind == "run" else "job_id": IDENTITY})


@pytest.mark.parametrize("kind", ["run", "answer"])
def test_exact_task_is_accepted_without_claiming_an_answer(kind):
    intent = delivery.validate_task(task(kind), kind, IDENTITY)
    assert intent["canonical_target_identity_and_body_verified"]
    assert not intent["automatic_retry_permitted"] and not intent["successful_answer_claimed"]


@pytest.mark.parametrize("field", ["name", "origin", "audience", "invoker", "method", "deadline", "body", "header", "dispatched", "responses", "kind", "identity"])
def test_altered_or_previously_dispatched_task_is_rejected(field):
    value = deepcopy(task())
    kind, identity = "run", IDENTITY
    request = value["httpRequest"]
    if field == "name":
        value["name"] += "-replacement"
    elif field == "origin":
        request["url"] = "https://another-project.run.app/internal/research/run"
    elif field == "audience":
        request["oidcToken"]["audience"] = "https://another-project.run.app"
    elif field == "invoker":
        request["oidcToken"]["serviceAccountEmail"] = "other@example.com"
    elif field == "method":
        request["httpMethod"] = "GET"
    elif field == "deadline":
        value["dispatchDeadline"] = "3600s"
    elif field == "body":
        request["body"] = "not-base64"
    elif field == "header":
        request["headers"]["Authorization"] = "unexpected"
    elif field == "dispatched":
        value["dispatchCount"] = 1
    elif field == "responses":
        value["responseCount"] = 1
    elif field == "kind":
        kind = "answer"
    else:
        identity = DELIVERY
    with pytest.raises((delivery.guard.Rejected, ValueError)):
        delivery.validate_task(value, kind, identity)


def test_uncertain_dispatch_retains_intent_and_cannot_be_repeated(monkeypatch, tmp_path):
    import json
    serving, controller, contract = make_material()
    controller = completed(controller, delivery.rollout.plan_transition(controller, "controller", contract))
    for phase in ["stage", "promote", "admit-stage", "admit-promote"]:
        serving = completed(serving, delivery.rollout.plan_transition(serving, phase, contract))
    path = tmp_path / "contract.json"
    path.write_text(json.dumps(contract))
    monkeypatch.setattr(delivery.rollout, "CONTRACT_PATH", path)
    class Cloud:
        writes = 0
        def request(self, url, **kwargs):
            if kwargs.get("method") == "POST":
                self.writes += 1
                raise OSError("Synthetic lost acknowledgement")
            if url.endswith(":getIamPolicy"):
                return {"bindings": [{"role": "roles/run.invoker", "members": [
                    "serviceAccount:" + delivery.SETTINGS.task_invoker_email]}]}
            if "/tasks?" in url:
                return {"tasks": [task()]}
            if url.endswith("/queues/ocean-v1-beta-research"):
                return {"state": "PAUSED"}
            return controller if url.endswith("-controller") else serving
    cloud = Cloud()
    with pytest.raises(OSError):
        delivery.execute(cloud, tmp_path, "run", IDENTITY)
    assert (tmp_path / ("manual-run-" + IDENTITY) / "intent.json").is_file()
    with pytest.raises(delivery.guard.Rejected):
        delivery.execute(cloud, tmp_path, "run", IDENTITY)
    assert cloud.writes == 1
