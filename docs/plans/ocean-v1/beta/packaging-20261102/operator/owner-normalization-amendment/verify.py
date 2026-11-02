"""Read-only owner-stage evidence and explicit predecessor-source verification."""

from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[7]
HERE = Path(__file__).resolve().parent
OPERATOR = ROOT / "deploy/gcp/beta/operator/operator.py"
INSPECTION = HERE.parent / "bootstrap-order-amendment"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    receipt = json.loads((HERE / "receipt.json").read_text())
    predecessor = json.loads((HERE / "predecessor.json").read_text())
    assert sha(HERE / "operator.before.py") == predecessor["operator_sha256"]
    assert (
        sha(HERE / "inspection-readiness.before.json")
        == predecessor["inspection_readiness_sha256"]
    )
    assert (
        sha(INSPECTION / "inspection-readiness.json")
        == predecessor["inspection_readiness_sha256"]
    )
    for relative, digest in receipt["source_pins"].items():
        assert sha(ROOT / relative) == digest, relative
    for relative, digest in receipt["artifact_pins"].items():
        assert sha(HERE / relative) == digest, relative
    for relative, digest in receipt["external_evidence_pins"].items():
        assert sha(ROOT / relative) == digest, relative
    # Do not retarget the previous inspection's operator pin to amended source.
    old = json.loads((HERE / "inspection-readiness.before.json").read_text())
    for relative, digest in old["source_pins"].items():
        path = (
            HERE / "operator.before.py"
            if relative == str(OPERATOR.relative_to(ROOT))
            else ROOT / relative
        )
        assert sha(path) == digest, relative
    for relative, digest in old["artifact_pins"].items():
        assert sha(INSPECTION / relative) == digest, relative
    checks = json.loads((HERE / "checks.json").read_text())
    assert (
        checks["passed"] == 23 and not checks["cloud_database_native_or_secret_actions"]
    )

    def segments(path):
        source = path.read_text()
        return {
            node.name: ast.get_source_segment(source, node)
            for node in ast.parse(source).body
            if isinstance(node, ast.FunctionDef)
        }

    before, current = segments(HERE / "operator.before.py"), segments(OPERATOR)
    for name, digest in checks["security_function_source_hashes"].items():
        assert before[name] == current[name], name
        assert hashlib.sha256(current[name].encode()).hexdigest() == digest, name
    assert len(checks["security_function_source_hashes"]) == 11
    live_path = ROOT / receipt["prior_provider_qualification"]
    qualified = json.loads(live_path.read_text())
    observed = qualified["result"]
    assert (
        qualified["state"] == "qualification_observed"
        and qualified["operator_revision"] == predecessor["operator_revision"]
    )
    assert observed["sequence_supported"] and not observed["bootstrap_authorized"]
    assert (
        observed["memberships_after_create"]
        == observed["memberships_after_revoke"]
        == []
    )
    assert all(
        observed[name] is True
        for name in (
            "transaction_rolled_back",
            "probe_absent_after_rollback",
            "application_role_inventory_unchanged",
            "application_table_inventory_unchanged",
        )
    )
    assert receipt["cloud_actions"] is False and receipt["native_actions"] is False
    print(
        json.dumps(
            {
                "state": receipt["state"],
                "pure_checks": 23,
                "existing_security_functions_unchanged": 11,
                "provider_nologin_probe": "previous dcde1ef source qualification observed",
                "new_owner_stage_managed_execution": "pending root",
                "independent_review": receipt["independent_review"],
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
