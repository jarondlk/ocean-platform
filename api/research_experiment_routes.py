"""C22 worker-owned private review/approval APIs; no code execution."""
from __future__ import annotations

from anyio.lowlevel import checkpoint
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

from api.auth import CurrentUser, get_current_user
from api.research_run_routes import ResearchRunRoute
from orchestration.investigations import InvestigationService
from orchestration.research_experiments import ResearchExperimentError, ResearchExperimentService
from schema.context_catalogue import canonical_json
from schema.research_experiments import (
    EXPERIMENT_REQUEST_MODELS, EXPERIMENT_RESPONSE_MODELS,
    ExperimentAddressRequest, ExperimentApprovalRequest, ExperimentCreateRequest,
    ExperimentDispatchRequest, ExperimentEventsRequest, ExperimentGetRequest,
    ExperimentListRequest, ExperimentRetryRequest, ExperimentReviseRequest,
)

MAX_RESPONSE_BYTES = 8 * 1024 * 1024
MUTATIONS = frozenset({'create', 'revise', 'approve', 'dispatch', 'retry'})
router = APIRouter(prefix='/research/experiments', tags=['research-experiments'], route_class=ResearchRunRoute)


def _error(code, message, status=503):
    return JSONResponse(status_code=status, content={'error': {'code': code, 'message': message}},
                        headers={'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff'})


def configured_experiment_service(service, investigations):
    return (isinstance(service, ResearchExperimentService) and isinstance(investigations, InvestigationService)
            and service.investigations is investigations and service.site_id == investigations.site_id
            and service.session_factory is investigations.session_factory)


def _bound(name, data, result):
    if name == 'events':
        if result['experiment_id'] != data['experiment_id'] or result['after_cursor'] != data['after_cursor']:
            raise ValueError('Wrong experiment event history')
        if len(result['items']) > data['limit']:
            raise ValueError('Experiment event page exceeds its requested bound')
        return
    items = result['items'] if name == 'list' else [result['experiment']] if result['experiment'] else []
    if name == 'list' and len(items) > data['limit']:
        raise ValueError('Experiment page exceeds its requested bound')
    for experiment in items:
        if 'experiment_id' in data and experiment['id'] != data['experiment_id']:
            raise ValueError('Wrong private experiment')
        binding = experiment['binding']
        preparing = name in {'create', 'revise'} and (not result['operation'] or result['operation']['state'] != 'ready')
        keys = ('investigation_id', 'conversation_id') if preparing else (
            'investigation_id', 'conversation_id', 'context_revision_id', 'snapshot_id', 'context_payload_sha256')
        for key in keys:
            if key in data and data[key] is not None and binding[key] != data[key]:
                raise ValueError('Wrong frozen experiment context')
        revision = data.get('proposal_revision_id') if name == 'get' else data.get('expected_proposal_revision_id') if name in {'approve', 'dispatch'} else None
        if revision is not None and experiment['proposal_revision_id'] != revision:
            raise ValueError('Wrong proposal revision')
        if name in {'approve', 'dispatch'} and experiment['hashes'] != data['expected_hashes']:
            raise ValueError('Wrong approved experiment identity')
        if name in {'create', 'revise'} and not preparing:
            if (result['operation']['result_revision_id'] != experiment['proposal_revision_id']
                    or experiment['proposal'] != data['proposal']):
                raise ValueError('Wrong prepared experiment proposal')
    if name == 'retry' and (not result['operation'] or result['operation']['id'] != data['operation_id']):
        raise ValueError('Wrong prepared experiment operation')
    if name == 'list':
        identities = [item['id'] for item in items]
        if len(set(identities)) != len(identities):
            raise ValueError('Duplicate experiment history entries')


def research_experiment_response(user, service, investigations, name, payload):
    """Authorization, persistence and all output serialization stay in one worker."""
    if not isinstance(user, CurrentUser):
        return _error('authentication_required', 'Authentication is required', 401)
    if user.status != 'active' or user.role not in {'researcher', 'admin'} or not {'chat:use', 'data:read'} <= user.permissions:
        return _error('access_denied', 'Experiment access is denied', 403)
    if name in MUTATIONS and 'data:export' not in user.permissions:
        return _error('access_denied', 'Experiment preparation access is denied', 403)
    try:
        raw = payload.model_dump(mode='json') if isinstance(payload, BaseModel) else payload
        data = EXPERIMENT_REQUEST_MODELS[name].model_validate(raw).model_dump(mode='json')
    except (KeyError, TypeError, ValueError, UnicodeError, RecursionError):
        return _error('invalid_request', 'Experiment request is invalid', 422)
    if not configured_experiment_service(service, investigations):
        return _error('experiments_unavailable', 'Experiments are unavailable')
    try:
        result = service.invoke(name, data, user)
        public = EXPERIMENT_RESPONSE_MODELS[name].model_validate(result).model_dump(mode='json')
        _bound(name, data, public)
        if len(canonical_json(public).encode('utf-8')) > MAX_RESPONSE_BYTES:
            raise ValueError('Experiment response exceeds its byte bound')
        return JSONResponse(content=public, headers={'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff'})
    except ResearchExperimentError as exc:
        return _error(exc.code, exc.message, exc.status_code)
    except Exception:
        return _error('experiments_unavailable', 'Experiments are unavailable')


async def _invoke(request, name, payload):
    response = await run_in_threadpool(
        research_experiment_response, get_current_user(request),
        getattr(request.app.state, 'research_experiment_service', None),
        getattr(request.app.state, 'investigation_service', None), name, payload,
    )
    await checkpoint()
    return response


@router.post('/create')
async def create(request: Request, payload: ExperimentCreateRequest):
    return await _invoke(request, 'create', payload)


@router.post('/revise')
async def revise(request: Request, payload: ExperimentReviseRequest):
    return await _invoke(request, 'revise', payload)


@router.post('/get')
async def get(request: Request, payload: ExperimentGetRequest):
    return await _invoke(request, 'get', payload)


@router.post('/status')
async def status(request: Request, payload: ExperimentAddressRequest):
    return await _invoke(request, 'status', payload)


@router.post('/list')
async def list_experiments(request: Request, payload: ExperimentListRequest):
    return await _invoke(request, 'list', payload)


@router.post('/approve')
async def approve(request: Request, payload: ExperimentApprovalRequest):
    return await _invoke(request, 'approve', payload)


@router.post('/dispatch')
async def dispatch(request: Request, payload: ExperimentDispatchRequest):
    return await _invoke(request, 'dispatch', payload)


@router.post('/events')
async def events(request: Request, payload: ExperimentEventsRequest):
    return await _invoke(request, 'events', payload)


@router.post('/retry')
async def retry(request: Request, payload: ExperimentRetryRequest):
    return await _invoke(request, 'retry', payload)
