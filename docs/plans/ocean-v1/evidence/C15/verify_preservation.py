"""Bind frozen C15 source and explicit P00/C14 supersessions; run no tests."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

output = Path(__file__).resolve().parent
root = output.parents[4]
evidence = root / "docs/plans/ocean-v1/evidence"


def sha(path):
    return hashlib.sha256((root / path).read_bytes()).hexdigest()


def read(path):
    return json.loads((root / path).read_text())


def aggregate(files):
    value = "".join(f"{path}:{files[path]}\n" for path in sorted(files))
    return hashlib.sha256(value.encode()).hexdigest()


def write(path, value):
    path.write_text(json.dumps(value, indent=2) + "\n")


snapshot_path = "docs/plans/ocean-v1/evidence/C15/start-snapshot.json"
start = read(snapshot_path)
base = "c6eb0041250d0bbcd0323d313a6f452f695faf16"
assert start["implementation_base"] == base
assert start["C15_implementation_started"] is True

preserved = {}
expected_counts = {
    "unrelated_files": 30, "scientific_artifacts": 7, "serving_files": 2,
    "legacy_frontend_files": 106, "prior_evidence_files": 572,
}
for name, expected_count in expected_counts.items():
    files = start[name]
    assert len(files) == expected_count, name
    assert all(sha(path) == expected for path, expected in files.items()), name
    preserved[name] = {"count": len(files), "all_match": True}

# These are frontend-v1-relative P00 changes; the unrelated root README.md is
# preserved above, not accepted as part of C15.
p00_allowed = {
    "frontend-v1/README.md", "frontend-v1/app/layout.tsx",
    "frontend-v1/app/page.tsx", "frontend-v1/app/about/page.tsx",
    "frontend-v1/app/admin/page.tsx", "frontend-v1/app/feedback/page.tsx",
    "frontend-v1/package.json", "frontend-v1/scripts/preview.mjs",
    "frontend-v1/src/research-app.tsx",
}
p00 = start["P00_current_files"]
assert len(p00) == 36
p00_changes = {
    path: {"previous_sha256": previous, "accepted_C15_sha256": sha(path)}
    for path, previous in p00.items() if sha(path) != previous
}
assert set(p00_changes) == p00_allowed, "Unapproved or missing P00 supersession"
preserved["P00_current_files"] = {
    "count": len(p00), "unchanged": len(p00) - len(p00_changes),
    "intentional_C15_supersessions": p00_changes,
    "all_paths_match_or_are_explicitly_superseded": True,
}

source_prerequisites = start["source_files"]
assert set(source_prerequisites) == {"P00", "C08"}
for entries in source_prerequisites.values():
    for item in entries.values():
        assert sha(item["accepted_receipt"]) == item["accepted_receipt_sha256"]
assert len(source_prerequisites["C08"]) == 12
assert all(sha(path) == item["current_sha256"] for path, item in source_prerequisites["C08"].items())
preserved["C08_current_source"] = {"count": 12, "all_match": True}

c14_path = "docs/plans/ocean-v1/evidence/C14/verification.json"
c14_delivery_path = "docs/plans/ocean-v1/evidence/C14/delivery.json"
c14, delivery = read(c14_path), read(c14_delivery_path)
assert aggregate(c14["files"]) == c14["source_sha256"]
assert delivery["source_files"] == c14["files"]
assert delivery["source_sha256"] == c14["source_sha256"]
assert delivery["original_local_receipt"]["sha256"] == sha(c14_path)
assert delivery["implementation_commit"] == "19ba9110206dacb061c23f8e6dd7422be4b2adb1"
assert delivery["hosted_ci"]["source_commit"] == delivery["implementation_commit"]
assert delivery["hosted_ci"]["conclusion"] == "success"
integration_allowed = {"api/auth.py", "api/main.py", "config.py"}
assert set(start["integration_base_files"]) == integration_allowed
assert all(c14["files"][path] == previous for path, previous in start["integration_base_files"].items())
c14_changes = {
    path: {"previous_sha256": previous, "accepted_C15_sha256": sha(path)}
    for path, previous in c14["files"].items() if sha(path) != previous
}
assert set(c14_changes) == integration_allowed, "Unapproved or missing C14 supersession"
preserved["C14_current_source"] = {
    "count": len(c14["files"]), "unchanged": len(c14["files"]) - len(c14_changes),
    "intentional_C15_supersessions": c14_changes,
    "all_paths_match_or_are_explicitly_superseded": True,
}

confirmation_path = "docs/plans/ocean-v1/evidence/c15-readiness-2026-10-16/ready-confirmation.json"
confirmation = read(confirmation_path)
assert confirmation["base_commit"] == base
assert confirmation["prerequisite_entries_reconciled"] == 48
assert sha(confirmation["preparation_receipt"]["path"]) == confirmation["preparation_receipt"]["sha256"]
assert sha(c14_delivery_path) == confirmation["previous_delivery"]["sha256"]
assert confirmation["previous_delivery"]["delivery_checkpoint"] == base

backend_path = "docs/plans/ocean-v1/evidence/C15/backend-tested-source.json"
backend = read(backend_path)
backend_files = {"api/v1_runtime_routes.py", "api/auth.py", "api/main.py", "config.py", "tests/test_v1_runtime.py"}
assert set(backend) == backend_files
assert all(sha(path) == expected for path, expected in backend.items()), "Backend source differs from tested bytes"

paths = sorted(p00_allowed | backend_files | {
    "frontend-v1/scripts/preview-mode.mjs",
    "frontend-v1/src/application-shell.tsx", "frontend-v1/src/presentation.ts",
    "frontend-v1/src/runtime-app.tsx", "frontend-v1/src/runtime.ts",
    "frontend-v1/src/shell-panels.tsx", "frontend-v1/src/shell.css",
    "frontend-v1/src/v1-entry.tsx", "frontend-v1/tests/presentation.test.ts",
    "frontend-v1/tests/preview-mode.test.ts", "frontend-v1/tests/runtime.test.ts",
})
assert len(paths) == 25
files = {path: sha(path) for path in paths}
accepted = {
    "files": files, "source_sha256": aggregate(files),
    "aggregate_algorithm": "SHA256 of sorted UTF-8 path:SHA256 lines with LF endings",
}
accepted_path = output / "accepted-source.json"
if accepted_path.exists():
    assert json.loads(accepted_path.read_text()) == accepted, "Frozen C15 accepted source changed"
else:
    write(accepted_path, accepted)

receipt = {
    "component": "C15", "date": "2026-10-17 JST", "implementation_base": base,
    "source_sha256": accepted["source_sha256"], "source_paths": len(files),
    "all_source_hashes_match": True, "preservation": preserved,
    "backend_tested_source": {
        "path": backend_path, "sha256": sha(backend_path), "paths": len(backend),
        "all_current_hashes_match": True, "files": backend,
    },
    "formal_prerequisites": {
        "P00": {"paths": 36, "unchanged": 27, "intentional_C15_supersessions": p00_changes},
        "C08": {"paths": 12, "unchanged": 12, "intentional_C15_supersessions": {}},
    },
    "integration_edits": c14_changes,
    "earlier_receipts": {
        c14_path: sha(c14_path), c14_delivery_path: sha(c14_delivery_path),
        confirmation_path: sha(confirmation_path), snapshot_path: sha(snapshot_path),
    },
    "earlier_receipts_policy": "Original P00/C08/C14 receipts and all 572 earlier evidence files are immutable; only this later map records C15 supersessions",
    "scope": "Hash and preservation verification only; no tests, source/docs edits, services, commit or push",
}
write(output / "preservation.json", receipt)
print(json.dumps({
    "source_paths": len(files), "source_sha256": accepted["source_sha256"],
    "preserved_counts": expected_counts, "P00_unchanged": 27,
    "P00_C15_supersessions": len(p00_changes), "C14_unchanged": len(c14["files"]) - len(c14_changes),
    "C14_C15_supersessions": len(c14_changes), "C08_unchanged": 12,
    "backend_tested_source_match": len(backend), "all_assertions_passed": True,
}))
