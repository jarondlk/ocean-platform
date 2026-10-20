"""Reconcile C21 prerequisites without running tests or selecting a component.

Default execution creates one immutable pending receipt. Import collect_audit for
finalization, or use --final only after the C20 hosted delivery checkpoint is
committed and pushed. --check revalidates an existing receipt without writing it.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]
PLAN = Path("docs/plans/ocean-v1")
EVIDENCE = PLAN / "evidence"
SOURCE = "fc46da36aa27c203357a1b5874a02378ae089847"
FORMAL = ("C05", "C06", "C07", "C13", "C19", "C20")
PROTECTED_COUNTS = {"unrelated_files": 30, "scientific_artifacts": 7,
                    "serving_files": 2, "legacy_frontend_files": 106}


def git(*arguments: str) -> str:
    return subprocess.check_output(["git", *arguments], cwd=ROOT, text=True).strip()


def sha(path: str | Path) -> str:
    return hashlib.sha256((ROOT / path).read_bytes()).hexdigest()


def aggregate(files: dict[str, str]) -> str:
    return hashlib.sha256("".join(f"{path}:{digest}\n" for path, digest in sorted(files.items())).encode()).hexdigest()


def read(path: str | Path) -> dict:
    return json.loads((ROOT / path).read_text())


def verify(files: dict[str, str]) -> None:
    changed = [path for path, digest in files.items() if not (ROOT / path).is_file() or sha(path) != digest]
    if changed:
        raise RuntimeError("Changed or missing source/evidence: " + repr(changed))


def ancestor(before: str, after: str) -> None:
    subprocess.run(["git", "merge-base", "--is-ancestor", before, after], cwd=ROOT, check=True)


def commit_sha(commit: str, path: str | Path) -> str:
    return hashlib.sha256(subprocess.check_output(["git", "show", f"{commit}:{path}"], cwd=ROOT)).hexdigest()


def source_map(path: Path, pins: dict[str, str]) -> dict[str, str]:
    data = read(path)
    files = data["files"]
    if aggregate(files) != data["source_sha256"]:
        raise RuntimeError("Invalid source-map aggregate: " + str(path))
    pins[str(path)] = sha(path)
    if commit_sha(SOURCE, path) != pins[str(path)]:
        raise RuntimeError("Receipt differs from C20 source checkpoint: " + str(path))
    return files


def committed_evidence() -> dict[str, str]:
    """Hash Git's retained blobs, not a working-tree-generated baseline."""
    listing = subprocess.check_output(["git", "ls-tree", "-r", "-z", SOURCE, "--", str(EVIDENCE)], cwd=ROOT)
    entries = []
    for record in listing.split(b"\0"):
        if not record:
            continue
        metadata, path = record.split(b"\t", 1)
        mode, kind, identity = metadata.split()
        if kind != b"blob" or mode not in {b"100644", b"100755"}:
            raise RuntimeError("Unexpected evidence object in source checkpoint")
        entries.append((path.decode("utf-8"), identity))
    result = {}
    with subprocess.Popen(["git", "cat-file", "--batch"], cwd=ROOT,
                          stdin=subprocess.PIPE, stdout=subprocess.PIPE) as process:
        if process.stdin is None or process.stdout is None:
            raise RuntimeError("Git object reader unavailable")
        for path, identity in entries:
            process.stdin.write(identity + b"\n")
            process.stdin.flush()
            actual, kind, size = process.stdout.readline().split()
            if actual != identity or kind != b"blob":
                raise RuntimeError("Unexpected retained Git object")
            body = process.stdout.read(int(size))
            if len(body) != int(size) or process.stdout.read(1) != b"\n":
                raise RuntimeError("Incomplete retained Git object")
            result[path] = hashlib.sha256(body).hexdigest()
        process.stdin.close()
        if process.wait() != 0:
            raise RuntimeError("Git object reader failed")
    verify(result)
    return result


def hosted(component: str, path: Path, files: dict[str, str], pins: dict[str, str]) -> dict:
    data = read(path)
    ci = data.get("hosted_ci", data)
    run = ci.get("run", ci)
    source = ci.get("source_commit", data.get("source_commit", data.get("implementation_commit")))
    if not source or run.get("conclusion") != "success":
        raise RuntimeError("Missing successful source-bound hosted receipt: " + component)
    if run.get("head_sha", source) != source:
        raise RuntimeError("Hosted receipt has a different source: " + component)
    ancestor(source, SOURCE if component != "C20" else git("rev-parse", "HEAD"))
    for item, expected in files.items():
        if commit_sha(source, item) != expected:
            raise RuntimeError("Hosted source-map mismatch: " + component + ":" + item)
    pins[str(path)] = sha(path)
    return {"receipt": str(path), "receipt_sha256": sha(path), "source_commit": source,
            "run_id": run.get("id", run.get("run_id")),
            "url": run.get("html_url", run.get("url")),
            "conclusion": "success", "all_receipt_sources_match_hosted_commit": True}


def collect_audit(*, require_delivery: bool = False) -> dict:
    if git("branch", "--show-current") != "overhaul":
        raise RuntimeError("Readiness must remain on overhaul")
    head = git("rev-parse", "HEAD")
    ancestor(SOURCE, head)
    pins, originals, sequence = {}, {}, []
    for index in range(1, 21):
        component = f"C{index:02d}"
        original = EVIDENCE / component / "verification.json"
        original_files = source_map(original, pins)
        originals[component] = original_files
        sequence.append((component, original, original_files))
        selected = EVIDENCE / component / "accepted-source.json"
        if (ROOT / selected).exists():
            sequence.append((component, selected, source_map(selected, pins)))
        for suffix in {"C13": ("method-alias-amendment/accepted-source.json",),
                       "C19": ("ci-budget-amendment/accepted-source.json",)}.get(component, ()):
            amendment = EVIDENCE / component / suffix
            sequence.append((component, amendment, source_map(amendment, pins)))

    rows, current, summary = {}, {}, {}
    for component in FORMAL:
        rows[component] = {}
        for path, original_hash in originals[component].items():
            chain, started = [], False
            for step, receipt, files in sequence:
                started = started or step == component
                if started and path in files and (not chain or files[path] != chain[-1]["sha256"]):
                    chain.append({"component": step, "receipt": str(receipt),
                                  "receipt_sha256": pins[str(receipt)], "sha256": files[path]})
            expected = chain[-1]["sha256"]
            if sha(path) != expected or commit_sha(SOURCE, path) != expected:
                raise RuntimeError("Unexplained formal source drift: " + component + ":" + path)
            current[path] = expected
            rows[component][path] = {"original_sha256": original_hash, "current_sha256": expected,
                                     "intentional_later_supersession": expected != original_hash,
                                     "acceptance_chain": chain}
        summary[component] = {"original_entries": len(rows[component]),
                              "superseded_entries": sum(row["intentional_later_supersession"] for row in rows[component].values())}

    c20 = read(EVIDENCE / "C20/verification.json")
    accepted = source_map(EVIDENCE / "C20/accepted-source.json", pins)
    if accepted != c20["files"] or aggregate(accepted) != c20["source_sha256"]:
        raise RuntimeError("C20 local/source receipts disagree")
    tested = c20["tested_transitive_source_files"]
    verify(tested)
    for path, digest in {**accepted, **tested}.items():
        if commit_sha(SOURCE, path) != digest:
            raise RuntimeError("C20 tested source differs from source checkpoint: " + path)
    verify(c20["evidence_files"])
    start_path = EVIDENCE / "C20/start-snapshot.json"
    start = read(start_path)
    if {key: len(values) for key, values in start["preservation"].items()} != PROTECTED_COUNTS:
        raise RuntimeError("Protected baseline counts changed")
    for values in start["preservation"].values():
        verify(values)
    verify(start["prior_evidence_files"])
    if len(start["prior_evidence_files"]) != 912:
        raise RuntimeError("Unexpected C20 prior-evidence baseline")
    tracked = committed_evidence()

    prior_hosted = {}
    for component, path, files in (
        ("C05", EVIDENCE / "c06-readiness-2026-10-15/verification.json", originals["C05"]),
        ("C06", EVIDENCE / "C06/delivery.json", originals["C06"]),
        ("C07", EVIDENCE / "C07/delivery.json", originals["C07"]),
        ("C13", EVIDENCE / "C13/delivery.json", read(EVIDENCE / "C13/method-alias-amendment/accepted-source.json")["files"]),
        ("C19", EVIDENCE / "C19/delivery.json", read(EVIDENCE / "C19/delivery.json")["files"]),
    ):
        prior_hosted[component] = hosted(component, path, files, pins)

    delivery_path = EVIDENCE / "C20/delivery.json"
    c20_delivery = {"present": (ROOT / delivery_path).exists(), "required_receipt": str(delivery_path),
                    "required_source_commit": SOURCE, "expected_ci_run_id": 39207358123,
                    "accepted": False, "documentation_checkpoint_committed_and_pushed": False}
    if require_delivery:
        if not c20_delivery["present"]:
            raise RuntimeError("C20 delivery.json is missing; hosted delivery remains pending")
        item = hosted("C20", delivery_path, accepted, pins)
        if item["source_commit"] != SOURCE:
            raise RuntimeError("C20 delivery refers to another source checkpoint")
        if commit_sha(head, delivery_path) != sha(delivery_path) or head == SOURCE:
            raise RuntimeError("C20 delivery must be committed in a separate documentation checkpoint")
        # This observes the locally recorded remote-tracking ref; it performs no
        # network fetch and is not a substitute for the root's push receipt.
        ancestor(head, "origin/overhaul")
        c20_delivery.update(item)
        c20_delivery.update(accepted=True, documentation_checkpoint_committed_and_pushed=True,
                            remote_tracking_qualification="HEAD is contained in local origin/overhaul; no network operation performed")

    for name in ("README.md", "MASTER_PLAN.md", "DECISIONS.md", "STATUS.md", "ACCEPTANCE_MAP.md",
                 "SITE_SEPARATION.md", "UI_UX_BRIEF.md", "PROMPTS.md", "components.json",
                 "components/C21-evidence-synthesis.md", "C19_AGENT_CONTROLLER_CONTRACT.md",
                 "C20_DURABLE_EXECUTION_CONTRACT.md", *[f"handoffs/{component}.md" for component in FORMAL]):
        pins[str(PLAN / name)] = sha(PLAN / name)
    for name in ("preparation.md", "formal-map.md", "audit_pending.py"):
        path = HERE / name
        pins[str(path.relative_to(ROOT))] = sha(path.relative_to(ROOT))
    return {
        "component": "C21", "state": "prerequisites_verified_awaiting_root_selection" if require_delivery else "pending-hosted-delivery",
        "audited_at": datetime.now(timezone.utc).isoformat(), "branch": "overhaul", "head": head,
        "source_commit": SOURCE, "component_selected": False,
        "ready_for_selection": require_delivery,
        "formal_prerequisites": list(FORMAL), "formal_source_summary": summary,
        "formal_source_entries": sum(len(entries) for entries in rows.values()), "unique_source_paths": len(current),
        "source_entries": rows, "formal_current_source_files": current, "formal_current_source_sha256": aggregate(current),
        "C20_all_accepted_source_files_match_commit": True, "C20_accepted_source_files": accepted,
        "C20_tested_transitive_source_files": tested, "C20_local_acceptance_checks": c20["checks"],
        "prior_hosted_prerequisites": prior_hosted, "C20_hosted_delivery": c20_delivery,
        "immutable_receipt_pins_sha256": {path: digest for path, digest in pins.items() if path.startswith(str(EVIDENCE)) and path in tracked},
        "original_receipt_and_planning_pins_sha256": pins,
        "preservation": {"protected_counts": PROTECTED_COUNTS, "protected_files": start["preservation"],
                         "C20_start_prior_evidence_count": 912, "C20_start_prior_evidence_files": start["prior_evidence_files"],
                         "source_commit_tracked_evidence_count": len(tracked), "source_commit_tracked_evidence_files": tracked,
                         "source_commit_tracked_evidence_sha256": aggregate(tracked),
                         "C20_local_evidence_files": c20["evidence_files"], "all_verified_unchanged": True},
        "required_before_implementation": [] if require_delivery else [
            "C20 exact-source hosted CI must finish successfully for fc46da36aa27c203357a1b5874a02378ae089847.",
            "Root must create C20/delivery.json and commit/push the separate delivery documentation checkpoint.",
            "Root must finalize a new C21 readiness receipt against delivered source and current protected/evidence state before selecting C21."],
        "checks_run": "Read-only source/receipt/Git/preservation reconciliation only; no application tests or services executed",
        "external_gates": [
            "No paid/live model calls, cloud provisioning/deployment or real-data acquisition/transfer authorized by readiness.",
            "Independent v1 target identities/storage/queues, transfer authority, scientific reviews and live acceptance remain separately documented gates.",
            "Local synthetic receipt/synthesis/access/retention/HTTP/UI implementation can proceed only after root final readiness and selection."],
    }


def check_receipt(path: Path) -> dict:
    receipt = json.loads(path.read_text())
    for key in ("formal_current_source_files", "C20_accepted_source_files", "C20_tested_transitive_source_files", "immutable_receipt_pins_sha256"):
        verify(receipt[key])
    preserved = receipt["preservation"]
    for values in preserved["protected_files"].values():
        verify(values)
    for key in ("C20_start_prior_evidence_files", "source_commit_tracked_evidence_files", "C20_local_evidence_files"):
        verify(preserved[key])
    return {"state": "recorded source/immutable-evidence/protected pins still match", "receipt_state_unchanged": receipt["state"],
            "qualification": "Mutable planning documentation pins are historical; no receipt rewritten and no readiness promoted"}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--final", action="store_true", help="Require committed/pushed C20 hosted delivery; never select C21")
    parser.add_argument("--output", type=Path, help="New receipt path relative to this directory; create only")
    parser.add_argument("--check", type=Path, help="Read-only verify an existing receipt relative to this directory")
    options = parser.parse_args()
    if options.check:
        if options.final or options.output:
            parser.error("--check cannot create or finalize a receipt")
        print(json.dumps(check_receipt(HERE / options.check)))
        return
    output = HERE / (options.output or ("verification.json" if options.final else "pending-verification.json"))
    if output.exists():
        raise RuntimeError("Immutable receipt already exists; use --check or another explicitly named new receipt")
    result = collect_audit(require_delivery=options.final)
    with output.open("x") as stream:
        json.dump(result, stream, indent=2)
        stream.write("\n")
    print(json.dumps({"state": result["state"], "formal_entries": result["formal_source_entries"],
                      "unique_paths": result["unique_source_paths"],
                      "tracked_evidence": result["preservation"]["source_commit_tracked_evidence_count"],
                      "receipt_sha256": sha(output.relative_to(ROOT)), "component_selected": False}))


if __name__ == "__main__":
    main()
