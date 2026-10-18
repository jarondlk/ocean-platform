"""Capture real C17 HTTP envelopes for the independent TypeScript transport tests.

Sealed synthetic C09/C10-C13 fixtures, separate disposable SQLite AppBase and
explicit TEST identity only. No listening sockets, providers, OIDC or legacy data.
The recorded responses are test inputs, never a production transport fallback.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import uuid

ROOT = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(ROOT))
for key, value in {
    "DEPLOYMENT_ENV": "test", "AUTH_MODE": "disabled", "ENABLE_MOCK_LOGIN": "false",
    "PERSIST_LOCAL_CHAT": "false", "ENABLE_V1_INVESTIGATIONS": "true", "ENABLE_V1_CATALOGUE": "true",
    "DATABASE_URL": "postgresql://unused:unused@127.0.0.1:1/c18_client_unused",
    "MODEL_PROVIDER": "ollama", "OLLAMA_BASE_URL": "http://127.0.0.1:1",
}.items():
    os.environ[key] = value

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine, event  # noqa: E402

from api import auth  # noqa: E402
from api.investigation_routes import router  # noqa: E402
from db.app_models import AppBase  # noqa: E402
from tests.investigation_support import make_investigation_fixture  # noqa: E402


def digest(path):
    return hashlib.sha256((ROOT / path).read_bytes()).hexdigest()


def main():
    output = Path(__file__).parent / "client-wire.json"
    if output.exists():
        raise SystemExit("Refusing to overwrite the original HTTP wire capture")
    paths = ["api/investigation_routes.py", "orchestration/investigations.py", "schema/investigations.py", "tests/investigation_support.py", "db/app_models.py"]
    before = {path: digest(path) for path in paths}
    cases = []
    with tempfile.TemporaryDirectory(prefix="ocean-c18-client-") as directory:
        root = Path(directory)
        engine = create_engine("sqlite+pysqlite:///" + str(root / "separate-v1.sqlite"))

        @event.listens_for(engine, "connect")
        def foreign_keys(connection, _record):
            connection.execute("PRAGMA foreign_keys=ON")

        AppBase.metadata.create_all(engine)
        fixture = make_investigation_fixture(engine, root)
        state = {"principal": fixture.user}
        original_authenticate = auth.authenticate_request

        def authenticate(_request):
            if state["principal"] is None:
                raise auth.AuthenticationFailure(401, "Authentication is required")
            return state["principal"]

        auth.authenticate_request = authenticate
        app = FastAPI()
        app.middleware("http")(auth.authorization_middleware)
        app.include_router(router)
        app.state.investigation_service = fixture.service
        try:
            with TestClient(app) as client:
                def post(method, endpoint, payload, expected_status=200):
                    response = client.post("/research/investigations/" + endpoint, json=payload)
                    assert response.status_code == expected_status, response.text
                    assert response.headers["cache-control"] == "no-store"
                    result = response.json()
                    cases.append({"method": method, "path": "/research/investigations/" + endpoint, "payload": payload, "status": response.status_code, "expected": result})
                    return result

                def key():
                    return str(uuid.uuid4())

                post("list", "list", {})
                created_request = {"name": "Synthetic private investigation 調査", "snapshot_id": fixture.snapshots[0], "scope": fixture.scope, "idempotency_key": key()}
                created = post("create", "create", created_request)
                post("create", "create", created_request)
                inv = {"investigation_id": created["investigation"]["id"]}
                post("list", "list", {"limit": 1})
                post("get", "get", inv)
                renamed = post("rename", "rename", {**inv, "name": "Renamed 調査", "expected_version": created["investigation"]["metadata_version"], "idempotency_key": key()})
                archived = post("archive", "archive", {**inv, "expected_version": renamed["investigation"]["metadata_version"], "idempotency_key": key()})
                post("archive", "archive", {**inv, "archived": False, "expected_version": archived["investigation"]["metadata_version"], "idempotency_key": key()})
                first = post("createConversation", "conversations/create", {**inv, "name": "First synthetic chat", "idempotency_key": key()})
                post("createConversation", "conversations/create", {**inv, "name": "Separate synthetic chat", "idempotency_key": key()})
                page = post("listConversations", "conversations/list", {**inv, "limit": 1})
                post("listConversations", "conversations/list", {**inv, "limit": 1, "after_id": page["next_after_id"]})
                conv = {**inv, "conversation_id": first["conversation"]["id"]}
                post("getConversation", "conversations/get", conv)
                post("renameConversation", "conversations/rename", {**conv, "name": "Renamed synthetic chat", "expected_version": first["conversation"]["metadata_version"], "idempotency_key": key()})
                post("getContext", "context/get", inv)
                reference = {"kind": "catalogue", "id": fixture.dataset_ids["ctd"], "snapshot_id": fixture.snapshots[0]}
                def change(previous, delta):
                    return post("changeContext", "context/change", {**inv, "expected_revision_id": previous["context"]["id"], "change": delta, "idempotency_key": key()})
                attached = change(created, {"op": "attach", "reference": reference})
                pinned = change(attached, {"op": "pin", "reference": reference})
                post("getContext", "context/get", {**inv, "revision_id": created["context"]["id"]})
                post("getOperation", "operations/get", {"operation_id": attached["operation"]["id"]})
                post("retryOperation", "operations/retry", {"operation_id": attached["operation"]["id"]})
                post("retryOperation", "operations/retry", {"operation_id": renamed["operation"]["id"]})
                fixture.policy[fixture.snapshots[1]].add(fixture.source_dataset_ids["ctd"])
                post("refresh", "refresh", {**inv, "expected_revision_id": pinned["context"]["id"], "target_snapshot_id": fixture.snapshots[1], "name": "Explicit refresh branch", "idempotency_key": key()})
                scoped = change(pinned, {"op": "scope", "scope": fixture.scope})
                unpinned = change(scoped, {"op": "unpin", "reference": reference})
                change(unpinned, {"op": "detach", "reference": reference})
                post("changeContext", "context/change", {**inv, "expected_revision_id": created["context"]["id"], "change": {"op": "pin", "reference": reference}, "idempotency_key": key()}, 409)
                state["principal"] = fixture.other
                post("get", "get", inv, 404)
                state["principal"] = None
                post("list", "list", {}, 401)
        finally:
            auth.authenticate_request = original_authenticate
            engine.dispose()
    after = {path: digest(path) for path in paths}
    assert before == after
    methods = sorted({case["method"] for case in cases})
    assert len(methods) == 14
    result = {"boundary": "Actual C17 ASGI HTTP + TEST identity + synthetic frozen sources + separate SQLite; no socket/browser/OIDC/production claim", "source_before_sha256": before, "source_after_sha256": after, "method_count": len(methods), "methods": methods, "request_count": len(cases), "cases": cases}
    with output.open("x") as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    print(json.dumps({"request_count": len(cases), "method_count": len(methods), "output_sha256": digest(str(output.relative_to(ROOT)))}, sort_keys=True))


if __name__ == "__main__":
    main()
