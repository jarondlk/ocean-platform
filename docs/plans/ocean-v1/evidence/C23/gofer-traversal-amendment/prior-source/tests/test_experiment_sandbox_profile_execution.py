"""Configuration-only profile-v2 tests; all runtime gates remain false."""
from copy import deepcopy
import hashlib
from pathlib import Path

import pytest

from orchestration.experiment_sandbox.contracts import SandboxError
from orchestration.experiment_sandbox.profile import rootfs_inventory_sha256
from orchestration.experiment_sandbox.profile_execution import (
    GUEST_INIT_PATH, VERSION, render_execution_profile,
)
from sandbox.experiment.trusted_init import INIT_CAP_NAMES, START_CAP_NAMES, validate_policy
from tests.test_experiment_sandbox_profile import _layout, _structural_envelope
from tests.test_experiment_sandbox_contracts import approved_envelope as _retained_fixture

approved_envelope = _retained_fixture


@pytest.fixture
def layout(tmp_path, approved_envelope):
    envelope = _structural_envelope(approved_envelope)
    envelope, job, image, runtime = _layout(tmp_path, envelope)
    wrapper = job / 'rootfs' / GUEST_INIT_PATH.lstrip('/')
    wrapper.parent.mkdir(parents=True)
    raw = Path('sandbox/experiment/trusted_init.py').read_bytes()
    wrapper.write_bytes(raw)
    wrapper.chmod(0o444)
    image['rootfs_inventory_sha256'] = rootfs_inventory_sha256(job / 'rootfs')
    options = {'job_root': job, 'image_receipt': image, 'runtime_manifest': runtime,
               'control_host_uid': runtime['input_host_uid'] + 1,
               'control_host_gid': runtime['input_host_gid'] + 1,
               'trusted_init_sha256': hashlib.sha256(raw).hexdigest()}
    return envelope, options, wrapper


def test_control_root_separate_from_analysis_and_no_host_writable_mount(layout):
    envelope, options, _ = layout
    prepared = render_execution_profile(envelope, **options)
    document, config = prepared.document, prepared.config
    assert prepared.dispatch_eligible is False and document['dispatch_eligible'] is False
    assert document['version'] == VERSION and document['evidence_class'] == 'configuration-only'
    assert config['process']['user'] == {'uid': 0, 'gid': 0, 'additionalGids': []}
    assert config['process']['capabilities'] == {
        'bounding': list(START_CAP_NAMES), 'permitted': list(START_CAP_NAMES),
        'effective': list(START_CAP_NAMES), 'inheritable': [], 'ambient': []}
    assert config['process']['noNewPrivileges'] is True
    assert config['process']['args'][:5] == ['/usr/local/bin/python3', '-I', '-B', GUEST_INIT_PATH, '--policy']
    assert config['root']['readonly'] is True
    for mount in config['mounts']:
        if mount['type'] == 'bind':
            assert mount['destination'] == '/inputs' and 'ro' in mount['options']
        elif 'rw' in mount['options']:
            assert mount['type'] == 'tmpfs' and mount['destination'] in {'/outputs', '/scratch'}
    assert document['trusted_init']['analysis_guest_uid'] == 65532
    assert document['trusted_init']['post_mount_capabilities'] == list(INIT_CAP_NAMES)
    assert all(mount['destination'] not in {'/outputs', '/scratch'} for mount in config['mounts'])
    assert prepared.requirements['trusted_guest_mounts'] == [
        {'path': '/outputs', 'max_bytes': prepared.requirements['output_file_budget_bytes'], 'max_inodes': 512},
        {'path': '/scratch', 'max_bytes': prepared.requirements['scratch_max_bytes'], 'max_inodes': 4096}]
    assert config['linux']['uidMappings'] == [
        {'containerID': 0, 'hostID': options['control_host_uid'], 'size': 1},
        {'containerID': 65532, 'hostID': options['runtime_manifest']['input_host_uid'], 'size': 1}]
    assert all(item['hostID'] != 0 for item in config['linux']['uidMappings'])
    assert config['linux']['cgroupsPath'] == '/ocean-c23/' + envelope.job_id + '/sandbox'
    assert prepared.requirements['outer_cgroup_path'] == '/ocean-c23/' + envelope.job_id
    assert prepared.requirements['host_control_cgroup_path'] == '/ocean-c23/' + envelope.job_id + '/host'
    assert prepared.requirements['actual_linux_gvisor_verified'] is False
    assert prepared.requirements['production_dispatch_built'] is False
    mounts = {mount['destination']: mount for mount in config['mounts']}
    for path in ('/tmp', '/dev/shm'):
        assert mounts[path] == {'destination': path, 'type': 'tmpfs', 'source': 'tmpfs',
            'options': ['ro', 'nosuid', 'nodev', 'noexec', 'size=4096', 'uid=0', 'gid=0', 'mode=0555']}
    assert prepared.requirements['readonly_guest_temporary_paths'] == ['/tmp', '/dev/shm', '/run', '/var/tmp']
    assert 'TMPDIR=/scratch' in config['process']['env']
    assert 'MPLCONFIGDIR=/scratch/matplotlib' in config['process']['env']
    assert 'HOME=/scratch' in config['process']['env']


def test_policy_is_bound_to_approved_identity_and_unchanged_limits(layout):
    envelope, options, _ = layout
    prepared = render_execution_profile(envelope, **options)
    policy = validate_policy(prepared.document['trusted_init']['policy'])
    assert policy['job_id'] == envelope.job_id and policy['envelope_sha256'] == envelope.envelope_sha256
    assert policy['expected_names'] == sorted(p['name'] for p in envelope.proposal['expected_outputs'])
    assert policy['wall_seconds'] == envelope.resources['wall_seconds']
    assert policy['max_output_bytes'] == envelope.resources['max_output_bytes']
    assert policy['scratch_max_bytes'] == prepared.requirements['scratch_max_bytes']
    assert '--network=none' in prepared.runtime_args
    assert '--directfs=false' in prepared.runtime_args
    assert '--overlay2=none' in prepared.runtime_args
    assert '--oci-seccomp=true' in prepared.runtime_args
    # Detached Sentry boot failures use the existing bounded stderr capture.
    # Enabling debug itself would alter stdio routing and threaten the frame.
    assert '--debug=false' in prepared.runtime_args
    assert '--debug-log=/dev/stderr' in prepared.runtime_args
    assert '--panic-log=/dev/stderr' in prepared.runtime_args
    assert '--debug=true' not in prepared.runtime_args


@pytest.mark.parametrize('key,value', [
    ('control_host_uid', 0), ('control_host_uid', True), ('control_host_uid', -1),
    ('control_host_gid', 0), ('control_host_gid', True), ('control_host_gid', 2**32),
    ('trusted_init_sha256', 'f' * 64), ('trusted_init_sha256', None),
])
def test_operator_mapping_and_wrapper_identity_cannot_be_omitted_or_broadened(layout, key, value):
    envelope, options, _ = layout
    options[key] = value
    with pytest.raises(SandboxError):
        render_execution_profile(envelope, **options)


@pytest.mark.parametrize('key', ['control_host_uid', 'control_host_gid'])
def test_control_and_analysis_cannot_share_host_owner(layout, key):
    envelope, options, _ = layout
    options[key] = options['runtime_manifest']['input_host_' + key.removeprefix('control_host_')]
    with pytest.raises(SandboxError):
        render_execution_profile(envelope, **options)


@pytest.mark.parametrize('change', ['writable', 'symlink', 'hardlink', 'missing'])
def test_sealed_wrapper_material_must_be_regular_single_link_readonly(layout, change):
    envelope, options, wrapper = layout
    if change == 'writable':
        wrapper.chmod(0o644)
    elif change == 'missing':
        wrapper.unlink()
    elif change == 'symlink':
        raw = wrapper.read_bytes()
        wrapper.unlink()
        other = wrapper.parent / 'other.py'
        other.write_bytes(raw)
        wrapper.symlink_to(other.name)
    else:
        import os
        os.link(wrapper, wrapper.parent / 'other.py')
    # Re-pin the altered tree: rejection must not rely solely on stale inventory.
    try:
        options['image_receipt']['rootfs_inventory_sha256'] = rootfs_inventory_sha256(wrapper.parents[2])
    except SandboxError:
        pass
    with pytest.raises(SandboxError):
        render_execution_profile(envelope, **options)


def test_returned_profiles_are_detached_and_root_input_arguments_unchanged(layout):
    envelope, options, _ = layout
    before = deepcopy(options)
    prepared = render_execution_profile(envelope, **options)
    mutated = prepared.config
    mutated['linux']['uidMappings'][0]['hostID'] = 0
    document = prepared.document
    document['trusted_init']['policy']['wall_seconds'] = 99999
    assert prepared.config['linux']['uidMappings'][0]['hostID'] != 0
    assert prepared.document['trusted_init']['policy']['wall_seconds'] <= 600
    assert options == before


def seccomp_decision(policy, syscall, *arguments):
    """Evaluate this small OCI policy subset without making any syscall.

    This is a boundary-case oracle for serialized policy, not a gVisor proof.
    Actual guest raw-syscall probes are mandatory independently.
    """
    for rule in policy['syscalls']:
        if syscall not in rule['names']:
            continue
        if all((arguments[arg['index']] & arg['value']) == arg['valueTwo'] for arg in rule['args']):
            return rule['action'], rule.get('errnoRet')
    return policy['defaultAction'], None


@pytest.mark.parametrize('namespace', [0x00020000, 0x02000000, 0x04000000, 0x08000000,
                                       0x10000000, 0x20000000, 0x40000000])
def test_each_namespace_clone_bit_is_denied_alone_and_with_ordinary_flags(layout, namespace):
    envelope, options, _ = layout
    profile = render_execution_profile(envelope, **options)
    policy = profile.config['linux']['seccomp']
    for flags in (namespace, namespace | 17, namespace | 0x100 | 17, namespace | 0x7e020000):
        assert seccomp_decision(policy, 'clone', flags) == ('SCMP_ACT_ERRNO', 1)
    assert profile.requirements['guest_syscall_guard']['actual_adversarial_verified'] is False


@pytest.mark.parametrize('syscall,flags', [('fork', 0), ('vfork', 0), ('clone', 17),
    ('clone', 0x100 | 0x200 | 0x400 | 0x800 | 0x10000), ('mount', 14),
    ('capset', 0), ('setresuid', 65532), ('prctl', 38)])
def test_normal_processes_threads_and_trusted_init_mount_capability_operations_remain_allowed(layout, syscall, flags):
    envelope, options, _ = layout
    policy = render_execution_profile(envelope, **options).config['linux']['seccomp']
    assert seccomp_decision(policy, syscall, flags) == ('SCMP_ACT_ALLOW', None)


@pytest.mark.parametrize('syscall,expected_errno', [('unshare', 1), ('setns', 1), ('clone3', 38)])
def test_namespace_syscalls_and_pointer_based_clone3_are_denied_regardless_of_arguments(layout, syscall, expected_errno):
    envelope, options, _ = layout
    policy = render_execution_profile(envelope, **options).config['linux']['seccomp']
    for arguments in ((0, 0), (0x10000000, 0x20000), (2**63 - 1, 2**63 - 1)):
        assert seccomp_decision(policy, syscall, *arguments) == ('SCMP_ACT_ERRNO', expected_errno)


def test_syscall_amendment_keeps_image_wrapper_and_all_runtime_acceptance_gates_unchanged(layout):
    envelope, options, _ = layout
    profile = render_execution_profile(envelope, **options)
    document = profile.document
    assert document['supersedes_execution_profile_version'] == 'c23-oci-execution-preparation-v3'
    assert document['trusted_init']['sha256'] == options['trusted_init_sha256']
    assert document['image_preparation'] == options['image_receipt']
    architecture = options['runtime_manifest']['architecture']
    assert profile.config['linux']['seccomp']['architectures'] == [
        'SCMP_ARCH_X86_64' if architecture == 'amd64' else 'SCMP_ARCH_AARCH64']
    assert profile.requirements['guest_syscall_guard']['mount_syscall_remains_allowed_for_trusted_init'] is True
    assert profile.requirements['actual_linux_gvisor_verified'] is False
    assert profile.dispatch_eligible is False
