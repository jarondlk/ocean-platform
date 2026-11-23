"""Bind the reviewed B3 worker archive to the single approved Tokyo trial."""

import argparse
import ast
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
import subprocess
import tarfile

BASE_SOURCE = "a7a373150c57cb94d08a5867ce537a6b65ae3368"
BASE_ARCHIVE = "3419682cf3401bfa259284f94a03b7834f86cd3e2285a0aa08a138e7193ea6d7"
SOURCE_COUNT = 248
CONTEXT = "2adbed53ee4ccebd3e9bc8d632720d71744e3a09b268205219bbcb0d48900639"
REMOTE_ROOT = "/var/lib/ocean-c23/operator-source-beta-b3-20261123"
PROJECT = "ocean-v1-beta-20261101"
INSTANCE = "ocean-v1-beta-b3-worker-1123"
NETWORK = "ocean-v1-beta-b3-isolated"
SUBNET = "ocean-v1-beta-b3-tokyo"
HOST_PINS = (
    ("ocean-v1-c23-20261024", PROJECT, 1),
    ("c23-containment-01", INSTANCE, 1),
)
DOWNLOAD = """curl --fail --location --proto '=https' --tlsv1.2 --retry 3 \\
  --output "$C23_ARCHIVE" \\
  https://github.com/google/gvisor/releases/download/release-20261019.0/gvisor-x86_64.tar.zstd"""
BINDINGS = {
    "run_operator_acceptance.py": HOST_PINS
    + (
        ("c23-private", NETWORK, 2),
        ("c23-tokyo", SUBNET, 2),
    ),
    "normalize_rootfs.py": HOST_PINS,
    "bootstrap_worker.sh": HOST_PINS
    + ((DOWNLOAD, 'install -m 0400 /tmp/gvisor-x86_64.tar.zstd "$C23_ARCHIVE"', 1),),
    "prepare_operator_env.sh": HOST_PINS,
    "resume_worker.sh": HOST_PINS,
    "build_quota_amendment.sh": HOST_PINS
    + (
        (
            "b0627e69c180f3880c683673fee289b4c82de926a1cd48d3cfccb3b3462cb653",
            CONTEXT,
            1,
        ),
    ),
}
BINDINGS = {
    f"sandbox/experiment/gcp/{name}": bindings for name, bindings in BINDINGS.items()
}


def digest(data):
    return sha256(data).hexdigest()


def read_base(archive, manifest):
    raw = archive.read_bytes()
    document = json.loads(manifest.read_bytes())
    expected = document["source_files"]
    if (
        digest(raw) != BASE_ARCHIVE
        or document["archive_sha256"] != BASE_ARCHIVE
        or document["source_commit"] != BASE_SOURCE
        or len(expected) != SOURCE_COUNT
    ):
        raise ValueError("Unexpected base archive or manifest")
    files = {}
    with tarfile.open(fileobj=BytesIO(raw), mode="r:") as source:
        for member in source:
            if (
                member.name not in expected
                or member.name in files
                or not member.isreg()
                or not 0 < member.size <= 2 * 1024**2
            ):
                raise ValueError(f"Unexpected source member {member.name}")
            payload = source.extractfile(member).read()
            if digest(payload) != expected[member.name]:
                raise ValueError(f"Unexpected source digest for {member.name}")
            files[member.name] = payload
    if files.keys() != expected.keys():
        raise ValueError("Base archive member set is incomplete")
    return files


def prepare(archive, manifest, context, output):
    files = read_base(archive, manifest)
    if digest(context.read_bytes()) != CONTEXT:
        raise ValueError("Unexpected scientific build context")
    supersessions = {}
    for name, bindings in BINDINGS.items():
        old_payload = files[name]
        rendered = old_payload.decode("utf-8")
        for old, new, count in bindings:
            if rendered.count(old) != count:
                raise ValueError(f"Host or setup binding moved in {name}")
            rendered = rendered.replace(old, new)
        payload = rendered.encode("utf-8")
        if name.endswith(".py"):
            ast.parse(rendered, filename=name)
        else:
            subprocess.run(["bash", "-n"], input=payload, check=True)
        files[name] = payload
        supersessions[name] = {
            "base_sha256": digest(old_payload),
            "trial_sha256": digest(payload),
        }

    output.mkdir(mode=0o700, exist_ok=False)
    target_archive = output / "tokyo-worker-source.tar"
    with tarfile.open(target_archive, mode="x:") as target:
        for name, payload in sorted(files.items()):
            entry = tarfile.TarInfo(name)
            entry.mode = 0o400
            entry.size = len(payload)
            target.addfile(entry, BytesIO(payload))
    document = {
        "version": "beta-b3-tokyo-worker-target-v1",
        "source_commit": BASE_SOURCE,
        "base_archive_sha256": BASE_ARCHIVE,
        "archive_sha256": digest(target_archive.read_bytes()),
        "build_context_sha256": CONTEXT,
        "intended_remote_root": REMOTE_ROOT,
        "project": PROJECT,
        "instance": INSTANCE,
        "network": NETWORK,
        "subnet": SUBNET,
        "zone": "asia-northeast1-a",
        "source_files": {
            name: digest(payload) for name, payload in sorted(files.items())
        },
        "intentional_source_supersessions": supersessions,
    }
    with (output / "tokyo-worker-source.json").open("x") as record:
        json.dump(document, record, sort_keys=True, indent=2)
        record.write("\n")
    return document


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for argument in ("archive", "manifest", "context", "output"):
        parser.add_argument(f"--{argument}", required=True, type=Path)
    arguments = parser.parse_args()
    rendered = prepare(
        arguments.archive, arguments.manifest, arguments.context, arguments.output
    )
    print(rendered["archive_sha256"])
