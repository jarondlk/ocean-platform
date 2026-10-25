"""Host-safe trusted-init boundary checks; no UID/capability/signal effects.

Actual Linux/gVisor lifecycle and hostile descendant probes are separate gates.
"""
import base64
import ctypes
import hashlib
import json
import os
from pathlib import Path
import struct
import subprocess
import sys
from types import SimpleNamespace

import pytest

from sandbox.experiment import trusted_init as init


@pytest.fixture
def policy():
    return {'version': init.VERSION, 'job_id': 'c23-' + 'a' * 48,
            'envelope_sha256': 'b' * 64, 'expected_names': ['result.csv'],
            'wall_seconds': 60, 'max_output_bytes': 32768,
            'output_file_budget_bytes': 16384, 'stdout_max_bytes': 4096, 'stderr_max_bytes': 4096,
            'scratch_max_bytes': 1024 * 1024}


def result(policy):
    return {'version': init.VERSION, 'job_id': policy['job_id'],
            'envelope_sha256': policy['envelope_sha256'], 'outcome': 'completed',
            'reason': 'completed', 'analysis_exit_code': 0, 'writers_reaped': True,
            'files': {'result.csv': base64.b64encode(b'x,y\n1,2\n').decode()},
            'logs': {'stdout': base64.b64encode(b'not a protocol frame\n').decode(), 'stderr': ''}}


def frame(document, policy):
    return init.encode_frame(document, max_output_bytes=policy['max_output_bytes'])


def test_control_frame_preserves_exact_bytes_and_child_logs_are_data(policy):
    document = result(policy)
    document['logs']['stdout'] = base64.b64encode(init.MAGIC + b'forged child frame').decode()
    retained, decoded = init.decode_frame(frame(document, policy), policy=policy)
    assert retained['writers_reaped'] is True
    assert decoded == {'files': {'result.csv': b'x,y\n1,2\n'},
                       'logs': {'stdout': init.MAGIC + b'forged child frame', 'stderr': b''}}


@pytest.mark.parametrize('transform', [
    lambda raw: raw[1:], lambda raw: raw[:-1], lambda raw: raw + b'forgery',
    lambda raw: raw[:len(init.MAGIC)] + struct.pack('>Q', 2**63) + raw[len(init.MAGIC) + 8:],
    lambda raw: raw[:len(init.MAGIC) + 8] + b'x' * 32 + raw[len(init.MAGIC) + 40:],
])
def test_truncated_extended_corrupt_or_forged_length_frame_rejected(policy, transform):
    with pytest.raises(init.InitError):
        init.decode_frame(transform(frame(result(policy), policy)), policy=policy)


@pytest.mark.parametrize('key,value', [
    ('job_id', 'c23-' + 'c' * 48), ('envelope_sha256', 'c' * 64),
    ('writers_reaped', False), ('writers_reaped', 1), ('analysis_exit_code', True),
    ('analysis_exit_code', -9), ('outcome', []), ('reason', 'some arbitrary exception/path'),
    ('version', 'another-version'), ('files', {'unexpected.csv': ''}),
    ('logs', {'stdout': '', 'stderr': '', 'extra': ''}),
])
def test_claimed_success_requires_bound_exact_identity_and_clean_writer_result(policy, key, value):
    document = result(policy)
    document[key] = value
    with pytest.raises(init.InitError):
        init.decode_frame(frame(document, policy), policy=policy)


@pytest.mark.parametrize('outcome', ['failed', 'cancelled', 'timed_out'])
def test_non_success_can_retain_logs_but_cannot_retain_outputs(policy, outcome):
    document = result(policy)
    document['outcome'], document['reason'] = outcome, 'analysis_nonzero'
    with pytest.raises(init.InitError):
        init.decode_frame(frame(document, policy), policy=policy)
    document['files'] = {}
    retained, decoded = init.decode_frame(frame(document, policy), policy=policy)
    assert retained['outcome'] == outcome and not decoded['files']


@pytest.mark.parametrize('which', ['stdout', 'stderr'])
def test_log_budget_applies_after_valid_base64_decode(policy, which):
    document = result(policy)
    document['logs'][which] = base64.b64encode(b'x' * (policy[which + '_max_bytes'] + 1)).decode()
    with pytest.raises(init.InitError, match='log_limit'):
        init.decode_frame(frame(document, policy), policy=policy)


def test_file_budget_is_independent_from_larger_frame_budget(policy):
    document = result(policy)
    document['files']['result.csv'] = base64.b64encode(b'x' * 16385).decode()
    with pytest.raises(init.InitError, match='output_limit'):
        init.decode_frame(frame(document, policy), policy=policy)


@pytest.mark.parametrize('encoded', ['?', '\u263a', 'YQ', 'YQ===', 1, None])
def test_noncanonical_or_invalid_base64_is_not_accepted(policy, encoded):
    document = result(policy)
    document['files']['result.csv'] = encoded
    with pytest.raises(init.InitError):
        init.decode_frame(frame(document, policy), policy=policy)


@pytest.mark.parametrize('raw', [
    b'{"version":1,"version":2}',
    b'[' * 9 + b'0' + b']' * 9,
    b'[' + b'0,' * 513 + b'0]',
    b'{"x":' + b'1' * 65 + b'}',
    b'{"x":NaN}',
])
def test_json_structure_and_duplicate_keys_refused_before_object_allocation(raw):
    with pytest.raises(init.InitError):
        init._json(raw)


@pytest.mark.parametrize('key,value', [
    ('wall_seconds', True), ('wall_seconds', 601), ('wall_seconds', 0),
    ('max_output_bytes', 8191), ('max_output_bytes', init.MAX_OUTPUT + 1),
    ('stdout_max_bytes', init.MAX_LOG + 1), ('stderr_max_bytes', 0),
    ('expected_names', ['../escape.csv']), ('expected_names', ['a.csv', 'a.csv']),
    ('expected_names', ['b.csv', 'a.csv']), ('expected_names', ['x.html']),
    ('expected_names', ['a.csv'] * 33), ('expected_names', []),
    ('output_file_budget_bytes', 32768), ('job_id', 'arbitrary'),
    ('output_file_budget_bytes', 16385), ('scratch_max_bytes', 4095),
    ('scratch_max_bytes', 4097), ('scratch_max_bytes', init.MAX_SCRATCH + 4096),
    ('scratch_max_bytes', True),
])
def test_policy_refuses_unapproved_bounds_paths_and_ambiguous_inventory(policy, key, value):
    policy[key] = value
    with pytest.raises(init.InitError):
        init.validate_policy(policy)


def test_policy_caller_mutation_cannot_change_validated_copy(policy):
    detached = init.validate_policy(policy)
    policy['expected_names'][0] = 'another.csv'
    assert detached['expected_names'] == ['result.csv']


def collect(directory, names=None, maximum=200):
    descriptor = os.open(directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        return init.collect_outputs_fd(descriptor, expected_names=names or ['result.csv'],
                                       maximum=maximum, expected_uid=os.geteuid())
    finally:
        os.close(descriptor)


def test_fd_collection_preserves_int64_unicode_and_exact_machine_bytes(tmp_path):
    expected = 'id,label\n9007199254740993,\u6d77\n'.encode()
    (tmp_path / 'result.csv').write_bytes(expected)
    assert collect(tmp_path) == {'result.csv': expected}


@pytest.mark.parametrize('unsafe', ['symlink', 'hardlink', 'fifo', 'directory'])
def test_guest_output_filetypes_refused_without_opening_unsafe_nodes(tmp_path, unsafe):
    target = tmp_path / 'result.csv'
    if unsafe == 'symlink':
        target.symlink_to('/etc/passwd')
    elif unsafe == 'hardlink':
        original = tmp_path.parent / (tmp_path.name + '-outside')
        original.write_bytes(b'outside')
        os.link(original, target)
    elif unsafe == 'fifo':
        os.mkfifo(target)
    else:
        target.mkdir()
    with pytest.raises(init.InitError):
        collect(tmp_path)


def test_unexpected_inventory_and_aggregate_file_limit(tmp_path):
    (tmp_path / 'result.csv').write_bytes(b'12345')
    with pytest.raises(init.InitError):
        collect(tmp_path, maximum=4)
    (tmp_path / 'extra.csv').write_bytes(b'x')
    with pytest.raises(init.InitError):
        collect(tmp_path)
    assert collect(tmp_path, names=['extra.csv', 'result.csv'], maximum=6) == {
        'extra.csv': b'x', 'result.csv': b'12345'}


def test_expired_collection_deadline_rejects_before_file_read(tmp_path):
    (tmp_path / 'result.csv').write_bytes(b'x')
    descriptor = os.open(tmp_path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        with pytest.raises(init.InitError, match='deadline'):
            init.collect_outputs_fd(descriptor, expected_names=['result.csv'], maximum=10,
                                    expected_uid=os.geteuid(), deadline=0)
    finally:
        os.close(descriptor)


def test_changed_open_file_is_rejected_even_when_name_and_length_match(tmp_path, monkeypatch):
    target = tmp_path / 'result.csv'
    target.write_bytes(b'original')
    original = os.read
    changed = False
    def modify(descriptor, count):
        nonlocal changed
        raw = original(descriptor, count)
        if not changed:
            target.write_bytes(b'modified')
            changed = True
        return raw
    monkeypatch.setattr(init.os, 'read', modify)
    with pytest.raises(init.InitError, match='changed'):
        collect(tmp_path)


def test_guard_prevents_every_dangerous_entry_before_effect_on_host(monkeypatch):
    # Do not simulate a successful guard or any real privileged operation.
    monkeypatch.setattr(init.sys, 'platform', 'darwin')
    def forbidden(*_args, **_kwargs):
        raise AssertionError('A privileged operation was attempted on the host')
    for operation in ('kill', 'setgroups', 'setresuid', 'setresgid', 'fork', 'execve'):
        monkeypatch.setattr(init.os, operation, forbidden, raising=False)
    monkeypatch.setattr(init.ctypes, 'CDLL', forbidden)
    for operation in (lambda: init._harden_init({}), lambda: init._drop_child(file_budget=100),
                      lambda: init._kill_and_reap(deadline=0, drain=lambda: None),
                      lambda: init._prctl(24, 8), lambda: init._run({}),
                      lambda: init._mount_guest_tmpfs({}), init._set_init_capabilities):
        with pytest.raises(init.InitError, match='guest_pid1_required'):
            operation()


def test_standalone_script_refuses_ordinary_host_process_before_analysis(policy, tmp_path):
    script = Path(init.__file__).resolve()
    observation = subprocess.run([sys.executable, '-I', '-B', str(script), '--policy', json.dumps(policy)],
                                 cwd=tmp_path, capture_output=True, timeout=10)
    assert observation.returncode == 125
    assert observation.stdout == b''
    assert observation.stderr == b'c23_trusted_init_refused\n'
    assert list(tmp_path.iterdir()) == []


def test_large_structure_frame_cannot_hide_under_valid_checksum(policy):
    payload = b'[' + b'0,' * 2000 + b'0]'
    forged = init.MAGIC + struct.pack('>Q', len(payload)) + hashlib.sha256(payload).digest() + payload
    with pytest.raises(init.InitError):
        init.decode_frame(forged, policy=policy)


def empty_mount():
    return SimpleNamespace(f_frsize=4096, f_bsize=4096, f_blocks=4, f_bfree=4, f_bavail=4,
                           f_files=512, f_ffree=511, f_favail=511, f_flag=14)


def test_fresh_mount_readback_binds_exact_bytes_inodes_owner_and_safety_flags(monkeypatch):
    monkeypatch.setattr(init.os, 'stat', lambda *_a, **_k: SimpleNamespace(
        st_mode=0o40700, st_uid=65532, st_gid=65532))
    monkeypatch.setattr(init.os, 'statvfs', lambda _p: empty_mount())
    init._verify_empty_mount('/outputs', 16384, 512)


@pytest.mark.parametrize('field,value', [
    ('f_frsize', 8192), ('f_bsize', 8192), ('f_blocks', 5), ('f_bfree', 3),
    ('f_bavail', 3), ('f_files', 0), ('f_files', 513), ('f_ffree', 512),
    ('f_favail', 512), ('f_flag', 6), ('f_flag', 15),
])
def test_unlimited_or_mismatched_mount_never_reaches_analysis(monkeypatch, field, value):
    observed = empty_mount()
    setattr(observed, field, value)
    monkeypatch.setattr(init.os, 'stat', lambda *_a, **_k: SimpleNamespace(
        st_mode=0o40700, st_uid=65532, st_gid=65532))
    monkeypatch.setattr(init.os, 'statvfs', lambda _p: observed)
    with pytest.raises(init.InitError, match='quota_readback'):
        init._verify_empty_mount('/outputs', 16384, 512)


@pytest.mark.parametrize('field,value', [('st_mode', 0o40777), ('st_mode', 0o100700),
                                        ('st_uid', 0), ('st_gid', 0)])
def test_guest_mount_wrong_owner_mode_or_type_is_refused(monkeypatch, field, value):
    observed = SimpleNamespace(st_mode=0o40700, st_uid=65532, st_gid=65532)
    setattr(observed, field, value)
    monkeypatch.setattr(init.os, 'stat', lambda *_a, **_k: observed)
    monkeypatch.setattr(init.os, 'statvfs', lambda _p: empty_mount())
    with pytest.raises(init.InitError, match='quota_readback'):
        init._verify_empty_mount('/outputs', 16384, 512)


def test_privileged_mount_calls_have_only_two_fixed_targets_and_fixed_safe_options(policy, monkeypatch):
    # Every boundary is a local fake; no real mount/capability/UID syscall runs.
    calls = []
    monkeypatch.setattr(init, '_guard_guest_root', lambda **_k: calls.append('guard'))
    monkeypatch.setattr(init.os, 'stat', lambda *_a, **_k: SimpleNamespace(st_mode=0o40755))
    class Libc:
        def mount(self, source, target, filesystem, flags, options):
            calls.append((source.value, target.value, filesystem.value, flags.value, options.value))
            return 0
    monkeypatch.setattr(init.ctypes, 'CDLL', lambda *_a, **_k: Libc())
    monkeypatch.setattr(init, '_verify_empty_mount', lambda *args: calls.append(('readback', *args)))
    init._mount_guest_tmpfs(policy)
    assert calls == ['guard',
        (b'tmpfs', b'/outputs', b'tmpfs', 14,
         b'size=16384,nr_inodes=512,uid=65532,gid=65532,mode=0700'),
        ('readback', '/outputs', 16384, 512),
        (b'tmpfs', b'/scratch', b'tmpfs', 14,
         b'size=1048576,nr_inodes=4096,uid=65532,gid=65532,mode=0700'),
        ('readback', '/scratch', 1048576, 4096)]


def test_mount_failure_refuses_before_second_mount_or_capability_transition(policy, monkeypatch):
    calls = []
    monkeypatch.setattr(init, '_guard_guest_root', lambda **_k: None)
    monkeypatch.setattr(init.os, 'stat', lambda *_a, **_k: SimpleNamespace(st_mode=0o40755))
    class Libc:
        def mount(self, *_args):
            calls.append('failed_mount')
            return -1
    monkeypatch.setattr(init.ctypes, 'CDLL', lambda *_a, **_k: Libc())
    monkeypatch.setattr(init, '_verify_empty_mount', lambda *_a: calls.append('readback'))
    with pytest.raises(init.InitError, match='tmpfs_mount_failed'):
        init._mount_guest_tmpfs(policy)
    assert calls == ['failed_mount']


def test_sys_admin_removed_from_current_and_bounding_before_analysis_boundary(policy, monkeypatch):
    events = []
    before = sum(1 << cap for cap in init.START_CAPS)
    after = sum(1 << cap for cap in init.INIT_CAPS)
    states = iter([dict(CapEff=before, CapPrm=before, CapBnd=before,
                        CapInh=0, CapAmb=0, NoNewPrivs=1),
                   dict(CapEff=after, CapPrm=after, CapBnd=0,
                        CapInh=0, CapAmb=0, NoNewPrivs=1)])
    monkeypatch.setattr(init, '_guard_guest_root', lambda **_k: events.append('guard'))
    monkeypatch.setattr(init, '_status', lambda: next(states))
    monkeypatch.setattr(init, '_prctl', lambda *args: events.append(('prctl', *args)))
    monkeypatch.setattr(init, '_mount_guest_tmpfs', lambda _p: events.append('fixed_mounts'))
    monkeypatch.setattr(init, '_set_init_capabilities', lambda: events.append('remove_current_sys_admin'))
    def forbidden(*_a, **_k):
        raise AssertionError('No host privileged syscall or analysis fork is permitted in this unit test')
    monkeypatch.setattr(init.ctypes, 'CDLL', forbidden)
    monkeypatch.setattr(init.os, 'fork', forbidden)
    init._harden_init(policy)
    assert events.index('fixed_mounts') < events.index(('prctl', 24, init.MOUNT_CAP))
    assert events.index(('prctl', 24, init.MOUNT_CAP)) < events.index('remove_current_sys_admin')
    assert events[-1] == ('prctl', 47, 4)


@pytest.mark.parametrize('return_code', [0, -1])
def test_capset_abi_removes_sys_admin_from_both_current_masks(monkeypatch, return_code):
    calls = []
    monkeypatch.setattr(init, '_guard_guest_root', lambda **_k: None)
    class Libc:
        def capset(self, header, data):
            calls.append((list(ctypes.cast(header, ctypes.POINTER(ctypes.c_uint32 * 2)).contents),
                          list(ctypes.cast(data, ctypes.POINTER(ctypes.c_uint32 * 6)).contents)))
            return return_code
    monkeypatch.setattr(init.ctypes, 'CDLL', lambda *_a, **_k: Libc())
    if return_code:
        with pytest.raises(init.InitError, match='capset_failed'):
            init._set_init_capabilities()
    else:
        init._set_init_capabilities()
    wanted = sum(1 << cap for cap in init.INIT_CAPS)
    assert calls == [([0x20080522, 0], [wanted, wanted, 0, 0, 0, 0])]
    assert wanted & (1 << init.MOUNT_CAP) == 0


@pytest.mark.parametrize('phase', ['missing_initial_mount_cap', 'residual_current_mount_cap'])
def test_initial_and_post_mount_capability_readback_refuse_an_unsafe_boundary(policy, monkeypatch, phase):
    events = []
    six = sum(1 << cap for cap in init.START_CAPS)
    five = sum(1 << cap for cap in init.INIT_CAPS)
    states = iter([
        dict(CapEff=five if phase == 'missing_initial_mount_cap' else six,
             CapPrm=six, CapBnd=six, CapInh=0, CapAmb=0, NoNewPrivs=1),
        dict(CapEff=six, CapPrm=six, CapBnd=0, CapInh=0, CapAmb=0, NoNewPrivs=1),
    ])
    monkeypatch.setattr(init, '_guard_guest_root', lambda **_k: None)
    monkeypatch.setattr(init, '_status', lambda: next(states))
    monkeypatch.setattr(init, '_prctl', lambda *_a: None)
    monkeypatch.setattr(init, '_mount_guest_tmpfs', lambda _p: events.append('mounts'))
    monkeypatch.setattr(init, '_set_init_capabilities', lambda: events.append('capset'))
    with pytest.raises(init.InitError):
        init._harden_init(policy)
    assert events == ([] if phase == 'missing_initial_mount_cap' else ['mounts', 'capset'])
