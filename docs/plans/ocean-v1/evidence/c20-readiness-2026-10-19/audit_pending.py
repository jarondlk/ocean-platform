"""Preliminary C20 source reconciliation; final selection awaits C19 delivery."""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
import subprocess

ROOT = Path(__file__).resolve().parents[5]
HERE = Path(__file__).resolve().parent
PLAN = Path("docs/plans/ocean-v1")
EVIDENCE = PLAN / "evidence"
FORMAL = ("C04", "C17", "C19")


def sha(path):
    return hashlib.sha256((ROOT / path).read_bytes()).hexdigest()


def aggregate(files):
    return hashlib.sha256("".join(f"{p}:{h}\n" for p, h in sorted(files.items())).encode()).hexdigest()


def read(path):
    return json.loads((ROOT / path).read_text())


def git(*arguments):
    return subprocess.check_output(["git", *arguments], cwd=ROOT, text=True).strip()


def verify(files):
    assert all(sha(path) == expected for path, expected in files.items())


assert not (HERE / "pending-verification.json").exists(), "Immutable preliminary audit already exists"
assert git("branch", "--show-current") == "overhaul"
head = git("rev-parse", "HEAD")
sequence, originals, pins = [], {}, {}
for index in range(1, 20):
    component = f"C{index:02d}"
    original = EVIDENCE / component / "verification.json"
    originals[component] = read(original)
    pins[str(original)] = sha(original)
    selected = EVIDENCE / component / "accepted-source.json"
    if not (ROOT / selected).exists():
        selected = original
    data = read(selected)
    assert aggregate(data["files"]) == data["source_sha256"]
    pins[str(selected)] = sha(selected)
    sequence.append((component, selected, data["files"]))
    if component == "C02":
        historical = EVIDENCE / "delivery-2026-10-14/verification.json"
        sequence.append(("C01/C02 delivery audit", historical, read(historical)["files"]))
        pins[str(historical)] = sha(historical)
rows, current = {}, {}
for component in FORMAL:
    rows[component] = {}
    for path, original_sha in originals[component]["files"].items():
        chain = [{"component": component, "receipt": str(EVIDENCE / component / "verification.json"), "sha256": original_sha}]
        started = False
        for step, receipt, files in sequence:
            if step == component:
                started = True
            if started and path in files and files[path] != chain[-1]["sha256"]:
                chain.append({"component": step, "receipt": str(receipt), "sha256": files[path]})
        assert sha(path) == chain[-1]["sha256"], (component, path)
        current[path] = sha(path)
        rows[component][path] = {"original_sha256": original_sha, "current_sha256": sha(path), "intentional_later_supersession": sha(path) != original_sha, "acceptance_chain": chain}
source = "a38b181cb7ac6472095a2b279e3c0aacbabb8e5c"
assert head == source
accepted = read(EVIDENCE / "C19/accepted-source.json")
verify(accepted["files"])
tested = read(EVIDENCE / "C19/backend-tested-source.json")
assert tested["before_sha256"] == tested["after_sha256"] and not tested["changed"]
verify(tested["after_sha256"])
verify(read(EVIDENCE / "C18/accepted-source.json")["files"])
for path, expected in accepted["files"].items():
    content = subprocess.check_output(["git", "show", source + ":" + path], cwd=ROOT)
    assert hashlib.sha256(content).hexdigest() == expected
hosted = {}
for component, path in (
    ("C04", EVIDENCE / "c05-readiness-2026-10-15/hosted-ci.json"),
    ("C17", EVIDENCE / "C17/hosted-ci.json"),
):
    data = read(path)
    run = data.get("run", data)
    assert run["conclusion"] == "success"
    commit = data["source_commit"]
    subprocess.run(["git", "merge-base", "--is-ancestor", commit, head], cwd=ROOT, check=True)
    pins[str(path)] = sha(path)
    hosted[component] = {"receipt": str(path), "source_commit": commit, "run": run, "source_is_ancestor": True}
    for source_path, expected in originals[component]["files"].items():
        content = subprocess.check_output(["git", "show", commit + ":" + source_path], cwd=ROOT)
        assert hashlib.sha256(content).hexdigest() == expected, (component, source_path)
for name in ("README.md", "MASTER_PLAN.md", "DECISIONS.md", "STATUS.md", "ACCEPTANCE_MAP.md", "SITE_SEPARATION.md", "UI_UX_BRIEF.md", "PROMPTS.md", "components/C20-durable-execution.md", "C19_AGENT_CONTROLLER_CONTRACT.md", "C18_CHAT_WORKSPACE_CONTRACT.md", *[f"handoffs/{c}.md" for c in FORMAL]):
    pins[str(PLAN / name)] = sha(PLAN / name)
pins[str(Path(__file__).resolve().relative_to(ROOT))] = sha(Path(__file__).resolve().relative_to(ROOT))
result = {
    "component": "C20", "state": "Preliminary sources reconciled; C19 source-bound hosted delivery remains required before selection",
    "audited_at": datetime.now(timezone.utc).isoformat(), "head": head, "branch": "overhaul",
    "formal_prerequisites": list(FORMAL), "formal_source_entries": sum(len(x) for x in rows.values()), "unique_source_paths": len(current),
    "source_entries": rows, "formal_current_source_files": current, "formal_current_source_sha256": aggregate(current),
    "C19_source": source, "C19_all13_sources_equal_source_commit": True,
    "C19_tested_transitive_source_files": tested["after_sha256"], "C18_all23_sources_unchanged": True,
    "original_receipt_and_planning_pins_sha256": pins, "prior_hosted_prerequisites": hosted,
    "requires_refresh_after_C19_delivery": True, "component_selected": False,
    "implementation_gaps_owned_by_C20": [
        "Versioned C19 restore/replay with stable logical steps and committed raw outputs/actions; budget-counter restoration alone is insufficient.",
        "Worker current-owner identity from explicit v1 store; private dispatch identity cannot replace owner authorization.",
        "Atomic outbox/events/payloads/step commits, lease epochs and final cancel/complete fencing; conservative active-time reservation across crashes.",
        "Owner/conversation-scoped run discovery for reload; six C18 actions alone cannot recover unknown run IDs.",
        "Retained frontend mutation intents/idempotency keys across lost acknowledgements; explicit configured execution capability and awaiting_approval state.",
        "Immutable clarification inputs and linked continuation semantics; preserve frozen snapshot/revision and distinguish C21 final synthesis.",
    ],
    "external_gates": ["No live queue/controller provisioning, paid provider, real data transfer or deployment is authorized by local readiness.", "Actual GCP integration requires separate concrete authorization and target configuration; local fake queue/isolated PostgreSQL are allowed."],
}
with (HERE / "pending-verification.json").open("x") as stream:
    stream.write(json.dumps(result, indent=2) + "\n")
print(json.dumps({"state": result["state"], "formal_entries": result["formal_source_entries"], "unique_paths": len(current), "transitive_paths": len(tested["after_sha256"])}))
