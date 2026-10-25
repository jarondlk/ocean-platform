#!/usr/bin/env bash
# Trusted setup only, for the one explicitly authorized synthetic C23 VM.
set -euo pipefail

[[ "$(uname -s)" == Linux && "$(uname -m)" == x86_64 && "$(id -u)" == 0 ]]
C23_PROJECT="$(curl --connect-timeout 2 --max-time 5 -fsS -H 'Metadata-Flavor: Google' http://metadata.google.internal/computeMetadata/v1/project/project-id)"
[[ "$C23_PROJECT" == ocean-v1-c23-20261024 ]]
[[ "$(hostname -s)" == c23-containment-01 ]]

umask 077
exec > >(tee -a /var/log/ocean-c23-bootstrap.log) 2>&1
export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y --no-install-recommends ca-certificates curl zstd podman skopeo umoci python3-venv python3-pip

install -d -m 0700 /var/lib/ocean-c23 /var/lib/ocean-c23/materials /var/lib/ocean-c23/evidence /var/lib/ocean-c23/jobs
install -d -m 0755 /opt/ocean-c23-runtime
C23_RELEASE=release-20261019.0
C23_ARCHIVE=/var/lib/ocean-c23/materials/gvisor-x86_64.tar.zstd
C23_RUNTIME=/opt/ocean-c23-runtime/release-20261019.0
curl --fail --location --proto '=https' --tlsv1.2 --retry 3 \
  --output "$C23_ARCHIVE" \
  https://github.com/google/gvisor/releases/download/release-20261019.0/gvisor-x86_64.tar.zstd
printf '%s  %s\n' 8637abfb50f81552af25ca08f7172589c09292a7c881efe8d9e09a9f3b6bec7b "$C23_ARCHIVE" | sha256sum --check --strict

if [[ -e "$C23_RUNTIME" ]]; then
  echo 'Runtime directory already exists; operator must verify it rather than overwrite it.'
  exit 1
fi
install -d -m 0755 "$C23_RUNTIME"
zstd --decompress --stdout "$C23_ARCHIVE" > /var/lib/ocean-c23/materials/gvisor-x86_64.tar
python3 - <<'PY'
import hashlib
import json
from pathlib import Path, PurePosixPath
import tarfile

destination = Path('/opt/ocean-c23-runtime/release-20261019.0')
archive = Path('/var/lib/ocean-c23/materials/gvisor-x86_64.tar')
with tarfile.open(archive) as source:
    members = source.getmembers()
    assert 3 <= len(members) <= 256
    for member in members:
        path = PurePosixPath(member.name)
        assert not path.is_absolute() and '..' not in path.parts
        assert member.isfile() or member.isdir()
        assert member.size <= 512 * 1024**2
        logical = str(path)
        assert logical in {'runsc', 'containerd-shim-runsc-v1', 'gvisor-bin'} or logical.startswith('gvisor-bin/') or (logical == '.' and member.isdir())
    assert sum(member.size for member in members) <= 1024**3
    source.extractall(destination, filter='data')
for path in destination.rglob('*'):
    path.chmod(0o755)
files = {str(p.relative_to(destination)): hashlib.sha256(p.read_bytes()).hexdigest()
         for p in sorted(destination.rglob('*')) if p.is_file()}
assert {'runsc', 'containerd-shim-runsc-v1'} <= files.keys()
assert any(name.startswith('gvisor-bin/') for name in files)
manifest = {'release': 'release-20261019.0', 'architecture': 'amd64', 'files': files,
            'archive_sha256': '8637abfb50f81552af25ca08f7172589c09292a7c881efe8d9e09a9f3b6bec7b'}
with Path('/var/lib/ocean-c23/evidence/installed-runtime.json').open('x') as out:
    json.dump(manifest, out, indent=2, sort_keys=True)
    out.write('\n')
PY
"$C23_RUNTIME/runsc" --version > /var/lib/ocean-c23/evidence/runsc-version.txt
"$C23_RUNTIME/runsc" flags > /var/lib/ocean-c23/evidence/runsc-flags.txt
uname -a > /var/lib/ocean-c23/evidence/host-kernel.txt
cat /proc/sys/kernel/random/boot_id > /var/lib/ocean-c23/evidence/host-boot-id.txt
cat /sys/fs/cgroup/cgroup.controllers > /var/lib/ocean-c23/evidence/cgroup-controllers.txt
dpkg-query -W > /var/lib/ocean-c23/evidence/host-packages.txt
printf '%s\n' 'Trusted host preparation complete; no experiment has been executed.' > /var/lib/ocean-c23/evidence/bootstrap-complete.txt
