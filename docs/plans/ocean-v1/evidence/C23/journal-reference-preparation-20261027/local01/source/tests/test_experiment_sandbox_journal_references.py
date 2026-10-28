"""Actual held-lease SQLite read references; no runtime or physical authority."""
from copy import copy
from dataclasses import FrozenInstanceError, fields, replace
import hashlib
import json
import os
import select
import sqlite3
import threading
import uuid
import warnings

import pytest

from orchestration.experiment_sandbox.contracts import SandboxError
from orchestration.experiment_sandbox import journal as module
from orchestration.experiment_sandbox.journal import (
    DurableJournalIdentityReference, DurableLease, DurableTerminalReference,
)
from tests import test_experiment_sandbox_journal as legacy

root, journal = legacy.root, legacy.journal
JOB, OTHER_JOB, ENVELOPE = legacy.JOB, legacy.OTHER_JOB, legacy.ENVELOPE
BOOT, NEXT_BOOT, HOST = legacy.BOOT, legacy.NEXT_BOOT, legacy.HOST
create, raw, Clock = legacy.create, legacy.raw, legacy.Clock
METHODS = ('identity_reference', 'terminal_reference')


@pytest.fixture
def finished(journal):
    with journal.claim(JOB, ENVELOPE) as lease:
        lease.append('create_intent', {'fixture': 'local journal readback only'})
        lease.finish({'state': 'control_record', 'label': '海洋', 'nested': {'value': 7}})
        yield lease


def test_identity_and_terminal_references_bind_same_validated_marker_and_snapshot(journal, root, finished):
    identity = journal.identity_reference(finished)
    terminal = journal.terminal_reference(finished)
    marker = json.loads((root / 'identity.json').read_text())
    snapshot = finished.require_current()
    stored, digest, sequence, head = raw(root,
        'SELECT document_json,sha256,event_sequence,event_sha256 FROM results WHERE job_id=?', (JOB,))[0]
    assert type(identity) is DurableJournalIdentityReference
    assert type(terminal) is DurableTerminalReference
    assert identity.journal_id == terminal.journal_id == marker['journal_id']
    assert str(uuid.UUID(identity.journal_id)) == identity.journal_id
    assert identity.job_id == terminal.job_id == JOB
    assert identity.envelope_sha256 == terminal.envelope_sha256 == ENVELOPE
    assert identity.epoch == terminal.epoch == finished.epoch == snapshot.epoch
    assert identity.host_id == terminal.host_id == HOST
    assert identity.configured_host_boot_id == terminal.configured_host_boot_id == BOOT
    assert identity.event_host_boot_id == terminal.event_host_boot_id == BOOT
    assert identity.sequence == terminal.terminal_sequence == sequence == snapshot.events[-1].sequence
    assert identity.head_sha256 == terminal.terminal_head_sha256 == head == snapshot.events[-1].sha256
    assert identity.monotonic_ns == terminal.terminal_recorded_monotonic_ns == snapshot.events[-1].monotonic_ns
    assert terminal.terminal_result_sha256 == digest == hashlib.sha256(stored.encode('utf-8')).hexdigest()
    record = json.dumps(json.loads(stored)['record'], ensure_ascii=False, sort_keys=True, separators=(',', ':'))
    assert terminal.terminal_result_sha256 != hashlib.sha256(record.encode('utf-8')).hexdigest()
    assert snapshot.events[-1].payload == {'result_sha256': terminal.terminal_result_sha256}


@pytest.mark.parametrize('kind',[DurableJournalIdentityReference, DurableTerminalReference])
def test_reference_constructors_are_private_and_values_are_frozen_scalars(journal, finished, kind):
    method = journal.identity_reference if kind is DurableJournalIdentityReference else journal.terminal_reference
    reference = method(finished)
    with pytest.raises(TypeError):
        kind(**{field.name: getattr(reference, field.name) for field in fields(reference)})
    with pytest.raises(TypeError):
        replace(reference, epoch=999)
    with pytest.raises(FrozenInstanceError):
        reference.epoch = 999
    assert all(type(getattr(reference, field.name)) in {str, int} for field in fields(reference))
    assert not hasattr(reference, '__dict__')
    assert not any(isinstance(getattr(reference, field.name), DurableLease) for field in fields(reference))


def test_references_do_not_mutate_history_and_remain_detached_after_lease_close(journal, finished):
    before = finished.require_current()
    first = journal.identity_reference(finished)
    terminal = journal.terminal_reference(finished)
    assert journal.identity_reference(finished) == first
    assert journal.terminal_reference(finished) == terminal
    assert finished.require_current() == before
    finished.close()
    assert first.head_sha256 == terminal.terminal_head_sha256 == before.events[-1].sha256
    for method in METHODS:
        with pytest.raises(SandboxError, match='fence_lost'):
            getattr(journal, method)(finished)
        for detached in (first, terminal, copy(first), copy(terminal)):
            with pytest.raises(SandboxError, match='fence_lost'):
                getattr(journal, method)(detached)
    assert journal.read(JOB, ENVELOPE) == before


def test_nonterminal_cannot_supply_a_terminal_reference(journal):
    with journal.claim(JOB, ENVELOPE) as lease:
        lease.append('termination_verified', {'populated': 0, 'caller_claim_only': True})
        assert journal.identity_reference(lease).sequence == 2
        with pytest.raises(SandboxError, match='journal_not_terminal'):
            journal.terminal_reference(lease)
        assert not lease.snapshot().terminal


def test_same_boot_recovery_and_terminal_reacquisition_preserve_exact_references(root):
    with create(root, clock_ns=Clock(100)) as journal:
        with journal.claim(JOB, ENVELOPE) as initial:
            original = journal.identity_reference(initial)
            initial.append('start_intent', {})
        with journal.claim(JOB, ENVELOPE) as recovered:
            assert recovered.epoch == 2 and recovered.reconciliation_required
            recovered.finish({'state': 'control_record_only'})
            terminal = journal.terminal_reference(recovered)
            identity = journal.identity_reference(recovered)
            assert terminal.epoch == 2 and original.epoch == 1
    with create(root, clock_ns=Clock(200)) as reopened:
        with reopened.claim(JOB, ENVELOPE) as replay:
            assert replay.epoch == 2
            assert reopened.terminal_reference(replay) == terminal
            assert reopened.identity_reference(replay) == identity
            assert reopened.identity_reference(replay).journal_id == original.journal_id


def test_prior_boot_terminal_is_readable_but_cannot_supply_terminal_reference(root):
    with create(root, clock_ns=Clock(100)) as journal:
        with journal.claim(JOB, ENVELOPE) as lease:
            lease.finish({'state': 'prior_boot_record'})
            previous = journal.terminal_reference(lease)
    with create(root, host_boot_id=NEXT_BOOT, clock_ns=Clock(1)) as reopened:
        before = reopened.read(JOB, ENVELOPE)
        with reopened.claim(JOB, ENVELOPE) as lease:
            identity = reopened.identity_reference(lease)
            assert identity.configured_host_boot_id == NEXT_BOOT
            assert identity.event_host_boot_id == BOOT
            assert identity.epoch == previous.epoch == 1
            with pytest.raises(SandboxError, match='journal_boot_continuity'):
                reopened.terminal_reference(lease)
        assert reopened.read(JOB, ENVELOPE) == before


def test_mixed_boot_finished_chain_is_readable_but_cannot_supply_terminal_reference(root):
    with create(root, clock_ns=Clock(100)) as journal:
        with journal.claim(JOB, ENVELOPE) as lease:
            lease.append('start_intent', {})
    with create(root, host_boot_id=NEXT_BOOT, clock_ns=Clock(1)) as rebooted:
        with rebooted.claim(JOB, ENVELOPE) as lease:
            assert lease.epoch == 2
            lease.finish({'state': 'mixed_boot_record'})
            identity = rebooted.identity_reference(lease)
            assert identity.configured_host_boot_id == identity.event_host_boot_id == NEXT_BOOT
            assert {event.host_boot_id for event in lease.snapshot().events} == {BOOT, NEXT_BOOT}
            with pytest.raises(SandboxError, match='journal_boot_continuity'):
                rebooted.terminal_reference(lease)
            assert rebooted.read(JOB, ENVELOPE).terminal


@pytest.mark.parametrize('method', METHODS)
@pytest.mark.parametrize('fake',[None, True, {'epoch': 1}, object.__new__(DurableLease)])
def test_actual_registered_lease_required(journal, finished, method, fake):
    with pytest.raises(SandboxError, match='fence_lost'):
        getattr(journal, method)(fake)


@pytest.mark.parametrize('method', METHODS)
def test_copied_subclassed_foreign_and_pid_changed_lease_denied(journal, root, finished, method):
    class Forged(DurableLease):
        pass

    with create(root) as other:
        with pytest.raises(SandboxError, match='fence_lost'):
            getattr(other, method)(finished)
    for kind in (DurableLease, Forged):
        forged = object.__new__(kind)
        for slot in DurableLease.__slots__:
            setattr(forged, slot, getattr(finished, slot))
        with pytest.raises(SandboxError, match='fence_lost'):
            getattr(journal, method)(forged)
    pid = finished._pid
    try:
        finished._pid = pid + 1
        with pytest.raises(SandboxError, match='fence_lost'):
            getattr(journal, method)(finished)
    finally:
        finished._pid = pid
    assert getattr(journal, method)(finished).epoch == 1


@pytest.mark.parametrize('method', METHODS)
def test_stale_epoch_and_replaced_lock_cannot_supply_references(journal, root, finished, method):
    epoch = finished._epoch
    try:
        finished._epoch = epoch + 1
        with pytest.raises(SandboxError, match='fence_lost'):
            getattr(journal, method)(finished)
    finally:
        finished._epoch = epoch
    lock = root / 'locks' / (JOB + '.lock')
    lock.rename(root / 'locks' / 'original.lock')
    lock.touch(mode=0o600)
    with pytest.raises(SandboxError, match='fence_lost'):
        getattr(journal, method)(finished)


@pytest.mark.parametrize('method', METHODS)
def test_closed_journal_cannot_supply_references(journal, finished, method):
    journal.close()
    with pytest.raises(SandboxError, match='fence_lost'):
        getattr(journal, method)(finished)


@pytest.mark.parametrize('method', METHODS)
@pytest.mark.parametrize('target',['marker','metadata','chain','result'])
def test_tampered_control_identity_chain_and_result_rejected(journal, root, finished, method, target):
    if target == 'marker':
        marker = json.loads((root / 'identity.json').read_text())
        marker['journal_id'] = str(uuid.uuid4())
        (root / 'identity.json').write_text(module._encode(marker, 4096))
    else:
        table, column = {'metadata': ('metadata','value'), 'chain': ('events','payload_json'),
                         'result': ('results','document_json')}[target]
        trigger = f'{table}_no_update'
        with sqlite3.connect(root / 'journal.sqlite3') as connection:
            connection.execute(f'DROP TRIGGER {trigger}')
            connection.execute(f'UPDATE {table} SET {column}=?', ('{}',))
            connection.execute(module._TRIGGERS[trigger])
    with pytest.raises(SandboxError, match='journal_integrity'):
        getattr(journal, method)(finished)


def test_journal_uuid_is_validated_from_matching_marker_and_metadata(root):
    with create(root) as initial:
        with initial.claim(JOB, ENVELOPE) as lease:
            lease.finish({'state': 'control_record_only'})
    marker = json.loads((root / 'identity.json').read_text())
    marker['journal_id'] = 'not-a-journal-uuid'
    encoded = module._encode(marker, 4096)
    (root / 'identity.json').write_text(encoded)
    with sqlite3.connect(root / 'journal.sqlite3') as connection:
        connection.execute('DROP TRIGGER metadata_no_update')
        connection.execute("UPDATE metadata SET value=? WHERE key='identity'", (encoded,))
        connection.execute(module._TRIGGERS['metadata_no_update'])
    # Existing read/claim behavior is retained. New typed references additionally
    # reject this privileged-corruption fixture's malformed marker UUID.
    with create(root) as reopened:
        assert reopened.read(JOB, ENVELOPE).terminal
        with reopened.claim(JOB, ENVELOPE) as lease:
            for method in METHODS:
                with pytest.raises(SandboxError, match='journal_integrity'):
                    getattr(reopened, method)(lease)


def test_forked_child_never_inherits_reference_access_or_parent_mutex(journal, finished):
    held, release = threading.Event(), threading.Event()

    def hold_mutex():
        with journal._mutex:
            held.set()
            release.wait(10)

    thread = threading.Thread(target=hold_mutex)
    thread.start()
    assert held.wait(3)
    read_fd, write_fd = os.pipe()
    with warnings.catch_warnings():
        warnings.simplefilter('ignore', DeprecationWarning)
        pid = os.fork()
    if pid == 0:
        os.close(read_fd)
        try:
            for method in METHODS:
                try:
                    getattr(journal, method)(finished)
                except SandboxError as error:
                    if error.reason != 'sandbox_fence_lost':
                        os.write(write_fd, b'wrong_error')
                        break
                else:
                    os.write(write_fd, b'inherited_reference_access')
                    break
            else:
                os.write(write_fd, b'all_reference_access_denied')
        finally:
            os.close(write_fd)
            os._exit(0)
    os.close(write_fd)
    waited = False
    try:
        assert select.select([read_fd], [], [], 3)[0], 'child waited on inherited parent mutex'
        assert os.read(read_fd, 256) == b'all_reference_access_denied'
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
    assert journal.terminal_reference(finished).epoch == 1


def test_closed_old_lease_never_regains_reference_access_after_actual_reacquisition(journal):
    first = journal.claim(JOB, ENVELOPE)
    detached = journal.identity_reference(first)
    first.close()
    with journal.claim(JOB, ENVELOPE) as recovered:
        recovered.finish({'state': 'recovered_control_record'})
        assert journal.terminal_reference(recovered).epoch == 2
        assert detached.epoch == 1
        for method in METHODS:
            with pytest.raises(SandboxError, match='fence_lost'):
                getattr(journal, method)(first)


@pytest.mark.parametrize('method', METHODS)
def test_closed_original_lock_descriptor_cannot_supply_reference(journal, finished, method):
    os.close(finished._fd)
    with pytest.raises(SandboxError, match='fence_lost'):
        getattr(journal, method)(finished)
