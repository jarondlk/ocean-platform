"""Export a committed configuration-only layer over one exact beta API image."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[4]
HERE = Path(__file__).resolve().parent
PROJECT = "ocean-v1-beta-20261101"
API_REVISION = "7924a28e919b1fb751890c694f7b1f9b26b104ff"
API_IMAGE = (
    "asia-northeast1-docker.pkg.dev/" + PROJECT + "/ocean-v1-beta/api@"
    "sha256:f2e73ca98ba915e29a4dd7dc429e34a165475faa7f9000bc8cefaa10e5a6ee4f"
)
CONFIG_PATH = "/opt/ocean/beta-host-config.json"
SOURCE_NAMES = ("Dockerfile", "api-host-config.json", "prepare_context.py")
EXPECTED_CONFIG = {
    "version": "ocean-v1-api-host-v1",
    "project_id": PROJECT,
    "site_id": "v1:" + PROJECT,
    "revision": API_REVISION,
    "public_origin": "https://beta.oceaninfobio.com",
    "database_name": "ocean_v1_beta",
    "backend_hosts": ["127.0.0.1:8000"],
    "allowed_providers": ["google"],
    "internal_issuer": "ocean-v1-frontend",
    "internal_audience": "ocean-v1-api",
}


def git(*args):
    result = subprocess.run(
        ["git", "-C", str(ROOT), *args],
        check=False,
        capture_output=True,
    )
    if result.returncode:
        raise ValueError("Committed serving configuration source is unavailable")
    return result.stdout


def unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate configuration key")
        result[key] = value
    return result


def validate_configuration(data):
    if not isinstance(data, bytes) or len(data) > 65536:
        raise ValueError("Bounded canonical non-secret API configuration required")
    try:
        document = json.loads(data.decode("utf-8"), object_pairs_hook=unique)
    except (UnicodeError, ValueError):
        raise ValueError("Canonical independent API configuration required") from None
    canonical = (json.dumps(EXPECTED_CONFIG, indent=2, sort_keys=True) + "\n").encode()
    if document != EXPECTED_CONFIG or data != canonical:
        raise ValueError(
            "API configuration must match the exact reviewed base source and identity"
        )


def validate_dockerfile(data):
    expected = [
        "FROM " + API_IMAGE,
        "COPY --chown=0:0 --chmod=0444 api-host-config.json " + CONFIG_PATH,
        "COPY --chown=0:0 --chmod=0444 serving-manifest.json /opt/ocean/serving-manifest.json",
        "ENV OCEAN_V1_HOST_CONFIG=" + CONFIG_PATH,
    ]
    try:
        instructions = [
            line.strip()
            for line in data.decode("utf-8").splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        ]
    except UnicodeError:
        raise ValueError("Exact configuration-only Dockerfile required") from None
    if instructions != expected:
        raise ValueError(
            "Only the reviewed immutable base and read-only configuration copies are allowed"
        )


def read_committed_sources(revision):
    sources = {}
    for name in SOURCE_NAMES:
        path = HERE / name
        relative = path.relative_to(ROOT).as_posix()
        listing = git("ls-tree", revision, "--", relative).decode().split()
        if len(listing) != 4 or listing[0] != "100644" or listing[1] != "blob":
            raise ValueError("Committed regular configuration package sources required")
        accepted = git("show", revision + ":" + relative)
        if path.is_symlink() or not path.is_file() or path.read_bytes() != accepted:
            raise ValueError(
                "Serving configuration source differs from the explicit commit"
            )
        sources[name] = accepted
    validate_dockerfile(sources["Dockerfile"])
    validate_configuration(sources["api-host-config.json"])
    return sources


def prepare(*, revision, api_revision, api_image, output):
    if (
        not re.fullmatch(r"[a-f0-9]{40}", revision)
        or revision == API_REVISION
        or api_revision != API_REVISION
        or api_image != API_IMAGE
    ):
        raise ValueError(
            "Explicit new committed revision and exact accepted base API are required"
        )
    output = output.absolute()
    if (
        output.exists()
        or output.is_symlink()
        or any(parent.is_symlink() for parent in output.parents)
    ):
        raise ValueError("Output must be a new non-symlink directory")
    if (
        git("rev-parse", "--verify", revision + "^{commit}").decode().strip()
        != revision
    ):
        raise ValueError("Explicit source commit mismatch")
    git("merge-base", "--is-ancestor", API_REVISION, revision)
    sources = read_committed_sources(revision)
    pins = {
        name: hashlib.sha256(data).hexdigest() for name, data in sorted(sources.items())
    }
    manifest = {
        "version": "ocean-v1-beta-serving-api-context-v1",
        "project_id": PROJECT,
        "revision": revision,
        "base_api_revision": API_REVISION,
        "base_api_image": API_IMAGE,
        "api_host_config_path": CONFIG_PATH,
        "api_host_config_sha256": pins["api-host-config.json"],
        "source_pins": pins,
        "base_source_manifest_unchanged": True,
        "inherited_runtime_user": "10001:10001",
        "entrypoint_cmd_and_listener_unchanged": True,
        "credentials_or_scientific_data_included": False,
        "image_build_performed": False,
    }
    raw_manifest = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode()
    # Validate all inputs before creating the caller's new output directory.
    output.mkdir(parents=True, exist_ok=False)
    for name in ("Dockerfile", "api-host-config.json"):
        (output / name).write_bytes(sources[name])
    (output / "serving-manifest.json").write_bytes(raw_manifest)
    return {
        "revision": revision,
        "base_api_revision": API_REVISION,
        "base_api_image": API_IMAGE,
        "context_files": [
            "Dockerfile",
            "api-host-config.json",
            "serving-manifest.json",
        ],
        "manifest_sha256": hashlib.sha256(raw_manifest).hexdigest(),
        "api_host_config_sha256": pins["api-host-config.json"],
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--revision", required=True)
    parser.add_argument("--api-revision", required=True)
    parser.add_argument("--api-image", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(
        json.dumps(
            prepare(
                revision=args.revision,
                api_revision=args.api_revision,
                api_image=args.api_image,
                output=args.output,
            ),
            indent=2,
        )
    )
