"""Record exact-source C20 hosted delivery once without rewriting local receipts."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[4]
SOURCE = "fc46da36aa27c203357a1b5874a02378ae089847"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(name):
    return json.loads((OUT / name).read_text())


assert not (OUT / "delivery.json").exists(), "Delivery receipts are create-only"
ci = read("hosted-ci.json")
assert ci["source_commit"] == ci["run"]["head_sha"] == SOURCE
assert ci["run"]["status"] == "completed" and ci["run"]["conclusion"] == "success"
required = {"Backend tests and security boundary", "Frontend typecheck and build",
            "OCEAN v1 prototype tests and build", "PostgreSQL migration and metadata integration"}
jobs = {job["name"]: job for job in ci["jobs"]}
assert required <= jobs.keys() and all(jobs[name]["conclusion"] == "success" for name in required)
assert all(job["conclusion"] == "success" for name, job in jobs.items() if name != "Dependency review")
local, accepted, start = read("verification.json"), read("accepted-source.json"), read("start-snapshot.json")
assert local["files"] == accepted["files"] and local["source_sha256"] == accepted["source_sha256"]
for files in (local["files"], local["evidence_files"], local["tested_transitive_source_files"],
              start["prior_evidence_files"], *start["preservation"].values()):
    assert all(sha(ROOT / path) == digest for path, digest in files.items())
for path, digest in local["tested_transitive_source_files"].items():
    assert hashlib.sha256(subprocess.check_output(["git", "show", SOURCE + ":" + path], cwd=ROOT)).hexdigest() == digest, path
assert not subprocess.check_output(["git", "diff", "--name-only", SOURCE, "--", str(OUT.relative_to(ROOT))], cwd=ROOT, text=True).strip()

logs = {name: (OUT / name).read_text() for name in (
    "hosted-backend.txt", "hosted-postgres.txt", "hosted-frontend-v1.txt", "hosted-frontend-legacy.txt",
)}
matches = re.findall(r"(\d+) passed, (\d+) skipped[^\n]*?in ([\d.]+)s", logs["hosted-backend.txt"])
assert matches
passed, skipped, seconds = matches[-1]
coverage = float(re.findall(r"Total coverage: ([\d.]+)%", logs["hosted-backend.txt"])[-1])
assert int(passed) == local["checks"]["backend"]["passed"] - 9 == 4838
assert int(skipped) == 231 and coverage >= 70
pg = [int(value) for value in re.findall(r"(\d+) passed[^\n]*? in [\d.]+s", logs["hosted-postgres.txt"])]
assert pg == [82, 12, 12, 21, 60, 44], pg
assert re.search(r"# pass 781\b", logs["hosted-frontend-v1.txt"])
assert re.search(r"# pass 132\b", logs["hosted-frontend-legacy.txt"])
assert all("found 0 vulnerabilities" in logs[name] for name in ("hosted-frontend-v1.txt", "hosted-frontend-legacy.txt"))
for name, job_name in (("backend", "Backend tests and security boundary"),
                       ("postgres", "PostgreSQL migration and metadata integration"),
                       ("frontend-v1", "OCEAN v1 prototype tests and build"),
                       ("frontend-legacy", "Frontend typecheck and build")):
    metadata = read("hosted-" + name + "-log-metadata.json")
    assert metadata["source_commit"] == SOURCE and metadata["job_id"] == jobs[job_name]["id"]
    assert metadata["saved_sha256"] == sha(OUT / ("hosted-" + name + ".txt"))

extras = {str(path.relative_to(ROOT)): sha(path) for path in sorted(OUT.rglob("*"))
          if path.is_file() and "__pycache__" not in path.parts and path.name != "delivery.json"
          and str(path.relative_to(ROOT)) not in local["evidence_files"]}
record = {
    "component": "C20", "created_at": datetime.now(timezone.utc).isoformat(),
    "state": "Complete; source committed/pushed and exact-source hosted application validation passed",
    "branch": "overhaul", "source_commit": SOURCE,
    "original_local_receipt_sha256": sha(OUT / "verification.json"),
    "accepted_source_receipt_sha256": sha(OUT / "accepted-source.json"),
    "source_sha256": accepted["source_sha256"], "files": accepted["files"],
    "tested_transitive_source_files": local["tested_transitive_source_files"],
    "all167_tested_sources_match_hosted_source_commit": True,
    "hosted_ci": ci,
    "hosted_counts": {"backend": int(passed), "postgres_gated_skips": int(skipped),
        "coverage_percent": coverage, "backend_pytest_seconds": float(seconds),
        "postgres_actual": sum(pg), "postgres_steps": pg, "v1_frontend": 781, "legacy_frontend": 132,
        "both_builds_typechecks": "pass", "both_frontend_production_dependency_audits": "zero vulnerabilities",
        "generated_contracts": "pass", "migration_idempotent_upsert_backup_isolated_restore": "pass"},
    "hosted_log_sha256": {name: sha(OUT / name) for name in logs},
    "additional_delivery_evidence_files": extras,
    "original_local_evidence_files_unchanged": len(local["evidence_files"]),
    "prior_evidence_files_unchanged": len(start["prior_evidence_files"]),
    "protected_counts": {name: len(files) for name, files in start["preservation"].items()},
    "all_tracked_C20_evidence_unchanged_since_source": True,
    "local_hosted_count_difference": "Nine pre-existing unrelated benchmark cases remain uncommitted",
    "supersessions": "Original receipts retained; source/preservation and scheduler/test-only amendments record intentional changes.",
    "external_gates": [
        "Actual Cloud Tasks/private worker/identity/target configuration is separately authorized and configured later; no provisioning/deployment acceptance claimed.",
        "C21 retained answers/evidence and C26 assembled browser acceptance remain separate components.",
        "No real-model/OIDC/scientific approval/acquisition/transfer validation claimed.",
    ],
}
with (OUT / "delivery.json").open("x") as stream:
    json.dump(record, stream, indent=2)
    stream.write("\n")
print(json.dumps({"state": "delivered", "source": SOURCE, "backend": int(passed),
                  "postgres": sum(pg), "v1_frontend": 781, "coverage_percent": coverage,
                  "delivery_sha256": sha(OUT / "delivery.json")}))
