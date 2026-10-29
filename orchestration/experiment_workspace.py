"""C25 owner-authorized views over an explicitly supplied durable execution port.

No port is discovered or created here. A port's projections are trusted host
observations, not execution/physical-proof authority minted by these schemas.
Production retained-worker integration remains a separately accepted adapter.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
import base64
from contextlib import contextmanager
from dataclasses import dataclass
import csv
import hashlib
import io
import json
import struct
import uuid
import zlib

import config
from sqlalchemy import select

from db.app_models import ResearchExperimentApproval
from orchestration.experiment_sandbox.files import _csv_table, _json_table, _png
from orchestration.investigations import RetainedArtifactBinding
from orchestration.research_experiments import ResearchExperimentError, ResearchExperimentService
from schema.context_catalogue import canonical_json
from schema.experiment_workspace import (
    EXECUTION_REQUEST_MODELS, EXECUTION_RESPONSE_MODELS, EXECUTION_VERSION,
    ExecutionArtifact, ExecutionCapability, ExecutionSnapshot, MAX_ARTIFACT_CHUNK,
)
from schema.research_experiments import ExperimentApprovalRequest


class ExperimentWorkspaceError(ResearchExperimentError):
    def __init__(self, code='execution_unavailable', status_code=503):
        super().__init__(code, status_code)
        self.message = {
            'access_denied': 'Experiment execution access is denied',
            'not_found': 'Experiment execution was not found',
            'invalid_request': 'Experiment execution request is invalid',
            'conflict': 'Experiment execution identity changed; review it again',
            'integrity_error': 'Retained experiment execution is unavailable',
        }.get(code, 'Experiment execution is unavailable')


@dataclass(frozen=True)
class ExecutionAccess:
    """Detached public identity selected from freshly authorized retained C22 bytes."""
    owner_user_id: str
    site_id: str
    experiment_id: str
    proposal_revision_id: str
    proposal_version: int
    approval_id: str | None
    approval_request_sha256: str | None
    binding_json: str
    hashes_json: str
    expected_outputs_json: str
    output_limit: int

    @property
    def sha256(self):
        return hashlib.sha256(canonical_json({
            'owner': self.owner_user_id, 'site': self.site_id, 'experiment': self.experiment_id,
            'revision': self.proposal_revision_id, 'binding': json.loads(self.binding_json),
            'hashes': json.loads(self.hashes_json),
            'approval_id': self.approval_id, 'approval_request_sha256': self.approval_request_sha256,
        }).encode()).hexdigest()


class ExperimentExecutionPort(ABC):
    """Trusted durable host port, never a client-supplied capability.

    Implementations must retain immutable owner/revision-bound observations,
    consecutive events, hash-bound artifacts and durable idempotency. They must
    not launch or release capacity from these calls. ``cancel`` invokes
    closing_authorize immediately before committing only a cancellation intent
    while the service's authority context is held; no remote I/O in that fence.
    A synthetic fixture is allowed only in explicit development/test hosts.
    No production implementation or in-memory fallback is supplied here.
    """
    def __init__(self, *, experiments, source, cancel_available=True, artifacts_available=True):
        if (not isinstance(experiments, ResearchExperimentService)
                or source not in {'synthetic-fixture', 'retained-operator'}
                or type(cancel_available) is not bool or type(artifacts_available) is not bool):
            raise ValueError('Explicit bound execution port required')
        self.experiments = experiments
        self.site_id = experiments.site_id
        self.session_factory = experiments.session_factory
        self.source = source
        self.cancel_available, self.artifacts_available = cancel_available, artifacts_available

    @abstractmethod
    def status(self, access: ExecutionAccess, execution_id=None):
        """Return None or {'access_sha256':..., 'execution':<ExecutionSnapshot>} from durable bytes."""

    @abstractmethod
    def events(self, access: ExecutionAccess, execution_id, after_cursor, limit):
        """Return bounded consecutive {items,next_cursor,latest_event_cursor,has_more}."""

    @abstractmethod
    def cancel(self, access: ExecutionAccess, execution_id, idempotency_key, *, closing_authorize):
        """Durably retain exact retry key; return a CancellationAcknowledgement, never termination."""

    @abstractmethod
    def artifact(self, access: ExecutionAccess, execution_id, artifact_id):
        """Return the exact immutable bounded validated file bytes; never a URL/path."""


class ExperimentWorkspaceService:
    def __init__(self, *, experiments, port=None, enabled=None):
        if not isinstance(experiments, ResearchExperimentService):
            raise ValueError('Explicit C22 service required')
        if port is not None and not isinstance(port, ExperimentExecutionPort):
            raise ValueError('Explicit durable execution port required')
        self.experiments, self.port = experiments, port
        self.investigations = experiments.investigations
        self.site_id, self.session_factory = experiments.site_id, experiments.session_factory
        if enabled is not None and not callable(enabled):
            raise ValueError('Workspace availability must be a trusted callback')
        self.enabled = enabled if enabled is not None else config.v1_experiment_workspace_enabled
        self._binding()

    def _binding(self):
        service = self.experiments
        if (service.site_id != self.site_id or service.session_factory is not self.session_factory
                or service.investigations is not self.investigations):
            raise ExperimentWorkspaceError()
        if self.port is not None and (self.port.experiments is not service
                or self.port.site_id != self.site_id or self.port.session_factory is not self.session_factory):
            raise ExperimentWorkspaceError()

    def _capability(self):
        self._binding()
        port = self.port
        try:
            ready = self.enabled() is True and port is not None
            if ready and port.source == 'synthetic-fixture' and config.production_like_environment():
                ready = False
            if ready and (port.source not in {'synthetic-fixture', 'retained-operator'}
                    or type(port.cancel_available) is not bool or type(port.artifacts_available) is not bool):
                ready = False
        except Exception:
            ready = False
        value = {'transport': 'http-v1' if ready else 'unavailable',
            'source': port.source if ready else 'unavailable', 'start_enabled': False,
            'cancel_enabled': port.cancel_available if ready else False,
            'artifacts_enabled': port.artifacts_available if ready else False,
            'reason': None if ready else {'en': 'The execution service is unavailable; approval does not run Python.',
                'ja': '実行サービスは利用できません。承認だけではPythonは実行されません。'}}
        return ExecutionCapability.model_validate(value).model_dump(mode='json')

    def capability(self, user):
        # Host flag callbacks run between current principal checks.
        with self.experiments._transaction() as session:
            self.experiments._actor(session, user=user)
        capability = self._capability()
        with self.experiments._transaction() as session:
            self.experiments._actor(session, user=user)
        return {'version': EXECUTION_VERSION, 'capability': capability}

    def _authorized(self, session, data, user):
        service = self.experiments
        actor = service._actor(session, user=user)
        head = service._owned(session, actor, data['experiment_id'])
        revision, _ = service._revision(session, actor, head, data['expected_proposal_revision_id'])
        review = service._public(session, actor, head, revision)
        if (review['version'] != data['expected_version']
                or review['proposal_revision_id'] != data['expected_proposal_revision_id']
                or review['hashes'] != data['expected_hashes']
                or any(review['binding'][key] != data[key] for key in review['binding'])):
            raise ExperimentWorkspaceError('conflict', 409)
        # Fresh DB authority closes all outward source/flag callbacks above.
        service._closing_gate(session, user=user, head_id=head.id, revision_id=revision.id, active=False)
        approval = session.scalar(select(ResearchExperimentApproval).where(
            ResearchExperimentApproval.revision_id == revision.id))
        if approval is not None:
            try:
                request = ExperimentApprovalRequest.model_validate(json.loads(approval.request_json)).model_dump(mode='json')
                if (approval.experiment_id != head.id or approval.user_id != actor.id
                        or canonical_json(request) != approval.request_json
                        or hashlib.sha256(approval.request_json.encode()).hexdigest() != approval.request_sha256
                        or request['experiment_id'] != review['id']
                        or request['expected_proposal_revision_id'] != review['proposal_revision_id']
                        or request['expected_hashes'] != review['hashes']
                        or any(request[k] != value for k, value in review['binding'].items())):
                    raise ValueError
            except (ValueError, TypeError, KeyError):
                raise ExperimentWorkspaceError('integrity_error', 409) from None
        return ExecutionAccess(owner_user_id=str(actor.id), site_id=self.site_id,
            experiment_id=review['id'], proposal_revision_id=review['proposal_revision_id'],
            proposal_version=review['version'], approval_id=str(approval.id) if approval else None,
            approval_request_sha256=approval.request_sha256 if approval else None,
            binding_json=canonical_json(review['binding']),
            hashes_json=canonical_json(review['hashes']),
            expected_outputs_json=canonical_json(review['proposal']['expected_outputs']),
            output_limit=review['proposal']['resources']['max_output_bytes'])

    def _access(self, data, user):
        with self.experiments._transaction() as session:
            return self._authorized(session, data, user)

    def _closing(self, data, user, expected):
        current = self._access(data, user)
        if current != expected:
            raise ExperimentWorkspaceError('conflict', 409)
        self._binding()

    def _port_call(self, method, *args, **kwargs):
        try:
            return getattr(self.port, method)(*args, **kwargs)
        except ResearchExperimentError:
            raise
        except Exception:
            raise ExperimentWorkspaceError() from None

    @contextmanager
    def _cancel_fence(self, data, user, access):
        # No source/role/context change can cross the held C22 owner/head locks.
        with self.experiments._transaction() as session:
            current = self._authorized(session, data, user)
            if current != access:
                raise ExperimentWorkspaceError('conflict', 409)

            checks = []
            def closing_authorize():
                if self._authorized(session, data, user) != access or not self._capability()['cancel_enabled']:
                    raise ExperimentWorkspaceError('access_denied', 403)
                # Capability callbacks cannot be the final DB check.
                self.experiments._actor(session, user=user)
                head = self.experiments._owned(session, user, data['experiment_id'])
                self.experiments._closing_gate(session, user=user, head_id=head.id,
                    revision_id=uuid.UUID(data['expected_proposal_revision_id']), active=False)
                checks.append(True)

            yield closing_authorize
            if not checks:
                raise ExperimentWorkspaceError('integrity_error', 409)

    def _snapshot(self, access, user, execution_id=None):
        result = self._port_call('status', access, execution_id)
        if result is None:
            return None
        if type(result) is not dict or set(result) != {'access_sha256', 'execution'} or result['access_sha256'] != access.sha256:
            raise ExperimentWorkspaceError('integrity_error', 409)
        try:
            execution = ExecutionSnapshot.model_validate(result['execution']).model_dump(mode='json')
        except (ValueError, TypeError):
            raise ExperimentWorkspaceError('integrity_error', 409) from None
        if (access.approval_id is None or execution['source'] != self.port.source
                or (execution_id is not None and execution['id'] != execution_id)):
            raise ExperimentWorkspaceError('integrity_error', 409)
        expected = {item['name']: item['kind'] for item in json.loads(access.expected_outputs_json)}
        if (sum(item['size_bytes'] for item in execution['artifacts']) > access.output_limit
                or any(expected.get(item['name']) != item['kind'] for item in execution['artifacts'])):
            raise ExperimentWorkspaceError('integrity_error', 409)
        # Attachment availability requires the actual configured C17 resolver.
        for item in execution['artifacts']:
            reference = item['attachment_reference']
            if reference is not None:
                try:
                    resolver = self.investigations.artifact_resolver
                    binding = resolver(user, reference) if callable(resolver) else None
                    if (not isinstance(binding, RetainedArtifactBinding) or str(binding.owner_user_id) != access.owner_user_id
                            or binding.id != reference['id'] or binding.snapshot_id != reference['snapshot_id']
                            or reference['id'] != item['id']
                            or reference['snapshot_id'] != json.loads(access.binding_json)['snapshot_id']
                            or binding.sha256 != item['sha256']):
                        item['attachment_reference'] = None
                except Exception:
                    item['attachment_reference'] = None
        return execution

    @staticmethod
    def _response(access, capability, execution):
        return {'version': EXECUTION_VERSION, 'experiment_id': access.experiment_id,
            'proposal_revision_id': access.proposal_revision_id, 'proposal_version': access.proposal_version,
            'binding': json.loads(access.binding_json), 'hashes': json.loads(access.hashes_json),
            'capability': capability, 'execution': execution}

    def invoke(self, name, payload, user):
        try:
            data = EXECUTION_REQUEST_MODELS[name].model_validate(payload).model_dump(mode='json')
            if len(canonical_json(data).encode()) > 65536:
                raise ValueError
        except (KeyError, ValueError, TypeError):
            raise ExperimentWorkspaceError('invalid_request', 422) from None
        if name == 'capability':
            return self.capability(user)
        self._binding()
        access = self._access(data, user)
        capability = self._capability()
        if capability['transport'] == 'unavailable':
            self._closing(data, user, access)
            if name == 'status':
                return self._response(access, capability, None)
            raise ExperimentWorkspaceError()
        execution = self._snapshot(access, user, data.get('execution_id'))
        if name != 'status' and execution is None:
            raise ExperimentWorkspaceError('not_found', 404)
        result = self._response(access, capability, execution)
        if name == 'events':
            page = self._port_call('events', access, execution['id'], data['after_cursor'], data['limit'])
            if type(page) is not dict or set(page) != {'items', 'next_cursor', 'latest_event_cursor', 'has_more'}:
                raise ExperimentWorkspaceError('integrity_error', 409)
            if len(page['items']) > data['limit']:
                raise ExperimentWorkspaceError('integrity_error', 409)
            result.update(execution_id=execution['id'], after_cursor=data['after_cursor'], **page)
            result['execution'] = self._snapshot(access, user, execution['id'])
        elif name == 'cancel':
            if not capability['cancel_enabled']:
                raise ExperimentWorkspaceError()
            with self._cancel_fence(data, user, access) as closing_authorize:
                acknowledgement = self._port_call('cancel', access, execution['id'], data['idempotency_key'], closing_authorize=closing_authorize)
            if type(acknowledgement) is not dict or acknowledgement.get('idempotency_key') != data['idempotency_key']:
                raise ExperimentWorkspaceError('integrity_error', 409)
            result['cancellation'] = acknowledgement
            result['execution'] = self._snapshot(access, user, execution['id'])
        elif name == 'artifact':
            if not capability['artifacts_enabled']:
                raise ExperimentWorkspaceError()
            result.update(self._artifact(access, execution, data))
        # An outward adapter/resolver cannot be the last authorization check.
        self._closing(data, user, access)
        if self._capability() != capability:
            raise ExperimentWorkspaceError()
        self._closing(data, user, access)
        try:
            public = EXECUTION_RESPONSE_MODELS[name].model_validate(result).model_dump(mode='json')
            if len(canonical_json(public).encode()) > 8 * 1024 * 1024:
                raise ValueError
            return public
        except (ValueError, TypeError):
            raise ExperimentWorkspaceError('integrity_error', 409) from None

    def _artifact(self, access, execution, data):
        item = next((a for a in execution['artifacts'] if a['id'] == data['artifact_id']), None)
        if item is None:
            raise ExperimentWorkspaceError('not_found', 404)
        if item['sha256'] != data['expected_sha256']:
            raise ExperimentWorkspaceError('conflict', 409)
        raw = self._port_call('artifact', access, execution['id'], item['id'])
        if (type(raw) is not bytes or len(raw) != item['size_bytes'] or len(raw) > access.output_limit
                or hashlib.sha256(raw).hexdigest() != item['sha256']):
            raise ExperimentWorkspaceError('integrity_error', 409)
        try:
            validation = {'application/json': _json_table, 'text/csv': _csv_table, 'image/png': _png}[item['media_type']](raw)
            preview = None
            if item['kind'] == 'table':
                if item['media_type'] == 'application/json':
                    table = json.loads(raw)
                    columns, rows = table['columns'], table['rows'][:100]
                    rows = [[None if cell is None else str(cell) if type(cell) is not bool else str(cell).lower() for cell in row] for row in rows]
                else:
                    iterator = csv.reader(io.StringIO(raw.decode(), newline=''), strict=True)
                    columns = next(iterator)
                    rows = [row for _, row in zip(range(100), iterator)]
                preview = {'columns': columns, 'rows': rows, 'total_rows': validation['rows'],
                    'truncated': len(rows) < validation['rows'], 'cells_are_display_strings': True}
                if (any(len(column) > 4096 for column in columns)
                        or any(cell is not None and len(cell) > 4096 for row in rows for cell in row)
                        or len(canonical_json(preview).encode()) > 256 * 1024):
                    preview = None  # Download remains available; oversized display is not silently truncated.
        except (ValueError, TypeError, KeyError, UnicodeError, csv.Error, struct.error, zlib.error, StopIteration, RecursionError):
            raise ExperimentWorkspaceError('integrity_error', 409) from None
        offset = data['offset']
        if offset > len(raw):
            raise ExperimentWorkspaceError('invalid_request', 422)
        chunk = raw[offset:offset + min(data['limit'], MAX_ARTIFACT_CHUNK)]
        return {'artifact': ExecutionArtifact.model_validate(item).model_dump(mode='json'),
            'offset': offset, 'next_offset': offset + len(chunk), 'eof': offset + len(chunk) == len(raw),
            'content_base64': base64.b64encode(chunk).decode(), 'preview': preview if offset == 0 else None}
