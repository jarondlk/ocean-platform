"""Capture actual isolated C20 HTTP envelopes for the TypeScript consumer.

Creates a new immutable fixture file once. Uses sealed synthetic sources, TEST
principals, a private temporary SQLite store and the explicitly fake queue.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import tempfile
from unittest.mock import patch
import uuid

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event

from api import auth
from api.research_run_routes import router
from db.app_models import AppBase
from tests.research_run_support import make_run_fixture

EVIDENCE = Path(__file__).resolve().parent
ROOT = EVIDENCE.parents[4]
SOURCES = (
    "api/research_run_routes.py", "schema/research_runs.py", "db/app_models.py",
    "orchestration/research_runs.py", "orchestration/research_dispatch.py",
    "orchestration/research_controller.py", "orchestration/research_controller_budget.py",
    "orchestration/research_controller_replay.py", "tests/research_run_support.py",
    "tests/investigation_support.py", "docs/plans/ocean-v1/evidence/C20/export_wire.py",
)


def main():
    output = EVIDENCE / "wire-fixtures.json"
    if output.exists():
        raise RuntimeError("Existing wire evidence is immutable")
    before = {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in SOURCES}
    cases = []
    environment = {"DEPLOYMENT_ENV": "test", **{
        "ENABLE_V1_" + flag: "true" for flag in (
            "CATALOGUE", "INVESTIGATIONS", "RESEARCH_CONTROLLER", "RESEARCH_RUNS", "RESEARCH_DISPATCH",
        )
    }}
    with tempfile.TemporaryDirectory(prefix="ocean-c20-wire-") as temporary, patch.dict(os.environ, environment):
        directory = Path(temporary)
        engine = create_engine("sqlite+pysqlite:///" + str(directory / "private-v1.sqlite"))

        @event.listens_for(engine, "connect")
        def foreign_keys(connection, _record):
            connection.execute("PRAGMA foreign_keys=ON")

        try:
            AppBase.metadata.create_all(engine)
            fixture = make_run_fixture(engine, directory)
            app = FastAPI()
            app.middleware("http")(auth.authorization_middleware)
            app.include_router(router)
            app.state.research_run_service = fixture.service
            app.state.investigation_service = fixture.retained.service

            with patch.object(auth, "authenticate_request", lambda request: fixture.user), TestClient(app) as client:
                def post(method, request, client_request=None):
                    response = client.post("/research/runs/" + method, json=request)
                    assert response.status_code == 200, response.text
                    result = response.json()
                    cases.append({"method": method, "request": client_request or request,
                                  "response": result, "status_code": 200})
                    return result

                request = fixture.request()
                frozen = fixture.retained.service.load_for_submission(
                    investigation_id=request["investigation_id"], conversation_id=request["conversation_id"],
                    revision_id=request["revision_id"], user=fixture.user,
                )
                context = {"binding": {name: frozen[name] for name in (
                    "investigation_id", "conversation_id", "revision_id", "snapshot_id", "payload_sha256",
                )}, **{name: frozen["context"][name] for name in ("scope", "attachments", "pins")}}
                accepted = post("submit", request, {"context": context, "question": request["question"],
                                                   "idempotency_key": request["idempotency_key"]})["run"]
                address = fixture.address(accepted)
                post("status", address)
                post("events", {**address, "after_cursor": 0, "limit": 100})
                post("cancel", {**address, "idempotency_key": str(uuid.uuid4())})
                child = post("continue", {**address, "idempotency_key": str(uuid.uuid4())})["run"]
                post("list", {"investigation_id": request["investigation_id"],
                              "conversation_id": request["conversation_id"], "limit": 25, "cursor": None})
                assert fixture.service.execute_delivery(**fixture.delivery(child))["run"]["status"] == "completed"
                post("status", fixture.address(child))
                post("events", {**fixture.address(child), "after_cursor": 0, "limit": 100})

                waiting = fixture.submit("Help me understand this")
                paused = fixture.service.execute_delivery(**fixture.delivery(waiting))["run"]
                assert paused["status"] == "awaiting_clarification"
                post("clarify", {**fixture.address(waiting), "clarification_id": paused["clarification_id"],
                                  "idempotency_key": str(uuid.uuid4()), "answer": "Count all datasets"})
        finally:
            engine.dispose()
    after = {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in SOURCES}
    assert before == after, "Sources changed during wire capture"
    with output.open("x") as stream:
        json.dump({"version": "research-runs-wire-v1", "synthetic_only": True,
                   "source_sha256": before, "cases": cases}, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    print(json.dumps({"cases": len(cases), "methods": sorted({item["method"] for item in cases}),
                      "sha256": hashlib.sha256(output.read_bytes()).hexdigest()}))


if __name__ == "__main__":
    main()
