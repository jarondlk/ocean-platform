"""Package readable answer templates as a one-file overlay on the live B2 API image.

The live serving API and research controller both run the B2 image built from
runtime 0994e9d. This packager selects a runtime commit that differs from that
runtime only in ``orchestration/research_synthesis.py``, copies that file over
the exact live image, and rewrites the packaged source manifest and host
configuration to name the new runtime commit. Everything is read from Git
objects; the working checkout is not used. No cloud call is made here.

The generated Cloud Build configuration first proves that the base image
carries the reconstructed B2 manifest and host configuration byte for byte,
then, after the overlay, that every one of the 181 runtime files in the image
hashes to its manifest pin.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[4]
PROJECT = "ocean-v1-beta-20261101"
REGISTRY = f"asia-northeast1-docker.pkg.dev/{PROJECT}/ocean-v1-beta/snapshot-api"
BASE_IMAGE = REGISTRY + "@sha256:64f99fceba741b5ab781466c45191ea190d241cb9fe745fa342d2d53beeb574e"
BASE_RUNTIME = "0994e9de7684025d5bf94ec8ad6a96e21edd1526"
B1_REVISION = "4872d04323c7e7b2bc1946ece41bd0a6333f39c0"
B1_INVENTORY = "docs/plans/ocean-v1/beta/b1-20261114/ready-list-production-source-manifest.json"
ADDED = ("ingestion/edna_input_cache.py",)
CHANGED = "orchestration/research_synthesis.py"
# Pinned build inputs that are not copied into the image, and renamed copies.
NOT_IN_IMAGE = ("deploy/gcp/beta/api/Dockerfile", "deploy/gcp/beta/api/prepare_context.py", "requirements/runtime.txt")
RENAMED = {"deploy/gcp/beta/api/entry.py": "beta_entry.py"}
BUILDER = "gcr.io/cloud-builders/docker@sha256:fbc05705e6f24467e40ae8a4097ab9b8fae1116551f838fa2c55f4367427fc36"
BUILD_ACCOUNT = f"projects/{PROJECT}/serviceAccounts/ocean-v1-beta-build@{PROJECT}.iam.gserviceaccount.com"


def git(*args: str) -> bytes:
    return subprocess.run(["git", "-C", str(ROOT), *args], check=True, capture_output=True, timeout=30).stdout


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def canonical(value) -> bytes:
    # Same encoding as deploy/gcp/beta/b2/prepare_api_context.py.
    return (json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n").encode()


def blob(revision: str, name: str) -> bytes:
    entry = git("ls-tree", revision, "--", name).split()
    if len(entry) != 4 or entry[:2] != [b"100644", b"blob"]:
        raise ValueError(f"Expected a committed regular file: {name}@{revision}")
    return git("show", f"{revision}:{name}")


def runtime_paths() -> list[str]:
    paths = list(json.loads(blob(B1_REVISION, B1_INVENTORY))["sources"]) + list(ADDED)
    if len(paths) != 181 or len(set(paths)) != 181:
        raise ValueError("Expected the 181-file B2 runtime inventory")
    return paths


def pins_at(revision: str, paths: list[str]) -> dict[str, str]:
    return {name: digest(blob(revision, name)) for name in paths}


def source_manifest(revision: str, pins: dict[str, str]) -> dict:
    return {"version": "ocean-v1-beta-api-context-v1", "project_id": PROJECT, "revision": revision,
            "sources": pins,
            "source_manifest_sha256": digest(json.dumps(pins, sort_keys=True, separators=(",", ":")).encode())}


def host_configuration(revision: str) -> dict:
    return {"version": "ocean-v1-api-host-v1", "project_id": PROJECT, "site_id": "v1:" + PROJECT,
            "public_origin": "https://beta.oceaninfobio.com", "database_name": "ocean_v1_beta",
            "backend_hosts": ["127.0.0.1:8000"], "allowed_providers": ["google"],
            "internal_issuer": "ocean-v1-frontend", "internal_audience": "ocean-v1-api", "revision": revision}


def file_check() -> str:
    """Python lines that compare every image file with its manifest pin."""
    return (f"skip, renamed = {NOT_IN_IMAGE!r}, {RENAMED!r}\n"
            "manifest = json.load(open('/opt/ocean/source-manifest.json'))\n"
            "pins = {n: p for n, p in manifest['sources'].items() if n not in skip}\n"
            "bad = [n for n, p in pins.items() if sha('/opt/ocean/' + renamed.get(n, n)) != p]\n"
            "assert not bad and len(manifest['sources']) == 181 and len(pins) == 178, bad\n")


def base_check(manifest_sha: str, host_sha: str) -> str:
    return ("import hashlib, json, os\n"
            "sha = lambda p: hashlib.sha256(open(p, 'rb').read()).hexdigest() if os.path.exists(p) else None\n"
            f"assert sha('/opt/ocean/source-manifest.json') == {manifest_sha!r}, 'base manifest differs'\n"
            f"assert sha('/opt/ocean/beta-host-config.json') == {host_sha!r}, 'base host configuration differs'\n"
            + file_check() +
            "assert os.getuid() == 10001\n"
            "print('Base image carries the reconstructed B2 manifest and host configuration; 178 image files match pins')\n")


def image_proof(manifest_sha: str, revision: str) -> str:
    return ("import hashlib, json, os, sys\n"
            "sha = lambda p: hashlib.sha256(open(p, 'rb').read()).hexdigest() if os.path.exists(p) else None\n"
            f"assert sha('/opt/ocean/source-manifest.json') == {manifest_sha!r}\n"
            + file_check() +
            "host = json.load(open('/opt/ocean/beta-host-config.json'))\n"
            f"assert manifest['revision'] == host['revision'] == {revision!r}\n"
            "assert os.getuid() == 10001\n"
            "sys.path.insert(0, '/opt/ocean')\n"
            "import orchestration.research_synthesis as synthesis\n"
            "assert synthesis.PACK_VERSION == 'c21-synthesis-pack-v2'\n"
            "assert synthesis._count_text({'entity': 'datasets', 'value': 1, 'denominator': 'd'}, 'en') == '1 dataset — counted as: d.'\n"
            "print('All 178 image files match their pins; readable templates import')\n")


def prepare(revision: str, output: Path) -> dict:
    if not re.fullmatch(r"[0-9a-f]{40}", revision):
        raise ValueError("Use an explicit full runtime commit")
    git("merge-base", "--is-ancestor", BASE_RUNTIME, revision)
    paths = runtime_paths()
    base_pins, pins = pins_at(BASE_RUNTIME, paths), pins_at(revision, paths)
    changed = sorted(name for name in paths if base_pins[name] != pins[name])
    if changed != [CHANGED]:
        raise ValueError(f"Runtime must differ from the live B2 runtime only in {CHANGED}: {changed}")
    base_manifest, base_host = canonical(source_manifest(BASE_RUNTIME, base_pins)), canonical(host_configuration(BASE_RUNTIME))
    manifest, host = canonical(source_manifest(revision, pins)), canonical(host_configuration(revision))
    image = REGISTRY + ":answers-" + revision[:12]
    package = {"version": "ocean-beta-answers-api-package-v1", "runtime_revision": revision,
               "base_runtime_revision": BASE_RUNTIME, "base_image": BASE_IMAGE, "overlay": [CHANGED],
               "base_source_manifest_file_sha256": digest(base_manifest), "base_host_configuration_sha256": digest(base_host),
               "source_manifest_file_sha256": digest(manifest), "host_configuration_sha256": digest(host),
               "packager_sha256": digest(Path(__file__).read_bytes()), "image_tag": image}
    dockerfile = "\n".join([
        "FROM " + BASE_IMAGE,
        f"COPY --chown=0:0 --chmod=0444 application/{CHANGED} /opt/ocean/{CHANGED}",
        "COPY --chown=0:0 --chmod=0444 source-manifest.json /opt/ocean/source-manifest.json",
        "COPY --chown=0:0 --chmod=0444 beta-host-config.json /opt/ocean/beta-host-config.json",
        "COPY --chown=0:0 --chmod=0444 answers-package.json /opt/ocean/answers-package.json", ""]).encode()
    run = ["run", "--rm", "--network=none", "--read-only", "--cap-drop=ALL", "--security-opt=no-new-privileges", "--entrypoint=python"]
    build = {"serviceAccount": BUILD_ACCOUNT, "timeout": "900s",
             "options": {"logging": "CLOUD_LOGGING_ONLY", "diskSizeGb": 100, "machineType": "E2_STANDARD_2"},
             "steps": [
                 {"name": BUILDER, "id": "verify-live-base-image", "args": [*run, BASE_IMAGE, "-c", base_check(digest(base_manifest), digest(base_host))]},
                 {"name": BUILDER, "id": "build-answers-api", "env": ["DOCKER_BUILDKIT=1"],
                  "args": ["build", "--platform=linux/amd64", "--tag=" + image, "--label=org.opencontainers.image.revision=" + revision, "."]},
                 {"name": BUILDER, "id": "verify-answers-api-offline", "args": [*run, image, "-c", image_proof(digest(manifest), revision)]}],
             "images": [image]}
    files = {"Dockerfile": dockerfile, "source-manifest.json": manifest, "beta-host-config.json": host,
             "answers-package.json": canonical(package), "cloudbuild.json": canonical(build),
             "application/" + CHANGED: blob(revision, CHANGED)}
    output = output.absolute()
    if output.exists() or output.is_relative_to(ROOT) or not output.parent.is_dir():
        raise ValueError("Choose a new directory outside the checkout")
    output.mkdir(mode=0o700)
    for name, raw in files.items():
        target = output / name
        target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        with os.fdopen(os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "wb") as stream:
            stream.write(raw)
    return {"package": package, "files": {name: digest(raw) for name, raw in sorted(files.items())}}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--revision", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(prepare(args.revision, args.output), indent=2))
