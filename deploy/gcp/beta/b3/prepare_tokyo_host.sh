#!/usr/bin/env bash
# Trusted setup for the exact temporary beta worker, before running any fixture.
set -euo pipefail
umask 077
[[ "$(id -u)" == 0 && "$(uname -s)" == Linux && "$(uname -m)" == x86_64 ]]
[[ "$(hostname -s)" == ocean-v1-beta-b3-worker-1123 ]]
[[ "$(curl --connect-timeout 2 --max-time 5 -fsS -H 'Metadata-Flavor: Google'   http://metadata.google.internal/computeMetadata/v1/project/project-id)" == ocean-v1-beta-20261101 ]]

bundle="${1:?root-private input directory required}"
manifest_sha="${2:?expected manifest SHA-256 required}"
[[ "$bundle" == /var/lib/ocean-c23/trial-inputs && "$manifest_sha" =~ ^[0-9a-f]{64}$ ]]
[[ "$(stat -c '%u:%g:%a' "$bundle")" == 0:0:700 ]]
printf '%s  %s\n' "$manifest_sha" "$bundle/tokyo-worker-source.json" | sha256sum --check --strict

root=/var/lib/ocean-c23/operator-source-beta-b3-20261123
python3 -I -S -B - "$bundle" "$root" <<'PY'
from hashlib import sha256
from pathlib import Path
import json
import sys
import tarfile

bundle, root = (Path(value) for value in sys.argv[1:])
manifest = json.loads((bundle / "tokyo-worker-source.json").read_bytes())
archive = bundle / "tokyo-worker-source.tar"
context = bundle / "c23-build-context-quota-v3.tar"
assert root == Path(manifest["intended_remote_root"])
assert sha256(archive.read_bytes()).hexdigest() == manifest["archive_sha256"]
assert sha256(context.read_bytes()).hexdigest() == manifest["build_context_sha256"]
expected = manifest["source_files"]
with tarfile.open(archive, mode="r:") as source:
    members = source.getmembers()
    assert len(members) == len(expected) == 248
    assert {member.name for member in members} == expected.keys()
    root.mkdir(mode=0o700)
    for member in members:
        path = root / member.name
        assert path.is_relative_to(root) and ".." not in path.parts
        assert member.isreg() and 0 < member.size <= 2 * 1024**2
        data = source.extractfile(member).read()
        assert sha256(data).hexdigest() == expected[member.name]
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        with path.open("xb") as output:
            output.write(data)
        path.chmod(0o400)
PY

set -o noclobber
stage=/tmp
for name in gvisor-x86_64.tar.zstd ocean-c23-sqlite-autoconf-3540100.tar.gz c23-build-context-quota-v3.tar; do
  cat "$bundle/$name" > "$stage/$name"
done
cat "$root/requirements/dev.txt" > "$stage/dev.txt"
bash "$root/sandbox/experiment/gcp/bootstrap_worker.sh"
bash "$root/sandbox/experiment/gcp/prepare_operator_env.sh"

install -m 0400 "$bundle/tokyo-worker-source.json" /var/lib/ocean-c23/evidence/
export LD_LIBRARY_PATH=/opt/ocean-c23-sqlite/lib
export PYTHONPATH="$root"
export PYTHONDONTWRITEBYTECODE=1
python=/var/lib/ocean-c23/operator-venv/bin/python
cd "$root"
"$python" -B - <<'PY'
import importlib
import json
from pathlib import Path
from orchestration.experiment_sandbox import physical_termination as physical

required = physical.WORKER_FILES - {"sandbox/experiment/trusted_init.py"}
for path in sorted(required):
    importlib.import_module(path[:-3].replace("/", "."))
importlib.import_module("tests.research_experiment_support")
importlib.import_module("sandbox.experiment.gcp.run_retained_acceptance")
manifest = json.loads(Path("/var/lib/ocean-c23/evidence/tokyo-worker-source.json").read_bytes())
physical._protected_sources(Path.cwd(), manifest["source_files"])
physical.require_loaded_source_provenance(Path.cwd(), manifest["source_files"], check=lambda: None)
print("Protected Linux sources and loaded imports verified")
PY

podman pull --arch=amd64 --os=linux   docker.io/library/python@sha256:57d96f71de145a98e7ceca18ee4ade77bba4103a33a72dfaea026b23625c6bf0
"$python" -B -m sandbox.experiment.gcp.run_operator_acceptance prepare-host-controls   --output=/var/lib/ocean-c23/evidence/host-positive-beta-b3-20261123.json
