"""Read-only amendment/current-source and immutable predecessor verification."""

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
    assert sha(BASE / "receipt.json") == receipt["predecessor_receipt_sha256"]
    assert (BASE / "receipt.json").read_bytes() == (
        HERE / "original-receipt.json"
    ).read_bytes()
    predecessor = json.loads((HERE / "original-receipt.json").read_text())
    for relative, digest in predecessor["source_pins"].items():
        assert sha(HERE / "frozen-source" / relative) == digest, relative
        if relative != "deploy/gcp/beta/operator/operator.py":
            assert sha(ROOT / relative) == digest, relative
    for relative, digest in predecessor["artifact_pins"].items():
        assert sha(BASE / relative) == digest, relative
    for relative, digest in receipt["source_pins"].items():
        assert sha(ROOT / relative) == digest, relative
    for relative, digest in receipt["artifact_pins"].items():
        assert sha(HERE / relative) == digest, relative
    native = json.loads((HERE / "native-accepted/receipt.json").read_text())
    assert native["state"] == "passed" and len(native["checks"]) == 38
    assert all(item["passed"] for item in native["checks"])
    assert all(native["cleanup"].values())
    for relative, digest in native["source_pins"].items():
        assert sha(ROOT / relative) == digest, relative
    for relative, digest in native["artifacts"].items():
        assert sha(HERE / "native-accepted" / relative) == digest, relative
    guards = json.loads((HERE / "guards.json").read_text())
    assert guards["passed"] == 26
    print(
        json.dumps(
            {
                "state": "verified",
                "native_checks": 38,
                "guard_checks": 26,
                "unchanged_predecessor_artifacts": len(predecessor["artifact_pins"]),
                "preserved_predecessor_sources": len(predecessor["source_pins"]),
                "current_sources": len(receipt["source_pins"]),
                "amendment_artifacts": len(receipt["artifact_pins"]),
                "cloud_or_stateful_actions": False,
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
