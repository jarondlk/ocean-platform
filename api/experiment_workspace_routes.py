"""C25 fixed owner-authorized execution projections; no launch or force release."""
from anyio.lowlevel import checkpoint
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

from api.auth import CurrentUser, get_current_user
from api.research_run_routes import ResearchRunRoute
from orchestration.experiment_workspace import ExperimentWorkspaceService
from orchestration.research_experiments import ResearchExperimentError, ResearchExperimentService
from schema.context_catalogue import canonical_json
from schema.experiment_workspace import (
    EXECUTION_REQUEST_MODELS, EXECUTION_RESPONSE_MODELS,
    ExecutionArtifactRequest, ExecutionCancelRequest, ExecutionCapabilityRequest,
    ExecutionEventsRequest, ExecutionStatusRequest,
)

router = APIRouter(prefix='/research/experiment-executions', tags=['experiment-workspace'], route_class=ResearchRunRoute)


def error(code, status=503):
    message = {'authentication_required': 'Authentication is required', 'access_denied': 'Experiment access is denied',
        'invalid_request': 'Experiment execution request is invalid', 'not_found': 'Experiment execution was not found',
        'conflict': 'Experiment execution changed; review it again'}.get(code, 'Experiment execution is unavailable')
    return JSONResponse(status_code=status, content={'error': {'code': code, 'message': message}},
        headers={'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff'})


def configured_workspace(service, experiments):
    return (isinstance(service, ExperimentWorkspaceService) and isinstance(experiments, ResearchExperimentService)
        and service.experiments is experiments and service.investigations is experiments.investigations
        and service.site_id == experiments.site_id and service.session_factory is experiments.session_factory)


def experiment_workspace_response(user, service, experiments, name, payload):
    if not isinstance(user, CurrentUser):
        return error('authentication_required', 401)
    if user.status != 'active' or user.role not in {'researcher', 'admin'} or not {'chat:use', 'data:read'} <= user.permissions:
        return error('access_denied', 403)
    if name in {'cancel', 'artifact'} and 'data:export' not in user.permissions:
        return error('access_denied', 403)
    try:
        raw = payload.model_dump(mode='json') if isinstance(payload, BaseModel) else payload
        request = EXECUTION_REQUEST_MODELS[name].model_validate(raw).model_dump(mode='json')
    except (KeyError, ValueError, TypeError, UnicodeError, RecursionError):
        return error('invalid_request', 422)
    if not configured_workspace(service, experiments):
        return error('execution_unavailable')
    try:
        result = EXECUTION_RESPONSE_MODELS[name].model_validate(service.invoke(name, request, user)).model_dump(mode='json')
        if name != 'capability':
            if (result['experiment_id'] != request['experiment_id']
                    or result['proposal_revision_id'] != request['expected_proposal_revision_id']
                    or result['proposal_version'] != request['expected_version']
                    or result['hashes'] != request['expected_hashes']
                    or any(result['binding'][k] != request[k] for k in result['binding'])
                    or (request.get('execution_id') is not None and
                        (result['execution'] is None or result['execution']['id'] != request['execution_id']))):
                raise ValueError
        if name == 'events' and (result['after_cursor'] != request['after_cursor'] or len(result['items']) > request['limit']):
            raise ValueError
        if name == 'cancel' and result['cancellation']['idempotency_key'] != request['idempotency_key']:
            raise ValueError
        if name == 'artifact' and (result['artifact']['id'] != request['artifact_id']
                or result['artifact']['sha256'] != request['expected_sha256'] or result['offset'] != request['offset']
                or result['next_offset'] - result['offset'] > request['limit']):
            raise ValueError
        if len(canonical_json(result).encode()) > 8 * 1024 * 1024:
            raise ValueError
        return JSONResponse(content=result, headers={'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff'})
    except ResearchExperimentError as exc:
        return error(exc.code, exc.status_code)
    except Exception:
        return error('execution_unavailable')


async def _invoke(request, name, payload):
    response = await run_in_threadpool(experiment_workspace_response, get_current_user(request),
        getattr(request.app.state, 'experiment_workspace_service', None),
        getattr(request.app.state, 'research_experiment_service', None), name, payload)
    await checkpoint()
    return response


@router.post('/capability')
async def capability(request: Request, payload: ExecutionCapabilityRequest):
    return await _invoke(request, 'capability', payload)


@router.post('/status')
async def status(request: Request, payload: ExecutionStatusRequest):
    return await _invoke(request, 'status', payload)


@router.post('/events')
async def events(request: Request, payload: ExecutionEventsRequest):
    return await _invoke(request, 'events', payload)


@router.post('/cancel')
async def cancel(request: Request, payload: ExecutionCancelRequest):
    return await _invoke(request, 'cancel', payload)


@router.post('/artifact')
async def artifact(request: Request, payload: ExecutionArtifactRequest):
    return await _invoke(request, 'artifact', payload)
