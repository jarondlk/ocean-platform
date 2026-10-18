"""Owned loopback C18 actual-service harness; explicit synthetic TEST identities.

The separately launched development frontend may proxy this API. This process
never loads an environment file, production database, legacy store or provider.
"""
from __future__ import annotations

import argparse
from dataclasses import replace
import json
import os
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import uuid

if os.environ.get("DEPLOYMENT_ENV") != "test" or os.environ.get("AUTH_MODE") != "disabled":
    raise RuntimeError("Explicit isolated test settings required")
ROOT = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(ROOT))
# ruff: noqa: E402
from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from sqlalchemy import create_engine, event, select
import uvicorn
from api import auth
from api.catalogue_routes import router as catalogue_router
from api.catalogue_browser_routes import router as browser_router
from api.investigation_routes import router as investigation_router
from api.v1_runtime_routes import V1RuntimeConfiguration, router as runtime_router
from db.app_models import AppBase, AppUser
from orchestration.catalogue_browser import CatalogueBrowser
from tests.investigation_support import make_investigation_fixture


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, choices=[3101], default=3101)
    parser.add_argument("--state-file", type=Path, required=True)
    parser.add_argument("--observations", type=Path, required=True)
    args = parser.parse_args()
    state_path, observations = args.state_file.resolve(), args.observations.resolve()
    for path in (state_path, observations):
        if not path.is_relative_to(Path("/private/tmp")):
            parser.error("QA controls/observations must be explicit private/tmp files")
    if not state_path.is_file() or observations.exists():
        parser.error("Create the test control file and choose a new observations path")

    def state():
        value = json.loads(state_path.read_text())
        if type(value) is not dict or value.get("actor") not in {"owner", "other", "admin"} or not isinstance(value.get("revision"), str):
            raise ValueError("Explicit TEST actor and revision required")
        return value

    with TemporaryDirectory(prefix="ocean-c18-research-") as directory:
        local = Path(directory)
        engine = create_engine("sqlite+pysqlite:///" + str(local / "owned-app.sqlite"))

        @event.listens_for(engine, "connect")
        def foreign_keys(connection, _):
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute("PRAGMA busy_timeout=10000")

        AppBase.metadata.create_all(engine)
        fixture = make_investigation_fixture(engine, local)
        browser = CatalogueBrowser(
            service=fixture.service.catalogue,
            snapshots=[{"snapshot_id": sid, "label": {"en": f"Synthetic snapshot {index + 1}", "ja": f"合成スナップショット {index + 1}"}} for index, sid in enumerate(reversed(fixture.snapshots))],
            permitted=lambda actor, descriptor: descriptor.snapshot_id in fixture.snapshots,
            revision=lambda actor: state()["revision"], cursor_key=b"c18-explicit-synthetic-key-0000000000",
        )
        app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
        app.state.catalogue_service = fixture.service.catalogue
        app.state.catalogue_browser = browser
        app.state.investigation_service = fixture.service

        def configuration(actor):
            initial = V1RuntimeConfiguration(site_id=fixture.service.site_id, revision=state()["revision"])
            capabilities = dict(initial.capabilities)
            capabilities.update(research="ready", catalogue="ready")
            return V1RuntimeConfiguration(site_id=fixture.service.site_id, revision=state()["revision"], capabilities=capabilities)

        app.state.v1_runtime_configuration = configuration
        actors = {"owner": fixture.user, "other": fixture.other, "admin": fixture.admin}

        def authenticate(request):
            current = state()
            if current.get("unauthorized") is True:
                raise auth.AuthenticationFailure(401, "Authentication is required")
            for sid in fixture.snapshots:
                fixture.policy[sid] = set(current.get("blocked_by_snapshot", {}).get(sid, []))
            actor = actors[current["actor"]]
            role = current.get("role", actor.role)
            if role not in {"viewer", "researcher", "admin"}:
                raise ValueError("Explicit known test role required")
            with fixture.factory.begin() as session:
                row = session.scalar(select(AppUser).where(AppUser.id == actor.id))
                if row.role != role:
                    row.role = role
            return replace(actor, role=role, permissions=auth.permissions_for_role(role))

        auth.authenticate_request = authenticate
        ledger, faults = [], set()

        @app.middleware("http")
        async def boundary(request, call_next):
            if request.headers.get("host") not in {"127.0.0.1:3101", "localhost:3101"}:
                return JSONResponse(status_code=403, content={"error": "Loopback test host required"})
            path = request.url.path
            if path.startswith(("/v1/", "/catalogue/", "/research/")):
                response = await auth.authorization_middleware(request, call_next)
                current = state()
                fault = current.get("lose_write_ack")
                if fault and fault not in faults and request.method == "POST" and path.endswith("/context/change") and response.status_code == 200:
                    faults.add(fault)
                    response = JSONResponse(status_code=503, content={"error": {"code": "synthetic_ack_lost", "message": "Synthetic response acknowledgement lost"}}, headers={"Cache-Control": "no-store"})
                ledger.append({"path": path, "method": request.method, "status": response.status_code, "actor": current["actor"]})
                return response
            return await call_next(request)

        app.include_router(runtime_router)
        app.include_router(catalogue_router)
        app.include_router(browser_router)
        app.include_router(investigation_router)

        @app.get("/_ocean/runtime-mode")
        async def mode():
            return JSONResponse(content={"version": "ocean-v1-mode-v1", "mode": "service"})

        output = ROOT / "frontend-v1/out"

        @app.get("/{path:path}")
        async def static(path: str):
            target = (output / (path or "index.html")).resolve()
            if output.resolve() not in target.parents:
                return JSONResponse(status_code=403, content={"error": "Forbidden"})
            if not target.is_file() and not target.suffix:
                target = target.with_suffix(".html")
            if not target.is_file():
                return JSONResponse(status_code=404, content={"error": "Not found"})
            return FileResponse(target, headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"})

        initial = fixture.service.invoke("create", {"name": "C18 synthetic coastal investigation", "snapshot_id": fixture.snapshots[0], "scope": fixture.scope, "idempotency_key": str(uuid.uuid4())}, fixture.user)
        chats = [fixture.service.invoke("conversations/create", {"investigation_id": initial["investigation"]["id"], "name": name, "idempotency_key": str(uuid.uuid4())}, fixture.user)["conversation"] for name in ("Temperature question", "Independent conversation")]
        metadata = {"fixture": "sealed synthetic data and TEST identities only", "directory": directory, "site_id": fixture.service.site_id, "investigation": initial["investigation"], "context": initial["context"], "conversations": chats, "snapshots": fixture.snapshots, "dataset_ids": fixture.dataset_ids, "source_dataset_ids": fixture.source_dataset_ids}
        print(json.dumps(metadata), flush=True)
        try:
            uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="warning")
        finally:
            engine.dispose()
            with observations.open("x") as stream:
                stream.write(json.dumps({"metadata": metadata, "actual_requests": ledger, "faults_consumed": sorted(faults), "server_stopped": True}, indent=2) + "\n")


if __name__ == "__main__":
    main()
