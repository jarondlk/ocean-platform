"""Read-only prerequisite reconciliation for C24 development planning.

This is receipt/source verification, not an application or cloud acceptance test.
The default creates a new receipt; --verify-only changes no existing receipt.
"""

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[6]
OUT = Path(__file__).resolve().parent
EVIDENCE = ROOT / "docs/plans/ocean-v1/evidence"
ACCEPTED = "f6f823b5ee9a93d68a9498c4037bce82d3c44954"


def read(path):
    return json.loads(path.read_text())


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git(*args):
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def committed_digest(commit, name):
    return hashlib.sha256(
        subprocess.check_output(["git", "show", f"{commit}:{name}"], cwd=ROOT)
    ).hexdigest()


def verify():
    baseline = read(OUT / "baseline.json")
    assert git("branch", "--show-current") == "overhaul"
    subprocess.run(
        ["git", "merge-base", "--is-ancestor", ACCEPTED, baseline["base_commit"]],
        cwd=ROOT, check=True,
    )
    for name, expected in baseline["protected_sha256"].items():
        assert digest(ROOT / name) == expected, name

    # New C24 receipts may be added. Every older tracked evidence blob stays exact.
    changes = git(
        "diff", "--name-only", baseline["base_commit"], "--",
        "docs/plans/ocean-v1/evidence",
    ).splitlines()
    assert all(name.startswith("docs/plans/ocean-v1/evidence/C24/") for name in changes)
    assert git(
        "rev-parse", baseline["base_commit"] + ":docs/plans/ocean-v1/evidence"
    ) == baseline["evidence_tree"]

    c20 = read(EVIDENCE / "C20/delivery.json")
    assert c20["hosted_ci"]["run"]["conclusion"] == "success"
    assert c20["hosted_ci"]["run"]["head_sha"] == c20["source_commit"]
    for name, expected in c20["delivery_evidence_files"].items():
        assert digest(ROOT / name) == expected, name
    supersessions = {}
    current_source = {}
    for name, historical in c20["tested_transitive_source_files"].items():
        assert committed_digest(c20["source_commit"], name) == historical, name
        current = digest(ROOT / name)
        assert current == committed_digest(ACCEPTED, name), name
        current_source[name] = current
        if current != historical:
            supersessions[name] = {
                "C20_sha256": historical,
                "current_accepted_sha256": current,
                "latest_source_change": git("log", "-1", "--format=%H %s", "--", name),
                "acceptance": "Later C21/C22/C23 changes covered by accepted f6f823b hosted CI; original C20 receipt retained",
            }

    c23 = read(EVIDENCE / "C23/completion-20261028.json")
    assert c23["status"] == "Complete" and c23["required_CI_complete"]
    assert c23["accepted_source_commit"] == ACCEPTED
    for name, expected in c23["receipt_sha256"].items():
        assert digest(EVIDENCE / "C23" / name) == expected, name
    hosted_path = EVIDENCE / "C23/operator-hosted-f6f823b/receipt.json"
    hosted = read(hosted_path)
    assert hosted["source_commit"] == ACCEPTED and hosted["required_hosted_CI_complete"]
    assert len(hosted["required_job_results"]) == 4
    assert set(hosted["required_job_results"].values()) == {"success"}
    run = read(hosted_path.parent / "run.json")
    assert run["head_sha"] == ACCEPTED and run["conclusion"] == "success"
    for name, expected in hosted["source_files"].items():
        assert digest(ROOT / name) == expected, name
        assert committed_digest(ACCEPTED, name) == expected, name
        current_source[name] = expected
    raw = read(EVIDENCE / "C23/retained-final-audit-20261028/final-receipt.json")
    assert raw["actual_retained_acceptance_passed"]
    assert len(raw["results"]) == 2 and all(case["passed"] for case in raw["results"].values())

    return {
        "version": "c24-development-readiness-v1",
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "base_commit": baseline["base_commit"],
        "branch": "overhaul",
        "component_implementation_status": "Not started",
        "ready_for_offline_C24_development": True,
        "C24_acceptance_or_deployment_claimed": False,
        "working_public_origin": baseline["working_public_origin"],
        "hostname_state": baseline["hostname_state"],
        "C20_accepted_source": c20["source_commit"],
        "C20_transitive_source_entries_reconciled": len(c20["tested_transitive_source_files"]),
        "C20_original_delivery_evidence_preserved": len(c20["delivery_evidence_files"]),
        "intentional_C20_source_supersessions": supersessions,
        "current_accepted_source": ACCEPTED,
        "current_source_files": dict(sorted(current_source.items())),
        "C23_actual_source_entries": len(hosted["source_files"]),
        "C23_actual_retained_cases_passed": 2,
        "hosted_run": hosted["run_url"],
        "hosted_job_results": hosted["required_job_results"],
        "prerequisite_receipts_sha256": {
            str(path.relative_to(ROOT)): digest(path)
            for path in (
                EVIDENCE / "C20/delivery.json",
                EVIDENCE / "C23/completion-20261028.json",
                hosted_path,
                EVIDENCE / "C23/retained-final-audit-20261028/final-receipt.json",
            )
        },
        "prior_evidence_tree": baseline["evidence_tree"],
        "prior_tracked_evidence_preserved": baseline["prior_tracked_evidence_files"],
        "unrelated_paths_preserved": len(baseline["protected_sha256"]),
        "new_application_tests": "Not run: preparation changes documentation/evidence only; existing accepted results retained",
        "cloud_DNS_TLS_OAuth_writes": "none",
        "live_configuration_gates": [
            "Explicit independent whole-site GCP targets and current IAM/network review",
            "DNS control, exact beta record, verified TLS/ingress and no legacy routing change",
            "Independent OAuth client, host-only sessions, secrets and cross-site negative checks",
            "Authenticated v1 serving host and real private Cloud Tasks adapter; neither supplied by static preview/fake queue",
            "Worker production supervisor/health/drain wiring, two-job capacity and qualified crash/reboot recovery",
            "Whole-site retention/backup/budget/rollout inputs and concrete live-action authorization",
        ],
        "scheduler": "PAUSED",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify-only", action="store_true")
    args = parser.parse_args()
    receipt = verify()
    if not args.verify_only:
        with (OUT / "verification.json").open("x") as stream:
            json.dump(receipt, stream, indent=2, sort_keys=True)
            stream.write("\n")
    print(json.dumps({
        "ready_for_offline_C24_development": True,
        "C20_entries": receipt["C20_transitive_source_entries_reconciled"],
        "intentional_supersessions": len(receipt["intentional_C20_source_supersessions"]),
        "C23_source_entries": receipt["C23_actual_source_entries"],
        "prior_evidence_preserved": receipt["prior_tracked_evidence_preserved"],
        "C24_implementation": "Not started",
    }))


if __name__ == "__main__":
    main()
