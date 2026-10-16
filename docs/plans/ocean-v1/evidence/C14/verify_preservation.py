"""Verify final C14 sources and explicitly record only accepted integration edits."""
import hashlib
import json
from pathlib import Path

out = Path(__file__).resolve().parent
root = out.parents[4]
start = json.loads((out / "start-snapshot.json").read_text())
accepted = json.loads((out / "accepted-source.json").read_text())


def digest(path):
    return hashlib.sha256((root / path).read_bytes()).hexdigest()


assert all(digest(path) == value for path, value in accepted["files"].items())
groups = {}
for group in (
    "unrelated_files", "scientific_artifacts", "serving_files", "P00_current_files",
    "prior_evidence_files",
):
    assert all(digest(path) == value for path, value in start[group].items()), group
    groups[group] = {"count": len(start[group]), "all_match": True}

prerequisites = {}
for component, entries in start["source_files"].items():
    unchanged, superseded = [], {}
    for path, entry in entries.items():
        previous, current = entry["current_sha256"], digest(path)
        if previous == current:
            unchanged.append(path)
        else:
            assert path == "api/auth.py" and component == "C04"
            assert current == accepted["files"][path]
            superseded[path] = {"previous_sha256": previous, "C14_sha256": current}
    prerequisites[component] = {
        "paths": len(entries), "unchanged": len(unchanged),
        "accepted_C14_supersessions": superseded,
    }

integration = {
    path: {"base_sha256": value, "accepted_C14_sha256": digest(path)}
    for path, value in start["integration_base_files"].items()
}
receipt = {
    "component": "C14", "source_sha256": accepted["source_sha256"],
    "source_paths": len(accepted["files"]), "all_source_hashes_match": True,
    "preservation": groups, "formal_prerequisites": prerequisites,
    "integration_edits": integration,
    "earlier_receipts": "Immutable; only this later source map records the additive auth/config/main integration",
}
(out / "preservation.json").write_text(json.dumps(receipt, indent=2) + "\n")
print(json.dumps(receipt))
