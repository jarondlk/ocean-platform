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
from api.research_evidence_routes import configured_answer_service, configured_evidence_service
from orchestration.catalogue_browser import CatalogueBrowser
from orchestration.catalogue_service import CatalogueService
from orchestration.investigations import InvestigationService
from orchestration.research_runs import ResearchRunService
from schema.context_catalogue import Identifier, canonical_json

VERSION = "ocean-v1-runtime-v1"
REQUIRED_PERMISSIONS = MappingProxyType({
    "research": ("chat:use", "data:read"),
    "catalogue": ("data:read",),
    "tools": ("data:read",),
    "settings": ("profile:read",),
    "administration": ("users:manage",),
    "feedback": ("feedback:write",),
    "about": ("profile:read",),
})
DEFERRED_REASONS = MappingProxyType({
    "research": "The configured research context services are unavailable.",
    "catalogue": "The configured catalogue browser services are unavailable.",
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
        if any(values[name] == "ready" for name in DEFERRED_REASONS if name not in {"catalogue", "research"}):
            raise ValueError("Unintegrated workflows cannot be enabled by configuration")
        object.__setattr__(self, "capabilities", MappingProxyType(values))


router = APIRouter(prefix="/v1", tags=["v1-runtime"])


def _error(status, code, message):
    return JSONResponse(status_code=status, content={"error": {"code": code, "message": message}})


def _catalogue_available(service, browser):
    try:
        return (
            config.v1_catalogue_enabled() and config.v1_catalogue_browser_enabled()
            and isinstance(service, CatalogueService)
            and isinstance(browser, CatalogueBrowser) and browser.service is service
        )
    except config.SecurityConfigurationError:
        return False


def _research_available(configuration, catalogue_service, catalogue_browser, investigation_service):
    """Context management readiness; this never enables production execution."""
    try:
        return (
            _catalogue_available(catalogue_service, catalogue_browser)
            and config.v1_investigations_enabled()
            and isinstance(investigation_service, InvestigationService)
            and investigation_service.catalogue is catalogue_service
            and investigation_service.site_id == configuration.site_id
        )
    except config.SecurityConfigurationError:
        return False


def _research_runs(configuration, user, research_status, investigations, service):
    capability = {
        "version": "research-runs-v1", "transport": "unavailable",
        "submit_enabled": False, "dispatch_enabled": False,
        "synthesis": "unavailable", "reason": "Research execution is unavailable.",
    }
    try:
        history_available = (
            research_status == "ready" and {"chat:use", "data:read"} <= user.permissions
            and config.v1_research_runs_enabled()
            and isinstance(service, ResearchRunService)
            and service.investigations is investigations
            and service.site_id == configuration.site_id
        )
    except config.SecurityConfigurationError:
        history_available = False
    if not history_available:
        return capability
    capability["transport"] = "http-v1"
    capability["reason"] = "New research execution is unavailable. Saved research remains accessible."
    try:
        dispatch = (
            config.v1_research_dispatch_enabled() and config.v1_research_controller_enabled()
            and service.dispatch_available is True
        )
    except config.SecurityConfigurationError:
        dispatch = False
    capability["submit_enabled"] = capability["dispatch_enabled"] = dispatch
    if dispatch:
        capability["reason"] = None
    return capability


def _research_evidence(user, research_status, investigations, evidence, answers):
    capability = {'version': 'research-evidence-v1', 'transport': 'unavailable',
        'synthesis': 'unavailable', 'submit_enabled': False, 'reason': 'Retained evidence is unavailable.'}
    try:
        history = (research_status == 'ready' and {'chat:use', 'data:read'} <= user.permissions
            and config.v1_evidence_enabled() and configured_evidence_service(evidence, investigations)
            and configured_answer_service(answers, evidence))
        if not history:
            return capability
        capability['transport'] = 'http-v1'
        capability['reason'] = 'New answer preparation is unavailable. Retained evidence remains accessible.'
        if (config.v1_synthesis_enabled() and configured_answer_service(answers, evidence)
                and answers.dispatch_available is True):
            capability.update(synthesis='http-v1', submit_enabled=True, reason=None)
    except config.SecurityConfigurationError:
        pass
    return capability


def runtime_response(user, configured, catalogue_service=None, catalogue_browser=None, investigation_service=None,
                     research_run_service=None, research_evidence_service=None, research_answer_service=None):
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
            if name == "catalogue" and status == "ready":
                if not _catalogue_available(catalogue_service, catalogue_browser):
                    status = "unavailable"
            if name == "research" and status == "ready":
                if not _research_available(configuration, catalogue_service, catalogue_browser, investigation_service):
                    status = "unavailable"
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
        research_runs = _research_runs(
            configuration, user, capabilities["research"]["status"],
            investigation_service, research_run_service,
        )
        extra = {}
        if research_evidence_service is not None or research_answer_service is not None:
            extra['research_evidence'] = _research_evidence(user, capabilities['research']['status'],
                investigation_service, research_evidence_service, research_answer_service)
        revision = hashlib.sha256(canonical_json({
            "identity": identity, "site_id": configuration.site_id,
            "configuration_revision": configuration.revision, "capabilities": capabilities,
            "research_runs": research_runs,
            **extra,
        }).encode()).hexdigest()
        return JSONResponse(content={
            "version": VERSION, "deployment": "v1", "identity": identity,
            "permission_revision": revision, "capabilities": capabilities,
            "research_runs": research_runs,
            **extra,
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
    response = await run_in_threadpool(
        runtime_response, user, configured,
        getattr(request.app.state, "catalogue_service", None),
        getattr(request.app.state, "catalogue_browser", None),
        getattr(request.app.state, "investigation_service", None),
        getattr(request.app.state, "research_run_service", None),
        getattr(request.app.state, "research_evidence_service", None),
        getattr(request.app.state, "research_answer_service", None),
    )
    await checkpoint()
    return response
