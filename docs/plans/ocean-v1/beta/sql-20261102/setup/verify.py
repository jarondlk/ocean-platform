"""Read-only hashes and pure setup logic checks; never applies GCP changes."""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[6]
HERE = Path(__file__).resolve().parent


def main():
    receipt = json.loads((HERE / "receipt.json").read_text())
    for relative, digest in receipt["source_pins"].items():
        assert hashlib.sha256((ROOT / relative).read_bytes()).hexdigest() == digest, (
            relative
        )
    for relative, digest in receipt["artifact_pins"].items():
        assert hashlib.sha256((HERE / relative).read_bytes()).hexdigest() == digest, (
            relative
        )
    spec = importlib.util.spec_from_file_location(
        "beta_setup_checks", HERE / "checks.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    result, _ = module.run()
    assert (
        result["passed"] == 50
        and not result["live_cloud_calls"]
        and not result["real_secret_or_token_generation"]
    )
    print(
        json.dumps(
            {
                "state": "verified_local_only",
                "checks": result["passed"],
                "source_pins": len(receipt["source_pins"]),
                "artifact_pins": len(receipt["artifact_pins"]),
                "independent_review": receipt["independent_review"],
                "cloud_apply_performed": False,
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
