"""Cloud Build executes this proof inside the candidate image with networking disabled."""

import hashlib
import json
import os
from pathlib import Path
import stat


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def read_owned(path):
    info = path.stat()
    assert not path.is_symlink() and stat.S_ISREG(info.st_mode), path
    assert info.st_uid == 0 and stat.S_IMODE(info.st_mode) == 0o444, path
    return path.read_bytes()


def verify():
    root = Path("/opt/ocean")
    assert (os.geteuid(), os.getegid()) == (10001, 10001)
    package = json.loads(read_owned(root / "b2-package.json"))
    sources = json.loads(read_owned(root / "source-manifest.json"))
    pins = sources["sources"]
    assert len(pins) == 181 and sources["revision"] == package["runtime_revision"]
    assert digest(json.dumps(pins, sort_keys=True, separators=(",", ":")).encode()) == (
        package["source_manifest_sha256"]
    )
    host = read_owned(root / "beta-host-config.json")
    assert digest(host) == package["host_configuration_sha256"]
    assert json.loads(host)["revision"] == sources["revision"]

    build_only = {
        "deploy/gcp/beta/api/Dockerfile", "deploy/gcp/beta/api/prepare_context.py",
        "requirements/runtime.txt",
    }
    overlays = set(package["superseded_sources"]) | set(package["added_sources"])
    for name, expected in pins.items():
        if name in build_only:
            continue
        path = root / ("beta_entry.py" if name == "deploy/gcp/beta/api/entry.py" else name)
        raw = read_owned(path) if name in overlays else path.read_bytes()
        assert digest(raw) == expected, name

    assert package["default_binding"] == "baseline"
    assert set(package["bindings"]) == {"baseline", "candidate"}
    assert os.environ["OCEAN_V1_CATALOGUE_CONFIG"] == package["bindings"]["baseline"]["path"]
    for entry in package["bindings"].values():
        raw = read_owned(Path(entry["path"]))
        assert digest(raw) == entry["sha256"]
        doc = json.loads(raw)
        assert doc == {
            "version": "ocean-v1-gcs-catalogue-host-v1", "project_id": sources["project_id"],
            "site_id": "v1:" + sources["project_id"], "bucket": sources["project_id"] + "-snapshots",
            "prefix": "v1/catalogue", "activation_sha256": entry["activation_sha256"],
            "activation_object": "v1/catalogue/activations/" + entry["activation_sha256"] + ".json",
        }
    assert package["bindings"]["baseline"]["activation_sha256"] != package["bindings"]["candidate"]["activation_sha256"]
    assert not (root / "data").exists() and not (root / "activation.json").exists()

    from api.v1_beta_question_entry import main as serving_entrypoint
    from api.v1_research_controller_host import create_from_environment as create_controller
    from ingestion.edna_input_cache import ValidatedEDNAInputCache

    assert callable(serving_entrypoint) and callable(create_controller)
    assert ValidatedEDNAInputCache().stats()["entries"] == 0
    print("Verified B2 image runtime source pins, both activation bindings, nonroot user and serving/controller imports")


if __name__ == "__main__":
    verify()
