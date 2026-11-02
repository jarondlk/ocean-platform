"""Pure config/guard checks only; no cloud, credentials, image or database."""

from __future__ import annotations

import ast
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import tempfile

ROOT = Path(__file__).resolve().parents[6]
PACKAGE = ROOT / "deploy/gcp/beta/serving-api"


def run():
    spec = importlib.util.spec_from_file_location(
        "serving_api_context", PACKAGE / "prepare_context.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    checks = []

    def reject(name, operation):
        try:
            operation()
        except ValueError:
            checks.append(name)
        else:
            raise AssertionError(name)

    ast.parse((PACKAGE / "prepare_context.py").read_text())
    checks.append("packager_python_parses")
    config = (PACKAGE / "api-host-config.json").read_bytes()
    dockerfile = (PACKAGE / "Dockerfile").read_bytes()
    module.validate_configuration(config)
    module.validate_dockerfile(dockerfile)
    checks.extend(
        ["canonical_exact_config_accepted", "exact_config_only_dockerfile_accepted"]
    )
    assert (
        config
        == (
            ROOT / "docs/plans/ocean-v1/beta/hosting-plan-20261102/api-host-config.json"
        ).read_bytes()
    )
    checks.append("config_equals_frozen_hosting_proposal")
    for field, replacement in [
        ("revision", "0" * 40),
        ("project_id", "data-infra-infobio"),
        ("backend_hosts", ["0.0.0.0:8000"]),
        ("allowed_providers", ["oidc"]),
        ("internal_audience", "legacy"),
        ("public_origin", "https://oceaninfobio.com"),
    ]:
        modified = deepcopy(module.EXPECTED_CONFIG)
        modified[field] = replacement
        raw = (json.dumps(modified, sort_keys=True, indent=2) + "\n").encode()
        reject(
            "config_rejects_" + field,
            lambda raw=raw: module.validate_configuration(raw),
        )
    reject(
        "duplicate_json_key_rejected",
        lambda: module.validate_configuration(b'{"version":1,"version":2}'),
    )
    reject(
        "noncanonical_config_rejected",
        lambda: module.validate_configuration(
            json.dumps(module.EXPECTED_CONFIG).encode()
        ),
    )
    modified = {**module.EXPECTED_CONFIG, "unexpected": True}
    reject(
        "extra_config_key_rejected",
        lambda: module.validate_configuration(json.dumps(modified).encode()),
    )
    reject(
        "oversize_config_rejected", lambda: module.validate_configuration(b" " * 65537)
    )
    for name, addition in [
        ("run", b"\nRUN false\n"),
        ("user", b"\nUSER 0\n"),
        ("entrypoint", b'\nENTRYPOINT ["false"]\n'),
        ("cmd", b'\nCMD ["false"]\n'),
    ]:
        reject(
            "dockerfile_rejects_" + name,
            lambda addition=addition: module.validate_dockerfile(dockerfile + addition),
        )
    reject(
        "dockerfile_rejects_alternate_base",
        lambda: module.validate_dockerfile(
            dockerfile.replace(b"api@sha256:f2", b"api@sha256:02")
        ),
    )
    with tempfile.TemporaryDirectory(
        prefix="ocean-serving-config-check-", dir="/private/tmp"
    ) as temporary:
        directory = Path(temporary)
        base = {
            "revision": "756c7a7dc46d4ba75e3a0308b7ab23d9b3553bfe",
            "api_revision": module.API_REVISION,
            "api_image": module.API_IMAGE,
            "output": directory / "not-created",
        }
        for name, values in [
            ("short_revision_rejected", {"revision": "main"}),
            ("base_revision_as_new_rejected", {"revision": module.API_REVISION}),
            ("different_api_source_rejected", {"api_revision": "0" * 40}),
            (
                "different_base_digest_rejected",
                {"api_image": module.API_IMAGE[:-1] + "0"},
            ),
        ]:
            reject(name, lambda values=values: module.prepare(**{**base, **values}))
        reject(
            "old_commit_cannot_export_uncommitted_package",
            lambda: module.prepare(**base),
        )
        assert not base["output"].exists()
        checks.append("all_rejections_before_output_creation")
        existing = directory / "existing"
        existing.mkdir()
        reject(
            "existing_output_rejected",
            lambda: module.prepare(**{**base, "output": existing}),
        )
    return {
        "version": "beta-serving-api-static-checks-v1",
        "checks_passed": len(checks),
        "checks": checks,
        "successful_committed_context_export": "pending source checkpoint; not claimed by pre-commit checks",
        "cloud_calls_performed": False,
        "database_or_native_run_performed": False,
        "image_build_or_linux_file_proof_performed": False,
        "owned_temporary_directory_removed": True,
    }


if __name__ == "__main__":
    print(json.dumps(run(), indent=2))
