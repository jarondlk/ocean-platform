"""Read-only C27 prerequisite audit; local readiness does not accept a live release."""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[6]
DIRECTORY = Path(__file__).resolve().parent
CHECKPOINT = "a69eb575ab9f11135778de052d27fa070ac3898e"
SOFTWARE = "afe9cb2d1a6d2c28a834daab1a342de4563dc3a3"
EVIDENCE = "docs/plans/ocean-v1/evidence"
C26 = ROOT / EVIDENCE / "C26"


def read(path):
    return json.loads(path.read_text())


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def git(*arguments):
    return subprocess.check_output(["git", *arguments], cwd=ROOT)


def tree(identity):
    entries = {}
    for entry in git("ls-tree", "-r", "-z", identity).split(b"\0"):
        if entry:
            metadata, name = entry.split(b"\t", 1)
            mode, kind, blob = metadata.decode().split()
            assert kind == "blob", (name, kind)
            entries[name.decode()] = {"mode": mode, "git_blob": blob}
    return entries


def git_blob(raw):
    return hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()


def relative_file(name):
    path = ROOT / name
    assert path.resolve().is_relative_to(ROOT), name
    assert path.is_file(), name
    return path


def migration_graph():
    revisions = {}
    for path in sorted((ROOT / "migrations/versions").glob("*.py")):
        values = {}
        for node in ast.parse(path.read_text()).body:
            if isinstance(node, ast.Assign):
                targets = node.targets
            elif isinstance(node, ast.AnnAssign):
                targets = [node.target]
            else:
                continue
            for target in targets:
                if isinstance(target, ast.Name) and target.id in {"revision", "down_revision"}:
                    assert target.id not in values, path
                    values[target.id] = ast.literal_eval(node.value)
        if "revision" not in values:
            continue
        revision, previous = values["revision"], values["down_revision"]
        assert isinstance(revision, str) and (previous is None or isinstance(previous, str)), path
        assert revision not in revisions, revision
        revisions[revision] = {"down_revision": previous,
            "path": str(path.relative_to(ROOT)), "sha256": sha(path.read_bytes())}
    parents = {row["down_revision"] for row in revisions.values() if row["down_revision"] is not None}
    assert parents <= set(revisions)
    heads = sorted(set(revisions) - parents)
    assert heads == ["20261027_0021"] and len(revisions) == 21
    lineage, current = [], heads[0]
    while current is not None:
        assert current not in lineage, "Migration cycle"
        lineage.append(current)
        current = revisions[current]["down_revision"]
    assert len(lineage) == len(revisions) and lineage[-1] == "20260723_0001"
    return {"head": heads[0], "revision_count": len(revisions),
        "lineage_oldest_first": list(reversed(lineage)), "revisions": revisions}


def verify():
    start = read(DIRECTORY / "start.json")
    assert git("branch", "--show-current").decode().strip() == "overhaul"
    assert start["checkpoint_commit"] == CHECKPOINT
    assert start["accepted_software_source_commit"] == SOFTWARE
    subprocess.run(["git", "merge-base", "--is-ancestor", CHECKPOINT, "HEAD"],
        cwd=ROOT, check=True, capture_output=True)
    evidence_tree = git("rev-parse", CHECKPOINT + ":" + EVIDENCE).decode().strip()
    assert start["prior_evidence_tree"] == evidence_tree
    entries = tree(evidence_tree)
    assert start["prior_evidence_files"] == entries
    for name, entry in entries.items():
        path = ROOT / EVIDENCE / name
        assert path.parent.resolve().is_relative_to(ROOT / EVIDENCE), name
        if entry["mode"] == "120000":
            assert path.is_symlink(), name
            raw = os.readlink(path).encode()
        else:
            assert entry["mode"] in {"100644", "100755"} and not path.is_symlink(), name
            raw = path.read_bytes()
        assert git_blob(raw) == entry["git_blob"], name
    original_start = read(C26 / "implementation-20261029/start.json")
    assert start["protected_sha256"] == original_start["protected_sha256"]
    for name, expected in start["protected_sha256"].items():
        assert sha(relative_file(name).read_bytes()) == expected, name
    delivery = read(C26 / "delivery.json")
    assert delivery["source_commit"] == SOFTWARE
    assert delivery["accepted_workflow_run_id"] == 41175282249
    assert delivery["local_preparation_complete"] is True
    assert delivery["release_accepted"] is False and delivery["release_status"] == "not_run"
    assert start["c26_delivery_sha256"] == sha((C26 / "delivery.json").read_bytes())
    assert start["c26_proof_sha256"] == delivery["proof_sha256"]
    for name, expected in delivery["proof_sha256"].items():
        assert sha(relative_file(name).read_bytes()) == expected, name
    result = subprocess.run([sys.executable, str(C26 / "verify_delivery.py")], cwd=ROOT,
        check=True, capture_output=True, text=True)
    verified = json.loads(result.stdout)
    assert verified["source_commit"] == SOFTWARE and verified["source_paths"] == 844
    assert verified["unchanged_application_paths"] == 843
    assert verified["local_preparation_verified"] and verified["hosted_verified"]
    assert not verified["release_accepted"] and verified["open_P2_history_latency_preserved"]
    pending = delivery["pending_release_requirements"]
    assert len(pending) == 20 and all(row["status"] == "not_run" for row in pending)
    ids = [row["requirement_id"] for row in pending]
    assert len(set(ids)) == len(ids) and ids == start["pending_release_requirement_ids"]
    findings = delivery["open_findings"]
    assert any(row["id"] == "D26-07" and row["severity"] == "P2" and row["status"] == "open"
        for row in findings)
    graph = migration_graph()
    assert graph == start["migration_graph"]
    pending_path = ROOT / "deploy/gcp-v1/examples/site.operator.pending.json"
    assert sha(pending_path.read_bytes()) == start["operator_pending_sha256"]
    operator = read(pending_path)
    assert operator["input_class"] == "operator-values"
    assert operator["target"]["public_origin"] == "https://beta.oceaninfobio.com"
    assert operator["target"]["project_id"] is None
    assert operator["browser"]["cookie_domain"] is None
    assert operator["browser"]["session_cookie"].startswith("__Host-ocean-v1-")
    assert operator["flags"] == {"research_dispatch": False, "experiment_dispatch": False}
    return {"version": "c27-readiness-verification-v1", "recorded_on": "2026-11-01 JST",
        "branch": "overhaul", "checkpoint_commit": CHECKPOINT,
        "accepted_software_source_commit": SOFTWARE,
        "effective_delivery_source_revision": verified["effective_delivery_source_revision"],
        "c26_proof_paths_verified": len(delivery["proof_sha256"]),
        "source_paths_verified": verified["source_paths"],
        "prior_evidence_files_preserved": len(entries),
        "prior_evidence_tree": evidence_tree,
        "protected_paths_preserved": len(start["protected_sha256"]),
        "migration_head": graph["head"], "migration_revisions": graph["revision_count"],
        "local_implementation_ready": True, "release_accepted": False,
        "pending_release_requirement_ids": ids,
        "pending_release_status": "not_run", "D26-07": "open P2",
        "host_only_cookie_null_domain_required": True,
        "production_dispatch_enabled": False,
        "baseline_application_tests_repeated": False,
        "cloud_or_production_actions_performed": False,
        "start_sha256": sha((DIRECTORY / "start.json").read_bytes()),
        "audit_source_sha256": sha(Path(__file__).read_bytes()),
        "qualification": "Only C27 local release-preparation readiness. Missing live configuration, production integrations, external validation and operator release acceptance remain explicit gates."}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify-only", action="store_true",
        help="Read-only verification; the default is also read-only")
    parser.parse_args()
    print(json.dumps(verify(), indent=2))
