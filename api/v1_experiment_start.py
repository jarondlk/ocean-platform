"""Explicit controller-only reservation route for an authenticated C22 owner.

Composition requires a private host with trusted owner authentication middleware.
The beta serving and Research hosts do not install this router.
"""
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError
from starlette.concurrency import run_in_threadpool

from api.auth import CurrentUser
from api.research_run_routes import ResearchRunRoute
from orchestration.experiment_sandbox.contracts import SandboxError
from orchestration.experiment_sandbox.retained_bridge import C23RetainedBridge, RetainedReserveRequest
from orchestration.research_experiments import ResearchExperimentError

_HEADERS = {'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff'}


def _error(code, status):
    return JSONResponse({'error': {'code': code}}, status_code=status, headers=_HEADERS)


def create_experiment_start_router(*, bridge):
    if type(bridge) is not C23RetainedBridge:
        raise ValueError('An explicit isolated C23 controller is required')
    router = APIRouter(route_class=ResearchRunRoute)

    @router.post('/internal/experiments/start')
    async def start(request: Request, payload: RetainedReserveRequest):
        owner = getattr(request.state, 'current_user', None)
        if not isinstance(owner, CurrentUser):
            return _error('authentication_required', 401)
        if request.headers.get('content-type', '').split(';', 1)[0].strip().lower() != 'application/json':
            return _error('invalid_media_type', 415)
        try:
            receipt = await run_in_threadpool(bridge.reserve, payload, current_owner=owner)
        except ResearchExperimentError as exc:
            return _error(exc.code, exc.status_code)
        except (SandboxError, SQLAlchemyError, ValueError):
            # A failed response can follow a commit. The same request and key
            # must be retained on retry, regardless of the apparent failure.
            return _error('reservation_unavailable', 503)
        document = receipt.document
        return JSONResponse({'version': 'experiment-start-reservation-v1',
            'execution_id': document['execution_id'], 'reservation_id': document['reservation_id'],
            'capacity_reserved_at_commit': document['capacity_reserved_at_commit'],
            'execution_authorized': False}, headers=_HEADERS)

    return router
