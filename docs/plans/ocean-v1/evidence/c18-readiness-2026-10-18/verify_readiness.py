"""Read-only C18 prerequisite audit; explicit output creation refuses rewrites.

No test, service, account, data-store, Git mutation or network operation occurs.
Without both C17 commit arguments this produces only a pending readiness audit.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[5]
HERE = Path(__file__).resolve().parent
PLAN = "docs/plans/ocean-v1/"
COMPONENTS = ("P00", "C15", "C16", "C17")
EXPECTED_COUNTS = (36, 25, 18, 19)
C17_AGGREGATE = "1a1f3d3ff413c8ba71da1e9a9dbc67823bde23801e5ad1385ae9fe57676d570f"
C17_SOURCE = "39bb811d1053c9dfb4b700f8524162800092aa44"


def digest(data):
    return hashlib.sha256(data).hexdigest()


def sha(path):
    return digest((ROOT / path).read_bytes())


def read(path):
    return json.loads((ROOT / path).read_text())


def git(*args):
    return subprocess.check_output(["git", *args], cwd=ROOT)


def aggregate(files):
    return digest("".join(f"{path}:{value}\n" for path, value in sorted(files.items())).encode())


def hosted_gate(delivery, source):
    hosted = delivery["hosted_ci"]
    run = hosted.get("run", hosted)
    assert hosted["source_commit"] == source
    assert run["conclusion"] == "success"
    assert run.get("status", "completed") == "completed"
    assert run.get("head_sha", source) == source
    assert all(job["conclusion"] in ("success", "skipped") for job in hosted["jobs"])
    jobs = {job["name"]: job["conclusion"] for job in hosted["jobs"]}
    for required in (
        "PostgreSQL migration and metadata integration", "Backend tests and security boundary",
        "Frontend typecheck and build", "OCEAN v1 prototype tests and build",
    ):
        assert jobs.get(required) == "success", required
    return {
        "source_commit": source,
        "run_id": run.get("id", run.get("run_id")),
        "url": run.get("html_url", run.get("url")),
        "conclusion": "success",
        "verification": delivery.get("hosted_verification", {}),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--c17-source")
    parser.add_argument("--c17-delivery")
    parser.add_argument("--output", help="New JSON file inside this audit directory")
    args = parser.parse_args()
    assert bool(args.c17_source) == bool(args.c17_delivery), "Supply both C17 commit identities or neither"
    baseline = json.loads((HERE / "preservation-snapshot.json").read_text())
    for path, expected in baseline["receipt_sha256"].items():
        assert sha(path) == expected, f"Immutable receipt changed: {path}"

    receipts = {
        "P00": PLAN + "mockups/p00/source-revision.json",
        **{component: PLAN + f"evidence/{component}/accepted-source.json" for component in COMPONENTS[1:]},
    }
    sources = {component: read(path)["files"] for component, path in receipts.items()}
    # Four accepted C07 browser-export/admin source supersessions predate C15.
    # Preserve their original receipt rather than attributing them to the shell.
    c07_receipt = PLAN + "evidence/C07/verification.json"
    sources["C07"] = read(c07_receipt)["files"]
    receipts["C07"] = c07_receipt
    assert tuple(len(sources[component]) for component in COMPONENTS) == EXPECTED_COUNTS
    for component, path in receipts.items():
        assert aggregate(sources[component]) == read(path)["source_sha256"], component
    for component in ("C15", "C16", "C17"):
        original = read(PLAN + f"evidence/{component}/verification.json")
        assert original["files"] == sources[component], component
        assert original["source_sha256"] == read(receipts[component])["source_sha256"], component
    assert read(receipts["C17"])["source_sha256"] == C17_AGGREGATE
    for path, expected in sources["C17"].items():
        assert digest(git("show", f"{C17_SOURCE}:{path}")) == expected, path

    entries = {}
    for index, component in enumerate(COMPONENTS):
        entries[component] = {}
        for path, original in sources[component].items():
            accepted = original
            chain = [{"component": component, "receipt": receipts[component], "sha256": original}]
            later_components = (("C07",) if component == "P00" else ()) + COMPONENTS[index + 1:]
            for later in later_components:
                later_hash = sources[later].get(path)
                if later_hash is not None and later_hash != accepted:
                    chain.append({"component": later, "receipt": receipts[later], "sha256": later_hash})
                    accepted = later_hash
            assert sha(path) == accepted, f"Unaccepted source difference: {component} {path}"
            entries[component][path] = {
                "original_sha256": original, "current_sha256": accepted,
                "intentional_later_supersession": len(chain) > 1,
                "acceptance_chain": chain,
            }

    preservation = {}
    for group, files in baseline["preservation"].items():
        assert all(sha(path) == expected for path, expected in files.items()), group
        preservation[group] = {"count": len(files), "all_match": True}
    prior = baseline["prior_evidence_files"]
    assert all(sha(path) == expected for path, expected in prior.items())
    preservation["pinned_prior_evidence_files"] = {"count": len(prior), "all_match": True}

    hosted = {}
    for component in ("C15", "C16"):
        delivery = read(PLAN + f"evidence/{component}/delivery.json")
        source = delivery.get("implementation_commit", delivery.get("source_commit"))
        hosted[component] = hosted_gate(delivery, source)

    state = "Pending C17 exact-source hosted acceptance and delivery; C18 remains unselected"
    pending = ["C17 source-bound hosted CI acceptance", "C17 delivery checkpoint"]
    c17_receipts = {}
    if args.c17_source:
        assert args.c17_source == C17_SOURCE
        for commit in (args.c17_source, args.c17_delivery):
            assert re.fullmatch(r"[a-f0-9]{40}", commit), "Use full commit SHA"
        subprocess.run(["git", "merge-base", "--is-ancestor", args.c17_source, args.c17_delivery], cwd=ROOT, check=True)
        subprocess.run(["git", "merge-base", "--is-ancestor", args.c17_delivery, "HEAD"], cwd=ROOT, check=True)
        for path, expected in sources["C17"].items():
            assert digest(git("show", f"{args.c17_source}:{path}")) == expected, path
        for name in ("accepted-source.json", "verification.json", "delivery.json"):
            path = PLAN + "evidence/C17/" + name
            c17_receipts[path] = sha(path)
            assert digest(git("show", f"{args.c17_delivery}:{path}")) == sha(path), path
        delivery = read(PLAN + "evidence/C17/delivery.json")
        assert delivery["source_commit"] == args.c17_source
        assert delivery["source_sha256"] == C17_AGGREGATE
        local = read(PLAN + "evidence/C17/verification.json")
        assert local["files"] == sources["C17"]
        assert local["source_sha256"] == C17_AGGREGATE
        hosted["C17"] = hosted_gate(delivery, args.c17_source)
        state = "Ready for isolated local implementation; selection remains root-owned"
        pending = []

    tracked = git("ls-files", "-z", PLAN + "evidence/").decode().split("\0")
    tracked_evidence = {path: sha(path) for path in tracked if path and not path.startswith(str(HERE.relative_to(ROOT)) + "/")}
    report = {
        "component": "C18", "state": state, "date": "2026-10-18 JST",
        "branch": git("branch", "--show-current").decode().strip(),
        "head": git("rev-parse", "HEAD").decode().strip(),
        "formal_prerequisites": list(COMPONENTS),
        "source_entries": entries,
        "formal_source_entry_counts": dict(zip(COMPONENTS, EXPECTED_COUNTS)),
        "all_98_formal_source_entries_accepted": True,
        "unique_formal_paths": len({path for component in COMPONENTS for path in sources[component]}),
        "receipt_sha256": {**baseline["receipt_sha256"], **c17_receipts},
        "reviewed_documents_sha256": {PLAN + path: sha(PLAN + path) for path in (
            "SITE_SEPARATION.md", "UI_UX_BRIEF.md", "ACCEPTANCE_MAP.md",
            "components/C18-chat-workspace.md", "handoffs/P00.md", "handoffs/C15.md",
            "handoffs/C16.md", "handoffs/C17.md", "C15_APPLICATION_SHELL_CONTRACT.md",
            "C16_CATALOGUE_BROWSER_CONTRACT.md", "C17_INVESTIGATION_CONTRACT.md",
        )},
        "preservation": preservation,
        "current_tracked_prior_evidence_files": tracked_evidence,
        "reused_source_bound_hosted_gates": hosted,
        "C17_source_commit": C17_SOURCE, "C17_delivery_commit": args.c17_delivery,
        "pending_readiness_gates": pending,
        "C18_selected_by_this_audit": False,
        "test_policy": "Hash/receipt/Git-read verification only; completed tests were not repeated",
        "scope": "Separate v1 only; no legacy/P00 storage mutation, execution, real-data transfer, provider or cloud operation",
        "external_gates": ["Real OIDC enrollment", "Real scientific/data approvals", "C20 durable execution and C21 generated answers/artifacts", "Concrete cloud target configuration and separate deployment authorization"],
    }
    assert report["branch"] == "overhaul"
    text = json.dumps(report, indent=2, ensure_ascii=False) + "\n"
    if args.output:
        target = HERE / args.output
        assert target.parent.resolve() == HERE
        with target.open("x") as handle:
            handle.write(text)
    print(json.dumps({"state": state, "entries": 98, "preservation": preservation, "pending": pending, "output": args.output}))


if __name__ == "__main__":
    main()
