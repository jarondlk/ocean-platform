import base64
import copy
import json
import uuid
from types import SimpleNamespace

from pydantic import ValidationError
import pytest

from orchestration.cloud_research_dispatch import (
    CloudDispatchError, CloudResearchQueue, CloudResearchSettings, delivery_body,
)


def cloud_settings(**changes):
    return CloudResearchSettings.model_validate({
        "version": "ocean-v1-beta-research-cloud-v1", "project_id": "ocean-v1-beta-20261101",
        "region": "asia-northeast1", "queue_id": "ocean-v1-beta-research",
        "controller_origin": "https://ocean-v1-beta-research-controller-abc-an.a.run.app",
        "task_invoker_email": "ocean-v1-beta-task-invoker@ocean-v1-beta-20261101.iam.gserviceaccount.com",
        "task_invoker_subject": "123456789012345678901", **changes})


def reply(status, data=None):
    return SimpleNamespace(status_code=status, json=lambda: data)


class Transport:
    def __init__(self):
        self.calls, self.post_status, self.get_status, self.mutate = [], 200, 200, lambda x: x

    def post(self, url, **kwargs):
        self.calls.append(("POST", url, kwargs))
        self.task = copy.deepcopy(kwargs["json"]["task"])
        return reply(self.post_status, {"name": self.task["name"]})

    def get(self, url, **kwargs):
        self.calls.append(("GET", url, kwargs))
        return reply(self.get_status, self.mutate(copy.deepcopy(self.task)))


@pytest.mark.parametrize("kind,key", [("run", "run_id"), ("answer", "job_id")])
def test_cloud_task_binds_exact_identity_and_contains_only_durable_ids(kind, key):
    transport = Transport()
    queue = CloudResearchQueue(settings=cloud_settings(), kind=kind, session=transport)
    address = {key: str(uuid.uuid4()), "delivery_id": str(uuid.uuid4())}
    queue.enqueue(**address)
    task = transport.task
    assert json.loads(base64.b64decode(task["httpRequest"]["body"])) == {
        "version": "research-cloud-delivery-v1", **address}
    assert task["httpRequest"]["oidcToken"] == {
        "serviceAccountEmail": queue.settings.task_invoker_email, "audience": queue.settings.controller_origin}
    assert task == queue.task(**address)
    assert queue.task(**{**address, "delivery_id": str(uuid.uuid4())})["name"] != task["name"]
    assert task["dispatchDeadline"] == "240s"
    assert transport.calls[0][2]["timeout"] == 10
    assert transport.calls[0][2]["allow_redirects"] is False


def test_lost_ack_requires_exact_task_readback_not_a_conflict_alone():
    transport = Transport()
    transport.post_status = 409
    queue = CloudResearchQueue(settings=cloud_settings(), kind="run", session=transport)
    address = {"run_id": str(uuid.uuid4()), "delivery_id": str(uuid.uuid4())}
    queue.enqueue(**address)
    assert [c[0] for c in transport.calls] == ["POST", "GET"]
    assert transport.calls[-1][2]["params"] == {"responseView": "FULL"}
    transport.get_status = 404  # A deleted task's name tombstone is not success.
    with pytest.raises(CloudDispatchError):
        queue.enqueue(**address)


@pytest.mark.parametrize("field", ["name", "dispatchDeadline", "url", "body", "httpMethod", "oidcToken", "headers"])
def test_conflicting_task_target_body_or_identity_is_never_accepted(field):
    transport = Transport()
    transport.post_status = 409
    def mutate(task):
        if field in {"name", "dispatchDeadline"}:
            task[field] = "changed"
        else:
            task["httpRequest"][field] = {} if field in {"oidcToken", "headers"} else "changed"
        return task
    transport.mutate = mutate
    queue = CloudResearchQueue(settings=cloud_settings(), kind="run", session=transport)
    with pytest.raises(CloudDispatchError):
        queue.enqueue(run_id=str(uuid.uuid4()), delivery_id=str(uuid.uuid4()))


@pytest.mark.parametrize("status", [301, 400, 401, 403, 429, 500, 503])
def test_remote_failures_are_safe_and_not_automatically_retried(status):
    transport = Transport()
    transport.post_status = status
    queue = CloudResearchQueue(settings=cloud_settings(), kind="run", session=transport)
    with pytest.raises(CloudDispatchError) as error:
        queue.enqueue(run_id=str(uuid.uuid4()), delivery_id=str(uuid.uuid4()))
    assert len(transport.calls) == 1
    assert str(error.value) == "Beta research task delivery is unavailable"


@pytest.mark.parametrize("origin", ["http://ocean-v1-beta-research-x.a.run.app", "https://legacy.run.app",
    "https://ocean-v1-beta-research-x.a.run.app/", "https://ocean-v1-beta-research-x.a.run.app?x=1",
    "https://user:password@ocean-v1-beta-research-x.a.run.app", "https://ocean-v1-beta-research-x.a.run.app.evil.invalid"])
def test_legacy_external_and_ambiguous_controller_targets_rejected(origin):
    with pytest.raises(ValidationError):
        cloud_settings(controller_origin=origin)


@pytest.mark.parametrize("identity", [None, "not-a-uuid", uuid.uuid4(), uuid.uuid4().hex])
def test_only_canonical_uuid_addresses_reach_transport(identity):
    with pytest.raises((ValueError, TypeError)):
        delivery_body("run", identity, str(uuid.uuid4()))
