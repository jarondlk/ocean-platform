"""Record C19 hosted delivery once; preserve its original local acceptance."""
from pathlib import Path
import hashlib
import json
import re
import subprocess

ROOT = Path(__file__).resolve().parents[5]
OUT = Path(__file__).resolve().parent
PLAN = ROOT / "docs/plans/ocean-v1"
AMENDMENT = OUT / "ci-budget-amendment"
SOURCE = "4618188f589b6b6e3d50dee0bdf3343be0ec3484"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


assert not (OUT / "delivery.json").exists()
ci = json.loads((AMENDMENT / "hosted-ci.json").read_text())
assert ci["source_commit"] == ci["run"]["head_sha"] == SOURCE
assert ci["run"]["status"] == "completed" and ci["run"]["conclusion"] == "success"
assert all(job["conclusion"] == "success" for job in ci["jobs"] if job["name"] != "Dependency review")
accepted = json.loads((AMENDMENT / "accepted-source.json").read_text())
amendment = json.loads((AMENDMENT / "verification.json").read_text())
local = json.loads((OUT / "verification.json").read_text())
tested = json.loads((OUT / "backend-tested-source.json").read_text())["after_sha256"]
start = json.loads((OUT / "start-snapshot.json").read_text())
assert amendment["files"] == accepted["files"]
assert amendment["original_local_receipt_sha256"] == sha(OUT / "verification.json")
assert not subprocess.check_output(["git", "diff", "--name-only", SOURCE, "--", str(OUT.relative_to(ROOT))], cwd=ROOT, text=True).strip(), "Tracked original C19 evidence changed"
for files in (local["evidence_files"], amendment["cancelled_evidence_sha256"], start["prior_evidence_files"], *start["preservation"].values(), accepted["files"]):
    for path, expected in files.items():
        assert sha(ROOT / path) == expected, path
workflow = ".github/workflows/tests.yml"
assert [path for path, expected in tested.items() if sha(ROOT / path) != expected] == [workflow]
tested[workflow] = accepted["files"][workflow]
for path, expected in tested.items():
    content = subprocess.check_output(["git", "show", SOURCE + ":" + path], cwd=ROOT)
    assert hashlib.sha256(content).hexdigest() == expected, path
logs = {name: (AMENDMENT / name).read_text() for name in (
    "hosted-backend.txt", "hosted-postgres.txt", "hosted-frontend-v1.txt", "hosted-frontend-legacy.txt",
)}
matches = re.findall(r"(\d+) passed, (\d+) skipped[^\n]*?in ([\d.]+)s", logs["hosted-backend.txt"])
assert matches
passed, skipped, seconds = matches[-1]
coverage = float(re.findall(r"Total coverage: ([\d.]+)%", logs["hosted-backend.txt"])[-1])
assert int(passed) == local["checks"]["backend"]["passed"] - 9 == 4561
assert int(skipped) == 187
pg = [int(value) for value in re.findall(r"(\d+) passed[^\n]*? in [\d.]+s", logs["hosted-postgres.txt"])]
assert pg == [82, 12, 12, 21, 60], pg
assert re.search(r"# pass 673\b", logs["hosted-frontend-v1.txt"])
assert re.search(r"# pass 132\b", logs["hosted-frontend-legacy.txt"])
assert all("found 0 vulnerabilities" in logs[name] for name in ("hosted-frontend-v1.txt", "hosted-frontend-legacy.txt"))
extras = {str(path.relative_to(ROOT)): sha(path) for path in sorted(OUT.rglob("*")) if path.is_file() and "__pycache__" not in path.parts and path.name != "delivery.json" and str(path.relative_to(ROOT)) not in local["evidence_files"]}
record = {
    "component": "C19", "state": "Complete; source committed/pushed and exact-source hosted validation passed",
    "branch": "overhaul", "source_commit": SOURCE,
    "original_feature_source_commit": "a38b181cb7ac6472095a2b279e3c0aacbabb8e5c",
    "original_local_receipt_sha256": sha(OUT / "verification.json"),
    "original_accepted_source_receipt_sha256": sha(OUT / "accepted-source.json"),
    "accepted_source_receipt_sha256": sha(AMENDMENT / "accepted-source.json"),
    "ci_budget_amendment_receipt_sha256": sha(AMENDMENT / "verification.json"),
    "source_sha256": accepted["source_sha256"], "files": accepted["files"],
    "hosted_ci": ci,
    "hosted_counts": {"backend": int(passed), "postgres_gated_skips": int(skipped), "coverage_percent": coverage,
        "backend_pytest_seconds": float(seconds), "postgres_actual": sum(pg), "postgres_steps": pg,
        "v1_frontend": 673, "legacy_frontend": 132, "both_builds_typechecks": "pass",
        "both_frontend_production_dependency_audits": "zero vulnerabilities", "generated_contracts": "pass",
        "migration_idempotent_upsert_backup_isolated_restore": "pass"},
    "hosted_log_sha256": {"ci-budget-amendment/" + name: sha(AMENDMENT / name) for name in logs},
    "additional_delivery_evidence_files": extras,
    "hosted_log_storage": "Decoded connector logs normalized once on first save; per-log metadata retains original decoded and saved SHA256. Original local evidence unchanged.",
    "all87_effective_sources_match_hosted_source_commit": True,
    "local_tested_source_qualification": "86 original source paths unchanged; workflow-only20-to30-minute CI timeout supersession verified in ci-budget-amendment. All13 feature/test sources unchanged.",
    "original_hosted_cancellation": "CI39152862279 reached98percent before20-minute job timeout; immutable original logs retained, not accepted as a complete run.",
    "original_local_evidence_files_unchanged": len(local["evidence_files"]), "prior_evidence_files_unchanged": 823,
    "all_tracked_C19_evidence_unchanged_since_amendment_source": True,
    "local_hosted_count_difference": "Nine unrelated benchmark cases intentionally excluded from commit",
    "external_gates": ["C20 durable execution/frontend transport and C21 final synthesis remain separate.", "No real model/OIDC/scientific approval/acquisition/transfer/cloud deployment acceptance."],
}
with (OUT / "delivery.json").open("x") as stream:
    stream.write(json.dumps(record, indent=2) + "\n")
url = ci["run"]["html_url"]
summary = f"Source4618188 is committed/pushed; [exact-source hosted CI]({url}) passes:4561 backend/187 gated skips/{coverage}%,187 actual PostgreSQL,673 v1/132 legacy frontend, both builds/typechecks/audits, generated checks, migration/idempotence and isolated backup/restore."
path = PLAN / "components/C19-agent-controller.md"
text = path.read_text().replace("**Status:** Complete for all3 local checkpoints; source checkpoint and exact-source hosted delivery pending.", "**Status:** Complete; all3 local checkpoints and exact-source hosted delivery pass.", 1)
path.write_text(text + "\n" + summary + " [Delivery receipt](../evidence/C19/delivery.json).\n")
path = PLAN / "STATUS.md"
text = path.read_text().replace("**P00 and C01–C19 are Complete locally; C18 hosted delivery is complete and C19 hosted delivery is pending.**", "**P00 and C01–C19 are Complete locally; C19 hosted delivery is complete.**", 1)
lines = text.splitlines()
lines = [("Latest delivered implementation: **C19 — Agent exploration controller**. " + summary + " [Handoff](handoffs/C19.md), [contract](C19_AGENT_CONTROLLER_CONTRACT.md), [delivery receipt](evidence/C19/delivery.json). C20 readiness follows delivery." if line.startswith("Latest delivered implementation:") else line) for line in lines]
text = "\n".join(lines) + "\n"
text = text.replace("| Complete | All3 local checkpoints; source checkpoint/hosted delivery pending |", "| Complete | All3 local checkpoints and source4618188 hosted delivery pass |", 1)
text = text.replace("C19 passes local controller acceptance;", "C19 passes local controller acceptance and hosted delivery;")
text = text.replace("Source checkpoint and exact-source hosted delivery are pending.", "Exact-source hosted delivery is complete.")
text = text.replace("C19 hosted delivery remains pending: original sourcea38b181", "Historical C19 attempt before CI budget amendment: sourcea38b181")
path.write_text(text)
path = PLAN / "README.md"
text = path.read_text().replace("**P00 and C01–C19 are Complete locally; C18 hosted delivery is complete and C19 hosted delivery is pending; C20–C27 are not started.**", "**P00 and C01–C19 are Complete locally with C19 hosted delivery complete; C20–C27 are not started.**", 1)
text = text.replace("Source checkpoint and exact-source hosted delivery are pending.", "Exact-source hosted delivery is complete.")
text = text.replace("Delivery is\npending a complete new exact-source run; C20 remains unselected.", "This historical\nattempt is superseded by the complete exact-source delivery below.")
path.write_text(text + "\n" + summary + " [Delivery receipt](evidence/C19/delivery.json). C20 readiness follows delivery.\n")
path = PLAN / "handoffs/C19.md"
text = path.read_text().replace("State: Complete for all3 local checkpoints; source checkpoint/hosted delivery pending.", "State: Complete; all3 local checkpoints and exact-source hosted delivery pass.", 1)
text = text.replace("## Source delivery in progress", "## Original source attempt (historical)")
text = text.replace("New exact-source CI39154765984 is running with30-minute backend allowance;", "Exact-source CI39154765984 subsequently passed with30-minute backend allowance;")
text = text.replace("Next: commit/push the source checkpoint to overhaul, await source-bound hosted CI\nand record a separate delivery checkpoint before C20 readiness. C20 is not started.", "Source4618188 is committed/pushed and its exact-source hosted CI passes.\nNext: commit/push this separate delivery record, then finalize C20 readiness. C20 is not started.")
path.write_text(text + "\n## Final hosted delivery\n\n" + summary + "\n[Delivery receipt](../evidence/C19/delivery.json) preserves the original local\nreceipt, all pinned local evidence and86 original tested source paths; the only\nsource supersession is the separately verified CI job timeout. All13 feature/test\nfiles are unchanged. The nine-case local/hosted difference is the unrelated\nuncommitted benchmark suite. Historical cancellation/pending entries are\nsuperseded by this complete new exact-source delivery. C20 readiness follows.\n")
print(json.dumps({"state": "delivered", "source": SOURCE, "backend": int(passed), "coverage_percent": coverage, "delivery_sha256": sha(OUT / "delivery.json")}))
