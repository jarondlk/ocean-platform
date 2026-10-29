"""Explicit durable C25 synthetic adapter. Never imported by production code.

Seeding is a test operator action, not Python execution. SQLite here retains
owner-bound projections, bytes, event cursors and cancellation request retries;
it owns no C23 reservation, physical proof or capacity-release authority.
"""
from contextlib import contextmanager
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sqlite3
import struct
import uuid
import zlib

from orchestration.experiment_workspace import ExperimentExecutionPort, ExperimentWorkspaceError
from orchestration.investigations import RetainedArtifactBinding
from schema.context_catalogue import canonical_json
from schema.experiment_workspace import ExecutionSnapshot


class DurableSyntheticExecutionPort(ExperimentExecutionPort):
    def __init__(self, *, experiments, path):
        super().__init__(experiments=experiments, source='synthetic-fixture')
        self.path = Path(path)
        with self._connection() as connection:
            connection.executescript('''
                CREATE TABLE IF NOT EXISTS executions (
                    id TEXT PRIMARY KEY, owner TEXT NOT NULL, access_sha256 TEXT NOT NULL,
                    snapshot TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS events (
                    execution_id TEXT NOT NULL, cursor INTEGER NOT NULL, payload TEXT NOT NULL,
                    PRIMARY KEY(execution_id,cursor));
                CREATE TABLE IF NOT EXISTS artifacts (
                    id TEXT PRIMARY KEY, execution_id TEXT NOT NULL, owner TEXT NOT NULL,
                    access_sha256 TEXT NOT NULL, snapshot_id TEXT NOT NULL, sha256 TEXT NOT NULL,
                    bytes BLOB NOT NULL);
                CREATE TABLE IF NOT EXISTS cancellations (
                    owner TEXT NOT NULL, key TEXT NOT NULL, access_sha256 TEXT NOT NULL,
                    execution_id TEXT NOT NULL, acknowledgement TEXT NOT NULL,
                    PRIMARY KEY(owner,key));
            ''')

    @contextmanager
    def _connection(self):
        connection = sqlite3.connect(self.path, timeout=5)
        connection.row_factory = sqlite3.Row
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    @staticmethod
    def _owned(connection, access, execution_id):
        row = connection.execute('SELECT * FROM executions WHERE id=? AND owner=? AND access_sha256=?',
            (execution_id, access.owner_user_id, access.sha256)).fetchone()
        if row is None:
            raise ExperimentWorkspaceError('not_found', 404)
        return row

    def seed(self, access, *, state='running', files=None, execution_id=None):
        """Explicit fixture-only publication; no runtime is invoked."""
        execution_id = execution_id or str(uuid.uuid4())
        artifacts = []
        with self._connection() as connection:
            for name, media_type, raw in files or []:
                digest = hashlib.sha256(raw).hexdigest()
                artifact_id = 'synthetic:' + execution_id + ':' + digest[:16]
                snapshot_id = json.loads(access.binding_json)['snapshot_id']
                artifacts.append({'id': artifact_id, 'name': name,
                    'kind': 'raster' if media_type == 'image/png' else 'table',
                    'media_type': media_type, 'sha256': digest, 'size_bytes': len(raw),
                    'attachment_reference': {'kind': 'artifact', 'id': artifact_id, 'snapshot_id': snapshot_id},
                    'authority': 'experimental', 'scientific_approval': 'not_independently_verified'})
                connection.execute('INSERT INTO artifacts VALUES (?,?,?,?,?,?,?)',
                    (artifact_id, execution_id, access.owner_user_id, access.sha256, snapshot_id, digest, raw))
            snapshot = ExecutionSnapshot.model_validate({'id': execution_id, 'state': state,
                'state_revision': 1, 'source': 'synthetic-fixture', 'execution_performed': False,
                'termination_verified': False, 'termination_proof_sha256': None,
                'cancel_requested': False, 'event_cursor': 0, 'latest_event_cursor': 1,
                'outputs_manifest_sha256': hashlib.sha256(canonical_json(artifacts).encode()).hexdigest() if artifacts else None,
                'artifacts': artifacts}).model_dump(mode='json')
            connection.execute('INSERT INTO executions VALUES (?,?,?,?)',
                (execution_id, access.owner_user_id, access.sha256, canonical_json(snapshot)))
            event = {'cursor': 1, 'kind': 'synthetic_observation', 'summary': {
                'en': 'Synthetic retained observation; no Python or physical execution.',
                'ja': '合成の保存済み観測です。Pythonや物理的な実行はありません。'}}
            connection.execute('INSERT INTO events VALUES (?,?,?)', (execution_id, 1, canonical_json(event)))
        return deepcopy(snapshot)

    def status(self, access, execution_id=None):
        with self._connection() as connection:
            if execution_id is None:
                row = connection.execute('SELECT * FROM executions WHERE owner=? AND access_sha256=? ORDER BY rowid DESC LIMIT 1',
                    (access.owner_user_id, access.sha256)).fetchone()
            else:
                row = self._owned(connection, access, execution_id)
            return None if row is None else {'access_sha256': row['access_sha256'], 'execution': json.loads(row['snapshot'])}

    def events(self, access, execution_id, after_cursor, limit):
        with self._connection() as connection:
            row = self._owned(connection, access, execution_id)
            latest = json.loads(row['snapshot'])['latest_event_cursor']
            if after_cursor > latest:
                raise ExperimentWorkspaceError('conflict', 409)
            items = [json.loads(row['payload']) for row in connection.execute(
                'SELECT payload FROM events WHERE execution_id=? AND cursor>? ORDER BY cursor LIMIT ?',
                (execution_id, after_cursor, limit))]
            next_cursor = after_cursor + len(items)
            return {'items': items, 'next_cursor': next_cursor, 'latest_event_cursor': latest, 'has_more': next_cursor < latest}

    def cancel(self, access, execution_id, idempotency_key, *, closing_authorize):
        with self._connection() as connection:
            connection.execute('BEGIN IMMEDIATE')
            row = self._owned(connection, access, execution_id)
            saved = connection.execute('SELECT * FROM cancellations WHERE owner=? AND key=?',
                (access.owner_user_id, idempotency_key)).fetchone()
            if saved is not None:
                if saved['access_sha256'] != access.sha256 or saved['execution_id'] != execution_id:
                    raise ExperimentWorkspaceError('conflict', 409)
                closing_authorize()
                return json.loads(saved['acknowledgement'])
            snapshot = json.loads(row['snapshot'])
            terminal = snapshot['state'] in {'completed', 'failed', 'cancelled', 'timed_out'}
            acknowledgement = {'idempotency_key': idempotency_key,
                'status': 'already_terminal' if terminal else 'requested', 'termination_confirmed': False}
            if not terminal and not snapshot['cancel_requested']:
                snapshot.update(state='cancelling', cancel_requested=True,
                    state_revision=snapshot['state_revision'] + 1, latest_event_cursor=snapshot['latest_event_cursor'] + 1)
                event = {'cursor': snapshot['latest_event_cursor'], 'kind': 'cancel_requested',
                    'summary': {'en': 'Cancellation intent retained; termination is not confirmed.',
                        'ja': 'キャンセル要求を保存しました。終了は確認されていません。'}}
                connection.execute('UPDATE executions SET snapshot=? WHERE id=?', (canonical_json(snapshot), execution_id))
                connection.execute('INSERT INTO events VALUES (?,?,?)', (execution_id, event['cursor'], canonical_json(event)))
            connection.execute('INSERT INTO cancellations VALUES (?,?,?,?,?)',
                (access.owner_user_id, idempotency_key, access.sha256, execution_id, canonical_json(acknowledgement)))
            closing_authorize()  # Last authority check before the durable request commit.
            return acknowledgement

    def artifact(self, access, execution_id, artifact_id):
        with self._connection() as connection:
            self._owned(connection, access, execution_id)
            row = connection.execute('SELECT bytes FROM artifacts WHERE id=? AND execution_id=? AND owner=? AND access_sha256=?',
                (artifact_id, execution_id, access.owner_user_id, access.sha256)).fetchone()
            if row is None:
                raise ExperimentWorkspaceError('not_found', 404)
            return row['bytes']

    def resolve_artifact(self, user, reference):
        with self.experiments._transaction() as session:
            actor = self.experiments._actor(session, user=user)
        with self._connection() as connection:
            row = connection.execute('SELECT * FROM artifacts WHERE id=? AND owner=? AND snapshot_id=?',
                (reference['id'], str(actor.id), reference['snapshot_id'])).fetchone()
            if (row is None or reference['kind'] != 'artifact'
                    or hashlib.sha256(row['bytes']).hexdigest() != row['sha256']):
                return None
            return RetainedArtifactBinding(id=row['id'], owner_user_id=actor.id,
                snapshot_id=row['snapshot_id'], sha256=row['sha256'])


def seed_workspace_examples(fixture, workspace, port):
    """Explicitly seed one context's draft/running/completed/failure/timeout UI cases.

    The caller creates ``fixture`` with make_experiment_fixture and binds the
    workspace/port/resolver explicitly. Returned values are real C22 snapshots
    and C25 synthetic projections, never a live-runtime acceptance receipt.
    """
    request = fixture.request()
    request['proposal']['expected_outputs'] = [
        {'name': 'summary.json', 'kind': 'table', 'description': 'Synthetic display table'},
        {'name': 'plot.png', 'kind': 'raster', 'description': 'Synthetic two-pixel raster'},
    ]
    request['proposal']['limitations'] = ['Explicit local synthetic fixture; Python was not executed.']
    def chunk(kind, payload):
        return struct.pack('>I', len(payload)) + kind + payload + struct.pack('>I', zlib.crc32(kind + payload) & 0xffffffff)
    png = (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', 2, 1, 8, 2, 0, 0, 0))
        + chunk(b'IDAT', zlib.compress(b'\x00\x20\x80\xc0\xa0\xd0\xe0')) + chunk(b'IEND', b''))
    table = canonical_json({'columns': ['cast_id', 'count', 'observation'],
        'rows': [['synthetic-01', 9223372036854775807, 'Experimental fixture only'],
                 ['synthetic-02', None, 'No independent scientific approval']]}).encode()
    examples = {}
    for state in ('draft', 'running', 'completed', 'failed', 'timed_out'):
        proposal = deepcopy(request)
        proposal['idempotency_key'] = str(uuid.uuid4())
        proposal['proposal']['question'] = 'Synthetic workspace example: ' + state
        experiment = fixture.service.invoke('create', proposal, fixture.user)['experiment']
        projection = None
        if state != 'draft':
            experiment = fixture.service.invoke('approve', fixture.decision(experiment), fixture.user)['experiment']
            binding = fixture.decision(experiment)
            binding.pop('idempotency_key')
            access = workspace._access(binding, fixture.user)
            files = [('summary.json', 'application/json', table), ('plot.png', 'image/png', png)] if state == 'completed' else None
            projection = port.seed(access, state=state, files=files)
        examples[state] = {'experiment': experiment, 'execution': projection}
    return {'binding': examples['draft']['experiment']['binding'], 'examples': examples}
