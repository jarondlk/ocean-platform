"""Read-only current password source and preserved predecessor verification."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[7]
HERE = Path(__file__).resolve().parent
BASE = HERE.parent


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    receipt = json.loads((HERE / "receipt.json").read_text())
    predecessor = json.loads((HERE / "predecessor.json").read_text())
    for relative, digest in predecessor["source_pins"].items():
        assert sha(HERE / "frozen-756c7a7" / relative) == digest, relative
    for relative, digest in predecessor["receipts"].items():
        assert sha(BASE / relative) == digest, relative
        assert sha(HERE / "frozen-receipts" / relative) == digest, relative
    for relative, digest in receipt["source_pins"].items():
        assert sha(ROOT / relative) == digest, relative
    for relative, digest in receipt["artifact_pins"].items():
        assert sha(HERE / relative) == digest, relative
    native = json.loads((HERE / "native-final-qualified/receipt.json").read_text())
    assert native["state"] == "passed" and len(native["checks"]) == 48
    assert all(check["passed"] for check in native["checks"]) and all(
        native["cleanup"].values()
    )
    assert native["server_log_password_or_verifier_absent"]
    assert (
        native["query_metrics"]["sensitive_material_absent"]
        and not native["query_metrics"]["query_text_exported"]
    )
    assert native["password_logging_policy"]["verified"]
    assert (
        native["password_logging_policy"]["utility_query_collection"][
            "credential_utility_capture"
        ]
        == "disabled"
    )
    for relative, digest in native["source_pins"].items():
        assert sha(ROOT / relative) == digest, relative
    for relative, digest in native["artifacts"].items():
        assert sha(HERE / "native-final-qualified" / relative) == digest, relative
    for folder in ("native-accepted", "native-final", "native-query-qualified"):
        historical = json.loads((HERE / folder / "receipt.json").read_text())
        assert (
            sha(HERE / folder / "operator-source.py")
            == historical["source_pins"]["deploy/gcp/beta/operator/operator.py"]
        )
        assert (
            sha(HERE / folder / "native-harness-source.py")
            == historical["source_pins"][
                str((HERE / "native_rehearsal.py").relative_to(ROOT))
            ]
        )
    assert json.loads((HERE / "checks.json").read_text())["passed"] == 32
    assert (
        json.loads((HERE / "auth-guard-regressions.json").read_text())["passed"] == 26
    )
    print(
        json.dumps(
            {
                "state": "verified_local_only",
                "pure_checks": 32,
                "guard_regressions": 26,
                "native_checks": 48,
                "current_sources": len(receipt["source_pins"]),
                "artifacts": len(receipt["artifact_pins"]),
                "independent_review": receipt["independent_review"],
                "cloud_apply_performed": False,
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
