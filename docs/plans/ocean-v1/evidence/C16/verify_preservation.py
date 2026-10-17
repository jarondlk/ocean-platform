"""Verify C16 preservation without tests or writes unless explicitly freezing.

Default usage prints a read-only preservation report. After the final source
freeze, --create-accepted-source exclusively creates accepted-source.json once;
subsequent default runs compare the current bytes with that frozen receipt.
This helper never rewrites an existing accepted-source or earlier evidence.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


OUTPUT = Path(__file__).resolve().parent
ROOT = OUTPUT.parents[4]
PREFIX = "docs/plans/ocean-v1/evidence/C16/"
START_PATH = PREFIX + "start-snapshot.json"
BASE_COMMIT = "96888675132adb420df34e75953033307e551fc5"
AGGREGATE_ALGORITHM = "SHA256 of sorted UTF-8 path:SHA256 lines with LF endings"
PINNED_RECEIPTS = {
    START_PATH: "f4806dc3a29325adfe042713f509466fcb4c9026d91029a4a6f376f3a504887c",
    PREFIX + "backend-tested-source.json": "ebe3408cc9accea947a4872fe8efeac40ccf958d5bea393cefc262db036e15f2",
    PREFIX + "backend-result.json": "617daf77afd5edfa0c206b949353c47b2afa57c766bee15fd375aeb0aebb08c4",
    PREFIX + "backend-tests.txt": "79beaf791813d8d6faf1834845f6848b9f28d11390ebe76fcb4b7646a3c3e0aa",
}
ALLOWED_SUPERSESSIONS = {
    "api/auth.py", "api/main.py", "config.py", "api/v1_runtime_routes.py",
    "tests/test_v1_runtime.py", "frontend-v1/src/runtime-app.tsx",
    "frontend-v1/README.md",
}
BACKEND_PATHS = {
    "api/auth.py", "api/main.py", "config.py", "api/v1_runtime_routes.py",
    "tests/test_v1_runtime.py", "api/catalogue_browser_routes.py",
    "orchestration/catalogue_browser.py", "schema/catalogue_browser.py",
    "tests/test_catalogue_browser.py", "tests/test_catalogue_browser_api.py",
}
FRONTEND_PATHS = {
    "frontend-v1/src/catalogue-browser.tsx",
    "frontend-v1/src/catalogue-browser.css",
    "frontend-v1/src/catalogue-service.ts",
    "frontend-v1/src/catalogue-browser-state.ts",
    "frontend-v1/tests/catalogue-service.test.ts",
    "frontend-v1/tests/catalogue-browser-state.test.ts",
    "frontend-v1/src/runtime-app.tsx", "frontend-v1/README.md",
}


class PreservationError(RuntimeError):
    """A preserved receipt or source byte differs from its accepted baseline."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise PreservationError(message)


def sha(path: str) -> str:
    target = ROOT / path
    require(not Path(path).is_absolute() and target.resolve().is_relative_to(ROOT),
            f"Path escapes the repository: {path}")
    return hashlib.sha256(target.read_bytes()).hexdigest()


def read(path: str) -> dict:
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


def aggregate(files: dict[str, str]) -> str:
    lines = "".join(f"{path}:{files[path]}\n" for path in sorted(files))
    return hashlib.sha256(lines.encode("utf-8")).hexdigest()


def unchanged(files: dict[str, str], label: str) -> None:
    for path, expected in files.items():
        require(sha(path) == expected, f"{label} changed: {path}")


def verify(create_accepted_source: bool = False) -> dict:
    accepted_path = OUTPUT / "accepted-source.json"
    if create_accepted_source:
        require(not accepted_path.exists(),
                "Refusing to rewrite frozen C16 accepted-source.json")
    unchanged(PINNED_RECEIPTS, "Pinned C16 baseline or completed backend receipt")
    start = read(START_PATH)
    require(start["component"] == "C16" and start["branch"] == "overhaul"
            and start["head"] == BASE_COMMIT
            and start["implementation_started"] is True,
            "C16 implementation baseline is invalid")
    require(start["formal_prerequisites"] == ["P00", "C14", "C15"],
            "C16 prerequisite set changed")

    preserved = {}
    expected_counts = {
        "unrelated_files": 30, "scientific_artifacts": 7,
        "serving_files": 2, "legacy_frontend_files": 106,
    }
    require(set(start["preservation"]) == set(expected_counts),
            "Preservation groups changed")
    for name, expected_count in expected_counts.items():
        files = start["preservation"][name]
        require(len(files) == expected_count, f"Wrong {name} count")
        unchanged(files, name)
        preserved[name] = {"count": len(files), "all_match": True}
    require(len(start["prior_evidence_files"]) == 617,
            "Wrong earlier evidence count")
    unchanged(start["prior_evidence_files"], "Earlier evidence")
    preserved["prior_evidence_files"] = {"count": 617, "all_match": True}
    require(len(start["receipts"]) == 6, "Wrong prerequisite receipt count")
    unchanged(start["receipts"], "Earlier prerequisite receipt")

    groups = start["source_entries"]
    require(set(groups) == {"P00", "C14", "C15"},
            "Prerequisite source groups changed")
    expected_source_counts = {"P00": 36, "C14": 14, "C15": 25}
    supersessions = {}
    for component, expected_count in expected_source_counts.items():
        entries = groups[component]
        require(len(entries) == expected_count,
                f"Wrong {component} source count")
        changed = {}
        for path, entry in entries.items():
            previous, current = entry["current_sha256"], sha(path)
            if current != previous:
                require(path in ALLOWED_SUPERSESSIONS,
                        f"Unapproved {component} supersession: {path}")
                changed[path] = {
                    "previous_sha256": previous, "C16_sha256": current,
                }
        supersessions[component] = changed
        preserved[component + "_current_source"] = {
            "count": len(entries), "unchanged": len(entries) - len(changed),
            "intentional_C16_supersessions": changed,
            "all_paths_match_or_are_explicitly_superseded": True,
        }
    require(set(supersessions["P00"]) <= {"frontend-v1/README.md"},
            "C16 changed P00 prototype source")
    c14_core = {
        path: entry["current_sha256"] for path, entry in groups["C14"].items()
        if path not in {"api/auth.py", "api/main.py", "config.py"}
    }
    require(len(c14_core) == 11, "Wrong unchanged C14 core count")
    unchanged(c14_core, "C14 core")
    preserved["C14_core"] = {"count": 11, "all_match": True}

    c15_accepted = read("docs/plans/ocean-v1/evidence/C15/accepted-source.json")
    require(aggregate(c15_accepted["files"]) == c15_accepted["source_sha256"],
            "C15 accepted source aggregate differs")
    require(c15_accepted["files"] == {
        path: entry["current_sha256"] for path, entry in groups["C15"].items()
    }, "C16 baseline does not match accepted C15 source")
    c15_start = read("docs/plans/ocean-v1/evidence/C15/start-snapshot.json")
    c08 = c15_start["source_files"]["C08"]
    require(len(c08) == 12, "Wrong C08 accepted source count")
    for entry in c08.values():
        require(sha(entry["accepted_receipt"]) == entry["accepted_receipt_sha256"],
                f"C08 accepted receipt changed: {entry['accepted_receipt']}")
    unchanged({path: entry["current_sha256"] for path, entry in c08.items()},
              "C08 accepted source")
    preserved["C08_current_source"] = {"count": 12, "all_match": True}

    backend_path = PREFIX + "backend-tested-source.json"
    backend = read(backend_path)
    require(set(backend) == BACKEND_PATHS and len(backend) == 10,
            "Completed backend source set changed")
    unchanged(backend, "Source differs from completed full backend run")
    require(read(PREFIX + "backend-result.json")["exit_code"] == 0,
            "Completed backend run failed")
    backend_log = (ROOT / (PREFIX + "backend-tests.txt")).read_text(encoding="utf-8")
    require("3895 passed, 127 skipped" in backend_log
            and "Total coverage: 84.87%" in backend_log,
            "Completed full backend receipt differs")

    paths = BACKEND_PATHS | FRONTEND_PATHS
    require(len(paths) == 18, "Wrong explicit C16 source binding count")
    files = {path: sha(path) for path in sorted(paths)}
    accepted = {
        "files": files, "source_sha256": aggregate(files),
        "aggregate_algorithm": AGGREGATE_ALGORITHM,
    }
    accepted_status = "not_created; current source candidate only"
    if accepted_path.exists():
        require(json.loads(accepted_path.read_text(encoding="utf-8")) == accepted,
                "Frozen C16 accepted source changed; receipt will not be rewritten")
        accepted_status = "frozen_and_matches"
    elif create_accepted_source:
        # Exclusive creation also rejects a racing creator; no existing file is opened
        # for writing, even when its contents would happen to match.
        with accepted_path.open("x", encoding="utf-8") as stream:
            stream.write(json.dumps(accepted, indent=2) + "\n")
        accepted_status = "created_once"

    return {
        "component": "C16", "implementation_base": BASE_COMMIT,
        "source_paths": len(files), "source_sha256": accepted["source_sha256"],
        "accepted_source_status": accepted_status, "files": files,
        "aggregate_algorithm": AGGREGATE_ALGORITHM,
        "preservation": preserved,
        "allowed_C16_supersessions": sorted(ALLOWED_SUPERSESSIONS),
        "earlier_receipts": start["receipts"],
        "pinned_C16_receipts": PINNED_RECEIPTS,
        "backend_tested_source": {
            "path": backend_path, "sha256": sha(backend_path),
            "paths": len(backend), "all_current_hashes_match": True,
            "full_run": {"passed": 3895, "skipped": 127, "coverage_percent": 84.87},
        },
        "all_assertions_passed": True,
        "scope": "Hash verification only; no tests, services, commits or pushes. "
                 "Default runs write nothing; explicit freeze creates only the new "
                 "C16 accepted-source receipt and refuses any rewrite.",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--create-accepted-source", action="store_true",
                        help="exclusively create the C16 receipt after final source freeze")
    args = parser.parse_args()
    try:
        report = verify(args.create_accepted_source)
    except (PreservationError, OSError, ValueError, KeyError, TypeError) as exc:
        parser.exit(1, f"C16 preservation verification failed: {exc}\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
