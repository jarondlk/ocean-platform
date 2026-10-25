#!/usr/bin/env bash
# Trusted offline build of the reviewed quota amendment. Retain the initial image.
set -euo pipefail
[[ "$(uname -s)" == Linux && "$(uname -m)" == x86_64 && "$(id -u)" == 0 ]]
[[ "$(hostname -s)" == c23-containment-01 ]]
[[ "$(curl --connect-timeout 2 --max-time 5 -fsS -H 'Metadata-Flavor: Google' http://metadata.google.internal/computeMetadata/v1/project/project-id)" == ocean-v1-c23-20261024 ]]
umask 077
C23_LABEL=quota-v3
C23_CONTEXT=/var/lib/ocean-c23/build-context-quota-v3
C23_BASE=docker.io/library/python@sha256:57d96f71de145a98e7ceca18ee4ade77bba4103a33a72dfaea026b23625c6bf0
printf '%s  %s\n' b0627e69c180f3880c683673fee289b4c82de926a1cd48d3cfccb3b3462cb653 /tmp/c23-build-context-quota-v3.tar | sha256sum --check --strict
[[ ! -e "$C23_CONTEXT" && ! -e /var/lib/ocean-c23/scientific-oci-quota-v3 && ! -e /var/lib/ocean-c23/scientific-bundle-quota-v3 ]]
if podman image exists localhost/ocean-c23:quota-v3; then
  echo 'Amendment image already exists; inspect it without overwriting.'
  exit 1
fi
python3 - <<'PY'
from pathlib import Path
import tarfile
destination = Path('/var/lib/ocean-c23/build-context-quota-v3')
destination.mkdir(mode=0o700)
with tarfile.open('/tmp/c23-build-context-quota-v3.tar') as source:
    entries = source.getmembers()
    assert len(entries) <= 64
    for entry in entries:
        path = Path(entry.name)
        assert not path.is_absolute() and '..' not in path.parts
        assert entry.isfile() or entry.isdir()
        assert entry.size <= 128 * 1024**2
    assert sum(entry.size for entry in entries) <= 512 * 1024**2
    source.extractall(destination, filter='data')
PY
printf '%s  %s\n' 1c808a836d4837b30c6a665222640f589bd9eb5f50cf60d71a764bec41273bbc "$C23_CONTEXT/trusted_init.py" | sha256sum --check --strict
# The base is already materialized from trusted preparation. No network or pull
# is permitted in this amendment build, even if setup egress still exists.
podman image exists "$C23_BASE"
podman build --network=none --pull=never --format=oci --no-cache \
  --build-arg "SCIENTIFIC_BASE=$C23_BASE" \
  --tag localhost/ocean-c23:quota-v3 "$C23_CONTEXT" \
  > /var/lib/ocean-c23/evidence/image-build-quota-v3.stdout.txt \
  2> /var/lib/ocean-c23/evidence/image-build-quota-v3.stderr.txt
podman image inspect localhost/ocean-c23:quota-v3 \
  > /var/lib/ocean-c23/evidence/scientific-image-inspect-quota-v3.json
skopeo copy containers-storage:localhost/ocean-c23:quota-v3 oci:/var/lib/ocean-c23/scientific-oci-quota-v3:quota-v3 \
  > /var/lib/ocean-c23/evidence/oci-copy-quota-v3.stdout.txt \
  2> /var/lib/ocean-c23/evidence/oci-copy-quota-v3.stderr.txt
umoci unpack --image /var/lib/ocean-c23/scientific-oci-quota-v3:quota-v3 /var/lib/ocean-c23/scientific-bundle-quota-v3 \
  > /var/lib/ocean-c23/evidence/umoci-unpack-quota-v3.stdout.txt \
  2> /var/lib/ocean-c23/evidence/umoci-unpack-quota-v3.stderr.txt
printf '%s\n' "Offline $C23_LABEL build completed; containment remains unverified." \
  > /var/lib/ocean-c23/evidence/image-build-quota-v3-complete.txt
