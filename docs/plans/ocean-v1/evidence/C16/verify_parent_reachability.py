"""Verify every sealed-fixture node through its canonical parent over real routes."""
from __future__ import annotations

import json
import os
from pathlib import Path
import sys
from tempfile import TemporaryDirectory

if os.environ.get("DEPLOYMENT_ENV") != "test" or os.environ.get("AUTH_MODE") != "disabled":
    raise RuntimeError("Explicit isolated test environment required")
root = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(root))
# ruff: noqa: E402
from fastapi import FastAPI
from fastapi.testclient import TestClient
from api import auth
from api.catalogue_routes import router
from fixture_support import build_fixture
from orchestration.catalogue_tools import invoke_catalogue


def main():
    output = Path(__file__).resolve().parent
    original_wire = json.loads((output / "actual-wire.json").read_text())
    baseline = next(case["expected"]["items"] for case in original_wire["cases"]
                    if case["name"] == "catalogue.list" and "filters" not in case["payload"])
    nodes = {node["id"]: node for node in baseline}
    with TemporaryDirectory(prefix="ocean-c16-parents-") as directory:
        fixture = build_fixture(Path(directory), state=lambda: {"revision": "synthetic-c16-wire-1"})
        common = {"snapshot_id": fixture.snapshots[0], "scope": fixture.scope.model_dump(mode="json")}
        app = FastAPI()
        app.state.catalogue_service = fixture.service
        authenticate = auth.authenticate_request
        auth.authenticate_request = lambda request: fixture.user

        @app.middleware("http")
        async def boundary(request, call_next):
            return await auth.authorization_middleware(request, call_next)

        app.include_router(router)
        seen = set()
        pages = 0
        try:
            with TestClient(app) as client:
                overview = client.post("/catalogue/overview", json=common)
                assert overview.status_code == 200
                roots = overview.json()["items"]
                seen.update(node["id"] for node in roots)
                assert all(nodes[node["id"]]["parent_id"] is None for node in roots)
                parents = sorted({node["parent_id"] for node in nodes.values() if node["parent_id"]})
                for parent_id in parents:
                    cursor = None
                    expected_ids = {key for key, node in nodes.items() if node["parent_id"] == parent_id}
                    found = set()
                    cursors = set()
                    while True:
                        payload = {**common, "parent_id": parent_id, "limit": 2}
                        if cursor is not None:
                            payload["cursor"] = cursor
                        response = client.post("/catalogue/list", json=payload)
                        assert response.status_code == 200
                        page = response.json()
                        status, tool = invoke_catalogue(fixture.service, "catalogue.list", payload, lambda: fixture.user)
                        assert status == 200 and tool == page
                        assert page["total"]["value"] == len(expected_ids)
                        pages += 1
                        for node in page["items"]:
                            assert node["parent_id"] == parent_id and node == nodes[node["id"]]
                            assert node["id"] not in found
                            found.add(node["id"])
                        cursor = page["next_cursor"]
                        if cursor is None:
                            break
                        assert cursor not in cursors
                        cursors.add(cursor)
                    assert found == expected_ids
                    seen.update(found)
                assert seen == set(nodes)
        finally:
            auth.authenticate_request = authenticate
    result = {"state": "pass", "canonical_objects": len(nodes), "root_objects": len(roots),
              "parents": len(parents), "parent_pages": pages, "every_object_reachable": True,
              "all_parent_pages_match_shared_tools": True,
              "qualification": "Actual sealed synthetic C09/C10-C13 fixtures and real authenticated C14 routes; no real data or scientific approval"}
    (output / "parent-reachability.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result))


if __name__ == "__main__":
    main()
