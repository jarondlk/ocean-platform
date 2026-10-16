"""C14 authenticated catalogue endpoints with one worker-owned invocation."""
from __future__ import annotations

from anyio.lowlevel import checkpoint
from fastapi import APIRouter, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

from api.auth import get_current_user
from orchestration.catalogue_tools import invoke_catalogue
from schema.catalogue_service import (
    CatalogueCoverageRequest,
    CatalogueListRequest,
    CatalogueOpenRequest,
    CatalogueOverviewRequest,
    CatalogueQueryRequest,
    CatalogueRelationshipsRequest,
    PublishedAnalysisRequest,
)

class CatalogueRoute(APIRoute):
    def get_route_handler(self):
        handler = super().get_route_handler()

        async def validate(request: Request):
            try:
                return await handler(request)
            except RequestValidationError:
                return JSONResponse(
                    status_code=422,
                    content={"error": {
                        "code": "invalid_request",
                        "message": "Catalogue request is invalid",
                    }},
                )

        return validate


router = APIRouter(prefix="/catalogue", tags=["catalogue"], route_class=CatalogueRoute)


def _worker_response(service, name: str, payload: BaseModel, user) -> JSONResponse:
    status_code, body = invoke_catalogue(service, name, payload, lambda: user)
    return JSONResponse(status_code=status_code, content=body)


async def _invoke(request: Request, name: str, payload: BaseModel) -> JSONResponse:
    user = get_current_user(request)
    service = getattr(request.app.state, "catalogue_service", None)
    response = await run_in_threadpool(
        _worker_response, service, name, payload, user,
    )
    # A shielded AnyIO worker closes its resources before pending cancellation
    # reaches this checkpoint, so no cancelled response escapes to the client.
    await checkpoint()
    return response


@router.post("/overview")
async def overview(request: Request, payload: CatalogueOverviewRequest) -> JSONResponse:
    return await _invoke(request, "catalogue.overview", payload)


@router.post("/list")
async def list_entries(request: Request, payload: CatalogueListRequest) -> JSONResponse:
    return await _invoke(request, "catalogue.list", payload)


@router.post("/open")
async def open_entry(request: Request, payload: CatalogueOpenRequest) -> JSONResponse:
    return await _invoke(request, "catalogue.open", payload)


@router.post("/coverage")
async def coverage(request: Request, payload: CatalogueCoverageRequest) -> JSONResponse:
    return await _invoke(request, "catalogue.coverage", payload)


@router.post("/query")
async def query(request: Request, payload: CatalogueQueryRequest) -> JSONResponse:
    return await _invoke(request, "catalogue.query", payload)


@router.post("/relationships")
async def relationships(request: Request, payload: CatalogueRelationshipsRequest) -> JSONResponse:
    return await _invoke(request, "catalogue.relationships", payload)


@router.post("/analysis/get-published")
async def get_published(request: Request, payload: PublishedAnalysisRequest) -> JSONResponse:
    return await _invoke(request, "analysis.get_published", payload)
