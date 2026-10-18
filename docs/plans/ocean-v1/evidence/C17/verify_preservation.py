"""Read-only C17 preservation check; explicit freeze creates one new receipt.

Default runs never write files or run tests/services. They report a source
candidate until the final backend result is complete. After the parent freezes
source and verifies the final run, --create-accepted-source creates the receipt
exclusively and refuses to overwrite it. Earlier receipts retain their original
source bindings, including the explicitly recorded C17 supersessions.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re

OUTPUT = Path(__file__).resolve().parent
ROOT = OUTPUT.parents[4]
PREFIX = "docs/plans/ocean-v1/evidence/C17/"
START_PATH = PREFIX + "start-snapshot.json"
BASE_COMMIT = "b39efc512bbf113d21d751d3619824006e066bfa"
AGGREGATE_ALGORITHM = "SHA256 of sorted UTF-8 path:SHA256 lines with LF endings"
PINNED_RECEIPTS = {
    START_PATH: "1cd0a7dc80a9e69665eb740f840ab66c4327310ec19797b37deff8a4810f9146",
    "docs/plans/ocean-v1/evidence/c17-readiness-2026-10-18/verification.json": "e8949d29657279ad61c5e7802964fa4a4b5744961c5b8792e4b4620807c24d27",
    "docs/plans/ocean-v1/evidence/C16/accepted-source.json": "b3198fc1db49ca5907f42540c34dfe1a3d0e0cb66c4a8fdf5ca4674e6bd2979d",
    "docs/plans/ocean-v1/evidence/C16/verification.json": "3d08bf93659366a59816cb84579dada932bae3a542374a350fde554d5d741f0d",
    "docs/plans/ocean-v1/evidence/C16/delivery.json": "fbf4ed0276f4b6c711fc10e75fe09006a1e1759a237a32970ccdc74a6bf6846b",
    PREFIX + "api-stream-verification.json": "20d1d14a47e4933b1ac55d01dc2642f59a9a8c3e6e0761eac40c8269edc7d4c2",
    PREFIX + "api-stream-tests-run.json": "e7de847dfc333206ef8cea2465c7f3c21499cf43d334a58125f50dd81fe357ea",
    PREFIX + "api-stream-tests.txt": "59aa86cb2fcabab1414567b18d4085c2145be7fa5b5033b30be6d250c319b048",
    PREFIX + "api-stream-ruff.txt": "82b3e6a6c090a57601d22943bd23fca9218d1031dbe5a7b754092f9a156b4f18",
    PREFIX + "postgres-result.json": "974ae36b008e44a2b8f292e3b6d0e59445a382dbca4eda8dc37a6cbb9bbd9831",
    PREFIX + "postgres-tested-source.json": "e408545629e3bf71db6fbe043c9a4791a2aabc93144976b9c736d9c2327be02c",
    PREFIX + "postgres-tests.txt": "48d0a78d99858194540b85e87d610ed7c6e0a7502627d73e3d114def6fda1d9f",
}
SOURCE_PATHS = {
    ".github/workflows/tests.yml", "api/auth.py", "api/main.py", "config.py",
    "db/app_models.py", "api/investigation_routes.py", "schema/investigations.py",
    "orchestration/investigations.py", "migrations/versions/20261018_0017_investigations.py",
    "tests/test_investigation_models.py", "tests/test_investigation_api.py",
    "tests/test_investigation_api_integration.py", "tests/test_investigation_api_stream.py",
    "tests/test_investigations.py", "tests/investigation_support.py",
    "tests/test_investigation_postgres_guard.py",
    "tests/integration/test_investigation_postgres.py",
    "tests/integration/test_investigation_service_postgres.py",
    "tests/test_bootstrap_database.py",
}
FORMAL_SUPERSESSIONS = {".github/workflows/tests.yml", "api/auth.py"}
C16_SUPERSESSIONS = {"api/auth.py", "api/main.py", "config.py"}
FINAL_BACKEND_FILES = (
    "final-backend-tested-source.json", "final-backend-result.json", "final-backend-tests.txt",
)


class PreservationError(RuntimeError):
    pass


def require(condition, message):
    if not condition:
        raise PreservationError(message)


def target(path):
    candidate = ROOT / path
    require(not Path(path).is_absolute() and candidate.resolve().is_relative_to(ROOT),
            f"Path escapes the repository: {path}")
    return candidate


def sha(path):
    return hashlib.sha256(target(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(target(path).read_text(encoding="utf-8"))


def aggregate(files):
    return hashlib.sha256("".join(f"{path}:{files[path]}\n" for path in sorted(files)).encode("utf-8")).hexdigest()


def unchanged(files, label):
    for path, expected in files.items():
        require(sha(path) == expected, f"{label} changed: {path}")


def supersessions(files, allowed, label):
    changed = {}
    for path, previous in files.items():
        current = sha(path)
        if current != previous:
            require(path in allowed, f"Unapproved {label} supersession: {path}")
            changed[path] = {"previous_sha256": previous, "C17_sha256": current}
    return changed


def final_backend(require_complete):
    present = [name for name in FINAL_BACKEND_FILES if (OUTPUT / name).exists()]
    if len(present) != len(FINAL_BACKEND_FILES):
        require(not require_complete, "Final full backend result is incomplete; accepted source cannot be frozen")
        return {"status": "pending", "present": present, "required": list(FINAL_BACKEND_FILES)}
    source = read(PREFIX + FINAL_BACKEND_FILES[0])
    require(source["changed"] == [] and source["before_sha256"] == source["after_sha256"],
            "Final backend source changed during its run")
    require(set(source["after_sha256"]) == SOURCE_PATHS, "Final backend requires the exact 19 C17 source paths")
    unchanged(source["after_sha256"], "Source differs from final backend run")
    result = read(PREFIX + FINAL_BACKEND_FILES[1])
    require(result["exit_code"] == 0 and result["source_changed_during_run"] == [], "Final backend run did not pass")
    command = result["command"]
    require("tests/" in command and "--cov-fail-under=70" in command, "Final backend command omits full-suite coverage gate")
    text = target(PREFIX + FINAL_BACKEND_FILES[2]).read_text(encoding="utf-8")
    summary = re.findall(r"(\d+) passed(?:, (\d+) skipped)?", text)
    coverage = re.findall(r"Total coverage:\s*(\d+(?:\.\d+)?)%", text)
    require(summary and coverage and float(coverage[-1]) >= 70, "Final backend summary or coverage gate is missing")
    return {
        "status": "passed_and_current_source_matches", "source_paths": len(SOURCE_PATHS),
        "passed": int(summary[-1][0]), "skipped": int(summary[-1][1] or 0),
        "coverage_percent": float(coverage[-1]),
        "receipt_sha256": {PREFIX + name: sha(PREFIX + name) for name in FINAL_BACKEND_FILES},
    }


def verify(create_accepted_source=False):
    accepted_path = OUTPUT / "accepted-source.json"
    if create_accepted_source:
        require(not accepted_path.exists(), "Refusing to rewrite frozen C17 accepted-source.json")
    unchanged(PINNED_RECEIPTS, "Pinned original receipt")
    start = read(START_PATH)
    require(start["component"] == "C17" and start["base_commit"] == BASE_COMMIT, "C17 implementation baseline differs")
    require(start["readiness_receipt_sha256"] == PINNED_RECEIPTS[start["readiness_receipt"]], "Readiness receipt pin differs")
    require(len(start["receipts"]) == 9, "Wrong prerequisite receipt count")
    unchanged(start["receipts"], "Original prerequisite receipt")
    for path in start["receipts"]:
        receipt = read(path)
        if isinstance(receipt.get("files"), dict) and "source_sha256" in receipt:
            require(aggregate(receipt["files"]) == receipt["source_sha256"], f"Original prerequisite aggregate differs: {path}")

    preservation = {}
    counts = {"unrelated_files": 30, "scientific_artifacts": 7, "serving_files": 2, "legacy_frontend_files": 106}
    require(set(start["preservation"]) == set(counts), "Preservation groups differ")
    for label, count in counts.items():
        files = start["preservation"][label]
        require(len(files) == count, f"Wrong {label} count")
        unchanged(files, label)
        preservation[label] = {"count": count, "all_match": True}
    require(len(start["prior_evidence_files"]) == 683, "Wrong earlier evidence count")
    unchanged(start["prior_evidence_files"], "Earlier evidence")
    preservation["prior_evidence_files"] = {"count": 683, "all_match": True}

    formal, formal_counts = start["formal_source_entries"], {"C03": 6, "C04": 4, "C08": 12, "C09": 14}
    require(set(formal) == set(formal_counts), "Formal prerequisite set differs")
    formal_report = {}
    for component, count in formal_counts.items():
        entries = formal[component]
        require(len(entries) == count, f"Wrong {component} source count")
        original = read(f"docs/plans/ocean-v1/evidence/{component}/verification.json")
        require(aggregate(original["files"]) == original["source_sha256"], f"Original {component} aggregate differs")
        require(original["files"] == {path: item["original_sha256"] for path, item in entries.items()},
                f"Original {component} source map differs from baseline")
        for path, item in entries.items():
            require(sha(item["accepted_receipt"]) == item["accepted_receipt_sha256"], f"Accepted {component} receipt changed")
            accepted_files = read(item["accepted_receipt"]).get("files", {})
            if path in accepted_files:
                require(accepted_files[path] == item["current_sha256"], f"Accepted {component} path differs from baseline: {path}")
        baseline = {path: item["current_sha256"] for path, item in entries.items()}
        changed = supersessions(baseline, FORMAL_SUPERSESSIONS, component)
        core = {path: digest for path, digest in baseline.items() if path not in FORMAL_SUPERSESSIONS}
        unchanged(core, component + " preserved core")
        formal_report[component] = {"paths": count, "unchanged": count - len(changed), "core_unchanged": len(core), "intentional_C17_supersessions": changed}

    c16 = read("docs/plans/ocean-v1/evidence/C16/accepted-source.json")
    require(len(c16["files"]) == 18 and aggregate(c16["files"]) == c16["source_sha256"], "C16 accepted aggregate differs")
    require(start["C16_source"] == c16, "C17 baseline differs from accepted C16 source")
    c16_changed = supersessions(c16["files"], C16_SUPERSESSIONS, "C16")
    unchanged({path: value for path, value in c16["files"].items() if path not in C16_SUPERSESSIONS}, "C16 preserved source")
    c16_verification = read("docs/plans/ocean-v1/evidence/C16/verification.json")
    c16_delivery = read("docs/plans/ocean-v1/evidence/C16/delivery.json")
    require(c16_verification["files"] == c16["files"] and c16_verification["source_sha256"] == c16_delivery["source_sha256"] == c16["source_sha256"],
            "C16 original accepted/local/delivery receipts disagree")

    api = read(PREFIX + "api-stream-verification.json")
    require(api["result"] == "passed" and api["sources_unchanged_during_run"] is True and api["tests"]["passed"] == 155,
            "Final affected API gate did not pass")
    require(len(api["source_sha256"]) == 11 and set(api["source_sha256"]) <= SOURCE_PATHS, "Final API source set differs")
    unchanged(api["source_sha256"], "Final affected API source")
    unchanged({PREFIX + name: value for name, value in api["evidence_sha256"].items()}, "Final API evidence")
    unchanged({PREFIX + name: value for name, value in api["prior_receipts_unchanged"].items()}, "Earlier C17 receipt")

    pg = read(PREFIX + "postgres-tested-source.json")
    pg_result = read(PREFIX + "postgres-result.json")
    require(pg["changed"] == [] and pg["before_sha256"] == pg["after_sha256"] and len(pg["after_sha256"]) == 14,
            "Original PostgreSQL source map differs")
    require(pg_result["source_before_sha256"] == pg_result["source_after_sha256"] == pg["after_sha256"]
            and pg_result["source_changed_during_run"] == [], "Original PostgreSQL result source map disagrees")
    require(pg_result["driver_exit_code"] == pg_result["test_exit_code"] == pg_result["stop_exit_code"] == 0
            and pg_result["server_stopped"] is True
            and pg_result["c17_schemas_remaining"] == 0 and pg_result["existing_database_urls_used"] is False,
            "Original disposable PostgreSQL acceptance did not complete safely")
    unchanged({PREFIX + name: value for name, value in pg_result["evidence_sha256"].items()}, "Original PostgreSQL evidence")
    pg_changed = supersessions(pg["after_sha256"], {"api/investigation_routes.py", "orchestration/investigations.py"}, "Original PostgreSQL source")
    recorded = {entry["path"]: entry for entry in api["intentional_supersessions"]}
    require(set(pg_changed) == set(recorded), "PostgreSQL later supersessions lack explicit API evidence")
    for path, change in pg_changed.items():
        require(change["previous_sha256"] == recorded[path]["before_sha256"] and change["C17_sha256"] == recorded[path]["after_sha256"],
                f"PostgreSQL source supersession differs from recorded API evidence: {path}")

    require(len(SOURCE_PATHS) == 19, "Wrong explicit C17 source count")
    files = {path: sha(path) for path in sorted(SOURCE_PATHS)}
    accepted = {"files": files, "source_sha256": aggregate(files), "aggregate_algorithm": AGGREGATE_ALGORITHM}
    backend = final_backend(create_accepted_source or accepted_path.exists())
    status = "not_created; current source candidate only"
    if accepted_path.exists():
        require(read(PREFIX + "accepted-source.json") == accepted, "Frozen C17 accepted source changed; receipt will not be rewritten")
        status = "frozen_and_matches"
    elif create_accepted_source:
        with accepted_path.open("x", encoding="utf-8") as stream:
            stream.write(json.dumps(accepted, indent=2) + "\n")
        status = "created_once"
    return {
        "component": "C17", "implementation_base": BASE_COMMIT,
        "source_paths": len(files), "source_sha256": accepted["source_sha256"],
        "accepted_source_status": status, "preservation": preservation,
        "formal_current_source": formal_report,
        "C16_current_source": {"paths": 18, "unchanged": 18 - len(c16_changed), "intentional_C17_supersessions": c16_changed},
        "prerequisite_receipts_unchanged": len(start["receipts"]), "pinned_receipts_unchanged": len(PINNED_RECEIPTS),
        "affected_API": {"passed": 155, "source_paths": 11, "all_current_hashes_match": True},
        "original_PostgreSQL": {"source_paths": 14, "intentional_later_supersessions": pg_changed, "original_receipts_unchanged": True},
        "final_backend": backend, "all_assertions_passed": True,
        "scope": "Hash checks only; default runs write nothing. Explicit freeze creates one accepted-source receipt only after final backend pass and never rewrites an existing receipt.",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--create-accepted-source", action="store_true")
    args = parser.parse_args()
    try:
        report = verify(args.create_accepted_source)
    except (PreservationError, OSError, ValueError, KeyError, TypeError) as exc:
        parser.exit(1, f"C17 preservation verification failed: {exc}\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
