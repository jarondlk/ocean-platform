"""Trusted read-only observation at the reviewed no-start recovery barrier."""
import json
import os
from pathlib import Path
import subprocess
import sys
import time

from sandbox.experiment.gcp import run_operator_acceptance as op
from sandbox.experiment.gcp import run_recovery_acceptance as recovery
from orchestration.experiment_sandbox.journal import DurableExecutionJournal

op.require_worker()
assert sys.platform == 'linux' and os.geteuid() == 0
attempt = Path('/var/lib/ocean-c23/operator-acceptance/native-forensic-create-20261027-01')
output = Path('/var/lib/ocean-c23/evidence/native-forensic-before-start-01')
output.mkdir(mode=0o700)
source = Path('/var/lib/ocean-c23/operator-source-20261027-06')
command = [sys.executable, '-B', '-m', 'sandbox.experiment.gcp.run_recovery_acceptance',
    'run', '--episode', 'lost-create-ack', '--attempt-dir', str(attempt),
    '--blueprint', str(source / 'docs/plans/ocean-v1/evidence/C23/operator-acceptance-preparation/blueprint.json'),
    '--blueprint-sha256', '6d63c5b5a091330af6bcfbfcd9ec978cad860248500e0923d685859310bd6f5d',
    '--host-controls', '/var/lib/ocean-c23/evidence/host-positive-controls-20261027-01.json',
    '--host-controls-sha256', '22130d14a7c720b4ce3be083821a60489fd680d77d53c0aaf8f7dc9c3525b995',
    '--network-isolation', '/var/lib/ocean-c23/evidence/network-isolation-20261027-06.json',
    '--network-isolation-sha256', 'b9514241b5ef88ee217dad86b17eaffb4a32d2179111ebd77923355ab75fb102',
    '--normalization-receipt', '/var/lib/ocean-c23/evidence/rootfs-normalization-quota-v3.json',
    '--normalization-sha256', 'd75b965714e6335774af59eb6ab7616325b45ac3add38a5f2abf9a474a329824']
with (output / 'coordinator.stdout.txt').open('xb') as stdout, (output / 'coordinator.stderr.txt').open('xb') as stderr:
    process = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=stdout,
        stderr=stderr, close_fds=True, cwd=source)
    deadline = time.monotonic() + 90
    barrier_path = attempt / 'episodes/first/barrier.json'
    while not barrier_path.exists():
        if process.poll() is not None or time.monotonic() >= deadline:
            raise RuntimeError('No actual create barrier; no identity inferred')
        time.sleep(0.02)
    context_raw = op._read(attempt / 'recovery-context.json', op.MAX_FIXTURE)
    context = recovery._load_context(attempt / 'recovery-context.json', op._sha(context_raw))
    barrier = json.loads(op._read(barrier_path, op.MAX_FIXTURE))
    assert barrier['context_sha256'] == op._sha(context_raw)
    assert barrier['point'] == 'create_succeeded_before_ack_handling'
    envelope = op.verify_operator_fixture(op._immutable_document(
        attempt / 'operator-fixture.json', context['pins']['operator-fixture.json']))
    with DurableExecutionJournal(attempt / 'journal') as journal:
        owned = recovery._population(attempt, envelope, journal)
    groups, pids, memberships = {}, set(), {}
    outer = Path('/sys/fs/cgroup/ocean-c23') / envelope.job_id
    for group in (outer, outer / 'host', outer / 'sandbox'):
        assert group == group.resolve(strict=True)
        values = [int(x) for x in op._kernel_read(group / 'cgroup.procs', 4096).decode('ascii').splitlines()]
        assert len(values) <= 128 and all(1 < pid < 2**31 for pid in values)
        groups[str(group)] = values
        for pid in values:
            assert pid not in memberships
            memberships[pid] = '0::/ocean-c23/' + envelope.job_id + ('' if group == outer else '/' + group.name) + '\n'
        pids.update(values)
    assert len(pids) <= 128
    observations = {}
    for pid in sorted(pids):
        item = {}
        descriptor = os.open(f'/proc/{pid}', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
        try:
            file = os.open('cgroup', os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=descriptor)
            try:
                member = os.read(file, 1025)
            finally:
                os.close(file)
            if member.decode('ascii') != memberships[pid]:
                observations[str(pid)] = {'changed_membership': True}
                continue
            for name in ('cmdline', 'stat', 'cgroup', 'limits', 'status'):
                try:
                    file = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=descriptor)
                    try:
                        raw = os.read(file, 8193)
                        assert len(raw) <= 8192
                    finally:
                        os.close(file)
                    item[name] = raw.decode('utf-8', 'backslashreplace')
                except OSError as error:
                    item[name] = {'error': type(error).__name__, 'errno': error.errno}
            try:
                item['exe_link'] = os.readlink('exe', dir_fd=descriptor)
                info = os.stat('exe', dir_fd=descriptor)
                item['exe_identity'] = [info.st_dev, info.st_ino, info.st_mode, info.st_uid,
                    info.st_gid, info.st_size, info.st_nlink, info.st_mtime_ns, info.st_ctime_ns]
            except OSError as error:
                item['exe_error'] = {'error': type(error).__name__, 'errno': error.errno}
        finally:
            os.close(descriptor)
        observations[str(pid)] = item
    op._create(output / 'observations.json', op._canonical({
        'purpose': 'Non-authorizing kernel observation before any start',
        'barrier': barrier, 'owned_cgroup': owned, 'groups': groups,
        'processes': observations, 'native_guard_bypassed': False,
        'execution_start_requested': False, 'C23_complete': False}))
    result = process.wait(timeout=150)
    op._create(output / 'observer-result.json', op._canonical({
        'coordinator_exit_code': result, 'C23_complete': False}))
    raise SystemExit(result)
