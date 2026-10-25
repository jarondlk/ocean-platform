"""Host-safe trusted-init boundary checks; no UID/capability/signal effects.

Actual Linux/gVisor lifecycle and hostile descendant probes are separate gates.
"""
import base64
import hashlib
import json
import os
from pathlib import Path
import struct
import subprocess
import sys

import pytest

from sandbox.experiment import trusted_init as init


@pytest.fixture
def policy():
    return {'version': init.VERSION, 'job_id': 'c23-' + 'a' * 48,
            'envelope_sha256': 'b' * 64, 'expected_names': ['result.csv'],
            'wall_seconds': 60, 'max_output_bytes': 32768,
            'output_file_budget_bytes': 16384, 'stdout_max_bytes': 4096, 'stderr_max_bytes': 4096}


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
    for operation in (init._harden_init, lambda: init._drop_child(file_budget=100),
                      lambda: init._kill_and_reap(deadline=0, drain=lambda: None),
                      lambda: init._prctl(24, 8), lambda: init._run({})):
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
