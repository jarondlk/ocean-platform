"""C23 fixed OCI preparation, never runtime admission or process execution.

All supplied identities are trusted operator preparation inputs. Their structural
agreement is checked here; none substitutes for signed/materialized image
provenance, a Linux preflight, or the real containment acceptance suite.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import posixpath
import re
import stat
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from orchestration.experiment_sandbox.contracts import SandboxError, VerifiedEnvelope
from schema.context_catalogue import canonical_json
from schema.research_experiments import EnvironmentDescriptor, ExperimentResources, content_sha256

PROFILE_VERSION = 'c23-oci-preparation-v1'
APP_UID = APP_GID = 65532
MAX_HOST_PIDS = 128
MAX_FDS = 256
MAX_ROOTFS_ENTRIES = 100000
MAX_ROOTFS_BYTES = 8 * 1024**3
SHA = Annotated[str, StringConstraints(pattern=r'^[a-f0-9]{64}$')]
DIGEST = Annotated[str, StringConstraints(pattern=r'^sha256:[a-f0-9]{64}$')]
PATCH_VERSION = Annotated[str, StringConstraints(pattern=r'^3\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)$')]
_NAME = re.compile(r'^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$')


class _Exact(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True, frozen=True)


class ImagePreparation(_Exact):
    version: Literal['c23-image-preparation-v1']
    evidence_class: Literal['configuration-only']
    image_digest: DIGEST
    base_image_digest: DIGEST
    architecture: Literal['amd64', 'arm64']
    python_version: PATCH_VERSION
    lockfile_sha256: SHA
    packages: dict[str, str]
    oci_manifest_sha256: SHA
    oci_config_sha256: SHA
    layer_sha256: Annotated[list[SHA], Field(min_length=1, max_length=256)]
    rootfs_inventory_sha256: SHA

    @model_validator(mode='after')
    def explicit_materialization(self):
        if self.image_digest != 'sha256:' + self.oci_manifest_sha256:
            raise ValueError('A platform image manifest digest is required')
        if not 6 <= len(self.packages) <= 256:
            raise ValueError('A bounded complete package manifest is required')
        for name in self.packages:
            normalized = re.sub(r'[-_.]+', '-', name).lower()
            if (not _NAME.fullmatch(name) or normalized in {
                    'pip', 'setuptools', 'wheel', 'fastapi', 'uvicorn', 'sqlalchemy',
                    'psycopg', 'psycopg2', 'psycopg2-binary', 'asyncpg', 'pg8000',
                    'openai', 'boto3', 'botocore', 'google-auth', 'google-api-core'}
                    or normalized.startswith(('google-cloud-', 'azure-'))):
                raise ValueError('Application, installer and cloud/database packages are excluded')
        if len({re.sub(r'[-_.]+', '-', n).lower() for n in self.packages}) != len(self.packages):
            raise ValueError('Package aliases cannot duplicate identities')
        return self


class RuntimePreparation(_Exact):
    version: Literal['c23-runtime-preparation-v1']
    evidence_class: Literal['configuration-only']
    release: Annotated[str, StringConstraints(pattern=r'^release-[0-9]{8}(?:\.[0-9]+)?$')]
    architecture: Literal['amd64', 'arm64']
    files: dict[str, SHA]
    # These are explicit non-root owner mappings, not invented host subuid ranges.
    # A real host must separately demonstrate namespace/readability semantics.
    input_host_uid: Annotated[int, Field(strict=True, ge=1, le=4294967294)]
    input_host_gid: Annotated[int, Field(strict=True, ge=1, le=4294967294)]

    @model_validator(mode='after')
    def full_release_manifest(self):
        if not 3 <= len(self.files) <= 128 or not {'runsc', 'containerd-shim-runsc-v1'} <= self.files.keys():
            raise ValueError('The complete release manifest including sidecars is required')
        sidecars = 0
        for name in self.files:
            if name in {'runsc', 'containerd-shim-runsc-v1'}:
                continue
            parts = PurePosixPath(name).parts
            if (len(parts) != 2 or parts[0] != 'gvisor-bin' or not _NAME.fullmatch(parts[1])
                    or name != str(PurePosixPath(name))):
                raise ValueError('Only adjacent pinned release sidecars are allowed')
            sidecars += 1
        if not sidecars:
            raise ValueError('A runsc-only pin cannot establish runtime identity')
        return self


def _stable(st):
    return (st.st_dev, st.st_ino, st.st_mode, st.st_uid, st.st_gid,
            st.st_size, st.st_mtime_ns, st.st_ctime_ns, st.st_nlink)


def _regular_bytes(directory_fd, name, *, maximum, owner=None, digest_only=False):
    before = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
    if (not stat.S_ISREG(before.st_mode) or before.st_nlink != 1
            or before.st_size > maximum or before.st_size < 0
            or (owner and (before.st_uid, before.st_gid) != owner)):
        raise ValueError
    descriptor = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory_fd)
    try:
        if _stable(os.fstat(descriptor)) != _stable(before):
            raise ValueError
        data, checksum, size = bytearray(), hashlib.sha256(), 0
        while size <= maximum:
            chunk = os.read(descriptor, min(1024 * 1024, maximum + 1 - size))
            if not chunk:
                break
            size += len(chunk)
            if digest_only:
                checksum.update(chunk)
            else:
                data.extend(chunk)
        if (size != before.st_size or size > maximum
                or _stable(os.fstat(descriptor)) != _stable(before)
                or _stable(os.stat(name, dir_fd=directory_fd, follow_symlinks=False)) != _stable(before)):
            raise ValueError
        return (checksum.hexdigest() if digest_only else bytes(data)), before
    finally:
        os.close(descriptor)


def _canonical_directory(value, *, private=False):
    path = Path(value)
    if not path.is_absolute() or path != path.resolve(strict=True):
        raise ValueError
    metadata = path.lstat()
    if not stat.S_ISDIR(metadata.st_mode):
        raise ValueError
    if private and (metadata.st_uid != os.getuid() or metadata.st_mode & 0o077):
        raise ValueError
    return path


def _bounded_names(descriptor, maximum):
    # Stop discovery before allocating an unbounded directory listing. The
    # caller's remaining *global discovered* budget includes deferred siblings.
    names = []
    with os.scandir(descriptor) as iterator:
        for entry in iterator:
            if len(names) >= maximum:
                raise ValueError
            names.append(entry.name)
    return names


def rootfs_inventory_sha256(rootfs):
    """Hash bounded no-follow image-tree bytes; do not execute or unpack them.

    This is not proof that the tree came from an OCI image or remains immutable
    after inspection. Materializer provenance and read-only sealing remain gates.
    Symlinks are hashed as guest-root-relative links, never followed on the host.
    """
    try:
        root = _canonical_directory(rootfs)
        entries, total, discovered = [], 0, 0

        def walk(fd, prefix, depth, device):
            nonlocal total, discovered
            if depth > 64:
                raise ValueError
            names = _bounded_names(fd, MAX_ROOTFS_ENTRIES - discovered)
            discovered += len(names)
            for name in sorted(names):
                if (name in {'.', '..'} or '\n' in name or '\r' in name
                        or not name.encode('utf-8') or len(name.encode('utf-8')) > 255):
                    raise ValueError
                relative = prefix + name
                before = os.stat(name, dir_fd=fd, follow_symlinks=False)
                if before.st_dev != device or len(entries) >= MAX_ROOTFS_ENTRIES:
                    raise ValueError
                mode = stat.S_IMODE(before.st_mode)
                if stat.S_ISDIR(before.st_mode):
                    entries.append({'path': relative, 'kind': 'directory', 'mode': mode})
                    child = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
                    try:
                        if (os.fstat(child).st_dev, os.fstat(child).st_ino) != (before.st_dev, before.st_ino):
                            raise ValueError
                        walk(child, relative + '/', depth + 1, device)
                    finally:
                        os.close(child)
                    after = os.stat(name, dir_fd=fd, follow_symlinks=False)
                    if _stable(after) != _stable(before):
                        raise ValueError
                elif stat.S_ISREG(before.st_mode):
                    checksum, observed = _regular_bytes(fd, name, maximum=MAX_ROOTFS_BYTES - total, digest_only=True)
                    total += observed.st_size
                    entries.append({'path': relative, 'kind': 'file', 'mode': mode,
                                    'size_bytes': observed.st_size, 'sha256': checksum})
                elif stat.S_ISLNK(before.st_mode):
                    target = os.readlink(name, dir_fd=fd)
                    if (not target or '\n' in target or '\r' in target or target.startswith('//')
                            or len(target.encode('utf-8')) > 4096):
                        raise ValueError
                    # Absolute links point into the guest root, never host '/' .
                    logical = posixpath.normpath(target if target.startswith('/') else posixpath.join(prefix, target))
                    if logical == '..' or logical.startswith('../'):
                        raise ValueError
                    entries.append({'path': relative, 'kind': 'symlink', 'mode': mode, 'target': target})
                    if _stable(os.stat(name, dir_fd=fd, follow_symlinks=False)) != _stable(before):
                        raise ValueError
                else:
                    raise ValueError

        descriptor = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            opened = os.fstat(descriptor)
            walk(descriptor, '', 0, opened.st_dev)
            if (os.stat(root, follow_symlinks=False).st_ino != opened.st_ino
                    or _stable(os.fstat(descriptor)) != _stable(opened)):
                raise ValueError
        finally:
            os.close(descriptor)
        if not entries:
            raise ValueError
        return content_sha256({'version': 'c23-rootfs-inventory-v1', 'entries': entries, 'total_bytes': total})
    except (OSError, ValueError, TypeError, UnicodeError, RecursionError):
        raise SandboxError('sandbox_rootfs_integrity') from None


@dataclass(frozen=True, init=False)
class PreparedProfile:
    _document_json: str
    profile_sha256: str

    def __init__(self, *args, **kwargs):
        raise TypeError('Use render_oci_profile')

    @property
    def document(self):
        return json.loads(self._document_json)

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


def render_oci_profile(envelope, *, job_root, image_receipt, runtime_manifest):
    """Render one fixed configuration; return no runnable command or eligibility.

    There are no request-controlled environment, mounts, devices, flags, hooks,
    namespace paths, cgroup paths or executable overrides. The reserved job root
    and operator preparation receipts are internal trusted inputs only.
    """
    try:
        if not isinstance(envelope, VerifiedEnvelope):
            raise ValueError
        image = ImagePreparation.model_validate(image_receipt)
        runtime = RuntimePreparation.model_validate(runtime_manifest)
        environment = EnvironmentDescriptor.model_validate(envelope.environment)
        resources = ExperimentResources.model_validate(envelope.resources)
        if resources.memory_bytes % 4096 or resources.max_output_bytes < 8192:
            # The fixed profile never rounds an approved limit upward to a
            # filesystem/kernel allocation unit. Unsupported narrow proposals
            # require revision instead of silently broadening their budget.
            raise ValueError
        if (environment.kind != 'linux-gvisor' or environment.test_only
                or image.image_digest != environment.image_digest
                or image.lockfile_sha256 != environment.lockfile_sha256
                or image.python_version != environment.python_version
                or image.packages != environment.packages
                or runtime.architecture != image.architecture):
            raise ValueError
        job = _canonical_directory(job_root, private=True)
        if job.name != envelope.job_id:
            raise ValueError
        # A prepared state root is outside the sealed input bundle. It does not
        # exist by consequence of rendering and must be created/verified later.
        state_root = job.parent / ('runsc-state-' + envelope.job_id)
        if state_root.exists() or state_root.is_symlink():
            _canonical_directory(state_root, private=True)
        inputs = _canonical_directory(job / 'inputs', private=True)
        expected = {**dict(envelope.files), 'analysis.py': envelope.code, 'manifest.json': envelope.manifest_bytes}
        if len(expected) != len(envelope.files) + 2 or envelope.input_size_bytes > resources.max_input_bytes:
            raise ValueError
        descriptor = os.open(inputs, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            if set(_bounded_names(descriptor, len(expected))) != set(expected):
                raise ValueError
            for name, value in expected.items():
                if not _NAME.fullmatch(name) or name in {'.', '..'}:
                    raise ValueError
                actual, metadata = _regular_bytes(descriptor, name, maximum=resources.max_input_bytes,
                    owner=(runtime.input_host_uid, runtime.input_host_gid))
                if actual != value or metadata.st_mode & 0o222:
                    raise ValueError
        finally:
            os.close(descriptor)
        rootfs = _canonical_directory(job / 'rootfs')
        if rootfs_inventory_sha256(rootfs) != image.rootfs_inventory_sha256:
            raise ValueError
        budget = resources.max_output_bytes
        log_each = min(1024 * 1024, budget // 8)
        manifest_budget = min(1024 * 1024, budget // 8)
        file_budget = ((budget - 2 * log_each - manifest_budget) // 4096) * 4096
        scratch_bytes = (min(256 * 1024**2, resources.memory_bytes // 4) // 4096) * 4096
        config = {
            'ociVersion': '1.1.0', 'hostname': envelope.job_id,
            'root': {'path': 'rootfs', 'readonly': True},
            'process': {'terminal': False, 'cwd': '/outputs',
                'args': ['/usr/local/bin/python3', '-I', '-B', '/inputs/analysis.py'],
                'user': {'uid': APP_UID, 'gid': APP_GID, 'additionalGids': []},
                'env': ['PATH=/usr/local/bin', 'HOME=/scratch', 'TMPDIR=/scratch',
                        'MPLCONFIGDIR=/scratch/matplotlib', 'MPLBACKEND=Agg', 'LANG=C.UTF-8', 'TZ=UTC',
                        f'OMP_NUM_THREADS={resources.cpus}', f'OPENBLAS_NUM_THREADS={resources.cpus}'],
                'noNewPrivileges': True,
                'capabilities': {key: [] for key in ('bounding', 'effective', 'inheritable', 'permitted', 'ambient')},
                'rlimits': [{'type': name, 'soft': number, 'hard': number} for name, number in (
                    ('RLIMIT_CORE', 0), ('RLIMIT_NOFILE', MAX_FDS), ('RLIMIT_NPROC', MAX_HOST_PIDS),
                    ('RLIMIT_FSIZE', file_budget))]},
            'mounts': [
                {'destination': '/inputs', 'type': 'bind', 'source': str(inputs),
                 'options': ['rbind', 'ro', 'nosuid', 'nodev', 'noexec', 'private']},
                {'destination': '/outputs', 'type': 'tmpfs', 'source': 'tmpfs',
                 'options': ['rw', 'nosuid', 'nodev', 'noexec', f'size={file_budget}', 'nr_inodes=512',
                             f'uid={APP_UID}', f'gid={APP_GID}', 'mode=0700']},
                {'destination': '/scratch', 'type': 'tmpfs', 'source': 'tmpfs',
                 'options': ['rw', 'nosuid', 'nodev', 'noexec', f'size={scratch_bytes}', 'nr_inodes=4096',
                             f'uid={APP_UID}', f'gid={APP_GID}', 'mode=0700']},
                {'destination': '/proc', 'type': 'proc', 'source': 'proc',
                 'options': ['ro', 'nosuid', 'nodev', 'noexec']}],
            'linux': {'namespaces': [{'type': kind} for kind in ('pid', 'mount', 'ipc', 'uts', 'network', 'user', 'cgroup')],
                'uidMappings': [{'containerID': APP_UID, 'hostID': runtime.input_host_uid, 'size': 1}],
                'gidMappings': [{'containerID': APP_GID, 'hostID': runtime.input_host_gid, 'size': 1}],
                'rootfsPropagation': 'private', 'cgroupsPath': '/ocean-c23/' + envelope.job_id,
                'resources': {'cpu': {'period': 100000, 'quota': resources.cpus * 100000},
                    'memory': {'limit': resources.memory_bytes, 'swap': resources.memory_bytes},
                    'pids': {'limit': MAX_HOST_PIDS}, 'devices': [{'allow': False, 'access': 'rwm'}]},
                'maskedPaths': ['/proc/kcore', '/proc/keys', '/proc/timer_list', '/proc/sched_debug'],
                'readonlyPaths': ['/proc/sys', '/proc/sysrq-trigger', '/proc/irq', '/proc/bus']},
        }
        args = ['--root=' + str(state_root), '--platform=systrap', '--rootless=false', '--network=none',
                '--gofer-network-namespace=new', '--directfs=false', '--overlay2=none', '--host-uds=none',
                '--host-fifo=none', '--character-device-policy=emulated-only', '--net-raw=false',
                '--ignore-cgroups=false', '--allow-flag-override=false',
                '--sidecar-release-enforcement-policy=ALWAYS', f'--fdlimit={MAX_FDS}']
        document = {'version': PROFILE_VERSION, 'evidence_class': 'configuration-only', 'dispatch_eligible': False,
            'job_id': envelope.job_id, 'envelope_sha256': envelope.envelope_sha256,
            'environment_sha256': content_sha256(envelope.environment),
            'proposal_hashes': envelope.metadata['hashes'], 'declared_seeds': envelope.proposal['seeds'],
            'approved_resources': envelope.resources, 'input_size_bytes': envelope.input_size_bytes,
            'image_preparation': image.model_dump(mode='json'), 'runtime_preparation': runtime.model_dump(mode='json'),
            'config': config, 'runtime_args': args,
            'requirements': {'actual_linux_gvisor_verified': False, 'production_dispatch_built': False,
                'lifecycle': ['create', 'verify-enforcement', 'fresh-admission', 'start', 'wait',
                              'terminate-all-writers', 'validate-extracted-outputs', 'destroy-and-prove-host-subtree-empty'],
                'external_wall_watchdog_seconds': resources.wall_seconds,
                'max_input_bytes': resources.max_input_bytes, 'aggregate_output_and_logs_bytes': budget,
                'output_file_budget_bytes': file_budget, 'stdout_max_bytes': log_each, 'stderr_max_bytes': log_each,
                'output_manifest_max_bytes': manifest_budget, 'scratch_max_bytes': scratch_bytes,
                'readback_before_start': {'cpu.max': f'{resources.cpus * 100000} 100000',
                    'memory.max': resources.memory_bytes, 'memory.swap.max': 0, 'pids.max': MAX_HOST_PIDS},
                'unverified': ['Authorized Linux target, complete installed runtime and supported fixed flags',
                    'Authenticated image/layer/config materialization provenance and immutable rootfs sealing',
                    'Actual private namespaces, non-root owner mappings and input readability/integrity',
                    'CPU/memory/swap/host and guest process limits plus aggregate writable tmpfs and inode limits',
                    'External watchdog, bounded stdout/stderr and no-network/metadata/host/socket/package-install containment',
                    'Race-free output extraction after all guest writers stop and before tmpfs destruction',
                    'Sentry/gofer whole-host-subtree termination proof; lease expiry/state absence is insufficient',
                    'Repeatable scientific numerical fixtures with explicit seeds and tolerances']}}
        value = object.__new__(PreparedProfile)
        object.__setattr__(value, '_document_json', canonical_json(document))
        object.__setattr__(value, 'profile_sha256', content_sha256(document))
        return value
    except SandboxError:
        raise
    except (OSError, ValueError, TypeError, KeyError, AttributeError, UnicodeError, RecursionError):
        raise SandboxError('sandbox_profile_unavailable') from None
