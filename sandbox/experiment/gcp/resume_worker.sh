#!/usr/bin/env bash
# Reestablish only the trusted cgroup parent after a fresh dedicated-worker boot.
# Does not rerun bootstrap/install, launch analysis, infer old-job termination,
# remove journal state or release any C22 reservation.
set -euo pipefail
[[ "$(uname -s)" == Linux && "$(uname -m)" == x86_64 && "$(id -u)" == 0 ]]
[[ "$(hostname -s)" == c23-containment-01 ]]
[[ "$(curl --connect-timeout 2 --max-time 5 -fsS -H 'Metadata-Flavor: Google' http://metadata.google.internal/computeMetadata/v1/project/project-id)" == ocean-v1-c23-20261024 ]]
umask 077
[[ -f /var/lib/ocean-c23/evidence/installed-runtime.json ]]
[[ -f /opt/ocean-c23-sqlite/lib/libsqlite3.so.0 ]]
[[ -x /var/lib/ocean-c23/operator-venv/bin/python ]]
[[ -f /sys/fs/cgroup/cgroup.controllers ]]
install -d -m 0700 /sys/fs/cgroup/ocean-c23
python3 -I -S -B - <<'PY'
from pathlib import Path
root = Path('/sys/fs/cgroup/ocean-c23')
assert not (root / 'cgroup.procs').read_text().strip()
assert 'populated 0' in (root / 'cgroup.events').read_text().splitlines()
PY
printf '+cpu +memory +pids\n' > /sys/fs/cgroup/cgroup.subtree_control
printf '+cpu +memory +pids\n' > /sys/fs/cgroup/ocean-c23/cgroup.subtree_control
LD_LIBRARY_PATH=/opt/ocean-c23-sqlite/lib /var/lib/ocean-c23/operator-venv/bin/python - <<'PY'
import json
from pathlib import Path
import sqlite3
with sqlite3.connect(':memory:') as db:
    sqlite_version = db.execute('select sqlite_version()').fetchone()[0]
assert sqlite_version == '3.54.1'
root = Path('/sys/fs/cgroup/ocean-c23')
assert not (root / 'cgroup.procs').read_text().strip()
assert 'populated 0' in (root / 'cgroup.events').read_text().splitlines()
controllers = (root / 'cgroup.subtree_control').read_text().split()
assert {'cpu', 'memory', 'pids'} <= set(controllers)
print(json.dumps({'version': 'c23-trusted-worker-resume-v1',
    'boot_id': Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
    'sqlite_version': sqlite_version, 'controllers': controllers,
    'old_job_termination_inferred': False, 'dispatch_eligible': False}, sort_keys=True))
PY
