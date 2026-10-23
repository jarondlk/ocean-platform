"""Create a separate immutable receipt for C23's existing preparation CI.

This records software checks only. It never executes a sandbox or grants runtime
eligibility. Downloaded GitHub text logs use LF and one trailing newline.
"""

import hashlib
import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[5]
BASE = Path(__file__).resolve().parent
HOSTED = BASE / "hosted-preparation-39578854643"
SOURCE = "b8e929e426ff9cd5c2b8feb58e7f5a7b31189ea8"


def sha(data):
    return hashlib.sha256(data).hexdigest()


def git(*args):
    return subprocess.check_output(["git", *args], cwd=ROOT)


def pin(path):
    return {"path": str(path.relative_to(ROOT)), "sha256": sha(path.read_bytes())}


def main():
    target = BASE / "hosted-preparation.json"
    if target.exists():
        raise SystemExit("Refusing to replace an existing receipt")
    run = json.loads((HOSTED / "run.json").read_text())
    jobs = json.loads((HOSTED / "jobs.json").read_text())
    assert run["id"] == 39578854643
    assert run["head_sha"] == SOURCE and run["head_branch"] == "overhaul"
    assert run["status"] == "completed" and run["conclusion"] == "success"
    assert git("branch", "--show-current").strip() == b"overhaul"
    assert git("merge-base", "--is-ancestor", SOURCE, "HEAD") == b""
    expected = {
        119151264787: "OCEAN v1 prototype tests and build",
        119151265293: "Frontend typecheck and build",
        119151265404: "Backend tests and security boundary",
        119151265420: "PostgreSQL migration and metadata integration",
    }
    logs = {}
    for job_id, name in expected.items():
        job = next(j for j in jobs if j["id"] == job_id)
        assert job["name"] == name and job["run_id"] == run["id"]
        assert job["status"] == "completed" and job["conclusion"] == "success"
        logs[job_id] = (HOSTED / f"job-{job_id}.log").read_text()
        assert SOURCE in logs[job_id]
    backend = logs[119151265404]
    assert "5556 passed, 275 skipped" in backend
    assert "Total coverage: 86.94%" in backend
    assert "All checks passed!" in backend
    pg_counts = [int(n) for n in re.findall(r"Z (\d+) passed", logs[119151265420])]
    assert pg_counts == [82, 12, 12, 21, 60, 44, 23, 21]
    for job_id, count in ((119151264787, 930), (119151265293, 132)):
        assert f"# tests {count}" in logs[job_id]
        assert f"# pass {count}" in logs[job_id] and "# fail 0" in logs[job_id]
        assert "found 0 vulnerabilities" in logs[job_id]
        for required in ("Typecheck", "Build", "Audit production"):
            job = next(j for j in jobs if j["id"] == job_id)
            assert any(required.lower() in s["name"].lower() and s["conclusion"] == "success"
                       for s in job["steps"]), (job_id, required)
    pushed = BASE / "pushed-checkpoint.json"
    previous = json.loads(pushed.read_text())
    assert previous["source_commit"] == SOURCE
    source_files = previous["source_files"]
    assert len(source_files) == 17
    for path, digest in source_files.items():
        assert sha(git("show", f"{SOURCE}:{path}")) == digest
        assert sha((ROOT / path).read_bytes()) == digest
    all_files = sorted(HOSTED.iterdir())
    receipt = {
        "component": "C23",
        "kind": "Hosted acceptance of local preparation; real runtime gates remain open",
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "source_commit": SOURCE,
        "branch": "overhaul",
        "hosted_run": {k: run[k] for k in (
            "id", "head_sha", "head_branch", "event", "status", "conclusion",
            "created_at", "updated_at", "html_url", "run_attempt")},
        "checks": {
            "backend": {"passed": 5556, "skipped": 275, "precise_coverage_percent": 86.94},
            "postgres_suites": pg_counts,
            "postgres_total": sum(pg_counts),
            "frontend_v1_passed": 930,
            "frontend_legacy_passed": 132,
            "required_jobs": "all four successful",
            "lint_generated_contracts_typechecks_builds_audits": "passed",
            "migration_upsert_backup_restore": "passed",
        },
        "unchanged_preparation_source_files": source_files,
        "evidence": [pin(p) for p in all_files],
        "prior_pending_receipt": pin(pushed),
        "recorder": pin(Path(__file__).resolve()),
        "log_encoding": "GitHub decoded UTF-8 text, CRLF normalized to LF, one trailing newline",
        "recorder_attempt_history": [
            "First invocation stopped before writing a receipt: the recorder expected a non-existent step label 'Production dependency audit'",
            "Corrected to the actual shared step prefix 'Audit production'; downloaded logs and source were unchanged",
        ],
        "C23_complete": False,
        "real_execution_eligible": False,
        "cloud_resources_created": False,
        "automation": "PAUSED at user request",
        "limitations": [
            "Hosted Ubuntu unit tests do not exercise runsc or establish containment",
            "Linux worker, pinned image/runtime, real adapter and durable journal remain",
            "Resource/whole-job termination, safe output extraction and numerical gates remain",
            "Only the 17 preparation source paths are compared to the current checkout",
            "Unrelated local README, legacy deployment template, audits and benchmarks are preserved",
        ],
    }
    with target.open("x") as stream:
        json.dump(receipt, stream, indent=2, sort_keys=True)
        stream.write("\n")
    print(json.dumps({"receipt": pin(target), "source_files": len(source_files),
                      "backend_passed": 5556, "C23_complete": False}))


if __name__ == "__main__":
    main()
