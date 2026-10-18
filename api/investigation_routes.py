"""C17 exact authenticated operations with one worker-owned service lifetime."""
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
from orchestration.investigations import InvestigationError, InvestigationService
from schema.investigations import (
    ContextChangeRequest,
    ContextGetRequest,
    ConversationCreateRequest,
    ConversationGetRequest,
    ConversationListRequest,
    ConversationRenameRequest,
    INVESTIGATION_REQUEST_MODELS,
    InvestigationArchiveRequest,
    InvestigationCreateRequest,
    InvestigationGetRequest,
    InvestigationListRequest,
    InvestigationRefreshRequest,
    InvestigationRenameRequest,
    OperationGetRequest,
    OperationRetryRequest,
    finite_utf8_json,
)

MAX_REQUEST_BYTES = 262144


def _error(code: str, message: str) -> dict:
    return {"error": {"code": code, "message": message}}


def _unique_object(items):
    result = {}
    for key, value in items:
        if key in result:
            raise ValueError("Duplicate JSON object key")
        result[key] = value
    return result


def _invalid_constant(_value):
    raise ValueError("Nonfinite JSON value")


class InvestigationRoute(APIRoute):
    def get_route_handler(self):
        handler = super().get_route_handler()

        async def validate(request: Request):
            # FastAPI's default JSON decoder accepts duplicate object members.
            # Reject ambiguous idempotency/context requests before dispatch and
            # never reflect submitted names, references or validator details.
            try:
                chunks, size = [], 0
                async for chunk in request.stream():
                    # Check before retaining the new chunk and stop receiving
                    # immediately; Content-Length cannot bound chunked input.
                    if len(chunk) > MAX_REQUEST_BYTES - size:
                        raise ValueError("Investigation request exceeds the bound")
                    size += len(chunk)
                    chunks.append(chunk)
                body = b"".join(chunks)
                # Starlette's Request.body/json methods share this cache. The
                # bounded stream has been consumed, so FastAPI must parse this
                # exact body instead of reading the receive channel again.
                request._body = body
                decoded = json.loads(
                    body.decode("utf-8"), object_pairs_hook=_unique_object,
                    parse_constant=_invalid_constant,
                )
                finite_utf8_json(decoded)
            except (ValueError, TypeError, UnicodeError, RecursionError):
                return JSONResponse(status_code=422, content=_error("invalid_request", "Investigation request is invalid"))
            try:
                return await handler(request)
            except RequestValidationError:
                return JSONResponse(status_code=422, content=_error("invalid_request", "Investigation request is invalid"))

        return validate


router = APIRouter(
    prefix="/research/investigations", tags=["investigations"], route_class=InvestigationRoute,
)


def investigation_response(user, service, name: str, payload: BaseModel | dict) -> JSONResponse:
    """Authorize, validate, invoke and encode on one resource-owning worker."""
    if not isinstance(user, CurrentUser):
        return JSONResponse(status_code=401, content=_error("authentication_required", "Authentication is required"))
    if user.status != "active" or "data:read" not in user.permissions:
        return JSONResponse(status_code=403, content=_error("access_denied", "Investigation access is denied"))
    try:
        model = INVESTIGATION_REQUEST_MODELS.get(name)
        if model is None:
            raise ValueError("Unknown operation")
        raw = payload.model_dump(mode="json", warnings=False) if isinstance(payload, BaseModel) else payload
        parsed = model.model_validate(raw)
    except (TypeError, ValueError, UnicodeError, RecursionError):
        return JSONResponse(status_code=422, content=_error("invalid_request", "Investigation request is invalid"))
    try:
        if not config.v1_investigations_enabled():
            return JSONResponse(status_code=503, content=_error("investigations_disabled", "Investigations are disabled"))
        if not isinstance(service, InvestigationService):
            return JSONResponse(status_code=503, content=_error("investigations_unavailable", "Investigations are unavailable"))
        result = service.invoke(name, parsed.model_dump(mode="json", exclude_none=True), user)
        if not isinstance(result, dict):
            raise ValueError("Investigation response must be an object")
        finite_utf8_json(result)
        return JSONResponse(content=result)
    except InvestigationError as exc:
        return JSONResponse(status_code=exc.status_code, content=_error(exc.code, exc.message))
    except Exception:
        return JSONResponse(status_code=503, content=_error("investigations_unavailable", "Investigations are unavailable"))


async def _invoke(request: Request, name: str, payload: BaseModel) -> JSONResponse:
    response = await run_in_threadpool(
        investigation_response, get_current_user(request),
        getattr(request.app.state, "investigation_service", None), name, payload,
    )
    # Pending cancellation is delivered only after worker-owned sessions close
    # and complete JSON encoding finishes; cancelled responses cannot escape.
    await checkpoint()
    return response


@router.post("/create")
async def create(request: Request, payload: InvestigationCreateRequest) -> JSONResponse:
    return await _invoke(request, "create", payload)


@router.post("/list")
async def list_investigations(request: Request, payload: InvestigationListRequest) -> JSONResponse:
    return await _invoke(request, "list", payload)


@router.post("/get")
async def get(request: Request, payload: InvestigationGetRequest) -> JSONResponse:
    return await _invoke(request, "get", payload)


@router.post("/rename")
async def rename(request: Request, payload: InvestigationRenameRequest) -> JSONResponse:
    return await _invoke(request, "rename", payload)


@router.post("/archive")
async def archive(request: Request, payload: InvestigationArchiveRequest) -> JSONResponse:
    return await _invoke(request, "archive", payload)


@router.post("/conversations/create")
async def create_conversation(request: Request, payload: ConversationCreateRequest) -> JSONResponse:
    return await _invoke(request, "conversations/create", payload)


@router.post("/conversations/list")
async def list_conversations(request: Request, payload: ConversationListRequest) -> JSONResponse:
    return await _invoke(request, "conversations/list", payload)


@router.post("/conversations/get")
async def get_conversation(request: Request, payload: ConversationGetRequest) -> JSONResponse:
    return await _invoke(request, "conversations/get", payload)


@router.post("/conversations/rename")
async def rename_conversation(request: Request, payload: ConversationRenameRequest) -> JSONResponse:
    return await _invoke(request, "conversations/rename", payload)


@router.post("/context/get")
async def get_context(request: Request, payload: ContextGetRequest) -> JSONResponse:
    return await _invoke(request, "context/get", payload)


@router.post("/context/change")
async def change_context(request: Request, payload: ContextChangeRequest) -> JSONResponse:
    return await _invoke(request, "context/change", payload)


@router.post("/refresh")
async def refresh(request: Request, payload: InvestigationRefreshRequest) -> JSONResponse:
    return await _invoke(request, "refresh", payload)


@router.post("/operations/get")
async def get_operation(request: Request, payload: OperationGetRequest) -> JSONResponse:
    return await _invoke(request, "operations/get", payload)


@router.post("/operations/retry")
async def retry_operation(request: Request, payload: OperationRetryRequest) -> JSONResponse:
    return await _invoke(request, "operations/retry", payload)
