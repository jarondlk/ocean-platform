"""Reconcile C13 prerequisite histories without modifying historical receipts."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess

output = Path(__file__).resolve().parent
root = output.parents[4]
base = "5abab665820d59af1a0b23c05992d35864d2011d"
evidence = "docs/plans/ocean-v1/evidence/"


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def current(path: str) -> str:
    return digest((root / path).read_bytes())


def committed(path: str) -> bytes:
    return subprocess.check_output(["git", "show", f"{base}:{path}"], cwd=root)


def read(path: str) -> dict:
    return json.loads(committed(path))


def aggregate(files: dict) -> str:
    return digest("".join(f"{p}:{files[p]}\n" for p in sorted(files)).encode())


def reconcile_historical(component: str, accepted: dict) -> dict:
    original_path = evidence + component + "/verification.json"
    original = read(original_path)
    results = {}
    for path, expected in original["files"].items():
        item = accepted[path]
        receipt_path = item["accepted_receipt"]
        receipt = read(receipt_path)
        assert digest(committed(receipt_path)) == item["accepted_receipt_sha256"]
        assert item["original_sha256"] == expected
        assert receipt["files"][path] == item["current_sha256"]
        assert current(path) == item["current_sha256"] == digest(committed(path))
        results[path] = item
    assert aggregate(original["files"]) == original["source_sha256"]
    return results


start = read(evidence + "C12/start-snapshot.json")
sources = {
    "C01": reconcile_historical("C01", start["C01_current_source"]),
    "C02": reconcile_historical("C02", read(evidence + "C11/verification.json")["C02_current_source"]),
}
for component in ("C10", "C11", "C12"):
    receipt_path = evidence + component + "/verification.json"
    receipt = read(receipt_path)
    assert aggregate(receipt["files"]) == receipt["source_sha256"]
    sources[component] = {}
    for path, expected in receipt["files"].items():
        assert current(path) == expected == digest(committed(path)), path
        sources[component][path] = {
            "current_sha256": expected, "original_match": True,
            "accepted_receipt": receipt_path,
            "accepted_receipt_sha256": digest(committed(receipt_path)),
        }

c12 = read(evidence + "C12/verification.json")
supersessions = {}
for component in ("C08", "C09"):
    old = read(evidence + component + "/verification.json")["files"]
    group = {}
    for path, original in old.items():
        now = current(path)
        assert now == digest(committed(path))
        if now != original:
            assert c12["files"][path] == now, path
        group[path] = {"original_sha256": original, "current_sha256": now,
                       "original_match": now == original,
                       "accepted_receipt": evidence + (component if now == original else "C12") + "/verification.json"}
    supersessions[component] = group

paths = subprocess.check_output(["git", "ls-tree", "-r", "--name-only", base,
                                 "docs/plans/ocean-v1/evidence"], cwd=root).decode().splitlines()
prior_evidence = {path: digest(committed(path)) for path in paths}
assert all(current(p) == expected for p, expected in prior_evidence.items())
preserved = {}
for group in ("unrelated_files", "scientific_artifacts", "serving_files", "P00_current_files"):
    preserved[group] = start[group]
    assert all(current(p) == expected for p, expected in preserved[group].items()), group

delivery = read(evidence + "C12/delivery.json")
assert delivery["implementation_commit"] == "d3ef6992e97c46ca3f7ff4f554ecc4e60e05bef9"
assert delivery["source_sha256"] == c12["source_sha256"]
assert delivery["source_files"] == c12["files"]
assert delivery["original_local_receipt"]["sha256"] == digest(committed(evidence + "C12/verification.json"))
for path, expected in delivery["evidence_files_sha256"].items():
    assert current(path) == expected == digest(committed(path))
hosted = read(evidence + "C12/hosted-ci.json")

snapshot = {
    "component": "C13 readiness only", "date": "2026-10-16 JST", "base_head": base,
    "formal_prerequisites": ["C01", "C02", "C10", "C11", "C12"],
    "prerequisite_sources": sources, "accepted_C08_C09_supersessions": supersessions,
    **preserved, "prior_evidence_files": prior_evidence,
    "C12_delivery_receipt_sha256": digest(committed(evidence + "C12/delivery.json")),
    "C12_original_local_receipt_sha256": digest(committed(evidence + "C12/verification.json")),
    "C12_hosted_ci": delivery["hosted_ci"],
    "C12_hosted_receipt": hosted,
    "C13_implementation_started": False,
}
(output / "start-snapshot.json").write_text(json.dumps(snapshot, indent=2) + "\n")
summary = {
    "base_head": base, "formal_prerequisites": {
        component: {"source_paths": len(items), "original_matches": sum(i["original_match"] for i in items.values()),
                    "accepted_supersessions": sum(not i["original_match"] for i in items.values()),
                    "all_current_hashes_match": True}
        for component, items in sources.items()
    },
    "C08_C09": {component: {"paths": len(items), "unchanged": sum(i["original_match"] for i in items.values()),
                              "accepted_C12_supersessions": [p for p, i in items.items() if not i["original_match"]]}
                    for component, items in supersessions.items()},
    "prior_evidence_files_preserved": len(prior_evidence),
    "preservation": {name: {"count": len(files), "all_match": True} for name, files in preserved.items()},
    "C12_hosted_ci": delivery["hosted_ci"], "all_assertions_passed": True,
    "start_snapshot_sha256": current(str((output / "start-snapshot.json").relative_to(root))),
}
(output / "source-verification.json").write_text(json.dumps(summary, indent=2) + "\n")
print(json.dumps(summary))
