#!/usr/bin/env bash
# Dedicated trusted operator interpreter; never changes the scientific image.
set -euo pipefail
[[ "$(uname -s)" == Linux && "$(uname -m)" == x86_64 && "$(id -u)" == 0 ]]
[[ "$(hostname -s)" == c23-containment-01 ]]
[[ "$(curl --connect-timeout 2 --max-time 5 -fsS -H 'Metadata-Flavor: Google' http://metadata.google.internal/computeMetadata/v1/project/project-id)" == ocean-v1-c23-20261024 ]]
umask 077
export DEBIAN_FRONTEND=noninteractive
apt-get install -y --no-install-recommends build-essential
printf '%s  %s\n' 926ef8d3eab93fbf6e06011901273eec076b25594a4e1cdadd50c987f4f6d64e /tmp/ocean-c23-sqlite-autoconf-3540100.tar.gz | sha256sum --check --strict
[[ ! -e /var/lib/ocean-c23/sqlite-source && ! -e /opt/ocean-c23-sqlite ]]
install -d -m 0700 /var/lib/ocean-c23/sqlite-source
tar --extract --gzip --file=/tmp/ocean-c23-sqlite-autoconf-3540100.tar.gz --directory=/var/lib/ocean-c23/sqlite-source --strip-components=1 --no-same-owner
install -d -m 0755 /opt/ocean-c23-sqlite/lib
# A private SONAME-compatible library for this interpreter only. Do not run
# ldconfig or replace the OS SQLite library, and do not load a second DB driver.
cc -O2 -fPIC -shared -DSQLITE_THREADSAFE=1 -DSQLITE_ENABLE_COLUMN_METADATA \
  -Wl,-soname,libsqlite3.so.0 \
  /var/lib/ocean-c23/sqlite-source/sqlite3.c -lm -ldl -pthread \
  -o /opt/ocean-c23-sqlite/lib/libsqlite3.so.0
python3 -m venv /var/lib/ocean-c23/operator-venv
/var/lib/ocean-c23/operator-venv/bin/python -m pip install --only-binary=:all: --require-hashes --requirement=/tmp/dev.txt \
  > /var/lib/ocean-c23/evidence/operator-install.stdout.txt 2> /var/lib/ocean-c23/evidence/operator-install.stderr.txt
LD_LIBRARY_PATH=/opt/ocean-c23-sqlite/lib /var/lib/ocean-c23/operator-venv/bin/python - <<'PY' > /var/lib/ocean-c23/evidence/operator-sqlite.json
import hashlib
import json
from pathlib import Path
import sqlite3
import sys
with sqlite3.connect(':memory:') as db:
    version, source = db.execute('select sqlite_version(), sqlite_source_id()').fetchone()
assert version == '3.54.1'
print(json.dumps({'python': sys.version, 'sqlite': version, 'source_id': source,
                  'library_sha256': hashlib.sha256(Path('/opt/ocean-c23-sqlite/lib/libsqlite3.so.0').read_bytes()).hexdigest(),
                  'requirements_sha256': hashlib.sha256(Path('/tmp/dev.txt').read_bytes()).hexdigest()}, sort_keys=True))
PY
/var/lib/ocean-c23/operator-venv/bin/python -m pip freeze --all > /var/lib/ocean-c23/evidence/operator-packages.txt
install -d -m 0700 /sys/fs/cgroup/ocean-c23
printf '+cpu +memory +pids\n' > /sys/fs/cgroup/cgroup.subtree_control
printf '+cpu +memory +pids\n' > /sys/fs/cgroup/ocean-c23/cgroup.subtree_control
cat /sys/fs/cgroup/ocean-c23/cgroup.controllers /sys/fs/cgroup/ocean-c23/cgroup.subtree_control > /var/lib/ocean-c23/evidence/operator-cgroup-parent.txt
