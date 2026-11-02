"""Export committed exact context-grant code only, without credentials or cloud."""
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
BASE_OPERATOR_REVISION = "8e2a1630d5d2a7028495ec7b56a422a38b1c0807"
BASE_OPERATOR_IMAGE = ("asia-northeast1-docker.pkg.dev/" + PROJECT + "/ocean-v1-beta/operator@sha256:"
    "0a89057b7459342e191e4b194628bee00cc7544749489df9f85f31508399e7b3")


def prepare(*, revision, output):
    output = Path(output)
    if (not re.fullmatch(r"[a-f0-9]{40}", revision) or not output.is_absolute()
            or output.exists() or output.is_symlink()):
        raise ValueError("Explicit committed source and new absolute context required")
    sources = {}
    for name in ("Dockerfile", "context_operator.py", "prepare_context.py"):
        path = HERE / name
        relative = path.relative_to(ROOT).as_posix()
        accepted = subprocess.check_output(["git", "show", revision + ":" + relative], cwd=ROOT)
        if path.is_symlink() or path.read_bytes() != accepted:
            raise ValueError("Context operator source differs from explicit commit")
        sources[name] = accepted
    # The grant-plan constants must agree with the reviewed context composition.
    helper = "api/v1_beta_research_host.py"
    helper_bytes = subprocess.check_output(["git", "show", revision + ":" + helper], cwd=ROOT)
    if (ROOT / helper).is_symlink() or (ROOT / helper).read_bytes() != helper_bytes:
        raise ValueError("Context application privilege contract differs from explicit commit")
    manifest = {"version": "ocean-v1-beta-context-operator-v1", "project_id": PROJECT,
        "revision": revision, "base_operator_revision": BASE_OPERATOR_REVISION,
        "base_operator_image": BASE_OPERATOR_IMAGE,
        "source_pins": {name: hashlib.sha256(value).hexdigest() for name, value in sorted(sources.items())},
        "context_contract": {"path": helper, "sha256": hashlib.sha256(helper_bytes).hexdigest()},
        "credentials_or_scientific_data_included": False}
    output.mkdir(parents=True)
    for name in ("Dockerfile", "context_operator.py"):
        (output / name).write_bytes(sources[name])
    (output / "context-operator-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return {"state": "context_operator_source_prepared", "revision": revision,
        "base_operator_image": BASE_OPERATOR_IMAGE, "cloud_calls": False, "credentials_included": False}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--revision", required=True)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    print(json.dumps(prepare(revision=args.revision, output=args.output)))
