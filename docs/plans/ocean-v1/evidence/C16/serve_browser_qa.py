"""Disposable loopback-only C16 integration harness with explicit TEST identity."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
from tempfile import TemporaryDirectory

if os.environ.get("DEPLOYMENT_ENV") != "test" or os.environ.get("AUTH_MODE") != "disabled":
    raise RuntimeError("Explicit isolated test settings are required")
root = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(root))
# ruff: noqa: E402
from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
import uvicorn
from api import auth
from api.catalogue_routes import router as catalogue_router
from api.catalogue_browser_routes import router as browser_router
from api.v1_runtime_routes import V1RuntimeConfiguration, router as runtime_router
from fixture_support import build_fixture


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--count", type=int)
    parser.add_argument("--port", type=int, choices=[3100, 3101], default=3100)
    parser.add_argument("--state-file", type=Path, required=True)
    args = parser.parse_args()
    if args.count is not None and not 0 <= args.count <= 100_000:
        parser.error("Explicit synthetic count must be between zero and100000")
    state_path = args.state_file.resolve()
    if not state_path.is_file():
        parser.error("Create an explicit test policy state file first")

    def state():
        value = json.loads(state_path.read_text())
        if not isinstance(value, dict) or not isinstance(value.get("revision"), str):
            raise ValueError("Explicit test policy revision required")
        return value

    with TemporaryDirectory(prefix="ocean-c16-browser-") as directory:
        fixture = build_fixture(Path(directory), state=state, count=args.count)
        app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
        app.state.catalogue_service = fixture.service
        app.state.catalogue_browser = fixture.browser
        initial = V1RuntimeConfiguration(site_id="v1:c16-local-test", revision="test")

        def configuration(actor):
            capabilities = dict(initial.capabilities)
            capabilities["catalogue"] = "ready"
            return V1RuntimeConfiguration(
                site_id="v1:c16-local-test", revision=state()["revision"], capabilities=capabilities,
            )

        app.state.v1_runtime_configuration = configuration

        def authenticate(request):
            if state().get("unauthorized") is True:
                raise auth.AuthenticationFailure(401, "Authentication is required")
            return fixture.user

        auth.authenticate_request = authenticate

        @app.middleware("http")
        async def boundary(request, call_next):
            if request.headers.get("host") not in {f"127.0.0.1:{args.port}", f"localhost:{args.port}"}:
                return JSONResponse(status_code=403, content={"error": "Loopback test host required"})
            if request.url.path.startswith(("/v1/", "/catalogue/")):
                return await auth.authorization_middleware(request, call_next)
            return await call_next(request)

        app.include_router(runtime_router)
        app.include_router(catalogue_router)
        app.include_router(browser_router)

        @app.get("/_ocean/runtime-mode")
        async def mode():
            return JSONResponse(content={"version": "ocean-v1-mode-v1", "mode": "service"})

        output = root / "frontend-v1/out"

        @app.get("/{path:path}")
        async def static(path: str):
            target = (output / (path or "index.html")).resolve()
            if output.resolve() not in target.parents:
                return JSONResponse(status_code=403, content={"error": "Forbidden"})
            if not target.is_file() and not target.suffix:
                target = target.with_suffix(".html")
            if not target.is_file():
                return JSONResponse(status_code=404, content={"error": "Not found"})
            return FileResponse(target, headers={
                "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff",
                "Content-Security-Policy": "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; connect-src 'self'; img-src 'self' data:; font-src 'self'; frame-ancestors 'none'",
            })

        print(json.dumps({"fixture": "explicit synthetic TEST identity only", "snapshots": fixture.snapshots,
                          "dataset_ids": fixture.dataset_ids[:5], "count": args.count}), flush=True)
        uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
