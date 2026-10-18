"""Freeze focused C18 client/state checks without rerunning unrelated suites."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import time

ROOT = Path(__file__).resolve().parents[5]
HERE = Path(__file__).parent
PATHS = [
    "frontend-v1/src/investigation-service.ts", "frontend-v1/src/research-state.ts",
    "frontend-v1/tests/investigation-service.test.ts", "frontend-v1/tests/research-state.test.ts",
]


def digest(path):
    return hashlib.sha256((ROOT / path).read_bytes()).hexdigest()


def main():
    names = ["client-tests.txt", "client-typecheck.txt", "client-python-lint.txt", "client-verification.json"]
    if any((HERE / name).exists() for name in names):
        raise SystemExit("Refusing to overwrite original C18 client verification")
    before = {path: digest(path) for path in PATHS}
    wire = json.loads((HERE / "client-wire.json").read_text())
    assert wire["source_before_sha256"] == wire["source_after_sha256"]
    assert all(digest(path) == expected for path, expected in wire["source_after_sha256"].items())
    commands = [
        ("client-tests.txt", ROOT / "frontend-v1", ["node", "--test", "--experimental-strip-types", "--disable-warning=ExperimentalWarning", "--disable-warning=MODULE_TYPELESS_PACKAGE_JSON", "tests/investigation-service.test.ts", "tests/research-state.test.ts"]),
        ("client-typecheck.txt", ROOT / "frontend-v1", ["node_modules/.bin/tsc", "--noEmit", "--strict", "--target", "ES2022", "--lib", "dom,dom.iterable,esnext", "--module", "esnext", "--moduleResolution", "bundler", "--allowImportingTsExtensions", "--skipLibCheck", "src/investigation-service.ts", "src/research-state.ts", "tests/investigation-service.test.ts", "tests/research-state.test.ts"]),
        ("client-python-lint.txt", ROOT, [".venv/bin/ruff", "check", "docs/plans/ocean-v1/evidence/C18/client_wire_probe.py", "docs/plans/ocean-v1/evidence/C18/client_verify.py"]),
    ]
    results = []
    for name, cwd, command in commands:
        start = time.monotonic()
        with (HERE / name).open("x") as output:
            result = subprocess.run(command, cwd=cwd, stdout=output, stderr=subprocess.STDOUT, check=False)
        results.append({"command": command, "cwd": str(cwd.relative_to(ROOT)), "exit_code": result.returncode, "seconds": round(time.monotonic() - start, 4), "log": name, "log_sha256": digest(str((HERE / name).relative_to(ROOT)))})
        assert result.returncode == 0, name
    after = {path: digest(path) for path in PATHS}
    assert before == after
    tests = (HERE / "client-tests.txt").read_text()
    assert "# tests 128\n" in tests and "# pass 128\n" in tests and "# fail 0\n" in tests
    result = {
        "verified_at": datetime.now(timezone.utc).isoformat(), "source_before_sha256": before, "source_after_sha256": after, "source_changed": [],
        "checks": results, "tests_passed": 128, "tests_failed": 0,
        "actual_http_wire": {"requests": wire["request_count"], "methods": wire["method_count"], "source_sha256": wire["source_after_sha256"], "sha256": digest(str((HERE / "client-wire.json").relative_to(ROOT)))},
        "boundaries": ["Captured actual C17 ASGI HTTP with sealed synthetic fixtures and TEST principal; TypeScript transport consumes immutable captured responses", "No browser, listening socket, PostgreSQL, production OIDC or real-data claim", "Standalone focused TypeScript check; root owns full frontend build/test/browser acceptance", "Bounded real request/response transport, no implicit fixture fallback, account/permission-bound volatile drafts and exact mutation replay", "Original wire capture remains immutable; optional null scope fields validated without altering retained wire DTO"],
    }
    with (HERE / "client-verification.json").open("x") as output:
        json.dump(result, output, indent=2, sort_keys=True)
        output.write("\n")
    print(json.dumps({"tests_passed": 128, "wire_requests": wire["request_count"], "wire_methods": wire["method_count"], "receipt_sha256": digest(str((HERE / "client-verification.json").relative_to(ROOT)))}, sort_keys=True))


if __name__ == "__main__":
    main()
