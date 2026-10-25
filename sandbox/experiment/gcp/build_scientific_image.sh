#!/usr/bin/env bash
# Trusted, network-separated image build on the dedicated synthetic worker.
set -euo pipefail
[[ "$(uname -s)" == Linux && "$(uname -m)" == x86_64 && "$(id -u)" == 0 ]]
[[ "$(hostname -s)" == c23-containment-01 ]]
[[ "$(curl --connect-timeout 2 --max-time 5 -fsS -H 'Metadata-Flavor: Google' http://metadata.google.internal/computeMetadata/v1/project/project-id)" == ocean-v1-c23-20261024 ]]
umask 077
[[ -f /var/lib/ocean-c23/evidence/bootstrap-complete.txt ]]
printf '%s  %s\n' 76a96e82db3aed605d2e5db99df4f88f4e2826648a14300a30c0e8dadb3a092c /tmp/c23-build-context-20261024.tar | sha256sum --check --strict
[[ ! -e /var/lib/ocean-c23/build-context ]]
install -d -m 0700 /var/lib/ocean-c23/build-context
tar --extract --file=/tmp/c23-build-context-20261024.tar --directory=/var/lib/ocean-c23/build-context --no-same-owner
printf '%s  %s\n' 7a2b4d4089d0911a8a678624bc02d70a90eea170e5fdb252271c9859c3fecf74 /var/lib/ocean-c23/build-context/trusted_init.py | sha256sum --check --strict
C23_BASE=docker.io/library/python@sha256:57d96f71de145a98e7ceca18ee4ade77bba4103a33a72dfaea026b23625c6bf0
# The only image pull occurs in this trusted setup phase. Build RUN steps have
# no networking and the recipe installs only the complete hash-locked wheels.
podman pull --arch=amd64 --os=linux "$C23_BASE" > /var/lib/ocean-c23/evidence/base-pull.stdout.txt 2> /var/lib/ocean-c23/evidence/base-pull.stderr.txt
podman image inspect "$C23_BASE" > /var/lib/ocean-c23/evidence/base-image-inspect.json
podman build --network=none --pull=never --format=oci --no-cache \
  --build-arg "SCIENTIFIC_BASE=$C23_BASE" \
  --tag localhost/ocean-c23:initial /var/lib/ocean-c23/build-context \
  > /var/lib/ocean-c23/evidence/image-build.stdout.txt 2> /var/lib/ocean-c23/evidence/image-build.stderr.txt
podman image inspect localhost/ocean-c23:initial > /var/lib/ocean-c23/evidence/scientific-image-inspect.json
skopeo copy containers-storage:localhost/ocean-c23:initial oci:/var/lib/ocean-c23/scientific-oci:initial \
  > /var/lib/ocean-c23/evidence/oci-copy.stdout.txt 2> /var/lib/ocean-c23/evidence/oci-copy.stderr.txt
umoci unpack --image /var/lib/ocean-c23/scientific-oci:initial /var/lib/ocean-c23/scientific-bundle \
  > /var/lib/ocean-c23/evidence/umoci-unpack.stdout.txt 2> /var/lib/ocean-c23/evidence/umoci-unpack.stderr.txt
printf '%s\n' 'Trusted offline scientific image built; containment and experiment execution remain unverified.' > /var/lib/ocean-c23/evidence/image-build-complete.txt
