"""C21 actual C20→evidence→answer jobs with explicit fake queue/runtime only."""
import json
import uuid

import pytest
from sqlalchemy import func, select

from db.app_models import ResearchAnswer, ResearchAnswerAttempt, ResearchAnswerJob, ResearchAnswerOutbox, ResearchRun
from orchestration.research_answers import FakeAnswerQueue, ResearchAnswerError, ResearchAnswerService
from tests import test_research_evidence_store as evidence_fixtures
from tests.test_research_controller import FakeRuntime, tool

retained = evidence_fixtures.retained
actual = evidence_fixtures.actual


def service(actual):
    fixture, evidence = actual
    answers = ResearchAnswerService(evidence=evidence, queue=FakeAnswerQueue(), enabled=lambda: True,
                                   synthesis_enabled=lambda: True, lease_seconds=5)
    return fixture, evidence, answers


def request(fixture):
    run = evidence_fixtures.finished(fixture)
    return run, {**fixture.address(run), 'input_version': 1, 'locale': 'en', 'idempotency_key': str(uuid.uuid4())}


def delivery(fixture, job):
    with fixture.retained.factory() as session:
        row = session.scalar(select(ResearchAnswerOutbox).where(ResearchAnswerOutbox.job_id == uuid.UUID(job['id'])))
        return {'job_id': job['id'], 'delivery_id': str(row.delivery_id)}


def address(job):
    return {'job_id': job['id'], 'run_id': job['run_id'],
            'investigation_id': job['binding']['investigation_id'], 'conversation_id': job['binding']['conversation_id']}


def test_actual_count_answer_keeps_c20_terminal_immutable_and_needs_no_model(actual):
    fixture, evidence, answers = service(actual)
    run, data = request(fixture)
    with fixture.retained.factory() as session:
        source_before = {c.name: getattr(session.get(ResearchRun, uuid.UUID(run['id'])), c.name) for c in ResearchRun.__table__.columns}
    discover = answers.invoke('list', fixture.address(run), fixture.user)
    assert discover['input_version'] == 1 and discover['eligible'] and discover['items'] == []
    job = answers.invoke('submit', data, fixture.user)['job']
    assert job['status'] == 'queued' and job['answer'] is None
    assert answers.invoke('submit', data, fixture.user)['job']['id'] == job['id']
    outcome = answers.execute_delivery(**delivery(fixture, job))['job']
    assert outcome['status'] == 'completed'
    assert outcome['answer']['model_used'] is False and outcome['answer']['completion'] == 'complete'
    assert outcome['answer']['scientific_verification'] == 'not_independently_verified'
    assert outcome['budget']['model_calls'] == job['budget']['model_calls']
    assert answers.execute_delivery(**delivery(fixture, job))['job'] == outcome
    with fixture.retained.factory() as session:
        assert session.scalar(select(func.count()).select_from(ResearchAnswer)) == 1
        assert session.scalar(select(func.count()).select_from(ResearchAnswerAttempt)) == 0
        source_after = {c.name: getattr(session.get(ResearchRun, uuid.UUID(run['id'])), c.name) for c in ResearchRun.__table__.columns}
    assert source_after == source_before
    page = answers.invoke('events', {**address(job), 'after_cursor': 0, 'limit': 1}, fixture.user)
    assert page['next_cursor'] == 1 and page['has_more']
    reopened = answers.invoke('status', address(job), fixture.user)['job']
    assert reopened['answer']['id'] == outcome['answer']['id']
    receipt_id = outcome['answer']['receipt_ids'][0]
    assert evidence.invoke('open', {'receipt_id': receipt_id, 'expected_sha256': receipt_id[12:]}, fixture.user)['receipt']['counts'][0]['value'] == 4


def test_new_submit_key_reuses_one_budget_head_and_locale_change_conflicts(actual):
    fixture, _, answers = service(actual)
    _, data = request(fixture)
    job = answers.invoke('submit', data, fixture.user)['job']
    second = {**data, 'idempotency_key': str(uuid.uuid4())}
    assert answers.invoke('submit', second, fixture.user)['job']['id'] == job['id']
    with pytest.raises(ResearchAnswerError, match='conflicts'):
        answers.invoke('submit', {**second, 'locale': 'ja', 'idempotency_key': str(uuid.uuid4())}, fixture.user)
    with fixture.retained.factory() as session:
        assert len(session.scalars(select(ResearchAnswerJob).where(ResearchAnswerJob.run_id == uuid.UUID(data['run_id']))).all()) == 1


def test_cancel_is_idempotent_separate_from_c20_and_prevents_delivery(actual):
    fixture, _, answers = service(actual)
    run, data = request(fixture)
    job = answers.invoke('submit', data, fixture.user)['job']
    cancellation = {**address(job), 'idempotency_key': str(uuid.uuid4())}
    first = answers.invoke('cancel', cancellation, fixture.user)
    assert first['job']['status'] == 'cancelled' and first['job']['budget']['cancellation_requested']
    assert answers.invoke('cancel', cancellation, fixture.user) == first
    assert answers.execute_delivery(**delivery(fixture, job))['job']['status'] == 'cancelled'
    assert fixture.service.invoke('status', fixture.address(run), fixture.user)['run']['status'] == 'completed'
    with pytest.raises(ResearchAnswerError, match='conflicts'):
        answers.invoke('cancel', {**cancellation, 'idempotency_key': data['idempotency_key']}, fixture.user)


def test_current_owner_role_or_policy_revocation_cannot_reopen_answer(actual):
    fixture, _, answers = service(actual)
    run, data = request(fixture)
    job = answers.invoke('submit', data, fixture.user)['job']
    answers.execute_delivery(**delivery(fixture, job))
    for user in (fixture.retained.other, fixture.retained.admin):
        with pytest.raises(ResearchAnswerError) as error:
            answers.invoke('status', address(job), user)
        assert error.value.status_code == 404
    fixture.retained.policy[run['context']['binding']['snapshot_id']].add('withdrawn-source-policy')
    with pytest.raises(ResearchAnswerError) as error:
        answers.invoke('status', address(job), fixture.user)
    assert error.value.status_code == 403
    with fixture.retained.factory() as session:
        saved = session.scalar(select(ResearchAnswer).where(ResearchAnswer.job_id == uuid.UUID(job['id'])))
        assert saved is not None and json.loads(saved.answer_json)['id']


SELECTION = {'version': 'c21-selection-v1', 'blocks': []}


def model_request(actual, actions=(SELECTION,), *, status='completed', before=None, repaired_source=False):
    fixture, evidence, answers = service(actual)
    identity = fixture.retained.dataset_ids['ctd']
    fixture.state['runtime'] = FakeRuntime((['malformed'] if repaired_source else []) +
                                           [tool('catalogue.open', object_id=identity, include_details=True)])
    run = evidence_fixtures.finished(fixture, f'Find dataset "{identity}"')
    answers.runtime, answers.model = FakeRuntime(actions, status=status, before=before), 'c21-fake'
    answers.runtime_identity = {'fixture': 'c21-explicit-local'}
    data = {**fixture.address(run), 'input_version': 1, 'locale': 'ja', 'idempotency_key': str(uuid.uuid4())}
    job = answers.invoke('submit', data, fixture.user)['job']
    return fixture, evidence, answers, job


def test_actual_model_answer_uses_host_facts_and_retains_raw_generation(actual):
    fixture, _, answers, job = model_request(actual)
    outcome = answers.execute_delivery(**delivery(fixture, job))['job']
    assert outcome['status'] == 'completed' and outcome['answer']['model_used']
    assert outcome['answer']['locale'] == 'ja' and outcome['answer']['blocks']
    assert outcome['budget']['model_calls'] == job['budget']['model_calls'] + 1
    assert len(answers.runtime.calls) == 1
    assert answers.execute_delivery(**delivery(fixture, job))['job'] == outcome
    assert len(answers.runtime.calls) == 1


@pytest.mark.parametrize('committed', [False, True])
def test_uncertain_model_attempt_charges_but_committed_attempt_replays(actual, monkeypatch, committed):
    fixture, _, answers, job = model_request(actual, actions=(SELECTION, SELECTION))
    original = answers._effect
    crashed = []

    def effect(lease, step_id, kind, request, limits, callback):
        def interrupted(remaining):
            result = callback(remaining)
            if not committed and not crashed:
                crashed.append(True)
                raise RuntimeError('Synthetic lost physical response')
            return result
        result = original(lease, step_id, kind, request, limits, interrupted)
        if committed and not crashed:
            crashed.append(True)
            raise RuntimeError('Synthetic lost committed acknowledgement')
        return result

    monkeypatch.setattr(answers, '_effect', effect)
    with pytest.raises(RuntimeError, match='Synthetic lost'):
        answers.execute_delivery(**delivery(fixture, job))
    fixture.clock.advance(6)
    monkeypatch.setattr(answers, '_effect', original)
    outcome = answers.execute_delivery(**delivery(fixture, job))['job']
    assert outcome['status'] == 'completed'
    assert len(answers.runtime.calls) == (1 if committed else 2)
    assert outcome['budget']['model_calls'] == job['budget']['model_calls'] + (1 if committed else 2)
    assert outcome['active_elapsed_ms'] >= job['active_elapsed_ms'] + 6000
    with fixture.retained.factory() as session:
        attempts = session.scalars(select(ResearchAnswerAttempt).where(ResearchAnswerAttempt.job_id == uuid.UUID(job['id']))).all()
        assert len(attempts) == (1 if committed else 2)


def test_completed_malformed_selection_uses_only_one_remaining_repair(actual):
    fixture, _, answers, job = model_request(actual, actions=('malformed', SELECTION))
    outcome = answers.execute_delivery(**delivery(fixture, job))['job']
    assert outcome['status'] == 'completed'
    assert outcome['budget']['malformed_repairs'] == 1
    assert outcome['budget']['model_calls'] == job['budget']['model_calls'] + 2
    assert len(answers.runtime.calls) == 2


def test_c20_spent_repair_is_not_reset_for_c21(actual):
    fixture, _, answers, job = model_request(actual, actions=('malformed', SELECTION), repaired_source=True)
    assert job['budget']['malformed_repairs'] == 1
    outcome = answers.execute_delivery(**delivery(fixture, job))['job']
    assert outcome['status'] == 'unavailable' and outcome['answer'] is None
    assert outcome['budget']['malformed_repairs'] == 1 and len(answers.runtime.calls) == 1


@pytest.mark.parametrize('status', ['output_limited', 'refused', 'unknown', 'failed'])
def test_incomplete_generation_never_becomes_an_answer_or_repair(actual, status):
    fixture, _, answers, job = model_request(actual, status=status)
    outcome = answers.execute_delivery(**delivery(fixture, job))['job']
    assert outcome['status'] == 'unavailable' and outcome['answer'] is None
    assert outcome['budget']['malformed_repairs'] == job['budget']['malformed_repairs']
    assert len(answers.runtime.calls) == 1


def test_cancellation_during_model_call_fences_late_publication(actual):
    fixture, _, answers, job = model_request(actual)
    answers.runtime.before = lambda _: answers.invoke('cancel', {**address(job), 'idempotency_key': str(uuid.uuid4())}, fixture.user)
    with pytest.raises(ResearchAnswerError) as failure:
        answers.execute_delivery(**delivery(fixture, job))
    assert failure.value.code == 'lease_lost'
    outcome = answers.invoke('status', address(job), fixture.user)['job']
    assert outcome['status'] == 'cancelled' and outcome['answer'] is None
    assert outcome['budget']['model_calls'] == job['budget']['model_calls'] + 1


@pytest.mark.parametrize('backwards', [False, True])
def test_expired_or_backwards_clock_cannot_publish_and_cannot_reset_budget(actual, backwards):
    fixture, _, answers, job = model_request(actual)
    answers.runtime.before = lambda _: fixture.clock.advance(-1 if backwards else 181)
    if backwards:
        outcome = answers.execute_delivery(**delivery(fixture, job))['job']
    else:
        with pytest.raises(ResearchAnswerError) as failure:
            answers.execute_delivery(**delivery(fixture, job))
        assert failure.value.code == 'lease_lost'
        outcome = answers.execute_delivery(**delivery(fixture, job))['job']
    assert outcome['status'] == 'unavailable' and outcome['answer'] is None
    assert outcome['active_elapsed_ms'] == 180000
    assert len(answers.runtime.calls) == 1


def test_waiting_in_queue_is_not_active_time_and_synthesis_toggle_keeps_reads(actual):
    fixture, _, answers = service(actual)
    _, data = request(fixture)
    job = answers.invoke('submit', data, fixture.user)['job']
    fixture.clock.advance(3600)
    answers.synthesis_enabled = lambda: False
    assert answers.invoke('status', address(job), fixture.user)['job']['active_elapsed_ms'] == job['active_elapsed_ms']
    with pytest.raises(ResearchAnswerError):
        answers.invoke('submit', {**data, 'idempotency_key': str(uuid.uuid4())}, fixture.user)
    answers.synthesis_enabled = lambda: True
    outcome = answers.execute_delivery(**delivery(fixture, job))['job']
    assert outcome['status'] == 'completed' and outcome['active_elapsed_ms'] < 180000


@pytest.mark.parametrize('backwards', [False, True])
def test_final_authorization_clock_is_charged_before_any_answer_publication(actual, monkeypatch, backwards):
    fixture, _, answers = service(actual)
    _, data = request(fixture)
    job = answers.invoke('submit', data, fixture.user)['job']
    original = answers._access_revision

    def last_callback(actor, run):
        value = original(actor, run)
        fixture.clock.advance(-1 if backwards else 181)
        return value

    monkeypatch.setattr(answers, '_access_revision', last_callback)
    outcome = answers.execute_delivery(**delivery(fixture, job))['job']
    assert outcome['status'] == 'unavailable' and outcome['answer'] is None
    assert outcome['active_elapsed_ms'] == 180000
    with fixture.retained.factory() as session:
        assert not session.scalars(select(ResearchAnswer).where(ResearchAnswer.job_id == uuid.UUID(job['id']))).all()


def test_only_exact_persisted_submit_replay_survives_synthesis_pause(actual):
    fixture, _, answers = service(actual)
    _, data = request(fixture)
    job = answers.invoke('submit', data, fixture.user)['job']
    answers.synthesis_enabled = lambda: False
    answers.queue = None
    assert answers.invoke('submit', data, fixture.user, allow_new_submit=False)['job'] == job
    with pytest.raises(ResearchAnswerError) as failure:
        answers.invoke('submit', {**data, 'idempotency_key': str(uuid.uuid4())}, fixture.user, allow_new_submit=False)
    assert failure.value.code == 'synthesis_unavailable'
    assert answers.invoke('cancel', {**address(job), 'idempotency_key': str(uuid.uuid4())}, fixture.user)['job']['status'] == 'cancelled'
