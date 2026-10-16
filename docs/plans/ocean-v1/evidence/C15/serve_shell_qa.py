"""Disposable loopback browser harness using the actual C15 bootstrap boundary.

The identity is an explicit server-side TEST dependency, never a real session.
No database, token, provider, credential or legacy service is accessed. This
harness is not a deployment entry point and requires a test-only environment.
"""
import argparse
import asyncio
import os
from pathlib import Path
import sys
import uuid

if os.environ.get("DEPLOYMENT_ENV") != "test" or os.environ.get("AUTH_MODE") != "disabled":
    raise RuntimeError("This disposable harness requires explicit isolated test settings")

root = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(root))

# Imports follow the test environment and checkout guards intentionally.
# ruff: noqa: E402
from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
import uvicorn
from api import auth
from api.auth import CurrentUser, ROLE_PERMISSIONS
from api.v1_runtime_routes import V1RuntimeConfiguration, router

parser = argparse.ArgumentParser()
parser.add_argument("--role", choices=sorted(ROLE_PERMISSIONS), required=True)
parser.add_argument("--state", choices=["ready", "unauthorized", "unavailable", "error", "malformed"], required=True)
parser.add_argument("--delay-seconds", type=float, default=0)
parser.add_argument("--mode-response", choices=["valid", "invalid"], default="valid")
args = parser.parse_args()
if not 0 <= args.delay_seconds <= 15:
    parser.error("Delay must be between zero and 15 seconds")
output = root / "frontend-v1/out"
if not (output / "index.html").is_file():
    raise RuntimeError("Build the current v1 frontend before browser verification")

identity = CurrentUser(
    id=uuid.UUID("ffb9cded-56c6-4072-bef9-a7c05a975042"),
    email="browser-qa@example.invalid", display_name="Local v1 test identity",
    role=args.role, account_type="research", status="active",
    permissions=ROLE_PERMISSIONS[args.role], auth_provider="local-v1-browser-test",
)


def current(request):
    if args.state == "unauthorized":
        raise auth.AuthenticationFailure(401, "Authentication is required")
    return identity


auth.authenticate_request = current
app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
if args.state != "unavailable":
    app.state.v1_runtime_configuration = V1RuntimeConfiguration(
        site_id="v1:local-browser-test", revision="browser-test-1"
    )
if args.state == "error":
    def failed(actor):
        raise OSError("Explicit synthetic runtime callback failure")
    app.state.v1_runtime_configuration = failed


@app.middleware("http")
async def boundary(request, call_next):
    if request.headers.get("host") not in {"127.0.0.1:3100", "localhost:3100"}:
        return JSONResponse(status_code=403, content={"error": "Loopback test host required"})
    if request.url.path.startswith("/v1/"):
        if args.delay_seconds:
            await asyncio.sleep(args.delay_seconds)
        if args.state == "malformed":
            return JSONResponse(content={"version": "explicit-invalid-browser-test"})
        return await auth.authorization_middleware(request, call_next)
    return await call_next(request)


app.include_router(router)


@app.get("/_ocean/runtime-mode")
async def mode():
    return JSONResponse(
        content={"version": "ocean-v1-mode-v1", "mode": "service"}
        if args.mode_response == "valid" else {"mode": "explicit-invalid-browser-test"},
        headers={"Cache-Control": "no-store"},
    )


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


if __name__ == "__main__":
    print(f"Local test identity only: {args.role}; state={args.state}", flush=True)
    uvicorn.run(app, host="127.0.0.1", port=3100, log_level="warning")
