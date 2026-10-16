"""Read-only prerequisite bindings at the amended C13 source checkpoint."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess

output = Path(__file__).resolve().parent
root = output.parents[4]
base = "98c2769402cb83602f515348651aca668f21d0dd"
prefix = "docs/plans/ocean-v1/evidence/"


def sha(data):
    return hashlib.sha256(data).hexdigest()


def committed(path):
    return subprocess.check_output(["git", "show", f"{base}:{path}"], cwd=root)


def current(path):
    return sha((root / path).read_bytes())


def read(path):
    return json.loads(committed(path))


def aggregate(files):
    return sha("".join(f"{p}:{files[p]}\n" for p in sorted(files)).encode())


c12_path = prefix + "C12/verification.json"
c12 = read(c12_path)
sources = {}
for component in ("C04", "C08", "C09", "C10", "C11", "C12", "C13"):
    original_path = prefix + component + "/verification.json"
    original = read(original_path)
    assert aggregate(original["files"]) == original["source_sha256"]
    accepted_path = prefix + "C13/method-alias-amendment/verification.json" if component == "C13" else original_path
    accepted = read(accepted_path)
    assert aggregate(accepted["files"]) == accepted["source_sha256"]
    group = {}
    for path, expected in original["files"].items():
        receipt_path = accepted_path
        value = accepted["files"][path]
        if component in {"C08", "C09"} and current(path) != value:
            receipt_path, value = c12_path, c12["files"][path]
        assert current(path) == value == sha(committed(path)), path
        group[path] = {
            "original_sha256": expected, "current_sha256": value,
            "original_match": expected == value,
            "accepted_receipt": receipt_path,
            "accepted_receipt_sha256": sha(committed(receipt_path)),
        }
    sources[component] = group

amendment_path = prefix + "C13/method-alias-amendment/verification.json"
amendment = read(amendment_path)
assert sha(committed(prefix + "C13/verification.json")) == amendment["original_local_receipt_sha256"]
for path, item in amendment["supersedes"].items():
    assert sources["C13"][path]["original_sha256"] == item["original_sha256"]
    assert sources["C13"][path]["current_sha256"] == item["amended_sha256"]
for path, expected in amendment["evidence_files_sha256"].items():
    assert current(path) == expected == sha(committed(path)), path

start = read(prefix + "C13/start-snapshot.json")
preserved = {name: start[name] for name in (
    "unrelated_files", "scientific_artifacts", "serving_files", "P00_current_files")}
for files in preserved.values():
    assert all(current(path) == expected for path, expected in files.items())
paths = subprocess.check_output(["git", "ls-tree", "-r", "--name-only", base,
                                 "docs/plans/ocean-v1/evidence"], cwd=root).decode().splitlines()
prior = {path: sha(committed(path)) for path in paths}
assert all(current(path) == expected for path, expected in prior.items())
snapshot = {
    "component": "C14 read-only readiness preparation", "date": "2026-10-16 JST",
    "base_head": base, "formal_prerequisites": list(sources), "source_files": sources,
    **preserved, "prior_evidence_files": prior,
    "C13_amendment_receipt_sha256": sha(committed(amendment_path)),
    "C13_final_source_sha256": amendment["source_sha256"],
    "C13_final_hosted_delivery": "Pending parent confirmation; original-source CI does not establish amended source",
}
(output / "start-snapshot.json").write_text(json.dumps(snapshot, indent=2) + "\n")
summary = {
    "base_head": base, "formal_prerequisites": {
        component: {"paths": len(group), "original_matches": sum(item["original_match"] for item in group.values()),
                    "accepted_supersessions": sum(not item["original_match"] for item in group.values()),
                    "all_current_hashes_match": True}
        for component, group in sources.items()},
    "prior_evidence_files_preserved": len(prior),
    "preservation": {name: {"count": len(files), "all_match": True} for name, files in preserved.items()},
    "C13_original_local_receipt_sha256": amendment["original_local_receipt_sha256"],
    "C13_final_amendment_receipt_sha256": sha(committed(amendment_path)),
    "C13_final_source_sha256": amendment["source_sha256"],
    "C13_final_hosted_delivery_gate": "Pending parent confirmation",
    "all_hash_assertions_passed": True,
    "start_snapshot_sha256": current(str((output / "start-snapshot.json").relative_to(root))),
}
(output / "source-verification.json").write_text(json.dumps(summary, indent=2) + "\n")
print(json.dumps(summary))
