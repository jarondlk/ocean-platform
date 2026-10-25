"""Actual SQLite/flock/process-crash tests; no sandbox or generated code runs."""
import hashlib
import fcntl
import json
import multiprocessing
import os
from pathlib import Path
import select
import shutil
import sqlite3
import stat
import threading
from types import ModuleType
import warnings

import pytest

from orchestration.experiment_sandbox.contracts import SandboxError
import orchestration.experiment_sandbox.journal as module
from orchestration.experiment_sandbox.journal import DurableExecutionJournal, DurableLease

JOB = 'c23-' + 'a' * 48
OTHER_JOB = 'c23-' + 'c' * 48
ENVELOPE = 'b' * 64
HOST = 'f' * 64
BOOT = '11111111-1111-4111-8111-111111111111'
NEXT_BOOT = '22222222-2222-4222-8222-222222222222'


def create(root, **kwargs):
    return DurableExecutionJournal(Path(root).resolve(), host_id=HOST,
                                   host_boot_id=kwargs.pop('host_boot_id', BOOT), **kwargs)


@pytest.fixture
def root(tmp_path):
    if not module._safe_sqlite_version(sqlite3.sqlite_version_info):
        pytest.skip('Actual durable-journal tests require SQLite with the WAL-reset fix')
    value = (tmp_path / 'trusted-control').resolve()
    value.mkdir(mode=0o700)
    return value


@pytest.fixture
def journal(root):
    with create(root) as value:
        yield value


class Clock:
    def __init__(self, value=100):
        self.value = value

    def __call__(self):
        return self.value


def raw(root, statement, args=()):
    with sqlite3.connect(root / 'journal.sqlite3') as connection:
        return connection.execute(statement, args).fetchall()


def _attempt_in_process(root, pipe):
    try:
        with create(root) as journal:
            with journal.claim(JOB, ENVELOPE) as lease:
                pipe.send(('acquired', lease.epoch))
    except SandboxError as error:
        pipe.send(('denied', error.reason))
    finally:
        pipe.close()


def _probe_database_lock(root, pipe):
    fd = os.open(Path(root) / 'journal.sqlite3', os.O_RDWR)
    try:
        try:
            fcntl.lockf(fd, fcntl.LOCK_EX | fcntl.LOCK_NB, 1, 1073741826, os.SEEK_SET)
        except BlockingIOError:
            pipe.send('blocked')
        else:
            pipe.send('acquired')
            fcntl.lockf(fd, fcntl.LOCK_UN, 1, 1073741826, os.SEEK_SET)
    finally:
        os.close(fd)
        pipe.close()


def probe_database_lock(root):
    context = multiprocessing.get_context('spawn')
    parent, child = context.Pipe()
    process = context.Process(target=_probe_database_lock, args=(str(root), child))
    process.start()
    child.close()
    try:
        assert parent.poll(15), 'database lock probe did not report'
        result = parent.recv()
        process.join(15)
        assert process.exitcode == 0
        return result
    finally:
        if process.is_alive():
            process.kill()
            process.join(5)
        parent.close()


def _hold_in_process(root, pipe, uncommitted):
    with create(root) as journal:
        with journal.claim(JOB, ENVELOPE) as lease:
            lease.append('create_intent', {'deterministic_job': JOB})
            if uncommitted:
                with journal._connection(write=True) as connection:
                    snapshot = journal._lease(lease, connection)
                    journal._append(connection, snapshot, 'uncommitted_effect',
                                    module._encode({'not_acknowledged': True}, 65536), journal._now())
                    pipe.send(('holding_uncommitted', lease.epoch))
                    pipe.recv()
            else:
                pipe.send(('holding', lease.epoch))
                pipe.recv()


def test_durable_reopen_detached_events_and_immutable_control_result(root):
    with create(root) as journal:
        assert journal.read(JOB, ENVELOPE) is None
        with journal.claim(JOB, ENVELOPE) as lease:
            assert not lease.reconciliation_required and lease.epoch == 1
            source = {'nested': [1, 'Δ', 2**63 - 1]}
            event = lease.append('create_intent', source)
            source['nested'].append('changed')
            assert event.payload == {'nested': [1, 'Δ', 2**63 - 1]}
            detached = event.payload
            detached['nested'].append('also_changed')
            assert lease.snapshot().events[-1].payload == {'nested': [1, 'Δ', 2**63 - 1]}
            result = {'state': 'record_only', 'termination_observed': False}
            retained = lease.finish(result)
            result['state'] = 'mutated'
            assert retained['record']['state'] == 'record_only'
            assert retained['dispatch_eligible'] is False
            assert retained['reservation_released'] is False
            assert retained['scientific_approval'] == 'not_independently_verified'
            retained['record']['state'] = 'changed_copy'
            assert lease.snapshot().result['record']['state'] == 'record_only'
    with create(root) as reopened:
        snapshot = reopened.read(JOB, ENVELOPE)
        assert snapshot.terminal and not snapshot.reconciliation_required
        before = snapshot.events
        with reopened.claim(JOB, ENVELOPE) as replay:
            assert replay.epoch == 1
            assert replay.finish({'state': 'record_only', 'termination_observed': False}) == snapshot.result
            with pytest.raises(SandboxError, match='result_immutable'):
                replay.finish({'state': 'replacement'})
            with pytest.raises(SandboxError, match='result_immutable'):
                replay.append('restart_intent', {})
        assert reopened.read(JOB, ENVELOPE).events == before


def test_wal_full_and_private_permissions(journal, root):
    with journal._connection() as connection:
        assert connection.execute('PRAGMA journal_mode').fetchone()[0] == 'wal'
        assert connection.execute('PRAGMA synchronous').fetchone()[0] == 2
        assert connection.execute('PRAGMA foreign_keys').fetchone()[0] == 1
        for sidecar in ('journal.sqlite3-wal', 'journal.sqlite3-shm'):
            assert stat.S_IMODE((root / sidecar).stat().st_mode) == 0o600
    with journal.claim(JOB, ENVELOPE) as lease:
        assert not os.get_inheritable(lease._fd)
        for path in (root / 'journal.sqlite3', root / 'identity.json', root / 'schema.lock',
                     root / 'locks' / (JOB + '.lock')):
            assert stat.S_IMODE(path.stat().st_mode) == 0o600
        assert stat.S_IMODE(root.stat().st_mode) == 0o700
        assert stat.S_IMODE((root / 'locks').stat().st_mode) == 0o700


def test_same_process_independent_controllers_cannot_steal_live_effect_lock(journal, root):
    with journal.claim(JOB, ENVELOPE) as active:
        active.append('start_intent', {})
        with create(root) as contender:
            with pytest.raises(SandboxError, match='worker_busy'):
                contender.claim(JOB, ENVELOPE)
        assert active.require_current().epoch == 1
        with pytest.raises(SandboxError, match='worker_busy'):
            journal.claim(JOB, ENVELOPE)
    with journal.claim(JOB, ENVELOPE) as recovered:
        assert recovered.epoch == 2 and recovered.reconciliation_required
        assert recovered.snapshot().result is None
        assert [e.kind for e in recovered.snapshot().events] == ['claimed', 'start_intent', 'claimed']


def test_separate_process_cannot_claim_while_effect_scope_is_active(journal, root):
    context = multiprocessing.get_context('spawn')
    parent, child = context.Pipe()
    with journal.claim(JOB, ENVELOPE) as lease:
        process = context.Process(target=_attempt_in_process, args=(str(root), child))
        process.start()
        child.close()
        try:
            assert parent.poll(15), 'contender did not report'
            assert parent.recv() == ('denied', 'sandbox_worker_busy')
            process.join(15)
            assert process.exitcode == 0
            assert lease.require_current().epoch == 1
        finally:
            if process.is_alive():
                process.kill()
                process.join(5)
            parent.close()


@pytest.mark.parametrize('uncommitted', [False, True])
def test_sigkill_releases_lock_but_requires_durable_reconciliation(root, uncommitted):
    # Child is killed while its actual SQLite write transaction is open in the
    # second case; unacknowledged history must roll back on the real database.
    context = multiprocessing.get_context('spawn')
    parent, child = context.Pipe()
    process = context.Process(target=_hold_in_process, args=(str(root), child, uncommitted))
    process.start()
    child.close()
    try:
        assert parent.poll(15), 'owner did not report'
        state, epoch = parent.recv()
        assert state == ('holding_uncommitted' if uncommitted else 'holding') and epoch == 1
        process.kill()
        process.join(15)
        assert process.exitcode is not None and process.exitcode != 0
        with create(root) as reopened:
            previous = reopened.read(JOB, ENVELOPE)
            assert [event.kind for event in previous.events] == ['claimed', 'create_intent']
            with reopened.claim(JOB, ENVELOPE) as recovered:
                assert recovered.epoch == 2 and recovered.reconciliation_required
                assert recovered.snapshot().result is None
                assert not reopened.releases_reservations and not reopened.grants_execution
    finally:
        if process.is_alive():
            process.kill()
            process.join(5)
        parent.close()


def test_fork_child_cannot_inherit_authority_or_unlock_parent(journal, root):
    with journal.claim(JOB, ENVELOPE) as lease:
        read_fd, write_fd = os.pipe()
        pid = os.fork()
        if pid == 0:
            os.close(read_fd)
            try:
                try:
                    lease.append('forked_effect', {})
                except SandboxError as error:
                    os.write(write_fd, error.reason.encode())
                else:
                    os.write(write_fd, b'ERROR-authority-inherited')
            finally:
                os.close(write_fd)
                os._exit(0)
        os.close(write_fd)
        try:
            assert os.read(read_fd, 256) == b'sandbox_fence_lost'
            assert os.waitpid(pid, 0)[1] == 0
            assert lease.require_current().epoch == 1
            with create(root) as contender:
                with pytest.raises(SandboxError, match='worker_busy'):
                    contender.claim(JOB, ENVELOPE)
        finally:
            os.close(read_fd)


def test_independent_job_locks_can_coexist_and_closed_fence_never_revives(journal):
    first = journal.claim(JOB, ENVELOPE)
    with journal.claim(OTHER_JOB, ENVELOPE) as other:
        assert other.epoch == 1
        first.close()
        with journal.claim(JOB, ENVELOPE) as replacement:
            assert replacement.epoch == 2
            for action in (first.require_current, lambda: first.append('stale', {}),
                           lambda: first.finish({'state': 'stale'})):
                with pytest.raises(SandboxError, match='fence_lost'):
                    action()
        first.close()  # Own explicit close is idempotent, never a terminal event.


@pytest.mark.parametrize('fake', [None, True, {'epoch': 1}, object.__new__(DurableLease)])
def test_exact_internal_live_lease_is_required(journal, fake):
    with pytest.raises(SandboxError, match='fence_lost'):
        journal.require_current(fake)


def test_copied_or_subclassed_lease_cannot_borrow_live_descriptor(journal):
    class Forged(DurableLease):
        pass

    with journal.claim(JOB, ENVELOPE) as actual:
        for kind in (DurableLease, Forged):
            forged = object.__new__(kind)
            for slot in DurableLease.__slots__:
                setattr(forged, slot, getattr(actual, slot))
            with pytest.raises(SandboxError, match='fence_lost'):
                journal.require_current(forged)
        actual.append('valid_owner', {})


@pytest.mark.parametrize('job,envelope', [
    ('../job', ENVELOPE), (JOB + '/file', ENVELOPE), (True, ENVELOPE),
    (JOB, True), (JOB, 'A' * 64), (JOB, 'short'),
])
def test_job_and_envelope_are_strict_not_paths(journal, job, envelope):
    with pytest.raises(SandboxError, match='journal_identity'):
        journal.claim(job, envelope)


def test_existing_job_cannot_be_rebound_to_another_envelope(journal):
    with journal.claim(JOB, ENVELOPE):
        pass
    for operation in (journal.claim, journal.read):
        with pytest.raises(SandboxError, match='journal_identity'):
            operation(JOB, 'd' * 64)
    assert journal.read(JOB, ENVELOPE).epoch == 1


def test_clock_rollback_rejected_within_boot_and_reboot_origin_is_explicit(root):
    clock = Clock(1000)
    with create(root, clock_ns=clock) as journal:
        with journal.claim(JOB, ENVELOPE) as lease:
            clock.value = 1001
            lease.append('observed', {})
            clock.value = 999
            with pytest.raises(SandboxError, match='journal_clock'):
                lease.append('rollback', {})
            assert [e.kind for e in lease.snapshot().events] == ['claimed', 'observed']
    with create(root, clock_ns=Clock(3), host_boot_id=NEXT_BOOT) as rebooted:
        with rebooted.claim(JOB, ENVELOPE) as lease:
            assert lease.epoch == 2 and lease.reconciliation_required
            assert [e.monotonic_ns for e in lease.snapshot().events] == [1000, 1001, 3]
            assert lease.snapshot().events[-1].host_boot_id == NEXT_BOOT


@pytest.mark.parametrize('value', [True, -1, 2**63, 1.5, float('nan'), None])
def test_invalid_clock_cannot_claim_effect_authority(root, value):
    with create(root, clock_ns=Clock(value)) as journal:
        with pytest.raises(SandboxError, match='journal_clock'):
            journal.claim(JOB, ENVELOPE)
        assert journal.read(JOB, ENVELOPE) is None


@pytest.mark.parametrize('payload', [
    {'x': float('nan')}, {'x': float('inf')}, {'x': b'bytes'}, {1: 'key'},
    {'x': object()}, {'x': '\ud800'}, {'x': 2**63}, ['not_an_object'],
])
def test_nonfinite_or_non_json_payload_cannot_enter_history(journal, payload):
    with journal.claim(JOB, ENVELOPE) as lease:
        with pytest.raises(SandboxError):
            lease.append('bad_payload', payload)
        assert len(lease.snapshot().events) == 1


def test_deep_cyclic_or_excessive_payload_is_bounded(journal):
    cycle = {}
    cycle['self'] = cycle
    deep = {}
    for _ in range(35):
        deep = {'child': deep}
    with journal.claim(JOB, ENVELOPE) as lease:
        for payload in (cycle, deep, {'data': 'x' * module.MAX_PAYLOAD_BYTES},
                        {'nodes': [None] * 65536}):
            with pytest.raises(SandboxError, match='journal_limit'):
                lease.append('too_large', payload)
        assert len(lease.snapshot().events) == 1


def test_result_bound_includes_wrapper_and_failed_finish_is_atomic(journal):
    with journal.claim(JOB, ENVELOPE) as lease:
        for payload in ({'x': 'a' * module.MAX_RESULT_BYTES},
                        {'x': 'a' * (module.MAX_RESULT_BYTES - 20)}):
            with pytest.raises(SandboxError, match='journal_limit'):
                lease.finish(payload)
            assert not lease.snapshot().terminal and len(lease.snapshot().events) == 1
        lease.finish({'safe': True})


def test_event_count_limit_is_fail_closed_and_includes_terminal_event(journal, monkeypatch):
    monkeypatch.setattr(module, 'MAX_EVENTS', 5)
    with journal.claim(JOB, ENVELOPE) as lease:
        for _ in range(3):
            lease.append('observation', {})
        lease.finish({'retained': True})
        assert len(lease.snapshot().events) == 5
    with journal.claim(OTHER_JOB, ENVELOPE) as lease:
        for _ in range(4):
            lease.append('observation', {})
        with pytest.raises(SandboxError, match='journal_limit'):
            lease.append('excess', {})
        with pytest.raises(SandboxError, match='journal_limit'):
            lease.finish({'retained': False})
        assert not lease.snapshot().terminal


@pytest.mark.parametrize('kind', ['claimed', 'finished', '../effect', 'effect-name', '', True])
def test_internal_event_kinds_and_bad_labels_cannot_be_forged(journal, kind):
    with journal.claim(JOB, ENVELOPE) as lease:
        with pytest.raises(SandboxError, match='journal_integrity'):
            lease.append(kind, {})


def test_result_and_finish_event_share_one_transaction(journal, monkeypatch):
    with journal.claim(JOB, ENVELOPE) as lease:
        append = journal._append

        def failure_after_event(*args):
            append(*args)
            raise OSError('injected control write failure')

        monkeypatch.setattr(journal, '_append', failure_after_event)
        with pytest.raises(OSError, match='injected'):
            lease.finish({'not_acknowledged': True})
        snapshot = lease.snapshot()
        assert not snapshot.terminal and len(snapshot.events) == 1
        monkeypatch.setattr(journal, '_append', append)
        lease.finish({'acknowledged': True})


@pytest.mark.parametrize('table', ['events', 'results', 'metadata'])
@pytest.mark.parametrize('operation', ['UPDATE', 'DELETE'])
def test_sql_triggers_forbid_retained_record_updates_and_deletes(journal, root, table, operation):
    with journal.claim(JOB, ENVELOPE) as lease:
        lease.finish({'retained': True})
    assignment = {'events': "payload_json='{}'", 'results': "document_json='{}'", 'metadata': "value='{}'"}
    statement = f'{operation} {table} SET {assignment[table]}' if operation == 'UPDATE' else f'DELETE FROM {table}'
    with pytest.raises(sqlite3.IntegrityError, match='immutable'):
        raw(root, statement)
    assert journal.read(JOB, ENVELOPE).terminal


def test_schema_trigger_removal_is_detected_not_silently_repaired(journal, root):
    with journal.claim(JOB, ENVELOPE):
        pass
    raw(root, 'DROP TRIGGER events_no_update')
    with pytest.raises(SandboxError, match='journal_integrity'):
        journal.read(JOB, ENVELOPE)
    with pytest.raises(SandboxError, match='journal_integrity'):
        create(root)


def test_mutable_head_tampering_is_detected_by_full_chain_readback(journal, root):
    with journal.claim(JOB, ENVELOPE):
        pass
    raw(root, 'UPDATE jobs SET head_sha256=? WHERE job_id=?', ('0' * 64, JOB))
    with pytest.raises(SandboxError, match='journal_integrity'):
        journal.read(JOB, ENVELOPE)


def test_hash_chain_is_recomputed_not_just_compared_to_head(journal, root):
    with journal.claim(JOB, ENVELOPE):
        pass
    original = module._TRIGGERS['events_no_update']
    with sqlite3.connect(root / 'journal.sqlite3') as connection:
        connection.execute('DROP TRIGGER events_no_update')
        connection.execute('UPDATE events SET payload_json=?', ('{}',))
        connection.execute(original)
    with pytest.raises(SandboxError, match='journal_integrity'):
        journal.read(JOB, ENVELOPE)


@pytest.mark.parametrize('mode', [0o755, 0o770, 0o777])
def test_control_root_must_be_private(root, mode):
    root.chmod(mode)
    with pytest.raises(SandboxError, match='journal_path'):
        create(root)


def test_relative_or_symlink_root_is_rejected(root, tmp_path):
    with pytest.raises(SandboxError, match='journal_path'):
        DurableExecutionJournal('relative', host_boot_id=BOOT, host_id=HOST)
    alias = tmp_path / 'alias'
    alias.symlink_to(root, target_is_directory=True)
    with pytest.raises(SandboxError, match='journal_path'):
        DurableExecutionJournal(alias, host_boot_id=BOOT, host_id=HOST)


@pytest.mark.parametrize('target', ['journal.sqlite3', 'identity.json', 'schema.lock'])
def test_symlink_or_hardlinked_control_files_are_rejected(journal, root, target):
    path = root / target
    extra = root.parent / ('extra-' + target)
    os.link(path, extra)
    with pytest.raises(SandboxError, match='journal_path'):
        journal.read(JOB, ENVELOPE)
    extra.unlink()
    moved = root.parent / ('moved-' + target)
    path.rename(moved)
    path.symlink_to(moved)
    with pytest.raises(SandboxError, match='journal_path'):
        journal.read(JOB, ENVELOPE)


@pytest.mark.parametrize('target', ['journal.sqlite3-wal', 'journal.sqlite3-shm'])
def test_sqlite_sidecar_symlink_is_rejected_before_open(journal, root, target):
    canary = root.parent / 'canary'
    canary.write_bytes(b'unchanged')
    (root / target).symlink_to(canary)
    with pytest.raises(SandboxError, match='journal_path'):
        journal.read(JOB, ENVELOPE)
    assert canary.read_bytes() == b'unchanged'


def test_lock_inode_replacement_invalidates_lease_and_cannot_create_new_epoch(journal, root):
    with journal.claim(JOB, ENVELOPE) as lease:
        lock = root / 'locks' / (JOB + '.lock')
        lock.rename(root / 'locks' / 'old.lock')
        lock.touch(mode=0o600)
        with pytest.raises(SandboxError, match='fence_lost'):
            lease.require_current()
        with create(root) as contender:
            with pytest.raises(SandboxError, match='fence_lost'):
                contender.claim(JOB, ENVELOPE)
        assert journal.read(JOB, ENVELOPE).epoch == 1


def test_missing_lock_or_database_is_not_a_fresh_job_reset(root):
    with create(root) as journal:
        with journal.claim(JOB, ENVELOPE):
            pass
    (root / 'locks' / (JOB + '.lock')).unlink()
    with create(root) as journal:
        with pytest.raises(SandboxError, match='journal_path'):
            journal.claim(JOB, ENVELOPE)
        assert journal.read(JOB, ENVELOPE).epoch == 1
    (root / 'journal.sqlite3').unlink()
    with pytest.raises(SandboxError, match='journal_path'):
        create(root)


def test_marker_loss_is_fail_closed_and_host_or_root_copy_cannot_be_reused(root, tmp_path):
    with create(root) as journal:
        with journal.claim(JOB, ENVELOPE):
            pass
    with pytest.raises(SandboxError, match='host_identity'):
        DurableExecutionJournal(root, host_boot_id=NEXT_BOOT, host_id='e' * 64)
    clone = (tmp_path / 'copied').resolve()
    shutil.copytree(root, clone)
    clone.chmod(0o700)
    with pytest.raises(SandboxError, match='journal_path'):
        create(clone)
    (root / 'identity.json').unlink()
    with pytest.raises(SandboxError, match='journal_integrity'):
        create(root)


def test_live_fd_must_still_refer_to_original_lock(journal):
    lease = journal.claim(JOB, ENVELOPE)
    os.close(lease._fd)
    with pytest.raises(SandboxError, match='fence_lost'):
        lease.require_current()
    lease.close()


def test_event_hashes_bind_identity_epoch_boot_clock_and_exact_json(journal):
    with journal.claim(JOB, ENVELOPE) as lease:
        event = lease.append('observed', {'text': 'Δ', 'integer': 2**63 - 1})
        document = {key: getattr(event, key) for key in event.__dataclass_fields__ if key != 'sha256'}
        encoded = json.dumps(document, ensure_ascii=False, allow_nan=False,
                             sort_keys=True, separators=(',', ':')).encode()
        assert hashlib.sha256(encoded).hexdigest() == event.sha256
        assert event.previous_sha256 == lease.snapshot().events[0].sha256


def test_sqlite_write_contention_fails_closed_without_stealing_fence(journal, root):
    with journal.claim(JOB, ENVELOPE) as lease:
        connection = sqlite3.connect(root / 'journal.sqlite3')
        try:
            connection.execute('BEGIN IMMEDIATE')
            with pytest.raises(SandboxError, match='journal_busy'):
                lease.append('blocked', {})
        finally:
            connection.rollback()
            connection.close()
        assert len(lease.require_current().events) == 1
        lease.append('not_retried_automatically', {})


def test_journal_close_revokes_all_local_effect_handles(journal):
    lease = journal.claim(JOB, ENVELOPE)
    journal.close()
    journal.close()
    with pytest.raises(SandboxError, match='fence_lost'):
        lease.require_current()


@pytest.mark.parametrize('version,safe', [
    ((3, 7, 0), False), ((3, 44, 5), False), ((3, 44, 6), True),
    ((3, 44, 7), True), ((3, 45, 1), False), ((3, 49, 2), False),
    ((3, 50, 6), False), ((3, 50, 7), True), ((3, 51, 2), False),
    ((3, 51, 3), True), ((3, 52, 0), True), ((3, 53, 4), True),
])
def test_known_fixed_sqlite_release_gate(version, safe):
    assert module._safe_sqlite_version(version) is safe


def driver(runtime_version, *, advertised='99.99.99', without_limits=False):
    """Trusted test driver proxy; actual durability cases use real stdlib only."""
    result = ModuleType('c23_test_operator_sqlite_driver')
    result.Row, result.Error = sqlite3.Row, sqlite3.Error
    result.sqlite_version = advertised
    result.sqlite_version_info = tuple(map(int, advertised.split('.')))

    class Connection:
        def __init__(self, actual):
            object.__setattr__(self, '_actual', actual)

        def __getattr__(self, name):
            if without_limits and name in {'setlimit', 'getlimit'}:
                raise AttributeError(name)
            return getattr(self._actual, name)

        def __setattr__(self, name, value):
            setattr(self._actual, name, value)

        def execute(self, sql, *args):
            if sql == 'SELECT sqlite_version()':
                return self._actual.execute('SELECT ?', (runtime_version,))
            return self._actual.execute(sql, *args)

    result.connect = lambda *args, **kwargs: Connection(sqlite3.connect(*args, **kwargs))
    return result


def test_unsafe_queried_sqlite_version_denied_before_creating_control_files(tmp_path):
    root = (tmp_path / 'control').resolve()
    root.mkdir(mode=0o700)
    with pytest.raises(SandboxError, match='journal_sqlite_version'):
        DurableExecutionJournal(root, host_boot_id=BOOT, host_id=HOST,
                               sqlite_module=driver('3.51.2', advertised='99.99.99'))
    assert list(root.iterdir()) == []


def test_trusted_driver_selection_queries_real_connection_not_module_metadata(root):
    with DurableExecutionJournal(root, host_boot_id=BOOT, host_id=HOST,
                                 sqlite_module=driver(sqlite3.sqlite_version, advertised='3.0.0')) as journal:
        assert journal.sqlite_runtime_version == sqlite3.sqlite_version
        with journal.claim(JOB, ENVELOPE) as lease:
            lease.finish({'test_driver_selection_only': True})
        assert journal.read(JOB, ENVELOPE).terminal


@pytest.mark.parametrize('invalid', [None, True, object(), ModuleType('empty')])
def test_sqlite_driver_is_trusted_explicit_module_not_duck_typed(tmp_path, invalid):
    with pytest.raises(SandboxError, match='journal_sqlite_driver'):
        DurableExecutionJournal(tmp_path.resolve(), host_boot_id=BOOT, host_id=HOST,
                               sqlite_module=invalid)


def test_clock_failure_does_not_revoke_live_effect_fence(journal):
    with journal.claim(JOB, ENVELOPE) as lease:
        lease.append('create_intent', {})

        def broken():
            raise OSError('clock unavailable')

        journal._clock_ns = broken
        with pytest.raises(SandboxError, match='journal_clock'):
            lease.append('unrecorded', {})
        assert lease.require_current().epoch == 1
        assert lease.snapshot().result is None


def test_driver_without_setlimit_uses_bounded_sql_readback(root):
    with DurableExecutionJournal(root, host_boot_id=BOOT, host_id=HOST,
                                 sqlite_module=driver(sqlite3.sqlite_version, without_limits=True)) as journal:
        assert journal.sqlite_readback_bounds == 'bounded-sql-projections'
        with journal.claim(JOB, ENVELOPE) as lease:
            lease.append('observed', {'safe': True})
            lease.finish({'state': 'control_record'})
        assert journal.read(JOB, ENVELOPE).terminal


@pytest.mark.parametrize('target', ['payload', 'result'])
def test_driver_without_setlimit_never_transfers_oversized_rows_to_python(root, target, monkeypatch):
    with DurableExecutionJournal(root, host_boot_id=BOOT, host_id=HOST,
                                 sqlite_module=driver(sqlite3.sqlite_version, without_limits=True)) as journal:
        with journal.claim(JOB, ENVELOPE) as lease:
            lease.finish({'state': 'control_record'})
        table = 'events' if target == 'payload' else 'results'
        column = 'payload_json' if target == 'payload' else 'document_json'
        maximum = module.MAX_PAYLOAD_BYTES if target == 'payload' else module.MAX_RESULT_BYTES
        trigger = f'{table}_no_update'
        with sqlite3.connect(root / 'journal.sqlite3') as connection:
            # Deliberate privileged-database corruption, outside the sandbox.
            connection.execute('PRAGMA ignore_check_constraints=ON')
            connection.execute(f'DROP TRIGGER {trigger}')
            connection.execute(f'UPDATE {table} SET {column}=?', ('X' * (maximum + 1),))
            connection.execute(module._TRIGGERS[trigger])
        decode = module._decode

        def bounded(text, limit):
            assert text is None or len(text.encode()) <= limit
            return decode(text, limit)

        monkeypatch.setattr(module, '_decode', bounded)
        with pytest.raises(SandboxError, match='journal_limit'):
            journal.read(JOB, ENVELOPE)


def test_payload_hash_bound_accounts_for_escaped_json_overhead(journal):
    payload = {'escaped': '\\' * 32750}
    assert len(json.dumps(payload, separators=(',', ':')).encode()) < module.MAX_PAYLOAD_BYTES
    with journal.claim(JOB, ENVELOPE) as lease:
        assert lease.append('bounded_escape', payload).payload == payload


def test_closing_an_independent_journal_does_not_cancel_live_sqlite_posix_locks(root):
    # Regression for sqlite.org/howtocorrupt.html §2.2. Closing an unrelated
    # raw FD on the same database inode cancels all this process's POSIX locks,
    # including locks owned by another real SQLite connection. Probe the real
    # SHAREDFIRST byte from separate processes before and after second.close().
    with create(root) as first:
        second = create(root)
        try:
            with first._connection(write=True):
                assert probe_database_lock(root) == 'blocked'
                second.close()
                assert probe_database_lock(root) == 'blocked'
            assert probe_database_lock(root) == 'acquired'
        finally:
            second.close()


def test_one_live_database_cannot_mix_independent_driver_modules(root):
    with create(root) as journal:
        alias = driver(sqlite3.sqlite_version)
        with pytest.raises(SandboxError, match='journal_sqlite_driver'):
            DurableExecutionJournal(root, host_boot_id=BOOT, host_id=HOST, sqlite_module=alias)
        with journal.claim(JOB, ENVELOPE) as lease:
            lease.append('same_driver_remains_valid', {})
    # A deliberate driver replacement requires every previous object/connection
    # to be closed first; the root itself is retained and reconciled.
    with DurableExecutionJournal(root, host_boot_id=BOOT, host_id=HOST, sqlite_module=alias) as replacement:
        with replacement.claim(JOB, ENVELOPE) as lease:
            assert lease.epoch == 2 and lease.reconciliation_required


def test_mutating_the_trusted_driver_binding_cannot_replace_a_live_engine(root):
    selected = driver(sqlite3.sqlite_version)
    with DurableExecutionJournal(root, host_boot_id=BOOT, host_id=HOST, sqlite_module=selected) as journal:
        selected.connect = sqlite3.connect
        with pytest.raises(SandboxError, match='journal_sqlite_driver'):
            journal.read(JOB, ENVELOPE)


def test_fork_from_multithreaded_controller_never_waits_on_parent_mutex(journal):
    held, release = threading.Event(), threading.Event()

    def hold_parent_mutex():
        with journal._mutex:
            held.set()
            release.wait(10)

    with journal.claim(JOB, ENVELOPE) as lease:
        thread = threading.Thread(target=hold_parent_mutex)
        thread.start()
        assert held.wait(3)
        read_fd, write_fd = os.pipe()
        with warnings.catch_warnings():
            warnings.simplefilter('ignore', DeprecationWarning)  # Deliberate fork safety regression.
            pid = os.fork()
        if pid == 0:
            os.close(read_fd)
            try:
                for action in (lambda: journal.read(JOB, ENVELOPE),
                               lambda: journal.claim(JOB, ENVELOPE), journal.close,
                               lease.require_current):
                    try:
                        action()
                    except SandboxError as error:
                        if error.reason != 'sandbox_fence_lost':
                            os.write(write_fd, b'wrong_error')
                            break
                    else:
                        os.write(write_fd, b'authority_inherited')
                        break
                else:
                    os.write(write_fd, b'all_fences_denied')
            finally:
                os.close(write_fd)
                os._exit(0)
        os.close(write_fd)
        waited = False
        try:
            assert select.select([read_fd], [], [], 3)[0], 'child hung on inherited parent mutex'
            assert os.read(read_fd, 256) == b'all_fences_denied'
            assert os.waitpid(pid, 0)[1] == 0
            waited = True
        finally:
            if not waited:
                try:
                    os.kill(pid, 9)
                except ProcessLookupError:
                    pass
                os.waitpid(pid, 0)
            os.close(read_fd)
            release.set()
            thread.join(5)
        assert not thread.is_alive()
        assert lease.require_current().epoch == 1
