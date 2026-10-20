"""C21 separately durable answer jobs; C20 terminal rows are never rewritten."""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from datetime import timedelta
import hashlib
import json
import math
from pathlib import Path
import uuid

from sqlalchemy import func, select

import config
from db.app_models import (
    ResearchAnswer, ResearchAnswerAttempt, ResearchAnswerEvent, ResearchAnswerInputHistory,
    ResearchAnswerJob, ResearchAnswerOutbox, ResearchAnswerPayload, ResearchAnswerStep, ResearchRun, ResearchRunManifest,
)
from model_runtime import GenerationError, GenerationResult
from orchestration.research_runs import ResearchRunError, _utc
from schema.context_catalogue import canonical_json
from schema.research_controller import ControllerLimits, canonical_hash
from schema.research_evidence import ANSWER_REQUEST_MODELS, ANSWER_RESPONSE_MODELS, RenderedAnswer

TERMINAL = frozenset({'completed', 'partial', 'cancelled', 'failed', 'unavailable'})
TEXT = {
    'accepted': ('Answer requested', '回答を依頼しました'),
    'started': ('Preparing retained evidence', '保持された根拠を準備しています'),
    'progress': ('Evidence preparation advanced', '根拠の準備が進みました'),
    'completed': ('Traceable answer ready', '出典付きの回答を準備しました'),
    'partial': ('Partial answer ready; limitations remain', '制限事項を含む部分的な回答を準備しました'),
    'cancelled': ('Answer preparation cancelled', '回答の準備をキャンセルしました'),
    'failed': ('Answer preparation failed', '回答を準備できませんでした'),
    'unavailable': ('Answer preparation is unavailable; retained evidence remains', '回答の準備を利用できません。保持された根拠は残ります'),
}


def _text(kind):
    en, ja = TEXT[kind]
    return {'en': en, 'ja': ja}


class ResearchAnswerError(Exception):
    def __init__(self, code='answers_unavailable', status_code=503):
        self.code, self.status_code = code, status_code
        self.message = {
            'authentication_required': 'Authentication is required', 'access_denied': 'Answer access is denied',
            'not_found': 'Answer was not found', 'invalid_request': 'Answer request is invalid',
            'conflict': 'Answer request conflicts with retained work', 'budget_exhausted': 'The shared research budget is exhausted',
            'integrity_error': 'Retained answer could not be verified', 'lease_lost': 'Answer preparation lease is no longer current',
            'synthesis_unavailable': 'New answer preparation is unavailable',
        }.get(code, 'Answer history is unavailable')
        super().__init__(self.message)


@dataclass(frozen=True)
class AnswerLease:
    job_id: str
    epoch: int


class FakeAnswerQueue:
    """Explicit synthetic-test adapter; never selected as a runtime fallback."""
    def __init__(self):
        self.deliveries = []

    def enqueue(self, *, job_id, delivery_id):
        self.deliveries.append({'job_id': str(job_id), 'delivery_id': str(delivery_id)})


class ResearchAnswerService:
    def __init__(self, *, evidence, queue=None, runtime=None, model=None, runtime_identity=None,
                 documentary_provider=None, enabled=None, synthesis_enabled=None, lease_seconds=180):
        from orchestration.research_evidence import ResearchEvidenceService
        if not isinstance(evidence, ResearchEvidenceService) or not evidence.site_id.startswith('v1:'):
            raise ValueError('Explicit independent v1 evidence service required')
        if queue is not None and not callable(getattr(queue, 'enqueue', None)):
            raise ValueError('Explicit answer queue required')
        if runtime is not None and (not callable(getattr(runtime, 'structured_chat_result', None)) or not model):
            raise ValueError('Explicit completed-generation runtime/model required')
        if documentary_provider is not None and not callable(getattr(documentary_provider, 'search', None)):
            raise ValueError('Explicit frozen documentary provider required')
        if documentary_provider is not None and evidence.documentary_provider is not documentary_provider:
            raise ValueError('Documentary generation and retention require the same explicit provider')
        if type(lease_seconds) not in (int, float) or not math.isfinite(lease_seconds) or not 0 < lease_seconds <= 180:
            raise ValueError('Answer lease must be bounded by research limit')
        self.evidence, self.runs, self.investigations = evidence, evidence.runs, evidence.investigations
        self.session_factory, self.site_id = evidence.session_factory, evidence.site_id
        self.queue, self.runtime, self.model = queue, runtime, model
        self.runtime_identity, self.documentary_provider = runtime_identity, documentary_provider
        self.enabled = enabled if enabled is not None else config.v1_evidence_enabled
        self.synthesis_enabled = synthesis_enabled if synthesis_enabled is not None else config.v1_synthesis_enabled
        self.lease_seconds = float(lease_seconds)

    @property
    def dispatch_available(self):
        return self.queue is not None

    @contextmanager
    def _transaction(self):
        with self.session_factory() as session:
            with session.begin():
                yield session

    def _enabled(self, *, dispatch=False):
        try:
            if self.enabled() is not True:
                raise ResearchAnswerError()
            if dispatch and (self.synthesis_enabled() is not True or not self.dispatch_available):
                raise ResearchAnswerError('synthesis_unavailable')
        except ResearchAnswerError:
            raise
        except Exception:
            raise ResearchAnswerError() from None

    def _actor(self, session, *, user=None, owner_id=None):
        try:
            actor = self.runs._principal(session, user=user, owner_id=owner_id)
        except ResearchRunError as exc:
            raise ResearchAnswerError(exc.code, exc.status_code) from None
        self.investigations._retention_lock(session)
        return actor

    def _source(self, session, actor, data, *, active=False):
        run = session.scalar(select(ResearchRun).where(
            ResearchRun.id == uuid.UUID(str(data['run_id'])), ResearchRun.user_id == actor.id,
            ResearchRun.investigation_id == uuid.UUID(str(data['investigation_id'])),
            ResearchRun.conversation_id == uuid.UUID(str(data['conversation_id'])),
        ).with_for_update().execution_options(populate_existing=True))
        if run is None:
            raise ResearchAnswerError('not_found', 404)
        try:
            self.runs._check_context(run, actor, require_active=active, session=session)
        except ResearchRunError as exc:
            raise ResearchAnswerError(exc.code, exc.status_code) from None
        return run

    @staticmethod
    def _address(job):
        return {key: str(getattr(job, key)) for key in ('run_id', 'investigation_id', 'conversation_id')}

    def _owned(self, session, actor, data, *, active=False):
        job = session.scalar(select(ResearchAnswerJob).where(
            ResearchAnswerJob.id == uuid.UUID(str(data['job_id'])), ResearchAnswerJob.user_id == actor.id,
            ResearchAnswerJob.run_id == uuid.UUID(str(data['run_id'])),
            ResearchAnswerJob.investigation_id == uuid.UUID(str(data['investigation_id'])),
            ResearchAnswerJob.conversation_id == uuid.UUID(str(data['conversation_id'])),
        ).with_for_update())
        if job is None:
            raise ResearchAnswerError('not_found', 404)
        run = self._source(session, actor, data, active=active)
        if job.input_version != run.input_version:
            raise ResearchAnswerError('integrity_error', 409)
        return job, run

    def _public(self, session, job):
        saved = session.scalar(select(ResearchAnswer).where(ResearchAnswer.job_id == job.id))
        answer = None
        if saved is not None:
            if hashlib.sha256(saved.answer_json.encode()).hexdigest() != saved.answer_sha256:
                raise ResearchAnswerError('integrity_error', 409)
            answer = RenderedAnswer.model_validate(json.loads(saved.answer_json)).model_dump(mode='json')
        return self._snapshot(job, answer)

    def _snapshot(self, job, answer):
        return {'id': str(job.id), 'run_id': str(job.run_id), 'input_version': job.input_version,
            'binding': self.runs._binding(job), 'locale': job.locale, 'status': job.status,
            'active_elapsed_ms': job.active_elapsed_ms, 'budget': self._budget(job),
            'event_cursor': 0, 'latest_event_cursor': job.event_cursor, 'activity': [],
            'answer': answer, 'error': _text(job.status) if job.status in {'failed', 'unavailable'} else None,
            'synthetic': False}

    def _access_revision(self, actor, run):
        from orchestration.catalogue_service import catalogue_access_binding
        return canonical_hash({'actor': catalogue_access_binding(actor),
            'policy': self.investigations.catalogue.resolver.resolve(actor, run.snapshot_id).revision,
            'site': self.site_id, 'snapshot_id': run.snapshot_id})

    def _envelope(self, session, actor, job, run):
        return {'version': 'research-answers-v1', 'access_revision': self._access_revision(actor, run),
                'job': self._public(session, job)}

    def _event(self, session, job, kind):
        job.event_cursor += 1
        session.add(ResearchAnswerEvent(job_id=job.id, cursor=job.event_cursor, kind=kind,
            elapsed_ms=job.active_elapsed_ms, summary_json=canonical_json(_text(kind))))

    def _input(self, session, actor, job, kind, data):
        session.add(ResearchAnswerInputHistory(user_id=actor.id, job_id=job.id, kind=kind,
            idempotency_key=data['idempotency_key'], request_json=canonical_json(data), request_sha256=canonical_hash(data)))

    def _replayed(self, session, actor, kind, data):
        old = session.scalar(select(ResearchAnswerInputHistory).where(
            ResearchAnswerInputHistory.user_id == actor.id,
            ResearchAnswerInputHistory.idempotency_key == data['idempotency_key']))
        if old is None:
            return None
        if old.kind != kind or old.request_sha256 != canonical_hash(data) or old.request_json != canonical_json(data):
            raise ResearchAnswerError('conflict', 409)
        job = session.get(ResearchAnswerJob, old.job_id)
        if job is None:
            raise ResearchAnswerError('integrity_error', 409)
        run = self._source(session, actor, self._address(job))
        return self._envelope(session, actor, job, run)

    def invoke(self, name, payload, user, *, allow_new_submit=True):
        self._enabled()
        try:
            data = ANSWER_REQUEST_MODELS[name].model_validate(payload).model_dump(mode='json', exclude_none=True)
        except (KeyError, TypeError, ValueError):
            raise ResearchAnswerError('invalid_request', 422) from None
        try:
            with self._transaction() as session:
                actor = self._actor(session, user=user)
                if name in {'submit', 'cancel'}:
                    old = self._replayed(session, actor, name, data)
                    if old is not None:
                        return ANSWER_RESPONSE_MODELS[name].model_validate(old).model_dump(mode='json')
                if name == 'submit':
                    if allow_new_submit is not True:
                        raise ResearchAnswerError('synthesis_unavailable')
                    self._enabled(dispatch=True)
                    result = self._submit(session, actor, data)
                elif name == 'list':
                    result = self._list(session, actor, data)
                else:
                    job, run = self._owned(session, actor, data)
                    if name == 'events':
                        result = self._events(session, actor, job, run, data)
                    else:
                        if name == 'cancel':
                            if job.status not in TERMINAL:
                                self._settle(session, job)
                                job.cancellation_requested, job.status = True, 'cancelled'
                                job.lease_epoch += 1
                                job.active_started_at = job.lease_until = None
                                job.version += 1
                                self._event(session, job, 'cancelled')
                            self._input(session, actor, job, name, data)
                        result = self._envelope(session, actor, job, run)
                session.flush()
                self.runs._principal(session, user=user)
                return ANSWER_RESPONSE_MODELS[name].model_validate(result).model_dump(mode='json')
        except ResearchRunError as exc:
            raise ResearchAnswerError(exc.code, exc.status_code) from None

    def _limits(self, session, run):
        manifest = session.get(ResearchRunManifest, (run.id, run.input_version))
        if manifest is None or hashlib.sha256(manifest.manifest_json.encode()).hexdigest() != manifest.manifest_sha256:
            raise ResearchAnswerError('integrity_error', 409)
        return ControllerLimits.model_validate(json.loads(manifest.manifest_json)['limits'])

    def _eligible(self, session, run):
        return (run.status in {'completed', 'partial'} and run.controller_result_json is not None
                and not run.cancellation_requested and run.reason_code != 'invalid_clock'
                and run.active_elapsed_ms < self._limits(session, run).active_seconds * 1000)

    def _submit(self, session, actor, data):
        run = self._source(session, actor, data, active=True)
        if run.input_version != data['input_version']:
            raise ResearchAnswerError('conflict', 409)
        prior = session.scalar(select(ResearchAnswerJob).where(
            ResearchAnswerJob.run_id == run.id, ResearchAnswerJob.input_version == run.input_version))
        if prior is not None:
            if prior.locale != data['locale']:
                raise ResearchAnswerError('conflict', 409)
            self._input(session, actor, prior, 'submit', data)
            return self._envelope(session, actor, prior, run)
        if not self._eligible(session, run):
            raise ResearchAnswerError('budget_exhausted' if run.active_elapsed_ms >= 180000 else 'synthesis_unavailable', 409)
        now = self.runs._now(session)
        job = ResearchAnswerJob(user_id=actor.id, run_id=run.id,
            investigation_id=run.investigation_id, conversation_id=run.conversation_id, revision_id=run.revision_id,
            snapshot_id=run.snapshot_id, payload_sha256=run.payload_sha256, input_version=run.input_version,
            locale=data['locale'], idempotency_key=data['idempotency_key'], request_json=canonical_json(data),
            request_sha256=canonical_hash(data), budget_floor_json=canonical_json(self.runs._budget(run)),
            active_elapsed_ms=run.active_elapsed_ms, tool_actions=run.tool_actions, model_calls=run.model_calls,
            malformed_repairs=run.malformed_repairs, status='queued', created_at=now, updated_at=now)
        session.add(job)
        session.flush()
        self._input(session, actor, job, 'submit', data)
        self._event(session, job, 'accepted')
        session.add(ResearchAnswerOutbox(job_id=job.id))
        session.flush()
        return self._envelope(session, actor, job, run)

    def _list(self, session, actor, data):
        run = self._source(session, actor, data)
        if data.get('cursor') is not None:
            raise ResearchAnswerError('invalid_request', 422)  # One canonical job per terminal input version.
        jobs = session.scalars(select(ResearchAnswerJob).where(
            ResearchAnswerJob.run_id == run.id, ResearchAnswerJob.user_id == actor.id,
        ).order_by(ResearchAnswerJob.id).limit(data['limit'])).all()
        eligible = self._eligible(session, run)
        return {'version': 'research-answers-v1', 'access_revision': self._access_revision(actor, run),
            'run_id': str(run.id), 'input_version': run.input_version, 'binding': self.runs._binding(run),
            'eligible': eligible, 'reason': None if eligible else _text('unavailable'),
            'items': [self._public(session, job) for job in jobs], 'next_cursor': None}

    def _events(self, session, actor, job, run, data):
        after = data['after_cursor']
        if after > job.event_cursor:
            raise ResearchAnswerError('conflict', 409)
        rows = session.scalars(select(ResearchAnswerEvent).where(
            ResearchAnswerEvent.job_id == job.id, ResearchAnswerEvent.cursor > after,
        ).order_by(ResearchAnswerEvent.cursor).limit(data['limit'])).all()
        next_cursor = rows[-1].cursor if rows else after
        return {'version': 'research-answers-v1', 'access_revision': self._access_revision(actor, run),
            'job_id': str(job.id), 'binding': self.runs._binding(job), 'after_cursor': after,
            'next_cursor': next_cursor, 'latest_event_cursor': job.event_cursor, 'has_more': next_cursor < job.event_cursor,
            'events': [{'cursor': row.cursor, 'job_id': str(job.id), 'elapsed_ms': row.elapsed_ms,
                        'kind': row.kind, 'summary': json.loads(row.summary_json)} for row in rows]}

    @staticmethod
    def _budget(job):
        return {'active_elapsed_seconds': job.active_elapsed_ms / 1000,
                'tool_actions': job.tool_actions, 'model_calls': job.model_calls,
                'malformed_repairs': job.malformed_repairs, 'cancellation_requested': job.cancellation_requested}

    def _settle(self, session, job):
        now = self.runs._now(session)
        if ((job.updated_at is not None and now < _utc(job.updated_at))
                or (job.active_started_at is not None and now < _utc(job.active_started_at))):
            job.active_elapsed_ms, job.reason_code = 180000, 'invalid_clock'
        if job.active_started_at is not None:
            elapsed = max(0, int((now - _utc(job.active_started_at)).total_seconds() * 1000))
            job.active_elapsed_ms = min(180000, job.active_elapsed_ms + elapsed)
            job.active_started_at = now
        job.updated_at = max(now, _utc(job.updated_at)) if job.updated_at is not None else now
        return now

    def claim(self, job_id, delivery_id):
        self._enabled(dispatch=True)
        with self._transaction() as session:
            head = session.get(ResearchAnswerJob, uuid.UUID(str(job_id)))
            if head is None:
                raise ResearchAnswerError('not_found', 404)
            actor = self._actor(session, owner_id=head.user_id)
            job = session.scalar(select(ResearchAnswerJob).where(ResearchAnswerJob.id == head.id)
                                 .with_for_update().execution_options(populate_existing=True))
            outbox = session.scalar(select(ResearchAnswerOutbox).where(
                ResearchAnswerOutbox.job_id == job.id, ResearchAnswerOutbox.delivery_id == uuid.UUID(str(delivery_id))))
            if outbox is None:
                raise ResearchAnswerError('not_found', 404)
            run = self._source(session, actor, self._address(job), active=job.status not in TERMINAL)
            if job.status in TERMINAL:
                return None
            now = self.runs._now(session)
            if job.status == 'running' and job.lease_until is not None and _utc(job.lease_until) > now:
                return None
            self._settle(session, job)
            maximum = self._limits(session, run).active_seconds * 1000
            if job.reason_code == 'invalid_clock' or job.active_elapsed_ms >= maximum:
                job.status, job.reason_code = 'unavailable', job.reason_code or 'budget_exhausted'
                job.active_started_at = job.lease_until = None
                job.version += 1
                self._event(session, job, 'unavailable')
                return None
            job.status = 'running'
            job.lease_epoch += 1
            job.active_started_at = now
            job.lease_until = now + timedelta(seconds=min(self.lease_seconds, (maximum - job.active_elapsed_ms) / 1000))
            job.version += 1
            self._event(session, job, 'started')
            return AnswerLease(str(job.id), job.lease_epoch)

    def _leased(self, session, lease, *, check_time=True):
        head = session.get(ResearchAnswerJob, uuid.UUID(lease.job_id))
        if head is None:
            raise ResearchAnswerError('not_found', 404)
        actor = self._actor(session, owner_id=head.user_id)
        job = session.scalar(select(ResearchAnswerJob).where(ResearchAnswerJob.id == head.id)
                             .with_for_update().execution_options(populate_existing=True))
        self._enabled(dispatch=True)
        if (job.lease_epoch != lease.epoch or job.status != 'running' or job.cancellation_requested
                or (check_time and (job.lease_until is None or _utc(job.lease_until) <= self.runs._now(session)))):
            raise ResearchAnswerError('lease_lost', 409)
        run = self._source(session, actor, self._address(job), active=True)
        return job, run, actor

    def _bind(self, lease, manifest):
        with self._transaction() as session:
            job, _, _ = self._leased(session, lease)
            value = canonical_json(manifest)
            if job.manifest_json is None:
                job.manifest_json = value
            elif job.manifest_json != value:
                raise ResearchAnswerError('integrity_error', 409)
            floor = manifest['budget_floor']
            job.active_elapsed_ms = min(180000, max(job.active_elapsed_ms, math.ceil(floor['active_elapsed_seconds'] * 1000)))
            for key in ('tool_actions', 'model_calls', 'malformed_repairs'):
                setattr(job, key, max(getattr(job, key), floor[key]))
            self._settle(session, job)

    def fresh_actor(self, lease):
        with self._transaction() as session:
            _, _, actor = self._leased(session, lease)
            return actor

    def _remaining(self, lease, limits):
        with self._transaction() as session:
            job, _, _ = self._leased(session, lease)
            self._settle(session, job)
            remaining = limits.active_seconds - job.active_elapsed_ms / 1000
            if remaining <= 0 or job.reason_code == 'invalid_clock':
                raise ResearchAnswerError('budget_exhausted', 409)
            return remaining

    def _effect(self, lease, step_id, kind, request, limits, callback):
        """Committed lookup precedes reservation; every uncertain physical retry charges."""
        digest = canonical_hash(request)
        with self._transaction() as session:
            job, _, _ = self._leased(session, lease)
            step = session.get(ResearchAnswerStep, (job.id, step_id))
            if step is not None and (step.kind != kind or step.request_sha256 != digest or step.request_json != canonical_json(request)):
                raise ResearchAnswerError('integrity_error', 409)
            if step is not None and step.state == 'committed':
                saved = session.get(ResearchAnswerPayload, (job.id, step.outcome_sha256))
                if saved is None or hashlib.sha256(saved.payload_json.encode()).hexdigest() != saved.sha256:
                    raise ResearchAnswerError('integrity_error', 409)
                return json.loads(saved.payload_json)
            now = self._settle(session, job)
            maximum = limits.active_seconds * 1000
            if job.active_elapsed_ms >= maximum or job.reason_code == 'invalid_clock':
                raise ResearchAnswerError('budget_exhausted', 409)
            counter, cap = {'tool': ('tool_actions', limits.tool_actions),
                            'model': ('model_calls', limits.tool_actions + limits.malformed_repairs + 1),
                            'repair': ('malformed_repairs', limits.malformed_repairs)}[kind]
            reuse_repair = kind == 'repair' and step is not None
            if not reuse_repair:
                if getattr(job, counter) >= cap:
                    raise ResearchAnswerError('budget_exhausted', 409)
                setattr(job, counter, getattr(job, counter) + 1)
            if step is None:
                step = ResearchAnswerStep(job_id=job.id, step_id=step_id, kind=kind,
                    request_json=canonical_json(request), request_sha256=digest, state='prepared')
                session.add(step)
                session.flush()
            ordinal = (session.scalar(select(func.max(ResearchAnswerAttempt.ordinal)).where(
                ResearchAnswerAttempt.job_id == job.id, ResearchAnswerAttempt.step_id == step_id)) or 0) + 1
            attempt_id = uuid.uuid4()
            session.add(ResearchAnswerAttempt(id=attempt_id, job_id=job.id, step_id=step_id,
                ordinal=ordinal, lease_epoch=lease.epoch, budget_json=canonical_json(self._budget(job))))
            job.lease_until = now + timedelta(seconds=min(self.lease_seconds, (maximum - job.active_elapsed_ms) / 1000))
        # No database connection/lock spans a blocking provider operation.
        outcome = callback(self._remaining(lease, limits))
        value, outcome_sha = canonical_json(outcome), canonical_hash(outcome)
        with self._transaction() as session:
            job, _, _ = self._leased(session, lease)
            self._settle(session, job)
            step = session.get(ResearchAnswerStep, (job.id, step_id))
            attempt = session.get(ResearchAnswerAttempt, attempt_id)
            if attempt is None or attempt.lease_epoch != lease.epoch or step.state != 'prepared':
                raise ResearchAnswerError('lease_lost', 409)
            existing = session.get(ResearchAnswerPayload, (job.id, outcome_sha))
            if existing is None:
                session.add(ResearchAnswerPayload(job_id=job.id, sha256=outcome_sha, payload_json=value))
                session.flush()
            elif existing.payload_json != value:
                raise ResearchAnswerError('integrity_error', 409)
            step.state, step.outcome_sha256 = 'committed', outcome_sha
            job.version += 1
            self._event(session, job, 'progress')
        return outcome

    def _finish(self, lease, *, answer=None, reason=None):
        if answer is not None:
            actor = self.fresh_actor(lease)
            for receipt_id in answer.receipt_ids:
                self.evidence.invoke('open', {'receipt_id': receipt_id,
                    'expected_sha256': receipt_id[len('c21:receipt:'):]}, actor)
        with self._transaction() as session:
            job, run, actor = self._leased(session, lease, check_time=answer is not None)
            limits = self._limits(session, run)
            candidate, value, digest = None, None, None
            if answer is not None:
                answer = RenderedAnswer.model_validate(answer.model_dump(mode='json'))
                candidate = answer.model_dump(mode='json')
                value = canonical_json(candidate)
                digest = hashlib.sha256(value.encode()).hexdigest()
            public = self._snapshot(job, candidate)
            # Finish expensive serialization and every current-access callback
            # before the closing clock fence. No candidate has been flushed.
            canonical_json(public)
            fresh = self._actor(session, owner_id=job.user_id)
            self._source(session, fresh, self._address(job), active=True)
            access_revision = self._access_revision(fresh, run)
            now = self._settle(session, job)
            allowed = (job.active_elapsed_ms < limits.active_seconds * 1000 and job.reason_code != 'invalid_clock'
                       and job.lease_until is not None and _utc(job.lease_until) > now)
            if answer is not None and allowed:
                session.add(ResearchAnswer(id=uuid.UUID(answer.id), job_id=job.id, user_id=job.user_id,
                    run_id=job.run_id, answer_json=value, answer_sha256=digest))
                job.status = 'completed' if answer.completion == 'complete' else 'partial'
                job.pack_sha256 = answer.pack_sha256
            else:
                job.status, job.reason_code = 'unavailable', reason or job.reason_code or 'budget_exhausted'
            job.lease_until = job.active_started_at = None
            job.version += 1
            self._event(session, job, job.status)
            # Only scalar DTO updates and local ORM inserts follow the fence.
            public.update(status=job.status, active_elapsed_ms=job.active_elapsed_ms, budget=self._budget(job),
                          latest_event_cursor=job.event_cursor,
                          answer=candidate if answer is not None and allowed else None,
                          error=_text(job.status) if job.status in {'failed', 'unavailable'} else None)
            return {'version': 'research-answers-v1', 'access_revision': access_revision, 'job': public}

    def execute_delivery(self, job_id, delivery_id):
        from orchestration.research_controller_replay import ReplayIntegrityError
        from orchestration.research_evidence import ResearchEvidenceError
        lease = self.claim(job_id, delivery_id)
        if lease is None:
            with self._transaction() as session:
                job = session.get(ResearchAnswerJob, uuid.UUID(str(job_id)))
                actor = self._actor(session, owner_id=job.user_id)
                run = self._source(session, actor, self._address(job))
                return self._envelope(session, actor, job, run)
        try:
            return self._execute_leased(lease)
        except ResearchEvidenceError:
            # Publication of an unavailable state still rechecks the current
            # owner, source context and epoch; revoked access cannot publish.
            return self._finish(lease, reason='evidence_unavailable')
        except ReplayIntegrityError:
            return self._finish(lease, reason='integrity_error')
        except ResearchAnswerError as exc:
            if exc.code in {'budget_exhausted', 'integrity_error'}:
                return self._finish(lease, reason=exc.code)
            raise

    def _execute_leased(self, lease):
        from orchestration.research_synthesis import (
            SynthesisInvalid, build_selection_request, build_synthesis_pack, deterministic_selection,
            parse_generation, render_selection,
        )
        from orchestration.research_controller_replay import generation_payload, restore_generation, runtime_fingerprint
        actor = self.fresh_actor(lease)
        with self._transaction() as session:
            job, _, _ = self._leased(session, lease)
            run_id, input_version, locale = str(job.run_id), job.input_version, job.locale
        verified = self.evidence.ensure_retained(run_id=run_id, input_version=input_version, user=actor)
        anchor = verified.anchor
        limits = anchor.limits
        manifest = {'version': 'c21-synthesis-execution-v1', 'run_id': run_id, 'input_version': input_version,
            'engine_fingerprint': canonical_hash({name: hashlib.sha256((Path(__file__).parents[1] / name).read_bytes()).hexdigest()
                for name in ('orchestration/research_answers.py', 'orchestration/research_synthesis.py',
                             'orchestration/frozen_documentary.py', 'schema/research_evidence.py')}),
            'binding': anchor.binding.model_dump(mode='json'), 'locale': locale,
            'controller_result_sha256': anchor.controller_result_sha256, 'scope_witness_sha256': anchor.scope_witness_sha256,
            'receipt_ids': [r.id for r in verified.receipts], 'attached_receipt_ids': [r.id for r in verified.attached_receipts],
            'limits': limits.model_dump(mode='json'), 'model': self.model,
            'budget_floor': anchor.run_budget_high_water.model_dump(mode='json'),
            'runtime': runtime_fingerprint(self.runtime, self.runtime_identity) if self.runtime is not None else None,
            'documentary': self.documentary_provider.identity if self.documentary_provider is not None else None,
            'actor_binding': anchor.actor_binding, 'catalogue_policy_revision': anchor.catalogue_policy_revision}
        self._bind(lease, manifest)
        try:
            self._remaining(lease, limits)
            pack = build_synthesis_pack(verified)
            selection = deterministic_selection(pack)
            documentary = None
            if selection is None and self.documentary_provider is not None:
                request = {'query': anchor.effective_question, 'binding': anchor.binding.model_dump(mode='json'),
                    'scope': anchor.effective_scope.model_dump(mode='json'), 'input_sha256': canonical_hash(verified.input_manifests_by_receipt),
                    'limit': 8, 'expected_policy_revision': anchor.catalogue_policy_revision}
                def search(remaining):
                    return self.documentary_provider.search(query=anchor.effective_question, binding=anchor.binding,
                        effective_scope=anchor.effective_scope,
                        permitted_input_manifest=[row for values in verified.input_manifests_by_receipt.values() for row in values],
                        current_actor=self.fresh_actor(lease), expected_policy_revision=anchor.catalogue_policy_revision,
                        limit=8, remaining_timeout=remaining)
                raw = self._effect(lease, 'documentary:1', 'tool', request, limits, search)
                receipt = self.evidence.retain_documentary(run_id=run_id, input_version=input_version,
                    payload=raw, user=self.fresh_actor(lease), remaining_timeout=self._remaining(lease, limits))
                documentary = [(receipt, raw)]
                pack = build_synthesis_pack(verified, documentary=documentary)
                selection = deterministic_selection(pack)
            model_used = selection is None
            if selection is None:
                if self.runtime is None or not self.model:
                    return self._finish(lease, reason='runtime_unavailable')
                for index in range(2):
                    request = build_selection_request(pack, repair=index == 1)
                    request['model'] = self.model
                    def generate(remaining):
                        try:
                            result = self.runtime.structured_chat_result(model=self.model, prompt=request['prompt'],
                                schema=request['schema'], max_output_tokens=request['max_output_tokens'],
                                timeout=max(0.001, remaining))
                        except GenerationError as exc:
                            result = exc.result
                        if not isinstance(result, GenerationResult):
                            raise ResearchAnswerError('integrity_error', 409)
                        return generation_payload(result)
                    raw = self._effect(lease, f'synthesis:{index + 1}', 'model', request, limits, generate)
                    generation = restore_generation(raw)
                    try:
                        selection = parse_generation(generation, pack)
                        break
                    except GenerationError:
                        return self._finish(lease, reason='generation_incomplete')
                    except SynthesisInvalid:
                        if index:
                            return self._finish(lease, reason='invalid_selection')
                        self._effect(lease, 'selection:repair', 'repair', {'pack_sha256': pack.sha256}, limits,
                                     lambda _remaining: {'repair_reserved': True})
            answer = render_selection(selection, pack, locale, model_used=model_used)
            return self._finish(lease, answer=answer)
        except ResearchAnswerError as exc:
            if exc.code == 'budget_exhausted':
                return self._finish(lease, reason='budget_exhausted')
            raise
        except SynthesisInvalid:
            return self._finish(lease, reason='evidence_pack_unavailable')

    def dispatch_outbox(self):
        self._enabled(dispatch=True)
        with self._transaction() as session:
            ids = list(session.scalars(select(ResearchAnswerOutbox.id).where(ResearchAnswerOutbox.state == 'pending').order_by(ResearchAnswerOutbox.id)))
        count = 0
        for identity in ids:
            self._enabled(dispatch=True)
            with self._transaction() as session:
                row = session.get(ResearchAnswerOutbox, identity)
                if row.state != 'pending':
                    continue
                job = session.get(ResearchAnswerJob, row.job_id)
                actor = self._actor(session, owner_id=job.user_id)
                if job.status not in {'queued', 'running'}:
                    continue
                self._source(session, actor, self._address(job), active=True)
                job_id, delivery_id = str(job.id), str(row.delivery_id)
                row.attempts += 1
            self.queue.enqueue(job_id=job_id, delivery_id=delivery_id)
            with self._transaction() as session:
                row = session.get(ResearchAnswerOutbox, identity)
                row.state, row.sent_at = 'sent', self.runs._now(session)
            count += 1
        return count
