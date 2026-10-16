"""Read-only C15 source reconciliation; never snapshots mutable C14 logs."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess

OUTPUT = Path(__file__).resolve().parent
ROOT = OUTPUT.parents[4]
BASE = subprocess.check_output(["git", "rev-parse", "b0cac5e"], cwd=ROOT).decode().strip()
PREFIX = "docs/plans/ocean-v1/"


def sha(value):
    return hashlib.sha256(value).hexdigest()


def committed(path):
    return subprocess.check_output(["git", "show", f"{BASE}:{path}"], cwd=ROOT)


def read(path):
    return json.loads(committed(path))


def current(path):
    return sha((ROOT / path).read_bytes())


def aggregate(files):
    return sha("".join(f"{path}:{files[path]}\n" for path in sorted(files)).encode())


receipts = {
    "P00": PREFIX + "mockups/p00/source-revision.json",
    "C07": PREFIX + "evidence/C07/verification.json",
    "C08": PREFIX + "evidence/C08/verification.json",
    "C12": PREFIX + "evidence/C12/verification.json",
}
data = {component: read(path) for component, path in receipts.items()}
for component, receipt in data.items():
    assert aggregate(receipt["files"]) == receipt["source_sha256"], component

sources = {}
for component, superseding in (("P00", "C07"), ("C08", "C12")):
    group = {}
    for path, original in data[component]["files"].items():
        value = current(path)
        selected = component if value == original else superseding
        assert value == data[selected]["files"][path] == sha(committed(path)), path
        group[path] = {
            "original_sha256": original,
            "current_sha256": value,
            "original_match": value == original,
            "accepted_receipt": receipts[selected],
            "accepted_receipt_sha256": sha(committed(receipts[selected])),
        }
    sources[component] = group

start = read(PREFIX + "evidence/C13/start-snapshot.json")
preserved = {name: start[name] for name in (
    "unrelated_files", "scientific_artifacts", "serving_files", "P00_current_files",
)}
for files in preserved.values():
    assert all(current(path) == expected for path, expected in files.items())
paths = subprocess.check_output(
    ["git", "ls-tree", "-r", "--name-only", BASE, PREFIX + "evidence"], cwd=ROOT,
).decode().splitlines()
prior = {path: sha(committed(path)) for path in paths}
assert all(current(path) == expected for path, expected in prior.items())

snapshot = {
    "component": "C15 read-only readiness preparation",
    "date": "2026-10-16 JST",
    "base_head": BASE,
    "formal_prerequisites": ["P00", "C08"],
    "source_files": sources,
    **preserved,
    "prior_evidence_files": prior,
    "evidence_boundary": "Only evidence committed at C13 delivery b0cac5e; mutable C14 logs are excluded",
    "C14_next_pipeline_gate": "Pending exact final-source hosted CI and parent delivery confirmation",
    "C15_implementation_started": False,
}
(OUTPUT / "start-snapshot.json").write_text(json.dumps(snapshot, indent=2) + "\n")
summary = {
    "base_head": BASE,
    "formal_prerequisites": {
        component: {
            "paths": len(group),
            "original_matches": sum(item["original_match"] for item in group.values()),
            "accepted_supersessions": sum(not item["original_match"] for item in group.values()),
            "all_current_hashes_match": True,
        }
        for component, group in sources.items()
    },
    "preservation": {name: {"count": len(files), "all_match": True} for name, files in preserved.items()},
    "prior_evidence_files_preserved": len(prior),
    "all_hash_assertions_passed": True,
    "start_snapshot_sha256": sha((OUTPUT / "start-snapshot.json").read_bytes()),
    "C14_final_source_CI_and_delivery_gate": "Pending parent confirmation",
    "C15_implementation_started": False,
}
(OUTPUT / "source-verification.json").write_text(json.dumps(summary, indent=2) + "\n")
print(json.dumps(summary))
