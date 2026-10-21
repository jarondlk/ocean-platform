"""C22 immutable private proposals, explicit approval and bounded fake dispatch.

No code is executed here. Independent source protection is prepared before
export; uncertain delivery retains both its immutable identity and capacity.
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import threading
import uuid

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

import config
from api.auth import CurrentUser, current_user_from_model
from db.app_models import (
    AppUser, ResearchContextRevision, ResearchConversation, ResearchExperiment,
    ResearchExperimentApproval, ResearchExperimentCapacity, ResearchExperimentEvent,
    ResearchExperimentInputBlob, ResearchExperimentOperation, ResearchExperimentOutbox,
    ResearchExperimentReservation, ResearchExperimentRevision, ResearchExperimentRevisionFile,
    ResearchInvestigation,
)
from ingestion.catalogue_snapshot import SnapshotCommitUncertain
from orchestration.investigations import InvestigationError, InvestigationService
from schema.context_catalogue import canonical_json
from schema.research_experiments import (
    EXPERIMENT_REQUEST_MODELS, EXPERIMENT_RESPONSE_MODELS, EnvironmentDescriptor,
    ExperimentProposal, MAX_INPUT_BYTES, content_sha256,
)

HASH_FIELDS = ('proposal_sha256', 'code_sha256', 'input_manifest_sha256', 'environment_sha256', 'resources_sha256')
MAX_MANIFEST_BYTES = 4 * 1024 * 1024
MAX_LIST_BYTES = 8 * 1024 * 1024 - 4096
OPERATION_REASONS = {
    'conflict': ('The proposal or context changed; prepare a new revision', '計画またはコンテキストが変更されました。新しい版を準備してください'),
    'protection_uncertain': ('Source protection acknowledgement is uncertain; retained references were not released', '原資料の保護確認が不確定です。保持参照は解除していません'),
    'commit_uncertain': ('Storage acknowledgement is uncertain; retry reconciles this same operation', '保存確認が不確定です。再試行で同じ処理を照合します'),
    'export_unavailable': ('The frozen export is unavailable; retained preparation remains', '固定入力の書き出しを利用できません。準備情報は保持しています'),
    'export_publication_unavailable': ('An exact current source publication decision is missing or withdrawn', '原資料の正確な現行公開判断がないか、取り消されています'),
    'export_publication_changed': ('The source publication decision changed; review a new revision', '原資料の公開判断が変更されました。新しい版を確認してください'),
    'export_input_size_exceeded': ('Frozen inputs exceed the declared byte limit; narrow the proposal', '固定入力が指定容量を超えています。計画の対象を絞ってください'),
    'export_access_changed': ('Current source access or scope changed', '原資料のアクセス権または範囲が変更されました'),
    'export_integrity': ('Frozen source identities or bytes could not be verified', '固定された原資料の識別子またはバイトを検証できません'),
    'export_complete_table_required': ('A complete source table is required; previews cannot supply experiment inputs', '完全な原資料テーブルが必要です。プレビューは実験入力にできません'),
    'export_unsupported_pin': ('A pinned restriction cannot be applied exactly', '固定条件を正確に適用できません'),
    'export_target_unavailable': ('A selected source is unavailable in this context', '選択した原資料はこのコンテキストで利用できません'),
    'export_table_unavailable': ('A selected source table is unavailable', '選択した原資料テーブルを利用できません'),
    'export_unknown_column': ('A requested column is unavailable in the selected table', '要求した列は選択したテーブルで利用できません'),
    'export_physical_pairing_unavailable': ('The requested physical pairing lacks a verified identity relationship', '要求した物理的対応に検証済みの同一性関係がありません'),
    'export_exclusion_outside_cohort': ('An excluded identity is outside the selected cohort', '除外対象の識別子は選択範囲に含まれていません'),
    'export_exclusion_target_unavailable': ('An exclusion does not identify an available source entity', '除外条件が利用可能な原資料の要素を特定していません'),
    'export_non_lossless_value': ('An input value cannot be represented without loss', '入力値を損失なく表現できません'),
    'export_invalid_table': ('The requested machine table is not valid', '要求した機械可読テーブルが無効です'),
    'export_publication_pin_requires_exact_table': ('The publication pin requires its exact published table', '公開結果の固定条件には正確な公開テーブルが必要です'),
    'export_publication_question_unsupported': ('The question is incompatible with the selected published result', '質問が選択した公開結果の適用範囲と一致しません'),
    'export_published_rows_cannot_be_recomputed': ('Published result rows cannot be reinterpreted as a recomputed cohort', '公開結果の行を再計算した対象集団として解釈し直すことはできません'),
}
TEXT = {
    'created': ('Experiment proposal prepared; Python was not executed', '実験計画を準備しました。Pythonは実行していません'),
    'revised': ('Experiment proposal revised; review is required', '実験計画を改訂しました。再確認が必要です'),
    'approved': ('Owner approved this exact experimental revision', '所有者がこの実験計画の版を承認しました'),
    'reserved': ('Fake dispatch reserved; Python was not executed', '模擬配送を予約しました。Pythonは実行していません'),
    'accepted': ('Fake dispatch acknowledged; Python was not executed', '模擬配送を確認しました。Pythonは実行していません'),
}


def _hash(value):
    return hashlib.sha256(value).hexdigest()


def _uuid(value):
    return uuid.UUID(str(value))


class ResearchExperimentError(Exception):
    def __init__(self, code='experiments_unavailable', status_code=503, message=None):
        self.code, self.status_code = code, status_code
        self.message = message or {
            'authentication_required': 'Authentication is required',
            'access_denied': 'Experiment access is denied',
            'not_found': 'Experiment was not found',
            'invalid_request': 'Experiment request is invalid',
            'conflict': 'Experiment review has changed',
            'integrity_error': 'Frozen experiment could not be verified',
            'capacity_unavailable': 'Experiment capacity is reserved',
            'environment_unavailable': 'The exact environment is not configured',
            'dispatch_unavailable': 'Experimental dispatch is unavailable',
        }.get(code, 'Experiment preparation is unavailable')
        super().__init__(self.message)


class FakeExperimentExecutor:
    """Explicit local acceptance adapter, with stable delivery deduplication.

    This object cannot interpret Python or return scientific outputs. Accepted
    deliveries keep reservations active until a later trusted execution boundary
    can establish termination. It is never a default runtime fallback.
    """
    kind = 'c22-fake'

    def __init__(self):
        self.deliveries = []
        self._receipts, self._lock = {}, threading.Lock()

    def enqueue(self, *, envelope, delivery_id):
        with self._lock:
            metadata = envelope['metadata']
            identity = content_sha256(metadata)
            if metadata['environment']['kind'] != self.kind or metadata['environment']['test_only'] is not True:
                raise ValueError('Only an explicit non-executing fake environment is supported')
            previous = self._receipts.get(str(delivery_id))
            if previous is not None:
                if previous['envelope_sha256'] != identity:
                    raise ValueError('Delivery identity cannot change')
                return dict(previous)
            receipt = {'kind': self.kind, 'delivery_id': str(delivery_id),
                'reservation_id': metadata['reservation_id'], 'envelope_sha256': identity,
                'accepted': True, 'execution_performed': False}
            self.deliveries.append({'delivery_id': str(delivery_id), 'metadata': json.loads(canonical_json(metadata))})
            self._receipts[str(delivery_id)] = receipt
            return dict(receipt)


class ResearchExperimentService:
    def __init__(self, *, session_factory, site_id, investigations, exporter, environments,
                 executor=None, enabled=None, dispatch_enabled=None):
        from orchestration.frozen_experiment_export import FrozenExperimentExporter
        if (not isinstance(investigations, InvestigationService) or session_factory is not investigations.session_factory
                or site_id != investigations.site_id or not site_id.startswith('v1:')):
            raise ValueError('Explicit matching independent investigation store required')
        if not isinstance(exporter, FrozenExperimentExporter):
            raise ValueError('Explicit frozen experiment exporter required')
        if exporter.catalogue is not investigations.catalogue or exporter.store is not investigations.store:
            raise ValueError('Exporter and investigation scientific sources must match')
        if executor is not None and (not isinstance(executor, FakeExperimentExecutor) or executor.kind != 'c22-fake'):
            raise ValueError('C22 accepts only the explicit non-executing fake adapter')
        parsed = {}
        for identity, descriptor in dict(environments).items():
            item = EnvironmentDescriptor.model_validate(descriptor)
            if identity != item.identity_sha256:
                raise ValueError('Environment registry must use exact descriptor identities')
            parsed[identity] = item.model_dump(mode='json')
        self.session_factory, self.site_id = session_factory, site_id
        self.investigations, self.exporter = investigations, exporter
        self.environments, self.executor = parsed, executor
        self.enabled = enabled if enabled is not None else config.v1_experiments_enabled
        self.dispatch_enabled = dispatch_enabled if dispatch_enabled is not None else config.v1_experiment_dispatch_enabled

    @property
    def dispatch_available(self):
        return isinstance(self.executor, FakeExperimentExecutor) and self.executor.kind == 'c22-fake'

    @contextmanager
    def _transaction(self):
        with self.session_factory() as session:
            with session.begin():
                yield session

    def _require_enabled(self, *, dispatch=False):
        try:
            if self.enabled() is not True:
                raise ResearchExperimentError()
            if dispatch and (self.dispatch_enabled() is not True or not self.dispatch_available):
                raise ResearchExperimentError('dispatch_unavailable')
        except ResearchExperimentError:
            raise
        except Exception:
            raise ResearchExperimentError() from None

    def _actor(self, session, *, user=None, owner_id=None):
        if user is not None and not isinstance(user, CurrentUser):
            raise ResearchExperimentError('authentication_required', 401)
        identity = user.id if user is not None else owner_id
        if identity is None:
            raise ResearchExperimentError('authentication_required', 401)
        current = session.scalar(select(AppUser).where(AppUser.id == identity)
            .with_for_update(key_share=True).execution_options(populate_existing=True))
        if current is None:
            raise ResearchExperimentError('access_denied', 403)
        actor = current_user_from_model(current)
        if actor.status != 'active' or actor.role not in {'researcher', 'admin'} or not {'chat:use', 'data:read', 'data:export'} <= actor.permissions:
            raise ResearchExperimentError('access_denied', 403)
        if user is not None and any(getattr(actor, key) != getattr(user, key) for key in (
                'id', 'email', 'role', 'status', 'account_type', 'auth_provider', 'permissions')):
            raise ResearchExperimentError('access_denied', 403)
        self.investigations._retention_lock(session)
        return actor

    def _investigation(self, session, actor, investigation_id, *, active=False):
        item = session.scalar(select(ResearchInvestigation).where(
            ResearchInvestigation.id == _uuid(investigation_id), ResearchInvestigation.user_id == actor.id)
            .with_for_update().execution_options(populate_existing=True))
        if item is None or item.status in {'preparing', 'retired'}:
            raise ResearchExperimentError('not_found', 404)
        if active and item.status != 'active':
            raise ResearchExperimentError('conflict', 409)
        return item

    def _context(self, session, actor, data, *, active=False):
        item = self._investigation(session, actor, data['investigation_id'], active=active)
        conversation = session.scalar(select(ResearchConversation).where(
            ResearchConversation.id == _uuid(data['conversation_id']), ResearchConversation.investigation_id == item.id))
        revision = session.scalar(select(ResearchContextRevision).where(
            ResearchContextRevision.id == _uuid(data['context_revision_id']), ResearchContextRevision.investigation_id == item.id))
        if conversation is None or revision is None:
            raise ResearchExperimentError('not_found', 404)
        if (revision.snapshot_id != data['snapshot_id'] or revision.payload_sha256 != data['context_payload_sha256']
                or _hash(revision.payload_json.encode('utf-8')) != revision.payload_sha256):
            raise ResearchExperimentError('conflict', 409)
        if active and item.head_revision_id != revision.id:
            raise ResearchExperimentError('conflict', 409)
        payload = json.loads(revision.payload_json)
        try:
            resolution, _ = self.investigations._resolve(payload, actor)
        except InvestigationError as exc:
            raise ResearchExperimentError('access_denied' if exc.status_code in {403, 404} else 'experiments_unavailable',
                403 if exc.status_code in {403, 404} else 503) from None
        if any(value['status'] != 'available' for value in resolution):
            raise ResearchExperimentError('access_denied', 403)
        return {'investigation_id': str(item.id), 'conversation_id': str(conversation.id),
            'revision_id': str(revision.id), 'snapshot_id': revision.snapshot_id,
            'payload_sha256': revision.payload_sha256, 'context': payload}

    @staticmethod
    def _binding(revision):
        return {'investigation_id': str(revision.investigation_id), 'conversation_id': str(revision.conversation_id),
            'context_revision_id': str(revision.context_revision_id), 'snapshot_id': revision.snapshot_id,
            'context_payload_sha256': revision.payload_sha256}

    def _owned(self, session, actor, experiment_id):
        # The investigation precedes head locks everywhere (including retirement).
        candidate = session.scalar(select(ResearchExperiment).where(
            ResearchExperiment.id == _uuid(experiment_id), ResearchExperiment.user_id == actor.id))
        if candidate is None:
            raise ResearchExperimentError('not_found', 404)
        self._investigation(session, actor, candidate.investigation_id)
        return session.scalar(select(ResearchExperiment).where(ResearchExperiment.id == candidate.id)
            .with_for_update().execution_options(populate_existing=True))

    def _revision(self, session, actor, head, revision_id=None, *, active=False):
        identity = _uuid(revision_id) if revision_id is not None else head.head_revision_id
        revision = session.scalar(select(ResearchExperimentRevision).where(
            ResearchExperimentRevision.id == identity, ResearchExperimentRevision.experiment_id == head.id,
            ResearchExperimentRevision.user_id == actor.id))
        if revision is None:
            raise ResearchExperimentError('not_found', 404)
        frozen = self._context(session, actor, self._binding(revision), active=active)
        if canonical_json(frozen) != revision.context_json:
            raise ResearchExperimentError('integrity_error', 409)
        return revision, frozen

    def _environment(self, proposal, *, dispatch=False):
        saved = self.environments.get(proposal['environment_id'])
        if saved is None:
            raise ResearchExperimentError('environment_unavailable')
        try:
            descriptor = EnvironmentDescriptor.model_validate(saved).model_dump(mode='json')
        except ValueError:
            raise ResearchExperimentError('environment_unavailable') from None
        if content_sha256(descriptor) != proposal['environment_id']:
            raise ResearchExperimentError('environment_unavailable')
        if dispatch and (descriptor['kind'] != 'c22-fake' or descriptor['test_only'] is not True):
            raise ResearchExperimentError('dispatch_unavailable')
        return descriptor

    def _exported(self, session, revision):
        from orchestration.frozen_experiment_export import FrozenExperimentExport
        proposal = json.loads(revision.proposal_json)
        environment = json.loads(revision.environment_json)
        if (canonical_json(ExperimentProposal.model_validate(proposal).model_dump(mode='json')) != revision.proposal_json
                or content_sha256(proposal) != revision.proposal_sha256
                or _hash(proposal['python_code'].encode('utf-8')) != revision.code_sha256
                or content_sha256(proposal['resources']) != revision.resources_sha256
                or content_sha256(environment) != revision.environment_sha256
                or proposal['environment_id'] != revision.environment_sha256
                or _hash(revision.manifest_json.encode('utf-8')) != revision.input_manifest_sha256):
            raise ResearchExperimentError('integrity_error', 409)
        files = {}
        total = len(revision.manifest_json.encode('utf-8'))
        for item in session.scalars(select(ResearchExperimentRevisionFile).where(
                ResearchExperimentRevisionFile.revision_id == revision.id).order_by(ResearchExperimentRevisionFile.name)):
            blob = session.get(ResearchExperimentInputBlob, (revision.user_id, item.sha256))
            if (blob is None or blob.size_bytes != item.size_bytes or len(blob.content) != item.size_bytes
                    or _hash(blob.content) != item.sha256 or total + item.size_bytes > MAX_INPUT_BYTES):
                raise ResearchExperimentError('integrity_error', 409)
            files[item.name] = bytes(blob.content)
            total += item.size_bytes
        try:
            exported = FrozenExperimentExport(manifest_json=revision.manifest_json, files=files)
        except (ValueError, TypeError, KeyError):
            raise ResearchExperimentError('integrity_error', 409) from None
        if (exported.input_manifest_sha256 != revision.input_manifest_sha256 or exported.source_sha256 != revision.source_sha256
                or total != revision.total_bytes or total > proposal['resources']['max_input_bytes']):
            raise ResearchExperimentError('integrity_error', 409)
        return proposal, environment, exported

    def _verify(self, *, frozen, proposal, actor, exported, access_only=False):
        try:
            callback = self.exporter.verify_access if access_only else self.exporter.verify
            callback(frozen=frozen, proposal=ExperimentProposal.model_validate(proposal), user=actor, exported=exported)
        except ResearchExperimentError:
            raise
        except Exception:
            raise ResearchExperimentError('access_denied', 403) from None

    def _closing_gate(self, session, *, user=None, owner_id=None, head_id, revision_id, active):
        """Final DB authority fence after all source/flag callbacks have run."""
        actor = self._actor(session, user=user, owner_id=owner_id)
        head = self._owned(session, actor, head_id)
        revision = session.get(ResearchExperimentRevision, _uuid(revision_id))
        if revision is None or revision.experiment_id != head.id or revision.user_id != actor.id:
            raise ResearchExperimentError('not_found', 404)
        item = self._investigation(session, actor, head.investigation_id, active=active)
        if active and (head.head_revision_id != revision.id or item.head_revision_id != revision.context_revision_id):
            raise ResearchExperimentError('conflict', 409)
        return actor

    def _event(self, session, head, kind):
        head.event_cursor += 1
        en, ja = TEXT[kind]
        session.add(ResearchExperimentEvent(experiment_id=head.id, cursor=head.event_cursor,
            kind=kind, summary_json=canonical_json({'en': en, 'ja': ja})))

    @staticmethod
    def _operation_snapshot(op):
        result = json.loads(op.result_json) if op.result_json else {}
        error_code = op.error_code if op.error_code in OPERATION_REASONS else 'export_unavailable' if op.error_code else None
        text = OPERATION_REASONS.get(error_code)
        return {'id': str(op.id), 'state': 'ready' if op.state == 'committed' else 'unavailable' if op.state == 'conflict' else op.state,
            'result_revision_id': result.get('revision_id'), 'error_code': error_code,
            'reason': {'en': text[0], 'ja': text[1]} if text is not None else None}

    def _approval(self, session, head, revision):
        approval = session.scalar(select(ResearchExperimentApproval).where(ResearchExperimentApproval.revision_id == revision.id))
        if approval is None:
            approval = session.scalar(select(ResearchExperimentApproval).where(
                ResearchExperimentApproval.experiment_id == head.id).order_by(ResearchExperimentApproval.created_at.desc(), ResearchExperimentApproval.id.desc()))
        if approval is None:
            return {'status': 'none', 'proposal_revision_id': None, 'approved_at': None}
        if _hash(approval.request_json.encode('utf-8')) != approval.request_sha256:
            raise ResearchExperimentError('integrity_error', 409)
        return {'status': 'current' if approval.revision_id == revision.id and head.head_revision_id == revision.id else 'stale',
            'proposal_revision_id': str(approval.revision_id), 'approved_at': approval.created_at.isoformat()}

    def _public(self, session, actor, head, revision, *, verify=True):
        frozen = self._context(session, actor, self._binding(revision))
        proposal, environment, exported = self._exported(session, revision)
        if verify:
            self._verify(frozen=frozen, proposal=proposal, actor=actor, exported=exported)
        approval = self._approval(session, head, revision)
        reservation = session.scalar(select(ResearchExperimentReservation).where(ResearchExperimentReservation.revision_id == revision.id))
        eligible, reason = False, 'Exact current approval and enabled fake dispatch are required'
        status = 'unavailable'
        if reservation is not None:
            status = reservation.state if reservation.state in {'reserved', 'accepted', 'uncertain'} else 'unavailable'
            reason = 'Retained fake delivery; Python was not executed'
        elif approval['status'] == 'current':
            try:
                self._require_enabled(dispatch=True)
                self._environment(proposal, dispatch=True)
                self._context(session, actor, self._binding(revision), active=True)
                active_reservations = list(session.scalars(select(ResearchExperimentReservation.user_id)
                    .where(ResearchExperimentReservation.state != 'released').limit(3)))
                if actor.id not in active_reservations and len(active_reservations) < 2:
                    eligible, reason, status = True, None, 'ready'
                else:
                    reason = 'Experiment capacity is reserved'
            except ResearchExperimentError:
                pass
        # Eligibility invokes host flag callbacks. They cannot be the final
        # authority check: refresh publication/access after those callbacks.
        if verify:
            self._verify(frozen=frozen, proposal=proposal, actor=actor, exported=exported, access_only=True)
        return {'id': str(head.id), 'binding': self._binding(revision), 'version': head.version,
            'proposal_revision_id': str(revision.id), 'proposal': proposal,
            'hashes': {key: getattr(revision, key) for key in HASH_FIELDS}, 'manifest': exported.manifest,
            'environment': environment, 'approval': approval,
            'dispatch': {'eligible': eligible, 'reason': reason, 'reservation_id': str(reservation.id) if reservation else None, 'status': status},
            'event_cursor': 0, 'latest_event_cursor': head.event_cursor, 'authority': 'experimental',
            'scientific_approval': 'not_independently_verified', 'execution_performed': False}

    def _response(self, session, actor, head, *, op=None, revision_id=None):
        experiment = None
        if head.head_revision_id is not None:
            revision, _ = self._revision(session, actor, head, revision_id)
            experiment = self._public(session, actor, head, revision)
        return {'version': 'research-experiments-v1', 'experiment': experiment,
            'operation': self._operation_snapshot(op) if op is not None else None}

    def _replayed(self, session, actor, kind, data):
        op = session.scalar(select(ResearchExperimentOperation).where(
            ResearchExperimentOperation.user_id == actor.id,
            ResearchExperimentOperation.idempotency_key == data['idempotency_key']).with_for_update())
        if op is None:
            return None
        if op.kind != kind or op.request_json != canonical_json(data) or op.request_sha256 != content_sha256(data):
            raise ResearchExperimentError('conflict', 409)
        return op

    def invoke(self, name, payload, user):
        try:
            data = EXPERIMENT_REQUEST_MODELS[name].model_validate(payload).model_dump(mode='json', exclude_none=True)
            if len(canonical_json(data).encode('utf-8')) > 65536:
                raise ValueError('Request too large')
        except (KeyError, ValueError, TypeError):
            raise ResearchExperimentError('invalid_request', 422) from None
        if name in {'create', 'revise'}:
            result = self._prepare(name, data, user)
        elif name in {'approve', 'dispatch'}:
            result = self._decision(name, data, user)
        elif name == 'retry':
            result = self._apply(_uuid(data['operation_id']), user, retry=True)
        else:
            with self._transaction() as session:
                actor = self._actor(session, user=user)
                if name == 'list':
                    result = self._list(session, actor, data)
                else:
                    head = self._owned(session, actor, data['experiment_id'])
                    if name == 'events':
                        result = self._events(session, actor, head, data)
                    else:
                        result = self._response(session, actor, head, revision_id=data.get('proposal_revision_id'))
                self._actor(session, user=user)
        try:
            return EXPERIMENT_RESPONSE_MODELS[name].model_validate(result).model_dump(mode='json')
        except ValueError:
            raise ResearchExperimentError('integrity_error', 409) from None

    def _prepare(self, kind, data, user):
        with self._transaction() as session:
            actor = self._actor(session, user=user)
            op = self._replayed(session, actor, kind, data)
            if op is None:
                self._require_enabled()
                frozen = self._context(session, actor, data, active=True)
                self._environment(data['proposal'])
                if kind == 'create':
                    head = ResearchExperiment(id=uuid.uuid4(), user_id=actor.id,
                        investigation_id=_uuid(data['investigation_id']), conversation_id=_uuid(data['conversation_id']), version=1, event_cursor=0)
                    session.add(head)
                    session.flush()
                else:
                    head = self._owned(session, actor, data['experiment_id'])
                    if (head.version != data['expected_version'] or str(head.head_revision_id) != data['expected_proposal_revision_id']
                            or str(head.investigation_id) != data['investigation_id'] or str(head.conversation_id) != data['conversation_id']):
                        raise ResearchExperimentError('conflict', 409)
                identity = uuid.uuid4()
                references = [{'snapshot_id': item['snapshot_id'], 'reference': 'c22:dependency:' + content_sha256(
                    [self.site_id, str(identity), item['snapshot_id']])}
                    for item in self.investigations._bindings(frozen['snapshot_id'], frozen['investigation_id'])]
                op = ResearchExperimentOperation(id=identity, experiment_id=head.id, user_id=actor.id,
                    investigation_id=head.investigation_id, kind=kind, idempotency_key=data['idempotency_key'],
                    expected_version=head.version, candidate_revision_id=uuid.uuid4(),
                    request_json=canonical_json(data), request_sha256=content_sha256(data),
                    frozen_json=canonical_json(frozen), references_json=canonical_json(references), state='prepared')
                session.add(op)
            identity = op.id
        return self._apply(identity, user)

    def _apply(self, operation_id, user, *, retry=False):
        with self._transaction() as session:
            actor = self._actor(session, user=user)
            op = session.scalar(select(ResearchExperimentOperation).where(
                ResearchExperimentOperation.id == operation_id, ResearchExperimentOperation.user_id == actor.id))
            if op is None:
                raise ResearchExperimentError('not_found', 404)
            head = self._owned(session, actor, op.experiment_id)
            if op.state in {'committed', 'conflict'} or op.kind not in {'create', 'revise'}:
                saved = json.loads(op.result_json) if op.result_json else {}
                return self._response(session, actor, head, op=op, revision_id=saved.get('revision_id'))
            # An ordinary lost-ack replay may observe a prepared operation while
            # paused. Explicit retry does not confer new preparation authority.
            try:
                self._require_enabled()
            except ResearchExperimentError:
                return self._response(session, actor, head, op=op)
            data, frozen, references = json.loads(op.request_json), json.loads(op.frozen_json), json.loads(op.references_json)
            if (op.request_sha256 != content_sha256(data) or canonical_json(frozen) != op.frozen_json
                    or head.version != op.expected_version):
                if head.version != op.expected_version:
                    op.state, op.error_code = 'conflict', 'conflict'
                    return self._response(session, actor, head, op=op)
                raise ResearchExperimentError('integrity_error', 409)
            actual = self._context(session, actor, data, active=True)
            if actual != frozen:
                raise ResearchExperimentError('conflict', 409)
            environment = self._environment(data['proposal'])
            owner, head_id, candidate, expected = actor, head.id, op.candidate_revision_id, op.expected_version
        try:
            lifecycle = self.investigations.store.lifecycle()
            for reference in references:
                previous = lifecycle['references'].get(reference['reference'])
                if previous is not None and previous != reference['snapshot_id']:
                    raise ValueError('Protection identity changed')
                self.investigations.store.add_reference(reference['snapshot_id'], reference['reference'])
            exported = self.exporter.freeze(frozen=frozen, proposal=ExperimentProposal.model_validate(data['proposal']), user=owner)
            if (len(exported.manifest_json.encode('utf-8')) > MAX_MANIFEST_BYTES
                    or exported.size_bytes > min(MAX_INPUT_BYTES, data['proposal']['resources']['max_input_bytes'])):
                raise ValueError('Frozen export exceeds approved bounds')
            protected = {item['snapshot_id'] for item in references}
            if not set(exported.snapshot_ids) <= protected:
                raise ValueError('Export dependencies were not prepared')
            self._verify(frozen=frozen, proposal=data['proposal'], actor=owner, exported=exported)
        except Exception as exc:
            with self._transaction() as session:
                actor = self._actor(session, user=user)
                head = self._owned(session, actor, head_id)
                op = session.get(ResearchExperimentOperation, operation_id)
                if op.state not in {'committed', 'conflict'}:
                    op.state = 'uncertain' if isinstance(exc, (SnapshotCommitUncertain, SQLAlchemyError)) else 'unavailable'
                    code = getattr(exc, 'code', None)
                    op.error_code = 'protection_uncertain' if op.state == 'uncertain' else code if code in OPERATION_REASONS else 'export_unavailable'
                saved = json.loads(op.result_json) if op.result_json else {}
                return self._response(session, actor, head, op=op, revision_id=saved.get('revision_id'))
        try:
            with self._transaction() as session:
                actor = self._actor(session, user=user)
                head = self._owned(session, actor, head_id)
                op = session.scalar(select(ResearchExperimentOperation).where(ResearchExperimentOperation.id == operation_id).with_for_update().execution_options(populate_existing=True))
                if op.state == 'committed':
                    return self._response(session, actor, head, op=op, revision_id=str(candidate))
                self._require_enabled()
                self._context(session, actor, data, active=True)
                if head.version != expected or self._environment(data['proposal']) != environment:
                    op.state, op.error_code = 'conflict', 'conflict'
                    return self._response(session, actor, head, op=op)
                proposal_json = canonical_json(data['proposal'])
                revision = ResearchExperimentRevision(id=candidate, experiment_id=head.id, user_id=actor.id,
                    investigation_id=head.investigation_id, conversation_id=head.conversation_id,
                    context_revision_id=_uuid(data['context_revision_id']), snapshot_id=data['snapshot_id'], payload_sha256=data['context_payload_sha256'],
                    sequence=head.version + (op.kind == 'revise'), context_json=canonical_json(frozen), proposal_json=proposal_json,
                    environment_json=canonical_json(environment), manifest_json=exported.manifest_json,
                    proposal_sha256=_hash(proposal_json.encode('utf-8')), code_sha256=_hash(data['proposal']['python_code'].encode('utf-8')),
                    input_manifest_sha256=exported.input_manifest_sha256, environment_sha256=content_sha256(environment),
                    resources_sha256=content_sha256(data['proposal']['resources']), source_sha256=exported.source_sha256,
                    total_bytes=exported.size_bytes)
                session.add(revision)
                session.flush()
                for name, content in exported.files.items():
                    digest = _hash(content)
                    blob = session.get(ResearchExperimentInputBlob, (actor.id, digest))
                    if blob is None:
                        session.add(ResearchExperimentInputBlob(user_id=actor.id, sha256=digest, content=content, size_bytes=len(content)))
                    elif blob.content != content or blob.size_bytes != len(content):
                        raise ResearchExperimentError('integrity_error', 409)
                    session.flush()
                    session.add(ResearchExperimentRevisionFile(revision_id=candidate, experiment_id=head.id, user_id=actor.id,
                        name=name, sha256=digest, size_bytes=len(content)))
                session.flush()
                head.head_revision_id = candidate
                if op.kind == 'revise':
                    head.version += 1
                self._event(session, head, 'created' if op.kind == 'create' else 'revised')
                op.state, op.error_code, op.result_json = 'committed', None, canonical_json({'revision_id': str(candidate)})
                session.flush()
                # Final publication witnesses are checked after all mutation
                # callbacks and immediately before transaction commitment.
                self._verify(frozen=frozen, proposal=data['proposal'], actor=actor, exported=exported, access_only=True)
                result = self._response(session, actor, head, op=op, revision_id=str(candidate))
                self._closing_gate(session, user=user, head_id=head.id, revision_id=candidate, active=True)
                return result
        except SQLAlchemyError:
            # Do not overwrite a possibly committed result. Exact operation/key
            # reconciliation distinguishes COMMIT-ack loss from rollback.
            with self._transaction() as session:
                actor = self._actor(session, user=user)
                head = self._owned(session, actor, head_id)
                op = session.get(ResearchExperimentOperation, operation_id)
                if op.state != 'committed':
                    op.state, op.error_code = 'uncertain', 'commit_uncertain'
                saved = json.loads(op.result_json) if op.result_json else {}
                return self._response(session, actor, head, op=op, revision_id=saved.get('revision_id'))

    def _expected(self, head, revision, data):
        if (head.version != data['expected_version'] or head.head_revision_id != revision.id
                or str(revision.id) != data['expected_proposal_revision_id']
                or data['expected_hashes'] != {key: getattr(revision, key) for key in HASH_FIELDS}
                or any(data[key] != value for key, value in self._binding(revision).items())):
            raise ResearchExperimentError('conflict', 409)

    def _decision(self, kind, data, user):
        with self._transaction() as session:
            actor = self._actor(session, user=user)
            replay = self._replayed(session, actor, kind, data)
            if replay is not None:
                head = self._owned(session, actor, replay.experiment_id)
                saved = json.loads(replay.result_json) if replay.result_json else {}
                return self._response(session, actor, head, op=replay, revision_id=saved.get('revision_id'))
            self._require_enabled(dispatch=kind == 'dispatch')
            head = self._owned(session, actor, data['experiment_id'])
            revision, frozen = self._revision(session, actor, head, active=True)
            self._expected(head, revision, data)
            proposal, environment, exported = self._exported(session, revision)
            if self._environment(proposal, dispatch=kind == 'dispatch') != environment:
                raise ResearchExperimentError('environment_unavailable')
        self._verify(frozen=frozen, proposal=proposal, actor=actor, exported=exported)
        self._require_enabled(dispatch=True)
        self._verify(frozen=frozen, proposal=proposal, actor=actor, exported=exported, access_only=True)
        with self._transaction() as session:
            actor = self._actor(session, user=user)
            replay = self._replayed(session, actor, kind, data)
            if replay is not None:
                head = self._owned(session, actor, replay.experiment_id)
                saved = json.loads(replay.result_json) if replay.result_json else {}
                return self._response(session, actor, head, op=replay, revision_id=saved.get('revision_id'))
            self._require_enabled(dispatch=kind == 'dispatch')
            head = self._owned(session, actor, data['experiment_id'])
            revision, frozen = self._revision(session, actor, head, active=True)
            self._expected(head, revision, data)
            if self._environment(proposal, dispatch=kind == 'dispatch') != environment:
                raise ResearchExperimentError('environment_unavailable')
            approval = session.scalar(select(ResearchExperimentApproval).where(ResearchExperimentApproval.revision_id == revision.id))
            if kind == 'approve':
                if approval is None:
                    approval = ResearchExperimentApproval(id=uuid.uuid4(), experiment_id=head.id, revision_id=revision.id,
                        user_id=actor.id, request_json=canonical_json(data), request_sha256=content_sha256(data))
                    session.add(approval)
                    self._event(session, head, 'approved')
            else:
                if approval is None or _hash(approval.request_json.encode('utf-8')) != approval.request_sha256:
                    raise ResearchExperimentError('conflict', 409)
                reservation = session.scalar(select(ResearchExperimentReservation).where(ResearchExperimentReservation.revision_id == revision.id))
                if reservation is None:
                    capacity = session.scalar(select(ResearchExperimentCapacity).where(ResearchExperimentCapacity.id == 1).with_for_update())
                    if capacity is None:
                        raise ResearchExperimentError('integrity_error', 409)
                    active = list(session.scalars(select(ResearchExperimentReservation).where(ResearchExperimentReservation.state != 'released')))
                    if any(item.user_id == actor.id for item in active) or len(active) >= 2:
                        raise ResearchExperimentError('capacity_unavailable', 409)
                    slot = next(number for number in (0, 1) if number not in {item.slot for item in active})
                    reservation = ResearchExperimentReservation(id=uuid.uuid4(), experiment_id=head.id, revision_id=revision.id,
                        approval_id=approval.id, user_id=actor.id, slot=slot, state='reserved', envelope_sha256='0' * 64)
                    reservation.envelope_sha256 = content_sha256(self._metadata(head, revision, approval, reservation, proposal, environment, exported))
                    session.add(reservation)
                    session.flush()
                    session.add(ResearchExperimentOutbox(reservation_id=reservation.id, state='pending', attempts=0))
                    self._event(session, head, 'reserved')
            op = ResearchExperimentOperation(experiment_id=head.id, user_id=actor.id, investigation_id=head.investigation_id,
                kind=kind, idempotency_key=data['idempotency_key'], expected_version=head.version,
                candidate_revision_id=revision.id, request_json=canonical_json(data), request_sha256=content_sha256(data),
                frozen_json=canonical_json(frozen), references_json='[]', state='committed', result_json=canonical_json({'revision_id': str(revision.id)}))
            session.add(op)
            session.flush()
            self._verify(frozen=frozen, proposal=proposal, actor=actor, exported=exported, access_only=True)
            result = self._response(session, actor, head, op=op)
            self._closing_gate(session, user=user, head_id=head.id, revision_id=revision.id, active=True)
            return result

    def _metadata(self, head, revision, approval, reservation, proposal, environment, exported):
        return {'version': 'c22-execution-envelope-v1', 'site_id': self.site_id,
            'experiment_id': str(head.id), 'proposal_revision_id': str(revision.id), 'owner_user_id': str(revision.user_id),
            'reservation_id': str(reservation.id), 'approval_id': str(approval.id), 'binding': self._binding(revision),
            'proposal': proposal, 'environment': environment, 'hashes': {key: getattr(revision, key) for key in HASH_FIELDS},
            'manifest': exported.manifest, 'authority': 'experimental', 'scientific_approval': 'not_independently_verified',
            'execution_performed': False}

    def load_execution_envelope(self, reservation_id, *, user=None):
        self._require_enabled(dispatch=True)
        with self._transaction() as session:
            row = session.get(ResearchExperimentReservation, _uuid(reservation_id))
            if row is None:
                raise ResearchExperimentError('not_found', 404)
            actor = self._actor(session, user=user, owner_id=row.user_id if user is None else None)
            if row.user_id != actor.id:
                raise ResearchExperimentError('not_found', 404)
            head = self._owned(session, actor, row.experiment_id)
            revision, frozen = self._revision(session, actor, head, row.revision_id, active=True)
            if head.head_revision_id != revision.id:
                raise ResearchExperimentError('conflict', 409)
            proposal, environment, exported = self._exported(session, revision)
            if self._environment(proposal, dispatch=True) != environment:
                raise ResearchExperimentError('environment_unavailable')
            approval = session.get(ResearchExperimentApproval, row.approval_id)
            if approval is None or approval.revision_id != revision.id or _hash(approval.request_json.encode()) != approval.request_sha256:
                raise ResearchExperimentError('integrity_error', 409)
            metadata = self._metadata(head, revision, approval, row, proposal, environment, exported)
            if content_sha256(metadata) != row.envelope_sha256:
                raise ResearchExperimentError('integrity_error', 409)
        self._verify(frozen=frozen, proposal=proposal, actor=actor, exported=exported)
        with self._transaction() as session:
            self._closing_gate(session, user=user, owner_id=row.user_id if user is None else None,
                head_id=head.id, revision_id=revision.id, active=True)
        return {'metadata': metadata, 'files': exported.files}

    def dispatch_outbox(self, *, limit=25, retry_uncertain=False):
        if type(limit) is not int or not 1 <= limit <= 100 or type(retry_uncertain) is not bool:
            raise ResearchExperimentError('invalid_request', 422)
        self._require_enabled(dispatch=True)
        with self._transaction() as session:
            states = ('pending', 'uncertain') if retry_uncertain else ('pending',)
            ids = list(session.scalars(select(ResearchExperimentOutbox.id).where(ResearchExperimentOutbox.state.in_(states))
                .order_by(ResearchExperimentOutbox.created_at, ResearchExperimentOutbox.id).limit(limit)))
        sent = 0
        for identity in ids:
            self._require_enabled(dispatch=True)
            with self._transaction() as session:
                initial = session.get(ResearchExperimentOutbox, identity)
                reservation = session.get(ResearchExperimentReservation, initial.reservation_id)
                actor = self._actor(session, owner_id=reservation.user_id)
                head = self._owned(session, actor, reservation.experiment_id)
                outbox = session.scalar(select(ResearchExperimentOutbox).where(ResearchExperimentOutbox.id == identity)
                    .with_for_update().execution_options(populate_existing=True))
                if outbox.state not in states:
                    continue
                revision, _ = self._revision(session, actor, head, reservation.revision_id, active=True)
                if head.head_revision_id != revision.id:
                    continue
                self._require_enabled(dispatch=True)
                reservation.state, outbox.state = 'uncertain', 'uncertain'
                outbox.attempts += 1
                delivery_id, reservation_id = str(outbox.delivery_id), str(reservation.id)
            try:
                envelope = self.load_execution_envelope(reservation_id)
                with self._transaction() as session:
                    self._closing_gate(session, owner_id=reservation.user_id, head_id=reservation.experiment_id,
                        revision_id=reservation.revision_id, active=True)
                receipt = self.executor.enqueue(envelope=envelope, delivery_id=delivery_id)
                expected = {'kind': 'c22-fake', 'delivery_id': delivery_id, 'reservation_id': reservation_id,
                    'envelope_sha256': content_sha256(envelope['metadata']), 'accepted': True, 'execution_performed': False}
                if receipt != expected:
                    raise ValueError('Unknown fake acknowledgement')
            except Exception:
                continue  # No release or fresh delivery ID after an uncertain effect.
            with self._transaction() as session:
                actor = self._actor(session, owner_id=reservation.user_id)
                head = self._owned(session, actor, reservation.experiment_id)
                outbox = session.scalar(select(ResearchExperimentOutbox).where(ResearchExperimentOutbox.id == identity)
                    .with_for_update().execution_options(populate_existing=True))
                if outbox.state == 'sent':
                    continue
                reservation = session.get(ResearchExperimentReservation, outbox.reservation_id, populate_existing=True)
                reservation.state, outbox.state = 'accepted', 'sent'
                outbox.receipt_json = canonical_json(expected)
                outbox.sent_at = datetime.now(timezone.utc)
                self._event(session, head, 'accepted')
                sent += 1
        return {'sent': sent, 'execution_performed': False}

    def _list(self, session, actor, data):
        self._investigation(session, actor, data['investigation_id'])
        statement = select(ResearchExperiment.id).where(ResearchExperiment.user_id == actor.id,
            ResearchExperiment.investigation_id == _uuid(data['investigation_id']), ResearchExperiment.head_revision_id.is_not(None))
        if data.get('conversation_id'):
            statement = statement.where(ResearchExperiment.conversation_id == _uuid(data['conversation_id']))
        if data.get('after_id'):
            statement = statement.where(ResearchExperiment.id > _uuid(data['after_id']))
        ids = list(session.scalars(statement.order_by(ResearchExperiment.id).limit(data['limit'] + 1)))
        items, total = [], 0
        for identity in ids[:data['limit']]:
            head = session.get(ResearchExperiment, identity)
            revision, _ = self._revision(session, actor, head)
            public = self._public(session, actor, head, revision)
            size = len(canonical_json(public).encode('utf-8'))
            if items and total + size > MAX_LIST_BYTES:
                break
            items.append(public)
            total += size
        more = len(ids) > len(items)
        return {'version': 'research-experiments-v1', 'items': items,
            'next_cursor': items[-1]['id'] if more and items else None}

    def _events(self, session, actor, head, data):
        self._revision(session, actor, head)
        if data['after_cursor'] > head.event_cursor:
            raise ResearchExperimentError('conflict', 409)
        rows = list(session.scalars(select(ResearchExperimentEvent).where(
            ResearchExperimentEvent.experiment_id == head.id, ResearchExperimentEvent.cursor > data['after_cursor'])
            .order_by(ResearchExperimentEvent.cursor).limit(data['limit'])))
        items = [{'cursor': row.cursor, 'kind': row.kind, 'summary': json.loads(row.summary_json)} for row in rows]
        next_cursor = data['after_cursor'] + len(items)
        return {'version': 'research-experiments-v1', 'experiment_id': str(head.id), 'after_cursor': data['after_cursor'],
            'items': items, 'next_cursor': next_cursor, 'latest_event_cursor': head.event_cursor, 'has_more': next_cursor < head.event_cursor}
