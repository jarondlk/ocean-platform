"""C20 fixed owner-private HTTP actions over an explicitly supplied v1 store."""
from __future__ import annotations

import json

from anyio.lowlevel import checkpoint
from fastapi import APIRouter, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

import config
from api.auth import CurrentUser, get_current_user
from orchestration.investigations import InvestigationService
from orchestration.research_runs import ResearchRunError, ResearchRunService
from schema.investigations import finite_utf8_json
from schema.research_runs import (
    RUN_REQUEST_MODELS, RunAddressRequest, RunClarifyRequest, RunEventsRequest,
    RunListRequest, RunMutationRequest, RunSubmitRequest, validate_run_response,
)

MAX_REQUEST_BYTES = 65536
DISPATCH_ACTIONS = frozenset({"submit", "clarify", "continue"})


def _error(code, message, status=503):
    return JSONResponse(status_code=status, content={"error": {"code": code, "message": message}})


def _unique_object(items):
    result = {}
    for key, value in items:
        if key in result:
            raise ValueError("Ambiguous object")
        result[key] = value
    return result


def _invalid_constant(_value):
    raise ValueError("Nonfinite value")


class ResearchRunRoute(APIRoute):
    def get_route_handler(self):
        handler = super().get_route_handler()

        async def validate(request):
            try:
                if request.query_params:
                    raise ValueError("Run requests do not accept query parameters")
                chunks, size = [], 0
                async for chunk in request.stream():
                    if len(chunk) > MAX_REQUEST_BYTES - size:
                        raise ValueError("Request exceeds the bound")
                    size += len(chunk)
                    chunks.append(chunk)
                body = b"".join(chunks)
                request._body = body
                decoded = json.loads(body.decode("utf-8"), object_pairs_hook=_unique_object, parse_constant=_invalid_constant)
                finite_utf8_json(decoded)
            except (ValueError, TypeError, UnicodeError, RecursionError):
                return _error("invalid_request", "Research request is invalid", 422)
            try:
                return await handler(request)
            except RequestValidationError:
                return _error("invalid_request", "Research request is invalid", 422)

        return validate


router = APIRouter(prefix="/research/runs", tags=["research-runs"], route_class=ResearchRunRoute)


def configured_run_service(service, investigations):
    return (
        isinstance(service, ResearchRunService) and isinstance(investigations, InvestigationService)
        and service.investigations is investigations and service.site_id == investigations.site_id
    )


def research_run_response(user, service, investigations, name, payload):
    """Keep authorization, service sessions and response encoding in one worker."""
    if not isinstance(user, CurrentUser):
        return _error("authentication_required", "Authentication is required", 401)
    if user.status != "active" or not {"chat:use", "data:read"} <= user.permissions:
        return _error("access_denied", "Research access is denied", 403)
    try:
        model = RUN_REQUEST_MODELS[name]
        raw = payload.model_dump(mode="json", warnings=False) if isinstance(payload, BaseModel) else payload
        parsed = model.model_validate(raw)
    except (KeyError, TypeError, ValueError, UnicodeError, RecursionError):
        return _error("invalid_request", "Research request is invalid", 422)
    try:
        if not config.v1_research_runs_enabled():
            return _error("research_runs_disabled", "Research history is disabled")
        if not configured_run_service(service, investigations):
            return _error("research_runs_unavailable", "Research history is unavailable")
        if name in DISPATCH_ACTIONS and (
            not config.v1_research_dispatch_enabled() or not config.v1_research_controller_enabled()
            or service.dispatch_available is not True
        ):
            return _error("research_dispatch_unavailable", "Research execution is unavailable")
        result = service.invoke(name, parsed.model_dump(mode="json", exclude_none=True), user)
        # This validates the complete public DTO, including consecutive event
        # cursors and the requested binding. Private journal fields cannot leak.
        return JSONResponse(content=validate_run_response(name, result, parsed))
    except ResearchRunError as exc:
        return _error(exc.code, exc.message, exc.status_code)
    except Exception:
        return _error("research_runs_unavailable", "Research history is unavailable")


async def _invoke(request, name, payload):
    response = await run_in_threadpool(
        research_run_response, get_current_user(request),
        getattr(request.app.state, "research_run_service", None),
        getattr(request.app.state, "investigation_service", None), name, payload,
    )
    await checkpoint()
    return response


@router.post("/submit")
async def submit(request: Request, payload: RunSubmitRequest):
    return await _invoke(request, "submit", payload)


@router.post("/status")
async def status(request: Request, payload: RunAddressRequest):
    return await _invoke(request, "status", payload)


@router.post("/events")
async def events(request: Request, payload: RunEventsRequest):
    return await _invoke(request, "events", payload)


@router.post("/cancel")
async def cancel(request: Request, payload: RunMutationRequest):
    return await _invoke(request, "cancel", payload)


@router.post("/clarify")
async def clarify(request: Request, payload: RunClarifyRequest):
    return await _invoke(request, "clarify", payload)


@router.post("/continue")
async def continue_run(request: Request, payload: RunMutationRequest):
    return await _invoke(request, "continue", payload)


@router.post("/list")
async def list_runs(request: Request, payload: RunListRequest):
    return await _invoke(request, "list", payload)
