"""Read-only source and recorded-check verifier for the config-only API layer."""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[6]
DIRECTORY = Path(__file__).resolve().parent


def read(path):
    return json.loads(path.read_text())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify():
    receipt = read(DIRECTORY / "receipt.json")
    for group in ("source_pins", "artifact_pins", "predecessor_metadata_pins"):
        for name, expected in receipt[group].items():
            path = ROOT / name
            assert path.resolve().is_relative_to(ROOT) and path.is_file()
            assert not path.is_symlink()
            assert sha(path) == expected, name
    package = ROOT / "deploy/gcp/beta/serving-api"
    spec = importlib.util.spec_from_file_location(
        "serving_api_validation", package / "prepare_context.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.validate_configuration((package / "api-host-config.json").read_bytes())
    module.validate_dockerfile((package / "Dockerfile").read_bytes())
    assert len(receipt["source_pins"]) == 3
    checks = read(DIRECTORY / "checks.json")
    assert checks["checks_passed"] == len(checks["checks"]) == 26
    assert len(set(checks["checks"])) == 26
    assert not checks["cloud_calls_performed"]
    assert not checks["image_build_or_linux_file_proof_performed"]
    c27 = read(ROOT / "docs/plans/ocean-v1/evidence/C27/release-manifest.json")
    overlay = read(
        ROOT / "docs/plans/ocean-v1/beta/checkpoint-20261102/source-supersession.json"
    )
    effective = {
        **c27["source"]["source_files"],
        **{entry["path"]: entry["to_sha256"] for entry in overlay["supersessions"]},
        **overlay["additive_app_sha256"],
    }
    assert len(effective) == receipt["preservation"]["application_source_paths"] == 880
    for name, expected in effective.items():
        assert sha(ROOT / name) == expected, name
    proposal = ROOT / "docs/plans/ocean-v1/beta/hosting-plan-20261102"
    inputs = read(proposal / "inspected-inputs.json")
    assert (
        len(inputs["sha256"])
        == receipt["preservation"]["hosting_inspected_inputs"]
        == 17
    )
    for name, expected in inputs["sha256"].items():
        assert sha(ROOT / name) == expected, name
    for name, expected in read(proposal / "artifacts.json")["sha256"].items():
        assert sha(proposal / name) == expected, name
    assert not receipt["cloud_calls_performed"] and not receipt["image_built"]
    assert receipt["successful_committed_context_export"] == "pending source checkpoint"
    return {
        "verified": True,
        "source_paths": 3,
        "pure_checks_passed": 26,
        "application_paths_unchanged": 880,
        "hosting_inputs_and_proposal_preserved": True,
        "successful_committed_export": "pending root checkpoint",
        "linux_configured_file_and_image_proof": "pending actual build",
        "cloud_actions_performed": False,
    }


if __name__ == "__main__":
    print(json.dumps(verify(), indent=2))
