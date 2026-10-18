"""Freeze C19 local acceptance once; later invocations verify immutable pins."""
from pathlib import Path
import hashlib
import json
import re

ROOT = Path(__file__).resolve().parents[5]
OUT = Path(__file__).resolve().parent


def sha(path):
    return hashlib.sha256((ROOT / path).read_bytes()).hexdigest()


def aggregate(files):
    return hashlib.sha256("".join(f"{p}:{h}\n" for p, h in sorted(files.items())).encode()).hexdigest()


def read(name):
    return json.loads((OUT / name).read_text())


def save(name, value):
    with (OUT / name).open("x") as stream:
        stream.write(json.dumps(value, indent=2) + "\n")


def verify(files):
    changed = [p for p, expected in files.items() if sha(p) != expected]
    if changed:
        raise SystemExit("Changed pinned files: " + repr(changed))


start = read("start-snapshot.json")
for files in start["preservation"].values():
    verify(files)
verify(start["prior_evidence_files"])
verify(start["C18_accepted_source"])
verify({start["readiness_receipt"]: start["readiness_receipt_sha256"]})
backend = read("backend-tested-source.json")
assert backend["before_sha256"] == backend["after_sha256"] and not backend["changed"]
verify(backend["after_sha256"])
results = read("backend-result.json")
assert len(results["results"]) == 2
assert all(item["exit_code"] == 0 for item in results["results"])
assert not results["source_changed_during_run"]
generated = read("generated-checks.json")
assert len(generated) == 9 and all(item["exit_code"] == 0 for item in generated)
assert (OUT / "ruff-acceptance.txt").read_text().strip() == "All checks passed!"
review = read("review-final.json")
verify(review["reviewed_source_sha256"])
files = {p: sha(p) for p in sorted(backend["owned_paths"])}
assert files == review["reviewed_source_sha256"]
assert len(files) == 13
formal = {}
for component, entries in start["formal_source_entries"].items():
    for path, entry in entries.items():
        if sha(path) != entry["current_sha256"]:
            assert path == "config.py" and path in files
            formal[f"{component}:{path}"] = {
                "before_sha256": entry["current_sha256"], "C19_sha256": sha(path),
                "reason": "Add independently strict default-off C19 flag/helper; existing behavior unchanged. Original receipts immutable.",
            }
if (OUT / "verification.json").exists():
    receipt = read("verification.json")
    verify(receipt["files"])
    verify(receipt["evidence_files"])
    print(json.dumps({"state": "read-only verification pass", "source_sha256": receipt["source_sha256"], "prior_evidence_unchanged": len(start["prior_evidence_files"])}))
else:
    summary = (OUT / "backend-tests.txt").read_text()
    match = re.search(r"(\d+) passed, (\d+) skipped, (\d+) warnings in ([\d.]+)s", summary)
    assert match
    passed, skipped, warnings = map(int, match.groups()[:3])
    coverage = float(re.search(r"Total coverage: ([\d.]+)%", summary).group(1))
    compatibility = (OUT / "compatibility-tests.txt").read_text()
    compatible = int(re.search(r"(\d+) passed", compatibility).group(1))
    protected = {key: len(values) for key, values in start["preservation"].items()}
    save("accepted-source.json", {"files": files, "source_sha256": aggregate(files), "aggregate_algorithm": "SHA256 of sorted UTF-8 path:SHA256 lines with LF endings"})
    save("preservation.json", {
        "formal_intentional_supersessions": formal,
        "prior_evidence_files_unchanged": len(start["prior_evidence_files"]),
        "protected_counts": protected, "all23_C18_sources_unchanged": True,
        "formal_source_entries": sum(len(entries) for entries in start["formal_source_entries"].values()),
        "original_intermediate_contract_receipts_retained": True,
        "contract_final_source_receipt": "contract-publication-pages-verification.json",
        "publication_fixture_supersession": "publication-integration-fix.json",
    })
    evidence = {str(p.relative_to(ROOT)): sha(p.relative_to(ROOT)) for p in sorted(OUT.iterdir()) if p.is_file() and p.name != "verification.json"}
    save("verification.json", {
        "component": "C19", "state": "All3 local checkpoints complete; source checkpoint and exact-source hosted delivery pending",
        "branch": "overhaul", "base_commit": start["implementation_base"],
        "files": files, "source_sha256": aggregate(files), "evidence_files": evidence,
        "contract": "docs/plans/ocean-v1/C19_AGENT_CONTROLLER_CONTRACT.md",
        "contract_sha256": sha("docs/plans/ocean-v1/C19_AGENT_CONTROLLER_CONTRACT.md"),
        "checks": {
            "backend": {"passed": passed, "postgres_gated_skips": skipped, "coverage_percent": coverage, "warnings": warnings, "seconds": float(match.group(4)), "source_paths_unchanged": len(backend["after_sha256"]), "unrelated_local_benchmark_cases_excluded_from_commit": 9},
            "required_compatibility_passed": compatible,
            "C19_new_cases": 356, "contract_cases": 144, "scope_cases": 131,
            "actual_controller_cases": 38, "budget_cases": 23, "observation_cases": 7,
            "explicit_100000_backend_cases": 8, "actual_publication_cases": 5,
            "active_python_ruff": "pass", "generated_checks": 9,
            "independent_source_review": "review-final.json",
            "frontend": "All23 C18 accepted sources unchanged; reuse C18 673 tests/build/typecheck evidence. Exact-source combined hosted frontend gates pending.",
            "hosted_ci": "pending exact-source run",
        },
        "preservation": {"prior_evidence_unchanged": len(start["prior_evidence_files"]), **protected, "all23_C18_sources_unchanged": True},
        "qualifications": [
            "Actual sealed synthetic C09-C13, C14/C17 services and TEST principals; fake completed/incomplete C06 runtimes only.",
            "The100000-object scale proof uses an explicit C14 backend and frozen submission loader, not C13 capacity or actual100000-dataset C17 storage.",
            "Bounded whole-input EN/JA grammar; unsupported scientific or artifact semantics require clarification/unavailable.",
            "Cancellation is cooperative; no blocking worker preemption claim. Invalid clock lower-bound timing cannot authorize future effects/completion.",
            "C20 owns durable payload/step storage, replay, leases, dispatch, frontend execution transport and publication transaction; C21 owns final synthesis.",
            "No real OIDC/provider/scientific approval/acquisition/transfer/cloud deployment acceptance.",
            "Initial unenabled investigation fixture, invalid cursor fixture, publication date/protocol mismatch, transient-clock auth-overview count and invalid bay-code fixture failures remain immutable and qualified by later checks.",
            "No schema migration or scientific query behavior changed. Local PostgreSQL gates remain skipped here; source-bound hosted regression required.",
        ],
    })
    print(json.dumps({"state": "local acceptance frozen", "source_sha256": aggregate(files), "source_paths": len(files), "verification_sha256": sha((OUT / "verification.json").relative_to(ROOT)), "checks": {"backend_passed": passed, "coverage_percent": coverage, "compatibility_passed": compatible}, "formal_supersessions": len(formal)}))
