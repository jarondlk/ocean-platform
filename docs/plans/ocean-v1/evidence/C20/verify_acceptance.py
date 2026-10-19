"""Freeze C20 local acceptance once; preserve every earlier receipt and failure."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[4]


def read(name):
    return json.loads((OUT / name).read_text())


def sha(path):
    return hashlib.sha256((ROOT / path).read_bytes()).hexdigest()


def relative(path):
    return str(path.relative_to(ROOT))


def verify(files):
    changed = [path for path, digest in files.items() if sha(path) != digest]
    if changed:
        raise RuntimeError("Changed source/evidence pins: " + repr(changed))


def aggregate(files):
    return hashlib.sha256("".join(f"{path}:{digest}\n" for path, digest in sorted(files.items())).encode()).hexdigest()


def save(name, value):
    with (OUT / name).open("x") as stream:
        json.dump(value, stream, indent=2)
        stream.write("\n")


start = read("start-snapshot.json")
verify(start["prior_evidence_files"])
for files in start["preservation"].values():
    verify(files)
verify({start["readiness_receipt"]: start["readiness_receipt_sha256"]})
if (OUT / "verification.json").exists():
    receipt = read("verification.json")
    verify(receipt["files"])
    verify(receipt["evidence_files"])
    print(json.dumps({"state": "read-only acceptance verification passed", "source_sha256": receipt["source_sha256"]}))
    raise SystemExit(0)

backend = read("backend-final/backend-result.json")
backend_sources = read("backend-final/backend-tested-source.json")
assert len(backend["results"]) == 2 and all(item["exit_code"] == 0 for item in backend["results"])
assert not backend["source_changed_during_run"] and not backend_sources["changed"]
assert backend_sources["before_sha256"] == backend_sources["after_sha256"]
verify(backend_sources["after_sha256"])
summary = (OUT / "backend-final/backend-tests.txt").read_text()
match = re.search(r"(\d+) passed, (\d+) skipped, (\d+) warnings in ([\d.]+)s", summary)
assert match, "Missing complete passing backend summary"
passed, skipped, warnings = map(int, match.groups()[:3])
coverage = float(re.search(r"Total coverage: ([\d.]+)%", summary).group(1))
assert skipped == 231 and coverage >= 70
compatibility = int(re.search(r"(\d+) passed", (OUT / "backend-final/compatibility-tests.txt").read_text()).group(1))

postgres = read("parity-repair/postgres-result.json")
assert postgres["driver_exit_code"] == postgres["test_exit_code"] == 0
assert postgres["test_counts"] == {"passed": 104}
assert postgres["tested_source_unchanged"] and not postgres["source_changed_during_run"]
assert postgres["server_stopped"] and postgres["test_schemas_remaining"] == 0
verify(postgres["source_after_sha256"])

frontend = read("frontend-full-verification.json")
assert all(item["exit_code"] == 0 for item in frontend["commands"])
assert frontend["test_counts"] == {"passed": 781, "failed": 0, "skipped": 0}
assert frontend["production_dependency_vulnerabilities"]["total"] == 0
assert all(frontend[name] for name in (
    "frontend_source_unchanged", "legacy_source_unchanged", "wire_fixture_unchanged", "dependencies_and_lockfiles_unchanged",
))
frontend_before = read("frontend-full-source-before.json")
assert frontend_before == read("frontend-full-source-after.json")
verify(frontend_before["frontend_source_sha256"])
verify(frontend_before["legacy_source_sha256"])
verify(frontend["reviewed_source_sha256"])
for command in frontend["commands"]:
    verify({command["log"]: command["log_sha256"]})

for name, key in (("replay-verification.json", "source_sha256"), ("store-verification.json", "source_sha256"),
                  ("backend-independent-review.json", "reviewed_source_sha256"),
                  ("backend-test-amendment-review.json", "reviewed_source_sha256"),
                  ("frontend-independent-review-amendment.json", "reviewed_source_sha256")):
    verify(read(name)[key])
assert not read("backend-independent-review.json")["blocking_findings"]
assert not read("backend-test-amendment-review.json")["blocking_findings"]
assert not read("frontend-independent-review-amendment.json")["remaining_findings"]
verify(read("backend-independent-review.json")["preserved_receipt_sha256"])
verify(read("replay-verification.json")["original_immutable_receipt_sha256"])
verify(read("replay-verification.json")["evidence_sha256"])
verify({relative(OUT / path): digest for path, digest in read("store-verification.json")["preserved_logs_sha256"].items()})
wire = read("wire-fixtures.json")
verify(wire["source_sha256"])
assert wire["synthetic_only"] and len(wire["cases"]) == 9
assert {item["method"] for item in wire["cases"]} == {"submit", "status", "events", "cancel", "clarify", "continue", "list"}
assert sha(relative(OUT / "wire-fixtures.json")) == frontend_before["wire_fixture_sha256"]
generated = read("generated-checks.json")
assert len(generated) == 9 and all(item["exit_code"] == 0 and item["source_unchanged"] for item in generated)
assert (OUT / "ruff-acceptance.txt").read_text().strip() == "All checks passed!"

owned = set(backend_sources["owned_paths"]) | set(frontend["reviewed_source_sha256"])
owned.add("docs/plans/ocean-v1/C20_DURABLE_EXECUTION_CONTRACT.md")
owned.update(relative(OUT / name) for name in ("verify_postgres.py", "export_wire.py", "verify_acceptance.py"))
files = {path: sha(path) for path in sorted(owned)}
supersessions = {}
for label, previous in (
    ("formal prerequisites", start["formal_current_source_files"]),
    ("C19 accepted", start["C19_accepted_source"]),
    ("C19 transitive", start["C19_tested_transitive_source_files"]),
    ("C18 accepted", start["C18_accepted_source"]),
):
    for path, digest in previous.items():
        current = sha(path)
        if current != digest:
            assert path in files, (label, path)
            supersessions[f"{label}:{path}"] = {"before_sha256": digest, "C20_sha256": current}
tested = {**backend_sources["after_sha256"], **postgres["source_after_sha256"], **frontend_before["frontend_source_sha256"]}
verify(tested)
save("accepted-source.json", {"files": files, "source_sha256": aggregate(files),
    "aggregate_algorithm": "SHA256 of sorted UTF-8 path:SHA256 lines with LF endings"})
save("preservation.json", {
    "prior_evidence_files_unchanged": len(start["prior_evidence_files"]),
    "protected_counts": {key: len(values) for key, values in start["preservation"].items()},
    "intentional_source_supersessions": supersessions,
    "reasons": [
        "Add owner-private run persistence/dispatch/replay and strict HTTP/runtime capability gates; preserve legacy/scientific files.",
        "C19 controller/budget sources intentionally add the independently tested C20 replay port; original receipts remain immutable.",
        "C18 frontend sources intentionally add explicit production transport and recovery; scheduler amendment supersedes only its originally verified workspace source.",
        "CI adds isolated C20 PostgreSQL gates, preserving the accepted30-minute backend timeout. Migration-head assertions advance additively to0018.",
        "Initial PostgreSQL parity and sandbox/head-assertion failures remain preserved; repaired runs have separate immutable receipts.",
    ],
})
evidence = {relative(path): sha(relative(path)) for path in sorted(OUT.rglob("*"))
            if path.is_file() and path.name != "verification.json" and "__pycache__" not in path.parts and path.suffix != ".pyc"}
save("verification.json", {
    "component": "C20", "created_at": datetime.now(timezone.utc).isoformat(),
    "state": "All3 local checkpoints verified; source checkpoint and exact-source hosted delivery pending",
    "branch": "overhaul", "base_commit": start["implementation_base"],
    "files": files, "source_sha256": aggregate(files), "tested_transitive_source_files": tested,
    "evidence_files": evidence,
    "checks": {
        "backend": {"passed": passed, "postgres_gated_skips": skipped, "warnings": warnings,
                    "coverage_percent": coverage, "seconds": float(match.group(4))},
        "required_compatibility_passed": compatibility,
        "actual_postgres": {"passed": 104, "C20": 44, "C17": 60, "schemas_remaining": 0, "owned_server_stopped": True},
        "frontend_v1": frontend["test_counts"], "typecheck_and_build": "passed", "production_npm_audit_vulnerabilities": 0,
        "generated_checks": 9, "actual_wire_cases": 9, "actual_wire_methods": 7,
        "independent_backend_and_amended_frontend_source_review": "no remaining blockers",
    },
    "qualifications": [
        "Local backend includes9 pre-existing unrelated benchmark tests that remain outside this source checkpoint; hosted counts may differ by9.",
        "No live cloud, provider, data acquisition/transfer, deployment or scientific approval operation performed.",
        "Cloud queue/worker configuration and C26 assembled browser acceptance remain separate external/later gates.",
        "Production C20 result remains null; C21 must retain evidence/answers separately and explicitly account for synthesis.",
    ],
})
print(json.dumps({"state": "local acceptance frozen", "owned_paths": len(files), "tested_source_paths": len(tested),
                  "backend_passed": passed, "postgres_passed": 104, "frontend_passed": 781, "source_sha256": aggregate(files)}))
