"""Byte-pin amendment and historical source supersessions; read-only verification."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[7]
HERE = Path(__file__).resolve().parent
PACKAGE = ROOT / "deploy/gcp/beta/operator/operator.py"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    receipt = json.loads((HERE / "receipt.json").read_text())
    predecessor = json.loads((HERE / "predecessor.json").read_text())
    assert sha(HERE / "operator.before.py") == predecessor["operator_sha256"]
    assert (
        sha(HERE / "password-safety-receipt.before.json")
        == predecessor["password_safety_receipt_sha256"]
    )
    assert (
        sha(HERE.parent / "password-safety-amendment/receipt.json")
        == predecessor["password_safety_receipt_sha256"]
    )
    for relative, digest in receipt["source_pins"].items():
        assert sha(ROOT / relative) == digest, relative
    for relative, digest in receipt["artifact_pins"].items():
        assert sha(HERE / relative) == digest, relative
    # Historical accepted privacy qualification remains tied to its old operator.
    historical = json.loads(
        (
            HERE.parent
            / "password-safety-amendment/native-final-qualified/receipt.json"
        ).read_text()
    )
    assert historical["state"] == "passed" and len(historical["checks"]) == 48
    for relative, digest in historical["source_pins"].items():
        path = (
            HERE / "operator.before.py"
            if relative == str(PACKAGE.relative_to(ROOT))
            else ROOT / relative
        )
        assert sha(path) == digest, relative
    for relative, digest in historical["artifacts"].items():
        assert (
            sha(
                HERE.parent
                / "password-safety-amendment/native-final-qualified"
                / relative
            )
            == digest
        ), relative
    failed = json.loads((HERE / "native-root-20261102/receipt.json").read_text())
    assert failed["state"] == "failed" and failed["failure_type"] == "OperatorError"
    assert all(failed["cleanup"].values())
    for relative, digest in failed["source_pins"].items():
        path = (
            HERE / "operator.ordering-candidate.py"
            if relative == str(PACKAGE.relative_to(ROOT))
            else ROOT / relative
        )
        assert sha(path) == digest, relative
    for relative, digest in failed["artifacts"].items():
        assert sha(HERE / "native-root-20261102" / relative) == digest, relative
    assert sha(HERE / "native-root-20261102/native-harness-source.py") == sha(
        HERE / "native_rehearsal.py"
    )
    for file, count in (
        ("probe-checks.json", 20),
        ("password-guard-regressions.json", 32),
        ("auth-guard-regressions.json", 26),
    ):
        assert json.loads((HERE / file).read_text())["passed"] == count, file
    native_count = 0
    for profile, folder in receipt["native_qualifications"].items():
        observed = json.loads((HERE / folder / "receipt.json").read_text())
        assert observed["state"] == "passed" and observed["profile"] == profile
        assert all(item["passed"] for item in observed["checks"])
        assert all(observed["cleanup"].values())
        assert (
            not observed["cloud_actions"]
            and not observed["managed_cloudsql_qualification_claimed"]
        )
        assert not observed["probe_observation"]["bootstrap_authorized"]
        assert observed["probe_observation"]["sequence_supported"] == (
            profile == "self-grantor"
        )
        for relative, digest in observed["source_pins"].items():
            assert sha(ROOT / relative) == digest, relative
        for relative, digest in observed["artifacts"].items():
            assert sha(HERE / folder / relative) == digest, relative
        native_count += len(observed["checks"])
    print(
        json.dumps(
            {
                "state": receipt["state"],
                "probe_checks": 20,
                "password_regressions": 32,
                "auth_proxy_regressions": 26,
                "native_profiles": len(receipt["native_qualifications"]),
                "native_checks": native_count,
                "managed_provider_qualification": "pending actual private job",
                "bootstrap_authorized": False,
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
