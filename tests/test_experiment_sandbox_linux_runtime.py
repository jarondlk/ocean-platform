"""Host-safe C23 runtime control tests; every runtime effect is mocked.

No generated analysis, runsc binary, watchdog process or real cgroup is launched.
These cases do not establish actual Linux/gVisor containment.
"""
from contextlib import contextmanager
from copy import deepcopy
import base64
import hashlib
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from orchestration.experiment_sandbox import linux_runtime as runtime
from orchestration.experiment_sandbox.contracts import SandboxError
from orchestration.experiment_sandbox.profile_execution import render_execution_profile
from sandbox.experiment.trusted_init import VERSION as INIT_VERSION, encode_frame
from schema.context_catalogue import canonical_json
from schema.research_experiments import content_sha256
from tests.test_experiment_sandbox_contracts import approved_envelope as _retained_fixture
from tests.test_experiment_sandbox_profile_execution import layout as _profile_fixture

approved_envelope = _retained_fixture
layout = _profile_fixture
_actual_arm_watchdog = runtime._arm_watchdog


class FakeJournal:
    host_boot_id = '11111111-1111-1111-1111-111111111111'

    def __init__(self):
        self.events, self.result, self.claims, self.held = [], None, 0, False
        self.failure, self.lost = None, False

    @contextmanager
    def claim(self, *_):
        self.claims += 1
        self.held = True
        try:
            yield self
        finally:
            self.held = False

    def require_current(self):
        assert self.held, 'all runtime effects must retain the effect lease'
        if self.lost:
            raise SandboxError('sandbox_fence_lost')
        return self.snapshot()

    def snapshot(self):
        return SimpleNamespace(terminal=self.result is not None,
            result={'record': deepcopy(self.result)} if self.result else None,
            reconciliation_required=self.claims > 1 and self.result is None,
            events=tuple(self.events))

    def append(self, kind, payload):
        self.require_current()
        if self.failure == kind:
            raise SandboxError('sandbox_journal_unavailable')
        self.events.append(SimpleNamespace(kind=kind, payload=deepcopy(payload)))

    def finish(self, record):
        self.require_current()
        if self.failure == 'finish':
            raise SandboxError('sandbox_journal_unavailable')
        self.result = deepcopy(record)


class FakeCapture:
    def __init__(self, raw):
        self.stdout, self.stderr = bytearray(raw), bytearray()
        self.eof, self.closed = True, False
        self.process = SimpleNamespace(poll=lambda: 0)

    def drain(self):
        return None

    def close(self):
        self.closed = True


class FakeWatchdog:
    pid = 12345

    def __init__(self):
        self.stopped = []

    def stop(self, *, proven):
        self.stopped.append(proven)

    def require_alive(self):
        return None


class MockAdapter(runtime.LinuxExecutionAdapter):
    def __init__(self, worker, manifest, journal, document):
        super().__init__(worker, worker / 'inert-runtime', manifest, journal,
            cgroup_root=worker / 'mock-cgroup-NOT-KERNEL')
        self.calls, self.document, self.inject, self.frame_change = [], document, None, None
        self.delete_ack, self.guest_outcome, self.wait_status = True, 'completed', 0

    def _preflight(self, envelope, profile):
        return self.worker_root / envelope.job_id, profile.document, content_sha256(json.loads(self._runtime_json))

    def _prepare_cgroups(self, job_id, requirements):
        self.journal.require_current()
        self.calls.append('cgroups')
        self._paths(job_id)[1].mkdir(parents=True)
        return (17, 23)

    def _frame(self):
        policy = self.document['trusted_init']['policy']
        raw = b'{"columns":["value"],"rows":[[1]]}'
        files = {'summary.json': base64.b64encode(raw).decode()}
        document = {'version': INIT_VERSION, 'job_id': policy['job_id'],
            'envelope_sha256': policy['envelope_sha256'], 'outcome': self.guest_outcome,
            'reason': 'completed' if self.guest_outcome == 'completed' else 'analysis_failed',
            'analysis_exit_code': 0 if self.guest_outcome == 'completed' else 1,
            'writers_reaped': True, 'files': files if self.guest_outcome == 'completed' else {},
            'logs': {'stdout': base64.b64encode(b'analysis log\n').decode(), 'stderr': ''}}
        if callable(self.frame_change):
            self.frame_change(document)
        raw = encode_frame(document, max_output_bytes=policy['max_output_bytes'])
        return raw + b'corrupt' if self.frame_change == 'trailing' else raw

    def _spawn(self, argv, host, *, deadline, frame_limit=runtime.MAX_COMMAND_BYTES):
        self.journal.require_current()
        assert argv[-3] == 'create' and argv[-2].startswith('--bundle=')
        self.calls.append('create')
        if self.inject == 'create':
            raise OSError('mock lost create acknowledgement')
        return FakeCapture(self._frame())

    def _readback(self, envelope, document, lease, argv, **_):
        lease.require_current()
        self.calls.append('readback')
        if self.inject == 'readback':
            raise SandboxError('sandbox_resource_enforcement')
        return {'mock': 'not-real-enforcement'}

    def _command(self, argv, host, **_):
        self.journal.require_current()
        command = argv[-2]
        self.calls.append(command)
        if self.inject == command:
            raise SandboxError('sandbox_wall_limit' if command == 'wait' else 'sandbox_start_uncertain')
        if command == 'wait':
            return 0, json.dumps({'id': argv[-1], 'exitStatus': self.wait_status}).encode(), b''
        return 0, b'', b''

    def _cleanup(self, envelope, argv, identity, lease, *, side=None):
        lease.require_current()
        self.calls.append('cleanup')
        if self.inject == 'cleanup':
            raise SandboxError('sandbox_termination_uncertain')
        return {'host_boot_id': self.journal.host_boot_id,
            'cgroup_path': '/ocean-c23/' + envelope.job_id,
            'cgroup_device': identity[0], 'cgroup_inode': identity[1], 'populated': 0,
            'whole_host_subtree_empty': True, 'runtime_delete_acknowledged': self.delete_ack}


@pytest.fixture
def control(layout, monkeypatch):
    envelope, options, _ = layout
    profile = render_execution_profile(envelope, **options)
    journal = FakeJournal()
    adapter = MockAdapter(options['job_root'].parent, options['runtime_manifest'], journal, profile.document)
    watchdog = FakeWatchdog()
    monkeypatch.setattr(runtime, '_require_linux_host', lambda *_: None)
    monkeypatch.setattr(runtime, '_arm_watchdog', lambda *_: watchdog)
    return adapter, envelope, profile, journal, watchdog


def execute(control, *, admission=None, cancelled=lambda: False):
    adapter, envelope, profile, _, _ = control
    return adapter.run(envelope, profile,
        admission=admission or (lambda value: value.envelope_sha256), cancelled=cancelled)


def test_completed_control_is_ordered_retained_and_never_releases(control, approved_envelope):
    adapter, envelope, profile, journal, watchdog = control
    result = execute(control)
    assert result.state == 'completed'
    assert adapter.calls == ['cgroups', 'create', 'readback', 'start', 'wait', 'cleanup']
    assert result.outputs.files['summary.json'] == b'{"columns":["value"],"rows":[[1]]}'
    assert result.document['dispatch_eligible'] is False and result.document['reservation_released'] is False
    assert result.document['runtime_acceptance_verified'] is False
    assert result.document['declared_seeds'] == envelope.proposal['seeds']
    assert result.document['analysis_exit_code'] == 0 and result.document['host_runtime_exit_status'] == 0
    assert result.document['profile_sha256'] == profile.profile_sha256
    assert journal.result and not journal.held and watchdog.stopped == [True]
    assert not approved_envelope[3].exists()


def test_terminal_replay_verifies_bytes_and_fresh_admission_without_rerun(control):
    adapter, _, _, _, _ = control
    first = execute(control)
    calls, admissions = adapter.calls.copy(), []
    replayed = execute(control, admission=lambda value: admissions.append(value.envelope_sha256) or value.envelope_sha256)
    assert adapter.calls == calls and replayed.document['replayed'] is True
    assert replayed.outputs.manifest_bytes == first.outputs.manifest_bytes and len(admissions) == 2


def test_replay_rejects_tampered_retained_outputs(control):
    adapter, envelope, _, _, _ = control
    execute(control)
    path = adapter.worker_root / envelope.job_id / 'retained/files/summary.json'
    path.chmod(0o600)
    path.write_bytes(b'{"columns":["changed"],"rows":[[2]]}')
    path.chmod(0o400)
    with pytest.raises(SandboxError, match='sandbox_retention_integrity'):
        execute(control)
    assert adapter.calls.count('create') == 1



def test_create_transport_body_is_not_duplicated_in_private_diagnostics(control):
    adapter, envelope, _, _, _ = control
    result = execute(control)
    directory = adapter.worker_root / envelope.job_id / 'diagnostics'
    entries = list(directory.iterdir())
    assert len(entries) == 1 and entries[0].name.startswith('create-')
    metadata = json.loads((entries[0] / 'metadata.json').read_text())
    assert metadata['stdout']['body_retained'] is False and not (entries[0] / 'stdout.bin').exists()
    assert metadata['stdout']['captured_sha256'] == result.document['frame_sha256']
    assert metadata['exit_status_observed'] == 0 and metadata['private_operator_evidence_only'] is True
    assert metadata['dispatch_eligible'] is False and metadata['reservation_released'] is False
    assert entries[0].stat().st_mode & 0o777 == 0o700
    assert (entries[0] / 'stderr.bin').stat().st_mode & 0o777 == 0o400


def test_failed_create_retains_runtime_stderr_exit_and_stage(control, monkeypatch):
    adapter, envelope, _, journal, _ = control
    original = adapter._spawn
    def spawn(*args, **kwargs):
        capture = original(*args, **kwargs)
        capture.stderr = bytearray(b'mock runtime: unsupported fixed flag\n')
        capture.process.poll = lambda: 1
        return capture
    monkeypatch.setattr(adapter, '_spawn', spawn)
    result = execute(control)
    assert result.state == 'uncertain' and result.outputs is None and journal.result is None
    entry = next((adapter.worker_root / envelope.job_id / 'diagnostics').iterdir())
    metadata = json.loads((entry / 'metadata.json').read_text())
    assert metadata['stage'] == 'create' and metadata['exit_status_observed'] == 1
    assert (entry / 'stderr.bin').read_bytes() == b'mock runtime: unsupported fixed flag\n'
    assert metadata['stderr']['retained_sha256'] == hashlib.sha256((entry / 'stderr.bin').read_bytes()).hexdigest()


def test_control_command_retains_bounded_stdout_and_stderr(control, monkeypatch):
    adapter, envelope, _, journal, _ = control
    capture = FakeCapture(b'{"id":"mock only"}')
    capture.stderr.extend(b'mock diagnostic\n')
    monkeypatch.setattr(adapter, '_spawn', lambda *_args, **_kwargs: capture)
    with journal.claim(envelope.job_id, envelope.envelope_sha256):
        code, stdout, stderr = runtime.LinuxExecutionAdapter._command(adapter,
            ['inert-runsc', 'state', envelope.job_id], Path('/unused'),
            deadline=adapter.clock() + 1, lease=journal)
    assert code == 0 and stdout == b'{"id":"mock only"}' and stderr == b'mock diagnostic\n'
    entry = next((adapter.worker_root / envelope.job_id / 'diagnostics').iterdir())
    metadata = json.loads((entry / 'metadata.json').read_text())
    assert metadata['stage'] == 'state' and metadata['stdout']['body_retained'] is True
    assert (entry / 'stdout.bin').read_bytes() == stdout
    assert (entry / 'stderr.bin').read_bytes() == stderr


def test_private_diagnostics_do_not_persist_over_cap_bytes(control):
    adapter, envelope, _, journal, _ = control
    capture = FakeCapture(b'x' * (runtime.MAX_COMMAND_BYTES + 1))
    capture.stderr = bytearray(b'y' * (runtime.MAX_RUNTIME_STDERR + 1))
    with journal.claim(envelope.job_id, envelope.envelope_sha256):
        adapter._diagnose(['inert-runsc', 'wait', envelope.job_id], capture, journal)
    entry = next((adapter.worker_root / envelope.job_id / 'diagnostics').iterdir())
    metadata = json.loads((entry / 'metadata.json').read_text())
    assert (entry / 'stdout.bin').stat().st_size == runtime.MAX_COMMAND_BYTES
    assert (entry / 'stderr.bin').stat().st_size == runtime.MAX_RUNTIME_STDERR
    assert metadata['stdout']['truncated'] is True and metadata['stderr']['truncated'] is True


def test_closing_capture_is_not_fabricated_pipe_eof():
    read_out, write_out = os.pipe()
    read_err, write_err = os.pipe()
    capture = runtime._Capture(SimpleNamespace(stdout=os.fdopen(read_out, 'rb'),
        stderr=os.fdopen(read_err, 'rb')), stdout_limit=4, stderr_limit=4)
    try:
        assert capture.eof is False
        capture.close()
        capture.close()
        assert capture.eof is False
    finally:
        os.close(write_out)
        os.close(write_err)


def test_diagnostic_retention_failure_prevents_publication(control, monkeypatch):
    adapter, _, _, journal, _ = control
    def unavailable(*_):
        raise OSError('mock unavailable private evidence storage')
    monkeypatch.setattr(adapter, '_diagnose', unavailable)
    result = execute(control)
    assert result.state == 'uncertain' and result.outputs is None and journal.result is None
    assert adapter.calls[-1] == 'cleanup'


def test_cleanup_kill_and_empty_readback_survive_delete_diagnostic_failure(control, monkeypatch):
    adapter, envelope, _, journal, _ = control
    outer, host, _ = adapter._paths(envelope.job_id)
    host.mkdir(parents=True)
    (outer / 'cgroup.kill').write_bytes(b'0\n')
    (outer / 'cgroup.events').write_text('populated 0\n')
    identity = outer.stat().st_dev, outer.stat().st_ino
    def unavailable(*_args, **_kwargs):
        raise SandboxError('sandbox_runtime_diagnostic_unavailable')
    monkeypatch.setattr(adapter, '_command', unavailable)
    with journal.claim(envelope.job_id, envelope.envelope_sha256):
        with pytest.raises(SandboxError, match='sandbox_runtime_diagnostic_unavailable'):
            runtime.LinuxExecutionAdapter._cleanup(adapter, envelope,
                ['inert-runtime'], identity, journal)
    assert (outer / 'cgroup.kill').read_bytes() == b'1\n'




@pytest.mark.parametrize('ack', [b'R', b'!'])
def test_watchdog_ready_handshake_is_required_and_only_scoped_fds_are_passed(control, monkeypatch, ack):
    adapter, envelope, _, _, _ = control
    outer = adapter._paths(envelope.job_id)[0]
    outer.mkdir(parents=True)
    (outer / 'cgroup.kill').write_bytes(b'')
    seen = {}
    process = SimpleNamespace(pid=321, poll=lambda: None, wait=lambda **_: None)
    def popen(argv, **kwargs):
        seen.update(argv=argv, kwargs=kwargs, liveness_read=os.dup(kwargs['pass_fds'][1]))
        os.write(kwargs['pass_fds'][2], ack)
        return process
    original_pipe = os.pipe
    with monkeypatch.context() as patch:
        patch.setattr(runtime.sys, 'platform', 'linux')
        patch.setattr(runtime.os, 'geteuid', lambda: 0)
        patch.setattr(runtime.os, 'pipe2', lambda _: original_pipe(), raising=False)
        patch.setattr(runtime.subprocess, 'Popen', popen)
        if ack == b'R':
            watchdog = _actual_arm_watchdog(outer, runtime.time.monotonic() + 5)
            assert seen['argv'][:5] == [runtime.sys.executable, '-I', '-S', '-B', str(Path(runtime.__file__).resolve())]
            assert len(seen['kwargs']['pass_fds']) == 3 and seen['kwargs']['close_fds'] is True
            assert 'preexec_fn' not in seen['kwargs']
            assert watchdog.pipe not in seen['kwargs']['pass_fds']
            watchdog.stop(proven=True)
            assert os.read(seen['liveness_read'], 1) == b'X'
        else:
            with pytest.raises(SandboxError, match='sandbox_watchdog_unavailable'):
                _actual_arm_watchdog(outer, runtime.time.monotonic() + 5)
            assert os.read(seen['liveness_read'], 1) == b''
    os.close(seen['liveness_read'])


@pytest.mark.parametrize('parent_state', ['stop', 'dead'])
def test_watchdog_acknowledges_before_bounded_control_loop(parent_state, tmp_path, monkeypatch):
    job = 'c23-' + '3' * 48
    target = tmp_path / 'fake-cgroup-kill-NOT-KERNEL'
    kill_fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    read_fd, write_fd = os.pipe()
    ready_read, ready_write = os.pipe()
    if parent_state == 'stop':
        os.write(write_fd, b'X')
    else:
        os.close(write_fd)
        write_fd = None
    try:
        with monkeypatch.context() as patch:
            patch.setattr(runtime.sys, 'platform', 'linux')
            patch.setattr(runtime.os, 'getuid', lambda: 0)
            patch.setattr(runtime.os, 'geteuid', lambda: 0)
            patch.setattr(runtime, '_host_helper_fd', lambda *_args, **_kwargs: kill_fd)
            assert runtime._host_helper_main(['--c23-watchdog', str(kill_fd), str(read_fd),
                str(runtime.time.monotonic() + 5), job, str(ready_write)]) == 0
        ready_write = None  # the helper closes its readiness descriptor
        assert os.read(ready_read, 2) == b'R'
        assert target.read_bytes() == (b'' if parent_state == 'stop' else b'1\n')
    finally:
        for fd in (kill_fd, read_fd, write_fd, ready_read, ready_write):
            if fd is not None:
                os.close(fd)


@pytest.mark.parametrize('stage', ['before_join', 'after_join'])
def test_launcher_deadline_fence_prevents_delayed_start_after_watchdog_expiry(stage, monkeypatch):
    job = 'c23-' + '4' * 48
    read_fd, write_fd = os.pipe()
    seen = []
    try:
        with monkeypatch.context() as patch:
            patch.setattr(runtime.sys, 'platform', 'linux')
            patch.setattr(runtime.os, 'getuid', lambda: 0)
            patch.setattr(runtime.os, 'geteuid', lambda: 0)
            patch.setattr(runtime, '_host_helper_fd', lambda *_args, **_kwargs: 999)
            patch.setattr(runtime.ctypes, 'CDLL', lambda *_args, **_kwargs:
                SimpleNamespace(prctl=lambda *_: 0))
            patch.setattr(runtime.os, 'getppid', lambda: 8)
            patch.setattr(runtime.select, 'select', lambda *_: ([], [], []))
            clock = iter((1, 101) if stage == 'before_join' else (1, 1, 1, 101))
            patch.setattr(runtime.time, 'monotonic', lambda: next(clock))
            patch.setattr(runtime.os, 'execve', lambda *_: pytest.fail('no expired runtime exec'))
            if stage == 'after_join':
                fake = SimpleNamespace(st_mode=0o100555, st_uid=0, st_nlink=1, st_size=4)
                original_fstat = os.fstat
                patch.setattr(runtime.os, 'fstat', lambda fd: fake if fd == 998 else original_fstat(fd))
                patch.setattr(runtime.os, 'open', lambda *_args, **_kwargs: 998)
                chunks = iter((b'fake', b''))
                patch.setattr(runtime.os, 'read', lambda *_: next(chunks))
                patch.setattr(runtime.os, 'write', lambda *_: seen.append('joined') or len(str(os.getpid()).encode()))
            with pytest.raises(ValueError):
                runtime._host_helper_main(['--c23-runsc-launch', '999', str(read_fd), '8', '100',
                    hashlib.sha256(b'fake').hexdigest(),
                    '/opt/ocean-c23-runtime/release-20261019.0/runsc', '--root=/controlled', 'start', job])
            assert ('joined' in seen) == (stage == 'after_join')
    finally:
        os.close(read_fd)
        os.close(write_fd)


def test_missing_watchdog_ready_prevents_create_and_start(control, monkeypatch):
    adapter, _, _, journal, _ = control
    def unavailable(*_):
        raise SandboxError('sandbox_watchdog_unavailable')
    monkeypatch.setattr(runtime, '_arm_watchdog', unavailable)
    result = execute(control)
    assert result.state == 'uncertain' and result.outputs is None and journal.result is None
    assert adapter.calls == ['cgroups', 'cleanup']


def test_dead_watchdog_during_create_prevents_start(control):
    adapter, _, _, journal, watchdog = control
    def unavailable():
        raise SandboxError('sandbox_watchdog_unavailable')
    watchdog.require_alive = unavailable
    result = execute(control)
    assert result.state == 'uncertain' and result.outputs is None and journal.result is None
    assert 'start' not in adapter.calls and adapter.calls[-1] == 'cleanup'



@pytest.mark.parametrize('answer', [True, False, None, 0, '0' * 64])
def test_current_retained_hash_required_before_start(control, answer):
    adapter, _, _, journal, _ = control
    result = execute(control, admission=lambda _: answer)
    assert result.state == 'uncertain' and result.outputs is None
    assert 'start' not in adapter.calls and adapter.calls[-1] == 'cleanup' and journal.result is None


def test_final_revocation_cleans_but_does_not_publish_or_finish(control):
    adapter, envelope, _, journal, _ = control
    count = 0
    def admission(_):
        nonlocal count
        count += 1
        return envelope.envelope_sha256 if count == 1 else None
    result = execute(control, admission=admission)
    assert result.state == 'uncertain' and result.outputs is None and journal.result is None
    assert adapter.calls[-1] == 'cleanup' and result.document['execution_started'] is True


@pytest.mark.parametrize('failure', ['readback', 'create', 'start', 'cleanup'])
def test_uncertain_effects_never_produce_outputs_or_release(control, failure):
    adapter, _, _, journal, watchdog = control
    adapter.inject = failure
    result = execute(control)
    assert result.state == 'uncertain' and result.outputs is None
    assert result.document['reservation_released'] is False and journal.result is None
    if failure == 'readback':
        assert 'start' not in adapter.calls
    if failure == 'start':
        assert result.document['execution_started'] is None
    if failure == 'cleanup':
        assert result.document['termination_proof'] is None and watchdog.stopped == [False]


def test_external_timeout_requires_cleanup_and_current_admission(control):
    adapter, _, _, journal, _ = control
    adapter.inject = 'wait'
    result = execute(control)
    assert result.state == 'timed_out' and result.outputs is None
    assert journal.result['state'] == 'timed_out' and adapter.calls[-1] == 'cleanup'


def test_cancellation_before_start_stops_created_job(control):
    adapter, _, _, journal, _ = control
    result = execute(control, cancelled=lambda: True)
    assert result.state == 'cancelled' and 'start' not in adapter.calls
    assert journal.result['state'] == 'cancelled' and adapter.calls[-1] == 'cleanup'


@pytest.mark.parametrize('answer', [1, 'yes', None])
def test_cancellation_is_strict_boolean(control, answer):
    adapter, _, _, journal, _ = control
    result = execute(control, cancelled=lambda: answer)
    assert result.state == 'uncertain' and result.outputs is None
    assert 'start' not in adapter.calls and journal.result is None


def test_missing_delete_ack_is_not_replaced_by_empty_state(control):
    adapter, _, _, journal, _ = control
    adapter.delete_ack = False
    result = execute(control)
    assert result.state == 'uncertain' and result.outputs is None and journal.result is None
    assert result.document['termination_proof']['whole_host_subtree_empty'] is True


@pytest.mark.parametrize('failure', ['prepared', 'create_intent', 'start_intent', 'cleanup_intent', 'finish'])
def test_journal_failures_keep_capacity_and_no_publication(control, failure):
    adapter, _, _, journal, _ = control
    journal.failure = failure
    result = execute(control)
    assert result.state == 'uncertain' and result.outputs is None and journal.result is None
    if failure in {'start_intent', 'cleanup_intent', 'finish'}:
        assert adapter.calls[-1] == 'cleanup'


def test_interrupted_job_reconciles_existing_group_without_rerun(control):
    adapter, _, _, journal, _ = control
    adapter.inject = 'start'
    assert execute(control).state == 'uncertain'
    calls = adapter.calls.copy()
    adapter.inject = None
    result = execute(control)
    assert result.state == 'interrupted' and result.outputs is None
    assert adapter.calls == calls + ['cleanup'] and journal.result['state'] == 'interrupted'
    assert result.document['execution_started'] is None


def test_missing_old_group_never_proves_termination_or_reexecutes(control):
    adapter, envelope, profile, journal, _ = control
    journal.claims = 1
    journal.events.append(SimpleNamespace(kind='create_intent', payload={
        'profile_sha256': profile.profile_sha256, 'cgroup_identity': [17, 23]}))
    result = execute(control)
    assert result.state == 'uncertain' and adapter.calls == [] and journal.result is None
    assert not adapter._paths(envelope.job_id)[0].exists()


def test_unknown_existing_group_has_no_kill_or_launch_authority(control):
    adapter, envelope, _, journal, _ = control
    adapter._paths(envelope.job_id)[0].mkdir(parents=True)
    result = execute(control)
    assert result.state == 'uncertain' and adapter.calls == [] and journal.result is None


@pytest.mark.parametrize('change', ['trailing', 'identity', 'writers', 'format'])
def test_guest_frame_or_output_errors_do_not_publish(control, change):
    adapter, _, _, journal, _ = control
    if change == 'trailing':
        adapter.frame_change = 'trailing'
    elif change == 'identity':
        adapter.frame_change = lambda doc: doc.update(envelope_sha256='0' * 64)
    elif change == 'writers':
        adapter.frame_change = lambda doc: doc.update(writers_reaped=False)
    else:
        adapter.frame_change = lambda doc: doc['files'].update(summary_json='unexpected')
    result = execute(control)
    assert result.state == 'uncertain' and result.outputs is None and journal.result is None
    assert adapter.calls[-1] == 'cleanup'


def test_nonzero_analysis_logs_retained_without_outputs(control):
    adapter, envelope, _, journal, _ = control
    adapter.guest_outcome, adapter.wait_status = 'failed', 1
    result = execute(control)
    assert result.state == 'failed' and result.outputs is None
    path = adapter.worker_root / envelope.job_id / 'retained/logs/stdout'
    assert path.read_bytes() == b'analysis log\n'
    assert result.document['retained_logs']['stdout']['sha256'] == hashlib.sha256(path.read_bytes()).hexdigest()
    assert result.document['analysis_exit_code'] == 1 and journal.result['state'] == 'failed'


def test_macos_guard_precedes_journal_and_popen(layout, monkeypatch):
    envelope, options, _ = layout
    profile = render_execution_profile(envelope, **options)
    journal = FakeJournal()
    adapter = runtime.LinuxExecutionAdapter(options['job_root'].parent, Path('/not-runtime'),
        options['runtime_manifest'], journal)
    monkeypatch.setattr(runtime.sys, 'platform', 'darwin')
    monkeypatch.setattr(runtime.subprocess, 'Popen', lambda *_args, **_kwargs: pytest.fail('no host execution'))
    with pytest.raises(SandboxError, match='sandbox_linux_root_required'):
        adapter.run(envelope, profile, admission=lambda value: value.envelope_sha256)
    assert journal.claims == 0


def test_watchdog_and_direct_helper_refuse_macos_before_process_effects(tmp_path, monkeypatch):
    monkeypatch.setattr(runtime.sys, 'platform', 'darwin')
    monkeypatch.setattr(runtime.subprocess, 'Popen', lambda *_args, **_kwargs: pytest.fail('no process'))
    with pytest.raises(SandboxError, match='sandbox_linux_root_required'):
        runtime._arm_watchdog(tmp_path, 1)
    with pytest.raises(ValueError):
        runtime._host_helper_main(['--c23-watchdog', '3', '4', '1'])


def test_capture_caps_one_byte_beyond_bound_without_process_execution():
    read_out, write_out = os.pipe()
    read_err, write_err = os.pipe()
    capture = runtime._Capture(SimpleNamespace(stdout=os.fdopen(read_out, 'rb'),
        stderr=os.fdopen(read_err, 'rb')), stdout_limit=4, stderr_limit=4)
    try:
        os.write(write_out, b'12345')
        os.close(write_out)
        write_out = None
        os.close(write_err)
        write_err = None
        with pytest.raises(SandboxError, match='sandbox_runtime_output_limit'):
            capture.drain()
        assert bytes(capture.stdout) == b'12345'
    finally:
        capture.close()
        for descriptor in (write_out, write_err):
            if descriptor is not None:
                os.close(descriptor)


@pytest.mark.parametrize('kind', ['symlink', 'hardlink', 'writable_by_others'])
def test_runtime_binary_identity_rejects_links_permissions(tmp_path, kind):
    path = tmp_path / 'runsc'
    path.write_bytes(b'inert fake runtime, never executed')
    if kind == 'symlink':
        other = tmp_path / 'link'
        other.symlink_to(path)
        path = other
    elif kind == 'hardlink':
        os.link(path, tmp_path / 'hardlink')
    else:
        path.chmod(0o666)
    with pytest.raises(SandboxError, match='sandbox_runtime_identity'):
        runtime._hash_runtime_file(path)


def test_hash_and_create_only_retention_use_exact_bytes(tmp_path):
    binary = tmp_path / 'runsc'
    raw = b'inert, not executable runtime fixture'
    binary.write_bytes(raw)
    binary.chmod(0o500)
    assert runtime._hash_runtime_file(binary) == hashlib.sha256(raw).hexdigest()
    output = tmp_path / 'retained'
    runtime._put(output, b'exact')
    runtime._put(output, b'exact', reuse=True)
    with pytest.raises(SandboxError):
        runtime._put(output, b'other', reuse=True)
    with pytest.raises(SandboxError):
        runtime._put(output, b'exact')
    assert output.read_bytes() == b'exact'


@pytest.mark.parametrize('populated', ['1', 'missing', 'duplicate'])
def test_cgroup_nonempty_or_bad_readback_never_proves_termination(control, populated):
    adapter, envelope, _, journal, _ = control
    outer = adapter._paths(envelope.job_id)[0]
    outer.mkdir(parents=True)
    content = {'1': 'populated 1\n', 'missing': 'frozen 0\n',
               'duplicate': 'populated 0\npopulated 0\n'}[populated]
    (outer / 'cgroup.events').write_text(content)
    identity = (outer.stat().st_dev, outer.stat().st_ino)
    with journal.claim(envelope.job_id, envelope.envelope_sha256):
        with pytest.raises(SandboxError):
            adapter._empty(outer, identity, deadline=0, lease=journal)


def test_cgroup_empty_proof_bound_to_device_inode(control):
    adapter, envelope, _, journal, _ = control
    outer = adapter._paths(envelope.job_id)[0]
    outer.mkdir(parents=True)
    (outer / 'cgroup.events').write_text('populated 0\nfrozen 0\n')
    identity = (outer.stat().st_dev, outer.stat().st_ino)
    with journal.claim(envelope.job_id, envelope.envelope_sha256):
        adapter._empty(outer, identity, deadline=0, lease=journal)
        with pytest.raises(SandboxError, match='sandbox_cgroup_identity'):
            adapter._empty(outer, (identity[0], identity[1] + 1), deadline=0, lease=journal)


@pytest.mark.parametrize('resource', ['cpu.max', 'memory.max', 'memory.swap.max', 'pids.max'])
def test_resource_mismatch_prevents_start(control, resource):
    adapter, envelope, profile, journal, _ = control
    outer, host, sandbox = adapter._paths(envelope.job_id)
    for group in (outer, host, sandbox):
        group.mkdir(parents=True, exist_ok=True)
    for group in (outer, sandbox):
        for name, value in profile.requirements['readback_before_start'].items():
            (group / name).write_text(str(value) + '\n')
    (sandbox / resource).write_text('max\n')
    with journal.claim(envelope.job_id, envelope.envelope_sha256):
        with pytest.raises(SandboxError, match='sandbox_resource_enforcement'):
            runtime.LinuxExecutionAdapter._readback(adapter, envelope, profile.document,
                journal, ['inert-runsc'], deadline=1, side=None)
    assert 'start' not in adapter.calls


def test_receipts_are_detached_and_never_grant_authority(control):
    result = execute(control)
    document = result.document
    document['reservation_released'] = True
    assert result.document['reservation_released'] is False
    with pytest.raises(SandboxError, match='sandbox_result_identity'):
        runtime.LinuxExecutionResult({'version': runtime.VERSION})
    assert json.loads(canonical_json(result.document)) == result.document



def test_spawn_passes_only_scoped_fds_no_python_preexec_or_inherited_cloud_env(control, monkeypatch):
    adapter, envelope, _, _, _ = control
    host = adapter._paths(envelope.job_id)[1]
    host.mkdir(parents=True)
    (host / 'cgroup.procs').write_bytes(b'')
    read_out, write_out = os.pipe()
    read_err, write_err = os.pipe()
    process = SimpleNamespace(stdout=os.fdopen(read_out, 'rb'), stderr=os.fdopen(read_err, 'rb'))
    seen = {}
    def popen(argv, **kwargs):
        seen.update(argv=argv, kwargs=kwargs, child_cancel=os.dup(kwargs['pass_fds'][1]))
        return process
    monkeypatch.setattr(runtime.subprocess, 'Popen', popen)
    capture = runtime.LinuxExecutionAdapter._spawn(adapter,
        ['/opt/ocean-c23-runtime/release-20261019.0/runsc', '--root=/private/controlled', 'start', envelope.job_id],
        host, deadline=runtime.time.monotonic() + 1)
    try:
        assert 'preexec_fn' not in seen['kwargs'] and 'shell' not in seen['kwargs']
        assert seen['kwargs']['close_fds'] is True and len(seen['kwargs']['pass_fds']) == 2
        assert seen['kwargs']['env'] == {'PATH': '/usr/sbin:/usr/bin:/sbin:/bin', 'LANG': 'C.UTF-8'}
        assert seen['argv'][:5] == [runtime.sys.executable, '-I', '-S', '-B', str(Path(runtime.__file__).resolve())]
        assert seen['argv'][5] == '--c23-runsc-launch'
        assert not os.get_inheritable(capture.cancel_pipe)
        capture.cancel_launch()
        assert os.read(seen['child_cancel'], 1) == b'', 'queued launcher observes cleanup cancellation'
    finally:
        capture.close()
        for fd in (write_out, write_err, seen['child_cancel']):
            os.close(fd)


def test_helper_script_exits_before_project_native_imports_and_has_no_fork_preexec():
    import ast
    tree = ast.parse(Path(runtime.__file__).read_text())
    guard = next(node for node in tree.body if isinstance(node, ast.If)
                 and isinstance(node.test, ast.Compare)
                 and isinstance(node.test.left, ast.Name) and node.test.left.id == '__name__')
    projects = [node.lineno for node in tree.body if isinstance(node, ast.ImportFrom)
                and node.module and node.module.startswith(('orchestration.', 'sandbox.', 'schema.'))]
    assert projects and guard.lineno < min(projects)
    assert not any(isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                   and node.func.attr == 'fork' for node in ast.walk(tree))
    assert not any(isinstance(node, ast.keyword) and node.arg == 'preexec_fn' for node in ast.walk(tree))


@pytest.mark.parametrize('stage', ['before_join_parent_death', 'before_join_cancelled', 'after_join_cancelled'])
def test_launcher_parent_and_cancel_fences_prevent_late_exec(stage, monkeypatch):
    job = 'c23-' + '1' * 48
    read_fd, write_fd = os.pipe()
    seen, checks = [], 0
    try:
        with monkeypatch.context() as patch:
            patch.setattr(runtime.sys, 'platform', 'linux')
            patch.setattr(runtime.os, 'getuid', lambda: 0)
            patch.setattr(runtime.os, 'geteuid', lambda: 0)
            patch.setattr(runtime, '_host_helper_fd', lambda *_args, **_kwargs: 999)
            patch.setattr(runtime.ctypes, 'CDLL', lambda *_args, **_kwargs:
                SimpleNamespace(prctl=lambda *_: seen.append('pdeathsig') or 0))
            patch.setattr(runtime.os, 'getppid', lambda: 7 if stage == 'before_join_parent_death' else 8)
            def ready(*_):
                nonlocal checks
                checks += 1
                if stage == 'before_join_cancelled' or stage == 'after_join_cancelled' and checks >= 3:
                    return [read_fd], [], []
                return [], [], []
            patch.setattr(runtime.select, 'select', ready)
            patch.setattr(runtime.os, 'execve', lambda *_: pytest.fail('no late runtime exec'))
            if stage == 'after_join_cancelled':
                fake = SimpleNamespace(st_mode=0o100555, st_uid=0, st_nlink=1, st_size=4)
                original_fstat = os.fstat
                patch.setattr(runtime.os, 'fstat', lambda fd: fake if fd == 998 else original_fstat(fd))
                patch.setattr(runtime.os, 'open', lambda *_args, **_kwargs: 998)
                chunks = iter((b'fake', b''))
                patch.setattr(runtime.os, 'read', lambda *_: next(chunks))
                patch.setattr(runtime.os, 'write', lambda *_: seen.append('joined') or len(str(os.getpid()).encode()))
            with pytest.raises(ValueError):
                runtime._host_helper_main(['--c23-runsc-launch', '999', str(read_fd), '8',
                    str(runtime.time.monotonic() + 5),
                    hashlib.sha256(b'fake').hexdigest(),
                    '/opt/ocean-c23-runtime/release-20261019.0/runsc', '--root=/controlled', 'start', job])
            assert seen[0] == 'pdeathsig'
            assert ('joined' in seen) == (stage == 'after_join_cancelled')
    finally:
        os.close(read_fd)
        os.close(write_fd)


def _resource_fixture(adapter, envelope, profile):
    outer, host, sandbox = adapter._paths(envelope.job_id)
    for group in (outer, host, sandbox):
        group.mkdir(parents=True, exist_ok=True)
    for group in (outer, sandbox):
        for name, value in profile.requirements['readback_before_start'].items():
            (group / name).write_text(str(value) + '\n')
    return outer, host, sandbox


@pytest.mark.parametrize('mutation', ['foreign_id', 'running', 'boolean_pid', 'foreign_bundle', 'outside_cgroup'])
def test_created_state_and_host_membership_bound_to_this_job(control, mutation, monkeypatch):
    adapter, envelope, profile, journal, _ = control
    _resource_fixture(adapter, envelope, profile)
    state = {'id': envelope.job_id, 'status': 'created', 'pid': 1234,
             'bundle': str(adapter.worker_root / envelope.job_id)}
    if mutation == 'foreign_id':
        state['id'] = 'c23-' + '2' * 48
    elif mutation == 'running':
        state['status'] = 'running'
    elif mutation == 'boolean_pid':
        state['pid'] = True
    elif mutation == 'foreign_bundle':
        state['bundle'] += '-foreign'
    monkeypatch.setattr(adapter, '_command', lambda *_args, **_kwargs:
        (0, json.dumps(state).encode(), b''))
    original = runtime._read
    def read(path, maximum=runtime.MAX_COMMAND_BYTES):
        if str(path).startswith('/proc/'):
            return b'0::/outside\n'
        return original(path, maximum)
    monkeypatch.setattr(runtime, '_read', read)
    with journal.claim(envelope.job_id, envelope.envelope_sha256):
        with pytest.raises(SandboxError):
            runtime.LinuxExecutionAdapter._readback(adapter, envelope, profile.document,
                journal, ['inert'], deadline=1, side=None)


def test_matching_readbacks_include_outer_and_inner_before_start(control, monkeypatch):
    adapter, envelope, profile, journal, _ = control
    _resource_fixture(adapter, envelope, profile)
    state = {'id': envelope.job_id, 'status': 'created', 'pid': 1234,
             'bundle': str(adapter.worker_root / envelope.job_id)}
    monkeypatch.setattr(adapter, '_command', lambda *_args, **_kwargs:
        (0, json.dumps(state).encode(), b''))
    original = runtime._read
    monkeypatch.setattr(runtime, '_read', lambda path, maximum=runtime.MAX_COMMAND_BYTES:
        ('0::/ocean-c23/' + envelope.job_id + '/sandbox\n').encode()
        if str(path).startswith('/proc/') else original(path, maximum))
    with journal.claim(envelope.job_id, envelope.envelope_sha256):
        readback = runtime.LinuxExecutionAdapter._readback(adapter, envelope, profile.document,
            journal, ['inert'], deadline=1, side=None)
    assert set(readback) == {envelope.job_id, 'sandbox'}
    assert all(values['memory.swap.max'] == '0' for values in readback.values())


def test_lost_fence_does_not_grant_cleanup_authority(control):
    adapter, _, _, journal, watchdog = control
    def admission(value):
        journal.lost = True
        return value.envelope_sha256
    result = execute(control, admission=admission)
    assert result.state == 'uncertain' and result.outputs is None and journal.result is None
    assert 'start' not in adapter.calls and 'cleanup' not in adapter.calls
    assert watchdog.stopped == [False], 'liveness EOF leaves independent bounded watchdog active'



class ActualJournalScope:
    """Actual SQLite/flock store with mock runtime effect assertions."""
    def __init__(self, store):
        self.store, self.lease = store, None
        self.host_boot_id = store.host_boot_id

    @contextmanager
    def claim(self, *args):
        with self.store.claim(*args) as lease:
            self.lease = lease
            try:
                yield lease
            finally:
                self.lease = None

    def require_current(self):
        assert self.lease is not None
        return self.lease.require_current()


@pytest.fixture
def actual_control(control, tmp_path):
    import sqlite3
    from orchestration.experiment_sandbox.journal import DurableExecutionJournal, _safe_sqlite_version
    if not _safe_sqlite_version(sqlite3.sqlite_version_info):
        pytest.skip('Actual journal interoperation needs the SQLite WAL-reset fix')
    path = (tmp_path / 'actual-durable-journal').resolve()
    path.mkdir(mode=0o700)
    store = DurableExecutionJournal(path,
        host_boot_id='11111111-1111-4111-8111-111111111111', host_id='1' * 64)
    scope = ActualJournalScope(store)
    adapter, envelope, profile, _, watchdog = control
    adapter.journal = scope
    try:
        yield adapter, envelope, profile, scope, watchdog
    finally:
        store.close()


def test_actual_durable_journal_retains_control_and_replays_without_rerun(actual_control):
    adapter, envelope, _, scope, _ = actual_control
    first = execute(actual_control)
    retained = scope.store.read(envelope.job_id, envelope.envelope_sha256)
    assert first.state == 'completed' and retained.terminal
    assert retained.result['record']['outputs_manifest_sha256'] == first.document['outputs_manifest_sha256']
    assert retained.result['reservation_released'] is False
    calls = adapter.calls.copy()
    second = execute(actual_control)
    assert second.state == 'completed' and second.document['replayed'] is True
    assert second.outputs.files == first.outputs.files and adapter.calls == calls


def test_actual_nonterminal_journal_requires_reconciliation_not_reexecution(actual_control):
    adapter, envelope, _, scope, _ = actual_control
    adapter.inject = 'start'
    assert execute(actual_control).state == 'uncertain'
    before = scope.store.read(envelope.job_id, envelope.envelope_sha256)
    assert not before.terminal and any(event.kind == 'start_intent' for event in before.events)
    calls = adapter.calls.copy()
    adapter.inject = None
    resumed = execute(actual_control)
    assert resumed.state == 'interrupted' and resumed.outputs is None
    assert adapter.calls == calls + ['cleanup']
    after = scope.store.read(envelope.job_id, envelope.envelope_sha256)
    assert after.terminal and after.result['record']['execution_started'] is None


def test_actual_journal_revocation_does_not_publish_stored_output_on_resume(actual_control):
    adapter, envelope, _, scope, _ = actual_control
    calls = 0
    def admission(_):
        nonlocal calls
        calls += 1
        return envelope.envelope_sha256 if calls == 1 else None
    denied = execute(actual_control, admission=admission)
    assert denied.state == 'uncertain' and denied.outputs is None
    assert not scope.store.read(envelope.job_id, envelope.envelope_sha256).terminal
    resumed = execute(actual_control)
    assert resumed.state == 'interrupted' and resumed.outputs is None
    assert adapter.calls.count('create') == 1



