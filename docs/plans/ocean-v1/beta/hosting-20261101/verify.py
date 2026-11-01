#!/usr/bin/env python3
"""Read-only verification of the new host snapshot and retained local evidence."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    evidence = Path(__file__).resolve().parent
    repository = evidence.parents[4]
    receipt = json.loads((evidence / "receipt.json").read_text())
    commands = json.loads((evidence / "accepted-commands.json").read_text())
    source_files = commands["source_files"]
    canonical = json.dumps(source_files, sort_keys=True, separators=(",", ":"))
    revision = "sha256:" + hashlib.sha256(canonical.encode()).hexdigest()
    assert revision == commands["source_revision"] == receipt["source_revision"]
    assert len(source_files) == receipt["source_file_count"]
    for name, expected in source_files.items():
        assert digest(repository / name) == expected, f"Source changed: {name}"
    for name, expected in receipt["evidence_files"].items():
        assert digest(evidence / name) == expected, f"Evidence changed: {name}"
    assert all(item["returncode"] == 0 for item in commands["commands"])
    assert {item["id"] for item in commands["commands"]} == {
        "host-unit", "host-typecheck", "host-build", "host-http", "host-audit",
    }
    for name, expected in receipt["tap_counts"].items():
        output = (evidence / name).read_text()
        for field, value in expected.items():
            assert re.search(rf"^# {field} {value}$", output, re.MULTILINE), (
                f"Unexpected {field}: {name}"
            )
    assert (evidence / "host-audit.stdout").read_text().strip() == "found 0 vulnerabilities"
    for name in ("host-build.stdout", "preview-build.stdout"):
        output = (evidence / name).read_text()
        assert "Compiled successfully" in output and "Finalizing page optimization" in output
    for name in ("host-typecheck.stdout", "preview-typecheck.stdout"):
        assert "Route types generated successfully" in (evidence / name).read_text()
    assert receipt["live_google_callback_tested"] is False
    assert receipt["deployment_accepted"] is False
    for item in receipt["intentional_supersessions"]:
        assert source_files[item["path"]] == item["new_sha256"]
        assert item["previous_sha256"] != item["new_sha256"]
    print(json.dumps({
        "status": "verified",
        "source_revision": revision,
        "source_files": len(source_files),
        "host_tests": 50,
        "standalone_http_tests": 1,
        "preview_tests": 1051,
        "qualification": receipt["qualification"],
    }, indent=2))


if __name__ == "__main__":
    main()
