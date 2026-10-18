"""Freeze a CI-timeout-only amendment; no local acceptance is rewritten."""
from pathlib import Path
import hashlib
import json
import subprocess

ROOT = Path(__file__).resolve().parents[6]
OUT = Path(__file__).resolve().parent
ORIGINAL = OUT.parent
SOURCE = "a38b181cb7ac6472095a2b279e3c0aacbabb8e5c"


def sha(path):
    return hashlib.sha256((ROOT / path).read_bytes()).hexdigest()


def aggregate(files):
    return hashlib.sha256("".join(f"{p}:{h}\n" for p, h in sorted(files.items())).encode()).hexdigest()


def save(name, value):
    with (OUT / name).open("x") as stream:
        stream.write(json.dumps(value, indent=2) + "\n")


assert not (OUT / "verification.json").exists()
workflow = ".github/workflows/tests.yml"
before = subprocess.check_output(["git", "show", SOURCE + ":" + workflow], cwd=ROOT)
after = (ROOT / workflow).read_bytes()
assert before.count(b"timeout-minutes: 20") >= 1
assert before.replace(b"timeout-minutes: 20", b"timeout-minutes: 30", 1) == after
local = json.loads((ORIGINAL / "verification.json").read_text())
accepted = json.loads((ORIGINAL / "accepted-source.json").read_text())
for files in (local["evidence_files"], accepted["files"]):
    for path, expected in files.items():
        assert sha(path) == expected, path
start = json.loads((ORIGINAL / "start-snapshot.json").read_text())
for files in [start["prior_evidence_files"], *start["preservation"].values()]:
    for path, expected in files.items():
        assert sha(path) == expected, path
tested = json.loads((ORIGINAL / "backend-tested-source.json").read_text())["after_sha256"]
changed = [path for path, expected in tested.items() if sha(path) != expected]
assert changed == [workflow]
ci = json.loads((ORIGINAL / "hosted-ci-cancelled.json").read_text())
assert ci["source_commit"] == ci["run"]["head_sha"] == SOURCE
assert ci["run"]["conclusion"] == "cancelled"
log = (ORIGINAL / "hosted-backend-cancelled.txt").read_text()
assert "[ 98%]" in log and "The operation was canceled." in log
assert "FAILED tests/" not in log
files = {**accepted["files"], workflow: sha(workflow)}
save("accepted-source.json", {"files": files, "source_sha256": aggregate(files), "aggregate_algorithm": "SHA256 of sorted UTF-8 path:SHA256 lines with LF endings"})
evidence = {str(path.relative_to(ROOT)): sha(path.relative_to(ROOT)) for path in sorted(ORIGINAL.glob("hosted-*-cancelled*")) if path.is_file()}
evidence[str((ORIGINAL / "hosted-ci-cancelled.json").relative_to(ROOT))] = sha((ORIGINAL / "hosted-ci-cancelled.json").relative_to(ROOT))
save("verification.json", {
    "component": "C19", "state": "CI budget amendment verified; new exact-source hosted run pending",
    "original_source_commit": SOURCE,
    "original_local_receipt_sha256": sha((ORIGINAL / "verification.json").relative_to(ROOT)),
    "original_accepted_source_receipt_sha256": sha((ORIGINAL / "accepted-source.json").relative_to(ROOT)),
    "original13_application_test_sources_unchanged": True,
    "local_tested_source_paths": len(tested), "unchanged_tested_paths": len(tested) - 1,
    "workflow_change": {"path": workflow, "before_sha256": hashlib.sha256(before).hexdigest(), "after_sha256": sha(workflow), "before_job_minutes": 20, "after_job_minutes": 30, "reason": "The4500-plus-case source-bound backend suite reached98percent with no reported test failure before the20-minute workflow timeout. Allow bounded completion while retaining every command and gate."},
    "files": files, "source_sha256": aggregate(files), "cancelled_run": ci["run"],
    "cancelled_evidence_sha256": evidence,
    "preservation": {"original_local_receipt_and_evidence": "unchanged", "prior_evidence_files": len(start["prior_evidence_files"]), "protected_counts": {key: len(values) for key, values in start["preservation"].items()}},
    "qualifications": ["Only backend CI job wall-time allowance changes; controller180seconds/12actions/one-repair and test/coverage commands are unchanged.", "No local application suite repeated for this workflow-only change; original4570/187skips/85.43percent acceptance remains immutable.", "The cancelled hosted run is not a complete acceptance receipt. New exact-source hosted success is required before C20 selection."]
})
print(json.dumps({"CI_budget_only": True, "application_sources_unchanged": 13, "tested_source_paths_unchanged": len(tested)-1, "new_source_sha256": aggregate(files)}))
