"""C16 authenticated discovery: current identity, worker lifetime, no fallback."""
from __future__ import annotations

from anyio.lowlevel import checkpoint
from fastapi import APIRouter, Request
from pydantic import BaseModel
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

import config
from api.auth import get_current_user
from api.catalogue_routes import CatalogueRoute
from orchestration.catalogue_browser import CatalogueBrowser
from orchestration.catalogue_service import CatalogueService, CatalogueServiceError, catalogue_access_binding
from schema.catalogue_browser import CatalogueSnapshotsRequest

router = APIRouter(prefix="/catalogue", tags=["catalogue-browser"], route_class=CatalogueRoute)


def snapshots_response(user, browser, payload: BaseModel | dict, catalogue_service=None):
    """Resolve policy, read/validate and encode the whole response on one worker."""
    try:
        catalogue_access_binding(user)
        try:
            request = CatalogueSnapshotsRequest.model_validate(
                payload.model_dump(mode="json", warnings=False) if isinstance(payload, BaseModel) else payload
            )
        except (ValueError, TypeError):
            raise CatalogueServiceError("invalid_request", "Catalogue request is invalid", 422) from None
        if not config.v1_catalogue_enabled() or not config.v1_catalogue_browser_enabled():
            raise CatalogueServiceError("catalogue_disabled", "Catalogue browser is disabled", 503)
        if (
            not isinstance(browser, CatalogueBrowser)
            or not isinstance(catalogue_service, CatalogueService)
            or browser.service is not catalogue_service
        ):
            raise CatalogueServiceError("catalogue_unavailable", "Catalogue is unavailable", 503)
        return JSONResponse(content=browser.discover(request, user))
    except CatalogueServiceError as exc:
        return JSONResponse(status_code=exc.status_code, content={"error": {"code": exc.code, "message": exc.message}})
    except Exception:
        return JSONResponse(status_code=503, content={"error": {"code": "catalogue_unavailable", "message": "Catalogue is unavailable"}})


@router.post("/snapshots")
async def snapshots(request: Request, payload: CatalogueSnapshotsRequest):
    response = await run_in_threadpool(
        snapshots_response, get_current_user(request), getattr(request.app.state, "catalogue_browser", None), payload,
        getattr(request.app.state, "catalogue_service", None),
    )
    await checkpoint()
    return response
