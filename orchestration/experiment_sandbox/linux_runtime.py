"""Operator-only Linux/runsc execution for C23 acceptance, never dispatch wiring.

Generated Python runs only in the separately pinned gVisor guest. The host runs
the pinned runtime and a small trusted watchdog. A private durable flock spans
all effects. Missing acknowledgements/state never imply termination or release.
Every result keeps C22 capacity and production dispatch disabled.
"""
from __future__ import annotations

# ruff: noqa: E402 -- the stdlib helper must exit before project/native imports.

from dataclasses import dataclass
import ctypes
import hashlib
import json
import math
import os
from pathlib import Path
import re
import select
import selectors
import signal
import stat
import subprocess
import sys
import time
import uuid


def _host_helper_fd(text, suffix, *, job_id):
    if not re.fullmatch(r'[0-9]{1,7}', text) or not 3 <= int(text) < 1 << 20:
        raise ValueError
    descriptor = int(text)
    target = os.readlink(f'/proc/self/fd/{descriptor}')
    pattern = r'/sys/fs/cgroup/ocean-c23/' + re.escape(job_id) + '/' + re.escape(suffix)
    if (not re.fullmatch(r'c23-[a-f0-9]{48}', job_id)
            or not re.fullmatch(pattern, target) or not stat.S_ISREG(os.fstat(descriptor).st_mode)
            or (os.fstat(descriptor).st_dev, os.fstat(descriptor).st_ino)
            != (os.stat(target).st_dev, os.stat(target).st_ino)):
        raise ValueError
    return descriptor


def _host_helper_main(arguments):
    """Fresh stdlib-only process; never imports project/native scientific code."""
    if sys.platform != 'linux' or os.getuid() != 0 or os.geteuid() != 0:
        raise ValueError
    if arguments and arguments[0] == '--c23-watchdog' and len(arguments) == 6:
        kill_fd = _host_helper_fd(arguments[1], 'cgroup.kill', job_id=arguments[4])
        read_fd = int(arguments[2])
        if (not re.fullmatch(r'[0-9]{1,7}', arguments[2]) or not 3 <= read_fd < 1 << 20
                or read_fd == kill_fd or not stat.S_ISFIFO(os.fstat(read_fd).st_mode)):
            raise ValueError
        deadline = float(arguments[3])
        if not math.isfinite(deadline) or deadline <= 0 or deadline > time.monotonic() + 600:
            raise ValueError
        ready_fd = int(arguments[5])
        if (not re.fullmatch(r'[0-9]{1,7}', arguments[5]) or not 3 <= ready_fd < 1 << 20
                or ready_fd in {kill_fd, read_fd} or not stat.S_ISFIFO(os.fstat(ready_fd).st_mode)):
            raise ValueError
        if os.write(ready_fd, b'R') != 1:
            raise ValueError
        os.close(ready_fd)
        while True:
            remaining = deadline - time.monotonic()
            ready = select.select([read_fd], [], [], max(0.0, remaining))[0]
            if ready and os.read(read_fd, 1) == b'X':
                return 0
            if ready or time.monotonic() >= deadline:
                os.write(kill_fd, b'1\n')
                return 0
    if arguments and arguments[0] == '--c23-runsc-launch' and len(arguments) >= 9:
        group_fd = _host_helper_fd(arguments[1], 'host/cgroup.procs', job_id=arguments[-1])
        cancel_fd, parent_pid = int(arguments[2]), int(arguments[3])
        if (not 3 <= cancel_fd < 1 << 20 or not stat.S_ISFIFO(os.fstat(cancel_fd).st_mode)
                or not 1 <= parent_pid < 2**31 or cancel_fd == group_fd):
            raise ValueError
        # Set this before testing PPID: an already-dead parent is detected by
        # the check; a later death is handled by the kernel. No placement/exec
        # occurs in the fork/exec/bootstrap gap before this guarded point.
        libc = ctypes.CDLL(None, use_errno=True)
        if libc.prctl(ctypes.c_int(1), ctypes.c_ulong(signal.SIGKILL),
                      ctypes.c_ulong(0), ctypes.c_ulong(0), ctypes.c_ulong(0)) != 0:
            raise ValueError
        deadline = float(arguments[4])
        if not math.isfinite(deadline) or deadline <= 0 or deadline > time.monotonic() + 600:
            raise ValueError
        def require_parent():
            if (os.getppid() != parent_pid or select.select([cancel_fd], [], [], 0)[0]
                    or time.monotonic() >= deadline):
                raise ValueError
        require_parent()
        digest, executable, *argv = arguments[5:]
        if (not re.fullmatch(r'[a-f0-9]{64}', digest)
                or not re.fullmatch(r'/opt/ocean-c23-runtime/release-[0-9]{8}(?:\.[0-9]+)?/runsc', executable)
                or not argv or not re.fullmatch(r'c23-[a-f0-9]{48}', argv[-1])):
            raise ValueError
        command = next((value for value in argv if not value.startswith('--')), None)
        if command not in {'create', 'state', 'start', 'wait', 'delete'}:
            raise ValueError
        fd = os.open(executable, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
        info = os.fstat(fd)
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o022
                or info.st_nlink != 1 or not 1 <= info.st_size <= 256 * 1024**2):
            raise ValueError
        checksum = hashlib.sha256()
        size = 0
        while True:
            raw = os.read(fd, 1024 * 1024)
            if not raw:
                break
            size += len(raw)
            if size > info.st_size:
                raise ValueError
            checksum.update(raw)
        if checksum.hexdigest() != digest or size != info.st_size:
            raise ValueError
        require_parent()
        pid = str(os.getpid()).encode()
        if os.write(group_fd, pid) != len(pid):
            raise ValueError
        # A concurrent cleanup may have killed an empty group just before this
        # join. Cancellation is rechecked AFTER joining, so no late queued
        # command can execute once the controller has begun cleanup.
        require_parent()
        os.close(group_fd)
        os.close(cancel_fd)
        os.execve(fd, [executable, *argv], {'PATH': '/usr/sbin:/usr/bin:/sbin:/bin', 'LANG': 'C.UTF-8'})
    raise ValueError


if __name__ == '__main__':
    # Deliberately BEFORE project imports: numpy/Arrow/native thread pools are
    # never loaded into the launcher/watchdog. Popen does no Python preexec.
    try:
        raise SystemExit(_host_helper_main(sys.argv[1:]))
    except (OSError, ValueError, TypeError, OverflowError):
        raise SystemExit('c23_host_helper_refused') from None


from orchestration.experiment_sandbox.contracts import SandboxError, VerifiedEnvelope
from orchestration.experiment_sandbox.files import ValidatedOutputs, validate_outputs
from orchestration.experiment_sandbox.journal import DurableExecutionJournal
from orchestration.experiment_sandbox.profile import RuntimePreparation
from orchestration.experiment_sandbox.traversal import private_directory
from orchestration.experiment_sandbox.profile_execution import (
    PreparedExecutionProfile, render_execution_profile,
)
from sandbox.experiment.trusted_init import MAGIC, InitError, decode_frame, max_payload_bytes
from schema.context_catalogue import canonical_json
from schema.research_experiments import content_sha256

VERSION = 'c23-linux-runsc-operator-v1'
MAX_COMMAND_BYTES = 64 * 1024
MAX_RUNTIME_STDERR = 1024 * 1024
MAX_ENFORCEMENT_BYTES = 48 * 1024
MAX_NATIVE_PROCESSES = 128
_SHA = re.compile(r'^[a-f0-9]{64}$')
_JOB = re.compile(r'^c23-[a-f0-9]{48}$')


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _read(path, maximum=MAX_COMMAND_BYTES):
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC)
    try:
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            raise SandboxError('sandbox_host_integrity')
        result = bytearray()
        while len(result) <= maximum:
            value = os.read(descriptor, min(65536, maximum + 1 - len(result)))
            if not value:
                break
            result.extend(value)
        if len(result) > maximum:
            raise SandboxError('sandbox_host_limit')
        return bytes(result)
    finally:
        os.close(descriptor)


def _read_at(directory, name, maximum):
    """Bounded procfs/cgroup read anchored to an already opened directory."""
    descriptor = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC,
                         dir_fd=directory)
    try:
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            raise SandboxError('sandbox_native_process_identity')
        result = bytearray()
        while len(result) <= maximum:
            value = os.read(descriptor, min(65536, maximum + 1 - len(result)))
            if not value:
                break
            result.extend(value)
        if len(result) > maximum:
            raise SandboxError('sandbox_host_limit')
        return bytes(result)
    finally:
        os.close(descriptor)


def _open_process_directory(pid):
    if type(pid) is not int or not 1 < pid < 2**31:
        raise SandboxError('sandbox_native_process_identity')
    return os.open(f'/proc/{pid}', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)


def _kernel_ascii(raw):
    if any(value < 32 and value not in (9, 10) or value > 126 for value in raw):
        raise SandboxError('sandbox_native_process_identity')
    return raw.decode('ascii')


def _process_stat_identity(raw, pid):
    text = _kernel_ascii(raw)
    if not text.startswith(str(pid) + ' (') or ') ' not in text:
        raise SandboxError('sandbox_native_process_identity')
    fields = text[text.rfind(') ') + 2:].split()
    if (not 50 <= len(fields) <= 128 or fields[0] not in {'R', 'S', 'D', 'T', 't', 'W', 'P', 'I'}
            or not re.fullmatch(r'0|[1-9][0-9]{0,9}', fields[1]) or int(fields[1]) >= 2**31
            or not re.fullmatch(r'[1-9][0-9]{0,19}', fields[19])
            or int(fields[19]) >= 2**64):
        raise SandboxError('sandbox_native_process_identity')
    return int(fields[19]), int(fields[1])


def _native_nofile(raw, expected):
    text = _kernel_ascii(raw)
    rows = [line for line in text.splitlines() if line.startswith('Max open files')]
    if len(rows) != 1:
        raise SandboxError('sandbox_native_nofile_enforcement')
    match = re.fullmatch(r'Max open files\s+(0|[1-9][0-9]{0,9})\s+'
                         r'(0|[1-9][0-9]{0,9})\s+files\s*', rows[0])
    if (match is None or type(expected) is not int or expected != 4096
            or tuple(map(int, match.groups())) != (expected, expected)):
        raise SandboxError('sandbox_native_nofile_enforcement')
    return {'soft': expected, 'hard': expected}


def _native_process_observation(pid):
    """Read through one proc-directory FD and reject reuse, exec or membership races.

    The opened proc-directory inode stays bound to that process, not a future
    reuse of its numeric PID. Missing files after exit are errors, never an
    observation about a replacement process.
    """
    descriptor = _open_process_directory(pid)
    try:
        directory = os.fstat(descriptor)
        if not stat.S_ISDIR(directory.st_mode):
            raise SandboxError('sandbox_native_process_identity')
        before = _read_at(descriptor, 'stat', 2048)
        start, parent = _process_stat_identity(before, pid)
        command = _read_at(descriptor, 'cmdline', 8192)
        # Empty argv is only an observation here. Classification below accepts
        # it solely for a positively bound child of the authenticated Sentry.
        if command and (not command.endswith(b'\0') or not command[:-1]):
            raise SandboxError('sandbox_native_process_identity')
        arguments = command[:-1].split(b'\0') if command else []
        if (len(arguments) > 256 or any(not item or any(c < 32 or c > 126 for c in item)
                                      for item in arguments)):
            raise SandboxError('sandbox_native_process_identity')
        membership = _read_at(descriptor, 'cgroup', 1024)
        limits = _read_at(descriptor, 'limits', 8192)
        executable = os.stat('exe', dir_fd=descriptor)
        after = _read_at(descriptor, 'stat', 2048)
        if ((start, parent) != _process_stat_identity(after, pid)
                or command != _read_at(descriptor, 'cmdline', 8192)
                or membership != _read_at(descriptor, 'cgroup', 1024)
                or limits != _read_at(descriptor, 'limits', 8192)
                or _stamp(executable) != _stamp(os.stat('exe', dir_fd=descriptor))
                or (directory.st_dev, directory.st_ino)
                != (os.fstat(descriptor).st_dev, os.fstat(descriptor).st_ino)):
            raise SandboxError('sandbox_native_process_changed')
        return {'pid': pid, 'start_time_ticks': start, 'parent_pid': parent,
            'proc_directory_identity': [directory.st_dev, directory.st_ino],
            'argv': [item.decode('ascii') for item in arguments],
            'cmdline_sha256': _sha(command), 'cmdline_empty': not command,
            'cmdline_bytes': len(command), 'stat_before': _kernel_ascii(before),
            'stat_after': _kernel_ascii(after), 'cgroup': _kernel_ascii(membership),
            'limits': _kernel_ascii(limits), 'executable_identity': list(_stamp(executable))}
    finally:
        os.close(descriptor)


def _write_control(path, raw):
    descriptor = os.open(path, os.O_WRONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        if not stat.S_ISREG(os.fstat(descriptor).st_mode) or os.write(descriptor, raw) != len(raw):
            raise SandboxError('sandbox_cgroup_integrity')
    finally:
        os.close(descriptor)


def _private(path, *, allow_search=False):
    try:
        return private_directory(path, allow_search=allow_search)
    except (OSError, ValueError):
        raise SandboxError('sandbox_worker_integrity')


def _require_linux_host(journal, cgroup_root):
    if (sys.platform != 'linux' or os.getuid() != 0 or os.geteuid() != 0
            or type(journal) is not DurableExecutionJournal):
        raise SandboxError('sandbox_linux_root_required')
    if Path(cgroup_root) != Path('/sys/fs/cgroup'):
        raise SandboxError('sandbox_cgroup_integrity')
    boot = _read('/proc/sys/kernel/random/boot_id', 128).decode('ascii').strip()
    if str(uuid.UUID(boot)) != boot or boot != journal.host_boot_id:
        raise SandboxError('sandbox_host_boot_changed')
    mounts = _read('/proc/self/mountinfo', 2 * 1024**2).decode('ascii').splitlines()
    if not any(' - ' in line and line.split(' - ', 1)[0].split()[4] == str(cgroup_root)
               and line.split(' - ', 1)[1].split()[0] == 'cgroup2' for line in mounts):
        raise SandboxError('sandbox_cgroup_v2_required')


def _stamp(info):
    return (info.st_dev, info.st_ino, info.st_mode, info.st_uid, info.st_gid,
            info.st_nlink, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def _hash_runtime_file(path):
    before = path.lstat()
    if (not stat.S_ISREG(before.st_mode) or before.st_nlink != 1
            or before.st_uid != os.geteuid() or before.st_mode & 0o022
            or not 1 <= before.st_size <= 256 * 1024**2):
        raise SandboxError('sandbox_runtime_identity')
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        if _stamp(os.fstat(descriptor)) != _stamp(before):
            raise SandboxError('sandbox_runtime_identity')
        digest, size = hashlib.sha256(), 0
        while True:
            raw = os.read(descriptor, 1024 * 1024)
            if not raw:
                break
            size += len(raw)
            if size > before.st_size:
                raise SandboxError('sandbox_runtime_identity')
            digest.update(raw)
        if (size != before.st_size or _stamp(os.fstat(descriptor)) != _stamp(before)
                or _stamp(path.lstat()) != _stamp(before)):
            raise SandboxError('sandbox_runtime_identity')
        return digest.hexdigest()
    finally:
        os.close(descriptor)


def _put(path, raw, *, reuse=False):
    if path.exists() or path.is_symlink():
        if not reuse or path.is_symlink() or _read(path, len(raw)) != raw:
            raise SandboxError('sandbox_retention_integrity')
        info = path.lstat()
        if info.st_uid != os.geteuid() or info.st_mode & 0o222 or info.st_nlink != 1:
            raise SandboxError('sandbox_retention_integrity')
        return
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, 0o400)
    try:
        view = memoryview(raw)
        while view:
            count = os.write(descriptor, view)
            if count <= 0:
                raise SandboxError('sandbox_retention_integrity')
            view = view[count:]
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)


def _sync_directory(path):
    descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


class _Capture:
    def __init__(self, process, *, stdout_limit, stderr_limit, cancel_pipe=None):
        self.process, self.stdout, self.stderr = process, bytearray(), bytearray()
        self.cancel_pipe = cancel_pipe
        self._closed, self._eof_at_close = False, False
        self.selector = selectors.DefaultSelector()
        for stream, name, bound in ((process.stdout, 'stdout', stdout_limit),
                                    (process.stderr, 'stderr', stderr_limit)):
            os.set_blocking(stream.fileno(), False)
            self.selector.register(stream, selectors.EVENT_READ, (name, bound))

    def drain(self):
        for key, _ in self.selector.select(0):
            name, bound = key.data
            retained = getattr(self, name)
            raw = os.read(key.fd, min(65536, bound + 1 - len(retained)))
            if not raw:
                self.selector.unregister(key.fileobj)
                key.fileobj.close()
            else:
                retained.extend(raw)
                if len(retained) > bound:
                    raise SandboxError('sandbox_runtime_output_limit')

    @property
    def eof(self):
        return self._eof_at_close if self._closed else not self.selector.get_map()

    def close(self):
        if self._closed:
            return
        self._eof_at_close = not self.selector.get_map()
        self.cancel_launch()
        for key in list(self.selector.get_map().values()):
            self.selector.unregister(key.fileobj)
            key.fileobj.close()
        self.selector.close()
        self._closed = True

    def cancel_launch(self):
        if self.cancel_pipe is not None:
            os.close(self.cancel_pipe)
            self.cancel_pipe = None


class _Watchdog:
    def __init__(self, process, pipe):
        self.process, self.pipe = process, pipe
        self.pid = process.pid

    def require_alive(self):
        if self.process.poll() is not None:
            raise SandboxError('sandbox_watchdog_unavailable')

    def stop(self, *, proven):
        if self.pipe is not None:
            try:
                if proven:
                    os.write(self.pipe, b'X')
            except OSError:
                pass
            finally:
                os.close(self.pipe)
                self.pipe = None
        # With no stop byte, EOF tells the independent child to kill the exact
        # originally opened cgroup. Never signal an unverified/reused host PID.
        try:
            self.process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            pass


def _arm_watchdog(outer, deadline):
    if sys.platform != 'linux' or os.geteuid() != 0:
        raise SandboxError('sandbox_linux_root_required')
    kill_fd = os.open(outer / 'cgroup.kill', os.O_WRONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    read_fd, write_fd = os.pipe2(os.O_CLOEXEC)
    ready_read, ready_write = os.pipe2(os.O_CLOEXEC)
    process = None
    try:
        try:
            process = subprocess.Popen([sys.executable, '-I', '-S', '-B', str(Path(__file__).resolve()),
                '--c23-watchdog', str(kill_fd), str(read_fd), repr(deadline), outer.name, str(ready_write)],
                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                close_fds=True, pass_fds=(kill_fd, read_fd, ready_write),
                env={'PATH': '/usr/sbin:/usr/bin:/sbin:/bin', 'LANG': 'C.UTF-8'})
        finally:
            os.close(kill_fd)
            os.close(read_fd)
            os.close(ready_write)
        remaining = max(0.0, min(5.0, deadline - time.monotonic()))
        if (not select.select([ready_read], [], [], remaining)[0]
                or os.read(ready_read, 2) != b'R' or process.poll() is not None):
            raise SandboxError('sandbox_watchdog_unavailable')
    except BaseException:
        os.close(write_fd)
        if process is not None:
            try:
                process.wait(timeout=1)
            except subprocess.TimeoutExpired:
                pass
        raise
    finally:
        os.close(ready_read)
    return _Watchdog(process, write_fd)


@dataclass(frozen=True, init=False)
class LinuxExecutionResult:
    _json: str
    _outputs: ValidatedOutputs | None

    def __init__(self, document, outputs=None):
        if (type(document) is not dict or document.get('version') != VERSION
                or document.get('dispatch_eligible') is not False
                or document.get('reservation_released') is not False
                or document.get('scientific_approval') != 'not_independently_verified'
                or (outputs is not None and type(outputs) is not ValidatedOutputs)):
            raise SandboxError('sandbox_result_identity')
        object.__setattr__(self, '_json', canonical_json(document))
        object.__setattr__(self, '_outputs', outputs)

    @property
    def document(self):
        return json.loads(self._json)

    @property
    def outputs(self):
        return self._outputs

    @property
    def state(self):
        return self.document['state']


class LinuxExecutionAdapter:
    """Single-host operator acceptance adapter; no API/worker registration.

    The job must already contain approved staged inputs and a verified read-only
    materialized rootfs. The journal and worker root are private local storage.
    A fresh stdlib-only helper joins cgroups before exec, so project/native
    threads do not run Python after fork. There is no host-Python analysis or
    ordinary-container fallback.
    """

    def __init__(self, worker_root, runtime_directory, runtime_manifest, journal,
                 *, cgroup_root=Path('/sys/fs/cgroup')):
        self.worker_root = Path(worker_root)
        self.runtime_directory = Path(runtime_directory)
        self._runtime_json = canonical_json(RuntimePreparation.model_validate(runtime_manifest).model_dump(mode='json'))
        self._helper_sha256 = _hash_runtime_file(Path(__file__).resolve())
        self.journal = journal
        self.cgroup_root = Path(cgroup_root)
        self.clock = time.monotonic

    def _preflight(self, envelope, profile):
        _require_linux_host(self.journal, self.cgroup_root)
        _private(self.worker_root, allow_search=True)
        if type(envelope) is not VerifiedEnvelope or type(profile) is not PreparedExecutionProfile:
            raise SandboxError('sandbox_runtime_identity')
        document = profile.document
        job = _private(self.worker_root / envelope.job_id, allow_search=True)
        runtime = json.loads(self._runtime_json)
        if _hash_runtime_file(Path(__file__).resolve()) != self._helper_sha256:
            raise SandboxError('sandbox_host_helper_changed')
        if (document['job_id'] != envelope.job_id
                or document['envelope_sha256'] != envelope.envelope_sha256
                or document['runtime_preparation'] != runtime
                or document['config']['linux']['cgroupsPath'] != f'/ocean-c23/{envelope.job_id}/sandbox'):
            raise SandboxError('sandbox_runtime_identity')
        rerendered = render_execution_profile(envelope, job_root=job,
            image_receipt=document['image_preparation'], runtime_manifest=runtime,
            control_host_uid=document['trusted_init']['control_host_uid'],
            control_host_gid=document['trusted_init']['control_host_gid'],
            trusted_init_sha256=document['trusted_init']['sha256'])
        if rerendered.profile_sha256 != profile.profile_sha256:
            raise SandboxError('sandbox_profile_changed')
        root = self.runtime_directory
        if root != root.resolve(strict=True) or root.lstat().st_uid != os.geteuid() or root.lstat().st_mode & 0o022:
            raise SandboxError('sandbox_runtime_identity')
        sidecars = root / 'gvisor-bin'
        if (sidecars != sidecars.resolve(strict=True) or not sidecars.is_dir()
                or sidecars.lstat().st_uid != os.geteuid() or sidecars.lstat().st_mode & 0o022):
            raise SandboxError('sandbox_runtime_identity')
        observed = {entry.name for entry in sidecars.iterdir()}
        expected = {name.split('/', 1)[1] for name in runtime['files'] if name.startswith('gvisor-bin/')}
        if observed != expected or len(observed) > 126:
            raise SandboxError('sandbox_runtime_identity')
        for name, digest in runtime['files'].items():
            if _hash_runtime_file(root / name) != digest:
                raise SandboxError('sandbox_runtime_identity')
        machine = {'x86_64': 'amd64', 'aarch64': 'arm64'}.get(os.uname().machine)
        if machine != runtime['architecture'] or not os.access(root / 'runsc', os.X_OK):
            raise SandboxError('sandbox_runtime_identity')
        if not os.statvfs(job / 'rootfs').f_flag & os.ST_RDONLY:
            raise SandboxError('sandbox_rootfs_not_sealed')
        return job, document, content_sha256(runtime)

    def _paths(self, job_id):
        if type(job_id) is not str or not _JOB.fullmatch(job_id):
            raise SandboxError('sandbox_runtime_identity')
        outer = self.cgroup_root / 'ocean-c23' / job_id
        return outer, outer / 'host', outer / 'sandbox'

    def _prepare_cgroups(self, job_id, requirements):
        parent = self.cgroup_root / 'ocean-c23'
        if (parent != parent.resolve(strict=True) or parent.lstat().st_uid != os.geteuid()
                or parent.lstat().st_mode & 0o022
                or not {'cpu', 'memory', 'pids'} <= set(_read(parent / 'cgroup.controllers').decode().split())
                or not {'cpu', 'memory', 'pids'} <= set(_read(parent / 'cgroup.subtree_control').decode().split())):
            raise SandboxError('sandbox_cgroup_unavailable')
        outer, host, _ = self._paths(job_id)
        outer.mkdir(mode=0o700)
        if _read(outer / 'cgroup.type').strip() != b'domain':
            raise SandboxError('sandbox_cgroup_unavailable')
        for name, value in requirements['readback_before_start'].items():
            _write_control(outer / name, (str(value) + '\n').encode())
        _write_control(outer / 'cgroup.subtree_control', b'+cpu +memory +pids\n')
        host.mkdir(mode=0o700)
        info = outer.stat()
        return (info.st_dev, info.st_ino)

    def _spawn(self, argv, host, *, deadline, frame_limit=MAX_COMMAND_BYTES):
        if _hash_runtime_file(Path(__file__).resolve()) != self._helper_sha256:
            raise SandboxError('sandbox_host_helper_changed')
        descriptor = os.open(host / 'cgroup.procs', os.O_WRONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
        cancel_read, cancel_write = os.pipe()
        try:
            launch = [sys.executable, '-I', '-S', '-B', str(Path(__file__).resolve()),
                '--c23-runsc-launch', str(descriptor), str(cancel_read), str(os.getpid()),
                repr(deadline), json.loads(self._runtime_json)['files']['runsc'], *argv]
            process = subprocess.Popen(launch, stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, close_fds=True,
                pass_fds=(descriptor, cancel_read),
                cwd=self.worker_root, env={'PATH': '/usr/sbin:/usr/bin:/sbin:/bin', 'LANG': 'C.UTF-8'})
        except BaseException:
            os.close(cancel_write)
            raise
        finally:
            os.close(descriptor)
            os.close(cancel_read)
        return _Capture(process, stdout_limit=frame_limit, stderr_limit=MAX_RUNTIME_STDERR,
            cancel_pipe=cancel_write)

    def _wait(self, capture, *, deadline, lease, side=None, cancelled=lambda: False,
              require_eof=True, watchdog=None):
        while True:
            lease.require_current()
            capture.drain()
            if side is not None:
                side.drain()
            decision = cancelled()
            if type(decision) is not bool:
                raise SandboxError('sandbox_cancellation_invalid')
            if decision:
                raise SandboxError('sandbox_cancelled')
            if self.clock() >= deadline:
                raise SandboxError('sandbox_wall_limit')
            if watchdog is not None:
                watchdog.require_alive()
            code = capture.process.poll()
            if code is not None and (capture.eof or not require_eof):
                return code
            time.sleep(0.01)

    def _command(self, argv, host, *, deadline, lease, side=None, cancelled=lambda: False,
                 watchdog=None):
        capture = self._spawn(argv, host, deadline=deadline)
        try:
            code = self._wait(capture, deadline=deadline, lease=lease, side=side,
                cancelled=cancelled, watchdog=watchdog)
            return code, bytes(capture.stdout), bytes(capture.stderr)
        finally:
            # All commands are already inside the exact job cgroup. On error,
            # caller cleanup kills the cgroup; a lone CLI PID is no tree proof.
            capture.close()
            self._diagnose(argv, capture, lease)

    def _diagnose(self, argv, capture, lease):
        """Create-only private bounded diagnostics, never execution authority."""
        lease.require_current()
        job_id = argv[-1]
        if type(job_id) is not str or not _JOB.fullmatch(job_id):
            raise SandboxError('sandbox_runtime_identity')
        stage = next((value for value in argv[1:] if not value.startswith('--')), None)
        if stage not in {'create', 'state', 'start', 'wait', 'delete'}:
            raise SandboxError('sandbox_runtime_identity')
        job = _private(self.worker_root / job_id, allow_search=True)
        directory = job / 'diagnostics'
        if not directory.exists() and not directory.is_symlink():
            directory.mkdir(mode=0o700)
            _sync_directory(job)
        _private(directory)
        receipt_dir = directory / (stage + '-' + uuid.uuid4().hex)
        receipt_dir.mkdir(mode=0o700)
        _sync_directory(directory)
        stdout, stderr = bytes(capture.stdout), bytes(capture.stderr)
        prefix_out = stdout[:MAX_COMMAND_BYTES] if stage != 'create' else None
        prefix_err = stderr[:MAX_RUNTIME_STDERR]
        _put(receipt_dir / 'stderr.bin', prefix_err)
        if prefix_out is not None:
            _put(receipt_dir / 'stdout.bin', prefix_out)
        metadata = {'version': 'c23-private-runtime-diagnostics-v1', 'stage': stage,
            'job_id': job_id, 'epoch': lease.epoch if hasattr(lease, 'epoch') else None,
            'exit_status_observed': capture.process.poll(), 'pipes_eof': capture.eof,
            'stdout': {'captured_bytes': len(stdout), 'captured_sha256': _sha(stdout),
                'retained_bytes': len(prefix_out) if prefix_out is not None else 0,
                'retained_sha256': _sha(prefix_out) if prefix_out is not None else None,
                'body_retained': prefix_out is not None,
                'truncated': prefix_out is not None and len(prefix_out) != len(stdout)},
            'stderr': {'captured_bytes': len(stderr), 'captured_sha256': _sha(stderr),
                'retained_sha256': _sha(prefix_err),
                'retained_bytes': len(prefix_err), 'truncated': len(prefix_err) != len(stderr)},
            'private_operator_evidence_only': True, 'dispatch_eligible': False,
            'reservation_released': False, 'scientific_approval': 'not_independently_verified'}
        _put(receipt_dir / 'metadata.json', (canonical_json(metadata) + '\n').encode())

    def _owned_process_inventory(self, job_id, cgroup_identity):
        if (type(cgroup_identity) is not tuple or len(cgroup_identity) != 2
                or any(type(value) is not int or value < 0 for value in cgroup_identity)):
            raise SandboxError('sandbox_cgroup_identity')
        outer, host, sandbox = self._paths(job_id)
        result = {'groups': {}, 'processes': {}}
        for path in (outer, host, sandbox):
            descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
            try:
                info = os.fstat(descriptor)
                identity = (info.st_dev, info.st_ino)
                if (not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid()
                        or info.st_mode & 0o022 or path != path.resolve(strict=True)
                        or (path == outer and identity != cgroup_identity)):
                    raise SandboxError('sandbox_cgroup_identity')
                children = set()
                with os.scandir(descriptor) as entries:
                    for count, entry in enumerate(entries, 1):
                        if count > 256 or entry.is_symlink():
                            raise SandboxError('sandbox_cgroup_identity')
                        if entry.is_dir(follow_symlinks=False):
                            children.add(entry.name)
                if children != ({'host', 'sandbox'} if path == outer else set()):
                    raise SandboxError('sandbox_cgroup_identity')
                raw = _read_at(descriptor, 'cgroup.procs', 4096)
                lines = raw.decode('ascii').splitlines()
                if len(lines) > MAX_NATIVE_PROCESSES:
                    raise SandboxError('sandbox_native_process_identity')
                pids = []
                membership = '/ocean-c23/' + job_id + ('' if path == outer else '/' + path.name)
                for line in lines:
                    if not re.fullmatch(r'[1-9][0-9]{0,9}', line) or not 1 < int(line) < 2**31:
                        raise SandboxError('sandbox_native_process_identity')
                    pid = int(line)
                    if pid in result['processes']:
                        raise SandboxError('sandbox_native_process_identity')
                    result['processes'][pid] = membership
                    pids.append(pid)
                if len(result['processes']) > MAX_NATIVE_PROCESSES or (path == outer and pids):
                    raise SandboxError('sandbox_native_process_identity')
                current = path.lstat()
                if ((current.st_dev, current.st_ino, current.st_uid, current.st_gid, current.st_mode)
                        != (info.st_dev, info.st_ino, info.st_uid, info.st_gid, info.st_mode)):
                    raise SandboxError('sandbox_cgroup_identity')
                result['groups'][path.name] = {'identity': list(identity), 'pids': sorted(pids)}
            finally:
                os.close(descriptor)
        return result

    def _native_nofile_readback(self, job_id, sentry_pid, requirements, *, cgroup_identity,
                               lease, deadline, watchdog=None):
        """Verify actual host limits before start; OCI guest limits stay separate."""
        if (type(requirements.get('native_nofile_limit')) is not int
                or requirements['native_nofile_limit'] != 4096
                or type(requirements.get('analysis_nofile_limit')) is not int
                or requirements['analysis_nofile_limit'] != 256):
            raise SandboxError('sandbox_native_nofile_enforcement')
        def current():
            lease.require_current()
            if self.clock() >= deadline:
                raise SandboxError('sandbox_wall_limit')
            if watchdog is not None:
                watchdog.require_alive()
        current()
        inventory = self._owned_process_inventory(job_id, cgroup_identity)
        if sentry_pid not in inventory['processes']:
            raise SandboxError('sandbox_native_process_identity')
        roles, auxiliary, pinned_executables = {}, [], {}
        runtime = json.loads(self._runtime_json)
        state_flag = '--root=' + str(self.worker_root / ('runsc-state-' + job_id))

        def observe(pid):
            current()
            observed = _native_process_observation(pid)
            if observed['cgroup'] != '0::' + inventory['processes'][pid] + '\n':
                raise SandboxError('sandbox_host_subtree_identity')
            return observed

        def executable_identity(observed, relative):
            executable = self.runtime_directory / relative
            if relative not in pinned_executables:
                if (relative not in runtime['files']
                        or _hash_runtime_file(executable) != runtime['files'][relative]):
                    raise SandboxError('sandbox_runtime_identity')
                pinned_executables[relative] = list(_stamp(executable.lstat()))
            if observed['executable_identity'] != pinned_executables[relative]:
                raise SandboxError('sandbox_runtime_identity')
            observed['executable_relative_path'] = relative
            observed['executable_sha256'] = runtime['files'][relative]

        def core(observed, role):
            argv = observed['argv']
            if (role in roles or not argv
                    or argv[0] != ('runsc-sandbox' if role == 'sentry' else 'runsc-gofer')
                    or argv[-1] != job_id or argv.count(state_flag) != 1):
                raise SandboxError('sandbox_native_process_identity')
            executable_identity(observed, 'gvisor-bin/gvisor_sentry' if role == 'sentry' else 'runsc')
            observed['nofile'] = _native_nofile(observed['limits'].encode('ascii'),
                                               requirements['native_nofile_limit'])
            roles[role] = observed

        # state.pid identifies the one core Sentry. Systrap forks native child
        # TGIDs without exec and unmaps their argv memory; they must never be
        # mistaken for another core or accepted merely because argv is empty.
        sentry = observe(sentry_pid)
        core(sentry, 'sentry')
        for pid in sorted(inventory['processes']):
            if pid == sentry_pid:
                continue
            observed = observe(pid)
            argv = observed['argv']
            if argv and argv[0] == 'runsc-gofer':
                core(observed, 'gofer')
                continue
            if not argv or argv[0] == 'runsc-sandbox':
                if (observed['parent_pid'] != sentry_pid
                        or observed['start_time_ticks'] < sentry['start_time_ticks']
                        or observed['cgroup'] != sentry['cgroup']
                        or (argv and argv != sentry['argv'])):
                    raise SandboxError('sandbox_native_process_identity')
                executable_identity(observed, 'gvisor-bin/gvisor_sentry')
                observed['nofile'] = _native_nofile(observed['limits'].encode('ascii'),
                                                   requirements['native_nofile_limit'])
                observed['classification'] = 'authenticated-systrap-child'
            elif argv == [str(self.runtime_directory / 'gvisor-bin/runsc-fd-parking')]:
                if (observed['cgroup'] != '0::/ocean-c23/' + job_id + '/host\n'
                        or observed['parent_pid'] != 1
                        or observed['start_time_ticks'] < sentry['start_time_ticks']):
                    raise SandboxError('sandbox_native_process_identity')
                executable_identity(observed, 'gvisor-bin/runsc-fd-parking')
                observed['classification'] = 'pinned-fd-parking-helper'
                observed['native_nofile_enforced_by_this_gate'] = False
            elif argv == ['gvisor-proc-umounter', '/proc']:
                if (observed['parent_pid'] != sentry_pid
                        or observed['start_time_ticks'] < sentry['start_time_ticks']
                        or observed['cgroup'] != sentry['cgroup']):
                    raise SandboxError('sandbox_native_process_identity')
                executable_identity(observed, 'gvisor-bin/gvisor-proc-umounter')
                observed['classification'] = 'pinned-proc-umounter-helper'
                observed['native_nofile_enforced_by_this_gate'] = False
            else:
                raise SandboxError('sandbox_native_process_identity')
            auxiliary.append(observed)
        if set(roles) != {'sentry', 'gofer'} or roles['sentry']['pid'] == roles['gofer']['pid']:
            raise SandboxError('sandbox_native_process_identity')
        # Re-read both cores and every authenticated auxiliary process. Parent,
        # PID/exec/cgroup/limit races cannot hide behind a stable PID inventory.
        for observed in [*roles.values(), *auxiliary]:
            current()
            again = _native_process_observation(observed['pid'])
            for field in ('start_time_ticks', 'parent_pid', 'proc_directory_identity', 'argv',
                          'cmdline_empty', 'cmdline_bytes', 'cmdline_sha256', 'cgroup',
                          'limits', 'executable_identity'):
                if again[field] != observed[field]:
                    raise SandboxError('sandbox_native_process_changed')
        for relative, identity in pinned_executables.items():
            if list(_stamp((self.runtime_directory / relative).lstat())) != identity:
                raise SandboxError('sandbox_runtime_identity')
        if inventory != self._owned_process_inventory(job_id, cgroup_identity):
            raise SandboxError('sandbox_native_process_changed')
        current()
        result = {'version': 'c23-native-nofile-readback-v2',
            'native_nofile_limit': 4096, 'analysis_nofile_limit': 256,
            'observed_before_start': True, 'inventory': inventory['groups'], 'roles': roles,
            'auxiliary_processes': auxiliary}
        if len(canonical_json(result).encode()) > MAX_ENFORCEMENT_BYTES:
            raise SandboxError('sandbox_host_limit')
        return result

    def _readback(self, envelope, document, lease, argv, *, deadline, side, cgroup_identity,
                  watchdog=None):
        outer, host, sandbox = self._paths(envelope.job_id)
        expected = document['requirements']['readback_before_start']
        readback = {}
        for group in (outer, sandbox):
            values = {}
            for name, value in expected.items():
                observed = ' '.join(_read(group / name).decode('ascii').split())
                if observed != str(value):
                    raise SandboxError('sandbox_resource_enforcement')
                values[name] = observed
            readback[group.name] = values
        code, raw, _ = self._command(argv + ['state', envelope.job_id], host,
            deadline=deadline, lease=lease, side=side, watchdog=watchdog)
        state = json.loads(raw)
        if (code != 0 or state.get('id') != envelope.job_id or state.get('status') != 'created'
                or type(state.get('pid')) is not int or not 1 < state['pid'] < 2**31
                or Path(state.get('bundle', '')) != self.worker_root / envelope.job_id):
            raise SandboxError('sandbox_created_identity')
        membership = _read(f'/proc/{state["pid"]}/cgroup').decode('ascii').splitlines()
        expected_path = f'/ocean-c23/{envelope.job_id}/'
        if len(membership) != 1 or not membership[0].startswith('0::' + expected_path):
            raise SandboxError('sandbox_host_subtree_identity')
        readback['native_processes'] = self._native_nofile_readback(envelope.job_id, state['pid'],
            document['requirements'], cgroup_identity=cgroup_identity, lease=lease,
            deadline=deadline, watchdog=watchdog)
        if len(canonical_json({'readback': readback}).encode()) > MAX_ENFORCEMENT_BYTES:
            raise SandboxError('sandbox_host_limit')
        return readback

    @staticmethod
    def _admit(lease, admission, envelope):
        lease.require_current()
        current = admission(envelope)
        if type(current) is not str or current != envelope.envelope_sha256:
            raise SandboxError('sandbox_current_admission')
        lease.require_current()

    def _empty(self, outer, identity, *, deadline, lease):
        while True:
            lease.require_current()
            info = outer.stat()
            if (info.st_dev, info.st_ino) != identity or outer != outer.resolve(strict=True):
                raise SandboxError('sandbox_cgroup_identity')
            fields = {}
            for line in _read(outer / 'cgroup.events').decode('ascii').splitlines():
                key, value = line.split()
                if key in fields:
                    raise SandboxError('sandbox_cgroup_integrity')
                fields[key] = value
            if fields.get('populated') == '0':
                return
            if fields.get('populated') != '1' or self.clock() >= deadline:
                raise SandboxError('sandbox_termination_uncertain')
            time.sleep(0.01)

    def _cleanup(self, envelope, argv, identity, lease, *, side=None):
        outer, host, _ = self._paths(envelope.job_id)
        lease.require_current()
        if side is not None:
            side.cancel_launch()
        info = outer.stat()
        if (info.st_dev, info.st_ino) != identity:
            raise SandboxError('sandbox_cgroup_identity')
        # Stop all untrusted execution immediately. Only trusted delete cleanup
        # may subsequently re-enter this group; it is killed/proved empty again.
        _write_control(outer / 'cgroup.kill', b'1\n')
        self._empty(outer, identity, deadline=self.clock() + 2, lease=lease)
        acknowledged = False
        try:
            code, _, _ = self._command(argv + ['delete', '--force', envelope.job_id], host,
                deadline=self.clock() + 2, lease=lease, side=side)
            acknowledged = code == 0
        finally:
            lease.require_current()
            _write_control(outer / 'cgroup.kill', b'1\n')
            self._empty(outer, identity, deadline=self.clock() + 2, lease=lease)
        if side is not None:
            limit = self.clock() + 1
            while not side.eof:
                side.drain()
                if self.clock() >= limit:
                    raise SandboxError('sandbox_runtime_pipe_uncertain')
                time.sleep(0.01)
        return {'host_boot_id': self.journal.host_boot_id, 'cgroup_path': f'/ocean-c23/{envelope.job_id}',
                'cgroup_device': identity[0], 'cgroup_inode': identity[1],
                'populated': 0, 'whole_host_subtree_empty': True,
                'runtime_delete_acknowledged': acknowledged}

    def _retain_outputs(self, job, envelope, decoded):
        retained = job / 'retained'
        retained.mkdir(mode=0o700)
        _sync_directory(job)
        files, logs = retained / 'files', retained / 'logs'
        files.mkdir(mode=0o700)
        logs.mkdir(mode=0o700)
        _sync_directory(retained)
        for name, raw in decoded['files'].items():
            _put(files / name, raw)
        for name, raw in decoded['logs'].items():
            _put(logs / name, raw)
        files.chmod(0o500)
        logs.chmod(0o500)
        _sync_directory(files)
        _sync_directory(logs)
        outputs = validate_outputs(files, expected_outputs=envelope.proposal['expected_outputs'],
            max_output_bytes=envelope.resources['max_output_bytes'], logs=decoded['logs'])
        _put(retained / 'manifest.json', outputs.manifest_bytes)
        retained.chmod(0o500)
        _sync_directory(retained)
        return outputs

    def _retain_failure_logs(self, job, decoded):
        retained = job / 'retained'
        retained.mkdir(mode=0o700)
        _sync_directory(job)
        logs = retained / 'logs'
        logs.mkdir(mode=0o700)
        _sync_directory(retained)
        for name, raw in decoded['logs'].items():
            _put(logs / name, raw)
        logs.chmod(0o500)
        _sync_directory(logs)
        _put(retained / 'manifest.json', canonical_json({'version': VERSION,
            'logs': {name: {'sha256': _sha(raw), 'size_bytes': len(raw)}
                     for name, raw in decoded['logs'].items()}, 'outputs': []}).encode())
        retained.chmod(0o500)
        _sync_directory(retained)

    def _replay_outputs(self, job, envelope, record):
        if record.get('state') != 'completed':
            return None
        retained = job / 'retained'
        logs = {name: _read(retained / 'logs' / name, 1024**2) for name in ('stdout', 'stderr')}
        outputs = validate_outputs(retained / 'files', expected_outputs=envelope.proposal['expected_outputs'],
            max_output_bytes=envelope.resources['max_output_bytes'], logs=logs)
        if (_sha(outputs.manifest_bytes) != record.get('outputs_manifest_sha256')
                or _read(retained / 'manifest.json', 1024**2) != outputs.manifest_bytes):
            raise SandboxError('sandbox_retention_integrity')
        return outputs

    def _record(self, envelope, profile, runtime_sha, *, state, reason, attempted=False,
                started=False, proof=None, outputs=None, frame=None, replayed=False,
                init=None, waited_exit_status=None, logs=None):
        return {'version': VERSION, 'job_id': envelope.job_id,
            'envelope_sha256': envelope.envelope_sha256, 'profile_sha256': profile.profile_sha256,
            'runtime_sha256': runtime_sha, 'state': state, 'reason': reason,
            'adapter_source_sha256': self._helper_sha256,
            'image_digest': envelope.environment['image_digest'],
            'trusted_init_sha256': profile.document['trusted_init']['sha256'],
            'approved_hashes': envelope.metadata['hashes'],
            'declared_seeds': envelope.proposal['seeds'],
            'start_attempted': attempted, 'execution_started': started,
            'analysis_exit_code': init['analysis_exit_code'] if init else None,
            'host_runtime_exit_status': waited_exit_status,
            'simulation': False, 'dispatch_eligible': False, 'reservation_released': False,
            'scientific_approval': 'not_independently_verified',
            'runtime_acceptance_verified': False, 'termination_proof': proof,
            'private_diagnostics_directory': 'diagnostics',
            'outputs_manifest_sha256': _sha(outputs.manifest_bytes) if outputs else None,
            'retained_logs': {name: {'sha256': _sha(raw), 'size_bytes': len(raw)}
                              for name, raw in (logs or {}).items()},
            'total_output_bytes': outputs.total_bytes if outputs else 0,
            'frame_sha256': _sha(frame) if frame else None, 'replayed': replayed}

    def run(self, envelope, profile, *, admission, cancelled=lambda: False):
        # This guard precedes journal mutation and every executable path.
        _require_linux_host(self.journal, self.cgroup_root)
        if type(envelope) is not VerifiedEnvelope or type(profile) is not PreparedExecutionProfile:
            raise SandboxError('sandbox_runtime_identity')
        if not callable(admission) or not callable(cancelled):
            raise SandboxError('sandbox_current_admission')
        # Pure host/image/profile checks happen before creating a durable job.
        # A missing mount/material must not consume an execution identity.
        job, document, runtime_sha = self._preflight(envelope, profile)
        with self.journal.claim(envelope.job_id, envelope.envelope_sha256) as lease:
            snapshot = lease.snapshot()
            if snapshot.terminal:
                record = snapshot.result['record']
                if (record.get('version') != VERSION or record.get('job_id') != envelope.job_id
                        or record.get('envelope_sha256') != envelope.envelope_sha256
                        or record.get('profile_sha256') != profile.profile_sha256
                        or record.get('runtime_sha256') != runtime_sha):
                    raise SandboxError('sandbox_result_identity')
                self._admit(lease, admission, envelope)
                outputs = self._replay_outputs(job, envelope, record)
                self._admit(lease, admission, envelope)
                return LinuxExecutionResult({**record, 'replayed': True}, outputs)
            argv = [str(self.runtime_directory / 'runsc'), *profile.runtime_args]
            outer, host, _ = self._paths(envelope.job_id)
            state_root = self.worker_root / ('runsc-state-' + envelope.job_id)
            if snapshot.reconciliation_required:
                # Reconciliation can stop only a previously bound exact group.
                # It never reconstructs or replays a launch intent.
                intents = [event.payload for event in snapshot.events if event.kind == 'create_intent']
                identity = tuple(intents[-1]['cgroup_identity']) if intents and 'cgroup_identity' in intents[-1] else None
                if (identity is None or intents[-1].get('profile_sha256') != profile.profile_sha256
                        or not outer.exists()):
                    return LinuxExecutionResult(self._record(envelope, profile, runtime_sha,
                        state='uncertain', reason='reconciliation_required', started=None))
                proof = self._cleanup(envelope, argv, identity, lease)
                self._admit(lease, admission, envelope)
                record = self._record(envelope, profile, runtime_sha, state='interrupted',
                    reason='reconciled_without_reexecution', attempted=True, started=None, proof=proof)
                if not proof['runtime_delete_acknowledged']:
                    record['state'] = 'uncertain'
                else:
                    lease.finish(record)
                return LinuxExecutionResult(record)
            if outer.exists() or state_root.exists() or state_root.is_symlink():
                return LinuxExecutionResult(self._record(envelope, profile, runtime_sha,
                    state='uncertain', reason='unowned_existing_runtime', started=None))
            identity = None
            capture = watchdog = None
            proof = None
            attempted = started = False
            journal_healthy = True
            create_diagnosed = False
            create_argv = argv + ['create', '--bundle=' + str(job), envelope.job_id]
            try:
                lease.append('prepared', {'profile_sha256': profile.profile_sha256,
                    'runtime_sha256': runtime_sha})
                _put(job / 'config.json', (canonical_json(profile.config) + '\n').encode(), reuse=True)
                state_root.mkdir(mode=0o700)
                _sync_directory(self.worker_root)
                lease.append('cgroup_intent', {'path': f'/ocean-c23/{envelope.job_id}'})
                identity = self._prepare_cgroups(envelope.job_id, document['requirements'])
                lease.append('create_intent', {'profile_sha256': profile.profile_sha256,
                    'cgroup_identity': list(identity)})
                deadline = self.clock() + envelope.resources['wall_seconds']
                watchdog = _arm_watchdog(outer, deadline)
                lease.append('watchdog_armed', {'pid': watchdog.pid,
                    'host_boot_id': self.journal.host_boot_id, 'deadline_monotonic': deadline})
                frame_limit = len(MAGIC) + 40 + max_payload_bytes(envelope.resources['max_output_bytes'])
                capture = self._spawn(create_argv, host, deadline=deadline, frame_limit=frame_limit)
                if self._wait(capture, deadline=deadline, lease=lease,
                              cancelled=cancelled, require_eof=False, watchdog=watchdog) != 0:
                    raise SandboxError('sandbox_create_failed')
                readback = self._readback(envelope, document, lease, argv,
                    deadline=deadline, side=capture, cgroup_identity=identity, watchdog=watchdog)
                lease.append('enforcement_verified', {'readback': readback})
                self._admit(lease, admission, envelope)
                lease.append('start_intent', {'envelope_sha256': envelope.envelope_sha256})
                attempted = True
                code, _, _ = self._command(argv + ['start', envelope.job_id], host,
                    deadline=deadline, lease=lease, side=capture, cancelled=cancelled, watchdog=watchdog)
                if code != 0:
                    raise SandboxError('sandbox_start_uncertain')
                started = True
                lease.append('started', {})
                code, raw, _ = self._command(argv + ['wait', envelope.job_id], host,
                    deadline=deadline, lease=lease, side=capture, cancelled=cancelled, watchdog=watchdog)
                waited = json.loads(raw)
                if (code != 0 or type(waited) is not dict or set(waited) != {'id', 'exitStatus'}
                        or waited['id'] != envelope.job_id or type(waited['exitStatus']) is not int
                        or not 0 <= waited['exitStatus'] <= 255):
                    raise SandboxError('sandbox_wait_uncertain')
                lease.append('cleanup_intent', {})
                proof = self._cleanup(envelope, argv, identity, lease, side=capture)
                self._diagnose(create_argv, capture, lease)
                create_diagnosed = True
                if not proof['runtime_delete_acknowledged']:
                    raise SandboxError('sandbox_delete_uncertain')
                frame = bytes(capture.stdout)
                init, decoded = decode_frame(frame, policy=document['trusted_init']['policy'])
                if init['writers_reaped'] is not True or (init['outcome'] == 'completed' and waited['exitStatus'] != 0):
                    raise SandboxError('sandbox_guest_writers_uncertain')
                lease.append('termination_verified', {'proof': proof, 'frame_sha256': _sha(frame)})
                if init['outcome'] == 'completed':
                    outputs = self._retain_outputs(job, envelope, decoded)
                else:
                    self._retain_failure_logs(job, decoded)
                    outputs = None
                self._admit(lease, admission, envelope)
                record = self._record(envelope, profile, runtime_sha, state=init['outcome'],
                    reason=init['reason'], attempted=True, started=True, proof=proof, outputs=outputs,
                    frame=frame, init=init, waited_exit_status=waited['exitStatus'], logs=decoded['logs'])
                lease.finish(record)
                return LinuxExecutionResult(record, outputs)
            except (SandboxError, InitError, OSError, ValueError, TypeError, KeyError, subprocess.SubprocessError) as error:
                reason = error.reason if isinstance(error, SandboxError) else 'sandbox_runtime_uncertain'
                if isinstance(error, SandboxError) and ('journal' in reason or 'fence' in reason or 'lease' in reason):
                    journal_healthy = False
                if identity is not None and proof is None:
                    try:
                        lease.require_current()
                        proof = self._cleanup(envelope, argv, identity, lease, side=capture)
                    except (SandboxError, OSError, ValueError, subprocess.SubprocessError):
                        proof = None
                if capture is not None and not create_diagnosed:
                    try:
                        self._diagnose(create_argv, capture, lease)
                    except (SandboxError, OSError, ValueError):
                        journal_healthy = False
                record = self._record(envelope, profile, runtime_sha, state='uncertain', reason=reason,
                    attempted=attempted, started=started if started or not attempted else None, proof=proof)
                # Even a known timeout/cancellation remains uncertain if durable
                # intent, whole-group proof, delete acknowledgement or current
                # publication admission is missing. No partial outputs escape.
                if (journal_healthy and proof is not None and proof['runtime_delete_acknowledged']
                        and reason in {'sandbox_wall_limit', 'sandbox_cancelled'}):
                    try:
                        self._admit(lease, admission, envelope)
                        record['state'] = 'timed_out' if reason == 'sandbox_wall_limit' else 'cancelled'
                        lease.finish(record)
                    except (SandboxError, OSError, ValueError):
                        record['state'] = 'uncertain'
                return LinuxExecutionResult(record)
            finally:
                if capture is not None:
                    capture.close()
                if watchdog is not None:
                    watchdog.stop(proven=proof is not None)
