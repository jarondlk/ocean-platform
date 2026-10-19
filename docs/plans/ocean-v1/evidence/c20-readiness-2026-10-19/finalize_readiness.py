"""Select local C20 only after C19 exact-source delivery is committed/pushed."""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
import subprocess

ROOT = Path(__file__).resolve().parents[5]
HERE = Path(__file__).resolve().parent
PLAN = ROOT / "docs/plans/ocean-v1"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    return json.loads(path.read_text())


def save(path, value):
    with path.open("x") as stream:
        stream.write(json.dumps(value, indent=2) + "\n")


def git(*args):
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


assert not (HERE / "verification.json").exists(), "Final readiness already frozen"
assert git("branch", "--show-current") == "overhaul"
head = git("rev-parse", "HEAD")
assert git("rev-parse", "origin/overhaul") == head, "C19 delivery must be pushed first"
pending = read(HERE / "pending-verification.json")
workflow = ".github/workflows/tests.yml"
amendment_path = PLAN / "evidence/C19/ci-budget-amendment/verification.json"
amendment = read(amendment_path)
amended = read(amendment_path.with_name("accepted-source.json"))
assert amendment["original_source_commit"] == pending["C19_source"]
assert amendment["original13_application_test_sources_unchanged"]
assert sha(ROOT / workflow) == amended["files"][workflow]
original_workflow = subprocess.check_output(["git", "show", pending["C19_source"] + ":" + workflow], cwd=ROOT)
assert original_workflow.replace(b"timeout-minutes: 20", b"timeout-minutes: 30", 1) == (ROOT / workflow).read_bytes()
original_feature_source = pending["C19_source"]
for key in ("formal_current_source_files", "C19_tested_transitive_source_files"):
    pending[key][workflow] = amended["files"][workflow]
entry = pending["source_entries"]["C17"][workflow]
entry["acceptance_chain"].append({"component": "C19 CI budget amendment", "receipt": str(amendment_path.with_name("accepted-source.json").relative_to(ROOT)), "sha256": amended["files"][workflow]})
entry["current_sha256"] = amended["files"][workflow]
entry["intentional_later_supersession"] = True
for key in ("formal_current_source_files", "C19_tested_transitive_source_files"):
    for path, expected in pending[key].items():
        assert sha(ROOT / path) == expected, path
for path, expected in pending["original_receipt_and_planning_pins_sha256"].items():
    if "/evidence/" in path:
        assert sha(ROOT / path) == expected, path
delivery_path = PLAN / "evidence/C19/delivery.json"
delivery = read(delivery_path)
ci = delivery["hosted_ci"]
assert ci["source_commit"] == ci["run"]["head_sha"] == "4618188f589b6b6e3d50dee0bdf3343be0ec3484"
pending["C19_source"] = ci["source_commit"]
assert ci["run"]["status"] == "completed" and ci["run"]["conclusion"] == "success"
subprocess.run(["git", "merge-base", "--is-ancestor", pending["C19_source"], head], cwd=ROOT, check=True)
committed = subprocess.check_output(["git", "show", head + ":docs/plans/ocean-v1/evidence/C19/delivery.json"], cwd=ROOT)
assert hashlib.sha256(committed).hexdigest() == sha(delivery_path)
for path, expected in delivery["files"].items():
    assert sha(ROOT / path) == expected, path
    content = subprocess.check_output(["git", "show", pending["C19_source"] + ":" + path], cwd=ROOT)
    assert hashlib.sha256(content).hexdigest() == expected, path
for component in ("C04", "C17", "C19"):
    assert any(line.startswith("| [" + component) and "| Complete |" in line for line in (PLAN / "STATUS.md").read_text().splitlines())
pending["original_receipt_and_planning_pins_sha256"][str(amendment_path.relative_to(ROOT))] = sha(amendment_path)
pending["original_receipt_and_planning_pins_sha256"][str(amendment_path.with_name("accepted-source.json").relative_to(ROOT))] = sha(amendment_path.with_name("accepted-source.json"))
pending["formal_current_source_sha256"] = hashlib.sha256("".join(f"{path}:{value}\n" for path, value in sorted(pending["formal_current_source_files"].items())).encode()).hexdigest()
result = {
    **pending, "state": "Ready; C04/C17/C19 prerequisites reconcile and C19 hosted delivery is committed/pushed",
    "audited_at": datetime.now(timezone.utc).isoformat(), "head": head,
    "preliminary_receipt_sha256": sha(HERE / "pending-verification.json"),
    "C19_delivery_receipt_sha256": sha(delivery_path), "C19_hosted_ci": ci["run"],
    "C19_original_feature_source": original_feature_source,
    "C19_CI_timeout_only_supersession": {"receipt": str(amendment_path.relative_to(ROOT)), "sha256": sha(amendment_path), "original_monitored_paths_unchanged": 86, "feature_test_paths_unchanged": 13, "workflow_path": workflow, "new_exact_source_hosted_complete": True},
    "component_selected": True, "requires_refresh_after_C19_delivery": False,
    "planning_pin_qualification": "Preliminary ledger/handoff hashes are historical through C19 delivery. Original evidence pins are preserved; effective current source pins were revalidated after the documented CI-only timeout supersession.",
    "selection_authorization": "Standing human authorization for sequential local implementation, subagents and commits/pushes. Select C20 local API/persistence/replay/dispatch/transport; no real cloud/model/data action.",
}
save(HERE / "verification.json", result)
(HERE / "final-audit.md").write_text(
    "# C20 final readiness\n\nAll36 formal entries/34unique paths reconcile to immutable accepted C04/C17/C19\n"
    "source receipts, including C17 auth and C19 default-off config supersessions.\n"
    "All13 feature/test and86 prior monitored paths plus23 C18 frontend paths are\n"
    "unchanged. The sole workflow timeout20→30-minute supersession is verified\n"
    "separately. C19 source4618188 exact-source CI passes and delivery is committed\n"
    "and pushed. No external decision blocks isolated local C20 implementation.\n\n"
    "Select all3 C20 checkpoints under standing sequential authorization. Implement\n"
    "additive v1 run/event/outbox/lease/step persistence, owner APIs, fake dispatch,\n"
    "versioned C19 replay and concrete frontend transport/discovery. Pending journal,\n"
    "current owner, lost-ack, clarification and approval-state gaps are C20 work,\n"
    "not prior-component acceptance claims. Use sealed synthetic sources, TEST\n"
    "principals, fake structured runtimes and guarded disposable local PostgreSQL.\n"
    "No real queue/resource provisioning, provider, transfer or deployment action.\n"
    "Actual cloud integration remains separately gated on authorization/configuration.\n"
)
out = PLAN / "evidence/C20"
out.mkdir(exist_ok=True)
previous = read(PLAN / "evidence/C19/start-snapshot.json")
prior = {path: sha(ROOT / path) for path in git("ls-files", "docs/plans/ocean-v1/evidence").splitlines() if (ROOT / path).is_file()}
save(out / "start-snapshot.json", {
    "component": "C20", "implementation_base": head,
    "readiness_receipt": str((HERE / "verification.json").relative_to(ROOT)),
    "readiness_receipt_sha256": sha(HERE / "verification.json"),
    "formal_source_entries": result["source_entries"], "formal_current_source_files": result["formal_current_source_files"],
    "C19_accepted_source": delivery["files"], "C19_tested_transitive_source_files": result["C19_tested_transitive_source_files"],
    "C18_accepted_source": read(PLAN / "evidence/C18/accepted-source.json")["files"],
    "C19_delivery_receipt_sha256": sha(delivery_path),
    "preservation": previous["preservation"], "prior_evidence_files": prior,
    "authorization": result["selection_authorization"],
})
path = PLAN / "components/C20-durable-execution.md"
path.write_text(path.read_text().replace("**Status:** Not started.", "**Status:** In progress; readiness passed and all3 local checkpoints selected.", 1))
path = PLAN / "components.json"
data = read(path)
assert "C20" not in data["authorized_components"]
data["authorized_components"].append("C20")
path.write_text(json.dumps(data, indent=2) + "\n")
path = PLAN / "STATUS.md"
text = path.read_text().replace("C20–C27 remain Not started.", "C20 is In progress; C21–C27 remain Not started.")
text = text.replace("| [C20 — Durable research execution](components/C20-durable-execution.md) | Not started | None | Not run | Not created |", "| [C20 — Durable research execution](components/C20-durable-execution.md) | In progress | All36 prerequisite entries reconcile; API/persistence/replay/transport checkpoints selected | C19 hosted delivery complete; implementation acceptance pending | [C20](handoffs/C20.md) |")
path.write_text(text)
path = PLAN / "README.md"
path.write_text(path.read_text().replace("C20–C27 are not started.", "C20 is In progress; C21–C27 are not started.") + "\nC20 final36-entry/34-path readiness passes after C19 exact-source delivery; isolated local implementation is selected. [Handoff](handoffs/C20.md).\n")
(PLAN / "handoffs/C20.md").write_text(
    "# C20 — Durable research execution\n\nState: In progress; all3 local checkpoints selected after36-entry/34-path final\n"
    "readiness and C19 exact-source hosted delivery. Base " + head + ".\n"
    "User authorizes sequential local implementation, subagents and commits/pushes.\n\n"
    "Implement additive run/event/outbox/step/lease persistence, owner-scoped APIs,\n"
    "private dispatch abstraction/fake queue, conservative persisted budgets and\n"
    "versioned C19 replay. Complete six frontend HTTP actions plus run discovery,\n"
    "lost-ack intent recovery, approval wait and explicit configured execution mode.\n"
    "No C21 answer or experiment approval is fabricated. Current owner/policy checks\n"
    "apply to replay and final publication; service dispatch identity is separate.\n\n"
    "Next: agree owned interfaces, implement and test local checkpoints, disposable\n"
    "PostgreSQL race/recovery checks, frontend transport and reload recovery, then\n"
    "source checkpoint and hosted delivery. Preserve prior receipts/science/legacy\n"
    "and unrelated files. No actual cloud queue/worker, real model/data/transfer or\n"
    "deployment operation is authorized; live configuration remains an external gate.\n"
)
print(json.dumps({"ready": True, "formal_entries": 36, "unique_paths": 34, "prior_evidence": len(prior), "readiness_sha256": sha(HERE / "verification.json")}))
