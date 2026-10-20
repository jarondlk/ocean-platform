"""C21 fixed independent-v1 answer/evidence actions with worker-owned resources."""
from __future__ import annotations

from anyio.lowlevel import checkpoint
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

import config
from api.auth import CurrentUser, get_current_user
from api.research_run_routes import ResearchRunRoute
from orchestration.investigations import InvestigationService
from orchestration.research_answers import ResearchAnswerError, ResearchAnswerService
from orchestration.research_evidence import ResearchEvidenceError, ResearchEvidenceService
from schema.research_evidence import (
    ANSWER_REQUEST_MODELS, ANSWER_RESPONSE_MODELS, EVIDENCE_REQUEST_MODELS, EVIDENCE_RESPONSE_MODELS,
    AnswerAddressRequest, AnswerCancelRequest, AnswerEventsRequest, AnswerListRequest, AnswerSubmitRequest,
    EvidenceAddressRequest, EvidenceExportRequest, EvidenceListRequest, EvidencePageRequest,
)

MAX_RESPONSE_BYTES = 8 * 1024 * 1024
router = APIRouter(prefix='/research', tags=['research-evidence'], route_class=ResearchRunRoute)


def _error(code, message, status=503):
    return JSONResponse(status_code=status, content={'error': {'code': code, 'message': message}})


def configured_evidence_service(evidence, investigations):
    return (isinstance(evidence, ResearchEvidenceService) and isinstance(investigations, InvestigationService)
            and evidence.investigations is investigations and evidence.site_id == investigations.site_id
            and evidence.session_factory is investigations.session_factory)


def configured_answer_service(answers, evidence):
    return (isinstance(answers, ResearchAnswerService) and answers.evidence is evidence
            and answers.site_id == evidence.site_id and answers.session_factory is evidence.session_factory)


def _bound(group, name, data, result):
    if group == 'answers':
        if name == 'list':
            if result['run_id'] != data['run_id']:
                raise ValueError('Wrong answer history')
            binding = result['binding']
        elif name == 'events':
            if result['job_id'] != data['job_id'] or result['after_cursor'] != data['after_cursor']:
                raise ValueError('Wrong answer event page')
            binding = result['binding']
        else:
            job = result['job']
            if job['run_id'] != data['run_id'] or ('job_id' in data and job['id'] != data['job_id']):
                raise ValueError('Wrong answer')
            if 'input_version' in data and job['input_version'] != data['input_version']:
                raise ValueError('Wrong clarified input')
            binding = job['binding']
        if any(binding[key] != data[key] for key in ('investigation_id', 'conversation_id')):
            raise ValueError('Wrong answer context')
    elif name == 'list':
        if (result['run_id'] != data['run_id'] or result['input_version'] != data['input_version']
                or result['offset'] != data['offset']):
            raise ValueError('Wrong evidence history')
    else:
        receipt = result['receipt']
        if receipt['id'] != data['receipt_id'] or receipt['sha256'] != data['expected_sha256']:
            raise ValueError('Wrong evidence')
        if name in {'page', 'export'} and (result['offset'] != data['offset'] or result['section'] != data['section']):
            raise ValueError('Wrong retained evidence page')
        if name == 'export' and result['format'] != data['format']:
            raise ValueError('Wrong export format')


def research_evidence_response(user, evidence, answers, investigations, group, name, payload):
    if not isinstance(user, CurrentUser):
        return _error('authentication_required', 'Authentication is required', 401)
    if user.status != 'active' or not {'chat:use', 'data:read'} <= user.permissions:
        return _error('access_denied', 'Research access is denied', 403)
    if group == 'evidence' and name == 'export' and 'data:export' not in user.permissions:
        return _error('access_denied', 'Evidence export access is denied', 403)
    requests = ANSWER_REQUEST_MODELS if group == 'answers' else EVIDENCE_REQUEST_MODELS
    responses = ANSWER_RESPONSE_MODELS if group == 'answers' else EVIDENCE_RESPONSE_MODELS
    try:
        raw = payload.model_dump(mode='json') if isinstance(payload, BaseModel) else payload
        data = requests[name].model_validate(raw).model_dump(mode='json')
    except (KeyError, TypeError, ValueError, UnicodeError, RecursionError):
        return _error('invalid_request', 'Research request is invalid', 422)
    try:
        if not config.v1_evidence_enabled() or not configured_evidence_service(evidence, investigations):
            return _error('evidence_unavailable', 'Retained evidence is unavailable')
        if group == 'answers':
            if not configured_answer_service(answers, evidence):
                return _error('answers_unavailable', 'Answer history is unavailable')
            service = answers
        else:
            service = evidence
        if group == 'answers' and name == 'submit':
            try:
                allow_new_submit = config.v1_synthesis_enabled() and answers.dispatch_available
            except config.SecurityConfigurationError:
                allow_new_submit = False
            result = service.invoke(name, data, user, allow_new_submit=allow_new_submit)
        else:
            result = service.invoke(name, data, user)
        result = responses[name].model_validate(result).model_dump(mode='json')
        _bound(group, name, data, result)
        response = JSONResponse(content=result)
        if len(response.body) > MAX_RESPONSE_BYTES:
            return _error('response_unavailable', 'Research response exceeds its supported bound')
        return response
    except (ResearchAnswerError, ResearchEvidenceError) as exc:
        return _error(exc.code, exc.message, exc.status_code)
    except Exception:
        return _error('answers_unavailable' if group == 'answers' else 'evidence_unavailable',
                      'Research evidence is unavailable')


async def _invoke(request, group, name, payload):
    response = await run_in_threadpool(research_evidence_response, get_current_user(request),
        getattr(request.app.state, 'research_evidence_service', None),
        getattr(request.app.state, 'research_answer_service', None),
        getattr(request.app.state, 'investigation_service', None), group, name, payload)
    await checkpoint()
    return response


@router.post('/answers/submit')
async def submit(request: Request, payload: AnswerSubmitRequest):
    return await _invoke(request, 'answers', 'submit', payload)


@router.post('/answers/status')
async def status(request: Request, payload: AnswerAddressRequest):
    return await _invoke(request, 'answers', 'status', payload)


@router.post('/answers/events')
async def events(request: Request, payload: AnswerEventsRequest):
    return await _invoke(request, 'answers', 'events', payload)


@router.post('/answers/cancel')
async def cancel(request: Request, payload: AnswerCancelRequest):
    return await _invoke(request, 'answers', 'cancel', payload)


@router.post('/answers/list')
async def list_answers(request: Request, payload: AnswerListRequest):
    return await _invoke(request, 'answers', 'list', payload)


@router.post('/evidence/list')
async def list_evidence(request: Request, payload: EvidenceListRequest):
    return await _invoke(request, 'evidence', 'list', payload)


@router.post('/evidence/open')
async def open_evidence(request: Request, payload: EvidenceAddressRequest):
    return await _invoke(request, 'evidence', 'open', payload)


@router.post('/evidence/page')
async def page_evidence(request: Request, payload: EvidencePageRequest):
    return await _invoke(request, 'evidence', 'page', payload)


@router.post('/evidence/export')
async def export_evidence(request: Request, payload: EvidenceExportRequest):
    return await _invoke(request, 'evidence', 'export', payload)
