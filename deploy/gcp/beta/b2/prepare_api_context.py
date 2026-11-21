"""Package the qualified B2 runtime as a read-only overlay on the accepted B1 image."""

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
REGISTRY = "asia-northeast1-docker.pkg.dev/" + PROJECT + "/ocean-v1-beta/snapshot-api"
BASE_REVISION = "4872d04323c7e7b2bc1946ece41bd0a6333f39c0"
BASE_IMAGE = REGISTRY + "@sha256:55cef31147023d09858d5ea104bfbcfac2096b5cc92c9c80bee68480b9362cd6"
BASE_SOURCE_DIGEST = "b3a1bb1e03b55466070f621e71c7a906a146adb093cf558b4e04a067f0694007"
RECEIPTS = "docs/plans/ocean-v1/beta/"
BASE_INVENTORY = RECEIPTS + "b1-20261114/ready-list-production-source-manifest.json"
QUALIFICATION = RECEIPTS + "b2-20261116/qualified-private-candidate.json"
TRANSPORT_QUALIFICATION = RECEIPTS + "b2-20261116/transport-hosted-20261121.json"
DECODE_QUALIFICATION = RECEIPTS + "b2-20261116/decode-hosted-20261121.json"
DISCOVERY_QUALIFICATION = RECEIPTS + "b2-20261116/discovery-hosted-20261122.json"
SUPERSEDED = (
    "api/v1_catalogue_host.py",
    "ingestion/edna_catalogue_inputs.py",
    "ingestion/gcs_catalogue_snapshot.py",
    "orchestration/catalogue_service.py",
    "orchestration/frozen_edna_catalogue.py",
)
TRANSPORT_SUPERSEDED = (*SUPERSEDED, "orchestration/frozen_scientific_catalogue.py")
DISCOVERY_SUPERSEDED = (*TRANSPORT_SUPERSEDED, "ingestion/artifact_store.py", "ingestion/catalogue_adapter_inputs.py")
ADDED = ("ingestion/edna_input_cache.py",)
BINDINGS = {
    "baseline": "/opt/ocean/beta-catalogue-source.json",
    "candidate": "/opt/ocean/beta-b2-catalogue-source.json",
}
BUILDER = "gcr.io/cloud-builders/docker@sha256:fbc05705e6f24467e40ae8a4097ab9b8fae1116551f838fa2c55f4367427fc36"
BUILD_ACCOUNT = f"projects/{PROJECT}/serviceAccounts/ocean-v1-beta-build@{PROJECT}.iam.gserviceaccount.com"


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical(value):
    return (json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n").encode()


def git(*args):
    return subprocess.run(
        ["git", "-C", str(ROOT), *args], check=True, capture_output=True, timeout=30,
    ).stdout


def committed(revision, name, *, current=False):
    path = Path(name)
    if not re.fullmatch(r"[a-zA-Z0-9_./-]+", name) or path.is_absolute() or ".." in path.parts:
        raise ValueError("Expected a repository-relative source path")
    entry = git("ls-tree", revision, "--", name).split()
    if len(entry) != 4 or entry[:2] != [b"100644", b"blob"]:
        raise ValueError(f"Expected a committed regular file: {name}")
    source = git("show", f"{revision}:{name}")
    if current:
        checkout = ROOT / path
        if checkout.resolve() != checkout or checkout.read_bytes() != source:
            raise ValueError(f"Checkout source differs from selected commit: {name}")
    return source


def source_digest(pins):
    return digest(json.dumps(pins, sort_keys=True, separators=(",", ":")).encode())


def binding(activation_sha):
    if type(activation_sha) is not str or not re.fullmatch(r"[0-9a-f]{64}", activation_sha):
        raise ValueError("Expected an exact activation digest")
    return {
        "version": "ocean-v1-gcs-catalogue-host-v1",
        "project_id": PROJECT,
        "site_id": "v1:" + PROJECT,
        "bucket": PROJECT + "-snapshots",
        "prefix": "v1/catalogue",
        "activation_object": f"v1/catalogue/activations/{activation_sha}.json",
        "activation_sha256": activation_sha,
    }


def review_sources(revision, superseded):
    """Reconstruct the 180 original pins and permit exactly the B2 runtime changes."""
    base_paths = json.loads(committed(BASE_REVISION, BASE_INVENTORY))["sources"]
    base_pins = {name: digest(committed(BASE_REVISION, name)) for name in base_paths}
    if len(base_pins) != 180 or source_digest(base_pins) != BASE_SOURCE_DIGEST:
        raise ValueError("The reconstructed B1 source inventory differs from the accepted image")
    git("merge-base", "--is-ancestor", BASE_REVISION, revision)
    pins = {}
    overlays = {}
    for name, original in base_pins.items():
        data = committed(revision, name, current=True)
        pins[name] = digest(data)
        if name in superseded:
            if pins[name] == original:
                raise ValueError(f"Expected B2 supersession missing: {name}")
            overlays[name] = data
        elif pins[name] != original:
            raise ValueError(f"Unreviewed change to inherited runtime source: {name}")
    for name in ADDED:
        if name in pins:
            raise ValueError(f"Expected new runtime path: {name}")
        overlays[name] = committed(revision, name, current=True)
        pins[name] = digest(overlays[name])
    if set(overlays) != set(superseded) | set(ADDED):
        raise ValueError("The runtime overlay inventory is incomplete")
    return pins, overlays


def dockerfile(superseded):
    # Inherit the existing image's user, entrypoint, host settings and default binding.
    lines = ["FROM " + BASE_IMAGE]
    for name in (*superseded, *ADDED):
        lines.append(f"COPY --chown=0:0 --chmod=0444 application/{name} /opt/ocean/{name}")
    lines.extend([
        "COPY --chown=0:0 --chmod=0444 source-manifest.json /opt/ocean/source-manifest.json",
        "COPY --chown=0:0 --chmod=0444 b2-package.json /opt/ocean/b2-package.json",
        "COPY --chown=0:0 --chmod=0444 beta-host-config.json /opt/ocean/beta-host-config.json",
        f"COPY --chown=0:0 --chmod=0444 baseline.json {BINDINGS['baseline']}",
        f"COPY --chown=0:0 --chmod=0444 candidate.json {BINDINGS['candidate']}",
    ])
    return ("\n".join(lines) + "\n").encode()


def build_config(revision, image, proof):
    return {
        "serviceAccount": BUILD_ACCOUNT,
        "timeout": "600s",
        "options": {"logging": "CLOUD_LOGGING_ONLY", "diskSizeGb": 100, "machineType": "E2_STANDARD_2"},
        "steps": [
            {"name": BUILDER, "id": "build-b2-api", "env": ["DOCKER_BUILDKIT=1"],
             "args": ["build", "--platform=linux/amd64", "--tag=" + image,
                      "--label=org.opencontainers.image.revision=" + revision, "."]},
            {"name": BUILDER, "id": "verify-configured-runtime-user", "entrypoint": "sh",
             "args": ["-ec", f'docker image inspect --format "{{{{.Config.User}}}}" {image} | grep -Fx "10001:10001"']},
            {"name": BUILDER, "id": "verify-b2-image-offline",
             "args": ["run", "--rm", "--network=none", "--read-only", "--cap-drop=ALL",
                      "--security-opt=no-new-privileges", "--entrypoint=python", image, "-c", proof]},
        ],
        "images": [image],
    }


def prepare(revision, output):
    if not re.fullmatch(r"[0-9a-f]{40}", revision):
        raise ValueError("Select an exact hosted runtime commit")
    head = git("rev-parse", "HEAD^{commit}").decode().strip()
    receipt_raw = committed(head, QUALIFICATION, current=True)
    receipt = json.loads(receipt_raw)
    runtime_raw = receipt_raw
    runtime_receipt = receipt
    superseded = SUPERSEDED
    for checkpoint, superseded_paths in (
        (TRANSPORT_QUALIFICATION, TRANSPORT_SUPERSEDED),
        (DECODE_QUALIFICATION, TRANSPORT_SUPERSEDED),
        (DISCOVERY_QUALIFICATION, DISCOVERY_SUPERSEDED),
    ):
        if runtime_receipt["source_revision"] == revision:
            break
        preceding_revision = runtime_receipt["source_revision"]
        runtime_raw = committed(head, checkpoint, current=True)
        runtime_receipt = json.loads(runtime_raw)
        if runtime_receipt["supersedes_runtime_revision"] != preceding_revision:
            raise ValueError("Expected an intentional supersession of the preceding qualified runtime")
        superseded = superseded_paths
    if runtime_receipt["source_revision"] != revision or runtime_receipt["hosted"]["conclusion"] != "success":
        raise ValueError("The selected B2 runtime needs accepted hosted checks")
    package_name = Path(__file__).relative_to(ROOT).as_posix()
    package_source = committed(head, package_name, current=True)
    proof_source = committed(head, package_name.replace("prepare_api_context.py", "verify_api_image.py"), current=True)
    pins, overlays = review_sources(revision, superseded)
    old_sha = receipt["base_read_only_selection"]["activation_sha256"]
    new_sha = receipt["private_preparation"]["activation_sha256"]
    if old_sha == new_sha or receipt["private_preparation"]["base_activation_sha256"] != old_sha:
        raise ValueError("Expected distinct, linked baseline and candidate activations")
    bindings = {"baseline": binding(old_sha), "candidate": binding(new_sha)}
    host = {
        "version": "ocean-v1-api-host-v1", "project_id": PROJECT, "site_id": "v1:" + PROJECT,
        "public_origin": "https://beta.oceaninfobio.com", "database_name": "ocean_v1_beta",
        "backend_hosts": ["127.0.0.1:8000"], "allowed_providers": ["google"],
        "internal_issuer": "ocean-v1-frontend", "internal_audience": "ocean-v1-api",
        "revision": revision,
    }
    sources = {"version": "ocean-v1-beta-api-context-v1", "project_id": PROJECT,
               "revision": revision, "sources": pins, "source_manifest_sha256": source_digest(pins)}
    image = REGISTRY + ":b2-" + revision[:12] + "-" + head[:12]
    package = {
        "version": "ocean-beta-b2-api-package-v1", "runtime_revision": revision,
        "packaging_revision": head, "base_revision": BASE_REVISION, "base_image": BASE_IMAGE,
        "base_source_manifest_sha256": BASE_SOURCE_DIGEST, "qualification_sha256": digest(receipt_raw),
        "runtime_qualification_sha256": digest(runtime_raw),
        "packaging_source_sha256": digest(package_source), "image_proof_sha256": digest(proof_source),
        "source_manifest_sha256": sources["source_manifest_sha256"],
        "host_configuration_sha256": digest(canonical(host)), "image_tag": image,
        "superseded_sources": list(superseded), "added_sources": list(ADDED),
        "default_binding": "baseline",
        "bindings": {name: {"path": BINDINGS[name], "sha256": digest(canonical(doc)),
                            "activation_sha256": doc["activation_sha256"]}
                     for name, doc in bindings.items()},
    }
    files = {
        "Dockerfile": dockerfile(superseded), "source-manifest.json": canonical(sources),
        "b2-package.json": canonical(package), "beta-host-config.json": canonical(host),
        "baseline.json": canonical(bindings["baseline"]), "candidate.json": canonical(bindings["candidate"]),
        "cloudbuild.json": canonical(build_config(revision, image, proof_source.decode())),
    }
    files.update({"application/" + path: data for path, data in overlays.items()})
    output = output.absolute()
    if (output.exists() or output.resolve() != output or output.is_relative_to(ROOT)
            or not output.parent.is_dir()):
        raise ValueError("Select a new build context under an existing private directory outside the checkout")
    output.mkdir(mode=0o700)
    for name, raw in files.items():
        target = output / name
        target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(raw)
    return {"package": package, "files": {name: digest(raw) for name, raw in sorted(files.items())}}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--revision", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(canonical(prepare(args.revision, args.output)).decode(), end="")
