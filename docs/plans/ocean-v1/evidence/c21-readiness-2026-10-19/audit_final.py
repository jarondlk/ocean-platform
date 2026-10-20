"""Finalize C21 prerequisite evidence only after amended C20 hosted delivery.

This helper never selects a component, calls a service or changes an existing
receipt. All amended-source and delivery inputs are explicit. --help performs no
audit; --check revalidates a saved final receipt without writing it.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]
PLAN = Path("docs/plans/ocean-v1")
ORIGINAL_SOURCE = "fc46da36aa27c203357a1b5874a02378ae089847"
PRESERVED_PREPARATION = {
    "audit_pending.py": "4c1229acd24468eec0c1a5a227e6c144281d061357d93e8c4a2e5262cb922c22",
    "formal-map.md": "8dedb1bfb10740a0762e9bec6c275d73f0cda6d39d8994948438a153269eafdc",
    "pending-verification.json": "6a7c96fdc49e4e717ba80a97bf9d1c37bacf55eb3fd1245a03f56f0093f0b171",
    "preparation.md": "959951041ddbaad99af8bc5c0d76529f1f73453c0a1537cce6f74eb5ff95a80a",
}


def git(*arguments: str) -> str:
    return subprocess.check_output(["git", *arguments], cwd=ROOT, text=True).strip()


def sha(path: str | Path) -> str:
    return hashlib.sha256((ROOT / path).read_bytes()).hexdigest()


def read(path: str | Path) -> dict:
    return json.loads((ROOT / path).read_text())


def relative(path: str | Path) -> str:
    candidate = (ROOT / path).resolve()
    result = candidate.relative_to(ROOT)
    if candidate.is_symlink():
        raise RuntimeError("Symlink receipt/source is not accepted")
    return str(result)


def verify(files: dict[str, str]) -> None:
    changed = [path for path, digest in files.items() if not (ROOT / path).is_file() or sha(path) != digest]
    if changed:
        raise RuntimeError("Changed or missing pinned files: " + repr(changed))


def aggregate(files: dict[str, str]) -> str:
    return hashlib.sha256("".join(f"{path}:{digest}\n" for path, digest in sorted(files.items())).encode()).hexdigest()


def validate_map(files: dict[str, str]) -> None:
    if not isinstance(files, dict) or not files:
        raise RuntimeError("A nonempty exact source map is required")
    for path, digest in files.items():
        if (not isinstance(path, str) or Path(path).is_absolute() or ".." in Path(path).parts
                or "\\" in path or not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest)):
            raise RuntimeError("Invalid source map entry")


def ancestor(before: str, after: str) -> None:
    subprocess.run(["git", "merge-base", "--is-ancestor", before, after], cwd=ROOT, check=True)


def commit_sha(commit: str, path: str | Path) -> str:
    return hashlib.sha256(subprocess.check_output(["git", "show", f"{commit}:{path}"], cwd=ROOT)).hexdigest()


def verify_commit(commit: str, files: dict[str, str]) -> None:
    validate_map(files)
    verify(files)
    for path, digest in files.items():
        if commit_sha(commit, path) != digest:
            raise RuntimeError("Source checkpoint mismatch: " + path)


def tracked_evidence(commit: str) -> dict[str, str]:
    prefix = str(PLAN / "evidence")
    listing = subprocess.check_output(["git", "ls-tree", "-r", "-z", commit, "--", prefix], cwd=ROOT)
    result = {}
    with subprocess.Popen(["git", "cat-file", "--batch"], cwd=ROOT,
                          stdin=subprocess.PIPE, stdout=subprocess.PIPE) as process:
        if process.stdin is None or process.stdout is None:
            raise RuntimeError("Git object reader unavailable")
        for record in listing.split(b"\0"):
            if not record:
                continue
            metadata, raw_path = record.split(b"\t", 1)
            mode, kind, identity = metadata.split()
            if kind != b"blob" or mode not in {b"100644", b"100755"}:
                raise RuntimeError("Unexpected evidence object in source checkpoint")
            process.stdin.write(identity + b"\n")
            process.stdin.flush()
            actual, actual_kind, size = process.stdout.readline().split()
            body = process.stdout.read(int(size))
            if (actual != identity or actual_kind != b"blob" or len(body) != int(size)
                    or process.stdout.read(1) != b"\n"):
                raise RuntimeError("Incomplete retained Git object")
            result[raw_path.decode("utf-8")] = hashlib.sha256(body).hexdigest()
        process.stdin.close()
        if process.wait() != 0:
            raise RuntimeError("Git object reader failed")
    verify(result)
    return result


def collect_final(*, source_commit: str, amendment_receipt: str | Path,
                  amendment_source_map: str | Path, delivery: str | Path) -> dict:
    if not re.fullmatch(r"[0-9a-f]{40}", source_commit) or source_commit == ORIGINAL_SOURCE:
        raise RuntimeError("An explicit new full amended source commit is required")
    if git("branch", "--show-current") != "overhaul":
        raise RuntimeError("Readiness must remain on overhaul")
    head = git("rev-parse", "HEAD")
    ancestor(ORIGINAL_SOURCE, source_commit)
    ancestor(source_commit, head)
    preparation_pins = {str((HERE / name).relative_to(ROOT)): digest for name, digest in PRESERVED_PREPARATION.items()}
    verify(preparation_pins)
    pending = read(HERE / "pending-verification.json")
    if (pending["state"] != "pending-hosted-delivery" or pending["ready_for_selection"]
            or pending["component_selected"] or pending["source_commit"] != ORIGINAL_SOURCE):
        raise RuntimeError("The original pending audit must remain unpromoted")
    verify(pending["immutable_receipt_pins_sha256"])
    preservation = pending["preservation"]
    for values in preservation["protected_files"].values():
        verify(values)
    for key in ("C20_start_prior_evidence_files", "source_commit_tracked_evidence_files", "C20_local_evidence_files"):
        verify(preservation[key])

    receipt_path, map_path, delivery_path = map(relative, (amendment_receipt, amendment_source_map, delivery))
    amendment, accepted, delivered = read(receipt_path), read(map_path), read(delivery_path)
    if amendment["original_source_commit"] != ORIGINAL_SOURCE:
        raise RuntimeError("Amendment must preserve the original C20 source identity")
    files, tested = accepted["files"], amendment["tested_transitive_source_files"]
    validate_map(files)
    validate_map(tested)
    if accepted["source_sha256"] != aggregate(files):
        raise RuntimeError("Amended source-map aggregate is invalid")
    original_files = pending["C20_accepted_source_files"]
    original_tested = pending["C20_tested_transitive_source_files"]
    if len(original_files) != 46 or len(original_tested) != 167:
        raise RuntimeError("Unexpected original C20 source baseline")
    if not original_files.keys() <= files.keys() or not original_tested.keys() <= tested.keys():
        raise RuntimeError("Amendment omitted an original accepted/tested source")
    original_combined = {**original_files, **original_tested}
    if any(original_files[path] != original_tested[path] for path in original_files.keys() & original_tested.keys()):
        raise RuntimeError("Original accepted and tested maps disagree")
    effective = {**files, **tested}
    if any(files[path] != tested[path] for path in files.keys() & tested.keys()):
        raise RuntimeError("Amended accepted and tested maps disagree")
    changes = {path: {"before_sha256": digest, "after_sha256": effective[path]}
               for path, digest in original_combined.items() if effective[path] != digest}
    if not changes or amendment["intentional_source_supersessions"] != changes:
        raise RuntimeError("Every changed original46/167 path needs one exact intentional supersession")
    if not changes.keys() <= files.keys():
        raise RuntimeError("Changed original source must appear in the amended accepted source map")
    verify_commit(source_commit, effective)
    immutable_new_receipts = {receipt_path: sha(receipt_path), map_path: sha(map_path)}
    verify_commit(source_commit, immutable_new_receipts)
    for path, digest in original_combined.items():
        if commit_sha(ORIGINAL_SOURCE, path) != digest:
            raise RuntimeError("Original C20 source baseline no longer matches history")
    changed_paths = git("diff", "--name-only", ORIGINAL_SOURCE, source_commit, "--").splitlines()
    unmapped = [path for path in changed_paths if not path.startswith(str(PLAN) + "/") and path not in effective]
    if unmapped:
        raise RuntimeError("Unmapped application/workflow source changes in amendment: " + repr(unmapped))

    if (delivered["source_commit"] != source_commit or delivered["files"] != files
            or delivered["source_sha256"] != aggregate(files)
            or delivered["tested_transitive_source_files"] != tested):
        raise RuntimeError("Final C20 delivery must bind the complete amended accepted/tested maps")
    ci = delivered["hosted_ci"]
    run = ci.get("run", ci)
    hosted_source = ci.get("source_commit", run.get("head_sha"))
    if (hosted_source != source_commit or run.get("head_sha", hosted_source) != source_commit
            or run.get("conclusion") != "success"):
        raise RuntimeError("C20 requires successful hosted CI on the amended source itself")
    if head == source_commit or commit_sha(head, delivery_path) != sha(delivery_path):
        raise RuntimeError("Final hosted delivery must be committed in a separate documentation checkpoint")
    ancestor(head, "origin/overhaul")
    immutable_new_receipts[delivery_path] = sha(delivery_path)
    current_tracked = tracked_evidence(source_commit)

    rows = json.loads(json.dumps(pending["source_entries"]))
    current = dict(pending["formal_current_source_files"])
    for component, entries in rows.items():
        for path, row in entries.items():
            old = row["current_sha256"]
            expected = effective.get(path, old)
            if expected != old:
                if path not in changes or changes[path]["before_sha256"] != old:
                    raise RuntimeError("Formal prerequisite change lacks a consistent amendment witness")
                row["acceptance_chain"].append({"component": "C20 history amendment", "receipt": map_path,
                                                 "receipt_sha256": sha(map_path), "sha256": expected})
            row["current_sha256"] = expected
            row["intentional_later_supersession"] = expected != row["original_sha256"]
            current[path] = expected
    verify_commit(source_commit, current)
    audit_pins = {**preparation_pins, **immutable_new_receipts,
                  str(Path(__file__).relative_to(ROOT)): sha(Path(__file__).relative_to(ROOT)),
                  str((HERE / "final-formal-map.md").relative_to(ROOT)): sha((HERE / "final-formal-map.md").relative_to(ROOT))}
    planning_pins = {}
    for name in ("STATUS.md", "components/C20-durable-execution.md", "components/C21-evidence-synthesis.md", "handoffs/C20.md"):
        planning_pins[str(PLAN / name)] = sha(PLAN / name)
    return {
        "component": "C21", "state": "prerequisites_verified_awaiting_root_selection",
        "audited_at": datetime.now(timezone.utc).isoformat(), "branch": "overhaul", "head": head,
        "original_C20_source_commit": ORIGINAL_SOURCE, "source_commit": source_commit,
        "component_selected": False, "ready_for_selection": True,
        "formal_prerequisites": pending["formal_prerequisites"],
        "formal_source_entries": sum(len(entries) for entries in rows.values()), "unique_source_paths": len(current),
        "source_entries": rows, "formal_current_source_files": current, "formal_current_source_sha256": aggregate(current),
        "original_C20_accepted_source_count": 46, "original_C20_tested_source_count": 167,
        "C20_accepted_source_files": files, "C20_tested_transitive_source_files": tested,
        "intentional_source_supersessions": changes,
        "new_accepted_paths": sorted(files.keys() - original_files.keys()),
        "new_tested_paths": sorted(tested.keys() - original_tested.keys()),
        "prior_hosted_prerequisites": pending["prior_hosted_prerequisites"],
        "C20_hosted_delivery": {"receipt": delivery_path, "receipt_sha256": sha(delivery_path),
                                "source_commit": source_commit, "conclusion": "success",
                                "run_id": run.get("id", run.get("run_id")), "url": run.get("html_url", run.get("url")),
                                "documentation_checkpoint": head,
                                "remote_tracking_qualification": "HEAD is contained in local origin/overhaul; no fetch/network operation performed"},
        "immutable_input_and_audit_pins_sha256": audit_pins,
        "historical_pending_immutable_receipt_pins_sha256": pending["immutable_receipt_pins_sha256"],
        "planning_document_pins_sha256": planning_pins,
        "preservation": {**preservation, "amended_source_tracked_evidence_count": len(current_tracked),
                         "amended_source_tracked_evidence_files": current_tracked,
                         "amended_source_tracked_evidence_sha256": aggregate(current_tracked)},
        "checks_run": "Read-only source/receipt/Git/preservation reconciliation only; no application tests, services or component selection",
        "qualifications": [
            "Original pending receipt describes the superseded fc46da3 source and remains immutable; it was not promoted or rewritten.",
            "Original CI success, if present, does not clear the amended source: final hosted success is required for the explicit amended source commit.",
            "Final readiness does not itself select C21; root must record the selection under the existing sequential authorization.",
            "No live provider, actual data transfer, scientific approval, cloud provisioning or deployment is authorized or performed by this helper."],
    }


def check_saved(path: str | Path) -> dict:
    receipt = read(path)
    for key in ("formal_current_source_files", "C20_accepted_source_files", "C20_tested_transitive_source_files",
                "immutable_input_and_audit_pins_sha256", "historical_pending_immutable_receipt_pins_sha256"):
        verify(receipt[key])
    preserved = receipt["preservation"]
    for values in preserved["protected_files"].values():
        verify(values)
    for key in ("C20_start_prior_evidence_files", "source_commit_tracked_evidence_files",
                "C20_local_evidence_files", "amended_source_tracked_evidence_files"):
        verify(preserved[key])
    return {"state": "saved final source/evidence/protected pins match", "component_selected": False,
            "qualification": "No receipt rewritten and no component selected; mutable planning pins remain historical"}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-commit", help="Exact full amended C20 source commit supplied by root")
    parser.add_argument("--amendment-receipt", type=Path, help="Repository-relative standard amendment verification.json")
    parser.add_argument("--amendment-source-map", type=Path, help="Repository-relative standard amended accepted-source.json")
    parser.add_argument("--delivery", type=Path, help="Repository-relative committed/pushed final C20 delivery.json")
    parser.add_argument("--output", type=Path, help="New receipt filename within this readiness directory; create only")
    parser.add_argument("--check", type=Path, help="Existing final receipt within this readiness directory; read only")
    options = parser.parse_args()
    inputs = (options.source_commit, options.amendment_receipt, options.amendment_source_map, options.delivery)
    if options.check:
        if any(inputs) or options.output:
            parser.error("--check cannot create or finalize a receipt")
        print(json.dumps(check_saved(HERE / options.check)))
        return
    if not all(inputs) or options.output is None:
        parser.error("Explicit --source-commit, --amendment-receipt, --amendment-source-map, --delivery and --output are required")
    output = (HERE / options.output).resolve()
    if output.parent != HERE or output.exists():
        raise RuntimeError("Output must be a new receipt directly in this readiness directory")
    result = collect_final(source_commit=options.source_commit, amendment_receipt=options.amendment_receipt,
                           amendment_source_map=options.amendment_source_map, delivery=options.delivery)
    with output.open("x") as stream:
        json.dump(result, stream, indent=2)
        stream.write("\n")
    print(json.dumps({"state": result["state"], "source_commit": result["source_commit"],
                      "formal_entries": result["formal_source_entries"], "unique_paths": result["unique_source_paths"],
                      "intentional_supersessions": len(result["intentional_source_supersessions"]),
                      "receipt_sha256": sha(output.relative_to(ROOT)), "component_selected": False}))


if __name__ == "__main__":
    main()
