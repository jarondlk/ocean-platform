"""Explicit, authenticated bootstrap for the separate v1 application shell.

No database, credential, fixture, catalogue or legacy resource discovery occurs.
CurrentUser comes from the existing current-request authentication boundary.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
from types import MappingProxyType
from typing import Mapping

from anyio.lowlevel import checkpoint
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import TypeAdapter
from starlette.concurrency import run_in_threadpool

import config
from api.auth import CurrentUser, get_current_user
from schema.context_catalogue import Identifier, canonical_json

VERSION = "ocean-v1-runtime-v1"
REQUIRED_PERMISSIONS = MappingProxyType({
    "research": ("chat:use",),
    "catalogue": ("data:read",),
    "tools": ("data:read",),
    "settings": ("profile:read",),
    "administration": ("users:manage",),
    "feedback": ("feedback:write",),
    "about": ("profile:read",),
})
DEFERRED_REASONS = MappingProxyType({
    "research": "Research sessions and execution are not integrated in this shell stage.",
    "catalogue": "The catalogue browser is not integrated in this shell stage.",
    "tools": "Specialist tools are not integrated in this shell stage.",
    "administration": "V1 administration workflows are not integrated in this shell stage.",
    "feedback": "V1 feedback persistence is not integrated in this shell stage.",
})


@dataclass(frozen=True)
class V1RuntimeConfiguration:
    """Trusted host configuration; never derived from query, cookies or storage."""
    site_id: str
    revision: str
    capabilities: Mapping[str, str] = field(default_factory=lambda: {
        name: "unavailable" if name in DEFERRED_REASONS else "ready"
        for name in REQUIRED_PERMISSIONS
    })

    def __post_init__(self):
        for value in (self.site_id, self.revision):
            TypeAdapter(Identifier).validate_python(value)
        if not self.site_id.startswith("v1:"):
            raise ValueError("An explicit v1 site identity is required")
        values = dict(self.capabilities)
        if set(values) != set(REQUIRED_PERMISSIONS) or any(
            value not in {"ready", "unavailable", "disabled"}
            for value in values.values()
        ):
            raise ValueError("Explicit known capability states required")
        if any(values[name] == "ready" for name in DEFERRED_REASONS):
            raise ValueError("Unintegrated workflows cannot be enabled by configuration")
        object.__setattr__(self, "capabilities", MappingProxyType(values))


router = APIRouter(prefix="/v1", tags=["v1-runtime"])


def _error(status, code, message):
    return JSONResponse(status_code=status, content={"error": {"code": code, "message": message}})


def runtime_response(user, configured):
    """Own configuration callback lifetime and serialization in the same worker."""
    if not isinstance(user, CurrentUser):
        return _error(401, "authentication_required", "Authentication is required")
    if user.status != "active" or "profile:read" not in user.permissions:
        return _error(403, "access_denied", "V1 runtime access is denied")
    try:
        if not config.v1_shell_enabled():
            return _error(503, "runtime_disabled", "V1 shell access is disabled")
        configuration = configured(user) if callable(configured) else configured
        if not isinstance(configuration, V1RuntimeConfiguration):
            return _error(503, "runtime_unavailable", "V1 runtime is unavailable")
        capabilities = {}
        for name, required in REQUIRED_PERMISSIONS.items():
            permitted = set(required) <= user.permissions
            status = configuration.capabilities[name] if permitted else "forbidden"
            reason = None if status == "ready" else (
                "This identity does not have the required permissions." if not permitted
                else "This capability is disabled." if status == "disabled"
                else DEFERRED_REASONS.get(name, "This capability is unavailable.")
            )
            capabilities[name] = {
                "status": status, "reason": reason, "required_permissions": list(required),
            }
        identity = {
            "id": str(user.id), "display_name": user.display_name,
            "role": user.role, "account_type": user.account_type,
            "status": user.status, "permissions": sorted(user.permissions),
        }
        revision = hashlib.sha256(canonical_json({
            "identity": identity, "site_id": configuration.site_id,
            "configuration_revision": configuration.revision, "capabilities": capabilities,
        }).encode()).hexdigest()
        return JSONResponse(content={
            "version": VERSION, "deployment": "v1", "identity": identity,
            "permission_revision": revision, "capabilities": capabilities,
        })
    except Exception:
        # Host callbacks/configuration may fail; paths and provider text are not
        # a public sign-in or runtime response, and no fallback is permitted.
        return _error(503, "runtime_unavailable", "V1 runtime is unavailable")


@router.get("/runtime")
async def runtime(request: Request):
    user = get_current_user(request)
    if request.query_params:
        return _error(422, "invalid_request", "V1 runtime does not accept query parameters")
    configured = getattr(request.app.state, "v1_runtime_configuration", None)
    response = await run_in_threadpool(runtime_response, user, configured)
    await checkpoint()
    return response
