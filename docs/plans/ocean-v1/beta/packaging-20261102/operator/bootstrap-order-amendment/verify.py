"""Verify inspection-only readiness and immutable historical source mappings."""

from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[7]
HERE = Path(__file__).resolve().parent
OPERATOR = ROOT / "deploy/gcp/beta/operator/operator.py"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def check_pins(record, *, source_override=None, artifact_base=None):
    for relative, digest in record["source_pins"].items():
        path = (source_override or {}).get(relative, ROOT / relative)
        assert sha(path) == digest, relative
    for relative, digest in record.get("artifacts", {}).items():
        assert sha(artifact_base / relative) == digest, relative


def main():
    receipt = json.loads((HERE / "inspection-readiness.json").read_text())
    predecessor = json.loads((HERE / "predecessor.json").read_text())
    assert receipt["permitted_next_stages"] == ["readback", "qualify"]
    assert receipt["bootstrap_authorized"] is False
    assert receipt["managed_cloudsql_qualification_claimed"] is False
    assert receipt["ordering_success_qualified"] is False
    assert receipt["cloud_actions"] is False
    assert sha(HERE / "operator.before.py") == predecessor["operator_sha256"]
    assert (
        sha(HERE / "password-safety-receipt.before.json")
        == predecessor["password_safety_receipt_sha256"]
    )
    assert (
        sha(HERE.parent / "password-safety-amendment/receipt.json")
        == predecessor["password_safety_receipt_sha256"]
    )
    check_pins(receipt)
    for relative, digest in receipt["artifact_pins"].items():
        assert sha(HERE / relative) == digest, relative
    prepared = json.loads((HERE / "receipt.json").read_text())
    assert (HERE / "receipt.json").read_bytes() == (
        HERE / "frozen-preparation/receipt.json"
    ).read_bytes()
    override = {
        str((HERE / name).relative_to(ROOT)): HERE / "frozen-preparation" / name
        for name in ("README.md", "verify.py")
    }
    check_pins(prepared, source_override=override)
    for relative, digest in prepared["artifact_pins"].items():
        assert sha(HERE / relative) == digest, relative
    assert prepared["native_qualifications"] == {}
    # The accepted predecessor qualification remains bound to its old operator.
    historical_dir = HERE.parent / "password-safety-amendment/native-final-qualified"
    historical = json.loads((historical_dir / "receipt.json").read_text())
    assert historical["state"] == "passed" and len(historical["checks"]) == 48
    assert all(item["passed"] for item in historical["checks"]) and all(
        historical["cleanup"].values()
    )
    old_operator = {str(OPERATOR.relative_to(ROOT)): HERE / "operator.before.py"}
    check_pins(historical, source_override=old_operator, artifact_base=historical_dir)
    failed_dir = HERE / "native-root-20261102"
    failed = json.loads((failed_dir / "receipt.json").read_text())
    assert failed["state"] == "failed" and failed["failure_type"] == "OperatorError"
    assert all(failed["cleanup"].values())
    check_pins(
        failed,
        source_override={
            str(OPERATOR.relative_to(ROOT)): HERE / "operator.ordering-candidate.py"
        },
        artifact_base=failed_dir,
    )
    assert sha(failed_dir / "native-harness-source.py") == sha(
        HERE / "native_rehearsal.py"
    )
    for file, count in (
        ("probe-checks.json", 20),
        ("password-guard-regressions.json", 32),
        ("auth-guard-regressions.json", 26),
    ):
        assert json.loads((HERE / file).read_text())["passed"] == count, file
    native_dir = HERE / receipt["native_qualifications"]["other-grantor"]
    observed = json.loads((native_dir / "receipt.json").read_text())
    assert observed["state"] == "passed" and observed["profile"] == "other-grantor"
    assert len(observed["checks"]) == 20 and all(
        item["passed"] for item in observed["checks"]
    )
    assert (
        all(observed["cleanup"].values()) and observed["server_log_exported"] is False
    )
    assert observed["probe_observation"]["bootstrap_authorized"] is False
    assert observed["probe_observation"]["sequence_supported"] is False
    assert observed["probe_observation"]["probe_absent_after_rollback"] is True
    assert (
        observed["old_order"]["outcome"]
        == observed["corrected_order"]["outcome"]
        == "refused"
    )
    check_pins(observed, artifact_base=native_dir)
    assert sha(native_dir / "native-harness-source.py") == sha(
        HERE / "probe_native_rehearsal.py"
    )
    unsupported_dir = HERE / "native-probe-self-20261102"
    unsupported = json.loads((unsupported_dir / "receipt.json").read_text())
    assert (
        unsupported["state"] == "failed"
        and unsupported["failure_type"] == "NotSupportedError"
    )
    assert (
        "provider_before" not in unsupported and "probe_observation" not in unsupported
    )
    assert len(unsupported["checks"]) == 2 and all(
        item["passed"] for item in unsupported["checks"]
    )
    assert all(unsupported["cleanup"].values())
    check_pins(unsupported, artifact_base=unsupported_dir)
    assert sha(unsupported_dir / "native-harness-source.py") == sha(
        HERE / "probe_native_rehearsal.py"
    )
    security = json.loads((HERE / "preserved-security-functions.json").read_text())
    current, old = OPERATOR.read_text(), (HERE / "operator.before.py").read_text()

    def segments(source):
        values = {}
        for node in ast.parse(source).body:
            if isinstance(node, ast.FunctionDef):
                values[node.name] = ast.get_source_segment(source, node)
            if isinstance(node, ast.Assign) and any(
                isinstance(target, ast.Name) and target.id == "PASSWORD_LOGGING_POLICY"
                for target in node.targets
            ):
                values["PASSWORD_LOGGING_POLICY"] = ast.get_source_segment(source, node)
        return values

    current_segments, old_segments = segments(current), segments(old)
    for name, value in security["functions"].items():
        assert current_segments[name] == old_segments[name]
        assert (
            hashlib.sha256(current_segments[name].encode()).hexdigest()
            == value["sha256"]
        )
    print(
        json.dumps(
            {
                "state": receipt["state"],
                "permitted_next_stages": receipt["permitted_next_stages"],
                "probe_checks": 20,
                "password_regressions": 32,
                "auth_proxy_regressions": 26,
                "new_native_checks": 20,
                "native_supported_bootstrap_qualified": False,
                "managed_provider_qualification": "pending actual private rollback-only job",
                "bootstrap_authorized": False,
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
