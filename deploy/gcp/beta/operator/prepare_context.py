"""Prepare only committed operator code atop an explicitly immutable beta API."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[4]
HERE = Path(__file__).resolve().parent
IMAGE_PATTERN = r"asia-northeast1-docker\.pkg\.dev/ocean-v1-beta-20261101/ocean-v1-beta/api@sha256:[a-f0-9]{64}"


def prepare(*, output, revision, api_image, api_revision):
    if (
        not re.fullmatch(r"[a-f0-9]{40}", revision)
        or not re.fullmatch(r"[a-f0-9]{40}", api_revision)
        or not re.fullmatch(IMAGE_PATTERN, api_image)
    ):
        raise ValueError(
            "Explicit committed operator, API source and immutable beta API digest required"
        )
    if output.exists() or output.is_symlink():
        raise ValueError("Context output must not already exist")
    sources = {}
    for name in ("Dockerfile", "operator.py", "prepare_context.py"):
        path = HERE / name
        relative = path.relative_to(ROOT).as_posix()
        accepted = subprocess.run(
            ["git", "show", revision + ":" + relative],
            cwd=ROOT,
            capture_output=True,
            check=True,
        ).stdout
        if path.is_symlink() or path.read_bytes() != accepted:
            raise ValueError("Operator source differs from the explicit commit")
        sources[name] = accepted
    manifest = {
        "version": "ocean-v1-beta-operator-context-v1",
        "project_id": "ocean-v1-beta-20261101",
        "revision": revision,
        "api_revision": api_revision,
        "api_image": api_image,
        "source_pins": {
            name: hashlib.sha256(value).hexdigest()
            for name, value in sorted(sources.items())
        },
        "image_build_performed": False,
    }
    output.mkdir(parents=True)
    for name in ("Dockerfile", "operator.py"):
        (output / name).write_bytes(sources[name])
    (output / "operator-manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n"
    )
    print(
        json.dumps(
            {
                "output": str(output),
                "api_image": api_image,
                "revision": revision,
                "api_revision": api_revision,
                "source_count": len(sources),
            }
        )
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--revision", required=True)
    parser.add_argument("--api-image", required=True)
    parser.add_argument("--api-revision", required=True)
    args = parser.parse_args()
    prepare(
        output=args.output.absolute(),
        revision=args.revision,
        api_image=args.api_image,
        api_revision=args.api_revision,
    )
