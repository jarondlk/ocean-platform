"""Explicit synthetic C20 service harness shared by SQLite/HTTP/PG checks."""
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import uuid

from sqlalchemy import select

from db.app_models import ResearchRunOutbox
from orchestration.research_controller import ResearchController
from orchestration.research_dispatch import FakeResearchQueue
from orchestration.research_runs import ResearchRunService
from tests.investigation_support import make_investigation_fixture


class RunClock:
    def __init__(self):
        self.value = datetime(2026, 10, 19, tzinfo=timezone.utc)

    def __call__(self):
        return self.value

    def advance(self, seconds):
        self.value += timedelta(seconds=seconds)


@dataclass
class RunFixture:
    retained: object
    service: ResearchRunService
    queue: FakeResearchQueue
    clock: RunClock
    state: dict

    @property
    def user(self):
        return self.retained.user

    def request(self, question="Count all datasets"):
        service = self.retained.service
        created = service.invoke("create", {"name": "C20 synthetic research",
            "snapshot_id": self.retained.snapshots[0], "scope": self.retained.scope,
            "idempotency_key": str(uuid.uuid4())}, self.user)
        conversation = service.invoke("conversations/create", {
            "investigation_id": created["investigation"]["id"], "name": "C20 private conversation",
            "idempotency_key": str(uuid.uuid4())}, self.user)["conversation"]
        return {"investigation_id": created["investigation"]["id"], "conversation_id": conversation["id"],
                "revision_id": created["context"]["id"], "expected_snapshot_id": created["context"]["snapshot_id"],
                "expected_payload_sha256": created["context"]["payload_sha256"],
                "question": question, "idempotency_key": str(uuid.uuid4())}

    def submit(self, question="Count all datasets"):
        return self.service.invoke("submit", self.request(question), self.user)["run"]

    @staticmethod
    def address(run):
        return {"run_id": run["id"], "investigation_id": run["context"]["binding"]["investigation_id"],
                "conversation_id": run["context"]["binding"]["conversation_id"]}

    def delivery(self, run):
        with self.retained.factory() as session:
            row = session.scalar(select(ResearchRunOutbox).where(ResearchRunOutbox.run_id == uuid.UUID(run["id"])).order_by(ResearchRunOutbox.input_version.desc()))
            return {"run_id": run["id"], "delivery_id": str(row.delivery_id)}


def make_run_fixture(engine, directory, *, lease_seconds=5):
    retained = make_investigation_fixture(engine, directory)
    clock, queue, state = RunClock(), FakeResearchQueue(), {"runtime": None, "factory_calls": 0}

    def controller_factory(identity_provider):
        state["factory_calls"] += 1
        return ResearchController(investigations=retained.service, catalogue=retained.service.catalogue,
            identity_provider=identity_provider, runtime=state["runtime"],
            model="c20-fake" if state["runtime"] is not None else None,
            runtime_identity={"fixture": "C20-local-only"})

    service = ResearchRunService(session_factory=retained.factory, site_id=retained.service.site_id,
        investigations=retained.service, controller_factory=controller_factory, queue=queue,
        enabled=lambda: True, dispatch_enabled=lambda: True, db_clock=clock, lease_seconds=lease_seconds)
    return RunFixture(retained, service, queue, clock, state)
