"""Capture actual C14/C16 HTTP/tool wire parity over sealed synthetic sources."""
from __future__ import annotations

import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory

root = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(root))
# ruff: noqa: E402
from fastapi import FastAPI
from fastapi.testclient import TestClient
from api import auth
from api.catalogue_routes import router as catalogue_router
from api.catalogue_browser_routes import router as browser_router
from fixture_support import build_fixture
from orchestration.catalogue_tools import invoke_catalogue


def main():
    out = Path(__file__).resolve().parent
    state = {"revision": "synthetic-c16-wire-1"}
    with TemporaryDirectory(prefix="ocean-c16-wire-") as directory:
        fixture = build_fixture(Path(directory), state=lambda: state)
        app = FastAPI()
        app.state.catalogue_service = fixture.service
        app.state.catalogue_browser = fixture.browser
        original = auth.authenticate_request
        auth.authenticate_request = lambda request: fixture.user

        @app.middleware("http")
        async def security(request, call_next):
            return await auth.authorization_middleware(request, call_next)

        app.include_router(catalogue_router)
        app.include_router(browser_router)
        cases = []
        try:
            with TestClient(app) as client:
                def capture(name, path, payload):
                    response = client.post(path, json=payload)
                    assert response.status_code == 200, (name, response.status_code, response.json())
                    actual = response.json()
                    if name.startswith("snapshots"):
                        expected = fixture.browser.discover(payload, fixture.user)
                    else:
                        status, expected = invoke_catalogue(
                            fixture.service, name, payload, lambda: fixture.user
                        )
                        assert status == 200, (name, expected)
                    assert actual == expected, name
                    cases.append({"name": name, "path": path, "payload": payload,
                                  "expected": actual, "http_tool_parity": True})
                    return actual

                selected_scope = fixture.scope.model_dump(mode="json")
                first = capture("snapshots", "/catalogue/snapshots", {"scope": selected_scope, "limit": 1})
                capture("snapshots-page-2", "/catalogue/snapshots", {
                    "scope": selected_scope, "limit": 1, "cursor": first["next_cursor"],
                })
                common = {"snapshot_id": fixture.snapshots[0], "scope": selected_scope}
                capture("catalogue.overview", "/catalogue/overview", common)
                listed = capture("catalogue.list", "/catalogue/list", {**common, "limit": 500})
                first_datasets = capture("catalogue.list", "/catalogue/list", {
                    **common, "filters": {"kinds": ["dataset"]}, "limit": 2,
                })
                capture("catalogue.list", "/catalogue/list", {
                    **common, "filters": {"kinds": ["dataset"]}, "limit": 2,
                    "cursor": first_datasets["next_cursor"],
                })
                for node in listed["items"]:
                    capture("catalogue.open", "/catalogue/open", {**common, "object_id": node["id"]})
                    capture("catalogue.open", "/catalogue/open", {
                        **common, "object_id": node["id"], "include_details": True,
                    })
                for identity in fixture.dataset_ids:
                    capture("catalogue.coverage", "/catalogue/coverage", {
                        **common, "object_id": identity, "limit": 2,
                    })
                    detail = next(item["expected"] for item in cases
                                  if item["name"] == "catalogue.open"
                                  and item["payload"].get("include_details")
                                  and item["payload"]["object_id"] == identity)
                    metadata = detail["details"]
                    native = next(item for item in metadata["source_operations"]
                                  if item["id"].endswith(".table"))
                    for table in metadata["tables"]:
                        parameters = {} if native["id"] == "c11.table" else {"table": table["name"]}
                        if native["id"] == "c12.table":
                            parameters["population"] = "raw"
                        capture("catalogue.query", "/catalogue/query", {
                            **common, "operation_id": "c13.operation", "operation_version": "c13-v1",
                            "input_ids": [identity], "parameters": {
                                "operation_id": native["id"], "operation_version": native["version"],
                                "parameters": parameters, "limit": 2,
                            },
                        })
                    if native["id"] == "c12.table":
                        capture("catalogue.query", "/catalogue/query", {
                            **common, "operation_id": "c13.operation", "operation_version": "c13-v1",
                            "input_ids": [identity], "parameters": {
                                "operation_id": "c12.summary", "operation_version": "c12-v1",
                                "parameters": {"population": "raw"}, "limit": 1,
                            },
                        })
                        capture("catalogue.coverage", "/catalogue/coverage", {
                            **common, "object_id": identity, "parameters": {"population": "raw"}, "limit": 2,
                        })
                for node in listed["items"]:
                    if node["kind"] == "statistic":
                        capture("catalogue.coverage", "/catalogue/coverage", {
                            **common, "object_id": node["id"], "limit": 2,
                        })
                capture("catalogue.coverage", "/catalogue/coverage", {
                    **common, "object_id": "root:metadata", "limit": 2,
                })
                capture("catalogue.query", "/catalogue/query", {
                    **common, "operation_id": "c13.inventory", "operation_version": "c13-v1",
                    "input_ids": ["root:data"], "parameters": {"limit": 2},
                })
                capture("catalogue.relationships", "/catalogue/relationships", {**common, "limit": 2})
                analysis = next(node["id"] for node in listed["items"] if node["kind"] == "analysis")
                capture("analysis.get_published", "/catalogue/analysis/get-published", {
                    **common, "analysis_id": analysis, "limit": 2,
                })
        finally:
            auth.authenticate_request = original
        result = {"qualification": "Actual sealed synthetic C09/C10-C13 inputs; no real scientific approval or live services",
                  "scope": selected_scope, "snapshots": fixture.snapshots, "cases": cases}
        (out / "actual-wire.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
        (out / "wire-python-result.json").write_text(json.dumps({
            "cases": len(cases), "all_http_tool_parity": True,
            "canonical_objects": len(listed["items"]), "datasets": len(fixture.dataset_ids),
            "snapshot_pages": 2, "methods": sorted({item["name"] for item in cases}),
        }, indent=2) + "\n")
        print(json.dumps({"cases": len(cases), "canonical_objects": len(listed["items"]),
                          "datasets": len(fixture.dataset_ids), "all_http_tool_parity": True}))


if __name__ == "__main__":
    main()
