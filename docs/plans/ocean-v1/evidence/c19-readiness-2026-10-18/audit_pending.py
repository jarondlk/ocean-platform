"""Read-only preliminary C19 prerequisite audit; no selection or implementation.

Only this new readiness directory is written. Component receipts and source files
are read without running application tests, services, providers or Git mutations.
The parent must recheck after C18 source/hosted delivery before advancing.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[5]
HERE = Path(__file__).parent
PLANS = Path("docs/plans/ocean-v1")
EVIDENCE = PLANS / "evidence"
FORMAL = ["C01", "C06", "C14", "C17"]


def digest(path):
    return hashlib.sha256((ROOT / path).read_bytes()).hexdigest()


def aggregate(files):
    return hashlib.sha256("".join(f"{path}:{sha}\n" for path, sha in sorted(files.items())).encode()).hexdigest()


def receipt(path):
    data = json.loads((ROOT / path).read_text())
    if "files" in data and "source_sha256" in data:
        assert aggregate(data["files"]) == data["source_sha256"], str(path)
    return data


def git(*arguments):
    return subprocess.check_output(["git", *arguments], cwd=ROOT, text=True).strip()


def main():
    output = HERE / "pending-verification.json"
    if output.exists():
        raise SystemExit("Refusing to overwrite this preliminary audit")
    assert git("branch", "--show-current") == "overhaul"
    head = git("rev-parse", "HEAD")
    sequence = []
    originals = {}
    pins = {}
    for index in range(1, 18):
        component = f"C{index:02d}"
        original_path = EVIDENCE / component / "verification.json"
        original = receipt(original_path)
        pins[str(original_path)] = digest(original_path)
        originals[component] = (original_path, original)
        accepted_path = EVIDENCE / component / "accepted-source.json"
        if not (ROOT / accepted_path).exists():
            accepted_path = original_path
        accepted = receipt(accepted_path)
        pins[str(accepted_path)] = digest(accepted_path)
        sequence.append((component, accepted_path, accepted["files"]))
        if component == "C02":
            audit_path = EVIDENCE / "delivery-2026-10-14/verification.json"
            audit = receipt(audit_path)
            pins[str(audit_path)] = digest(audit_path)
            sequence.append(("C01/C02 delivery audit", audit_path, audit["files"]))
    rows = {}
    source_files = {}
    for component in FORMAL:
        original_path, original = originals[component]
        rows[component] = {}
        for path, original_sha in original["files"].items():
            current = digest(path)
            chain = [{"component": component, "receipt": str(original_path), "sha256": original_sha}]
            started = False
            for step, source_receipt, files in sequence:
                if step == component:
                    started = True
                if started and path in files and files[path] != chain[-1]["sha256"]:
                    chain.append({"component": step, "receipt": str(source_receipt), "sha256": files[path]})
            assert current == chain[-1]["sha256"], (component, path, current, chain)
            rows[component][path] = {"original_sha256": original_sha, "current_sha256": current, "intentional_later_supersession": original_sha != current, "acceptance_chain": chain}
            source_files[path] = current
    hosted = {}
    for component in ["C06", "C14", "C17"]:
        path = EVIDENCE / component / "delivery.json"
        data = receipt(path)
        pins[str(path)] = digest(path)
        ci = data["hosted_ci"]
        run = ci.get("run", ci)
        source = ci["source_commit"]
        assert run["conclusion"] == "success"
        subprocess.run(["git", "merge-base", "--is-ancestor", source, head], cwd=ROOT, check=True)
        accepted_path = EVIDENCE / component / "accepted-source.json"
        if not (ROOT / accepted_path).exists():
            accepted_path = EVIDENCE / component / "verification.json"
        accepted = receipt(accepted_path)
        for source_path, sha in accepted["files"].items():
            actual = subprocess.check_output(["git", "show", f"{source}:{source_path}"], cwd=ROOT)
            assert hashlib.sha256(actual).hexdigest() == sha, (component, source_path)
        original_path = EVIDENCE / component / "verification.json"
        expected = data.get("original_local_receipt_sha256", data.get("original_local_receipt", {}).get("sha256"))
        assert expected == digest(original_path)
        hosted[component] = {"receipt": str(path), "receipt_sha256": digest(path), "source_commit": source, "run_id": run.get("id", run.get("run_id")), "url": run.get("html_url", run.get("url")), "conclusion": run["conclusion"], "source_files_in_commit_equal_accepted_map": len(accepted["files"]), "source_is_ancestor_of_current_head": True}
    docs = [
        "README.md", "MASTER_PLAN.md", "DECISIONS.md", "STATUS.md", "ACCEPTANCE_MAP.md", "SITE_SEPARATION.md", "UI_UX_BRIEF.md", "PROMPTS.md", "components/C19-agent-controller.md",
        *[f"handoffs/{component}.md" for component in FORMAL],
        "C14_CATALOGUE_SERVICE_CONTRACT.md", "C17_INVESTIGATION_CONTRACT.md",
    ]
    for path in docs:
        pins[str(PLANS / path)] = digest(PLANS / path)
    c18_client = EVIDENCE / "C18/client-verification.json"
    client = json.loads((ROOT / c18_client).read_text())
    for path, sha in client["source_after_sha256"].items():
        assert digest(path) == sha, path
    pins[str(c18_client)] = digest(c18_client)
    result = {
        "component": "C19", "state": "Preliminary prerequisites reconciled; pending C18 delivery and parent final readiness selection",
        "audited_at": datetime.now(timezone.utc).isoformat(), "branch": "overhaul", "head": head,
        "formal_prerequisites": FORMAL, "formal_source_entries": sum(map(len, rows.values())), "unique_source_paths": len(source_files),
        "formal_current_source_sha256": aggregate(source_files), "formal_current_source_files": source_files, "source_entries": rows,
        "original_receipt_and_planning_pins_sha256": pins, "hosted_receipts_reused_without_network_queries": hosted,
        "C17_current19_equal_accepted_source": len(rows["C17"]) == 19 and all(not row["intentional_later_supersession"] for row in rows["C17"].values()),
        "C18_client4_unchanged": True, "application_tests_run": False, "services_started": False, "source_implementation_edits": False,
        "component_selected": False, "requires_refresh_after_C18_delivery": True,
        "known_gaps_owned_by_C19": [
            "C06 supplies strict provider-independent structured generation outcomes, but C19 must define the exploration action/observation/budget/checklist schema",
            "C17 stores pins; C14 tools authorize scope but do not independently interpret C17 pins. C19 must enforce compatible effective restrictions before dispatch",
            "C01 publication compatibility is a bounded exact-workflow contract, not a generic free-question scope parser; new descriptive qualifiers need deterministic conservative resolution",
            "Inventory and requested-fact/dataset-disposition completion are not implemented; model finish must not authorize completion",
            "No production durable execution/queue/run route exists; C20 owns that integration and C21 owns final synthesis/evidence presentation",
        ],
        "missing_user_decisions_for_isolated_local_fake_runtime_implementation": [],
        "external_gates": ["No paid/live model calls authorized", "No scientific approval, real-data acquisition/transfer or regeneration inferred", "No cloud provisioning/deployment, production OIDC or production capacity acceptance inferred"],
    }
    with output.open("x") as stream:
        json.dump(result, stream, indent=2, sort_keys=True)
        stream.write("\n")
    print(json.dumps({"pending": True, "formal_entries": result["formal_source_entries"], "unique_paths": len(source_files), "formal_source_sha256": result["formal_current_source_sha256"], "receipt_sha256": digest(output.relative_to(ROOT))}, sort_keys=True))


if __name__ == "__main__":
    main()
