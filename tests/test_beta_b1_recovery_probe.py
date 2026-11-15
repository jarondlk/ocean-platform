"""Actual retained services with synthetic transport; live GCP acceptance is separate."""
import base64
import copy
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient
import pytest

from tests import test_beta_question_services as journey
from tests.test_beta_question_services import questions as questions
from tests.test_beta_research_host import context as context
from tests.test_beta_snapshot_catalogue import sealed as sealed
from tests.test_v1_host import independent as independent

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("b1_recovery_probe", ROOT / "deploy/gcp/beta/b1/recovery_probe.py")
PROBE = importlib.util.module_from_spec(spec)
spec.loader.exec_module(PROBE)


class MemoryTasks:
    def __init__(self):
        self.tasks = {}
        self.creates = 0

    def post(self, url, **kwargs):
        task = copy.deepcopy(kwargs["json"]["task"])
        if task["name"] in self.tasks:
            return SimpleNamespace(status_code=409, json=lambda: {"error": {"code": 409}})
        self.tasks[task["name"]] = task
        self.creates += 1
        return SimpleNamespace(status_code=200, json=lambda: {"name": task["name"]})

    def get(self, url, **kwargs):
        name = url.split("/v2/", 1)[1]
        return SimpleNamespace(status_code=200, json=lambda: copy.deepcopy(self.tasks[name]))


def exercise(questions):
    services, actor, _, sealed = questions
    transport = MemoryTasks()
    for service in (services.research_run_service, services.research_answer_service):
        service.queue._session = transport
    prepared = PROBE.prepare(services, actor, sealed[2]["index_id"])
    assert prepared["lost_ack_after_provider_create_verified"]
    assert prepared["same_delivery_409_full_readback_recovered"] and transport.creates == 3
    with TestClient(journey.private_app(questions)) as client:
        for task in prepared["tasks"].values():
            response = client.post("/internal/research/run", content=base64.b64decode(task["httpRequest"]["body"]),
                headers={"Authorization": "Bearer synthetic-test", "Content-Type": "application/json"})
            assert response.status_code == 200, response.text
    answer = PROBE.prepare_answer(services, actor)
    assert answer["deterministic_selection_checked_before_answer_admission"] and transport.creates == 4
    with TestClient(journey.private_app(questions)) as client:
        response = client.post("/internal/research/answer", content=base64.b64decode(answer["task"]["httpRequest"]["body"]),
            headers={"Authorization": "Bearer synthetic-test", "Content-Type": "application/json"})
        assert response.status_code == 200, response.text
        before = PROBE.verify(services, actor)
        # Real service duplicate handling, with exactly the retained task body.
        for task in [*prepared["tasks"].values(), answer["task"]]:
            path = "/internal/research/answer" if "job_id" in json.loads(base64.b64decode(task["httpRequest"]["body"])) else "/internal/research/run"
            response = client.post(path, content=base64.b64decode(task["httpRequest"]["body"]),
                headers={"Authorization": "Bearer synthetic-test", "Content-Type": "application/json"})
            assert response.status_code == 200, response.text
        after = PROBE.verify(services, actor)
    assert before == after and before["model_calls"] == 0 and before["wrong_context_denied"]
    return before


def test_recovery_source_exercises_lost_ack_cancel_continue_answer_and_duplicates(questions):
    exercise(questions)


def test_ack_fault_requires_a_successful_real_create_shape():
    delegate = SimpleNamespace(post=lambda *args, **kwargs: SimpleNamespace(status_code=503, json=lambda: {}))
    lost = PROBE.AckLoss(delegate)
    with pytest.raises(ValueError, match="not created"):
        lost.post("https://cloudtasks.googleapis.com/v2/fixed", json={"task": {"name": "fixed"}})
    assert lost.created is None
