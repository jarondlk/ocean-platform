"""C21 strict private wire: unknowns, snapshot cursors and bounded events."""
import copy

import pytest
from pydantic import ValidationError

from schema.research_evidence import (
    AnswerEventsResponse, AnswerJob, AnswerListResponse, AnswerSubmitRequest,
    EvidenceAddressRequest, EvidenceTotal,
)

U = '00000000-0000-0000-0000-000000000001'
BINDING = {'investigation_id': U, 'conversation_id': U, 'revision_id': U,
           'snapshot_id': 'a' * 64, 'payload_sha256': 'b' * 64}


def job():
    return {'id': U, 'run_id': U, 'input_version': 2, 'binding': BINDING,
            'locale': 'en', 'status': 'queued', 'active_elapsed_ms': 1,
            'budget': {'active_elapsed_seconds': 0.001, 'tool_actions': 2,
                       'model_calls': 0, 'malformed_repairs': 0, 'cancellation_requested': False},
            'event_cursor': 0, 'latest_event_cursor': 0, 'activity': [],
            'answer': None, 'error': None, 'synthetic': False}


def test_unknown_total_is_not_zero_and_real_zero_remains_known():
    assert EvidenceTotal(state='known', value=0, reason=None).value == 0
    assert EvidenceTotal(state='unknown', value=None, reason='Not reported').value is None
    for invalid in ({'state': 'known', 'value': None, 'reason': None},
                    {'state': 'unknown', 'value': 0, 'reason': 'Not reported'},
                    {'state': 'unknown', 'value': None, 'reason': None},
                    {'state': 'known', 'value': True, 'reason': None}):
        with pytest.raises(ValidationError):
            EvidenceTotal.model_validate(invalid)


@pytest.mark.parametrize('field,value', [('event_cursor', False), ('event_cursor', 0.0),
                                        ('event_cursor', 1), ('synthetic', 0), ('synthetic', True),
                                        ('active_elapsed_ms', True), ('input_version', True)])
def test_answer_snapshot_rejects_literal_coercion_and_untrusted_fixture_flags(field, value):
    value_job = job()
    value_job[field] = value
    with pytest.raises(ValidationError):
        AnswerJob.model_validate(value_job)


def test_empty_answer_history_discovers_actual_clarified_input_version_and_binding():
    response = AnswerListResponse(version='research-answers-v1', access_revision='c' * 64,
        run_id=U, input_version=2, binding=BINDING, eligible=True, reason=None, items=[], next_cursor=None)
    assert response.input_version == 2 and response.items == []
    assert response.binding.revision_id == BINDING['revision_id']


def test_success_cannot_be_reported_without_immutable_rendered_answer():
    for status in ('completed', 'partial'):
        value_job = job()
        value_job['status'] = status
        with pytest.raises(ValidationError):
            AnswerJob.model_validate(value_job)


def test_receipt_address_binds_exact_expected_hash():
    address = {'receipt_id': 'c21:receipt:' + 'd' * 64, 'expected_sha256': 'd' * 64}
    EvidenceAddressRequest.model_validate(address)
    address['expected_sha256'] = 'e' * 64
    with pytest.raises(ValidationError):
        EvidenceAddressRequest.model_validate(address)


def test_answer_requests_reject_authority_and_budget_injection():
    valid = {'investigation_id': U, 'conversation_id': U, 'run_id': U,
             'input_version': 2, 'locale': 'ja', 'idempotency_key': U}
    assert AnswerSubmitRequest.model_validate(valid).locale == 'ja'
    for key, value in {'user_id': U, 'authority': 'published', 'budget': {},
                       'scope': {}, 'controller_result': {}, 'model': 'untrusted'}.items():
        with pytest.raises(ValidationError):
            AnswerSubmitRequest.model_validate({**valid, key: value})


def event_page():
    return {'version': 'research-answers-v1', 'access_revision': 'c' * 64, 'job_id': U,
            'binding': BINDING, 'after_cursor': 0, 'next_cursor': 1, 'latest_event_cursor': 2,
            'has_more': True, 'events': [{'cursor': 1, 'job_id': U, 'elapsed_ms': 1,
                'kind': 'accepted', 'summary': {'en': 'Answer requested', 'ja': '回答を依頼'}}]}


def test_event_page_requires_consecutive_owned_job_cursors_without_allocating_high_water():
    page = event_page()
    assert AnswerEventsResponse.model_validate(page).has_more
    invalids = []
    for key, value in [('next_cursor', 9007199254740991), ('has_more', False),
                       ('latest_event_cursor', 0), ('after_cursor', 2)]:
        invalids.append({**page, key: value})
    wrong_job = copy.deepcopy(page)
    wrong_job['events'][0]['job_id'] = '00000000-0000-0000-0000-000000000002'
    invalids.append(wrong_job)
    for invalid in invalids:
        with pytest.raises(ValidationError):
            AnswerEventsResponse.model_validate(invalid)
