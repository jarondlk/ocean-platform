"""Explicit sealed-init profile amendment; rendering never grants execution.

The original C23 configuration-only renderer remains unchanged. This additive
version changes the trusted guest control process, not the non-root analysis.
Only a real, separately accepted adapter may consume these preparations.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import stat

from orchestration.experiment_sandbox.contracts import SandboxError, VerifiedEnvelope
from orchestration.experiment_sandbox.files import validate_expected_outputs
from orchestration.experiment_sandbox.profile import (
    ImagePreparation, RuntimePreparation, rootfs_inventory_sha256,
)
from sandbox.experiment.trusted_init import (
    INIT_CAP_NAMES, OUTPUT_INODES, SCRATCH_INODES, START_CAP_NAMES,
    VERSION as INIT_VERSION, validate_policy,
)
from schema.context_catalogue import canonical_json
from schema.research_experiments import EnvironmentDescriptor, ExperimentResources, content_sha256

VERSION = 'c23-oci-execution-preparation-v4'
GUEST_INIT_PATH = '/opt/c23/trusted_init.py'
# One rule per bit is essential: matching the combined mask would deny only
# calls containing every namespace bit simultaneously.
CLONE_NAMESPACE_BITS = (0x00020000, 0x02000000, 0x04000000, 0x08000000,
                        0x10000000, 0x20000000, 0x40000000)


def _guest_syscall_policy(architecture):
    return {
        'defaultAction': 'SCMP_ACT_ALLOW',
        'architectures': ['SCMP_ARCH_X86_64' if architecture == 'amd64' else 'SCMP_ARCH_AARCH64'],
        'syscalls': [
            {'names': ['unshare', 'setns'], 'action': 'SCMP_ACT_ERRNO', 'errnoRet': 1, 'args': []},
            # glibc falls back to clone for threads on ENOSYS. It may not do so
            # for EPERM; argument pointers cannot be inspected by classic BPF.
            {'names': ['clone3'], 'action': 'SCMP_ACT_ERRNO', 'errnoRet': 38, 'args': []},
            *[{'names': ['clone'], 'action': 'SCMP_ACT_ERRNO', 'errnoRet': 1,
               'args': [{'index': 0, 'value': bit, 'valueTwo': bit, 'op': 'SCMP_CMP_MASKED_EQ'}]}
              for bit in CLONE_NAMESPACE_BITS],
        ],
    }


def _directory(value, *, owner=None, mode=None):
    path = Path(value)
    if not path.is_absolute() or path != path.resolve(strict=True):
        raise ValueError
    info = path.lstat()
    if (not stat.S_ISDIR(info.st_mode)
            or owner is not None and (info.st_uid, info.st_gid) != owner
            or mode is not None and stat.S_IMODE(info.st_mode) != mode):
        raise ValueError
    return path


def _base_document(envelope, *, job_root, image_receipt, runtime_manifest):
    """Render without v1's supervisor-owned input-directory assumption.

    V2 has a private supervisor-owned job root and an application-owned sealed
    input directory. A root supervisor may inspect these bytes, but the guest
    application must be able to traverse its own read-only bind mount.
    """
    if type(envelope) is not VerifiedEnvelope:
        raise ValueError
    image = ImagePreparation.model_validate(image_receipt)
    runtime = RuntimePreparation.model_validate(runtime_manifest)
    environment = EnvironmentDescriptor.model_validate(envelope.environment)
    resources = ExperimentResources.model_validate(envelope.resources)
    if (resources.memory_bytes % 4096 or resources.max_output_bytes < 8192
            or environment.kind != 'linux-gvisor' or environment.test_only
            or image.image_digest != environment.image_digest
            or image.lockfile_sha256 != environment.lockfile_sha256
            or image.python_version != environment.python_version
            or image.packages != environment.packages or runtime.architecture != image.architecture):
        raise ValueError
    job = _directory(job_root)
    if job.name != envelope.job_id or job.stat().st_uid != os.geteuid() or job.stat().st_mode & 0o077:
        raise ValueError
    inputs = _directory(job / 'inputs', owner=(runtime.input_host_uid, runtime.input_host_gid), mode=0o500)
    expected = {**envelope.files, 'analysis.py': envelope.code, 'manifest.json': envelope.manifest_bytes}
    if len(expected) != len(envelope.files) + 2 or envelope.input_size_bytes > resources.max_input_bytes:
        raise ValueError
    descriptor = os.open(inputs, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        names = []
        with os.scandir(descriptor) as iterator:
            for entry in iterator:
                if len(names) >= len(expected):
                    raise ValueError
                names.append(entry.name)
        if set(names) != set(expected):
            raise ValueError
        for name, raw in expected.items():
            if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,127}', name):
                raise ValueError
            before = os.stat(name, dir_fd=descriptor, follow_symlinks=False)
            if (not stat.S_ISREG(before.st_mode) or before.st_nlink != 1
                    or stat.S_IMODE(before.st_mode) != 0o400
                    or (before.st_uid, before.st_gid) != (runtime.input_host_uid, runtime.input_host_gid)
                    or before.st_size != len(raw)):
                raise ValueError
            opened = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC, dir_fd=descriptor)
            try:
                def stamp(info):
                    return (info.st_dev, info.st_ino, info.st_mode, info.st_uid, info.st_gid,
                            info.st_size, info.st_nlink, info.st_mtime_ns, info.st_ctime_ns)
                if stamp(before) != stamp(os.fstat(opened)):
                    raise ValueError
                offset = 0
                while offset < len(raw):
                    chunk = os.read(opened, min(1024 * 1024, len(raw) - offset))
                    if not chunk or chunk != raw[offset:offset + len(chunk)]:
                        raise ValueError
                    offset += len(chunk)
                if os.read(opened, 1) or stamp(before) != stamp(os.fstat(opened)):
                    raise ValueError
                if stamp(before) != stamp(os.stat(name, dir_fd=descriptor, follow_symlinks=False)):
                    raise ValueError
            finally:
                os.close(opened)
    finally:
        os.close(descriptor)
    rootfs = _directory(job / 'rootfs')
    if rootfs_inventory_sha256(rootfs) != image.rootfs_inventory_sha256:
        raise ValueError
    state_root = job.parent / ('runsc-state-' + envelope.job_id)
    if state_root.exists() or state_root.is_symlink():
        _directory(state_root)
        if state_root.stat().st_uid != os.geteuid() or state_root.stat().st_mode & 0o077:
            raise ValueError
    budget = resources.max_output_bytes
    log_each = min(1024 * 1024, budget // 8)
    manifest_budget = min(1024 * 1024, budget // 8)
    file_budget = ((budget - 2 * log_each - manifest_budget) // 4096) * 4096
    scratch = (min(256 * 1024**2, resources.memory_bytes // 4) // 4096) * 4096
    config = {
        'ociVersion': '1.1.0', 'hostname': envelope.job_id,
        'root': {'path': 'rootfs', 'readonly': True},
        'process': {'terminal': False, 'cwd': '/outputs',
            'args': ['/usr/local/bin/python3', '-I', '-B', '/inputs/analysis.py'],
            'user': {'uid': 65532, 'gid': 65532, 'additionalGids': []},
            'env': ['PATH=/usr/local/bin', 'HOME=/scratch', 'TMPDIR=/scratch',
                'MPLCONFIGDIR=/scratch/matplotlib', 'MPLBACKEND=Agg', 'LANG=C.UTF-8', 'TZ=UTC',
                f'OMP_NUM_THREADS={resources.cpus}', f'OPENBLAS_NUM_THREADS={resources.cpus}'],
            'noNewPrivileges': True,
            'capabilities': {key: [] for key in ('bounding', 'effective', 'inheritable', 'permitted', 'ambient')},
            'rlimits': [{'type': key, 'soft': value, 'hard': value} for key, value in (
                ('RLIMIT_CORE', 0), ('RLIMIT_NOFILE', 256), ('RLIMIT_NPROC', 128), ('RLIMIT_FSIZE', file_budget))]},
        'mounts': [
            {'destination': '/inputs', 'type': 'bind', 'source': str(inputs),
             'options': ['rbind', 'ro', 'nosuid', 'nodev', 'noexec', 'private']},
            # Explicit /tmp suppresses runsc's automatic writable1777 tmpfs.
            # OCI size/ro are implemented; maskedPaths is not our authority.
            {'destination': '/tmp', 'type': 'tmpfs', 'source': 'tmpfs',
             'options': ['ro', 'nosuid', 'nodev', 'noexec', 'size=4096', 'uid=0', 'gid=0', 'mode=0555']},
            {'destination': '/dev/shm', 'type': 'tmpfs', 'source': 'tmpfs',
             'options': ['ro', 'nosuid', 'nodev', 'noexec', 'size=4096', 'uid=0', 'gid=0', 'mode=0555']},
            {'destination': '/proc', 'type': 'proc', 'source': 'proc',
             'options': ['ro', 'nosuid', 'nodev', 'noexec']}],
        'linux': {'namespaces': [{'type': key} for key in ('pid', 'mount', 'ipc', 'uts', 'network', 'user', 'cgroup')],
            'uidMappings': [{'containerID': 65532, 'hostID': runtime.input_host_uid, 'size': 1}],
            'gidMappings': [{'containerID': 65532, 'hostID': runtime.input_host_gid, 'size': 1}],
            'rootfsPropagation': 'private', 'resources': {
                'cpu': {'period': 100000, 'quota': resources.cpus * 100000},
                'memory': {'limit': resources.memory_bytes, 'swap': resources.memory_bytes},
                'pids': {'limit': 128}, 'devices': [{'allow': False, 'access': 'rwm'}]},
            'maskedPaths': ['/proc/kcore', '/proc/keys', '/proc/timer_list', '/proc/sched_debug'],
            'readonlyPaths': ['/proc/sys', '/proc/sysrq-trigger', '/proc/irq', '/proc/bus']},
    }
    args = ['--root=' + str(state_root), '--platform=systrap', '--rootless=false', '--network=none',
            '--gofer-network-namespace=new', '--directfs=false', '--overlay2=none', '--host-uds=none',
            '--host-fifo=none', '--character-device-policy=emulated-only', '--net-raw=false',
            '--ignore-cgroups=false', '--allow-flag-override=false',
            '--sidecar-release-enforcement-policy=ALWAYS', '--fdlimit=256', '--gvisor-marker-file=true',
            '--oci-seccomp=true', '--debug=false',
            '--debug-log=/dev/stderr', '--panic-log=/dev/stderr']
    return {'evidence_class': 'configuration-only', 'dispatch_eligible': False,
        'job_id': envelope.job_id, 'envelope_sha256': envelope.envelope_sha256,
        'environment_sha256': content_sha256(envelope.environment), 'proposal_hashes': envelope.metadata['hashes'],
        'declared_seeds': envelope.proposal['seeds'], 'approved_resources': envelope.resources,
        'input_size_bytes': envelope.input_size_bytes, 'image_preparation': image.model_dump(mode='json'),
        'runtime_preparation': runtime.model_dump(mode='json'), 'config': config, 'runtime_args': args,
        'requirements': {'actual_linux_gvisor_verified': False, 'production_dispatch_built': False,
            'external_wall_watchdog_seconds': resources.wall_seconds, 'max_input_bytes': resources.max_input_bytes,
            'aggregate_output_and_logs_bytes': budget, 'output_file_budget_bytes': file_budget,
            'stdout_max_bytes': log_each, 'stderr_max_bytes': log_each,
            'output_manifest_max_bytes': manifest_budget, 'scratch_max_bytes': scratch,
            'readback_before_start': {'cpu.max': f'{resources.cpus * 100000} 100000',
                'memory.max': resources.memory_bytes, 'memory.swap.max': 0, 'pids.max': 128},
            'unverified': [
                'Pinned installed runtime and supported flags, image materialization and immutable rootfs',
                'Actual guest UID mapping, staged input readability and ownership under the pinned gofer',
                'Measured CPU/memory/swap/guest and host process/output/scratch/inode limits',
                'Network/metadata/host/socket/credential/package-manager containment probes',
                'Outer-cgroup descendant termination, durable recovery/release and numerical fixtures',
            ]}}


@dataclass(frozen=True, init=False)
class PreparedExecutionProfile:
    _json: str
    profile_sha256: str

    def __init__(self, *args, **kwargs):
        raise TypeError('Use render_execution_profile')

    @property
    def document(self):
        return json.loads(self._json)

    @property
    def config(self):
        return self.document['config']

    @property
    def runtime_args(self):
        return tuple(self.document['runtime_args'])

    @property
    def requirements(self):
        return self.document['requirements']

    @property
    def dispatch_eligible(self):
        return False


def _init_bytes(rootfs, expected_sha):
    if type(expected_sha) is not str or not re.fullmatch(r'[a-f0-9]{64}', expected_sha):
        raise ValueError
    path = Path(rootfs) / GUEST_INIT_PATH.lstrip('/')
    if path != path.resolve(strict=True):
        raise ValueError
    before = path.lstat()
    if (not stat.S_ISREG(before.st_mode) or before.st_nlink != 1
            or before.st_mode & 0o222 or not 1 <= before.st_size <= 65536):
        raise ValueError
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC)
    try:
        raw = os.read(descriptor, 65537)
        def stamp(info):
            return (info.st_dev, info.st_ino, info.st_mode, info.st_nlink, info.st_size,
                    info.st_uid, info.st_gid, info.st_mtime_ns, info.st_ctime_ns)
        if (len(raw) != before.st_size or stamp(before) != stamp(os.fstat(descriptor))
                or stamp(before) != stamp(path.lstat()) or hashlib.sha256(raw).hexdigest() != expected_sha):
            raise ValueError
    finally:
        os.close(descriptor)


def render_execution_profile(envelope, *, job_root, image_receipt, runtime_manifest,
                             control_host_uid, control_host_gid, trusted_init_sha256):
    """Prepare trusted PID1 and untrusted child separation without launching.

    Root inside this guest is a sealed control process mapped to a distinct
    non-root host owner. A transient sixth capability mounts only two fixed
    quota-enforced tmpfs filesystems. It is removed before any analysis fork;
    the original five capabilities then drop privileges, clean up and extract.
    """
    try:
        document = _base_document(envelope, job_root=job_root, image_receipt=image_receipt,
                                  runtime_manifest=runtime_manifest)
        runtime = document['runtime_preparation']
        for value, previous in ((control_host_uid, runtime['input_host_uid']),
                                (control_host_gid, runtime['input_host_gid'])):
            if type(value) is not int or not 1 <= value <= 2**32 - 2 or value == previous:
                raise ValueError
        _init_bytes(Path(job_root) / 'rootfs', trusted_init_sha256)
        expected = validate_expected_outputs(envelope.proposal['expected_outputs'])
        requirements = document['requirements']
        policy = validate_policy({
            'version': INIT_VERSION, 'job_id': envelope.job_id,
            'envelope_sha256': envelope.envelope_sha256,
            'expected_names': sorted(expected), 'wall_seconds': envelope.resources['wall_seconds'],
            'max_output_bytes': envelope.resources['max_output_bytes'],
            'output_file_budget_bytes': requirements['output_file_budget_bytes'],
            'stdout_max_bytes': requirements['stdout_max_bytes'],
            'stderr_max_bytes': requirements['stderr_max_bytes'],
            'scratch_max_bytes': requirements['scratch_max_bytes'],
        })
        config = document['config']
        config['process']['user'] = {'uid': 0, 'gid': 0, 'additionalGids': []}
        config['process']['args'] = ['/usr/local/bin/python3', '-I', '-B', GUEST_INIT_PATH,
                                     '--policy', canonical_json(policy)]
        config['process']['cwd'] = '/'
        config['process']['capabilities'] = {
            'bounding': list(START_CAP_NAMES), 'effective': list(START_CAP_NAMES),
            'permitted': list(START_CAP_NAMES), 'inheritable': [], 'ambient': [],
        }
        config['linux']['uidMappings'].insert(0, {'containerID': 0, 'hostID': control_host_uid, 'size': 1})
        config['linux']['gidMappings'].insert(0, {'containerID': 0, 'hostID': control_host_gid, 'size': 1})
        outer_cgroup = '/ocean-c23/' + envelope.job_id
        config['linux']['cgroupsPath'] = outer_cgroup + '/sandbox'
        config['linux']['seccomp'] = _guest_syscall_policy(runtime['architecture'])
        requirements['outer_cgroup_path'] = outer_cgroup
        requirements['host_control_cgroup_path'] = outer_cgroup + '/host'
        requirements['runtime_cgroup_path'] = outer_cgroup + '/sandbox'
        document['version'] = VERSION
        document['supersedes_configuration_only_profile_version'] = 'c23-oci-preparation-v1'
        document['supersedes_execution_profile_version'] = 'c23-oci-execution-preparation-v3'
        document['trusted_init'] = {
            'version': INIT_VERSION, 'path': GUEST_INIT_PATH, 'sha256': trusted_init_sha256,
            'control_guest_uid': 0, 'analysis_guest_uid': 65532,
            'control_host_uid': control_host_uid, 'control_host_gid': control_host_gid,
            'policy': policy,
            'initial_capabilities': list(START_CAP_NAMES),
            'post_mount_capabilities': list(INIT_CAP_NAMES),
        }
        requirements['trusted_guest_mounts'] = [
            {'path': '/outputs', 'max_bytes': policy['output_file_budget_bytes'], 'max_inodes': OUTPUT_INODES},
            {'path': '/scratch', 'max_bytes': policy['scratch_max_bytes'], 'max_inodes': SCRATCH_INODES},
        ]
        requirements['readonly_guest_temporary_paths'] = ['/tmp', '/dev/shm', '/run', '/var/tmp']
        requirements['guest_syscall_guard'] = {
            'evidence_class': 'configuration-only', 'actual_adversarial_verified': False,
            'oci_seccomp_explicitly_enabled': True,
            'clone_namespace_bits': list(CLONE_NAMESPACE_BITS), 'clone3_errno': 38,
            'mount_syscall_remains_allowed_for_trusted_init': True,
        }
        requirements['lifecycle'] = [
            'create', 'verify-enforcement', 'fresh-admission', 'start-sealed-init',
            'fixed-guest-tmpfs-mounts-and-quota-readback', 'drop-current-and-bounding-SYS_ADMIN',
            'analysis-child-without-privileges', 'wait-main-child', 'kill-and-reap-to-ECHILD',
            'bounded-nofollow-output-extraction', 'bounded-control-frame',
            'destroy-and-prove-host-subtree-empty', 'fresh-admission-and-retain',
        ]
        requirements['unverified'].extend([
            'Sealed guest PID1 gVisor marker, minimal caps, UID drop, empty child caps/groups and proc-FD isolation',
            'Actual descendant cleanup to ECHILD before output extraction, including daemon/namespace/fork races',
            'Unforgeable separate child pipes, bounded host frame decoder and outer watchdog within approved wall',
            'No additional exec process may be introduced into this single-init sandbox',
            'Actual /tmp,/dev/shm readonly views and /run,/var/tmp readonly-root write denials',
            'Actual guest OCI seccomp namespace/clone3 denial, inheritance, direct child mount denial and ordinary fork/thread compatibility',
        ])
        value = object.__new__(PreparedExecutionProfile)
        object.__setattr__(value, '_json', canonical_json(document))
        object.__setattr__(value, 'profile_sha256', content_sha256(document))
        return value
    except SandboxError:
        raise
    except (OSError, ValueError, TypeError, KeyError, AttributeError, UnicodeError, RecursionError):
        raise SandboxError('sandbox_execution_profile_unavailable') from None
