"""Read-only verification of retained C27 local rollback evidence."""
from __future__ import annotations

import gzip
import hashlib
import json
from pathlib import Path
import subprocess
import xml.etree.ElementTree as ET

DIRECTORY = Path(__file__).resolve().parent
ROOT = DIRECTORY.parents[5]


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def verify():
    result = json.loads((DIRECTORY / "accepted/result.json").read_text())
    assert result["status"] == "passed" and result["release_accepted"] is False
    assert result["disposable_stores_removed"] is True
    assert result["source_revision"] == "sha256:" + sha(canonical(result["source_files"]).encode())
    for name, identity in result["source_files"].items():
        path = (ROOT / name).resolve()
        assert path.is_relative_to(ROOT) and path.is_file()
        raw = path.read_bytes()
        assert sha(raw) == identity, name
        if path != DIRECTORY / "rehearse.py":
            accepted = subprocess.check_output(["git", "show", result["accepted_runtime_source"] + ":" + name], cwd=ROOT)
            assert raw == accepted, name
    for name, identity in result["artifacts_sha256"].items():
        assert Path(name).name == name
        path = DIRECTORY / "accepted" / name
        raw = path.read_bytes() if path.is_file() else gzip.decompress(path.with_suffix(path.suffix + ".gz").read_bytes())
        assert sha(raw) == identity, name
    cases = list(ET.parse(DIRECTORY / "accepted/regressions.xml").getroot().iter("testcase"))
    assert len(cases) == result["regressions"]["passed"] == 11
    assert not any(case.find(tag) is not None for case in cases for tag in ("failure", "error", "skipped"))
    assert result["regressions"]["returncode"] == 0
    shared = result["shared_stack"]
    assert shared["status"] == "passed"
    assert shared["snapshots"]["before_dispatch_disable"] == shared["snapshots"]["after_dispatch_disable_and_reads"]
    assert shared["drain"]["cancelled_states"] == ["cancelled", "cancelled"]
    assert shared["drain"]["terminal_redelivery_unchanged"] is True
    assert shared["research_ack_loss"]["committed_steps"] == 1
    assert shared["research_ack_loss"]["identical_delivery_identity"] is True
    assert shared["experiment_ack_loss"]["state_while_disabled"] == "uncertain"
    assert shared["experiment_ack_loss"]["reservation_released"] is False
    assert shared["experiment_ack_loss"]["execution_performed"] is False
    assert shared["previous_binary_compatibility"] == "not_established"
    return {"verified": True, "runtime_source": result["accepted_runtime_source"],
        "source_revision": result["source_revision"], "source_paths": len(result["source_files"]),
        "table_hashes_preserved_by_dispatch_disable": len(shared["snapshots"]["before_dispatch_disable"]),
        "targeted_regressions_passed": len(cases), "release_accepted": False,
        "qualification": "Local synthetic queues and execution projections; C23 tests mock physical runtime; no previous-binary or live rollback acceptance"}


if __name__ == "__main__":
    print(json.dumps(verify(), indent=2))
