"""Sealed C23 guest PID1; stdlib only, with a bounded control frame.

This file never runs an analysis merely by import. ``main`` refuses anything
except root PID1 in a gVisor guest. Host orchestration, image provenance, fresh
admission and actual containment acceptance remain separate mandatory gates.
"""
from __future__ import annotations

import base64
import ctypes
import hashlib
import json
import os
from pathlib import Path
import re
import resource
import selectors
import signal
import stat
import struct
import sys
import time

VERSION = 'c23-trusted-init-v2'
MAGIC = b'C23FRAME1\n'
CHILD_UID = CHILD_GID = 65532
MAX_OUTPUT = 50 * 1024 * 1024
MAX_LOG = 1024 * 1024
MAX_NAMES = 32
MAX_FDS = 256
MAX_GUEST_TASKS = 128
INIT_CAPS = (2, 5, 6, 7, 8)  # DAC_READ_SEARCH, KILL, SETGID, SETUID, SETPCAP
INIT_CAP_NAMES = ('CAP_DAC_READ_SEARCH', 'CAP_KILL', 'CAP_SETGID', 'CAP_SETUID', 'CAP_SETPCAP')
MOUNT_CAP = 21  # CAP_SYS_ADMIN exists only before fixed tmpfs setup.
START_CAPS = (*INIT_CAPS, MOUNT_CAP)
START_CAP_NAMES = (*INIT_CAP_NAMES, 'CAP_SYS_ADMIN')
OUTPUT_INODES = 512
SCRATCH_INODES = 4096
MAX_SCRATCH = 256 * 1024**2
_NAME = re.compile(r'^[A-Za-z0-9][A-Za-z0-9_.-]{0,99}$')
_SHA = re.compile(r'^[a-f0-9]{64}$')
_JOB = re.compile(r'^c23-[a-f0-9]{48}$')


class InitError(ValueError):
    pass


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'),
                      ensure_ascii=False, allow_nan=False).encode('utf-8')


def _pairs(items):
    result = {}
    for key, value in items:
        if key in result:
            raise InitError('duplicate_json_key')
        result[key] = value
    return result


def _json(raw):
    try:
        value = raw.decode('utf-8') if type(raw) is bytes else raw
        if type(value) is not str:
            raise InitError('invalid_json')
        # Bound structure BEFORE JSON builds Python lists/dicts. Large base64
        # strings are allowed, but nested collections/millions of tiny values
        # cannot turn a bounded wire frame into an unbounded object allocation.
        quoted, escaped, depth, strings, atoms, atom_size = False, False, 0, 0, 0, 0
        for character in value:
            if quoted:
                if escaped:
                    escaped = False
                elif character == '\\':
                    escaped = True
                elif character == '"':
                    quoted = False
                continue
            if character == '"':
                quoted, strings, atom_size = True, strings + 1, 0
            elif character in '{[':
                depth, atoms, atom_size = depth + 1, atoms + 1, 0
            elif character in '}]':
                depth, atom_size = depth - 1, 0
            elif character in ',: \n\r\t':
                atom_size = 0
            else:
                if not atom_size:
                    atoms += 1
                atom_size += 1
            if not 0 <= depth <= 8 or strings > 256 or atoms > 512 or atom_size > 64:
                raise InitError('json_structure_limit')
        return json.loads(value, object_pairs_hook=_pairs,
                          parse_constant=lambda _: (_ for _ in ()).throw(InitError('nonfinite_json')))
    except (ValueError, UnicodeError, RecursionError):
        raise InitError('invalid_json') from None


def _integer(value, low, high):
    return type(value) is int and low <= value <= high


def validate_policy(policy):
    keys = {'version', 'job_id', 'envelope_sha256', 'expected_names', 'wall_seconds',
            'max_output_bytes', 'output_file_budget_bytes', 'stdout_max_bytes', 'stderr_max_bytes',
            'scratch_max_bytes'}
    if type(policy) is not dict or set(policy) != keys or policy['version'] != VERSION:
        raise InitError('policy_shape')
    if (type(policy['job_id']) is not str or not _JOB.fullmatch(policy['job_id'])
            or type(policy['envelope_sha256']) is not str or not _SHA.fullmatch(policy['envelope_sha256'])
            or not _integer(policy['wall_seconds'], 1, 600)
            or not _integer(policy['max_output_bytes'], 8192, MAX_OUTPUT)
            or not _integer(policy['output_file_budget_bytes'], 1, policy['max_output_bytes'])
            or policy['output_file_budget_bytes'] % 4096
            or not _integer(policy['scratch_max_bytes'], 4096, MAX_SCRATCH)
            or policy['scratch_max_bytes'] % 4096
            or any(not _integer(policy[key], 1, MAX_LOG) for key in ('stdout_max_bytes', 'stderr_max_bytes'))):
        raise InitError('policy_bounds')
    names = policy['expected_names']
    if (type(names) is not list or not 1 <= len(names) <= MAX_NAMES
            or any(type(name) is not str or not _NAME.fullmatch(name)
                   or Path(name).suffix not in {'.json', '.csv', '.png'} for name in names)
            or len(set(names)) != len(names) or names != sorted(names)
            or policy['output_file_budget_bytes'] + policy['stdout_max_bytes'] + policy['stderr_max_bytes']
               > policy['max_output_bytes']):
        raise InitError('policy_outputs')
    return _json(canonical(policy))


def max_payload_bytes(max_output_bytes):
    if not _integer(max_output_bytes, 8192, MAX_OUTPUT):
        raise InitError('frame_bound')
    return ((max_output_bytes + 2) // 3) * 4 + 128 * 1024


def encode_frame(document, *, max_output_bytes):
    raw = canonical(document)
    if len(raw) > max_payload_bytes(max_output_bytes):
        raise InitError('frame_limit')
    return MAGIC + struct.pack('>Q', len(raw)) + hashlib.sha256(raw).digest() + raw


def decode_frame(raw, *, policy):
    """Parse untrusted transport bytes; no process/containment authority granted.

    The caller must already bind the pipe to the verified sealed guest init.
    The checksum detects truncation/corruption; it is not a signature.
    """
    policy = validate_policy(policy)
    header = len(MAGIC) + 8 + 32
    if type(raw) is not bytes or len(raw) < header or raw[:len(MAGIC)] != MAGIC:
        raise InitError('frame_header')
    size = struct.unpack('>Q', raw[len(MAGIC):len(MAGIC) + 8])[0]
    if size > max_payload_bytes(policy['max_output_bytes']) or len(raw) != header + size:
        raise InitError('frame_limit')
    payload = raw[header:]
    if hashlib.sha256(payload).digest() != raw[len(MAGIC) + 8:header]:
        raise InitError('frame_checksum')
    document = _json(payload)
    expected = {'version', 'job_id', 'envelope_sha256', 'outcome', 'reason', 'analysis_exit_code',
                'writers_reaped', 'files', 'logs'}
    if (type(document) is not dict or set(document) != expected
            or document['version'] != VERSION or document['job_id'] != policy['job_id']
            or document['envelope_sha256'] != policy['envelope_sha256']
            or type(document['outcome']) is not str
            or document['outcome'] not in {'completed', 'failed', 'timed_out', 'cancelled'}
            or type(document['reason']) is not str or not re.fullmatch(r'[a-z_]{1,64}', document['reason'])
            or type(document['writers_reaped']) is not bool
            or (document['analysis_exit_code'] is not None
                and not _integer(document['analysis_exit_code'], -255, 255))
            or type(document['files']) is not dict or type(document['logs']) is not dict
            or set(document['logs']) != {'stdout', 'stderr'}):
        raise InitError('frame_document')
    completed = document['outcome'] == 'completed'
    if (completed and (document['writers_reaped'] is not True or document['analysis_exit_code'] != 0
                       or document['reason'] != 'completed' or sorted(document['files']) != policy['expected_names'])
            or not completed and document['files']):
        raise InitError('frame_result')
    decoded = {'files': {}, 'logs': {}}
    total = 0
    for group in ('files', 'logs'):
        for name, encoded in document[group].items():
            if type(encoded) is not str:
                raise InitError('frame_encoding')
            try:
                value = base64.b64decode(encoded, validate=True)
            except (ValueError, UnicodeError):
                raise InitError('frame_encoding') from None
            total += len(value)
            if total > policy['max_output_bytes']:
                raise InitError('frame_output_limit')
            if group == 'logs' and len(value) > policy[f'{name}_max_bytes']:
                raise InitError('frame_log_limit')
            decoded[group][name] = value
    if sum(map(len, decoded['files'].values())) > policy['output_file_budget_bytes']:
        raise InitError('frame_output_limit')
    return document, decoded


def _stamp(info):
    return (info.st_dev, info.st_ino, info.st_mode, info.st_nlink,
            info.st_uid, info.st_gid, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def collect_outputs_fd(directory_fd, *, expected_names, maximum, expected_uid, deadline=None):
    """Bounded byte extraction from an already quiescent directory FD.

    This pure filesystem helper is not a writer-stop or type/format acceptance
    receipt. The real entrypoint calls it only after waitpid reports ECHILD.
    """
    if (type(expected_names) is not list or not 1 <= len(expected_names) <= MAX_NAMES
            or len(set(expected_names)) != len(expected_names)
            or any(type(name) is not str or not _NAME.fullmatch(name) for name in expected_names)
            or not _integer(maximum, 1, MAX_OUTPUT) or not _integer(expected_uid, 0, 2**32 - 2)):
        raise InitError('output_declaration')
    root_before = os.fstat(directory_fd)
    if not stat.S_ISDIR(root_before.st_mode):
        raise InitError('output_directory')
    names = []
    with os.scandir(directory_fd) as iterator:
        for entry in iterator:
            if len(names) >= len(expected_names):
                raise InitError('output_inventory')
            names.append(entry.name)
    if sorted(names) != sorted(expected_names):
        raise InitError('output_inventory')
    result, total = {}, 0
    for name in sorted(names):
        if deadline is not None and time.monotonic() >= deadline:
            raise InitError('output_deadline')
        before = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
        if (not stat.S_ISREG(before.st_mode) or before.st_nlink != 1 or before.st_uid != expected_uid
                or before.st_size < 0 or before.st_size > maximum - total or before.st_dev != root_before.st_dev):
            raise InitError('output_file')
        descriptor = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC, dir_fd=directory_fd)
        try:
            if _stamp(before) != _stamp(os.fstat(descriptor)):
                raise InitError('output_changed')
            data = bytearray()
            while len(data) <= before.st_size:
                if deadline is not None and time.monotonic() >= deadline:
                    raise InitError('output_deadline')
                chunk = os.read(descriptor, min(64 * 1024, before.st_size + 1 - len(data)))
                if not chunk:
                    break
                data.extend(chunk)
            if (len(data) != before.st_size or _stamp(before) != _stamp(os.fstat(descriptor))
                    or _stamp(before) != _stamp(os.stat(name, dir_fd=directory_fd, follow_symlinks=False))):
                raise InitError('output_changed')
            total += len(data)
            result[name] = bytes(data)
        finally:
            os.close(descriptor)
    if _stamp(root_before) != _stamp(os.fstat(directory_fd)):
        raise InitError('output_changed')
    return result


def _guard_guest_root(*, init):
    # Every privileged/process-group operation checks this independently. Never
    # relax this for unit tests or run this file on a host as a helper program.
    if (sys.platform != 'linux' or os.geteuid() != 0 or os.getuid() != 0
            or (os.getpid() != 1 if init else os.getppid() != 1)):
        raise InitError('guest_pid1_required')
    try:
        info = os.stat('/proc/gvisor', follow_symlinks=False)
    except OSError:
        raise InitError('gvisor_guest_required') from None
    if not stat.S_ISDIR(info.st_mode):
        raise InitError('gvisor_guest_required')


def _status():
    result = {}
    with open('/proc/self/status', encoding='ascii') as stream:
        for line in stream:
            key, _, value = line.partition(':')
            if key in {'CapInh', 'CapPrm', 'CapEff', 'CapBnd', 'CapAmb', 'NoNewPrivs'}:
                result[key] = int(value.strip(), 10 if key == 'NoNewPrivs' else 16)
    if set(result) != {'CapInh', 'CapPrm', 'CapEff', 'CapBnd', 'CapAmb', 'NoNewPrivs'}:
        raise InitError('capability_readback')
    return result


def _prctl(option, argument=0):
    # This helper is also guarded after the child drops UID. It must never
    # alter capabilities or privileges on an ordinary host process.
    if sys.platform != 'linux' or not (os.getpid() == 1 or os.getppid() == 1):
        raise InitError('guest_pid1_required')
    try:
        if not stat.S_ISDIR(os.stat('/proc/gvisor', follow_symlinks=False).st_mode):
            raise InitError('gvisor_guest_required')
    except OSError:
        raise InitError('gvisor_guest_required') from None
    libc = ctypes.CDLL(None, use_errno=True)
    if libc.prctl(ctypes.c_int(option), ctypes.c_ulong(argument), ctypes.c_ulong(0),
                  ctypes.c_ulong(0), ctypes.c_ulong(0)) != 0:
        raise InitError('prctl_failed')


def _mount_specs(policy):
    policy = validate_policy(policy)
    return (('/outputs', policy['output_file_budget_bytes'], OUTPUT_INODES),
            ('/scratch', policy['scratch_max_bytes'], SCRATCH_INODES))


def _verify_empty_mount(path, maximum, inodes):
    """Read back fixed fresh tmpfs quotas before any untrusted writer exists."""
    info = os.stat(path, follow_symlinks=False)
    fs = os.statvfs(path)
    if (not stat.S_ISDIR(info.st_mode) or stat.S_IMODE(info.st_mode) != 0o700
            or (info.st_uid, info.st_gid) != (CHILD_UID, CHILD_GID)
            or fs.f_frsize != 4096 or fs.f_bsize != 4096
            or fs.f_blocks * fs.f_frsize != maximum or fs.f_bfree != fs.f_blocks
            or fs.f_bavail != fs.f_blocks or fs.f_files != inodes
            or fs.f_ffree != inodes - 1 or fs.f_favail != inodes - 1
            or fs.f_flag & 14 != 14 or fs.f_flag & 1):
        raise InitError('tmpfs_quota_readback')


def _mount_guest_tmpfs(policy):
    _guard_guest_root(init=True)
    # runsc's OCI tmpfs whitelist drops nr_inodes in the pinned release. The
    # guest mount syscall passes this fixed data directly to the filesystem.
    # No user-selected mount path, source, flag, inode limit or UID is accepted.
    specs = _mount_specs(policy)
    for path, _maximum, _inodes in specs:
        if not stat.S_ISDIR(os.stat(path, follow_symlinks=False).st_mode):
            raise InitError('tmpfs_mountpoint')
    libc = ctypes.CDLL(None, use_errno=True)
    for path, maximum, inodes in specs:
        data = f'size={maximum},nr_inodes={inodes},uid={CHILD_UID},gid={CHILD_GID},mode=0700'.encode('ascii')
        if libc.mount(ctypes.c_char_p(b'tmpfs'), ctypes.c_char_p(path.encode('ascii')),
                      ctypes.c_char_p(b'tmpfs'), ctypes.c_ulong(14), ctypes.c_char_p(data)) != 0:
            raise InitError('tmpfs_mount_failed')
        _verify_empty_mount(path, maximum, inodes)


def _set_init_capabilities():
    _guard_guest_root(init=True)
    class Header(ctypes.Structure):
        _fields_ = [('version', ctypes.c_uint32), ('pid', ctypes.c_int)]
    class Data(ctypes.Structure):
        _fields_ = [('effective', ctypes.c_uint32), ('permitted', ctypes.c_uint32),
                    ('inheritable', ctypes.c_uint32)]
    header = Header(0x20080522, 0)  # _LINUX_CAPABILITY_VERSION_3, current task.
    wanted = sum(1 << number for number in INIT_CAPS)
    data = (Data * 2)(Data(wanted, wanted, 0), Data(0, 0, 0))
    libc = ctypes.CDLL(None, use_errno=True)
    if libc.capset(ctypes.byref(header), ctypes.byref(data)) != 0:
        raise InitError('capset_failed')


def _harden_init(policy):
    _guard_guest_root(init=True)
    initial = sum(1 << number for number in START_CAPS)
    wanted = sum(1 << number for number in INIT_CAPS)
    status = _status()
    if (status['CapEff'] != initial or status['CapPrm'] != initial or status['CapBnd'] != initial
            or any(status[key] != 0 for key in ('CapInh', 'CapAmb')) or status['NoNewPrivs'] != 1):
        raise InitError('init_capabilities')
    _prctl(4, 0)  # PR_SET_DUMPABLE: the child cannot access PID1's control FDs.
    _prctl(8, 0)  # PR_SET_KEEPCAPS disabled before the child's UID transition.
    _mount_guest_tmpfs(policy)
    # Only declared bounding bits are set. Drop these with CAP_SETPCAP while
    # retaining current effective capabilities until the separate child drops UID.
    for capability in START_CAPS:
        _prctl(24, capability)
    _set_init_capabilities()  # Remove SYS_ADMIN from CURRENT permitted/effective too.
    _prctl(47, 4)  # PR_CAP_AMBIENT_CLEAR_ALL.
    status = _status()
    if (status['CapBnd'] != 0 or status['CapEff'] != wanted or status['CapPrm'] != wanted
            or status['CapInh'] != 0 or status['CapAmb'] != 0 or status['NoNewPrivs'] != 1):
        raise InitError('bounding_readback')


def _drop_child(*, file_budget):
    _guard_guest_root(init=False)
    os.setgroups([])
    os.setresgid(CHILD_GID, CHILD_GID, CHILD_GID)
    os.setresuid(CHILD_UID, CHILD_UID, CHILD_UID)
    _prctl(47, 4)  # PR_CAP_AMBIENT_CLEAR_ALL.
    _prctl(38, 1)  # PR_SET_NO_NEW_PRIVS.
    status = _status()
    if (any(status[key] != 0 for key in ('CapInh', 'CapPrm', 'CapEff', 'CapBnd', 'CapAmb'))
            or status['NoNewPrivs'] != 1 or os.getgroups()
            or os.getresuid() != (CHILD_UID,) * 3 or os.getresgid() != (CHILD_GID,) * 3):
        raise InitError('child_privileges')
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    resource.setrlimit(resource.RLIMIT_NOFILE, (MAX_FDS, MAX_FDS))
    resource.setrlimit(resource.RLIMIT_FSIZE, (file_budget, file_budget))
    resource.setrlimit(resource.RLIMIT_NPROC, (MAX_GUEST_TASKS - 1,) * 2)


def _kill_and_reap(*, deadline, drain):
    _guard_guest_root(init=True)
    # No other trusted host exec is permitted for this container. Every guest
    # task is PID1 or a descendant of its one analysis child. ECHILD is therefore
    # the quiescence condition, rather than a main-process exit or ps snapshot.
    while True:
        if time.monotonic() >= deadline:
            return False
        try:
            os.kill(-1, signal.SIGKILL)
        except ProcessLookupError:
            pass
        try:
            while True:
                pid, _ = os.waitpid(-1, os.WNOHANG)
                if pid == 0:
                    break
        except ChildProcessError:
            return True
        drain()
        time.sleep(0.01)


def _run(policy):
    _guard_guest_root(init=True)
    deadline = time.monotonic() + policy['wall_seconds']
    _harden_init(policy)
    # Reserve cleanup inside the approved wall limit; never add time beyond it.
    analysis_deadline = deadline - min(2.0, policy['wall_seconds'] / 4)
    cancelled = False

    def cancel(_signum, _frame):
        nonlocal cancelled
        cancelled = True

    signal.signal(signal.SIGTERM, cancel)
    signal.signal(signal.SIGINT, cancel)
    stdout_r, stdout_w = os.pipe2(os.O_CLOEXEC)
    stderr_r, stderr_w = os.pipe2(os.O_CLOEXEC)
    stdin_r, stdin_w = os.pipe2(os.O_CLOEXEC)
    os.close(stdin_w)  # EOF stdin for the analysis; no host-readable FD.
    child = os.fork()
    if child == 0:
        try:
            os.dup2(stdin_r, 0)
            os.dup2(stdout_w, 1)
            os.dup2(stderr_w, 2)
            os.closerange(3, 1 << 20)
            _drop_child(file_budget=policy['output_file_budget_bytes'])
            os.chdir('/outputs')
            os.execve('/usr/local/bin/python3',
                      ['/usr/local/bin/python3', '-I', '-B', '/inputs/analysis.py'], dict(os.environ))
        except BaseException:
            os.write(2, b'c23_child_start_failed\n')
            os._exit(126)
    os.close(stdin_r)
    os.close(stdout_w)
    os.close(stderr_w)
    logs = {'stdout': bytearray(), 'stderr': bytearray()}
    selector = selectors.DefaultSelector()
    for descriptor, name in ((stdout_r, 'stdout'), (stderr_r, 'stderr')):
        os.set_blocking(descriptor, False)
        selector.register(descriptor, selectors.EVENT_READ, name)
    overflow = False

    def drain():
        nonlocal overflow
        for key, _ in selector.select(0):
            try:
                chunk = os.read(key.fd, 64 * 1024)
            except BlockingIOError:
                continue
            if not chunk:
                selector.unregister(key.fd)
                os.close(key.fd)
                continue
            limit = policy[key.data + '_max_bytes']
            room = limit - len(logs[key.data])
            logs[key.data].extend(chunk[:room])
            if len(chunk) > room:
                overflow = True

    exit_code, reason, outcome, quiescent = None, 'adapter_failure', 'failed', False
    files = {}
    try:
        while True:
            drain()
            pid, status = os.waitpid(child, os.WNOHANG)
            if pid:
                exit_code = os.waitstatus_to_exitcode(status)
                reason, outcome = ('completed', 'completed') if exit_code == 0 else ('analysis_nonzero', 'failed')
                break
            if cancelled:
                reason, outcome = 'cancelled', 'cancelled'
                break
            if overflow:
                reason = 'log_limit'
                break
            if time.monotonic() >= analysis_deadline:
                reason, outcome = 'wall_limit', 'timed_out'
                break
            selector.select(min(0.05, max(0, analysis_deadline - time.monotonic())))
        quiescent = _kill_and_reap(deadline=min(deadline, time.monotonic() + 2), drain=drain)
        if not quiescent:
            reason, outcome = 'writers_not_reaped', 'failed'
        else:
            while selector.get_map() and time.monotonic() < deadline:
                drain()
            if selector.get_map():
                reason, outcome = 'log_pipe_not_drained', 'failed'
            if overflow:
                reason, outcome = 'log_limit', 'failed'
            if outcome == 'completed':
                descriptor = os.open('/outputs', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
                try:
                    files = collect_outputs_fd(descriptor, expected_names=policy['expected_names'],
                                               maximum=policy['output_file_budget_bytes'], expected_uid=CHILD_UID,
                                               deadline=deadline)
                finally:
                    os.close(descriptor)
    except (OSError, InitError, ValueError):
        files, reason, outcome = {}, 'adapter_failure', 'failed'
        quiescent = _kill_and_reap(deadline=min(deadline, time.monotonic() + 2), drain=drain)
    finally:
        for key in list(selector.get_map().values()):
            selector.unregister(key.fd)
            os.close(key.fd)
        selector.close()
    if outcome != 'completed':
        files = {}
    return {'version': VERSION, 'job_id': policy['job_id'], 'envelope_sha256': policy['envelope_sha256'],
            'outcome': outcome, 'reason': reason, 'analysis_exit_code': exit_code, 'writers_reaped': quiescent,
            'files': {name: base64.b64encode(raw).decode('ascii') for name, raw in files.items()},
            'logs': {name: base64.b64encode(raw).decode('ascii') for name, raw in logs.items()}}


def main(argv=None):
    try:
        _guard_guest_root(init=True)
        args = sys.argv[1:] if argv is None else argv
        if len(args) != 2 or args[0] != '--policy' or len(args[1].encode()) > 16384:
            raise InitError('policy_arguments')
        policy = validate_policy(_json(args[1]))
        document = _run(policy)
        frame = encode_frame(document, max_output_bytes=policy['max_output_bytes'])
        # Only PID1 retains this stdout. The analysis receives distinct pipes;
        # none of its bytes are interpreted as transport framing or metadata.
        view = memoryview(frame)
        while view:
            view = view[os.write(1, view):]
        return 0 if document['outcome'] == 'completed' else 1
    except (InitError, OSError, ValueError):
        os.write(2, b'c23_trusted_init_refused\n')
        return 125


if __name__ == '__main__':
    raise SystemExit(main())
