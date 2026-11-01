"""Read-only beta source overlay and immutable predecessor evidence verification."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[5]
DIRECTORY = Path(__file__).resolve().parent


def read(path):
    return json.loads(path.read_text())


def safe(name):
    path = ROOT / name
    assert path.parent.resolve().is_relative_to(ROOT) and path.is_file(), name
    return path


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify():
    source = read(DIRECTORY / "source-supersession.json")
    preservation = read(DIRECTORY / "preservation.json")
    assert source["version"] == "beta-host-source-supersession-v1"
    assert preservation["version"] == "beta-predecessor-preservation-v1"
    for entry in preservation["predecessor_sources"].values():
        assert sha(safe(entry["path"])) == entry["sha256"], entry["path"]
    pinned = preservation["predecessor_sources"]
    predecessor = read(safe(pinned["c27_release_manifest"]["path"]))
    old = predecessor["source"]["source_files"]
    assert len(old) == source["predecessor_runtime_paths"] == 844
    changes = {entry["path"]: entry for entry in source["supersessions"]}
    assert set(changes) == {
        ".github/workflows/tests.yml", "frontend-v1/src/runtime-app.tsx",
        "frontend-v1/tsconfig.json",
    }
    for name, expected in old.items():
        if name in changes:
            assert changes[name]["from_sha256"] == expected, name
            expected = changes[name]["to_sha256"]
        assert sha(safe(name)) == expected, name
    assert len(old) - len(changes) == source["unchanged_predecessor_runtime_paths"] == 841
    additive = source["additive_app_sha256"]
    assert len(additive) == 36 and not set(additive).intersection(old)
    for name, expected in additive.items():
        assert sha(safe(name)) == expected, name
    ignored = subprocess.run(
        ["git", "check-ignore", "--stdin"], cwd=ROOT, input="\n".join(additive) + "\n",
        text=True, capture_output=True, check=False,
    )
    assert ignored.returncode in {0, 1} and not ignored.stdout.strip(), ignored.stdout
    effective = {**old, **{name: entry["to_sha256"] for name, entry in changes.items()}, **additive}
    identity = "sha256:" + hashlib.sha256(
        json.dumps(effective, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    assert identity == source["composed_source_revision"]
    start = read(safe(pinned["c27_readiness_start"]["path"]))
    assert preservation["protected_sha256"] == start["protected_sha256"]
    for name, expected in preservation["protected_sha256"].items():
        assert sha(safe(name)) == expected, name
    entries = start["prior_evidence_files"]
    for name, entry in entries.items():
        path = safe("docs/plans/ocean-v1/evidence/" + name)
        if entry["mode"] == "120000":
            assert path.is_symlink(), name
            raw = os.readlink(path).encode()
        else:
            assert entry["mode"] in {"100644", "100755"} and not path.is_symlink(), name
            raw = path.read_bytes()
        blob = hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()
        assert blob == entry["git_blob"], name
    package = read(safe(pinned["c27_package_manifest"]["path"]))["sha256"]
    for name, expected in package.items():
        assert sha(safe(name)) == expected, name
    assert len(entries) == preservation["prior_evidence_files_preserved"] == 5368
    assert len(package) == preservation["c27_package_artifacts_preserved"] == 90
    assert len(start["protected_sha256"]) == preservation["protected_paths_preserved"] == 42
    assert not source["live_release_accepted"] and not preservation["release_accepted"]
    return {
        "verified": True, "unchanged_predecessor_source_paths": 841,
        "intentional_source_supersessions": 3, "additive_source_paths": len(additive),
        "composed_source_revision": identity, "preserved_evidence_files": len(entries),
        "preserved_c27_package_artifacts": len(package), "protected_paths": 42,
        "hosted_ci_for_new_source": "separate_delivery_receipt_required",
        "live_release_accepted": False,
    }


if __name__ == "__main__":
    print(json.dumps(verify(), indent=2))
